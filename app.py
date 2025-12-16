# app.py
import streamlit as st
import asyncio
from pipeline import run_turn

DB_PATH = "yuh_products.db"

st.title("Yulia prototype")

if "state" not in st.session_state:
    st.session_state.state = {"mode": "AWAITING_GOAL"}

# Suggested prompts
st.subheader("Suggestions")
suggestions = [
    "I'm a beginner. How do I start investing?",
    "I want something safe and low risk.",
    "I’m curious about crypto but don’t know where to start.",
    "Are there themed investments like AI or clean energy?",
]
cols = st.columns(2)
for i, s in enumerate(suggestions):
    if cols[i % 2].button(s):
        st.session_state.state["last_user_message"] = s
        st.session_state.last_result = asyncio.run(run_turn(st.session_state.state, DB_PATH))

st.subheader("Your goal")
user_text = st.text_input("goal_text", "")

if st.button("Submit") and user_text.strip():
    st.session_state.state["last_user_message"] = user_text.strip()
    st.session_state.last_result = asyncio.run(run_turn(st.session_state.state, DB_PATH))

res = st.session_state.get("last_result")
if res:
    if res["response_type"] == "clarify":
        st.info(res["assistant_text"])
        for q in res.get("questions", []):
            st.write("- " + q)
    else:
        st.markdown(res["assistant_text"])
        st.caption(f"intent={res.get('intent')} conf={res.get('confidence')}, attempts={res.get('attempts')}, blocked={res.get('blocked')}")