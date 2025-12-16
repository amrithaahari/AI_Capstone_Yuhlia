"""
Conversation flow and state management logic
"""

from typing import List, Optional


from config import (
    CONFIDENCE_THRESHOLD,
    MAX_FOLLOWUP_QUESTIONS,
    MAX_GUARDRAIL_RETRIES,
    Intent,
    FOLLOWUP_QUESTIONS
)
from models import ConversationState, ProcessingResult
from agents import classify_intent, generate_response, check_guardrails
from database import search_products

def get_next_followup_question(followup_count: int, last_confidence: float) -> Optional[str]:
    """Determine next follow-up question based on conversation state"""
    if followup_count >= MAX_FOLLOWUP_QUESTIONS:
        return None

    # Simple strategy: ask about experience first, then goals
    if followup_count == 0:
        return FOLLOWUP_QUESTIONS["experience"]
    elif followup_count == 1:
        return FOLLOWUP_QUESTIONS["goals"]

    return None


def extract_search_terms(intent: str, goal: str, followup_answers: List[str]) -> List[str]:
    """Extract search terms based on intent and conversation"""
    terms = []

    if intent == Intent.BEGINNER:
        terms.extend(["Index", "ETF", "Fund"])
    elif intent == Intent.CAPITAL_PRESERVATION:
        terms.extend(["Bond", "Treasury", "Government", "Fixed Income", "Money Market"])

    # Add terms from user input
    goal_lower = goal.lower()
    if "swiss" in goal_lower or "switzerland" in goal_lower:
        terms.append("Swiss")
    if "sustainable" in goal_lower or "esg" in goal_lower or "green" in goal_lower:
        terms.append("ESG")
    if "tech" in goal_lower or "technology" in goal_lower:
        terms.append("Technology")

    return terms if terms else ["ETF", "Fund"]


async def process_user_message(message: str, state: ConversationState) -> ProcessingResult:
    """Main conversation processing logic"""

    # If this is a follow-up answer, add to history
    if state.followup_count > 0:
        state.followup_answers.append(message)
    else:
        # This is the original goal
        state.original_goal = message

    # Step 1: Classify intent
    classification = await classify_intent(state.original_goal, state.followup_answers)
    state.last_intent = classification.category
    state.last_confidence = classification.confidence

    # Step 2: Decision logic
    if classification.category == Intent.UNKNOWN or classification.confidence < CONFIDENCE_THRESHOLD:
        # Need more information
        next_question = get_next_followup_question(state.followup_count, classification.confidence)

        if next_question:
            state.followup_count += 1
            return ProcessingResult(
                type="followup",
                message=next_question,
                intent=classification.category,
                confidence=classification.confidence
            )
        else:
            # Max follow-ups reached, user doesn't match intents
            return ProcessingResult(
                type="mismatch",
                message="Thank you for sharing! Based on our conversation, it seems you might be looking for more advanced trading features or information that Yulia is not currently designed to provide. Yulia is specifically built to help beginners explore basic investing concepts and discover products in the yuh universe. For more advanced trading needs, you may want to explore other resources or contact yuh support directly.",
                intent=classification.category,
                confidence=classification.confidence
            )

    # Step 3: High confidence - proceed to generation
    search_terms = extract_search_terms(classification.category, state.original_goal, state.followup_answers)

    # Step 4: Product retrieval
    products = search_products(search_terms)

    # Step 5: Response generation with guardrail retries
    for retry in range(MAX_GUARDRAIL_RETRIES):
        response = await generate_response(
            state.original_goal,
            classification.category,
            products,
            state.followup_answers
        )

        # Step 6: Guardrail check
        guardrail = await check_guardrails(response)

        if guardrail.passed:
            return ProcessingResult(
                type="success",
                message=response,
                products=products,
                intent=classification.category,
                confidence=classification.confidence,
                retries=retry
            )
        else:
            # Log retry attempt
            if retry < MAX_GUARDRAIL_RETRIES - 1:
                print(f"Guardrail failed (attempt {retry + 1}): {guardrail.reason}. Retrying...")

    # All retries failed
    return ProcessingResult(
        type="guardrail_failure",
        message="I apologize, but I'm having trouble formulating an appropriate response that meets our safety guidelines. Let me provide some general information instead: yuh offers a variety of investment products including ETFs, bonds, and funds. You can explore these options in the yuh app to learn more about each product's characteristics and find what aligns with your interests. Please note that all investments carry risk, and it's important to do your own research.",
        products=products,
        intent=classification.category,
        confidence=classification.confidence,
        retries=MAX_GUARDRAIL_RETRIES
    )
