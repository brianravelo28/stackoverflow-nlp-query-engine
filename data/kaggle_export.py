"""Export a sampled StackOverflow slice from BigQuery to CSVs.

Run in a Kaggle Notebook (free BigQuery access, no local GCP setup):
  1. kaggle.com -> New Notebook -> Add Input -> attach the "Stack Overflow"
     BigQuery dataset (stackoverflow/stackoverflow)
  2. Paste this file into a cell and run it
  3. Download the 6 CSVs from the notebook's Output pane into this folder (data/)

Scope: questions created 2020-01-01..2025-12-31 (the public mirror actually
ends 2022-09-25) with at least one of the curated tags below, owner present,
sampled 1-in-16 by id (MOD(id, 16) = 0). Without the sample the tag filter
alone matches ~2.8M questions. Answers, comments, votes and users follow the
sampled question set. Post bodies are truncated to 500 characters.

Row counts from the run that produced the published database:
  tags 63,653 | posts_questions 174,131 | posts_answers 186,018
  comments 572,119 | votes 487,387 | users 227,026
"""
from google.cloud import bigquery

client = bigquery.Client()

SAMPLE_MOD = 16  # raise to shrink the export, lower to grow it
TAG_REGEX = r"(^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)"

P = "bigquery-public-data.stackoverflow"
QF = (
    "creation_date BETWEEN '2020-01-01' AND '2025-12-31' AND owner_user_id IS NOT NULL "
    f"AND MOD(id, {SAMPLE_MOD}) = 0 AND REGEXP_CONTAINS(tags, r'{TAG_REGEX}')"
)

Q_IDS = f"SELECT id FROM `{P}.posts_questions` WHERE {QF}"
A_IDS = (
    f"SELECT a.id FROM `{P}.posts_answers` a JOIN ({Q_IDS}) q ON a.parent_id = q.id "
    "WHERE a.owner_user_id IS NOT NULL"
)
POST_IDS = f"{Q_IDS} UNION DISTINCT {A_IDS}"

queries = {
    "tags": f"SELECT id AS tag_id, tag_name FROM `{P}.tags`",

    # keep the raw pipe-delimited `tags` column; src/build_db.py derives post_tags from it
    "posts_questions": f"""SELECT id AS post_id, owner_user_id AS user_id, title, SUBSTR(body,1,500) AS body,
        creation_date, view_count, answer_count, score, accepted_answer_id, tags
        FROM `{P}.posts_questions` WHERE {QF}""",

    "posts_answers": f"""SELECT a.id AS post_id, a.owner_user_id AS user_id, a.parent_id, SUBSTR(a.body,1,500) AS body,
        a.creation_date, a.score, CASE WHEN a.id = q.accepted_answer_id THEN 1 ELSE 0 END AS is_accepted
        FROM `{P}.posts_answers` a
        JOIN (SELECT id, accepted_answer_id FROM `{P}.posts_questions` WHERE {QF}) q ON a.parent_id = q.id
        WHERE a.owner_user_id IS NOT NULL""",

    "comments": f"""SELECT id AS comment_id, post_id, user_id, text AS body, creation_date, score
        FROM `{P}.comments` WHERE user_id IS NOT NULL AND post_id IN ({POST_IDS})""",

    # the public votes table has no voter id (anonymized); only the first 9 type codes are
    # decoded here, the rest load as numeric strings (10, 11, 15, 16, ...)
    "votes": f"""SELECT id AS vote_id, post_id,
        CASE vote_type_id WHEN 1 THEN 'AcceptedByOriginator' WHEN 2 THEN 'UpMod' WHEN 3 THEN 'DownMod'
            WHEN 5 THEN 'Favorite' WHEN 6 THEN 'Close' WHEN 7 THEN 'Reopen' WHEN 8 THEN 'BountyStart'
            WHEN 9 THEN 'BountyClose' ELSE CAST(vote_type_id AS STRING) END AS vote_type, creation_date
        FROM `{P}.votes` WHERE post_id IN ({POST_IDS})""",

    # authors of sampled questions, answers AND comments, so every user_id FK resolves
    "users": f"""SELECT u.id AS user_id, u.display_name, u.reputation, COALESCE(b.n,0) AS badge_count, u.creation_date
        FROM `{P}.users` u
        LEFT JOIN (SELECT user_id, COUNT(*) AS n FROM `{P}.badges` GROUP BY user_id) b ON u.id = b.user_id
        WHERE u.id IN (
            SELECT owner_user_id FROM `{P}.posts_questions` WHERE {QF}
            UNION DISTINCT
            SELECT a.owner_user_id FROM `{P}.posts_answers` a JOIN ({Q_IDS}) q ON a.parent_id = q.id
                WHERE a.owner_user_id IS NOT NULL
            UNION DISTINCT
            SELECT user_id FROM `{P}.comments` WHERE user_id IS NOT NULL AND post_id IN ({POST_IDS})
        )""",
}

for name, sql in queries.items():
    df = client.query(sql).to_dataframe()
    df.to_csv(f"{name}.csv", index=False)
    print(f"{name}: {len(df):,} rows")
