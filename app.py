# app.py
import streamlit as st

from database import init_database
from conversation import process_user_message, reset_state
from ui_components import (
    init_session_state,
    display_debug_info,
    render_assistant_message_with_table,
)


@st.cache_resource
def db_ready() -> bool:
    init_database()
    return True


def main():
    st.set_page_config(page_title="Yulia Assistant", page_icon="💎", layout="centered")

    MOBILE_CSS = """
    <style>
      /* Phone canvas */
      .block-container {
        max-width: 430px;
        padding-top: 44px;      /* FIX: prevent header clipping */
        padding-bottom: 124px;  /* room above chat input */
      }

      /* Background gradient */
      .stApp {
        background: radial-gradient(circle at 20% 10%, rgba(190, 170, 255, .35), transparent 40%),
                    radial-gradient(circle at 80% 30%, rgba(255, 190, 220, .30), transparent 45%),
                    linear-gradient(180deg, #f5f2ff 0%, #f7f7fb 55%, #f5f2ff 100%);
      }

      /* Typography */
      html, body, [class*="css"]  {
        font-family: "Proxima Nova", -apple-system, BlinkMacSystemFont, "Segoe UI",
                     Inter, Roboto, Helvetica, Arial, sans-serif;
      }

      /* Smaller overall text */
      .stMarkdown, .stMarkdown p, .stChatMessageContent {
        font-size: 14px !important;
        line-height: 1.35 !important;
      }

      /* Header */
      .yuh-header{
        display:flex;
        flex-direction:column;
        align-items:center;
        justify-content:center;
        text-align:center;
        margin-top: 12px;
        margin-bottom: 22px;
      }
    
      .yuh-title{
        font-size: 34px;
        font-weight: 800;
        letter-spacing: -0.4px;
        color: #12121a;
        margin: 0;
        line-height: 1.1;
        text-align:center;
      }
    
      .yuh-sub{
        font-size: 17px;
        font-weight: 600;
        color: rgba(60, 35, 90, .85);
        margin-top: 8px;
        text-align:center;
      }


      /* Chat bubbles */
      [data-testid="stChatMessage"] {
        border-radius: 18px;
      }

      /* Chip buttons */
      .yuh-chip button {
        width: 100%;
        border-radius: 999px !important;
        padding: 10px 14px !important;
        border: 1px solid rgba(50, 50, 93, .18) !important;
        background: rgba(255,255,255,.70) !important;
        font-size: 14px !important;
      }

      /* Bottom controls row */
      .yuh-bottom-controls {
        margin-top: 10px;
        margin-bottom: 8px;
      }

      /* Make toggle label smaller */
      [data-testid="stToggleSwitch"] label p {
        font-size: 13px !important;
      }
    </style>
    """
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)

    db_ready()
    init_session_state()

    # Header (mobile-style)
    st.markdown(
        """
        <div class="yuh-header">
          <div class="yuh-title">Hello</div>
          <div class="yuh-sub">How can I help you today?</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Render chat history (INCLUDING product tables)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            content = msg.get("content", "")
            products = msg.get("products") or []

            if msg["role"] == "assistant":
                render_assistant_message_with_table(content, products)
            else:
                st.write(content)

            if st.session_state.show_debug and msg.get("debug"):
                display_debug_info(msg["debug"])

    # Bottom controls: chips + debug + new chat (just above chat input)
    st.markdown('<div class="yuh-bottom-controls">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1, 1, 0.85, 0.85], gap="small")

    with c1:
        st.markdown('<div class="yuh-chip">', unsafe_allow_html=True)
        if st.button("What is the safest way to start investing", use_container_width=True):
            st.session_state.user_input = "What is the safest way to start investing in yuh"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="yuh-chip">', unsafe_allow_html=True)
        if st.button("Show me low-fee global ETFs", use_container_width=True):
            st.session_state.user_input = "What low-fee world ETFs are available on yuh?"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with c3:
        st.session_state.show_debug = st.toggle("Debug", value=st.session_state.show_debug)

    with c4:
        if st.button("New chat", use_container_width=True):
            st.session_state.messages = []
            reset_state(st.session_state.conversation_state)
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    user_input = st.chat_input('Ask about investing or products on yuh…')

    if "user_input" in st.session_state:
        user_input = st.session_state.user_input
        del st.session_state.user_input

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        with st.chat_message("assistant"):
            result = process_user_message(user_input, st.session_state.conversation_state)
            render_assistant_message_with_table(result.message, result.products or [])

            debug_payload = {
                "intent": result.intent,
                "confidence": result.confidence,
                "retries": result.retries,
                "type": result.type,
                "responses": result.responses,
                "guardrail": result.guardrail,
            }

            if st.session_state.show_debug:
                display_debug_info(debug_payload)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result.message,
                "products": result.products or [],
                "debug": debug_payload,
            }
        )

        if result.type in {"guardrail_failure", "error"}:
            reset_state(st.session_state.conversation_state)


if __name__ == "__main__":
    main()
