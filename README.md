# StackOverflow NLP Query Engine

Ask plain-English questions about a normalized StackOverflow database (2020–2025)
and get back the generated SQL plus a results table — a production-shaped
text-to-SQL system, not just an API call wrapped in a chat box.

## Problem Statement

Answering "which tags are trending?" or "who has the highest answer
acceptance rate?" against a relational database normally requires knowing
SQL and the schema. This project builds a system that translates the
question itself, grounded in the real schema, with a validation layer
between the LLM and the database.

## Solution Overview

- **Database**: 7-table normalized SQLite schema (users, tags, questions,
  answers, tag join table, comments, votes) loaded from a scoped BigQuery
  export (2020–2025, curated tag list — see [`docs/DATA_SCHEMA.md`](docs/DATA_SCHEMA.md))
- **Query suite**: 15 hand-validated analytical SQL queries covering the
  join/aggregation patterns the NLP layer needs to generalize to (see
  [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md))
- **NLP layer**: Claude, prompted with the full schema DDL, semantic notes
  on non-obvious columns, and 4 few-shot examples drawn from the query suite
- **Safety gate**: generated SQL is rejected unless it's a `SELECT`/`WITH`
  statement with no write/schema keywords, before it ever touches the database
- **Interface**: Streamlit chat app — ask a question, see the generated SQL
  and the result table

Full request flow and design tradeoffs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Status

This is an in-progress build, not a finished/deployed project. What's real
vs. what's still pending:

| Component | Status |
|---|---|
| Schema + loader (`src/build_db.py`) | ✅ Built, logic-verified |
| Indexes (`src/add_indexes.py`) | ✅ Built |
| 15 analytical queries (`src/queries.py`) | ✅ Built, SQL syntax-verified against the schema |
| NLP layer (`src/nlp_layer.py`) | ✅ Built |
| Streamlit app (`app/app.py`) | ✅ Built |
| Real data loaded | ⏳ Pending — requires running the Kaggle Notebook export (see below) |
| 20-question NLP accuracy test | ⏳ Pending real data + `ANTHROPIC_API_KEY` |
| Deployment (Hugging Face Spaces) | ⏳ Not started |

No results, row counts, or accuracy numbers are reported here until they're
real — see [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md#-evaluation--limitations)
for exactly what the eventual accuracy metric will and won't tell us.

## Data

Source: `bigquery-public-data.stackoverflow`, accessed via a free Kaggle
Notebook (no local GCP setup). Scoped to 2020–2025 and ~35 popular tags to
keep a local SQLite file a manageable size. Full schema, scoping rationale,
and the real-data caveat on `votes.user_id` (the official dump anonymizes
voters): [`docs/DATA_SCHEMA.md`](docs/DATA_SCHEMA.md).

Raw data and the built database are **not** committed to this repo — only
the acquisition scripts are. See [`data/kaggle_export_queries.sql`](data/kaggle_export_queries.sql)
to reproduce the export yourself.

## How to Run

```bash
pip install -r requirements.txt

# 1. Get data: run data/kaggle_export_queries.sql in a Kaggle Notebook
#    (Stack Overflow BigQuery dataset attached), download the CSVs into data/

# 2. Build the database
python src/build_db.py
python src/add_indexes.py

# 3. Verify the query suite
python src/queries.py

# 4. Set your API key, then test the NLP layer
export ANTHROPIC_API_KEY=your_key_here
python src/test_nlp_questions.py

# 5. Run the app
streamlit run app/app.py
```

## Files

```
README.md                       this file
LICENSE                          MIT
requirements.txt
data/
  kaggle_export_queries.sql      BigQuery export queries (run in a Kaggle Notebook)
src/
  build_db.py                    schema + loader
  add_indexes.py                 10 indexes tuned to the query suite
  queries.py                     15 validated analytical queries
  nlp_layer.py                   Claude-backed text-to-SQL + safety validation
  test_nlp_questions.py          20-question accuracy harness
app/
  app.py                         Streamlit chat interface
notebooks/
  01_eda.ipynb                   exploratory analysis (run after data is loaded)
docs/
  ARCHITECTURE.md                system design, request flow, safety model
  DATA_SCHEMA.md                 ER diagram, table definitions, scoping decisions
  METHODOLOGY.md                 prompt design, query suite rationale, evaluation plan
  CITATIONS.md                   data licensing and attribution
```

## Author
Brian | Data Scientist | August 2026
