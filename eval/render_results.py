# eval/render_results.py
# Usage:
#   python eval/render_results.py --in eval/last_results.jsonl --out eval/last_results.html
#
# Changes vs previous version:
# - Removes Category column
# - Clicking a row opens a modal with: input, output, reason, pass/fail
# - Includes search + pass/fail filter

import argparse
import json
from pathlib import Path
from html import escape
from datetime import datetime

CSS = """
:root{
  --bg:#0b0f17;
  --panel:#121a26;
  --panel2:#0f1622;
  --text:#e6edf3;
  --muted:#9fb0c0;
  --border:#263246;
  --good:#1f9d55;
  --bad:#e5534b;
  --pill:#1b2535;
  --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  --sans: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans";
}

*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0;
  background:linear-gradient(180deg, #070a10 0%, var(--bg) 35%, #070a10 100%);
  color:var(--text);
  font-family:var(--sans);
}
.container{max-width:1200px; margin:0 auto; padding:28px 18px 40px}
.header{display:flex; align-items:flex-end; justify-content:space-between; gap:12px; margin-bottom:18px}
.h1{font-size:22px; font-weight:700; letter-spacing:.2px}
.sub{color:var(--muted); font-size:13px; margin-top:6px}

.card{
  background:rgba(18,26,38,.85);
  border:1px solid var(--border);
  border-radius:14px;
  box-shadow:0 10px 30px rgba(0,0,0,.35);
  overflow:hidden;
}

.metrics{display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; padding:14px}
.metric{
  padding:12px;
  background:rgba(15,22,34,.65);
  border:1px solid var(--border);
  border-radius:12px;
}
.metric .k{color:var(--muted); font-size:12px}
.metric .v{font-size:20px; font-weight:700; margin-top:6px}

.controls{
  display:flex; flex-wrap:wrap; gap:10px;
  padding:14px; border-top:1px solid var(--border)
}
.input, .select, .btn{
  background:rgba(15,22,34,.65);
  border:1px solid var(--border);
  color:var(--text);
  border-radius:10px;
  padding:10px;
  font-size:13px;
  outline:none;
}
.input{min-width:260px; flex:1}
.select{min-width:160px}
.btn{cursor:pointer}
.btn:hover{border-color:#3b82f6}

.tableWrap{overflow:hidden}
table{width:100%; border-collapse:separate; border-spacing:0}
thead th{
  text-align:left;
  font-size:12px;
  color:var(--muted);
  font-weight:600;
  padding:12px;
  background:rgba(15,22,34,.8);
  border-bottom:1px solid var(--border);
}
tbody td{
  padding:12px;
  border-bottom:1px solid rgba(38,50,70,.65);
  vertical-align:top;
  font-size:13px;
}
tbody tr:hover td{background:rgba(15,22,34,.35)}
.col-id{width:110px}
.col-pass{width:90px}
.col-reason{width:320px}

.pill{
  display:inline-flex; align-items:center; gap:6px;
  padding:4px 10px;
  border-radius:999px;
  font-size:12px;
  font-weight:700;
  background:var(--pill);
  border:1px solid var(--border);
}
.dot{width:8px; height:8px; border-radius:99px; display:inline-block}
.good{color:#c7f9cc}
.good .dot{background:var(--good)}
.bad{color:#ffd6d6}
.bad .dot{background:var(--bad)}

.mono{font-family:var(--mono)}
.small{color:var(--muted); font-size:12px}
.footer{margin-top:14px; color:var(--muted); font-size:12px; text-align:right}

/* Modal */
.modalOverlay{
  position:fixed;
  inset:0;
  background:rgba(0,0,0,.6);
  display:none;
  align-items:center;
  justify-content:center;
  padding:18px;
  z-index:9999;
}
.modal{
  width:min(960px, 100%);
  max-height:90vh;
  overflow:auto;
  background:rgba(18,26,38,.98);
  border:1px solid var(--border);
  border-radius:16px;
  box-shadow:0 20px 60px rgba(0,0,0,.5);
}
.modalHeader{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  padding:14px 14px;
  border-bottom:1px solid var(--border);
  position:sticky;
  top:0;
  background:rgba(18,26,38,.98);
}
.modalTitle{
  display:flex;
  align-items:center;
  gap:10px;
  font-weight:800;
}
.closeBtn{
  cursor:pointer;
  border:1px solid var(--border);
  background:rgba(15,22,34,.65);
  color:var(--text);
  border-radius:10px;
  padding:8px 10px;
  font-size:13px;
}
.closeBtn:hover{border-color:#3b82f6}
.modalBody{padding:14px}
.modalGrid{
  display:grid;
  grid-template-columns: 1fr 1fr;
  gap:12px;
}
.block{
  background:rgba(15,22,34,.65);
  border:1px solid var(--border);
  border-radius:12px;
  padding:12px;
  overflow:auto;
}
.block h4{
  margin:0 0 10px 0;
  font-size:12px;
  color:var(--muted);
  font-weight:700;
  text-transform:uppercase;
  letter-spacing:.6px
}
pre{
  margin:0;
  white-space:pre-wrap;
  word-break:break-word;
  font-family:var(--mono);
  font-size:12px;
  line-height:1.45;
}
@media (max-width: 900px){
  .metrics{grid-template-columns:1fr 1fr}
  .modalGrid{grid-template-columns:1fr}
  .col-reason{display:none}
}
"""

