# agents.py
import json
import os
import re
from typing import List, Optional, Dict, Any

from config import Intent, LLM_ENABLED
from models import ClassificationResult, GuardrailResult, Product

DEFAULT_GEN_MODEL = "gpt-4o-mini"

NO_TEMPERATURE_MODELS = {
    "gpt-5.2",
    "gpt-5-mini",
}

# -------------------------
# Usage tracking (cost)
# -------------------------
# Aggregates OpenAI usage for one "request" (one yulia_reply call).
# eval_models.py will price this using MODEL_PRICES_PER_1M.
_USAGE = {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "calls": 0,
    "by_model": {},  # model -> same fields
}

def usage_reset() -> None:
    _USAGE["input_tokens"] = 0
    _USAGE["output_tokens"] = 0
    _USAGE["total_tokens"] = 0
    _USAGE["calls"] = 0
    _USAGE["by_model"] = {}

def usage_get() -> Dict[str, Any]:
    # return a shallow copy so callers don't mutate global state accidentally
    return {
        "input_tokens": _USAGE["input_tokens"],
        "output_tokens": _USAGE["output_tokens"],
        "total_tokens": _USAGE["total_tokens"],
        "calls": _USAGE["calls"],
        "by_model": dict(_USAGE["by_model"]),
    }

def _usage_add(model: str, input_tokens: int, output_tokens: int, total_tokens: int) -> None:
    _USAGE["input_tokens"] += int(input_tokens)
    _USAGE["output_tokens"] += int(output_tokens)
    _USAGE["total_tokens"] += int(total_tokens)
    _USAGE["calls"] += 1

    m = (model or "unknown").strip()
    bm = _USAGE["by_model"].setdefault(m, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "calls": 0})
    bm["input_tokens"] += int(input_tokens)
    bm["output_tokens"] += int(output_tokens)
    bm["total_tokens"] += int(total_tokens)
    bm["calls"] += 1

def record_usage(model: str, input_tokens: int, output_tokens: int = 0, total_tokens: Optional[int] = None) -> None:
    # for embeddings (output_tokens=0); total_tokens is usually equal to input_tokens
    if total_tokens is None:
        total_tokens = int(input_tokens) + int(output_tokens)
    _usage_add(model, int(input_tokens), int(output_tokens), int(total_tokens))

# -------------------------
# OpenAI client helpers
# -------------------------
def _get_openai_client():
    from openai import OpenAI
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def fetch_openai_response(
    user_prompt: str,
    system_prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 500,
) -> str:
    """
    Unified OpenAI call wrapper.

    Compatibility rules:
    - GPT-5 family:
        * does NOT accept temperature
        * does NOT accept max_tokens
        * requires max_completion_tokens
    - GPT-4.x / GPT-4o:
        * accepts temperature
        * accepts max_tokens
    """
    client = _get_openai_client()

    default_model = os.getenv("YULIA_GEN_MODEL", "gpt-4o-mini")
    chosen_model = (model or default_model).strip()

    messages = [
        {"role": "system", "content": system_prompt or ""},
        {"role": "user", "content": user_prompt or ""},
    ]

    is_gpt5 = chosen_model.startswith("gpt-5")

    kwargs = {
        "model": chosen_model,
        "messages": messages,
    }

    if is_gpt5:
        # GPT-5 models have a restricted parameter surface
        kwargs["max_completion_tokens"] = int(max_tokens)
    else:
        kwargs["temperature"] = float(temperature)
        kwargs["max_tokens"] = int(max_tokens)

    resp = client.chat.completions.create(**kwargs)
    # ---- record token usage for cost ----
    try:
        usage = getattr(resp, "usage", None)
        in_tok = int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else 0
        total_tok = int(getattr(usage, "total_tokens", 0) or 0) if usage is not None else (in_tok + out_tok)

        # Some SDKs/models also expose input_tokens/output_tokens
        if usage is not None and in_tok == 0 and hasattr(usage, "input_tokens"):
            in_tok = int(getattr(usage, "input_tokens", 0) or 0)
        if usage is not None and out_tok == 0 and hasattr(usage, "output_tokens"):
            out_tok = int(getattr(usage, "output_tokens", 0) or 0)
        if total_tok == 0:
            total_tok = in_tok + out_tok

        _usage_add(chosen_model, in_tok, out_tok, total_tok)
    except Exception:
        pass


    return (resp.choices[0].message.content or "").strip()



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

    schema = (
        "Return ONLY valid JSON (no prose, no markdown, no code fences) with exactly these keys:\n"
        '{\n'
        '  "type_contains_all": [string],\n'
        '  "region": string or null,\n'
        '  "max_ter": number or null,\n'
        '  "esg_scores_in": [string]\n'
        '}\n'
        "Rules:\n"
        "- If unknown, use null or []\n"
        "- Keep lists short\n"
    )

    prompt = f"USER_MESSAGE:\n{goal}\n\n{schema}"

    # Keep this small; filters should never need a large completion.
    raw = fetch_openai_response(
        user_prompt=prompt,
        system_prompt=_FILTER_EXTRACTOR_SYSTEM_PROMPT,
        temperature=0.0,
        max_tokens=220,
    )
    raw = _strip_code_fences(raw)

    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        # One repair attempt; still same model.
        repair_prompt = (
            "Fix the following into valid JSON ONLY (no prose, no markdown). "
            "Output must match the schema exactly.\n\n"
            f"BAD_OUTPUT:\n{raw}\n\n{schema}"
        )
        raw2 = fetch_openai_response(
            user_prompt=repair_prompt,
            system_prompt=_FILTER_EXTRACTOR_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=220,
        )
        raw2 = _strip_code_fences(raw2)
        try:
            data2 = json.loads(raw2)
            return data2 if isinstance(data2, dict) else {}
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

    # Only yuh_related is allowed to surface products or the table token
    products_allowed = (intent == Intent.yuh_related.value)
    has_products = bool(products_allowed and products)

    # user_asked_availability = _user_asked_availability_or_options(goal)
    # should_use_products = (intent == Intent.yuh_related.value) or user_asked_availability

    system_prompt = """You are Yulia, an investing discovery assistant inside the Yuh app.

You must NOT provide financial advice or recommendations.
You must NOT use imperative language telling the user what to do.

When describing "investment options on yuh", only use these high-level categories:
- Shares
- ETFs
- Digital assets / crypto
- Trending themes
- Bonds
- 3A for retirement or long-term investing in Switzerland
- Commission free ETFs
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

    product_list = _format_products(products, limit=40) if products_allowed else "- (Not provided for this intent)"

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

Response requirements:
- Answer the user’s question clearly.
- If the requested product does not exist directly, explain the closest equivalent at a category level.
- Structure:
  1) Direct answer in the first sentence
  2) Short explanation clarifying terminology or equivalence
  3) Bullet points with key facts
  4) Brief limitations or caveats


Product table token rules (STRICT):
- Never invent products.
- Never output any table content.
- Only if intent is "yuh_related" AND products list is non-empty:
  - Include this exact 1-sentence intro:
    "Here are some of our relevant products listed in the table below. Please note that these are just for your information and in no way or form are advice or recommendations:"
  - Then output this token on its own line:
    [[PRODUCT_TABLE]]
- Otherwise:
  - Do NOT mention a table
  - Do NOT output the token

Optional follow-up question (0 or 1):
- Only if needed to proceed and must be related to products at yuh.
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
