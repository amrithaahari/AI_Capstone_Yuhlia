# ui_components.py
# ui_components.py (top of file)
import streamlit as st
import streamlit.components.v1 as components  # <-- add this
import re
from typing import Optional

from models import ConversationState, Product


def display_debug_info(payload: dict) -> None:
    # Visible + compact; avoids nested expanders everywhere
    st.caption("Debug")
    st.json(payload, expanded=False)


def init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversation_state" not in st.session_state:
        st.session_state.conversation_state = ConversationState()
    if "show_debug" not in st.session_state:
        st.session_state.show_debug = False



def render_products_table(products: list[Product], table_key: str, default_limit: int = 10) -> None:
    if not products:
        return

    expanded_key = f"{table_key}_expanded"
    if expanded_key not in st.session_state:
        st.session_state[expanded_key] = False

    expanded = bool(st.session_state[expanded_key])

    total = len(products)
    limit = default_limit
    shown_products = products if expanded else products[:limit]

    # Toggle control (only if needed)

    rows_html = []
    for p in shown_products:
        name = (getattr(p, "name", "") or "").strip()
        p_type = (getattr(p, "type", "") or "").strip()

        rows_html.append(
            f"""
            <div class="yuh-row">
              <div class="yuh-cell yuh-name">{_escape_html(name)}</div>
              <div class="yuh-cell yuh-type">{_escape_html(p_type)}</div>
            </div>
            """
        )

    html = f"""
    <style>
      .yuh-table {{
        background: rgba(255,255,255,.85);
        border: 1px solid rgba(50, 50, 93, .10);
        border-radius: 18px;
        overflow: hidden;
        box-shadow: 0 6px 18px rgba(30, 20, 60, 0.06);
        margin-top: 10px;
      }}
      .yuh-head {{
        display: flex;
        padding: 12px 14px;
        font-weight: 700;
        font-size: 13px;
        color: rgba(20, 20, 30, 0.72);
        border-bottom: 1px solid rgba(50, 50, 93, .10);
      }}
      .yuh-head .yuh-h1 {{ flex: 1.35; }}
      .yuh-head .yuh-h2 {{ flex: 1; }}
      .yuh-row {{
        display: flex;
        padding: 12px 14px;
        border-bottom: 1px solid rgba(50, 50, 93, .08);
        align-items: center;
        gap: 10px;
      }}
      .yuh-row:last-child {{ border-bottom: none; }}
      .yuh-cell {{
        font-size: 14px;
        line-height: 1.2;
        color: rgba(18, 18, 26, 0.92);
        font-family: "Proxima Soft", -apple-system, BlinkMacSystemFont, "Segoe UI",
                     Inter, Roboto, Helvetica, Arial, sans-serif;
      }}
      .yuh-name {{ flex: 1.35; font-weight: 650; }}
      .yuh-type {{ flex: 1; font-weight: 500; color: rgba(18, 18, 26, 0.78); }}
    </style>

    <div class="yuh-table">
      <div class="yuh-head">
        <div class="yuh-h1">Name</div>
        <div class="yuh-h2">Type</div>
      </div>
      {''.join(rows_html)}
    </div>
    """

    # Height: header (~46) + row height (~44) * shown + padding
    height = 60 + (len(shown_products) * 44)
    components.html(html, height=height, scrolling=False)

    if total > limit:
        label = "Show less" if expanded else f"Show more ({total - limit} more)"
        if st.button(label, key=f"{table_key}_toggle", use_container_width=True):
            st.session_state[expanded_key] = not expanded
            st.rerun()


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&#039;")
    )


def render_assistant_message_with_table(
    message: str,
    products: Optional[list[Product]],
    table_key: str,
) -> None:
    TABLE_TOKEN_RE = re.compile(r"\[\[\s*PRODUCT_TABLE\s*\]\]|\[\s*PRODUCT_TABLE\s*\]", re.IGNORECASE)
    msg = (message or "").strip()

    token_found = TABLE_TOKEN_RE.search(msg or "")
    token_found = token_found.group(0) if token_found else None

    if token_found and products:
        cleaned = TABLE_TOKEN_RE.sub("", msg or "").strip()
        if cleaned:
            st.markdown(cleaned)
        render_products_table(products, table_key=table_key)
        return

    if msg:
        st.markdown(msg)
    if products:
        render_products_table(products, table_key=table_key)

