# conversation.py
from typing import List

from agents import classify_intent, generate_response, check_guardrails
from config import MAX_GUARDRAIL_RETRIES, Intent, TOP_K_PRODUCTS
from database import search_products
from models import ConversationState, ProcessingResult, Product


_YUH_AVAILABILITY_TRIGGERS = [
    "does yuh have",
    "do you have",
    "what options",
    "what products",
    "available",
    "in the app",
    "on yuh",
    "yuh",
]


def _wants_yuh_availability(message: str) -> bool:
    m = (message or "").lower()
    return any(t in m for t in _YUH_AVAILABILITY_TRIGGERS)


def _extract_search_terms_for_yuh(message: str) -> List[str]:
    m = (message or "").lower()
    terms: List[str] = []

    if "index" in m:
        terms += ["Index", "ETF"]
    if "etf" in m:
        terms += ["ETF"]
    if "stock" in m or "stocks" in m or "share" in m or "shares" in m:
        terms += ["Stock", "Share"]
    if "crypto" in m:
        terms += ["Crypto"]
    if "bond" in m:
        terms += ["Bond", "Bond ETF"]
    if "money market" in m:
        terms += ["Money Market"]

    return terms or ["ETF"]


def reset_state(state: ConversationState) -> None:
    state.goal = ""
    state.last_intent = None
    state.last_confidence = None


def process_user_message(message: str, state: ConversationState) -> ProcessingResult:
    msg = (message or "").strip()
    if not msg:
        return ProcessingResult(type="error", message="Enter a question about investing concepts or what’s available in Yuh.")

    state.goal = msg

    classification = classify_intent(state.goal, followup_answers=[])
    state.last_intent = classification.category
    state.last_confidence = classification.confidence

    # Retrieve products only when it helps answer (yuh-related availability/offerings)
    products: List[Product] = []
    if classification.category == Intent.yuh_related.value or _wants_yuh_availability(state.goal):
        terms = _extract_search_terms_for_yuh(state.goal)
        products = search_products(terms, type_whitelist=None)[:TOP_K_PRODUCTS]

    responses: List[str] = []
    last_guardrail = None
    rewrite_hint = ""

    for retry in range(MAX_GUARDRAIL_RETRIES):
        text = generate_response(
            goal=state.goal,
            intent=classification.category,
            products=products,
            followup_answers=[],
            rewrite_hint=rewrite_hint,
        )
        responses.append(text)

        gr = check_guardrails(text)
        last_guardrail = {
            "passed": gr.passed,
            "severity": gr.severity,
            "category": gr.category,
            "reason": gr.reason,
        }

        if gr.passed:
            return ProcessingResult(
                type="success",
                message=text,
                products=products,
                intent=classification.category,
                confidence=classification.confidence,
                retries=retry,
                responses=responses,
                guardrail=last_guardrail,
            )

        rewrite_hint = (
            "Rewrite to be purely educational and neutral. Remove any recommendation language "
            "(e.g., ideal/best/great choice), remove calls-to-action, remove buy/sell/timing, "
            "remove predictions/guarantees, and avoid 'risk-free'."
        )

    return ProcessingResult(
        type="guardrail_failure",
        message="I can’t phrase that safely. Ask a factual question about investing concepts or what’s available in Yuh.",
        products=products,
        intent=classification.category,
        confidence=classification.confidence,
        retries=MAX_GUARDRAIL_RETRIES,
        responses=responses,
        guardrail=last_guardrail,
    )
