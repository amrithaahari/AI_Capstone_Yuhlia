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


def fetch_openai_response(prompt: str, system_prompt: Optional[str] = None) -> str:
    client = _get_openai_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.4,
        max_tokens=900,
    )
    return resp.choices[0].message.content or ""

def _offline_fallback_response(goal: str, intent: str) -> str:
    """
    Used when OPENAI_API_KEY is not set.
    Allows Streamlit + DB to function without LLM calls.
    """
    if intent == Intent.yuh_related.value:
        return (
            "Yuh offers a range of investment products such as ETFs and other instruments.\n\n"
            "You can explore the available products in the table below."
        )

    if intent == Intent.basic_knowledge.value:
        return (
            "Investing is about putting money into assets with the aim of growing it over time.\n\n"
            "Different products have different levels of risk, cost, and diversification."
        )

    return (
        "I can help explain investing concepts or show what investment products are available in Yuh."
    )



def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    t = t.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    return t


_PRODUCT_FILTER_SYSTEM = """You extract product search filters for a Yuh product catalog query.

Return ONLY valid JSON with this schema:
{
  "type_contains": null|string,
  "sector": null|string,
  "region": null|string,
  "currency": null|string,
  "stock_exchange": null|string,
  "esg_min": null|number,
  "ter_max": null|number,
  "commission_free": null|boolean
}

Rules:
- Only set fields that are clearly implied by the user query. Otherwise null.
- If user asks for "low fee" / "low cost" / "cheap", set ter_max=0.30 by default.
- If user asks "commission-free" / "no commission" or "special savings", set commission_free=true.
- If user asks for ESG/sustainable/green, set esg_min=60 by default (ESG_score scale assumed 0–100).
- If user asks for "low fee ETFs", set type_contains="ETF" and commission_free=true (so Type contains Special savings).
- Never invent specific sectors/regions/exchanges unless the user says them.
"""

def parse_product_filters(user_query: str) -> Dict[str, Any]:
    q = (user_query or "").lower()

    f: Dict[str, Any] = {
        "type_contains": None,
        "sector": None,
        "region": None,
        "currency": None,
        "stock_exchange": None,
        "esg_min": None,
        "ter_max": None,
        "commission_free": None,
    }

    # deterministic hints
    if "commission free" in q or "commission-free" in q or "no commission" in q or "special savings" in q:
        f["commission_free"] = True

    if ("sustainable" in q or "esg" in q or "green" in q):
        f["esg_grade_in"] = ["AAA", "AA", "A"]

    if ("low fee" in q or "low cost" in q or "cheap" in q) and ("etf" in q or "etfs" in q):
        f["type_contains"] = "Special savings (ETF)"

    # if they explicitly mention ETFs, set type_contains
    if "etf" in q or "etfs" in q:
        f["type_contains"] = "ETF"

    # If we got anything deterministically, return
    if any(v is not None for v in f.values()):
        return f

    # ---- SAFE GUARD: no API key, do NOT call LLM ----
    if not LLM_ENABLED:
        return f

    # LLM fallback (only if key exists)
    out = _strip_code_fences(fetch_openai_response(
        prompt=f"User query:\n{user_query}\n",
        system_prompt=_PRODUCT_FILTER_SYSTEM
    ))

    try:
        data = json.loads(out)
        for k in f.keys():
            if k not in data:
                data[k] = None
        return data
    except Exception:
        return f

# -------------------------
# Intent classification
# -------------------------
# classify_intent() without followup_answers (LLM + high-precision Yuh override)

_YUH_OVERRIDE_PATTERNS = [
    r"\byuh\b",
    r"\bin the app\b",
    r"\bon yuh\b",
    r"\bdoes yuh have\b",
    r"\bdo you have\b",
    r"\bwhat (do you|does yuh) (offer|have)\b",
    r"\bavailable (in|on)\b",
]

_CLASSIFIER_SYSTEM_PROMPT = """You are an intent classifier for an investing discovery assistant in the Yuh app.

Pick EXACTLY ONE category:

- yuh_related: user asks what Yuh offers/has in-app, availability of ETFs/stocks/crypto/funds, or mentions "yuh", "in the app", "on yuh".
- basic_knowledge: user asks about investing concepts (ETF, index fund, fees, risk, diversification, returns), how investing works, or learning to invest.
- unknown: unrelated to investing/Yuh investing discovery, or not enough info.

Return ONLY valid JSON:
{"category":"basic_knowledge|yuh_related|unknown","confidence":0.0-1.0,"reasoning":"brief"}"""

def _offline_classify_intent(goal: str) -> ClassificationResult:
    g = (goal or "").lower().strip()

    # High precision yuh routing
    if any(re.search(p, g) for p in _YUH_OVERRIDE_PATTERNS):
        return ClassificationResult(
            category=Intent.yuh_related.value,
            confidence=0.95,
            reasoning="offline_heuristic_yuh_override",
        )

    # Basic investing concept routing (simple, conservative)
    basic_markers = [
        "what is", "what's", "etf", "index fund", "fees", "ter", "risk",
        "diversification", "returns", "stocks", "bonds", "portfolio",
        "investing", "invest", "compound", "inflation"
    ]
    if any(m in g for m in basic_markers):
        return ClassificationResult(
            category=Intent.basic_knowledge.value,
            confidence=0.70,
            reasoning="offline_heuristic_basic_knowledge",
        )

    return ClassificationResult(
        category=Intent.unknown.value,
        confidence=0.55,
        reasoning="offline_heuristic_unknown",
    )



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
        fetch_openai_response(f"User message:\n{goal}\n", _CLASSIFIER_SYSTEM_PROMPT)
    )

    try:
        data = json.loads(out)
        cat = (data.get("category") or Intent.unknown.value).strip()
        conf = float(data.get("confidence", 0.0))
        reasoning = (data.get("reasoning") or "").strip()

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
                reasoning=(reasoning + " | low_confidence").strip(" |"),
            )

        return ClassificationResult(category=cat, confidence=conf, reasoning=reasoning)

    except Exception:
        return ClassificationResult(category=Intent.unknown.value, confidence=0.0, reasoning="parse_error")