JS = """
function applyFilters(){
  const q = document.getElementById("search").value.toLowerCase();
  const f = document.getElementById("filter").value; // all|pass|fail
  const rows = document.querySelectorAll("tbody tr[data-row='main']");
  let shown = 0;

  rows.forEach(r=>{
    const rowPass = r.getAttribute("data-pass");
    const text = (r.getAttribute("data-search") || "").toLowerCase();
    const matchQ = !q || text.includes(q);
    const matchF = (f==="all") || (f===rowPass);
    const show = matchQ && matchF;
    r.style.display = show ? "" : "none";
    if(show) shown++;
  });

  document.getElementById("shown").innerText = shown;
}

function openModalFromRow(row){
  const dataJson = row.getAttribute("data-payload");
  if(!dataJson) return;
  const data = JSON.parse(dataJson);

  document.getElementById("m_id").innerText = data.id || "";
  document.getElementById("m_pass").innerHTML = data.pass_html || "";
  document.getElementById("m_reason").innerText = data.reason || "";
  document.getElementById("m_input").innerText = data.input || "";
  document.getElementById("m_output").innerText = data.output || "";

  const overlay = document.getElementById("overlay");
  overlay.style.display = "flex";
}

function closeModal(){
  document.getElementById("overlay").style.display = "none";
}

document.addEventListener("DOMContentLoaded", ()=>{
  document.getElementById("search").addEventListener("input", applyFilters);
  document.getElementById("filter").addEventListener("change", applyFilters);
  document.getElementById("closeBtn").addEventListener("click", closeModal);
  document.getElementById("overlay").addEventListener("click", (e)=>{
    if(e.target && e.target.id === "overlay") closeModal();
  });
  document.addEventListener("keydown", (e)=>{
    if(e.key === "Escape") closeModal();
  });

  document.querySelectorAll("tbody tr[data-row='main']").forEach(r=>{
    r.addEventListener("click", ()=>openModalFromRow(r));
  });

  applyFilters();
});
"""

def load_jsonl(path: Path):
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items

