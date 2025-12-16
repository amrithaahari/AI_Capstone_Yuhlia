"""
UI display components for Streamlit
"""

import streamlit as st
from typing import List, Dict


from models import Product, ConversationState

def display_product_table(products: List[Product]):
    """Display products as a formatted table"""
    if not products:
        return

    st.subheader("📊 Relevant Products")

    product_data = {
        "Name": [p.name for p in products],
        "Description": [p.description for p in products],
        "Sector": [p.sector for p in products],
        "Currency": [p.currency for p in products],
        "Region": [p.region for p in products],
        "ESG": [p.esg_score for p in products],
        "TER (%)": [p.ter for p in products]
    }

    st.dataframe(product_data, use_container_width=True)


def display_debug_info(result: Dict):
    """Display debug metadata in an expander"""
    with st.expander("🔍 Debug Information"):
        st.write(f"**Intent:** {result.get('intent', 'N/A')}")
        st.write(f"**Confidence:** {result.get('confidence', 0):.2f}")
        st.write(f"**Guardrail Retries:** {result.get('retries', 0)}")
        st.write(f"**Result Type:** {result.get('type', 'N/A')}")


def display_suggested_prompts(prompts: List[str]):
    """Display clickable suggested prompts"""
    st.write("**Suggested prompts:**")
    cols = st.columns(len(prompts))
    for idx, prompt in enumerate(prompts):
        if cols[idx].button(prompt, key=f"prompt_{idx}"):
            st.session_state.user_input = prompt
            st.rerun()


def init_session_state():
    """Initialize Streamlit session state"""
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'conversation_state' not in st.session_state:
        st.session_state.conversation_state = ConversationState(
            original_goal="",
            followup_count=0,
            followup_answers=[],
            last_intent=None,
            last_confidence=None
        )
    if 'awaiting_followup' not in st.session_state:
        st.session_state.awaiting_followup = False
