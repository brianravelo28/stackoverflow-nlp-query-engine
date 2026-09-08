import sqlite3
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nlp_layer import generate_sql, validate_and_execute  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "stackoverflow.db"

st.set_page_config(page_title="StackOverflow NLP Query Engine", layout="wide")
st.title("StackOverflow NLP Query Engine")
st.caption("Ask questions in plain English about StackOverflow questions, answers, tags, and users (2020-2025).")


@st.cache_resource
def get_connection():
    if not DB_PATH.exists():
        st.error(f"Database not found at {DB_PATH}. Run src/build_db.py first.")
        st.stop()
    return sqlite3.connect(DB_PATH, check_same_thread=False)


conn = get_connection()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("df") is not None:
            st.dataframe(msg["df"], use_container_width=True)

user_input = st.chat_input("Ask about StackOverflow...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input, "df": None})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        try:
            sql = generate_sql(user_input)
        except ValueError as e:
            st.error(str(e))
            st.session_state.messages.append({"role": "assistant", "content": str(e), "df": None})
            st.stop()

        result, error = validate_and_execute(sql, conn)

        if error:
            content = f"Error: {error}\n\n```sql\n{sql}\n```"
            st.markdown(content)
            st.session_state.messages.append({"role": "assistant", "content": content, "df": None})
        else:
            content = f"```sql\n{sql}\n```"
            st.markdown(content)
            st.dataframe(result, use_container_width=True)
            st.session_state.messages.append({"role": "assistant", "content": content, "df": result})

with st.sidebar:
    st.subheader("Example questions")
    for example in [
        "Top 20 tags by question volume",
        "Which questions have no accepted answer?",
        "Users with the highest answer acceptance rate",
        "Most common tag combinations",
        "Show me the top answerers in Python",
    ]:
        st.markdown(f"- {example}")
