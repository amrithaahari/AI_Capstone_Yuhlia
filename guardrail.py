# guardrail.py
import re
from typing import Tuple, List

BLOCK_PATTERNS = [
    r"\bguarantee(d)?\b",
    r"\bwill (definitely|certainly)\b",
    r"\bprice target\b",
    r"\b(buy|sell) (now|this)\b",
]

def guardrail_check(text: str) -> Tuple[bool, List[str]]:
    t = (text or "").lower()
    reasons = []
    for p in BLOCK_PATTERNS:
        if re.search(p, t):
            reasons.append(f"disallowed phrasing: /{p}/")
    return (len(reasons) == 0), reasons
