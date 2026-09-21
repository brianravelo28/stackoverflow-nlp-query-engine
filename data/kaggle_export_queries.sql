-- ============================================================================
-- StackOverflow data export queries for bigquery-public-data.stackoverflow
-- Run these in a Kaggle Notebook (free, no local GCP setup needed):
--
--   1. kaggle.com -> New Notebook -> "Add Input" -> search "Stack Overflow"
--      -> add the "stackoverflow/stackoverflow" BigQuery dataset
--   2. In a code cell, run each query below with the BigQuery client that
--      Kaggle wires up automatically:
--
--        from google.cloud import bigquery
--        client = bigquery.Client()
--        df = client.query(QUERY_STRING).to_dataframe()
--        df.to_csv("posts_questions.csv", index=False)
--
--   3. Download each CSV from the notebook's Output pane and drop it in
--      this project's data/ folder.
--
-- Scoped to 2020-2025 (the mirror actually ends 2022-09) and a curated set of ~35 popular tags. That set alone
-- is ~2.8M questions (too big for local SQLite), so every question filter
-- also applies a deterministic 1-in-16 sample: MOD(id, 16) = 0 (~177K
-- questions). Change 16 in every query (identically!) to resize; answers,
-- comments, votes and users follow the sampled question set.
-- Adjust TAG_REGEX below to change which tags are included.
-- ============================================================================

-- TAG_REGEX (reused in every query below):
-- (^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)

-- ---------------------------------------------------------------------------
-- 0. Sanity check row count BEFORE exporting (run this first)
-- ---------------------------------------------------------------------------
SELECT COUNT(*) AS n
FROM `bigquery-public-data.stackoverflow.posts_questions`
WHERE creation_date BETWEEN '2020-01-01' AND '2025-12-31'
  AND MOD(id, 16) = 0 AND REGEXP_CONTAINS(tags, r'(^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)');

-- ---------------------------------------------------------------------------
-- 1. tags.csv  (small, ~64K rows, pull the whole table)
-- ---------------------------------------------------------------------------
SELECT id AS tag_id, tag_name
FROM `bigquery-public-data.stackoverflow.tags`;

-- ---------------------------------------------------------------------------
-- 2. posts_questions.csv
--    NOTE: keep the raw `tags` column -- our local loader splits it into
--    post_tags rows using tags.csv, so no separate BigQuery join is needed.
-- ---------------------------------------------------------------------------
SELECT
  id AS post_id,
  owner_user_id AS user_id,
  title,
  body,
  creation_date,
  view_count,
  answer_count,
  score,
  accepted_answer_id,
  tags
FROM `bigquery-public-data.stackoverflow.posts_questions`
WHERE creation_date BETWEEN '2020-01-01' AND '2025-12-31'
  AND owner_user_id IS NOT NULL
  AND MOD(id, 16) = 0 AND REGEXP_CONTAINS(tags, r'(^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)');

-- ---------------------------------------------------------------------------
-- 3. posts_answers.csv (answers to the question set from query 2)
-- ---------------------------------------------------------------------------
SELECT
  a.id AS post_id,
  a.owner_user_id AS user_id,
  a.parent_id,
  a.body,
  a.creation_date,
  a.score,
  CASE WHEN a.id = q.accepted_answer_id THEN 1 ELSE 0 END AS is_accepted
FROM `bigquery-public-data.stackoverflow.posts_answers` a
JOIN (
  SELECT id, accepted_answer_id
  FROM `bigquery-public-data.stackoverflow.posts_questions`
  WHERE creation_date BETWEEN '2020-01-01' AND '2025-12-31'
    AND MOD(id, 16) = 0 AND REGEXP_CONTAINS(tags, r'(^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)')
) q ON a.parent_id = q.id
WHERE a.owner_user_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 4. users.csv (only users who own one of the selected questions/answers;
--    badge_count comes from a real COUNT over the badges table)
-- ---------------------------------------------------------------------------
SELECT
  u.id AS user_id,
  u.display_name,
  u.reputation,
  COALESCE(b.badge_count, 0) AS badge_count,
  u.creation_date
