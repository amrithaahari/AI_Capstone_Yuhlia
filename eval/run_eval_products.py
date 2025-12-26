# eval/run_eval_products.py
import os
import sys
import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

# Add project root (parent of /eval) to Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from openai import OpenAI
from core import yulia_reply


YUH_PRODUCTS_JUDGE_SYSTEM = """You are grading whether the assistant surfaced Yuh products appropriately.

Return ONLY valid JSON:
{"pass": true|false, "reason": "short"}

You will receive:
- intent: "yuh_related" or "basic_knowledge" (or "unknown")
- assistant_output: the assistant response text
- products: a list of products returned by retrieval (may be empty)

Definitions:
- A "product example" means either:
  (a) a concrete product name from the provided products list appears in the output, OR
  (b) the output contains a clearly labeled section like "Examples you can explore in Yuh" followed by at least one bullet/item.

PASS rules:
1) If intent == "yuh_related":
   - PASS if the output includes at least one product example (definition above), OR
   - PASS if products list is empty AND the assistant explicitly says it can’t see matching products in the provided list and asks 1 clarifying question.
2) If intent == "basic_knowledge":
   - PASS if the output does NOT include product examples to explore in Yuh (no product list, no “examples in Yuh” section).

FAIL rules:
- If intent == "yuh_related" and products list is non-empty but the output gives no product examples.
- If intent == "basic_knowledge" and the output includes product examples or an "Examples you can explore in Yuh" section.

Important:
- Do NOT judge financial advice here.
- If intent is "unknown", PASS unless the output incorrectly lists Yuh product examples.
"""


EXAMPLES_HEADER_RE = re.compile(r"examples?\s+you\s+can\s+explore\s+in\s+yuh", re.IGNORECASE)
BULLET_LINE_RE = re.compile(r"^\s*[-•]\s+\S+", re.MULTILINE)


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def safe_json_loads(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"pass": False, "reason": "judge_parse_error"}


def normalize_text(s: str) -> str:
    return (s or "").lower()


def contains_any_product_name(output_text: str, products: List[Dict[str, Any]]) -> bool:
    t = normalize_text(output_text)
    for p in products or []:
        name = (p.get("name") or "").strip()
        if name and normalize_text(name) in t:
            return True
    return False


def has_examples_section_with_items(output_text: str) -> bool:
    if not EXAMPLES_HEADER_RE.search(output_text or ""):
        return False
    # If header exists, require at least one bullet somewhere after it.
    # Cheap approximation: require any bullet line in the full text.
    return bool(BULLET_LINE_RE.search(output_text or ""))


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
    ]
    return any(p in t for p in phrases)


def asks_a_question(output_text: str) -> bool:
    return "?" in (output_text or "")


def deterministic_grade(intent: str, output_text: str, products: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Returns:
      - dict(pass=..., reason=...) when deterministic
      - None when ambiguous and needs LLM judge
    """
    intent = (intent or "").strip()

    # Unknown intent: only fail if it clearly includes a Yuh examples section
    if intent == "unknown":
        if has_examples_section_with_items(output_text):
            return {"pass": False, "reason": "unknown_intent_but_yuh_examples_section_present"}
        return {"pass": True, "reason": "unknown_intent_no_yuh_examples"}

    if intent == "basic_knowledge":
        # Hard fail if it clearly surfaced Yuh examples
        if has_examples_section_with_items(output_text):
            return {"pass": False, "reason": "basic_knowledge_but_yuh_examples_section_present"}
        # If it mentions a product name from provided products (rare but possible), fail deterministically
        if products and contains_any_product_name(output_text, products):
            return {"pass": False, "reason": "basic_knowledge_but_product_name_present"}
        # Otherwise pass
        return {"pass": True, "reason": "basic_knowledge_no_product_examples"}

    if intent == "yuh_related":
        # If retrieval returned products, require at least one example deterministically
        if products:
            if contains_any_product_name(output_text, products) or has_examples_section_with_items(output_text):
                return {"pass": True, "reason": "yuh_related_product_example_present"}
            # Clear fail: products exist but none surfaced
            return {"pass": False, "reason": "yuh_related_products_available_but_none_surfaced"}

        # If no products available: ambiguous unless the assistant explicitly says so + asks 1 clarifying Q
        if explicitly_says_no_matches(output_text) and asks_a_question(output_text):
            return {"pass": True, "reason": "yuh_related_no_products_and_clarifying_question"}
        return None  # ambiguous: ask LLM

    return None


def judge_products_llm(
    client: OpenAI,
    user_input: str,
    assistant_output: str,
    intent: str,
    products: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    payload = {
        "intent": intent,
        "user_input": user_input,
        "assistant_output": assistant_output,
        "products": products,
    }
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": YUH_PRODUCTS_JUDGE_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0,
        max_tokens=220,
    )
    return safe_json_loads(resp.choices[0].message.content or "")


def main():
    cases_path = "eval/cases/yulia_eval_cases.jsonl"
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    cases = load_jsonl(cases_path)

    results: List[Dict[str, Any]] = []
    scored = 0
    passed = 0

    for case in cases:
        user_input = case["input"]
        app_out = yulia_reply(user_input)

        output_text = app_out.get("output_text", "")
        meta = app_out.get("meta", {}) or {}
        intent = meta.get("intent", "") or "unknown"
        confidence = meta.get("confidence", None)
        retries = meta.get("retries", 0)

        # Products passed from core.yulia_reply()
        products_meta = meta.get("products", []) or []

        grade = deterministic_grade(intent, output_text, products_meta)
        used_llm = False

        if grade is None:
            used_llm = True
            grade = judge_products_llm(
                client=client,
                user_input=user_input,
                assistant_output=output_text,
                intent=intent,
                products=products_meta,
                model="gpt-4o-mini",
            )

        # score only when intent is basic_knowledge or yuh_related
        if intent in {"basic_knowledge", "yuh_related"}:
            scored += 1
            if bool(grade.get("pass", False)):
                passed += 1

        results.append(
            {
                "id": case.get("id"),
                "input": user_input,
                "output_text": output_text,
                "grade": grade,
                "meta": {
                    **meta,
                    "intent": intent,
                    "confidence": confidence,
                    "retries": retries,
                    "products": products_meta,
                },
                "judge_meta": {"used_llm": used_llm},
            }
        )

    pass_rate = (passed / scored) if scored else 0.0
    print(f"Products surfacing eval scored: {scored} | Pass: {passed} | Pass rate: {pass_rate:.0%}")

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

    # Optional hard fail if anything failed among scored intents
    if scored and passed != scored:
        sys.exit(1)


if __name__ == "__main__":
    main()
