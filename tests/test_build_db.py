"""Tests for the loader's integrity check in src/build_db.py (in-memory, no data files)."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import build_db  # noqa: E402


def _schema_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(build_db.SCHEMA)
    return conn


def test_clean_schema_has_no_violations():
    conn = _schema_db()
    conn.execute("INSERT INTO users (user_id, display_name, reputation, badge_count, creation_date) VALUES (1, 'a', 1, 0, '2020-01-01')")
    conn.execute("INSERT INTO posts_questions (post_id, user_id, title, body, creation_date, view_count, answer_count, score) "
                 "VALUES (10, 1, 't', 'b', '2020-01-02', 1, 0, 0)")
    assert build_db.foreign_key_violations(conn) == []


def test_orphan_row_is_reported():
    conn = _schema_db()
    conn.execute("INSERT INTO posts_questions (post_id, user_id, title, body, creation_date, view_count, answer_count, score) "
                 "VALUES (10, 999, 't', 'b', '2020-01-02', 1, 0, 0)")  # user 999 does not exist
    violations = build_db.foreign_key_violations(conn)
    assert len(violations) == 1 and violations[0][0] == "posts_questions" and violations[0][2] == "users"
