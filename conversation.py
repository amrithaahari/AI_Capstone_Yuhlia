# conversation.py
import re
from typing import List, Optional

from agents import classify_intent, generate_response, check_guardrails
from config import MAX_GUARDRAIL_RETRIES, Intent, TOP_K_PRODUCTS
from database import search_products, search_products_filtered
from models import ConversationState, ProcessingResult, Product


def reset_state(state: ConversationState) -> None:
    state.goal = ""
    state.last_intent = None
    state.last_confidence = None


def _extract_structured_filters(goal: str) -> dict:
    """Heuristic filter extraction (no new LLM prompts).

    Used only when classify_intent returns yuh_related.
    """
    text = (goal or "").lower()

    type_contains_all: List[str] = []
    region: Optional[str] = None
    max_ter: Optional[float] = None
    esg_scores_in: Optional[List[str]] = None

    # Region: world/global
    if any(k in text for k in ["world", "global", "worldwide"]):
        region = "World"

    # Sustainable shares/stocks -> Share + ESG A/AA/AAA
    if any(k in text for k in ["sustainable", "sustainability", "esg", "responsible"]):
        if any(k in text for k in ["stock", "stocks", "share", "shares"]):
            type_contains_all = ["Share"]
            esg_scores_in = ["AAA", "AA", "A"]

    # ETFs
    if "etf" in text or "etfs" in text:
        # Low-fee / cheap: upsell special savings ETFs (commission-free) per your rule
        if any(k in text for k in ["cheap", "low fee", "low-fee", "low cost", "low-cost", "low ter", "low-ter"]):
            type_contains_all = ["ETF", "Special savings"]
            max_ter = 0.003  # default cap unless user specifies another

        # Explicit special-savings / commission-free mention
        if any(k in text for k in ["special savings", "commission free", "commission-free"]):
            type_contains_all = ["ETF", "Special savings"]

        # If user asked ETFs but we didn't set special savings, keep it broad
        if not type_contains_all:
            type_contains_all = ["ETF"]

    # If user specifies an explicit TER cap like "0.2%" or "0.25 %"
    m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if m_pct:
        try:
            pct = float(m_pct.group(1))
            max_ter = pct / 100.0
        except Exception:
            pass
    else:
        # Or a decimal cap like "TER under 0.003"
        m_dec = re.search(r"ter\s*(?:<=|<|under|below)\s*(0\.\d+)", text)
        if m_dec:
            try:
                max_ter = float(m_dec.group(1))
            except Exception:
                pass

    return {
        "type_contains_all": type_contains_all,
        "region": region,
        "max_ter": max_ter,
        "esg_scores_in": esg_scores_in,
    }


def process_user_message(message: str, state: ConversationState) -> ProcessingResult:
    msg = (message or "").strip()
    if not msg:
        return ProcessingResult(type="error", message="Please enter a message.")

    state.goal = msg

    classification = classify_intent(state.goal, followup_answers=[])
    state.last_intent = classification.category
    state.last_confidence = classification.confidence

    products: List[Product] = []
    if classification.category == Intent.yuh_related.value:
        filters = _extract_structured_filters(state.goal)

        has_structured = bool(
            (filters.get("type_contains_all"))
            or (filters.get("region"))
            or (filters.get("max_ter") is not None)
            or (filters.get("esg_scores_in"))
        )

        if has_structured:
            products = search_products_filtered(
                type_contains_all=filters.get("type_contains_all") or None,
                region=filters.get("region"),
                max_ter=filters.get("max_ter"),
                esg_scores_in=filters.get("esg_scores_in") or None,
                top_k=TOP_K_PRODUCTS,
            )
        else:
            # fallback to previous fuzzy term search
            terms = [t for t in re.split(r"\W+", state.goal) if t]
            products = search_products(terms, type_whitelist=None)[:TOP_K_PRODUCTS]

    responses: List[str] = []
    last_guardrail = None
    rewrite_hint = ""

    for retry in range(MAX_GUARDRAIL_RETRIES):
        raw_response = generate_response(
            state.goal,
            classification.category,
            products=products,
            followup_answers=[],
            rewrite_hint=rewrite_hint,
        )
        responses.append(raw_response)

        gr = check_guardrails(raw_response)
        last_guardrail = {"passed": gr.passed, "reason": gr.reason, "severity": gr.severity, "category": gr.category}

        if gr.passed:
            return ProcessingResult(
                type="success",
                message=raw_response,
                products=products,
                intent=classification.category,
                confidence=classification.confidence,
                retries=retry,
                responses=responses,
                guardrail=last_guardrail,
            )

        rewrite_hint = (
            "Rewrite to remove recommendation language (e.g., ideal/best/great choice), remove calls-to-action, "
            "remove buy/sell/timing, remove predictions/guarantees, and avoid 'risk-free'."
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
