import streamlit as st
from typing import List, Dict

from models import Product, ConversationState
from config import SUGGESTED_PROMPTS

def display_product_table(products: List[Product]) -> None:
    if not products:
        return
    st.subheader("Relevant products (examples)")
    st.dataframe(
        {
            "Name": [p.name for p in products],
            "Description": [p.description for p in products],
            "Sector": [p.sector for p in products],
            "Currency": [p.currency for p in products],
            "Region": [p.region for p in products],
            "ESG": [p.esg for p in products],
            "TER": [p.ter for p in products],
        },
        use_container_width=True,
    )

def display_debug_info(result: Dict) -> None:
    with st.expander("Debug", expanded=False):
        st.write(f"Intent: {result.get('intent', 'n/a')}")
        st.write(f"Confidence: {result.get('confidence', 0):.2f}")
        st.write(f"Guardrail retries: {result.get('retries', 0)}")
        st.write(f"Result type: {result.get('type', 'n/a')}")

        responses = result.get("responses", [])
        if responses:
            st.markdown("### Generation attempts")
            for i, r in enumerate(responses, start=1):
                st.markdown(f"**Response {i}:**")
                st.code(r)
        gr = result.get("guardrail", None)
        if gr:
            st.markdown("### Guardrail")
            st.write(f"Passed: {gr.get('passed')}")
            st.write(f"Severity: {gr.get('severity')}")
            st.write(f"Category: {gr.get('category')}")
            st.write(f"Reason: {gr.get('reason')}")


def display_suggested_prompts() -> None:
    st.write("Suggested prompts:")
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
