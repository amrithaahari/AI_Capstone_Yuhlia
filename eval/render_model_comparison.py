# eval/render_model_comparison.py
import json
import argparse
import re
from pathlib import Path
from statistics import mean
from html import escape
from typing import Dict, List, Any, Optional, Tuple


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def quantile(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[int((len(xs) - 1) * q)]


def _infer_model_from_filename(p: Path) -> Optional[str]:
    """
    Expected names:
      result_<safe_model>_<pct>_<YYYY-MM-DD>_<HHMMSS>.jsonl
      result_products_<safe_model>_<pct>_<YYYY-MM-DD>_<HHMMSS>.jsonl

    safe_model is model with '.' replaced by '_'.
    Example: gpt-4_1 -> gpt-4.1
    """
    name = p.name
    m = re.match(r"^result(?:_products)?_(.+?)_\d+_\d{4}-\d{2}-\d{2}_\d{6}\.jsonl$", name)
    if not m:
        return None
    safe_model = m.group(1)
    return safe_model.replace("_", ".")  # reverse safe_model used in eval_models.py


def _sum_cost_from_rows(rows: List[Dict[str, Any]]) -> float:
    total = 0.0
    for r in rows:
        meta = r.get("meta", {}) or {}
        cost = meta.get("cost", {}) or {}
        # preferred: meta.cost.est_cost_usd
        v = cost.get("est_cost_usd", None)
        if isinstance(v, (int, float)):
            total += float(v)
    return float(total)


def _avg_cost_per_case(rows: List[Dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return _sum_cost_from_rows(rows) / len(rows)


def _pass_rate(rows: List[Dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    passed = sum(1 for r in rows if bool((r.get("grade", {}) or {}).get("pass", False)))
    return 100.0 * passed / len(rows)


def _overall_pass_rate(context_rows: List[Dict[str, Any]], product_rows: List[Dict[str, Any]]) -> float:
    """
    Overall pass = context pass AND products pass for the same case id.
    If ids are missing, fallback to min(len) positional matching.
    """
    if not context_rows or not product_rows:
        return 0.0

    # Prefer id-based matching
    ctx_by_id = {r.get("id"): r for r in context_rows if r.get("id") is not None}
    prod_by_id = {r.get("id"): r for r in product_rows if r.get("id") is not None}
    common_ids = [i for i in ctx_by_id.keys() if i in prod_by_id]

    if common_ids:
        ok = 0
        for i in common_ids:
            cpass = bool((ctx_by_id[i].get("grade", {}) or {}).get("pass", False))
            ppass = bool((prod_by_id[i].get("grade", {}) or {}).get("pass", False))
            if cpass and ppass:
                ok += 1
        return 100.0 * ok / len(common_ids)

    # Fallback: positional
    n = min(len(context_rows), len(product_rows))
    ok = 0
    for i in range(n):
        cpass = bool((context_rows[i].get("grade", {}) or {}).get("pass", False))
        ppass = bool((product_rows[i].get("grade", {}) or {}).get("pass", False))
        if cpass and ppass:
            ok += 1
    return 100.0 * ok / max(1, n)


def render(models_summary: List[Dict[str, Any]], out_path: Path):
    rows_html = []
    for m in models_summary:
        rows_html.append(
            f"""
<tr>
  <td>{escape(m['model'])}</td>
  <td>{m['cases']}</td>
  <td>{m['context_pass']:.1f}%</td>
  <td>{m['products_pass']:.1f}%</td>
  <td>{m['overall_pass']:.1f}%</td>
  <td>${m['total_cost']:.4f}</td>
  <td>${m['cost_per_case']:.5f}</td>
</tr>
"""
        )

    html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Model Comparison</title>
<style>
body {{ font-family: sans-serif; background:#0b0f17; color:#e6edf3; padding:40px }}
table {{ width:100%; border-collapse:collapse }}
th,td {{ padding:10px; border-bottom:1px solid #263246; text-align:left }}
th {{ background:#121a26 }}
</style>
</head>
<body>
<h1>Model comparison: quality · cost</h1>

<table>
<thead>
<tr>
  <th>Model</th>
  <th>Cases</th>
  <th>Context pass</th>
  <th>Products pass</th>
  <th>Overall</th>
  <th>Total cost</th>
  <th>Cost / case</th>
</tr>
</thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--context",
        nargs="+",
        required=True,
        help="List of context result jsonl files (one per model), e.g. eval/output/result_gpt-4_1_83_....jsonl",
    )
    ap.add_argument(
        "--products",
        nargs="+",
        required=True,
        help="List of products result jsonl files (one per model), e.g. eval/output/result_products_gpt-4_1_100_....jsonl",
    )
    ap.add_argument("--out", default="eval/output/model_comparison.html")
    args = ap.parse_args()

    # Load and group by inferred model
    ctx_by_model: Dict[str, List[Dict[str, Any]]] = {}
    for fp in args.context:
        p = Path(fp)
        model = _infer_model_from_filename(p) or p.stem
        ctx_by_model[model] = load_jsonl(p)

    prod_by_model: Dict[str, List[Dict[str, Any]]] = {}
    for fp in args.products:
        p = Path(fp)
        model = _infer_model_from_filename(p) or p.stem
        prod_by_model[model] = load_jsonl(p)

    # Models present in either set
    models = sorted(set(ctx_by_model.keys()) | set(prod_by_model.keys()))

    summary: List[Dict[str, Any]] = []
    for model in models:
        ctx_rows = ctx_by_model.get(model, [])
        prod_rows = prod_by_model.get(model, [])

        cases = max(len(ctx_rows), len(prod_rows))

        context_pass = _pass_rate(ctx_rows) if ctx_rows else 0.0
        products_pass = _pass_rate(prod_rows) if prod_rows else 0.0
        overall_pass = _overall_pass_rate(ctx_rows, prod_rows)

        # Cost: both files contain the same meta.cost per case; sum once (prefer context file)
        cost_rows = ctx_rows if ctx_rows else prod_rows
        total_cost = _sum_cost_from_rows(cost_rows)
        cost_per_case = (total_cost / len(cost_rows)) if cost_rows else 0.0

        summary.append(
            {
                "model": model,
                "cases": cases,
                "context_pass": context_pass,
                "products_pass": products_pass,
                "overall_pass": overall_pass,
                "total_cost": total_cost,
                "cost_per_case": cost_per_case,
            }
        )

    render(summary, Path(args.out))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
