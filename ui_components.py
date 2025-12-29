# ui_components.py
import streamlit as st
import pandas as pd

from models import ConversationState, Product
from config import SUGGESTED_PROMPTS


def display_debug_info(payload: dict) -> None:
    with st.expander("Debug", expanded=False):
        st.write(payload)


def display_suggested_prompts() -> None:
    st.write("Try one of these:")
    cols = st.columns(len(SUGGESTED_PROMPTS))
    for i, prompt in enumerate(SUGGESTED_PROMPTS):
        if cols[i].button(prompt, key=f"prompt_{i}"):
            st.session_state.user_input = prompt
            st.rerun()


def init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversation_state" not in st.session_state:
        st.session_state.conversation_state = ConversationState()
    if "show_debug" not in st.session_state:
        st.session_state.show_debug = False


def render_products_table(products: list[Product]) -> None:
    """
    Single-table display with highlighting for commission-free ETFs.
    We do NOT say "recommended". We only label the offer neutrally.
    """
    if not products:
        return

    rows = []
    for p in products:
        p_type = getattr(p, "type", "") or ""
        ter = getattr(p, "ter", None)
        rows.append(
            {
                "Name": getattr(p, "name", "") or "",
                "Type": p_type,
                "Region": getattr(p, "region", "") or "",
                "TER": ter,
                "ESG_score": getattr(p, "esg_score", "") or getattr(p, "esg", "") or "",
                "ISIN": getattr(p, "isin", "") or "",
                "Offer": "Commission-free" if ("special savings" in p_type.lower()) else "",
                "_special": ("special savings" in p_type.lower()),
            }
        )

    df = pd.DataFrame(rows)

    # Sort: commission-free first, then TER ascending (nulls last), then Name
    if "TER" in df.columns:
        df["_ter_null"] = df["TER"].isna()
        df = df.sort_values(
            by=["_special", "_ter_null", "TER", "Name"],
            ascending=[False, True, True, True],
            kind="mergesort",
        ).drop(columns=["_ter_null"])

    # Hide helper column
    df_display = df.drop(columns=["_special"])

    def _style_row(row):
        # Bold rows with the offer badge
        if row.get("Offer") == "Commission-free":
            return ["font-weight: 700"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df_display.style.apply(_style_row, axis=1),
        use_container_width=True,
        hide_index=True,
    )
