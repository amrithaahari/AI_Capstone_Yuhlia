# conversation.py
import re
from typing import List, Optional, Dict, Any

from agents import classify_intent, generate_response, check_guardrails, extract_filters
from config import MAX_GUARDRAIL_RETRIES, Intent, TOP_K_PRODUCTS
from database import search_products, search_products_filtered, get_type_overview, get_sample_products_for_types
from models import ConversationState, ProcessingResult, Product


def reset_state(state: ConversationState) -> None:
    state.goal = ""
    state.last_intent = None
    state.last_confidence = None


def _is_overview_query(text: str) -> bool:
    t = (text or "").lower().strip()
    patterns = [
        r"\bwhat (investment )?options\b",
        r"\bwhat (can i|could i) invest in\b",
        r"\bwhat('?s| is) available\b",
        r"\bwhat products\b",
        r"\bwhat do you have\b",
        r"\bavailable on yuh\b",
        r"\binvestment options\b",
    ]
    return any(re.search(p, t) for p in patterns)


def _validate_filters_llm(raw: Dict[str, Any]) -> dict:
    """Validate + normalize LLM-extracted filters to safe canonical values."""
    if not isinstance(raw, dict):
        raw = {}

    allowed_esg = {"AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D"}

    # type_contains_all
    tca = raw.get("type_contains_all")
    if not isinstance(tca, list):
        tca = []
    tca = [str(x).strip() for x in tca if str(x).strip()]

    seen = set()
    tca_norm = []
    for x in tca:
        xl = x.lower()
        if xl not in seen:
            seen.add(xl)
            tca_norm.append(x)

    # region
    region = raw.get("region")
    if region is not None:
        region = str(region).strip()
        if not region:
            region = None
        elif region.lower() in {"world", "global", "worldwide"}:
            region = "World"

    # max_ter
    max_ter = raw.get("max_ter")
    if max_ter is None or max_ter == "":
        max_ter = None
    else:
        try:
            max_ter = float(max_ter)
            if max_ter < 0:
                max_ter = 0.0
            if max_ter > 0.05:
                max_ter = 0.05
        except Exception:
            max_ter = None

    # esg_scores_in
    esg = raw.get("esg_scores_in")
    if esg is None:
        esg_norm = None
    else:
        if not isinstance(esg, list):
            esg = []
        esg_norm = []
        for x in esg:
            s = str(x).strip().upper()
            if s in allowed_esg:
                esg_norm.append(s)

        order = {"AAA": 1, "AA": 2, "A": 3, "BBB": 4, "BB": 5, "B": 6, "CCC": 7, "D": 8}
        esg_norm = sorted(set(esg_norm), key=lambda s: order.get(s, 99))
        if not esg_norm:
            esg_norm = None

    order_by_esg = raw.get("order_by_esg")
    order_by_esg = bool(order_by_esg) if order_by_esg is not None else False

    notes = raw.get("notes")
    notes = str(notes).strip() if notes is not None else ""



    return {
        "type_contains_all": tca_norm,
        "region": region,
        "max_ter": max_ter,
        "esg_scores_in": esg_norm,
        "order_by_esg": order_by_esg,
        "notes": notes,
    }


def process_user_message(message: str, state: ConversationState) -> ProcessingResult:
    msg = (message or "").strip()
    if not msg:
        return ProcessingResult(type="error", message="Please enter a message.")

    state.goal = msg
    generation_goal = state.goal  # always defined

    classification = classify_intent(state.goal, followup_answers=[])
    state.last_intent = classification.category
    state.last_confidence = classification.confidence

    products: List[Product] = []

    # Defaults so variables exist for all intents
    filters: Dict[str, Any] = {"notes": ""}

    if classification.category == Intent.yuh_related.value:
        raw_filters = extract_filters(state.goal)
        filters = _validate_filters_llm(raw_filters)

        is_overview = _is_overview_query(state.goal) or (filters.get("notes", "").lower() == "overview_query")
        if is_overview:
            overview = get_type_overview(limit_types=20)
            types = [t for (t, _) in overview]
            products = get_sample_products_for_types(types, per_type=2)

            overview_lines = [f"- {t} ({n})" for (t, n) in overview]
            catalog_overview_block = "CATALOG_TYPE_OVERVIEW (from yuh_products.db):\n" + "\n".join(overview_lines)
            generation_goal = state.goal + "\n\n" + catalog_overview_block
        else:
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
                    order_by_esg=bool(filters.get("order_by_esg")),
                )
            else:
                terms = [t for t in re.split(r"\W+", state.goal) if t]
                products = search_products(terms, top_k=TOP_K_PRODUCTS, type_whitelist=None)

        # Deterministic signal for the generator when no matches happened
        if len(products) == 0:
            generation_goal = (
                generation_goal
                + "\n\nCATALOG_SEARCH_RESULT: 0_MATCHES"
                + "\nAsk exactly ONE short follow-up question to relax ONE constraint "
                  "(remove World, remove Special savings, relax ESG to include BBB, or remove TER cap)."
            )

        # If extractor provided notes (e.g., exclusions are approximate), pass them through
        if filters.get("notes") and filters.get("notes").lower() not in {"overview_query"}:
            generation_goal = generation_goal + f"\n\nNOTES_FROM_FILTER_EXTRACTOR: {filters['notes']}"

    responses: List[str] = []
    last_guardrail = None
    rewrite_hint = ""

    for retry in range(MAX_GUARDRAIL_RETRIES):
        raw_response = generate_response(
            generation_goal,
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
