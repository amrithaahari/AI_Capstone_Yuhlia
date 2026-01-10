# eval/eval_models.py
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root (parent of /eval) to Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from openai import OpenAI
from core import yulia_reply

from eval.run_eval import judge as context_judge
from eval.run_eval_products import (
    deterministic_grade_surfacing,
    grade_products_correctness,
)

# Official pricing (Priority tier) per 1M tokens
# Source: https://platform.openai.com/docs/pricing
MODEL_PRICES_PER_1M = {
    "gpt-5.2": {"input": 3.50, "output": 28.00},
    "gpt-5-mini": {"input": 0.45, "output": 3.60},
    "gpt-4o-mini": {"input": 0.25, "output": 1.00},
    "gpt-4.1": {"input": 3.50, "output": 14.00},
}
EMBED_PRICES_PER_1M = {
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def safe_int(x: Any) -> int:
    try:
        return int(x)
    except Exception:
        return 0


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    p = MODEL_PRICES_PER_1M.get(model) or EMBED_PRICES_PER_1M.get(model)
    if not p:
        return None
    return (input_tokens / 1_000_000.0) * p["input"] + (output_tokens / 1_000_000.0) * p["output"]


def compute_case_cost_from_usage(usage: Dict[str, Any], fallback_model: str) -> Dict[str, Any]:
    """
    Returns:
      {
        "est_cost_usd": float,
        "by_model": {model: float},
        "tokens": {"input": int, "output": int, "total": int}
      }
    """
    usage = usage or {}
    in_tok = safe_int(usage.get("input_tokens"))
    out_tok = safe_int(usage.get("output_tokens"))
    total_tok = safe_int(usage.get("total_tokens"))

    by_model_usage = usage.get("by_model", {}) or {}
    by_model_cost: Dict[str, float] = {}
    total_cost = 0.0

    if by_model_usage:
        for m, u in by_model_usage.items():
            mi = safe_int(u.get("input_tokens"))
            mo = safe_int(u.get("output_tokens"))
            c = estimate_cost_usd(m, mi, mo)
            if c is None:
                continue
            by_model_cost[m] = float(c)
            total_cost += float(c)
    else:
        c = estimate_cost_usd(fallback_model, in_tok, out_tok)
        if c is not None:
            total_cost += float(c)
            by_model_cost[fallback_model] = float(c)

    return {
        "est_cost_usd": float(total_cost),
        "by_model": by_model_cost,
        "tokens": {"input": in_tok, "output": out_tok, "total": total_tok},
    }


def main():
    # Make default cases path stable regardless of current working directory
    cases_path = os.path.join(PROJECT_ROOT, "eval", "cases", "yulia_eval_cases.jsonl")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    cases = load_jsonl(cases_path)

    models_to_test = [
        "gpt-5.2",
        "gpt-4o-mini",
        "gpt-4.1",
    ]

    out_dir = Path(os.path.join(PROJECT_ROOT, "eval", "output"))
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")

    for model in models_to_test:
        os.environ["YULIA_GEN_MODEL"] = model

        context_results = []
        products_results = []

        ctx_passed = 0
        prod_passed = 0

        total_app_input_tokens = 0
        total_app_output_tokens = 0
        total_app_cost_usd = 0.0

        for case in cases:
            user_input = case["input"]
            expected = case.get("expected", {}) or {}

            app_out = yulia_reply(user_input)
            output_text = app_out.get("output_text", "")
            meta = app_out.get("meta", {}) or {}

            # ---- cost per case (stored into outputs) ----
            usage = meta.get("usage", {}) or {}
            cost_obj = compute_case_cost_from_usage(usage, fallback_model=model)

            # These are the fields your renderers can rely on
            meta["cost"] = cost_obj  # <--- FIX: write cost into outputs

            total_app_input_tokens += cost_obj["tokens"]["input"]
            total_app_output_tokens += cost_obj["tokens"]["output"]
            total_app_cost_usd += float(cost_obj["est_cost_usd"])

            # ---------- Context eval ----------
            ctx_grade = context_judge(client, user_input, output_text, "gpt-4o-mini")
            if bool(ctx_grade.get("pass", False)):
                ctx_passed += 1

            context_results.append(
                {
                    "id": case.get("id"),
                    "input": user_input,
                    "output_text": output_text,
                    "grade": ctx_grade,
                    "meta": meta,
                }
            )

            # ---------- Products eval ----------
            products_meta = meta.get("products", []) or []
            intent = meta.get("intent", "") or "unknown"

            surf = deterministic_grade_surfacing(intent, output_text, products_meta)
            corr = grade_products_correctness(products_meta, expected)

            overall_pass = bool(surf.get("pass", False)) and (
                bool(corr.get("pass", False)) if expected else True
            )
            reason_parts = [surf.get("reason", "") or ""]
            if expected:
                reason_parts.append(corr.get("reason", "") or "")
            overall_reason = " | ".join([p for p in reason_parts if p])

            prod_grade = {
                "pass": overall_pass,
                "reason": overall_reason,
                "surfacing": surf,
                "correctness": corr,
            }

            if overall_pass:
                prod_passed += 1

            products_results.append(
                {
                    "id": case.get("id"),
                    "input": user_input,
                    "output_text": output_text,
                    "grade": prod_grade,
                    "meta": meta,
                }
            )

        total = len(cases)
        ctx_pass_rate = ctx_passed / max(1, total)
        prod_pass_rate = prod_passed / max(1, total)

        ctx_pct = int(ctx_pass_rate * 100)
        prod_pct = int(prod_pass_rate * 100)

        safe_model = model.replace(".", "_")
        ctx_base = f"result_{safe_model}_{ctx_pct}_{date_str}_{time_str}"
        prod_base = f"result_products_{safe_model}_{prod_pct}_{date_str}_{time_str}"

        ctx_path = out_dir / f"{ctx_base}.jsonl"
        prod_path = out_dir / f"{prod_base}.jsonl"

        with open(ctx_path, "w", encoding="utf-8") as f:
            for r in context_results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        with open(prod_path, "w", encoding="utf-8") as f:
            for r in products_results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        print(f"[{model}] Context: {ctx_passed}/{total} = {ctx_pass_rate:.0%} → {ctx_path}")
        print(f"[{model}] Products: {prod_passed}/{total} = {prod_pass_rate:.0%} → {prod_path}")
        print(f"[{model}] App tokens (excl judges): in={total_app_input_tokens}, out={total_app_output_tokens}")
        print(
            f"[{model}] App cost (excl judges): ${total_app_cost_usd:.6f} total, "
            f"${(total_app_cost_usd / max(1, total)):.6f} per case"
        )


if __name__ == "__main__":
    main()
