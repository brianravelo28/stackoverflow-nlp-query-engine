# StackOverflow NLP Query Engine

Ask plain-English questions about a normalized StackOverflow database (Jan 2020 – Sep 2022)
and get back the generated SQL plus a results table.

**Live demo: https://stackoverflow-nlp-query-engine.onrender.com/**
(free Render tier — the first visit after idle takes about a minute to wake up; each session is capped at 10 questions)

## Problem Statement

Answering "which tags are trending?" or "who has the highest answer
acceptance rate?" against a relational database normally requires knowing
SQL and the schema. This project translates the question itself, grounded in
the real schema, with a validation layer between the LLM and the database.

## Solution Overview

- **Database**: 7-table normalized SQLite schema (users, tags, questions,
  answers, tag join table, comments, votes) loaded from a sampled BigQuery
  export — see [Data](#data) and [`docs/DATA_SCHEMA.md`](docs/DATA_SCHEMA.md)
- **Query suite**: 15 hand-written analytical SQL queries covering the
  join/aggregation patterns the NLP layer needs to reproduce (see
  [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md))
- **NLP layer**: Claude (`claude-sonnet-5`), prompted with the schema, notes on
  non-obvious columns and the data's date range, and 4 few-shot examples drawn
  from the query suite
- **Safety**: generated SQL is rejected unless it's a `SELECT`/`WITH` statement
  with no write/schema keywords; the deployed app also opens the database
  read-only
- **Interface**: Streamlit chat app — type a question or click one of 7 random
  example questions (35 in the pool, Shuffle for more); see the generated SQL
  and the result table

Full request flow and design tradeoffs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Status

Deployed and working. What was verified, and what wasn't:

| Component | Status |
|---|---|
| Data load (`src/build_db.py`) | ✅ 7 tables loaded, 0 foreign-key violations |
| 15 analytical queries (`src/queries.py`) | ✅ All 15 run against the real data |
| 20-question NLP test (`src/test_nlp_questions.py`) | ✅ 20/20 produce SQL that executes. Only 3 answers were checked against the hand-written queries; the other 17 were not checked for correctness, and 4 of the 20 questions appear in the prompt as few-shot examples, so this is **not** a held-out accuracy score (see [methodology](docs/METHODOLOGY.md#-evaluation--limitations)) |
| 35 example questions in the app | ✅ Each returns rows |
| Deployment (Render) | ✅ Live; one real question verified on the deployed site |

Not done: a semantic-correctness evaluation of generated SQL (expected result
sets or execution-match against reference queries).

## Data

Source: `bigquery-public-data.stackoverflow` (a mirror of the Stack Exchange
data dump), exported through a free Kaggle Notebook with
[`data/kaggle_export.py`](data/kaggle_export.py). The slice is:

- questions with at least one of 38 popular tags (python, javascript, java,
  sql, …), with a **1-in-16 sample** by post id — the tag filter alone matches
  ~2.8M questions, too large for a local SQLite file
- **2020-01-01 to 2022-09-25**: the public BigQuery mirror stops there, even
  though the export asks for 2020–2025
- answers, comments, votes and authors for the sampled questions; post bodies
  truncated to 500 characters

Result: 174,131 questions, 186,018 answers, 572,119 comments, 487,387 votes,
227,026 users, 63,653 tags (all tags are loaded, not just the 38). Voters are
anonymized in the source, so votes can be counted by post and type but not by
user. Details and caveats: [`docs/DATA_SCHEMA.md`](docs/DATA_SCHEMA.md),
[`docs/DATA_QUIRKS.md`](docs/DATA_QUIRKS.md).

The raw CSVs and the database are not committed to git. The built database is
published as a gzipped GitHub Release asset
([`data-v1`](https://github.com/brianravelo28/stackoverflow-nlp-query-engine/releases/tag/data-v1),
~175 MB) so you can skip the Kaggle step.

## How to Run

```bash
pip install -r requirements-dev.txt   # requirements.txt is the slimmer deploy set

# Option A — skip the export: download the prebuilt database
python src/download_db.py

# Option B — rebuild from scratch
#   1. run data/kaggle_export.py in a Kaggle Notebook (Stack Overflow BigQuery
#      dataset attached), download the 6 CSVs into data/
python src/build_db.py
python src/add_indexes.py

# Optional checks
python src/queries.py                 # the 15-query suite
export ANTHROPIC_API_KEY=your_key_here
python src/test_nlp_questions.py      # the 20-question test

# Run the app
streamlit run app/app.py
```

## Deploy (Render)

[`render.yaml`](render.yaml) defines a free web service. The build runs
`src/download_db.py`, which fetches the release asset (the 480 MB database is
too large for git; it is re-downloaded on every deploy). The app opens the
database read-only and caps each session at 10 questions to limit API spend.

1. Render → New → Blueprint → connect this repo
2. Set `ANTHROPIC_API_KEY` when prompted, and set a monthly spend limit on the
   key in the Anthropic Console

## Files

```
README.md
LICENSE                          MIT (code only; see docs/CITATIONS.md for the data license)
render.yaml                      Render service definition
requirements.txt                 deploy dependencies
requirements-dev.txt             adds pyarrow, matplotlib, jupyter
data/
  kaggle_export.py               BigQuery export, run in a Kaggle Notebook
src/
  download_db.py                 fetch the prebuilt database from the GitHub Release
  build_db.py                    schema + CSV loader
  add_indexes.py                 10 indexes
  queries.py                     15 analytical queries
  nlp_layer.py                   Claude-backed text-to-SQL + safety validation
  test_nlp_questions.py          20-question executability test
app/
  app.py                         Streamlit chat interface
notebooks/
  01_eda.ipynb                   exploratory analysis (needs the database built)
docs/
  ARCHITECTURE.md                design, request flow, safety model
  DATA_SCHEMA.md                 ER diagram, table definitions, scoping
  DATA_QUIRKS.md                 data problems found and how they were handled
  METHODOLOGY.md                 prompt design, query suite, evaluation
  CITATIONS.md                   sources and data license
```

## Author
Brian | Data Scientist | October 2026
