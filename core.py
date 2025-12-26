
from typing import Any, Dict, List

from models import ConversationState, Product
from conversation import process_user_message  # your orchestrator


def _products_to_meta(products: List[Product]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in products or []:
        out.append(
            {
                "id": p.id,
                "name": p.name,
            }
        )
    return out


def yulia_reply(user_input: str) -> Dict[str, Any]:
    """
    Returns a dict used by eval:
    {
      "output_text": str,
      "meta": {
        "intent": str,
        "confidence": float,
        "retries": int,
        "products": [{"id":..,"name":".."}...]
      }
    }
    """
    state = ConversationState()
    result = process_user_message(user_input, state)

    products = result.products or []
    meta = {
        "intent": result.intent,
        "confidence": result.confidence,
        "retries": result.retries,
        "products": _products_to_meta(products),
        "type": result.type,
    }

    return {
        "output_text": result.message,
        "meta": meta,
    }
