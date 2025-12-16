# yulia.py
from typing import Optional, List, Dict, Any

async def yulia_generate(
    intent: str,
    user_text: str,
    products_md_table: str,
    guardrail_feedback: Optional[str] = None,
) -> str:
    # Replace with LLM call. Keep deterministic early (low temp).
    # Important rule: do not invent products outside table.
    fb = f"\nGuardrail feedback: {guardrail_feedback}\n" if guardrail_feedback else ""
    return (
        f"{fb}"
        f"Intent: {intent}\n\n"
        f"Here’s a safe starting point based on what you said:\n"
        f"- (stub) I will explain options and trade-offs without telling you what to buy.\n\n"
        f"Products you can explore in Yuh (from catalog search):\n{products_md_table}\n"
    )
