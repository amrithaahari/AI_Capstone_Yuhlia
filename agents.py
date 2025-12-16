import json
import os
from typing import List, Optional

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
- Treat products as examples to explore, not picks"""

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
    system_prompt = """You are a safety checker for an investment assistant.
Fail if the text:
- recommends specific products (eg "I recommend X", "you should buy")
- includes buy/sell instructions
- predicts returns or guarantees outcomes
Return ONLY JSON:
{"passed":true|false,"reason":"short or null"}"""

    out = fetch_openai_response(f"TEXT:\n{text}", system_prompt).strip()
    out = out.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(out)
        return GuardrailResult(passed=bool(data.get("passed", False)), reason=data.get("reason"))
    except Exception:
        return GuardrailResult(passed=False, reason="guardrail_parse_error")
