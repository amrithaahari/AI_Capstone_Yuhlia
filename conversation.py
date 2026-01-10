# conversation.py
import re
from typing import List, Dict, Any

from agents import classify_intent, generate_response, check_guardrails, extract_filters
from config import MAX_GUARDRAIL_RETRIES, Intent, TOP_K_PRODUCTS
from database import search_products_filtered, get_type_overview, get_sample_products_for_types, search_products_by_ids
from models import ConversationState, ProcessingResult, Product
from rag.retrieve import rag_candidates, rag_web_snippets

TABLE_TOKEN_RE = re.compile(r"\[\[\s*PRODUCT_TABLE\s*\]\]", re.IGNORECASE)

def reset_state(state: ConversationState) -> None:
    state.goal = ""
    state.last_intent = None
    state.last_confidence = None
    state.awaiting_followup = False
    state.last_followup_question = None
    state.followup_answers = []



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

def _is_low_cost_etf_query(text: str, filters: Dict[str, Any]) -> bool:
    t = (text or "").lower()
    mentions_etf = "etf" in t or any("etf" in (x or "").lower() for x in (filters.get("type_contains_all") or []))
    low_cost_terms = ["low cost", "low-cost", "low fee", "low-fee", "cheap", "commission", "fee"]
    low_cost_signal = any(k in t for k in low_cost_terms) or (filters.get("max_ter") is not None)
    return bool(mentions_etf and low_cost_signal)


def _merge_dedup_keep_order(a: List[Product], b: List[Product], limit: int) -> List[Product]:
    out: List[Product] = []
    seen = set()
    for p in (a or []):
        if p.id not in seen:
            seen.add(p.id)
            out.append(p)
        if len(out) >= limit:
            return out
    for p in (b or []):
        if p.id not in seen:
            seen.add(p.id)
            out.append(p)
        if len(out) >= limit:
            return out
    return out


def enforce_table_token_contract(output_text: str, intent: str, products: List[Product]) -> str:
    """
    Deterministic contract:
    - Non-yuh_related: token must not appear
    - yuh_related + products: token must appear
    - yuh_related + no products: token must not appear
    """
    text = (output_text or "").strip()

    # Remove any token variants first (idempotent)
    text = TABLE_TOKEN_RE.sub("", text).strip()

    if intent == Intent.yuh_related.value and products:
        # Ensure token on its own line at the end
        text = text.rstrip() + "\n\n[[PRODUCT_TABLE]]"

    return text



