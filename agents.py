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

def generate_response(goal: str, intent: str, products: List[Product], followup_answers: List[str]) -> str:
    product_list = "\n".join([
        f"- {p.name}: {p.description} (Sector: {p.sector}, Currency: {p.currency}, TER: {p.ter})"
        for p in products
    ]) or "- (No matching products found)"

    context = f"User goal: {goal}\nIntent: {intent}\n"
    if followup_answers:
        context += "Follow-up answers:\n" + "\n".join([f"- {a}" for a in followup_answers]) + "\n"

    system_prompt = """You are Yulia, an educational investment discovery assistant for a banking app.
Hard rules:
- No financial advice or recommendations
- No buy/sell instructions
- No performance predictions or guarantees
- Do not ask for amounts, balances, or when exactly to invest
- Only mention products provided

Style:
- Educational, neutral, short paragraphs, bullets allowed
- Treat products as examples to explore, not picks
- Avoid recommendation adjectives: ideal, best, great choice, should, recommend
- Do not imply risk-free. Use ‘can be less volatile’ only when appropriate"""

    prompt = f"""{context}

Available products (examples only):
{product_list}

Write a response that:
1) Explains relevant concepts for the intent
2) Suggests what to look for when comparing options (fees, diversification, risk, horizon)
3) Mentions up to {min(5, len(products))} products as examples the user can explore in-app
"""

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

Output ONLY valid JSON (no markdown, no extra keys beyond these):
{"passed": true|false, "severity": "none|minor|fail", "category": "none|advice|instructions|prediction|recommendation_wording|risk_free_claim", "reason": "short string or null"}"""

    out = fetch_openai_response(f"TEXT:\n{text}", system_prompt).strip()
    out = out.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(out)
        return GuardrailResult(
            passed=bool(data.get("passed", False)),
            reason=data.get("reason"),
        )
    except Exception:
        # Fallback heuristic so you don't randomly block good content on JSON parse errors.
        # Only fail hard on truly disallowed patterns.
        t = text.lower()

        hard_patterns = [
            r"\bi recommend\b",
            r"\byou should\b",
            r"\byou need to\b",
            r"\bbuy\b.*\b(now|today|immediately)\b",
            r"\bsell\b.*\b(now|today|immediately)\b",
            r"\bguarantee(d)?\b",
            r"\brisk[- ]?free\b",
            r"\bcannot lose\b",
            r"\bwill outperform\b",
        ]
        if any(re.search(p, t) for p in hard_patterns):
            return GuardrailResult(passed=False, reason="heuristic_fail_hard_advice_or_guarantee")

        return GuardrailResult(passed=True, reason="heuristic_pass_parse_error")
