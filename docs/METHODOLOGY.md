# Methodology

## 🎯 Objective

Translate plain-English analytical questions into correct, safe, executable
SQL against a normalized StackOverflow schema — and be honest about where
that breaks down.

**Target**: ≥80% of a 20-question held-out test set (from the project spec)
execute successfully (valid SQL, passes the safety gate, returns without
error). This measures *executability*, not semantic correctness of the
result set — see [Evaluation](#-evaluation--limitations) below.

---

## 🧱 Query Suite Design (the "Day 2" 15 queries)

Rather than writing 15 arbitrary queries, each one in
[`src/queries.py`](../src/queries.py) was chosen to exercise a distinct SQL
pattern the NLP layer would also need to reproduce:

| Pattern | Example query |
|---|---|
| Simple aggregation + join | `q1` top tags by volume |
| Filter + threshold | `q2` users over 1000 reputation |
| NULL filtering | `q3` questions with no accepted answer |
| Aggregation ratio | `q4` avg answers per tag |
| GROUP BY + ORDER BY + LIMIT | `q5` top answerers |
| Date arithmetic (`julianday`) | `q6` time to first answer |
| Conditional SUM (`is_accepted`) | `q7`, `q9`, `q11` acceptance-rate family |
| Self-join across time buckets | `q8` YoY tag growth |
| HAVING clause (min sample size) | `q9`, `q15` — acceptance rate / avg score with `HAVING COUNT(*) >= 5` to avoid single-answer users/tags skewing rankings |
| Multi-table join (4+ tables) | `q10` most-commented questions |
| Parameterized filter | `q12` reputation ranking within a tag (defaults to `python`) |
| Compound WHERE | `q13` high-answer-count, unaccepted questions |
| Self-join on a join table | `q14` tag co-occurrence pairs |

These 15 queries also double as the **few-shot examples** for the NLP
system prompt — 4 of them (top tags, unanswered questions, acceptance rate,
tag combinations) are included verbatim in
[`src/nlp_layer.py`](../src/nlp_layer.py)'s `SYSTEM_PROMPT`, chosen to cover
the join patterns (single table, two-table, three-table via `post_tags`,
self-join) most likely to generalize to unseen questions.

**Median, deliberately not in SQL**: `q6` (time to first answer) computes
raw per-question deltas in SQL and takes the median in pandas —
SQLite has no `MEDIAN()`/`PERCENTILE_CONT()`. The system prompt tells the
model this explicitly so it doesn't hallucinate a nonexistent SQLite
function when asked a median question.

---

## 🤖 Prompt Architecture

The system prompt ([`src/nlp_layer.py`](../src/nlp_layer.py)) has four parts:

1. **Role + output contract** — "respond ONLY with a valid SQLite SELECT
   query, no markdown fences" — because the app parses the response directly
   as SQL; free text or code fences would break execution.
2. **Full schema DDL** — every table and column, plus semantic notes for
   the non-obvious relationships (`posts_answers.parent_id` → question,
   `post_tags` is the tag join table, `votes.user_id` may be NULL).
3. **Four few-shot examples** — see above.
4. **Constraints** — SELECT-only, prefer a `LIMIT` unless the question asks
   for a single aggregate, filter to `>= 2020-01-01` when a date filter is
   relevant.

**Why schema notes matter more than more examples**: the columns most likely
to cause a wrong join (`parent_id` naming, `is_accepted` being an answer-level
flag rather than a question-level one) are exactly the ones an LLM without
StackOverflow-specific training would guess wrong from column names alone —
that's why they're called out as prose notes rather than left implicit in
the DDL.

---

## 🛡️ Safety Validation

See [`docs/ARCHITECTURE.md`](ARCHITECTURE.md#-safety-model) for the
implementation. Methodologically: this is a **blocklist**, chosen over a full
SQL-parser allowlist because the threat model here is "LLM occasionally
emits a write statement it shouldn't," not "adversarial user crafts SQL to
evade detection." The tradeoff is explicit, not accidental.

---

## 📊 Evaluation & Limitations

**What ≥80% executability measures**: the generated SQL is syntactically
valid SQLite, references real tables/columns, and passes the safety gate.

**What it does *not* measure**: whether the query answers the question
*correctly*. A query that runs without error but joins the wrong tables
(e.g. counting `comments` when the user asked about `votes`) would still
count as a "pass" under this metric. A proper accuracy evaluation would need
either hand-written expected result sets per test question, or an
execution-match comparison against a reference query — neither is built yet
(see [README status](../README.md#status)).

**Actual pass/fail results**: pending — the 20-question test
([`src/test_nlp_questions.py`](../src/test_nlp_questions.py)) requires a
populated `stackoverflow.db` and an `ANTHROPIC_API_KEY`, neither of which
are committed to the repo. Results will be added here once the real Kaggle
export is loaded and the harness has been run.

---

## 📚 Data Scoping Decisions

See [`docs/DATA_SCHEMA.md`](DATA_SCHEMA.md) for the full rationale: the
BigQuery export is restricted to 2020–Sep 2022 and ~35 popular tags to keep a
local SQLite file a reasonable size, and `votes.user_id` is nullable because
the real dataset anonymizes voters (a correction from the original project
spec, which assumed a non-null FK there).