# -------------------------
# Response generation
# -------------------------
_AVAILABILITY_PATTERNS = [
    r"\bdoes yuh have\b",
    r"\bdo you have\b",
    r"\bis (it|this) available\b",
    r"\bavailable (in|on) (yuh|the app)\b",
    r"\bon yuh\b",
    r"\bin the app\b",
    r"\byuh\b.*\b(etf|etfs|stock|stocks|share|shares|crypto|cryptos|index fund|funds)\b",
]


def _user_asked_availability_or_options(goal: str) -> bool:
    g = (goal or "").lower().strip()
    return any(re.search(p, g) for p in _AVAILABILITY_PATTERNS)


def _format_products(products: List[Product], limit: int = 30) -> str:
    if not products:
        return "- (No matching products found)"
    lines = []
    for p in products[:limit]:
        name = getattr(p, "name", "") or ""
        desc = getattr(p, "description", "") or ""
        # Keep each entry compact; the model can elaborate if needed.
        if desc:
            lines.append(f"- {name}: {desc}")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines)


def generate_response(
    goal: str,
    intent: str,
    products: List[Product],
    followup_answers: List[str],
    rewrite_hint: str = "",
) -> str:

    if not LLM_ENABLED:
        return _offline_fallback_response(goal, intent)

    # Decide if product catalog should be used
    user_asked_availability = _user_asked_availability_or_options(goal)
    should_use_products = (intent == Intent.yuh_related.value) or user_asked_availability

    system_prompt = """You are Yulia, an investing discovery assistant inside the Yuh app.

Non-negotiable behavior:
1) ANSWER THE USER’S QUESTION FIRST in 1–2 sentences. 
2) Be educational and neutral. No personal recommendations. No “you should / I recommend”.
3) No trading instructions, no timing, no predictions, no guarantees, never “risk-free”.
4) Do not ask about amounts, balances, income, or how much they can invest.

Products:
- Never list or name specific products in the text response.
- Product availability and examples are shown separately in the UI.
- Do not say "no matching products" or similar statements.


Follow-ups:
- Ask at most 1–2 follow-up questions, only if it helps answer next.

Style:
- Plain language. Define jargon in-line.
- Keep it short and directly relevant.
- You can provide simple examples that will help demystify a concept.

Hard bans: "you should", "I recommend", "buy", "sell", "invest in X", "guaranteed", "risk-free", "start by", "the next step is".
"""

    product_list = _format_products(products, limit=40) if should_use_products else "- (Not provided for this intent)"

    prompt = f"""User message:
    {goal}

    Intent:
    {intent}

    Write the response using this structure:

    Direct answer (1–2 sentences).
    - Must directly address the user's question.
    - If they ask about availability, answer at a high level (e.g. "Yuh offers ETFs and other investment products").

    Short explanation (2–6 bullets).
    - Explain the concept in simple terms.
    - No product names.
    - No instructions or recommendations.

    Optional follow-up:
    - Ask at most 1 clarifying question, only if it helps refine understanding.
    - Never ask about money amounts or timing.
    """

    if rewrite_hint:
        prompt += f"\nRewrite constraint: {rewrite_hint}\n"

    return fetch_openai_response(prompt, system_prompt).strip()


# -------------------------
# Guardrails
# -------------------------
def check_guardrails(text: str) -> GuardrailResult:
    if not LLM_ENABLED:
        # In offline mode, assume text is safe.
        # We already control generation, so this is acceptable.
        return GuardrailResult(
            passed=True,
            reason="offline_mode_no_guardrails",
            severity="none",
            category="none",
        )

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
   - "will outperform", "guaranteed", "risk-free", "no risk", "safe return", "cannot lose", "sure profit"

Minor issue (passed=true) if the text only includes recommendation-like adjectives or soft persuasion WITHOUT telling the user what to do:
- "ideal", "best", "great option", "perfect", "top pick", "good choice"

Output ONLY valid JSON:
{"passed": true|false, "severity": "none|minor|fail", "category": "none|advice|instructions|prediction|recommendation_wording|risk_free_claim", "reason": "short string or null"}"""

    out = _strip_code_fences(fetch_openai_response(f"TEXT:\n{text}", system_prompt))

    try:
        data = json.loads(out)
        return GuardrailResult(
            passed=bool(data.get("passed", False)),
            reason=data.get("reason"),
            severity=data.get("severity", "fail"),
            category=data.get("category", "none"),
        )
    except Exception:
        t = (text or "").lower()

        hard_patterns = [
            r"\bi recommend\b",
            r"\byou should\b",
            r"\byou need to\b",
            r"\b(buy|sell)\b.*\b(now|today|immediately)\b",
            r"\bguarantee(d)?\b",
            r"\brisk[- ]?free\b",
            r"\bcannot lose\b",
            r"\bwill outperform\b",
            r"\bstart by\b",
            r"\bthe next step is\b",
            r"\byou can begin with\b",
        ]
        if any(re.search(p, t) for p in hard_patterns):
            return GuardrailResult(
                passed=False,
                reason="heuristic_fail_hard_advice_or_guarantee",
                severity="fail",
                category="advice",
            )

        # If parsing fails but there's no obvious hard violation, do not block.
        return GuardrailResult(
            passed=True,
            reason="heuristic_pass_parse_error",
            severity="minor",
            category="none",
        )
