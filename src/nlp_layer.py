"""Natural-language -> SQL layer for the StackOverflow database.

generate_sql() asks Claude for a single SELECT statement grounded in the
schema below; validate_and_execute() enforces read-only safety before
running it against stackoverflow.db.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from pathlib import Path

import pandas as pd
from anthropic import Anthropic, APIError

DB_PATH = Path(__file__).resolve().parent.parent / "stackoverflow.db"
MODEL = os.environ.get("NLP_MODEL", "claude-sonnet-5-5")

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
- SQLite has no MEDIAN(). If asked for a median, compute it exactly in a single query: number the rows with
  ROW_NUMBER() and COUNT(*) OVER (), then average the middle one or two rows.
- SQLite date functions: julianday(), strftime('%Y', creation_date) for year extraction

EXAMPLES:
Q: "Top 20 tags by question volume"
A: SELECT t.tag_name, COUNT(pt.post_id) AS question_count FROM tags t LEFT JOIN post_tags pt ON t.tag_id = pt.tag_id GROUP BY t.tag_id, t.tag_name ORDER BY question_count DESC LIMIT 20;

Q: "Which questions have no accepted answer?"
A: SELECT post_id, title, creation_date, answer_count FROM posts_questions WHERE accepted_answer_id IS NULL ORDER BY creation_date DESC;

Q: "Users with the highest answer acceptance rate"
A: SELECT u.user_id, u.display_name, COUNT(*) AS total_answers, SUM(a.is_accepted) AS accepted_answers, ROUND(1.0 * SUM(a.is_accepted) / COUNT(*), 3) AS acceptance_rate FROM posts_answers a JOIN users u ON a.user_id = u.user_id GROUP BY u.user_id, u.display_name HAVING COUNT(*) >= 5 ORDER BY acceptance_rate DESC LIMIT 20;

Q: "Most common tag combinations"
A: SELECT t1.tag_name AS tag_a, t2.tag_name AS tag_b, COUNT(*) AS pair_count FROM post_tags pt1 JOIN post_tags pt2 ON pt1.post_id = pt2.post_id AND pt1.tag_id < pt2.tag_id JOIN tags t1 ON t1.tag_id = pt1.tag_id JOIN tags t2 ON t2.tag_id = pt2.tag_id GROUP BY t1.tag_id, t2.tag_id ORDER BY pair_count DESC LIMIT 20;

CONSTRAINTS:
- Only SELECT (no writes)
- Do not add date filters the question did not ask for; all data already falls between 2020-01-01 and 2022-09-25
- Add a LIMIT only when the question asks for a top-N ("top 10" -> LIMIT 10; "the most" or "the highest" -> LIMIT 1). Otherwise return every matching row; results are cut off at 1,000 rows automatically
- Keep queries fast: do not join tables you do not need, and aggregate before joining when you can
- If the data to answer the question does not exist in this schema (for example salaries, edit history, or who cast a vote), return exactly: SELECT 'UNANSWERABLE: <short reason>' AS answer;
- Return ONLY the SQL query, nothing else
"""

_client = None


class GenerationError(Exception):
    """The model service failed; the message is safe to show to a visitor."""


def get_client() -> Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError("Set the ANTHROPIC_API_KEY environment variable first")
        _client = Anthropic(timeout=30.0)
    return _client


# Site-wide cap on questions per UTC day. The count lives in memory, so it
# also resets when the service restarts.
DAILY_LIMIT = 100
_daily = {"day": None, "count": 0}
_daily_lock = threading.Lock()


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def daily_limit_reached() -> bool:
    with _daily_lock:
        return _daily["day"] == _today() and _daily["count"] >= DAILY_LIMIT


def count_daily_question() -> None:
    with _daily_lock:
        today = _today()
        if _daily["day"] != today:
            _daily["day"], _daily["count"] = today, 0
        _daily["count"] += 1


