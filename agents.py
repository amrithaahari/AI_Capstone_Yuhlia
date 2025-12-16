"""
LLM agent calls for classification, generation, and guardrails
"""

import asyncio
import json
import os
from typing import List


from models import ClassificationResult, GuardrailResult, Product

def fetch_openai_response(prompt: str, system_prompt: str = None) -> str:
    """Make synchronous call to OpenAI API"""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model="gpt-4o",  # or "gpt-4o-mini" for faster/cheaper option
        messages=messages,
        temperature=0.7,
        max_tokens=1000
    )

    return response.choices[0].message.content


async def classify_intent(user_input: str, followup_history: List[str]) -> ClassificationResult:
    """Classify user intent using OpenAI API"""

    # Build context from follow-up history
    context = user_input
    if followup_history:
        context = f"Original request: {user_input}\n\nFollow-up answers:\n"
        context += "\n".join([f"- {answer}" for answer in followup_history])

    system_prompt = """You are an intent classifier for an investment discovery assistant called Yulia.

Your job is to classify the user's intent into one of these categories:
- "Beginner": User is new to investing, wants to learn basics, or needs educational guidance
- "capital_preservation": User wants to preserve capital, minimize risk, prefers stable/safe options
- "Unknown": Intent is unclear or doesn't fit the above categories

Respond ONLY with valid JSON in this exact format (no markdown, no explanation):
{"category": "Beginner|capital_preservation|Unknown", "confidence": 0.0-1.0, "reasoning": "brief explanation"}"""

    prompt = f"User input:\n{context}"

    try:
        response = await asyncio.to_thread(
            lambda: fetch_openai_response(prompt, system_prompt)
        )

        # Clean up potential markdown formatting
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        # Parse JSON response
        result = json.loads(response)

        return ClassificationResult(
            category=result['category'],
            confidence=float(result['confidence']),
            reasoning=result['reasoning']
        )
    except Exception as e:
        print(f"Classification error: {e}")
        return ClassificationResult(
            category="Unknown",
            confidence=0.0,
            reasoning="Error during classification"
        )


async def generate_response(
        user_goal: str,
        intent: str,
        products: List[Product],
        followup_history: List[str]
) -> str:
    """Generate educational response with product examples using OpenAI"""

    # Build context
    context = f"User's goal: {user_goal}"
    if followup_history:
        context += f"\n\nAdditional context from conversation:\n"
        context += "\n".join([f"- {answer}" for answer in followup_history])

    # Format products
    product_list = "\n".join([
        f"- {p.name}: {p.description} (Sector: {p.sector}, Currency: {p.currency}, TER: {p.ter}%)"
        for p in products
    ])

    system_prompt = """You are Yulia, an educational investment discovery assistant. Your role is to help users explore investing concepts and discover products available on the yuh platform.

IMPORTANT CONSTRAINTS:
- Do NOT give financial advice or recommendations
- Do NOT tell users to buy or sell specific products
- Do NOT make predictions or guarantees about performance
- Do NOT ask about investment amounts, account balances, or timing
- ONLY reference products from the list provided below
- Treat products as educational examples, not recommendations"""

    prompt = f"""User context:
{context}

Classified intent: {intent}

Available products to reference as examples:
{product_list}

Generate a helpful, educational response that:
1. Addresses the user's goal in a neutral, informative way
2. Explains relevant investing concepts for their situation
3. Mentions some of the products above as examples they COULD explore (not recommendations)
4. Uses phrases like "you might consider exploring", "options available include", "you could look at"
5. Keeps the tone friendly and educational

Response:"""

    try:
        response = await asyncio.to_thread(
            lambda: fetch_openai_response(prompt, system_prompt)
        )
        return response.strip()
    except Exception as e:
        print(f"Generation error: {e}")
        return "I apologize, but I'm having trouble generating a response right now. Please try again."


async def check_guardrails(response: str) -> GuardrailResult:
    """Check if response violates safety guardrails using OpenAI"""

    system_prompt = """You are a safety guardrail checker for an investment assistant.

Check if the following response violates ANY of these rules:
1. Gives financial advice or recommendations (e.g., "you should buy", "I recommend")
2. Makes predictions or guarantees about returns or performance
3. Gives direct buy/sell instructions
4. Promises specific outcomes

Respond ONLY with valid JSON (no markdown):
{"passed": true|false, "reason": "explanation if failed, null if passed"}"""

    prompt = f"Response to check:\n{response}"

    try:
        result = await asyncio.to_thread(
            lambda: fetch_openai_response(prompt, system_prompt)
        )

        # Clean up potential markdown formatting
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()

        parsed = json.loads(result)
        return GuardrailResult(
            passed=parsed['passed'],
            reason=parsed.get('reason')
        )
    except Exception as e:
        print(f"Guardrail check error: {e}")
        # Fail safe - reject on error
        return GuardrailResult(
            passed=False,
            reason="Error during guardrail check"
        )
