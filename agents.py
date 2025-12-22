# agents.py
import json
import os
import re
from typing import List, Optional

from config import Intent
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


def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    t = t.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    return t


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


def classify_intent(goal: str, followup_answers: List[str]) -> ClassificationResult:
    g = (goal or "").lower().strip()

    # High-precision override for Yuh availability questions
    if any(re.search(p, g) for p in _YUH_OVERRIDE_PATTERNS):
        return ClassificationResult(
            category=Intent.yuh_related.value,
            confidence=0.95,
            reasoning="heuristic_yuh_override",
        )

    out = _strip_code_fences(fetch_openai_response(f"User message:\n{goal}\n", _CLASSIFIER_SYSTEM_PROMPT))

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
- If the user asks about what Yuh has (availability), answer yes/no/unknown and then show relevant in-app products from the provided list (as examples, not recommendations).
- If the user asks a pure concept question, do not list products unless they explicitly asked for options in Yuh.

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

Available in-app products (use only if intent is yuh_related OR user asked what’s available in Yuh):
{product_list}

Write the response using this structure:

A) Direct answer (1–2 sentences). Must directly address the question.

B) Short explanation (2–6 bullets max). Only relevant points.

C) If intent is yuh_related (or the user asked what’s available in Yuh):
- State availability based on the provided products list.
- List up to 5 relevant products as "Examples you can explore in Yuh" (not recommendations).
- If none match, say you can’t see matching items in the provided list.

D) Optional follow-up: 0–2 questions, only if needed. Never ask about money amounts.
"""

    if rewrite_hint:
        prompt += f"\nRewrite constraint: {rewrite_hint}\n"

    return fetch_openai_response(prompt, system_prompt).strip()


# -------------------------
# Guardrails
# -------------------------
def check_guardrails(text: str) -> GuardrailResult:
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