def generate_sql(user_question: str) -> str:
    try:
        response = get_client().messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_question}],
        )
    except APIError:
        raise GenerationError("The language model is unavailable right now. Please try again in a minute.") from None
    sql = "".join(b.text for b in response.content if b.type == "text").strip()
    # strip accidental markdown fences
    if sql.startswith("```"):
        sql = sql.strip("`")
        if sql.lower().startswith("sql"):
            sql = sql[3:]
        sql = sql.strip()
    return sql


# Words that may not appear as SQL keywords. SQLite lets a WITH clause lead into
# INSERT/UPDATE/DELETE, so the first-keyword check alone is not enough.
BAD_WORDS = {"DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "ATTACH", "DETACH", "PRAGMA", "CREATE", "VACUUM", "REPLACE"}

# Tokens that carry no keywords: string literals, quoted identifiers, comments.
# An unterminated /* comment runs to the end of the text, as it does in SQLite.
_SKIP = re.compile(r"""'(?:[^']|'')*'|"(?:[^"]|"")*"|`(?:[^`]|``)*`|\[[^\]]*\]|--[^\n]*|/\*.*?(?:\*/|$)|\s+""", re.S)
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*|.", re.S)


def _tokens(sql: str) -> list[str]:
    """Significant tokens of `sql`: words and single punctuation characters."""
    out, pos = [], 0
    while pos < len(sql):
        m = _SKIP.match(sql, pos) or _TOKEN.match(sql, pos)
        if m.re is _TOKEN:
            out.append(m.group())
        pos = m.end()
    return out


def check_sql(sql_query: str) -> str | None:
    """Return an error message if the query is not a single read-only SELECT/WITH, else None."""
    tokens = _tokens(sql_query)
    while tokens and tokens[-1] == ";":
        tokens.pop()
    if not tokens or tokens[0].upper() not in ("SELECT", "WITH"):
        return "Error: only SELECT queries are allowed"
    if ";" in tokens:
        return "Error: only one statement is allowed"
    for i, tok in enumerate(tokens):
        word = tok.upper()
        if word not in BAD_WORDS:
            continue
        # replace(x, a, b) is a string function; REPLACE INTO is a write
        if word == "REPLACE" and tokens[i + 1:i + 2] == ["("]:
            continue
        return "Error: write/schema operations are not permitted"
    return None


MAX_ROWS = 1000
QUERY_TIMEOUT_S = 30

# The app shares one connection across sessions, so the deadline is kept per
# thread and a single progress handler (installed once, never cleared) checks it.
_deadline = threading.local()


def _abort_if_late() -> bool:
    limit = getattr(_deadline, "at", None)
    return limit is not None and time.monotonic() > limit


DECLINE_PREFIX = "UNANSWERABLE:"


def decline_reason(result: pd.DataFrame) -> str | None:
    """The reason when the model declined to answer (one cell starting with DECLINE_PREFIX), else None."""
    if result.shape == (1, 1) and isinstance(result.iat[0, 0], str) and result.iat[0, 0].startswith(DECLINE_PREFIX):
        return result.iat[0, 0][len(DECLINE_PREFIX):].strip()
    return None


def validate_and_execute(sql_query: str, conn: sqlite3.Connection,
                         max_rows: int = MAX_ROWS, timeout: float = QUERY_TIMEOUT_S):
    """Run a validated query. Returns (DataFrame, None) or (None, error message).

    At most `max_rows` rows come back; when there were more, result.attrs["truncated"]
    is True. A query running longer than `timeout` seconds is interrupted.
    """
    stripped = sql_query.strip().rstrip(";")
    error = check_sql(sql_query)
    if error:
        return None, error

    conn.set_progress_handler(_abort_if_late, 100_000)
    _deadline.at = time.monotonic() + timeout
    try:
        cur = conn.execute(stripped)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
        cur.close()
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            return None, f"Query timed out after {timeout:g} seconds. Try a narrower question."
        return None, f"Query failed: {str(e)[:200]}"
    except Exception as e:
        return None, f"Query failed: {str(e)[:200]}"
    finally:
        _deadline.at = None

    truncated = len(rows) > max_rows
    result = pd.DataFrame.from_records(rows[:max_rows], columns=columns, coerce_float=True)
    result.attrs["truncated"] = truncated
    return result, None


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
