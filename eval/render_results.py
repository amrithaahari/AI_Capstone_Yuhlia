# eval/render_results.py
# Usage:
#   python eval/render_results.py --context eval/output/result_context.jsonl --products eval/output/result_products.jsonl --out eval/output/report.html
#
# Renders a single HTML report with 2 tabs:
# - Context eval
# - Yuh products eval

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

.tabs{
  display:flex;
  gap:10px;
  padding:14px;
  border-bottom:1px solid var(--border);
  background:rgba(15,22,34,.4);
}
.tabBtn{
  cursor:pointer;
  border:1px solid var(--border);
  background:rgba(15,22,34,.65);
  color:var(--text);
  border-radius:999px;
  padding:8px 12px;
  font-size:13px;
  font-weight:700;
}
.tabBtn:hover{border-color:#3b82f6}
.tabBtn.active{
  border-color:#3b82f6;
  box-shadow:0 0 0 2px rgba(59,130,246,.15) inset;
}

.tabPanel{display:none}
.tabPanel.active{display:block}

.metrics{display:grid; grid-template-columns: repeat(5, 1fr); gap:12px; padding:14px}
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
.col-intent{width:170px}
.col-conf{width:110px}
.col-retries{width:90px}
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
  .col-intent{display:none}
  .col-conf{display:none}
  .col-retries{display:none}
}
"""

JS = """
function applyFilters(panelId){
  const panel = document.getElementById(panelId);
  const q = panel.querySelector(".search").value.toLowerCase();
  const f = panel.querySelector(".filter").value; // all|pass|fail
  const rows = panel.querySelectorAll("tbody tr[data-row='main']");
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

  panel.querySelector(".shown").innerText = shown;
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
  document.getElementById("m_intent").innerText = data.intent || "";
  document.getElementById("m_conf").innerText = data.confidence || "";
  document.getElementById("m_retries").innerText = data.retries || "";

  document.getElementById("overlay").style.display = "flex";
}

function closeModal(){
  document.getElementById("overlay").style.display = "none";
}

function setActiveTab(tabName){
  document.querySelectorAll(".tabBtn").forEach(b=>b.classList.remove("active"));
  document.querySelectorAll(".tabPanel").forEach(p=>p.classList.remove("active"));

  document.getElementById("btn_"+tabName).classList.add("active");
  document.getElementById("panel_"+tabName).classList.add("active");

  applyFilters("panel_"+tabName);
}