def process_user_message(message: str, state: ConversationState) -> ProcessingResult:
    msg = (message or "").strip()
    if not msg:
        return ProcessingResult(type="error", message="Please enter a message.")

    # Always re-classify and re-filter every user turn.
    # If we were awaiting a follow-up, we add context (original question + follow-up question + user answer),
    # but we still run the full pipeline again.
    awaiting_followup = bool(getattr(state, "awaiting_followup", False))
    last_followup_q = getattr(state, "last_followup_question", None) or ""
    original_goal = getattr(state, "goal", "") or ""

    if awaiting_followup and original_goal:
        effective_query = (
            f"ORIGINAL_QUESTION:\n{original_goal}\n\n"
            f"ASSISTANT_FOLLOWUP_QUESTION:\n{last_followup_q}\n\n"
            f"USER_ANSWER:\n{msg}\n"
        )
    else:
        # New thread
        state.goal = msg
        if hasattr(state, "followup_answers"):
            state.followup_answers = []
        if hasattr(state, "last_followup_question"):
            state.last_followup_question = None
        if hasattr(state, "awaiting_followup"):
            state.awaiting_followup = False
        effective_query = msg

    generation_goal = effective_query

    classification = classify_intent(effective_query, followup_answers=[])
    state.last_intent = classification.category
    state.last_confidence = classification.confidence

    # --- Website RAG grounding (narrative only) ---
    use_web_rag = (classification.category != Intent.yuh_related.value)

    if use_web_rag:
        snippets = rag_web_snippets(state.goal, top_n=6)

        if snippets:
            web_block = "YUH_WEBSITE_GROUNDING (from yuh.com Invest section):\n"
            for s in snippets:
                web_block += f"- Source: {s['url']}\n  {s['text']}\n\n"

            generation_goal = generation_goal + "\n\n" + web_block

    products: List[Product] = []
    filters: Dict[str, Any] = {"notes": ""}

    if classification.category == Intent.yuh_related.value:
        raw_filters = extract_filters(effective_query)
        filters = _validate_filters_llm(raw_filters)

        # Important: do NOT stay in overview mode when we're processing a follow-up answer
        is_overview = (not awaiting_followup) and (
            _is_overview_query(effective_query) or (filters.get("notes", "").lower() == "overview_query")
        )

        if is_overview:
            overview = get_type_overview(limit_types=20)
            types = [t for (t, _) in overview]
            products = get_sample_products_for_types(types, per_type=2)

            overview_lines = [f"- {t} ({n})" for (t, n) in overview]
            catalog_overview_block = "CATALOG_TYPE_OVERVIEW (from yuh_products.db):\n" + "\n".join(overview_lines)
            generation_goal = effective_query + "\n\n" + catalog_overview_block
        else:
            has_structured = bool(
                (filters.get("type_contains_all"))
                or (filters.get("region"))
                or (filters.get("max_ter") is not None)
                or (filters.get("esg_scores_in"))
            )

            if has_structured:
                if _is_low_cost_etf_query(effective_query, filters):
                    # 1) Commission-free first: Type contains "Special savings (ETF)"
                    commission_free = search_products_filtered(
                        type_contains_all=["Special savings (ETF)"],
                        region=filters.get("region"),
                        max_ter=None,  # important: don't TER-filter this set
                        esg_scores_in=filters.get("esg_scores_in") or None,
                        top_k=TOP_K_PRODUCTS,
                        order_by_esg=bool(filters.get("order_by_esg")),
                    )

                    # 2) Then low TER ETFs: TER < 0.4%
                    low_ter = search_products_filtered(
                        type_contains_all=["ETF"],
                        region=filters.get("region"),
                        max_ter=0.004,  # force 0.4% cap for this intent
                        esg_scores_in=filters.get("esg_scores_in") or None,
                        top_k=TOP_K_PRODUCTS,
                        order_by_esg=bool(filters.get("order_by_esg")),
                    )

                    products = _merge_dedup_keep_order(commission_free, low_ter, limit=TOP_K_PRODUCTS)
                else:
                    products = search_products_filtered(
                        type_contains_all=filters.get("type_contains_all") or None,
                        region=filters.get("region"),
                        max_ter=filters.get("max_ter"),
                        esg_scores_in=filters.get("esg_scores_in") or None,
                        top_k=TOP_K_PRODUCTS,
                        order_by_esg=bool(filters.get("order_by_esg")),
                    )

            else:
                # RAG fallback for fuzzy / values-based queries
                candidate_ids = rag_candidates(effective_query, top_n=80)

                products = search_products_by_ids(
                    candidate_ids=candidate_ids,
                    filters=filters,
                    top_k=TOP_K_PRODUCTS,
                )

        # Deterministic signal for the generator when no matches happened
        if len(products) == 0:
            generation_goal = (
                generation_goal
                + "\n\nCATALOG_SEARCH_RESULT: 0_MATCHES"
                + "\nAsk exactly ONE short follow-up question to relax ONE constraint "
                  "(remove World, remove Special savings, relax ESG to include BBB, or remove TER cap)."
            )

        # Pass extractor notes through for disclaimers (but ignore the overview marker)
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
            followup_answers=[],  # follow-up context is already embedded into effective_query
            rewrite_hint=rewrite_hint,
        )
        responses.append(raw_response)

        gr = check_guardrails(raw_response)
        last_guardrail = {"passed": gr.passed, "reason": gr.reason, "severity": gr.severity, "category": gr.category}

        if gr.passed:
            enforced = enforce_table_token_contract(raw_response, classification.category, products)
            text = (enforced or "").strip()
            last_line = text.splitlines()[-1].strip() if text else ""
            asked_followup = last_line.endswith("?")

            state.awaiting_followup = asked_followup
            state.last_followup_question = last_line if asked_followup else None

            if classification.category != Intent.yuh_related.value:
                assert len(products) == 0, "Non-yuh intent must not return products"
                assert TABLE_TOKEN_RE.search(enforced) is None, "Non-yuh intent must not include PRODUCT_TABLE token"
            if TABLE_TOKEN_RE.search(enforced):
                assert len(products) > 0, "PRODUCT_TABLE token present but products are empty"
            if classification.category == Intent.yuh_related.value and len(products) > 0:
                assert TABLE_TOKEN_RE.search(enforced), "yuh_related with products must include PRODUCT_TABLE token"

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

    # Guardrail failure: do not keep follow-up mode on
    state.awaiting_followup = False
    state.last_followup_question = None

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


