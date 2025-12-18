import json
import os
from typing import List, Optional
import re

from config import Intent
from models import ClassificationResult, GuardrailResult, Product

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

def classify_intent(goal: str, followup_answers: List[str]) -> ClassificationResult:
    context = f"Goal:\n{goal}\n"
    if followup_answers:
        context += "\nFollow-up answers:\n" + "\n".join([f"- {a}" for a in followup_answers])

    system_prompt = """You are an intent classifier for an investment discovery assistant.
Classify the user into exactly one category:
- beginner
- capital_preservation
- unknown

Return ONLY valid JSON:
{"category":"beginner|capital_preservation|unknown","confidence":0.0-1.0,"reasoning":"brief"}"""

    out = fetch_openai_response(context, system_prompt).strip()
    out = out.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(out)
        cat = data.get("category", "unknown")
        conf = float(data.get("confidence", 0.0))
        reasoning = data.get("reasoning", "")
        if cat not in {Intent.beginner.value, Intent.capital_preservation.value, Intent.unknown.value}:
            cat = Intent.unknown.value
        return ClassificationResult(category=cat, confidence=conf, reasoning=reasoning)
    except Exception:
        return ClassificationResult(category=Intent.unknown.value, confidence=0.0, reasoning="parse_error")

from typing import List
import re

from typing import List
import re

def generate_response(
    goal: str,
    intent: str,
    products: List[Product],
    followup_answers: List[str],
    rewrite_hint: str = "",
) -> str:
    goal_clean = (goal or "").strip().lower()

    # -------------------------
    # Decide whether to show products
    # -------------------------
    asked_for_products = any(
        kw in goal_clean
        for kw in [
            "what options",
            "what products",
            "available",
            "which etf",
            "show me",
            "list",
        ]
    )

    is_first_turn = len(followup_answers) == 0
    should_show_products = asked_for_products or not is_first_turn

    # -------------------------
    # System prompt (global rules)
    # -------------------------
    system_prompt = """You are Yulia, an educational investment discovery assistant.

Rules:
- No financial advice or recommendations
- No buy/sell instructions
- No predictions or guarantees
- Never claim anything is risk-free
- Do not ask about amounts, balances, or timing

Beginner intent:
- Use very simple language
- Avoid jargon and acronyms (explain if used)
- Do not mention TER unless the user already asked about fees

Conversation:
- Always ask 2–3 relevant follow-up questions
- If this is the first response to a beginner and they did not ask for products, do NOT list products.
"""

    # -------------------------
    # Prompt A: First-touch beginner (no products)
    # -------------------------
    if intent == "beginner" and not should_show_products:
        prompt = f"""
User goal: {goal}

Write a simple, reassuring explanation of investing for someone who has never invested before.

Requirements:
- Explain investing in plain language (use an analogy if helpful)
- Explain what an ETF is in ONE simple sentence
- Give a short “how to get started” checklist without telling them what to buy
- Do NOT list products
- Ask exactly 3 follow-up questions:
  1) short-term vs long-term money
  2) broad/simple vs themes (e.g. Switzerland, tech)
  3) whether they have ever invested before (yes/no)
"""

    # -------------------------
    # Prompt B: Product exploration phase
    # -------------------------
    else:
        product_list = "\n".join(
            f"- {p.name}: {p.description}"
            for p in products
        ) or "- (No matching products found)"

        prompt = f"""
User goal: {goal}
Intent: {intent}

Products available in-app (examples only):
{product_list}

Write a beginner-friendly response that:
- Explains how to compare options at a high level:
  - what they hold (broad vs narrow)
  - cost/fees (plain language, no jargon)
  - risk in simple terms
- Mentions up to 5 products as examples to explore (not recommendations)
- Asks 2 follow-up questions to refine the next step
"""

    # -------------------------
    # Optional rewrite constraint (used only after guardrail failure)
    # -------------------------
    if rewrite_hint:
        prompt += f"\nRewrite constraint: {rewrite_hint}\n"

    return fetch_openai_response(prompt, system_prompt).strip()


def check_guardrails(text: str) -> GuardrailResult:
    system_prompt = """You are a safety checker for an investment discovery assistant.

Goal:
- Catch clear financial advice and trading instructions.
- Do NOT fail purely educational content.
- If the issue is only "recommendation-like wording", mark it as a MINOR issue instead of failing.

Fail (passed=false) ONLY if the text contains ANY of:
1) Direct recommendations or instructions to act:
   - "I recommend", "you should", "you need to", "buy X", "sell X", "pick X", "go with X", "invest in X now"
2) Explicit buy/sell/trade instructions or timing:
   - "buy today/now", "sell immediately", "enter/exit", "open a position", "when to buy/sell"
3) Performance predictions or guarantees:
   - "will outperform", "guaranteed", "risk-free", "no risk", "safe return", "cannot lose", "sure profit"

Minor issue (passed=true) if the text only includes recommendation-like adjectives or soft persuasion WITHOUT telling the user what to do:
- "ideal", "best", "great option", "perfect", "top pick", "good choice"

Output ONLY valid JSON:
{"passed": true|false, "severity": "none|minor|fail", "category": "none|advice|instructions|prediction|recommendation_wording|risk_free_claim", "reason": "short string or null"}"""

    out = fetch_openai_response(f"TEXT:\n{text}", system_prompt).strip()
    out = out.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(out)
        return GuardrailResult(
            passed=bool(data.get("passed", False)),
            reason=data.get("reason"),
            severity=data.get("severity", "fail"),
            category=data.get("category", "none"),
        )
    except Exception:
        t = text.lower()

        hard_patterns = [
            r"\bi recommend\b",
            r"\byou should\b",
            r"\byou need to\b",
            r"\b(buy|sell)\b.*\b(now|today|immediately)\b",
            r"\bguarantee(d)?\b",
            r"\brisk[- ]?free\b",
            r"\bcannot lose\b",
            r"\bwill outperform\b",
        ]
        if any(re.search(p, t) for p in hard_patterns):
            return GuardrailResult(
                passed=False,
                reason="heuristic_fail_hard_advice_or_guarantee",
                severity="fail",
                category="advice",
            )

        # If parsing fails but there's no obvious hard violation, do not block the user.
        return GuardrailResult(
            passed=True,
            reason="heuristic_pass_parse_error",
            severity="minor",
            category="none",
        )

