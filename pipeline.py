# pipeline.py
from typing import Dict, Any, Tuple, List
from intents import classify_intent
from followups import get_followups
from products import retrieve_products, products_to_markdown
from guardrail import guardrail_check
from yulia import yulia_generate

FALLBACK = (
    "I can’t generate a compliant response right now. "
    "Try reframing your goal in general terms (for example: “I want a low-risk ETF overview” or “I’m a beginner, how do I start?”)."
)

CONF_THRESHOLD = 0.7

async def run_turn(state: Dict[str, Any], db_path: str) -> Dict[str, Any]:
    """
    state contains:
      - mode: 'AWAITING_GOAL' | 'AWAITING_FOLLOWUPS' | 'READY_TO_ANSWER'
      - original_goal_text
      - followup_questions
      - followup_answers
      - last_user_message
    Returns updated state plus a response payload:
      - response_type: 'clarify' | 'answer'
      - assistant_text
      - questions (if clarify)
    """
    user_msg = state.get("last_user_message", "") or ""

    # Step 1: If we are awaiting goal, capture it
    if state.get("mode") in (None, "AWAITING_GOAL"):
        state["original_goal_text"] = user_msg
        intent, conf, why = classify_intent(user_msg)
        state["intent"], state["confidence"], state["intent_rationale"] = intent, conf, why

        if intent == "unknown" or conf < CONF_THRESHOLD:
            qs = get_followups()
            state["mode"] = "AWAITING_FOLLOWUPS"
            state["followup_questions"] = qs
            state["followup_answers"] = []
            return {
                **state,
                "response_type": "clarify",
                "questions": qs,
                "assistant_text": "I need one or two details to answer safely. Please answer these:",
            }

        state["mode"] = "READY_TO_ANSWER"

    # Step 2: If awaiting followups, collect answer(s) and re-classify
    if state["mode"] == "AWAITING_FOLLOWUPS":
        state.setdefault("followup_answers", []).append(user_msg)

        combined = " | ".join(
            [state.get("original_goal_text", "")] + state.get("followup_answers", [])
        )
        intent, conf, why = classify_intent(combined)
        state["intent"], state["confidence"], state["intent_rationale"] = intent, conf, why

        if intent == "unknown" or conf < CONF_THRESHOLD:
            # Ask next follow-up if available, else force unknown → beginner guidance as safe default
            qs = state.get("followup_questions", [])
            if len(state["followup_answers"]) < len(qs):
                remaining = qs[len(state["followup_answers"]):]
                return {
                    **state,
                    "response_type": "clarify",
                    "questions": remaining[:1],
                    "assistant_text": "One more question:",
                }
            # safe default
            state["intent"], state["confidence"], state["intent_rationale"] = "beginner_guidance", 0.6, "default after insufficient clarity"
        state["mode"] = "READY_TO_ANSWER"

    # Step 3: Intent is ready → retrieve products → generate → guardrail retry loop
    combined_context = " | ".join(
        [state.get("original_goal_text", "")] + state.get("followup_answers", [])
    ).strip()

    products = retrieve_products(db_path, combined_context, k=8)
    products_md = products_to_markdown(products)

    guardrail_feedback = None
    reasons_log: List[Any] = []
    for attempt in range(1, 6):
        text = await yulia_generate(
            intent=state["intent"],
            user_text=combined_context,
            products_md_table=products_md,
            guardrail_feedback=guardrail_feedback,
        )
        ok, reasons = guardrail_check(text)
        if ok:
            state["mode"] = "AWAITING_GOAL"  # reset for next question or keep chatty, your choice
            return {
                **state,
                "response_type": "answer",
                "assistant_text": text,
                "attempts": attempt,
                "blocked": False,
                "guardrail_reasons": reasons_log,
            }

        reasons_log.append({"attempt": attempt, "reasons": reasons})
        guardrail_feedback = (
            "Revise your answer to remove prohibited content (no guarantees, no direct buy/sell commands, no price targets). "
            f"Reasons: {reasons}"
        )

    state["mode"] = "AWAITING_GOAL"
    return {
        **state,
        "response_type": "answer",
        "assistant_text": FALLBACK,
        "attempts": 5,
        "blocked": True,
        "guardrail_reasons": reasons_log,
    }
