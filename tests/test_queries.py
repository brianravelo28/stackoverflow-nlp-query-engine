"""Tests for the query suite in src/queries.py on a tiny in-memory database."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import queries  # noqa: E402


def _db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE tags (tag_id INTEGER, tag_name TEXT);
        CREATE TABLE post_tags (post_id INTEGER, tag_id INTEGER);
        CREATE TABLE posts_questions (post_id INTEGER, answer_count INTEGER);
    """)
    conn.executemany("INSERT INTO tags VALUES (?, ?)", [(1, "common"), (2, "rare")])
    # 'common': 50 questions with 2 answers each; 'rare': 1 question with 30 answers
    conn.executemany("INSERT INTO posts_questions VALUES (?, ?)", [(i, 2) for i in range(1, 51)] + [(100, 30)])
    conn.executemany("INSERT INTO post_tags VALUES (?, 1)", [(i,) for i in range(1, 51)])
    conn.execute("INSERT INTO post_tags VALUES (100, 2)")
    return conn


def test_q4_ignores_tags_with_fewer_than_50_questions():
    rows = _db().execute(queries.QUERIES["q4_avg_answers_per_tag"]).fetchall()
    assert rows == [("common", 2.0)]
