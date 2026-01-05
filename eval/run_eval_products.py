# eval/run_eval_products.py
import os
import sys
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core import yulia_reply

TABLE_TOKEN_RE = re.compile(r"\[\[PRODUCT_TABLE\]\]", re.IGNORECASE)

def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def normalize_text(s: str) -> str:
    return (s or "").lower()

def contains_table_token(output_text: str) -> bool:
    return bool(TABLE_TOKEN_RE.search(output_text or ""))

def explicitly_says_no_matches(output_text: str) -> bool:
    t = normalize_text(output_text)
    phrases = [
        "no matching products",
        "no matching items",
        "i can’t see matching products",
        "i can't see matching products",
        "i can’t find matching products",
        "i can't find matching products",
        "not seeing matching products",
        "not seeing any matching products",
        "not available in the provided list",
        "not in the provided list",
        "none in the provided list",
        "no products matched",
        "no products match",
    ]
    return any(p in t for p in phrases)

def question_count(output_text: str) -> int:
    return (output_text or "").count("?")

def get_field(p: Dict[str, Any], *names: str) -> Any:
    for n in names:
        if n in p:
            return p.get(n)
    return None

def deterministic_grade_surfacing(intent: str, output_text: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Surfacing grading aligned to your UI:
    - yuh_related:
        PASS if products non-empty AND token present
        PASS if products empty AND explicitly says no matches AND asks exactly 1 question
    - basic_knowledge:
        PASS if products empty AND token absent
    - unknown:
        PASS unless it surfaced products or token
    """
    intent = (intent or "unknown").strip()
    has_token = contains_table_token(output_text)

    if intent == "yuh_related":
        if products:
            if has_token:
                return {"pass": True, "reason": "yuh_related_products_present_and_table_token_present"}
            return {"pass": False, "reason": "yuh_related_products_present_but_table_token_missing"}

        if explicitly_says_no_matches(output_text) and question_count(output_text) == 1:
            return {"pass": True, "reason": "yuh_related_no_products_and_one_clarifying_question"}
        return {"pass": False, "reason": "yuh_related_no_products_without_clear_disclosure_or_single_question"}

    if intent == "basic_knowledge":
        if products:
            return {"pass": False, "reason": "basic_knowledge_should_not_return_products"}
        if has_token:
            return {"pass": False, "reason": "basic_knowledge_should_not_include_table_token"}
        return {"pass": True, "reason": "basic_knowledge_no_products_and_no_token"}

    # unknown
    if products or has_token:
        return {"pass": False, "reason": "unknown_should_not_surface_products_or_token"}
    return {"pass": True, "reason": "unknown_no_products_surfaced"}

def product_matches_expected(p: Dict[str, Any], expected: Dict[str, Any]) -> Tuple[bool, str]:
    """
    expected example:
    {
      "type_contains_all": ["ETF","Special savings"],
      "region": "World",
      "max_ter": 0.003,
      "esg_scores_in": ["AAA","AA","A"]
    }
    """
    p_type = str(get_field(p, "type", "Type") or "")
    p_region = str(get_field(p, "region", "Region") or "")
    p_ter = get_field(p, "ter", "TER")
    p_esg = str(get_field(p, "esg", "esg_score", "ESG_score") or "").strip().upper()

    for sub in (expected.get("type_contains_all") or []):
        if str(sub).lower() not in p_type.lower():
            return False, f"type_missing_substring:{sub}"

    if expected.get("region") is not None:
        if p_region != expected["region"]:
            return False, f"region_mismatch:{p_region}!= {expected['region']}"

    if expected.get("max_ter") is not None:
        if p_ter is None:
            return False, "ter_missing"
        try:
            if float(p_ter) > float(expected["max_ter"]):
                return False, f"ter_too_high:{p_ter}>{expected['max_ter']}"
        except Exception:
            return False, "ter_not_numeric"

    if expected.get("esg_scores_in") is not None:
        allowed = set([str(x).strip().upper() for x in (expected.get("esg_scores_in") or [])])
        if p_esg not in allowed:
            return False, f"esg_not_allowed:{p_esg}"

    return True, "ok"

def grade_products_correctness(products: List[Dict[str, Any]], expected: Dict[str, Any]) -> Dict[str, Any]:
    if not expected:
        return {"pass": True, "reason": "correctness_skipped_no_expected"}

    if not products:
        return {"pass": False, "reason": "no_products_returned_for_expected_constraints"}

    for p in products:
        ok, why = product_matches_expected(p, expected)
        if not ok:
            return {
                "pass": False,
                "reason": f"product_failed_constraints:{why}",
                "sample": {
                    "name": get_field(p, "name", "Name"),
                    "type": get_field(p, "type", "Type"),
                    "region": get_field(p, "region", "Region"),
                    "ter": get_field(p, "ter", "TER"),
                    "esg": get_field(p, "esg", "esg_score", "ESG_score"),
                },
            }
    return {"pass": True, "reason": "all_products_match_expected_constraints"}

def main():
    cases_path = "eval/cases/yulia_eval_cases.jsonl"
    cases = load_jsonl(cases_path)

    results: List[Dict[str, Any]] = []
    scored = 0
    passed = 0

    for case in cases:
        user_input = case["input"]
        expected = case.get("expected", {}) or {}

        app_out = yulia_reply(user_input)
        output_text = app_out.get("output_text", "")
        meta = app_out.get("meta", {}) or {}

        intent = meta.get("intent", "") or "unknown"
        confidence = meta.get("confidence", None)
        retries = meta.get("retries", 0)
        products_meta = meta.get("products", []) or []

        surf = deterministic_grade_surfacing(intent, output_text, products_meta)
        corr = grade_products_correctness(products_meta, expected)

        # Overall pass: always require surfacing pass.
        # If expected constraints exist, also require correctness.
        overall_pass = bool(surf.get("pass", False)) and (bool(corr.get("pass", False)) if expected else True)
        overall_reason_parts = [surf.get("reason", "")]
        if expected:
            overall_reason_parts.append(corr.get("reason", ""))
        overall_reason = " | ".join([p for p in overall_reason_parts if p])

        scored += 1
        if overall_pass:
            passed += 1

        results.append(
            {
                "id": case.get("id"),
                "input": user_input,
                "expected": expected,
                "output_text": output_text,
                "grade": {
                    # Backwards-compatible fields for render_results.py
                    "pass": overall_pass,
                    "reason": overall_reason,
                    # Detailed breakdown
                    "surfacing": surf,
                    "correctness": corr,
                },
                "meta": {
                    **meta,
                    "intent": intent,
                    "confidence": confidence,
                    "retries": retries,
                    "products": products_meta,
                },
                "judge_meta": {"used_llm": False},
            }
        )

    pass_rate = (passed / scored) if scored else 0.0
    print(f"Products eval scored: {scored} | Pass: {passed} | Pass rate: {pass_rate:.0%}")

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    pass_pct = int(pass_rate * 100)

    out_dir = Path("eval/output")
    out_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"result_products_{pass_pct}_{date_str}_{time_str}"
    jsonl_path = out_dir / f"{base_name}.jsonl"

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote JSONL: {jsonl_path}")

    if os.getenv("EVAL_HARD_FAIL", "").strip():
        if scored and passed != scored:
            sys.exit(1)

if __name__ == "__main__":
    main()