def pill_html(is_pass: bool) -> str:
    if is_pass:
        return '<span class="pill good"><span class="dot"></span>PASS</span>'
    return '<span class="pill bad"><span class="dot"></span>FAIL</span>'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", default=None)

    args = ap.parse_args()

    in_path = Path(args.inp)

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = in_path.with_suffix(".html")


    items = load_jsonl(in_path)

    total = len(items)
    passed = 0
    for r in items:
        g = r.get("grade", {})
        is_pass = bool(g.get("pass", False)) or bool(g.get("overall_pass", False))
        if is_pass:
            passed += 1
    failed = total - passed
    pass_rate = (passed / total * 100) if total else 0.0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows_html = []
    for i, r in enumerate(items):
        case_id = r.get("id", f"row_{i}")
        inp = r.get("input", "")
        out = r.get("output_text", "")
        grade = r.get("grade", {})
        is_pass = bool(grade.get("pass", False)) or bool(grade.get("overall_pass", False))
        reason = grade.get("reason", "") or ""

        # Search blob (id + input + reason)
        search_blob = f"{case_id} {inp} {reason}"

        payload = {
            "id": str(case_id),
            "pass_html": pill_html(is_pass),
            "reason": str(reason),
            "input": str(inp),
            "output": str(out),
        }

        rows_html.append(f"""
<tr data-row="main"
    data-pass="{'pass' if is_pass else 'fail'}"
    data-search="{escape(search_blob)}"
    data-payload="{escape(json.dumps(payload, ensure_ascii=False))}"
    style="cursor:pointer">
  <td class="col-id mono">{escape(str(case_id))}</td>
  <td class="col-pass">{pill_html(is_pass)}</td>
  <td>{escape(inp)}</td>
  <td class="col-reason small">{escape(str(reason))}</td>
</tr>
""")

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Yulia Eval Report</title>
  <style>{CSS}</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <div class="h1">Yulia Eval Report</div>
        <div class="sub">Source: {escape(str(in_path))} · Generated: {escape(now)}</div>
      </div>
      <div class="sub">Click a row to view details</div>
    </div>

    <div class="card">
      <div class="metrics">
        <div class="metric"><div class="k">Pass rate</div><div class="v">{pass_rate:.1f}%</div></div>
        <div class="metric"><div class="k">Total cases</div><div class="v">{total}</div></div>
        <div class="metric"><div class="k">Passed</div><div class="v">{passed}</div></div>
        <div class="metric"><div class="k">Failed</div><div class="v">{failed}</div></div>
      </div>

      <div class="controls">
        <input id="search" class="input" placeholder="Search by id, input text, reason…" />
        <select id="filter" class="select">
          <option value="all">All</option>
          <option value="pass">Pass only</option>
          <option value="fail">Fail only</option>
        </select>
        <button class="btn" onclick="document.getElementById('search').value=''; document.getElementById('filter').value='all'; applyFilters();">
          Reset
        </button>
        <div class="sub" style="margin-left:auto">Shown: <span id="shown">0</span> / {total}</div>
      </div>

      <div class="tableWrap">
        <table>
          <thead>
            <tr>
              <th class="col-id">ID</th>
              <th class="col-pass">Result</th>
              <th>Input</th>
              <th class="col-reason">Reason</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows_html)}
          </tbody>
        </table>
      </div>
    </div>

    <div class="footer">Report file: {escape(str(out_path))}</div>
  </div>

  <!-- Modal -->
  <div id="overlay" class="modalOverlay" aria-hidden="true">
    <div class="modal" role="dialog" aria-modal="true" aria-label="Eval details">
      <div class="modalHeader">
        <div class="modalTitle">
          <span class="mono" id="m_id"></span>
          <span id="m_pass"></span>
        </div>
        <button class="closeBtn" id="closeBtn">Close</button>
      </div>
      <div class="modalBody">
        <div class="block" style="margin-bottom:12px">
          <h4>Reason</h4>
          <pre id="m_reason"></pre>
        </div>
        <div class="modalGrid">
          <div class="block">
            <h4>Input</h4>
            <pre id="m_input"></pre>
          </div>
          <div class="block">
            <h4>Output</h4>
            <pre id="m_output"></pre>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>{JS}</script>
</body>
</html>
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