FROM `bigquery-public-data.stackoverflow.users` u
LEFT JOIN (
  SELECT user_id, COUNT(*) AS badge_count
  FROM `bigquery-public-data.stackoverflow.badges`
  GROUP BY user_id
) b ON u.id = b.user_id
WHERE u.id IN (
  SELECT owner_user_id
  FROM `bigquery-public-data.stackoverflow.posts_questions`
  WHERE creation_date BETWEEN '2020-01-01' AND '2025-12-31'
    AND owner_user_id IS NOT NULL
    AND MOD(id, 16) = 0 AND REGEXP_CONTAINS(tags, r'(^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)')
  UNION DISTINCT
  SELECT a.owner_user_id
  FROM `bigquery-public-data.stackoverflow.posts_answers` a
  JOIN `bigquery-public-data.stackoverflow.posts_questions` q ON a.parent_id = q.id
  WHERE q.creation_date BETWEEN '2020-01-01' AND '2025-12-31'
    AND a.owner_user_id IS NOT NULL
    AND MOD(q.id, 16) = 0 AND REGEXP_CONTAINS(q.tags, r'(^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)')
);

-- ---------------------------------------------------------------------------
-- 5. comments.csv (comments on the selected questions + answers)
-- ---------------------------------------------------------------------------
SELECT
  c.id AS comment_id,
  c.post_id,
  c.user_id,
  c.text AS body,
  c.creation_date,
  c.score
FROM `bigquery-public-data.stackoverflow.comments` c
WHERE c.user_id IS NOT NULL
  AND c.post_id IN (
    SELECT id
    FROM `bigquery-public-data.stackoverflow.posts_questions`
    WHERE creation_date BETWEEN '2020-01-01' AND '2025-12-31'
      AND MOD(id, 16) = 0 AND REGEXP_CONTAINS(tags, r'(^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)')
    UNION DISTINCT
    SELECT a.id
    FROM `bigquery-public-data.stackoverflow.posts_answers` a
    JOIN `bigquery-public-data.stackoverflow.posts_questions` q ON a.parent_id = q.id
    WHERE q.creation_date BETWEEN '2020-01-01' AND '2025-12-31'
      AND MOD(q.id, 16) = 0 AND REGEXP_CONTAINS(q.tags, r'(^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)')
  );

-- ---------------------------------------------------------------------------
-- 6. votes.csv
--    NOTE: the official SO data dump anonymizes voters -- there is NO
--    user_id column on the real votes table. vote_type_id is decoded to a
--    label here; our local schema's votes.user_id will just be NULL.
-- ---------------------------------------------------------------------------
SELECT
  v.id AS vote_id,
  v.post_id,
  CASE v.vote_type_id
    WHEN 1 THEN 'AcceptedByOriginator'
    WHEN 2 THEN 'UpMod'
    WHEN 3 THEN 'DownMod'
    WHEN 5 THEN 'Favorite'
    WHEN 6 THEN 'Close'
    WHEN 7 THEN 'Reopen'
    WHEN 8 THEN 'BountyStart'
    WHEN 9 THEN 'BountyClose'
    ELSE CAST(v.vote_type_id AS STRING)
  END AS vote_type,
  v.creation_date
FROM `bigquery-public-data.stackoverflow.votes` v
WHERE v.post_id IN (
  SELECT id
  FROM `bigquery-public-data.stackoverflow.posts_questions`
  WHERE creation_date BETWEEN '2020-01-01' AND '2025-12-31'
    AND MOD(id, 16) = 0 AND REGEXP_CONTAINS(tags, r'(^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)')
  UNION DISTINCT
  SELECT a.id
  FROM `bigquery-public-data.stackoverflow.posts_answers` a
  JOIN `bigquery-public-data.stackoverflow.posts_questions` q ON a.parent_id = q.id
  WHERE q.creation_date BETWEEN '2020-01-01' AND '2025-12-31'
    AND MOD(q.id, 16) = 0 AND REGEXP_CONTAINS(q.tags, r'(^|\|)(python|javascript|java|sql|reactjs|typescript|docker|kubernetes|amazon-web-services|pandas|numpy|django|flask|node\.js|c\+\+|c#|go|rust|sqlite|postgresql|mysql|git|html|css|linux|bash|regex|api|rest|graphql|machine-learning|tensorflow|pytorch|scikit-learn|nlp|streamlit|pytest|algorithm)(\||$)')
);

-- ---------------------------------------------------------------------------
-- post_tags.csv is NOT queried separately -- it's derived locally by
-- src/build_db.py from the `tags` column already included in
-- posts_questions.csv (pipe-delimited tag names -> tag_id lookups via
-- tags.csv). No BigQuery query needed for it.
-- ---------------------------------------------------------------------------
