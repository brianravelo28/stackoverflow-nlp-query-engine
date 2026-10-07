# Data Quirks

Problems found while getting the StackOverflow export into a working database,
and what was done about each. Row counts are from the loaded database.

| # | Quirk | Impact | Handling |
|---|---|---|---|
| 1 | The public BigQuery mirror ends on **2022-09-25**, though the export asks for 2020–2025 | The project spec's "2020–2025" was wrong; only ~2.7 years of data exist (68,340 questions in 2020, 59,701 in 2021, 46,090 in 2022) | Docs, app caption and prompt say Jan 2020 – Sep 2022. The prompt anchors "recent" to 2022-09-25 |
| 2 | The 38-tag filter alone matches ~2.8M questions (2,835,369 before sampling) | Far too big for a local SQLite file | Deterministic 1-in-16 sample by id (`MOD(id, 16) = 0`) → 177,424 questions |
| 3 | 3,293 sampled questions have no owner (deleted users) | The first count (177,424) did not match the loaded table (174,131) | Export excludes `owner_user_id IS NULL`, since `user_id` is `NOT NULL` with a foreign key |
| 4 | The public `votes` table has **no voter column** | The spec's `votes.user_id NOT NULL` foreign key could not be loaded | Column is nullable and always NULL; votes are analyzed by post and type only |
| 5 | `votes.vote_type_id` has codes beyond the ones decoded | `16` (14,504 rows), `11` (3,468), `15` (1,088) and `10` (1,088) load as numeric strings | Left as-is and documented; decoding them would need a code table |
| 6 | Two real tags are named `null` and `nan` | pandas treats those strings as missing, so loading failed with `NOT NULL constraint failed: tags.tag_name` | CSVs are read with `keep_default_na=False, na_values=[""]` so only empty cells are null |
| 7 | `DataFrame.to_sql(if_exists="replace")` rebuilt each table without its primary and foreign keys | The first load "succeeded" with 0 constraints; the schema in the docs was not what was in the database | The loader creates the schema first, then appends (`if_exists="append"`), and the database is deleted before each rebuild |
| 8 | Comments and votes can point at **answers** as well as questions (206,120 of 572,119 comments; 283,979 of 487,387 votes) | A foreign key from `post_id` to `posts_questions` is wrong and would fail | No foreign key on `comments.post_id` / `votes.post_id` |
| 9 | One comment has an empty body | `comments.body` is `NOT NULL`; the empty value was read as missing | Loaded as an empty string |
| 10 | A naive year-over-year tag-growth ranking is dominated by tiny tags | The first version ranked `pycord` (1 → 14 questions) and similar at the top, and compared against a partial 2022 | `q8` uses complete years (2020 vs 2021) and requires ≥50 questions in the prior year |
| 11 | The 1-in-16 sample thins out per-user counts | The example question "users who both asked and answered more than 20 questions" returned no rows | Threshold lowered to 3 in the app's example question |
