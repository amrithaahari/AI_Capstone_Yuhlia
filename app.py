# app.py
import base64
from pathlib import Path

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


@st.cache_resource
def load_image_base64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("utf-8")


def main():
    st.set_page_config(page_title="Yulia Assistant", page_icon="💎", layout="centered")

    MOBILE_CSS = """
    <style>
      section.main > div.block-container,
      div[data-testid="stAppViewContainer"] section.main > div.block-container,
      div[data-testid="stAppViewContainer"] .main .block-container {
        max-width: 430px;
        padding-top: 44px !important;
        padding-bottom: 140px !important;
      }

      .stApp {
        background: radial-gradient(circle at 20% 10%, rgba(190, 170, 255, .35), transparent 40%),
                    radial-gradient(circle at 80% 30%, rgba(255, 190, 220, .30), transparent 45%),
                    linear-gradient(180deg, #f5f2ff 0%, #f7f7fb 55%, #f5f2ff 100%);
      }

      html, body, [class*="css"], .stApp  {
        font-family: "Proxima Soft", "Proxima Nova", -apple-system, BlinkMacSystemFont, "Segoe UI",
                     Inter, Roboto, Helvetica, Arial, sans-serif !important;
      }

      .stMarkdown, .stMarkdown p, .stChatMessageContent {
        font-size: 14px !important;
        line-height: 1.35 !important;
      }

      /* Logo */
      .yuh-logo {
        display: flex;
        justify-content: center;
        margin-top: 8px;
        margin-bottom: 10px;
      }
      .yuh-logo img {
        width: 80px;
        height: 80px;
      }

      /* Center header */
      .yuh-header{
        display:flex;
        flex-direction:column;
        align-items:center;
        justify-content:center;
        text-align:center;
        margin-top: 2px;
        margin-bottom: 14px;
      }
      .yuh-title{
        font-size: 34px;
        font-weight: 800;
        letter-spacing: -0.4px;
        color: #12121a;
        margin: 0;
        line-height: 1.1;
      }
      .yuh-sub{
        font-size: 17px;
        font-weight: 600;
        color: rgba(60, 35, 90, .85);
        margin-top: 8px;
      }

      /* Chips */
      .yuh-chip button {
        width: 100% !important;
        height: 40px !important;
        border-radius: 999px !important;
        padding: 0 14px !important;
        border: 1px solid rgba(50, 50, 93, .14) !important;
        background: rgba(255,255,255,.92) !important;
        font-size: 14px !important;
        font-weight: 700 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        line-height: 40px !important;
      }

      /* Debug toggle compact */
      [data-testid="stToggleSwitch"] label p {
        font-size: 13px !important;
        font-weight: 700 !important;
      }

      /* Chat input styling */
      div[data-testid="stChatInput"] textarea {
        border-radius: 999px !important;
        padding: 14px 16px !important;
        font-size: 15px !important;
      }
      /* 🔒 Normalize ALL text inside chat messages */
    [data-testid="stChatMessageContent"] * {
      font-size: 14px !important;
      line-height: 1.35 !important;
      font-weight: 400;
    }
    
    /* Lists specifically */
    [data-testid="stChatMessageContent"] ul,
    [data-testid="stChatMessageContent"] ol {
      padding-left: 18px;
    }
    
    [data-testid="stChatMessageContent"] li {
      margin-bottom: 6px;
    }
    
    /* Kill Markdown heading scaling */
    [data-testid="stChatMessageContent"] h1,
    [data-testid="stChatMessageContent"] h2,
    [data-testid="stChatMessageContent"] h3,
    [data-testid="stChatMessageContent"] h4,
    [data-testid="stChatMessageContent"] h5,
    [data-testid="stChatMessageContent"] h6 {
      font-size: 14px !important;
      font-weight: 600 !important; /* keep emphasis without size jump */
      margin: 10px 0 6px 0;
    }
    
    /* Bold text: emphasis only, not size */
    [data-testid="stChatMessageContent"] strong {
      font-weight: 600;
    }

    </style>
    """
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)

    db_ready()
    init_session_state()

    # --- Top: logo + header ---
    img_b64 = load_image_base64("assets/gen_yulia_ai_logo.png")
    st.markdown(
        f"""
        <div class="yuh-logo">
          <img src="data:image/png;base64,{img_b64}" alt="Yulia logo" />
        </div>
        <div class="yuh-header">
          <div class="yuh-title">Hello</div>
          <div class="yuh-sub">How can I help you today?</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Chips row ---
    chip_col1, chip_col2 = st.columns(2, gap="small")

    with chip_col1:
        st.markdown('<div class="yuh-chip">', unsafe_allow_html=True)
        if st.button("Safest way to start investing", use_container_width=True):
            st.session_state.user_input = "What is the safest way to start investing?"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with chip_col2:
        st.markdown('<div class="yuh-chip">', unsafe_allow_html=True)
        if st.button("Show low-fee global ETFs", use_container_width=True):
            st.session_state.user_input = "Show me low-fee global ETFs."
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Debug AFTER chips ---
    debug_row_left, debug_row_right = st.columns([1, 1], gap="small")
    with debug_row_right:
        st.session_state.show_debug = st.toggle("Debug", value=st.session_state.show_debug)

    # --- Chat history ---
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

    # --- Chat input ---
    user_input = st.chat_input("Ask about investing or products on yuh…")

    # Chip click injection
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