document.addEventListener("DOMContentLoaded", ()=>{
  document.getElementById("btn_context").addEventListener("click", ()=>setActiveTab("context"));
  document.getElementById("btn_products").addEventListener("click", ()=>setActiveTab("products"));

  document.querySelectorAll(".tabPanel").forEach(panel=>{
    const panelId = panel.id;
    panel.querySelector(".search").addEventListener("input", ()=>applyFilters(panelId));
    panel.querySelector(".filter").addEventListener("change", ()=>applyFilters(panelId));
    panel.querySelector(".resetBtn").addEventListener("click", ()=>{
      panel.querySelector(".search").value = "";
      panel.querySelector(".filter").value = "all";
      applyFilters(panelId);
    });

    panel.querySelectorAll("tbody tr[data-row='main']").forEach(r=>{
      r.addEventListener("click", ()=>openModalFromRow(r));
    });
  });

  document.getElementById("closeBtn").addEventListener("click", closeModal);
  document.getElementById("overlay").addEventListener("click", (e)=>{
    if(e.target && e.target.id === "overlay") closeModal();
  });
  document.addEventListener("keydown", (e)=>{
    if(e.key === "Escape") closeModal();
  });

  setActiveTab("context");
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

def get_grade(item: dict) -> dict:
    return item.get("grade", {}) or {}

def summarize(items: list) -> dict:
    total = len(items)
    passed = 0
    for r in items:
        g = get_grade(r)
        is_pass = bool(g.get("pass", False)) or bool(g.get("overall_pass", False))
        if is_pass:
            passed += 1
    failed = total - passed
    pass_rate = (passed / total * 100) if total else 0.0
    return {"total": total, "passed": passed, "failed": failed, "pass_rate": pass_rate}

def build_rows_html(items: list) -> str:
    rows_html = []
    for i, r in enumerate(items):
        case_id = r.get("id", f"row_{i}")
        inp = r.get("input", "")
        out = r.get("output_text", "")
        meta = r.get("meta", {}) or {}

        intent = meta.get("intent") or r.get("intent") or ""
        retries = meta.get("retries")
        if retries is None:
            retries = r.get("retries", 0)
        confidence = meta.get("confidence")

        try:
            conf_val = float(confidence) if confidence is not None else None
        except Exception:
            conf_val = None
        conf_str = f"{conf_val:.2f}" if conf_val is not None else ""

        grade = get_grade(r)
        is_pass = bool(grade.get("pass", False)) or bool(grade.get("overall_pass", False))
        reason = grade.get("reason", "") or ""

        search_blob = f"{case_id} {intent} {conf_str} {retries} {inp} {reason}"

        payload = {
            "id": str(case_id),
            "pass_html": pill_html(is_pass),
            "reason": str(reason),
            "input": str(inp),
            "output": str(out),
            "intent": str(intent),
            "confidence": conf_str,
            "retries": str(retries),
        }

        rows_html.append(f"""
<tr data-row="main"
    data-pass="{'pass' if is_pass else 'fail'}"
    data-search="{escape(search_blob)}"
    data-payload="{escape(json.dumps(payload, ensure_ascii=False))}"
    style="cursor:pointer">
  <td class="col-id mono">{escape(str(case_id))}</td>
  <td class="col-pass">{pill_html(is_pass)}</td>
  <td class="col-intent">{escape(str(intent))}</td>
  <td class="col-conf mono">{escape(conf_str)}</td>
  <td class="col-retries mono">{escape(str(retries))}</td>
  <td>{escape(inp)}</td>
  <td class="col-reason small">{escape(str(reason))}</td>
</tr>
""")
    return "".join(rows_html)

def build_panel(panel_id: str, source_path: Path, items: list) -> str:
    m = summarize(items)
    rows = build_rows_html(items)
    return f"""
<div id="{panel_id}" class="tabPanel">
  <div class="metrics">
    <div class="metric"><div class="k">Pass rate</div><div class="v">{m["pass_rate"]:.1f}%</div></div>
    <div class="metric"><div class="k">Total cases</div><div class="v">{m["total"]}</div></div>
    <div class="metric"><div class="k">Passed</div><div class="v">{m["passed"]}</div></div>
    <div class="metric"><div class="k">Failed</div><div class="v">{m["failed"]}</div></div>
    <div class="metric"><div class="k">Source</div><div class="v mono" style="font-size:12px">{escape(source_path.name)}</div></div>
  </div>

  <div class="controls">
    <input class="input search" placeholder="Search by id, intent, input text, reason…" />
    <select class="select filter">
      <option value="all">All</option>
      <option value="pass">Pass only</option>
      <option value="fail">Fail only</option>
    </select>
    <button class="btn resetBtn">Reset</button>
    <div class="sub" style="margin-left:auto">Shown: <span class="shown">0</span> / {m["total"]}</div>
  </div>

  <div class="tableWrap">
    <table>
      <thead>
        <tr>
          <th class="col-id">ID</th>
          <th class="col-pass">Result</th>
          <th class="col-intent">Intent</th>
          <th class="col-conf">Conf</th>
          <th class="col-retries">Retries</th>
          <th>Input</th>
          <th class="col-reason">Reason</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </div>
</div>
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--context", required=True, help="JSONL from run_eval.py (context judge)")
    ap.add_argument("--products", required=True, help="JSONL from run_eval_products.py (yuh products judge)")
    ap.add_argument("--out", default=None, help="Output HTML path")
    args = ap.parse_args()

    context_path = Path(args.context)
    products_path = Path(args.products)

    out_path = Path(args.out) if args.out else context_path.with_suffix(".html")

    context_items = load_jsonl(context_path)
    products_items = load_jsonl(products_path)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    panel_context = build_panel("panel_context", context_path, context_items)
    panel_products = build_panel("panel_products", products_path, products_items)

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
        <div class="sub">Generated: {escape(now)}</div>
      </div>
      <div class="sub">Click a row to view details</div>
    </div>

    <div class="card">
      <div class="tabs">
        <button class="tabBtn" id="btn_context">Context eval</button>
        <button class="tabBtn" id="btn_products">Yuh products eval</button>
      </div>

      {panel_context}
      {panel_products}
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
          <h4>Meta</h4>
          <pre>Intent: <span id="m_intent"></span>
Confidence: <span id="m_conf"></span>
Retries: <span id="m_retries"></span></pre>
        </div>
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
