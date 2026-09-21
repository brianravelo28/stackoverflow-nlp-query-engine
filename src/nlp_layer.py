"""Natural-language -> SQL layer for the StackOverflow database.

generate_sql() asks Claude for a single SELECT statement grounded in the
schema below; validate_and_execute() enforces read-only safety before
running it against stackoverflow.db.
"""
import os
import sqlite3
from pathlib import Path

import pandas as pd
from anthropic import Anthropic

DB_PATH = Path(__file__).resolve().parent.parent / "stackoverflow.db"
MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a SQL expert. Users ask questions about a StackOverflow database (2020–Sep 2022).
Respond ONLY with a valid SQLite SELECT query. No explanations. No markdown fences. Just SQL.

SCHEMA:
- users(user_id, display_name, reputation, badge_count, creation_date)
- tags(tag_id, tag_name)
- posts_questions(post_id, user_id, title, body, creation_date, view_count, answer_count, score, accepted_answer_id)
- posts_answers(post_id, user_id, parent_id, body, creation_date, score, is_accepted)
- post_tags(post_id, tag_id)
- comments(comment_id, post_id, user_id, body, creation_date, score)
- votes(vote_id, post_id, user_id, vote_type, creation_date)  -- user_id may be NULL, votes are anonymized

NOTES:
- Data covers 2020-01-01 through 2022-09-25 only. Treat "recent", "last month", "last 6 months" as relative to 2022-09-25 (use date('2022-09-25', '-1 month')), never date('now').
- 2022 is a partial year; for year-over-year comparisons use complete years (2020 vs 2021) unless asked otherwise, and require a minimum count (e.g. HAVING prior_year_count >= 50).
- posts_answers.parent_id references posts_questions.post_id (the question an answer belongs to)
- post_tags is the many-to-many join between posts_questions and tags
- is_accepted is 1 if that answer was accepted, else 0
- To join a tag name to questions: posts_questions -> post_tags -> tags
- SQLite has no MEDIAN(); if asked for a median, either approximate with AVG or return raw values
  ordered so the caller can compute it, and say so is not needed -- just write your best single query.
- SQLite date functions: julianday(), strftime('%Y', creation_date) for year extraction

EXAMPLES:
Q: "Top 20 tags by question volume"
A: SELECT t.tag_name, COUNT(pt.post_id) AS question_count FROM tags t LEFT JOIN post_tags pt ON t.tag_id = pt.tag_id GROUP BY t.tag_id, t.tag_name ORDER BY question_count DESC LIMIT 20;

Q: "Which questions have no accepted answer?"
A: SELECT post_id, title, creation_date, answer_count FROM posts_questions WHERE accepted_answer_id IS NULL ORDER BY creation_date DESC LIMIT 50;

Q: "Users with the highest answer acceptance rate"
A: SELECT u.user_id, u.display_name, COUNT(*) AS total_answers, SUM(a.is_accepted) AS accepted_answers, ROUND(1.0 * SUM(a.is_accepted) / COUNT(*), 3) AS acceptance_rate FROM posts_answers a JOIN users u ON a.user_id = u.user_id GROUP BY u.user_id, u.display_name HAVING COUNT(*) >= 5 ORDER BY acceptance_rate DESC LIMIT 20;

Q: "Most common tag combinations"
A: SELECT t1.tag_name AS tag_a, t2.tag_name AS tag_b, COUNT(*) AS pair_count FROM post_tags pt1 JOIN post_tags pt2 ON pt1.post_id = pt2.post_id AND pt1.tag_id < pt2.tag_id JOIN tags t1 ON t1.tag_id = pt1.tag_id JOIN tags t2 ON t2.tag_id = pt2.tag_id GROUP BY t1.tag_id, t2.tag_id ORDER BY pair_count DESC LIMIT 20;

CONSTRAINTS:
- Only SELECT (no writes)
- Filter to creation_date >= '2020-01-01' where a date filter is relevant (data ends 2022-09-25)
- Avoid queries that would be slow (always include a reasonable LIMIT unless the user asks for an aggregate/single row)
- Return ONLY the SQL query, nothing else
"""

_client = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError("Set the ANTHROPIC_API_KEY environment variable first")
        _client = Anthropic()
    return _client


def generate_sql(user_question: str) -> str:
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_question}],
    )
    sql = "".join(b.text for b in response.content if b.type == "text").strip()
    # strip accidental markdown fences
    if sql.startswith("```"):
        sql = sql.strip("`")
        if sql.lower().startswith("sql"):
            sql = sql[3:]
        sql = sql.strip()
    return sql


BAD_WORDS = ("DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "ATTACH", "PRAGMA", "REPLACE")


def validate_and_execute(sql_query: str, conn: sqlite3.Connection):
    stripped = sql_query.strip().rstrip(";")
    if not stripped.upper().startswith("SELECT") and not stripped.upper().startswith("WITH"):
        return None, "Error: only SELECT queries are allowed"

    upper = stripped.upper()
    if any(word in upper for word in BAD_WORDS):
        return None, "Error: write/schema operations are not permitted"

    try:
        result = pd.read_sql(stripped, conn)
        return result, None
    except Exception as e:
        return None, f"Query failed: {str(e)[:200]}"


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found. Run src/build_db.py first.")
    conn = sqlite3.connect(DB_PATH)
    question = "Top 20 tags by question volume"
    sql = generate_sql(question)
    print(f"Q: {question}\nSQL: {sql}\n")
    result, error = validate_and_execute(sql, conn)
    if error:
        print(error)
    else:
        print(result)
    conn.close()


if __name__ == "__main__":
    main()
