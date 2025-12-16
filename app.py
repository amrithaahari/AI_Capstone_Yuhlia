"""
Main Streamlit application for Yulia Assistant
"""

import streamlit as st
import asyncio


#Import all modules (in actual implementation, these would be separate files)
from config import SUGGESTED_PROMPTS
from models import ConversationState
from database import init_database
from conversation import process_user_message
from ui_components import (
    init_session_state,
    display_suggested_prompts,
    display_product_table,
    display_debug_info
)

def main():
    """Main Streamlit application entry point"""

    # Page configuration
    st.set_page_config(
        page_title="Yulia Assistant",
        page_icon="💎",
        layout="wide"
    )

    # Initialize database (one-time setup)
    init_database()

    # Initialize session state
    init_session_state()

    # Header
    st.title("💎 Yulia Assistant")
    st.caption("Your guide to exploring investing concepts and yuh products")

    # Display suggested prompts for new conversations
    if len(st.session_state.messages) == 0:
        display_suggested_prompts(SUGGESTED_PROMPTS)

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if "products" in msg:
                display_product_table(msg["products"])
            if "debug" in msg:
                display_debug_info(msg["debug"])

    # Chat input
    user_input = st.chat_input("Ask me about investing or yuh products...")

    # Handle suggested prompt clicks
    if 'user_input' in st.session_state:
        user_input = st.session_state.user_input
        del st.session_state.user_input

    # Process user input
    if user_input:
        # Display user message
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        # Process message and generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Run async conversation processing
                result = asyncio.run(
                    process_user_message(user_input, st.session_state.conversation_state)
                )

                # Display assistant message
                st.write(result.message)

                # Display products if available
                if result.products:
                    display_product_table(result.products)

                # Display debug information
                display_debug_info({
                    "intent": result.intent,
                    "confidence": result.confidence,
                    "retries": result.retries,
                    "type": result.type
                })

                # Store assistant message in history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result.message,
                    "products": result.products or [],
                    "debug": {
                        "intent": result.intent,
                        "confidence": result.confidence,
                        "retries": result.retries,
                        "type": result.type
                    }
                })

                # Update state flags
                st.session_state.awaiting_followup = (result.type == "followup")

                # Reset conversation state if mismatch or failure
                if result.type in ["mismatch", "guardrail_failure"]:
                    st.session_state.conversation_state = ConversationState(
                        original_goal="",
                        followup_count=0,
                        followup_answers=[],
                        last_intent=None,
                        last_confidence=None
                    )


if __name__ == "__main__":
    main()