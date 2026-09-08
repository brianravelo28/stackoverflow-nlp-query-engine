"""Add indexes to stackoverflow.db to speed up the 15 analytical queries."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "stackoverflow.db"

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_posts_q_creation ON posts_questions(creation_date)",
    "CREATE INDEX IF NOT EXISTS idx_posts_q_user ON posts_questions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_posts_a_parent ON posts_answers(parent_id)",
    "CREATE INDEX IF NOT EXISTS idx_posts_a_user ON posts_answers(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_posts_a_creation ON posts_answers(creation_date)",
    "CREATE INDEX IF NOT EXISTS idx_post_tags_tag ON post_tags(tag_id)",
    "CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id)",
    "CREATE INDEX IF NOT EXISTS idx_comments_user ON comments(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_votes_post ON votes(post_id)",
    "CREATE INDEX IF NOT EXISTS idx_users_rep ON users(reputation)",
]


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found. Run src/build_db.py first.")
    conn = sqlite3.connect(DB_PATH)
    for idx in INDEXES:
        conn.execute(idx)
    conn.commit()
    conn.close()
    print(f"Created {len(INDEXES)} indexes.")


if __name__ == "__main__":
    main()
