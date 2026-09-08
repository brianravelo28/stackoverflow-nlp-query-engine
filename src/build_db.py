"""Create stackoverflow.db and load it from CSVs/parquet in data/.

Expected input files in data/ (from the Kaggle Notebook export, see
data/kaggle_export_queries.sql):
  tags.csv             tag_id, tag_name
  users.csv            user_id, display_name, reputation, badge_count, creation_date
  posts_questions.csv  post_id, user_id, title, body, creation_date, view_count,
                        answer_count, score, accepted_answer_id, tags (pipe-delimited,
                        dropped after post_tags is derived from it)
  posts_answers.csv    post_id, user_id, parent_id, body, creation_date, score, is_accepted
  comments.csv         comment_id, post_id, user_id, body, creation_date, score
  votes.csv            vote_id, post_id, vote_type, creation_date
                        (user_id is optional -- the real dataset anonymizes voters)
  post_tags.csv        post_id, tag_id (optional -- derived from posts_questions.tags
                        if not present)

Accepts .csv or .parquet for any table (parquet takes priority if both exist).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "stackoverflow.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    reputation INTEGER DEFAULT 0,
    badge_count INTEGER DEFAULT 0,
    creation_date TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    tag_id INTEGER PRIMARY KEY,
    tag_name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS posts_questions (
    post_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    creation_date TIMESTAMP NOT NULL,
    view_count INTEGER DEFAULT 0,
    answer_count INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,
    accepted_answer_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS posts_answers (
    post_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    parent_id INTEGER NOT NULL,
    body TEXT,
    creation_date TIMESTAMP NOT NULL,
    score INTEGER DEFAULT 0,
    is_accepted INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (parent_id) REFERENCES posts_questions(post_id)
);

CREATE TABLE IF NOT EXISTS post_tags (
    post_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (post_id, tag_id),
    FOREIGN KEY (post_id) REFERENCES posts_questions(post_id),
    FOREIGN KEY (tag_id) REFERENCES tags(tag_id)
);

CREATE TABLE IF NOT EXISTS comments (
    comment_id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    creation_date TIMESTAMP NOT NULL,
    score INTEGER DEFAULT 0,
    FOREIGN KEY (post_id) REFERENCES posts_questions(post_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- user_id is nullable: the official StackExchange data dump anonymizes
-- voters, so bigquery-public-data.stackoverflow.votes has no user_id.
CREATE TABLE IF NOT EXISTS votes (
    vote_id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,
    user_id INTEGER,
    vote_type TEXT NOT NULL,
    creation_date TIMESTAMP NOT NULL,
    FOREIGN KEY (post_id) REFERENCES posts_questions(post_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
"""


def find_source(table_name: str) -> Path | None:
    parquet_path = DATA_DIR / f"{table_name}.parquet"
    csv_path = DATA_DIR / f"{table_name}.csv"
    if parquet_path.exists():
        return parquet_path
    if csv_path.exists():
        return csv_path
    return None


def read_table(table_name: str) -> pd.DataFrame | None:
    path = find_source(table_name)
    if path is None:
        return None
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def derive_post_tags(questions_raw: pd.DataFrame, tags_df: pd.DataFrame) -> pd.DataFrame:
    name_to_id = dict(zip(tags_df["tag_name"], tags_df["tag_id"]))
    rows = []
    for post_id, tag_str in zip(questions_raw["post_id"], questions_raw["tags"]):
        if not isinstance(tag_str, str) or not tag_str:
            continue
        for name in tag_str.split("|"):
            tag_id = name_to_id.get(name)
            if tag_id is not None:
                rows.append((post_id, tag_id))
    return pd.DataFrame(rows, columns=["post_id", "tag_id"]).drop_duplicates()


def main():
    if not DATA_DIR.exists() or not any(DATA_DIR.glob("*.csv")) and not any(DATA_DIR.glob("*.parquet")):
        raise SystemExit(
            f"No data files found in {DATA_DIR}. Export from Kaggle first "
            f"(see data/kaggle_export_queries.sql) and drop the CSVs there."
        )

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    print("Schema created.")

    tags_df = read_table("tags")
    users_df = read_table("users")
    questions_df = read_table("posts_questions")
    answers_df = read_table("posts_answers")
    comments_df = read_table("comments")
    votes_df = read_table("votes")
    post_tags_df = read_table("post_tags")

    if tags_df is None or users_df is None or questions_df is None:
        raise SystemExit("tags, users, and posts_questions are required at minimum.")

    if post_tags_df is None and "tags" in questions_df.columns:
        print("Deriving post_tags from posts_questions.tags column...")
        post_tags_df = derive_post_tags(questions_df, tags_df)

    # posts_questions table has no `tags` column -- drop it after deriving post_tags
    schema_cols = [
        "post_id", "user_id", "title", "body", "creation_date",
        "view_count", "answer_count", "score", "accepted_answer_id",
    ]
    questions_df = questions_df[[c for c in schema_cols if c in questions_df.columns]]

    loads = {
        "tags": tags_df,
        "users": users_df,
        "posts_questions": questions_df,
        "posts_answers": answers_df,
        "post_tags": post_tags_df,
        "comments": comments_df,
        "votes": votes_df,
    }

    for name, df in loads.items():
        if df is None:
            print(f"  skipped {name}: no source file found")
            continue
        df.to_sql(name, conn, if_exists="replace", index=False)
        print(f"  loaded {name}: {len(df):,} rows")

    conn.commit()

    print("\nVerifying row counts...")
    for table in ["users", "tags", "posts_questions", "posts_answers", "post_tags", "comments", "votes"]:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count:,} rows")
        except sqlite3.OperationalError:
            print(f"  {table}: not loaded")

    conn.close()
    print(f"\nDone. Database at {DB_PATH}")


if __name__ == "__main__":
    main()
