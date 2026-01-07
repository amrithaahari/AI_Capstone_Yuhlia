# eval/render_model_comparison.py
import json
import argparse
from pathlib import Path
from statistics import mean
from html import escape

def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

def quantile(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[int((len(xs) - 1) * q)]

def render(models_summary, out_path: Path):
    rows = []
    for m in models_summary:
        rows.append(f"""
<tr>
  <td>{escape(m['model'])}</td>
  <td>{m['cases']}</td>
  <td>{m['context_pass']:.1f}%</td>
  <td>{m['products_pass']:.1f}%</td>
  <td>{m['overall_pass']:.1f}%</td>
  <td>{int(m['avg_ms'])}</td>
  <td>{int(m['p50_ms'])}</td>
  <td>{int(m['p90_ms'])}</td>
  <td>${m['total_cost']:.4f}</td>
  <td>${m['cost_per_case']:.5f}</td>
</tr>
""")

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
<h1>Model comparison: content · performance · cost</h1>

<table>
<thead>
<tr>
  <th>Model</th>
  <th>Cases</th>
  <th>Context pass</th>
  <th>Products pass</th>
  <th>Overall</th>
  <th>Avg ms</th>
  <th>P50 ms</th>
  <th>P90 ms</th>
  <th>Total cost</th>
  <th>Cost / case</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", required=True)
    ap.add_argument("--out", default="eval/output/model_comparison.html")
    args = ap.parse_args()

    items = load_jsonl(Path(args.infile))

    by_model = {}
    for r in items:
        by_model.setdefault(r["model"], []).append(r)

    summary = []
    for model, rows in by_model.items():
        ctx_pass = [r["grades"]["context"]["pass"] for r in rows]
        prod_pass = [r["grades"]["products"]["pass"] for r in rows]

        lat = [r["metrics"]["elapsed_ms"] for r in rows]
        cost = [r["metrics"]["est_cost_usd"] or 0 for r in rows]

        summary.append({
            "model": model,
            "cases": len(rows),
            "context_pass": 100 * sum(ctx_pass) / len(ctx_pass),
            "products_pass": 100 * sum(prod_pass) / len(prod_pass),
            "overall_pass": 100 * sum(
                1 for i in range(len(rows))
                if ctx_pass[i] and prod_pass[i]
            ) / len(rows),
            "avg_ms": mean(lat),
            "p50_ms": quantile(lat, 0.5),
            "p90_ms": quantile(lat, 0.9),
            "total_cost": sum(cost),
            "cost_per_case": sum(cost) / len(rows),
        })

    render(summary, Path(args.out))
    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()
