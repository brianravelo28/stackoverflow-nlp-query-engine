"""15 analytical queries against stackoverflow.db, run + sanity-checked here.

These are the hand-validated query suite (Day 2 of the roadmap) -- distinct
from the NLP layer's freely-generated SQL, which is tested separately against
20 natural-language questions in src/nlp_layer.py.
"""
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "stackoverflow.db"

QUERIES = {
    "q1_top_tags_by_question_volume": """
        SELECT t.tag_name, COUNT(pt.post_id) AS question_count
        FROM tags t
        LEFT JOIN post_tags pt ON t.tag_id = pt.tag_id
        GROUP BY t.tag_id, t.tag_name
        ORDER BY question_count DESC
        LIMIT 20
    """,

    "q2_users_over_1000_reputation": """
        SELECT user_id, display_name, reputation
        FROM users
        WHERE reputation > 1000
        ORDER BY reputation DESC
    """,

    "q3_questions_without_accepted_answer": """
        SELECT post_id, title, creation_date, answer_count
        FROM posts_questions
        WHERE accepted_answer_id IS NULL
        ORDER BY creation_date DESC
        LIMIT 50
    """,

    "q4_avg_answers_per_tag": """
        SELECT t.tag_name, AVG(q.answer_count) AS avg_answers
        FROM tags t
        JOIN post_tags pt ON t.tag_id = pt.tag_id
        JOIN posts_questions q ON pt.post_id = q.post_id
        GROUP BY t.tag_id, t.tag_name
        ORDER BY avg_answers DESC
        LIMIT 20
    """,

    "q5_top_answerers_overall": """
        SELECT u.user_id, u.display_name, COUNT(*) AS answer_count
        FROM posts_answers a
        JOIN users u ON a.user_id = u.user_id
        GROUP BY u.user_id, u.display_name
        ORDER BY answer_count DESC
        LIMIT 20
    """,

    # median computed in pandas (see compute_median_time_to_first_answer) --
    # this just extracts the raw per-question deltas in hours
    "q6_time_to_first_answer_hours_raw": """
        SELECT (julianday(MIN(a.creation_date)) - julianday(q.creation_date)) * 24 AS hours
        FROM posts_questions q
        JOIN posts_answers a ON a.parent_id = q.post_id
        GROUP BY q.post_id
    """,

    "q7_users_with_most_accepted_answers": """
        SELECT u.user_id, u.display_name, COUNT(*) AS accepted_count
        FROM posts_answers a
        JOIN users u ON a.user_id = u.user_id
        WHERE a.is_accepted = 1
        GROUP BY u.user_id, u.display_name
        ORDER BY accepted_count DESC
        LIMIT 20
    """,

    # complete years only (data ends 2022-09) and >=50 prior-year questions
    "q8_fastest_growing_tags_yoy": """
        WITH yearly AS (
            SELECT pt.tag_id, strftime('%Y', q.creation_date) AS yr, COUNT(*) AS cnt
            FROM post_tags pt
            JOIN posts_questions q ON pt.post_id = q.post_id
            WHERE q.creation_date < '2022-01-01'
            GROUP BY pt.tag_id, yr
        ),
        latest AS (SELECT MAX(yr) AS yr FROM yearly),
        prior AS (SELECT MAX(yr) AS yr FROM yearly WHERE yr < (SELECT yr FROM latest))
        SELECT
            t.tag_name,
            MAX(CASE WHEN y.yr = (SELECT yr FROM latest) THEN y.cnt END) AS latest_year_count,
            MAX(CASE WHEN y.yr = (SELECT yr FROM prior) THEN y.cnt END) AS prior_year_count
        FROM yearly y
        JOIN tags t ON t.tag_id = y.tag_id
        GROUP BY t.tag_id, t.tag_name
        HAVING prior_year_count >= 50 AND latest_year_count IS NOT NULL
        ORDER BY (1.0 * latest_year_count / prior_year_count) DESC
        LIMIT 20
    """,

    "q9_users_highest_acceptance_rate": """
        SELECT
            u.user_id, u.display_name,
            COUNT(*) AS total_answers,
            SUM(a.is_accepted) AS accepted_answers,
            ROUND(1.0 * SUM(a.is_accepted) / COUNT(*), 3) AS acceptance_rate
        FROM posts_answers a
        JOIN users u ON a.user_id = u.user_id
        GROUP BY u.user_id, u.display_name
        HAVING COUNT(*) >= 5
        ORDER BY acceptance_rate DESC
        LIMIT 20
    """,

    "q10_most_commented_questions": """
        SELECT q.post_id, q.title, COUNT(c.comment_id) AS comment_count
        FROM posts_questions q
        JOIN comments c ON c.post_id = q.post_id
        GROUP BY q.post_id, q.title
        ORDER BY comment_count DESC
        LIMIT 20
    """,

    "q11_overall_answer_acceptance_fraction": """
        SELECT
            ROUND(1.0 * SUM(is_accepted) / COUNT(*), 4) AS fraction_accepted,
            COUNT(*) AS total_answers
        FROM posts_answers
    """,

    "q12_top_users_by_reputation_in_tag": """
        SELECT DISTINCT u.user_id, u.display_name, u.reputation
        FROM users u
        JOIN posts_answers a ON a.user_id = u.user_id
        JOIN posts_questions q ON a.parent_id = q.post_id
        JOIN post_tags pt ON pt.post_id = q.post_id
        JOIN tags t ON t.tag_id = pt.tag_id
        WHERE t.tag_name = 'python'
        ORDER BY u.reputation DESC
        LIMIT 20
    """,

    "q13_questions_10plus_answers_no_accepted": """
        SELECT post_id, title, answer_count, creation_date
        FROM posts_questions
        WHERE answer_count >= 10 AND accepted_answer_id IS NULL
        ORDER BY answer_count DESC
        LIMIT 20
    """,

    "q14_most_common_tag_pairs": """
        SELECT t1.tag_name AS tag_a, t2.tag_name AS tag_b, COUNT(*) AS pair_count
        FROM post_tags pt1
        JOIN post_tags pt2 ON pt1.post_id = pt2.post_id AND pt1.tag_id < pt2.tag_id
        JOIN tags t1 ON t1.tag_id = pt1.tag_id
        JOIN tags t2 ON t2.tag_id = pt2.tag_id
        GROUP BY t1.tag_id, t2.tag_id
        ORDER BY pair_count DESC
        LIMIT 20
    """,

    "q15_avg_answer_score_by_tag": """
        SELECT t.tag_name, AVG(a.score) AS avg_answer_score, COUNT(*) AS n_answers
        FROM tags t
        JOIN post_tags pt ON pt.tag_id = t.tag_id
        JOIN posts_answers a ON a.parent_id = pt.post_id
        GROUP BY t.tag_id, t.tag_name
        HAVING COUNT(*) >= 5
        ORDER BY avg_answer_score DESC
        LIMIT 20
    """,
}


def compute_median_time_to_first_answer(conn) -> float:
    raw = pd.read_sql(QUERIES["q6_time_to_first_answer_hours_raw"], conn)
    return float(raw["hours"].median())


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found. Run src/build_db.py first.")
    conn = sqlite3.connect(DB_PATH)

    passed = 0
    for name, sql in QUERIES.items():
        try:
            result = pd.read_sql(sql, conn)
            print(f"OK  {name}: {len(result)} rows")
            passed += 1
        except Exception as e:
            print(f"FAIL {name}: {e}")

    median_hours = compute_median_time_to_first_answer(conn)
    print(f"\nMedian time to first answer: {median_hours:.2f} hours")

    print(f"\n{passed}/{len(QUERIES)} queries passed")
    conn.close()


if __name__ == "__main__":
    main()
