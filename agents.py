# agents.py
import json
import os
import re
from typing import List, Optional, Dict, Any

from config import Intent
from config import LLM_ENABLED
from models import ClassificationResult, GuardrailResult, Product


# -------------------------
# OpenAI client helpers
# -------------------------
def _get_openai_client():
    from openai import OpenAI
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def fetch_openai_response(user_prompt: str, system_prompt: str, model: str = "gpt-4o-mini") -> str:
    client = _get_openai_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""

def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    # remove ```json ... ``` or ``` ... ```
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


# -------------------------
# Offline fallbacks
# -------------------------
def _offline_classify_intent(goal: str) -> ClassificationResult:
    g = (goal or "").lower()
    if "yuh" in g or "in the app" in g or "on yuh" in g:
        return ClassificationResult(category=Intent.yuh_related.value, confidence=0.8, reasoning="offline_keyword")
    return ClassificationResult(category=Intent.basic_knowledge.value, confidence=0.6, reasoning="offline_default")

def _offline_fallback_response(goal: str, intent: str) -> str:
    if intent == Intent.yuh_related.value:
        return "Yuh offers several investment product types in the Invest section. Ask what type you want (e.g., ETFs, shares, crypto) or what constraints you care about (e.g., world, low cost, ESG)."
    return "I can explain investing concepts and definitions. What are you trying to understand?"

def _format_products(products: List[Product], limit: int = 20) -> str:
    if not products:
        return "- (No matching products found)"
    lines = []
    for p in products[:limit]:
        # keep it compact; generator is instructed not to name products to user
        lines.append(
            f"- Name={p.name!r}; Type={p.type!r}; Region={getattr(p,'region',None)!r}; "
            f"TER={getattr(p,'ter',None)!r}; ESG_score={getattr(p,'esg',None)!r}"
        )
    if len(products) > limit:
        lines.append(f"- ... ({len(products)-limit} more not shown)")
    return "\n".join(lines)


# -------------------------
# Intent classification
# -------------------------
_YUH_OVERRIDE_PATTERNS = [
    r"\byuh\b",
    r"\bin the app\b",
    r"\bon yuh\b",
    r"\bdoes yuh have\b",
    r"\bdo you have\b",
    r"\bwhat (do you|does yuh) (offer|have)\b",
    r"\bavailable (in|on)\b",
    r"\bwhat (investment )?options\b",
    r"\bwhat can i invest in\b",
    r"\binvestment options\b",
]

_CLASSIFIER_SYSTEM_PROMPT = """You are an intent classifier for an investing discovery assistant in the Yuh app.

Pick EXACTLY ONE category:

- yuh_related: user asks what Yuh offers/has/availability/options in the Yuh Invest section (including "what investment options are available", "what can I invest in on yuh")
- basic_knowledge: user asks general investing questions not tied to Yuh's catalog
- unknown: unclear / cannot decide

Return strict JSON:
{"category": "...", "confidence": 0-1, "reasoning": "short_reason"}

Only allowed categories:
- basic_knowledge
- yuh_related
- unknown
"""

def classify_intent(goal: str, followup_answers: List[str]) -> ClassificationResult:
    g = (goal or "").lower().strip()

    # High-precision override for Yuh availability questions
    if any(re.search(p, g) for p in _YUH_OVERRIDE_PATTERNS):
        return ClassificationResult(
            category=Intent.yuh_related.value,
            confidence=0.95,
            reasoning="heuristic_yuh_override",
        )

    if not LLM_ENABLED:
        return _offline_classify_intent(goal)

    out = _strip_code_fences(
        fetch_openai_response(
            user_prompt=f"USER_MESSAGE:\n{goal}\n\nReturn JSON only.",
            system_prompt=_CLASSIFIER_SYSTEM_PROMPT,
        )
    )

    try:
        data = json.loads(out)
        cat = str(data.get("category", "")).strip()
        conf = float(data.get("confidence", 0.0))
        reasoning = str(data.get("reasoning", "")).strip()

        allowed = {
            Intent.basic_knowledge.value,
            Intent.yuh_related.value,
            Intent.unknown.value,
        }
        if cat not in allowed:
            return ClassificationResult(category=Intent.unknown.value, confidence=0.0, reasoning="invalid_category")

        conf = min(max(conf, 0.0), 1.0)

        # Low-confidence fallback to unknown to reduce wrong routing
        if conf < 0.55:
            return ClassificationResult(
                category=Intent.unknown.value,
                confidence=conf,
                reasoning=f"low_confidence:{reasoning}",
            )

        return ClassificationResult(category=cat, confidence=conf, reasoning=reasoning)

    except Exception:
        return ClassificationResult(category=Intent.unknown.value, confidence=0.0, reasoning="parse_error")


