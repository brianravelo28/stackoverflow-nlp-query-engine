"""Tests for the read-only SQL gate in src/nlp_layer.py. No API key or database needed."""
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nlp_layer import SYSTEM_PROMPT, check_sql, validate_and_execute  # noqa: E402

ALLOWED = [
    "SELECT 1",
    "select 1;",
    "  WITH c AS (SELECT 1 AS n) SELECT n FROM c;  ",
    "-- count them\nSELECT COUNT(*) FROM posts_questions",
    "/* note */ SELECT 1",
    "SELECT 1 /* DROP TABLE x",  # unterminated comment runs to the end
    # words inside string literals, quoted identifiers and longer names
    "SELECT * FROM posts_questions WHERE title LIKE '%update%'",
    "SELECT * FROM posts_questions WHERE title LIKE '%how to drop a column%'",
    "SELECT 'it''s a DELETE' AS s",
    'SELECT 1 AS "update"',
    "SELECT 1 AS [insert]",
    "SELECT updated_at, created, dropped_n, replaced FROM t",
    "SELECT creation_date FROM posts_questions",
    # replace() is a string function
    "SELECT REPLACE(title, 'a', 'b') FROM posts_questions",
    "SELECT replace (title, 'a', 'b') FROM posts_questions",
]

REJECTED = [
    ("DROP TABLE users", "only SELECT"),
    ("DELETE FROM users", "only SELECT"),
    ("", "only SELECT"),
    ("-- just a comment", "only SELECT"),
    ("PRAGMA table_info(users)", "only SELECT"),
    ("REPLACE INTO tags VALUES (1, 'x')", "only SELECT"),
    ("(SELECT 1)", "only SELECT"),
    ("SELECT 1; DROP TABLE users", "one statement"),
    ("SELECT 1; SELECT 2", "one statement"),
    ("WITH c AS (SELECT 1) DELETE FROM users", "write/schema"),
    ("WITH c AS (SELECT 1) INSERT INTO tags SELECT * FROM c", "write/schema"),
    ("WITH c AS (SELECT 1) UPDATE users SET reputation = 0", "write/schema"),
    ("WITH c AS (SELECT 1) REPLACE INTO tags SELECT * FROM c", "write/schema"),
    ("SELECT 1 /* hide */ ; /* hide */ ATTACH DATABASE 'x' AS y", "one statement"),
    ("SELECT 1 UNION SELECT 2 -- c\n; CREATE TABLE t (a)", "one statement"),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed(sql):
    assert check_sql(sql) is None


@pytest.mark.parametrize("sql, expected", REJECTED)
def test_rejected(sql, expected):
    error = check_sql(sql)
    assert error is not None and expected in error


def test_prompt_examples_pass():
    examples = re.findall(r"^A: (.+)$", SYSTEM_PROMPT, re.M)
    assert len(examples) == 4
    for sql in examples:
        assert check_sql(sql) is None


def test_eval_reference_queries_pass():
    questions = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    checked = 0
    for q in questions:
        for sql in [q["reference_sql"], *(q["alt_sqls"] or [])]:
            if sql:
                assert check_sql(sql) is None, q["id"]
                checked += 1
    assert checked >= 56


def test_validate_and_execute_runs_query_with_blocked_looking_text():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE posts_questions (title TEXT)")
    conn.executemany("INSERT INTO posts_questions VALUES (?)",
                     [("How to update a row",), ("Delete files in bash",), ("Plain",)])
    result, error = validate_and_execute(
        "SELECT COUNT(*) AS n FROM posts_questions WHERE title LIKE '%update%' OR title LIKE '%delete%';", conn)
    assert error is None and result.n.iloc[0] == 2
    result, error = validate_and_execute("SELECT REPLACE(title, 'Plain', 'Done') AS t FROM posts_questions", conn)
    assert error is None and "Done" in set(result.t)


def test_validate_and_execute_blocks_writes_without_touching_data():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (a)")
    conn.execute("INSERT INTO t VALUES (1)")
    for sql in ["DELETE FROM t", "SELECT 1; DELETE FROM t", "WITH c AS (SELECT 1) DELETE FROM t"]:
        result, error = validate_and_execute(sql, conn)
        assert result is None and error.startswith("Error:")
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1


def _numbers_db(n):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    conn.executemany("INSERT INTO t VALUES (?, ?)", [(i, f"x{i}") for i in range(n)])
    return conn


def test_row_cap_truncates_and_flags():
    conn = _numbers_db(25)
    result, error = validate_and_execute("SELECT a, b FROM t ORDER BY a", conn, max_rows=10)
    assert error is None
    assert list(result.a) == list(range(10)) and result.attrs["truncated"] is True


def test_row_cap_not_flagged_at_or_under_limit():
    conn = _numbers_db(10)
    result, error = validate_and_execute("SELECT a FROM t", conn, max_rows=10)
    assert error is None and len(result) == 10 and result.attrs["truncated"] is False


def test_empty_result_keeps_columns():
    conn = _numbers_db(3)
    result, error = validate_and_execute("SELECT a, b FROM t WHERE a > 100", conn)
    assert error is None and list(result.columns) == ["a", "b"] and result.empty


def test_timeout_interrupts_runaway_query_and_connection_still_works():
    conn = _numbers_db(3)
    runaway = "WITH RECURSIVE c(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM c) SELECT COUNT(*) FROM c"
    start = time.monotonic()
    result, error = validate_and_execute(runaway, conn, timeout=0.5)
    assert result is None and "timed out" in error
    assert time.monotonic() - start < 5
    result, error = validate_and_execute("SELECT COUNT(*) AS n FROM t", conn)
    assert error is None and result.n.iloc[0] == 3


def test_sql_errors_still_reported():
    result, error = validate_and_execute("SELECT * FROM no_such_table", _numbers_db(1))
    assert result is None and error.startswith("Query failed:")
