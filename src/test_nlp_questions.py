"""Run the 20 natural-language test questions from the project spec against
the NLP layer and report pass/fail + accuracy. Requires ANTHROPIC_API_KEY
and a populated stackoverflow.db.
"""
import sqlite3
from pathlib import Path

from nlp_layer import generate_sql, validate_and_execute

DB_PATH = Path(__file__).resolve().parent.parent / "stackoverflow.db"

TEST_QUESTIONS = [
    "Top 20 tags by question volume",
    "Show me users with over 1000 reputation points",
    "Which questions have no accepted answer?",
    "How many answers does each tag receive on average?",
    "Show me the top answerers in Python",
    "What's the median time to first answer?",
    "Which users have answered the most questions?",
    "Tags that are growing fastest year-over-year",
    "Users with the highest answer acceptance rate",
    "Show me the most commented questions",
    "What fraction of answers get accepted?",
    "Rank users by reputation in the Java tag",
    "Questions with 10+ answers but no accepted answer",
    "Most common tag combinations",
    "Users who answered multiple questions on the same day",
    "Average score of answers by tag",
    "Show questions posted in the last month",
    "Which users have never had an answer accepted?",
    "Questions that got their first answer in under 1 hour",
    "Trending tags in the last 6 months",
]


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found. Run src/build_db.py first.")
    conn = sqlite3.connect(DB_PATH)

    passed = 0
    for i, question in enumerate(TEST_QUESTIONS, 1):
        try:
            sql = generate_sql(question)
        except Exception as e:
            print(f"FAIL Q{i}: generation error: {e}")
            continue

        result, error = validate_and_execute(sql, conn)
        if error:
            print(f"FAIL Q{i} [{question}]\n     SQL: {sql}\n     {error}")
        else:
            print(f"OK   Q{i} [{question}]: {len(result)} rows")
            passed += 1

    conn.close()
    total = len(TEST_QUESTIONS)
    print(f"\nAccuracy: {passed}/{total} ({100 * passed // total}%)")


if __name__ == "__main__":
    main()