# -------------------------
# LLM filter extraction (NEW)
# -------------------------
_FILTER_EXTRACTOR_SYSTEM_PROMPT = """You are a strict filter-extraction agent for a SQLite product catalog.

Output a single JSON object only (no markdown, no commentary).
Only these keys are allowed:
- "type_contains_all": array of strings (substrings that must appear in the Type field, case-insensitive)
- "region": string or null (exact match value, e.g., "World")
- "max_ter": number or null (e.g., 0.003 for 0.30%)
- "esg_scores_in": array of strings or null (subset of ["AAA","AA","A","BBB","BB","B","CCC","D"])
- "order_by_esg": boolean
- "notes": string (optional; e.g., "overview_query" or a disclaimer note)

Interpretation rules:
- If user asks for "sustainable"/"ethical"/"responsible"/"green"/"impact"/"durable":
  set esg_scores_in=["AAA","AA","A"] and order_by_esg=true.
- "sustainable shares/stocks": also include "Share" in type_contains_all
- "sustainable ETFs": also include "ETF" in type_contains_all
- "low-cost/cheap/low fee/low TER": set max_ter=0.003 unless user specified a cap.
- "world/global/worldwide": set region="World"
- "special savings"/"commission-free": include both "ETF" and "Special savings" in type_contains_all.
- Exclusions like "avoid defense/military/weapons": schema cannot guarantee exclusions.
  Treat as ethical intent (AAA/AA/A) and add a short disclaimer in notes.
- If the message is a broad overview question like "What investment options are available on yuh?":
  return empty filters (null/empty) and set notes="overview_query".
- If the user asks about crypto/cryptocurrencies/digital assets or asks what cryptos are available:
  set type_contains_all=["Crypto"] and leave other filters null unless explicitly stated.

"""

def extract_filters(goal: str) -> Dict[str, Any]:
    if not LLM_ENABLED:
        return {}

    raw = fetch_openai_response(
        user_prompt=f"USER_MESSAGE:\n{goal}\n\nReturn JSON only.",
        system_prompt=_FILTER_EXTRACTOR_SYSTEM_PROMPT,
    )
    raw = _strip_code_fences(raw)

    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# -------------------------
# Response generation
# -------------------------
def _user_asked_availability_or_options(text: str) -> bool:
    t = (text or "").lower()
    return any(
        k in t for k in [
            "available", "what do you have", "what can i invest in", "options", "offer", "does yuh have", "on yuh"
        ]
    )

