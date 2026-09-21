import random
import sqlite3
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nlp_layer import generate_sql, validate_and_execute  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "stackoverflow.db"

EXAMPLE_QUESTIONS = [
    "Top 20 tags by question volume",
    "Which questions have no accepted answer?",
    "Users with the highest answer acceptance rate",
    "Most common tag combinations",
    "Show me the top answerers in Python",
    "What's the median time to first answer?",
    "Which tags have the highest answer acceptance rate?",
    "Tags that are growing fastest year-over-year",
    "Show me the most commented questions",
    "What fraction of answers get accepted?",
    "Rank users by reputation in the Java tag",
    "Questions with 10+ answers but no accepted answer",
    "Average score of answers by tag",
    "Which users have never had an answer accepted?",
    "Trending tags in the last 6 months",
    "How many questions were asked each month?",
    "Which questions have the most views?",
    "Who are the users with the most badges?",
    "What is the average number of answers per question?",
    "Which tags have the most unanswered questions?",
    "What percentage of questions have an accepted answer, by tag?",
    "Show the top 10 highest-scoring answers",
    "Which users asked the most questions?",
    "How many questions were asked in 2021 vs 2020?",
    "What are the most popular tags used together with python?",
    "Which questions got their first answer within 10 minutes?",
    "Which hour of the day gets the most questions?",
    "What day of the week has the most questions?",
    "Which users have both asked and answered more than 3 questions?",
    "Show the most upvoted questions",
    "What are the most common vote types?",
    "Which tags have the highest average question score?",
    "Users who joined in 2022 with the highest reputation",
    "Which questions have the longest gap before their first answer?",
    "How has the number of javascript questions changed month by month?",
]

SHOWN = 7
MAX_QUESTIONS = 10


def new_sample():
    st.session_state.examples = random.sample(EXAMPLE_QUESTIONS, SHOWN)


def ask(question):
    st.session_state.pending = question


st.set_page_config(page_title="StackOverflow NLP Query Engine", layout="wide")
st.title("StackOverflow NLP Query Engine")
st.caption("Ask questions in plain English about StackOverflow questions, answers, tags, and users (2020–Sep 2022).")


@st.cache_resource
def get_connection():
    if not DB_PATH.exists():
        st.error(f"Database not found at {DB_PATH}. Run src/build_db.py first.")
        st.stop()
    return sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, check_same_thread=False)


conn = get_connection()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "examples" not in st.session_state:
    new_sample()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("df") is not None:
            st.dataframe(msg["df"], use_container_width=True)

with st.sidebar:
    st.subheader("Example questions")
    for i, example in enumerate(st.session_state.examples):
        st.button(example, key=f"ex_{i}", on_click=ask, args=(example,), use_container_width=True)
    st.button("Shuffle", on_click=new_sample, use_container_width=True)

typed = st.chat_input("Ask about StackOverflow...")
user_input = typed or st.session_state.pop("pending", None)

asked = sum(1 for m in st.session_state.messages if m["role"] == "user")
if user_input and asked >= MAX_QUESTIONS:
    st.warning(f"This demo is limited to {MAX_QUESTIONS} questions per session to control API costs. Refresh the page to start a new session.")
    user_input = None

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
