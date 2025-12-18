import streamlit as st

from database import init_database
from conversation import process_user_message, reset_state
from ui_components import (
    init_session_state,
    display_suggested_prompts,
    display_debug_info,
)

@st.cache_resource
def db_ready() -> bool:
    init_database()
    return True

def main():
    st.set_page_config(page_title="Yulia Assistant", page_icon="💎", layout="wide")

    db_ready()
    init_session_state()

    st.title("💎 Yulia Assistant")
    st.caption("Educational investing discovery. No advice. Products shown are examples available in yuh.")

    st.session_state.show_debug = st.toggle("Show debug", value=st.session_state.show_debug)

    if len(st.session_state.messages) == 0:
        display_suggested_prompts()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if st.session_state.show_debug and msg.get("debug"):
                display_debug_info(msg["debug"])

    user_input = st.chat_input("Ask me about investing or yuh products...")

    if "user_input" in st.session_state:
        user_input = st.session_state.user_input
        del st.session_state.user_input

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        with st.chat_message("assistant"):
            result = process_user_message(user_input, st.session_state.conversation_state)
            st.write(result.message)
            if st.session_state.show_debug:
                display_debug_info(
                    {
                        "intent": result.intent,
                        "confidence": result.confidence,
                        "retries": result.retries,
                        "type": result.type,
                        "responses": result.responses,
                    }
                )

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result.message,
                "products": result.products or [],
                "debug": {
                    "intent": result.intent,
                    "confidence": result.confidence,
                    "retries": result.retries,
                    "type": result.type,
                    "responses": result.responses,
                },
            }
        )

        if result.type in {"mismatch", "guardrail_failure"}:
            reset_state(st.session_state.conversation_state)

if __name__ == "__main__":
    main()