def generate_response(
    goal: str,
    intent: str,
    products: List[Product],
    followup_answers: List[str],
    rewrite_hint: str = "",
) -> str:

    if not LLM_ENABLED:
        return _offline_fallback_response(goal, intent)

    user_asked_availability = _user_asked_availability_or_options(goal)
    should_use_products = (intent == Intent.yuh_related.value) or user_asked_availability

    system_prompt = """You are Yulia, an investing discovery assistant inside the Yuh app.

You must NOT provide financial advice or recommendations.
You must NOT use imperative language telling the user what to do.

When describing "investment options on yuh", only use these high-level categories:
- Shares
- ETFs
- Digital assets / crypto
- Trending themes
- Bonds
Do NOT introduce categories like "funds" unless the user explicitly mentions "funds".

IMPORTANT UI RULES:
- Never output a markdown/ASCII table.
- Never list products as rows/columns.
- The UI will render the product table separately.

If the prompt contains "CATALOG_SEARCH_RESULT: 0_MATCHES":
- Say clearly that no products matched the current filters.
- Ask exactly ONE short follow-up question that's relevant to the user question and make it lead to displaying specific yuh products in the following response.
- Do not recommend specific products.

Follow-ups:
- Ask at most 1 follow-up question, only if it helps proceed in a way where it leads to displaying yuh products in a table.
- Never ask about amounts, expected returns, or timing.

Style:
- Plain language. Define jargon in-line.
- Keep it short and directly relevant.

Hard bans: "you should", "I recommend", "buy", "sell", "invest in X", "guaranteed", "risk-free", "start by", "the next step is".
"""

    product_list = _format_products(products, limit=40) if should_use_products else "- (Not provided for this intent)"

    # If we are processing a follow-up answer, include it explicitly
    followup_block = ""
    if followup_answers:
        followup_block = "Follow-up answer(s) from the user:\n" + "\n".join([f"- {a}" for a in followup_answers])

    prompt = f"""User message:
{goal}

Intent:
{intent}

{followup_block}

Product matches (internal grounding; do not name products in the response):
{product_list}

* Answer the user’s question clearly.
* If the product does not exist directly, explain the closest equivalent.
* Structure the response as follows:
1. Direct answer in the first sentence
2. Short explanation clarifying terminology or equivalence
3. Bullet points with key facts
4. A brief limitations or caveats section

* Avoid marketing language.
* Avoid assumptions about the user’s goals.
* Use simple examples where helpful.

Table intro (1 sentence).
- If products are provided OR the user asked about availability/options, include:
"Here are some of our <relevant product category> listed in the table below. Please note that these are just for your information and in no way or form are advice or recommendations:"
- Then output this token on its own line:
[[PRODUCT_TABLE]]
- Do NOT output any table content.

Optional follow-up question(s) (0–1 question).
- Only if needed to proceed and should be related to investment products at yuh.
- Never ask about amounts, expected returns, or timing.

{rewrite_hint}
"""

    return fetch_openai_response(prompt, system_prompt)

# -------------------------
# Guardrails
# -------------------------
def check_guardrails(text: str) -> GuardrailResult:
    if not LLM_ENABLED:
        return GuardrailResult(passed=True, reason=None, severity="none", category="none")

    system_prompt = """You are a safety checker for an investment discovery assistant.

Goal:
- Catch clear financial advice and trading instructions.
- Do NOT fail purely educational content.
- Be strict about imperative guidance that tells the user what to do.

Fail (passed=false) ONLY if the text contains ANY of:
1) Direct recommendations or instructions to act:
   - "I recommend", "you should", "you need to", "buy X", "sell X", "pick X", "go with X", "invest in X now"
   - "start by", "the next step is", "you can begin with" (when used as instructions to the user)
2) Explicit buy/sell/trade instructions or timing:
   - "buy today/now", "sell immediately", "enter/exit", "open a position", "when to buy/sell"
3) Performance predictions or guarantees:
   - "will outperform", "guaranteed", "no risk", "risk-free"

Return strict JSON only:
{"passed": true/false, "reason": "...", "severity":"low|medium|high", "category":"advice|timing|guarantee|none"}
"""

    out = _strip_code_fences(fetch_openai_response(f"TEXT:\n{text}\n\nReturn JSON only.", system_prompt))
    try:
        data = json.loads(out)
        passed = bool(data.get("passed", False))
        reason = data.get("reason", None)
        severity = str(data.get("severity", "none"))
        category = str(data.get("category", "none"))
        return GuardrailResult(passed=passed, reason=reason, severity=severity, category=category)
    except Exception:
        # Conservative: if parsing fails, don't block; just note parse error
        return GuardrailResult(passed=True, reason="guardrail_parse_error", severity="low", category="none")
