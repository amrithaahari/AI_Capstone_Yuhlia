from typing import List, Optional, Tuple

from config import CONFIDENCE_THRESHOLD, MAX_FOLLOWUP_QUESTIONS, MAX_GUARDRAIL_RETRIES, Intent, FOLLOWUP_QUESTIONS
from models import ConversationState, ProcessingResult
from agents import classify_intent, generate_response, check_guardrails
from database import search_products

def get_next_followup(state: ConversationState) -> Optional[Tuple[str, str]]:
    if state.followup_count >= MAX_FOLLOWUP_QUESTIONS:
        return None
    return FOLLOWUP_QUESTIONS[state.followup_count]

def extract_search_terms(intent: str, goal: str, followups: List[str]) -> List[str]:
    terms: List[str] = []

    g = (goal or "").lower()
    fblob = " ".join(followups).lower()

    if intent == Intent.beginner.value:
        terms += ["ETF", "Index", "Fund"]
    elif intent == Intent.capital_preservation.value:
        terms += ["Bond", "Government", "Treasury", "Money Market", "Short Duration"]

    if "swiss" in g or "switzerland" in g or "swiss" in fblob:
        terms.append("Swiss")
    if "esg" in g or "sustainable" in g or "green" in g or "esg" in fblob:
        terms.append("ESG")
    if "chf" in g or "franc" in g or "chf" in fblob:
        terms.append("CHF")

    return terms or ["ETF"]

def type_whitelist_for_intent(intent: str) -> Optional[List[str]]:
    # Adjust to match your DB's Type values
    if intent == Intent.beginner.value:
        return ["ETF", "Fund"]
    if intent == Intent.capital_preservation.value:
        return ["Bond ETF", "Bond", "Money Market", "ETF"]
    return None

def reset_state(state: ConversationState) -> None:
    state.goal = ""
    state.awaiting_followup = False
    state.followup_count = 0
    state.followup_answers = []
    state.last_followup_key = None
    state.last_intent = None
    state.last_confidence = None

def process_user_message(message: str, state: ConversationState) -> ProcessingResult:
    msg = (message or "").strip()
    if not msg:
        return ProcessingResult(type="followup", message="Tell me what you want to explore, in one sentence.")

    # Correct follow-up handling
    if state.awaiting_followup:
        state.followup_answers.append(msg)
        state.awaiting_followup = False
        state.last_followup_key = None
    else:
        # Treat as a new goal and reset followups
        state.goal = msg
        state.followup_count = 0
        state.followup_answers = []
        state.last_followup_key = None

    # Classify intent based on goal + accumulated followups
    classification = classify_intent(state.goal, state.followup_answers)
    state.last_intent = classification.category
    state.last_confidence = classification.confidence

    # Ask follow-up if low confidence
    if classification.category == Intent.unknown.value or classification.confidence < CONFIDENCE_THRESHOLD:
        nxt = get_next_followup(state)
        if nxt:
            key, q = nxt
            state.followup_count += 1
            state.awaiting_followup = True
            state.last_followup_key = key
            return ProcessingResult(
                type="followup",
                message=q,
                intent=classification.category,
                confidence=classification.confidence,
            )
        return ProcessingResult(
            type="mismatch",
            message="I can help with beginner investing education and conservative options to explore. Try: ‘I want to learn ETFs’ or ‘I want low-volatility options’.",
            intent=classification.category,
            confidence=classification.confidence,
        )

    # Retrieve products
    terms = extract_search_terms(classification.category, state.goal, state.followup_answers)
    whitelist = type_whitelist_for_intent(classification.category)
    products = search_products(terms, type_whitelist=whitelist)

    # Generate with limited guardrail retries
    responses: List[str] = []
    guardrail_attempts: List[dict] = []

    rewrite_hint = ""  # escalates only when needed

    for retry in range(MAX_GUARDRAIL_RETRIES):
        text = generate_response(
            state.goal,
            classification.category,
            products,
            state.followup_answers,
            rewrite_hint=rewrite_hint,
            # if you keep generate_response signature unchanged, append rewrite_hint into state.followup_answers instead (not ideal)
        )

        # If you can't change generate_response signature, do this instead:
        if rewrite_hint:
            text = text + "\n\n(Internal constraint reminder: " + rewrite_hint + ")"

        responses.append(text)

        gr = check_guardrails(text)
        guardrail_attempts.append({
            "passed": gr.passed,
            "severity": gr.severity,
            "category": gr.category,
            "reason": gr.reason,
        })

        # Accept on pass, including "minor" issues
        if gr.passed:
            return ProcessingResult(
                type="success",
                message=text,
                products=products,
                intent=classification.category,
                confidence=classification.confidence,
                retries=retry,
                responses=responses,
                # if you add this field (recommended) expose guardrail_attempts in debug too
                # guardrails=guardrail_attempts,
            )

        # Only retry on actual failures, with an explicit constraint
        rewrite_hint = (
            "Rewrite to be purely educational. Remove any recommendation language "
            "(eg ideal/best/great choice), remove calls-to-action, remove buy/sell/timing, "
            "remove predictions/guarantees, and avoid the term 'risk-free'."
        )

    # All retries failed
    return ProcessingResult(
        type="guardrail_failure",
        message="I cannot phrase that safely. General guidance: compare costs, diversification, and risk level. Explore ETFs and funds in-app to learn what each product is designed for. Investments can go down as well as up.",
        products=products,
        intent=classification.category,
        confidence=classification.confidence,
        retries=MAX_GUARDRAIL_RETRIES,
        responses=responses,
        # guardrails=guardrail_attempts,
    )

