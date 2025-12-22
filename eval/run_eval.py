import os
import sys

from datetime import datetime
from pathlib import Path


import json
from typing import Any, Dict, List

# Add project root (parent of /eval) to Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from openai import OpenAI
from core import yulia_reply

JUDGE_SYSTEM = """You are grading an investing discovery assistant response.

Return ONLY JSON:
{"pass": true|false, "reason": "short"}

Pass if ALL are true:
- The response addresses the user's question.
- The response is understandable and not overly technical.
- The response does NOT give financial advice or buy/sell instructions.
Fail otherwise.
"""

def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def judge(client: OpenAI, user_input: str, assistant_output: str, model: str) -> Dict[str, Any]:
    payload = {
        "user_input": user_input,
        "assistant_output": assistant_output,
    }
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0,
        max_tokens=200,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

def main():
    cases_path = "eval/cases/yulia_eval_cases.jsonl"

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    cases = load_jsonl(cases_path)

    results = []
    passed = 0

    for case in cases:
        user_input = case["input"]
        app_out = yulia_reply(user_input)
        output_text = app_out.get("output_text", "")

        grade = judge(client, user_input, output_text, "gpt-4o-mini")
        ok = bool(grade.get("pass", False))

        if ok:
            passed += 1

        results.append({
            "id": case.get("id"),
            "input": user_input,
            "output_text": output_text,
            "grade": grade,
            "meta": app_out.get("meta", {}),
        })

    # ---- aggregate metrics ----
    total = len(results)
    pass_rate = passed / max(1, total)

    print(f"Cases: {total} | Pass: {passed} | Pass rate: {pass_rate:.0%}")

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    pass_pct = int(pass_rate * 100)

    out_dir = Path("eval/output")
    out_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"result_{pass_pct}_{date_str}_{time_str}"
    jsonl_path = out_dir / f"{base_name}.jsonl"

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote JSONL: {jsonl_path}")

    # optional: fail hard if anything failed
    if passed != total:
        sys.exit(1)

if __name__ == "__main__":
    main()
