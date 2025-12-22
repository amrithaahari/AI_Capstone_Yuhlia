from models import ConversationState
from conversation import process_user_message

def yulia_reply(user_message: str) -> dict:
    state = ConversationState()  # reset per case (single-turn eval)
    result = process_user_message(user_message, state)
    return {
        "output_text": result.message,
        "meta": {
            "intent": result.intent,
            "confidence": result.confidence,
            "type": result.type,
            "retries": result.retries,
        },
    }
