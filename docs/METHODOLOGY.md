# Methodology

## 🎯 Objective

Translate plain-English analytical questions into correct, safe, executable
SQL against a normalized StackOverflow schema — and be honest about where
that breaks down.

**Target**: ≥80% of a 20-question test set (from the project spec) execute
successfully (valid SQL, passes the safety gate, returns without error). This
measures *executability*, not semantic correctness of the result set, and the
test set is not held out from the prompt — see
[Evaluation](#-evaluation--limitations) below.

---

## 🧱 Query Suite Design (the 15 queries)

Each of the 15 queries in
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
| Filter on a flag (`is_accepted = 1`) | `q7` most accepted answers |
| Conditional SUM (`is_accepted`) | `q9`, `q11` acceptance rates |
| CTE + conditional aggregation across years | `q8` YoY tag growth — complete years only (2020 vs 2021, since 2022 is partial) and tags with ≥50 prior-year questions, otherwise one-off tags with 1→14 questions top the list |
| HAVING clause (min sample size) | `q9`, `q15` — acceptance rate / avg score with `HAVING COUNT(*) >= 5` to avoid single-answer users/tags skewing rankings |
| Two-table join + COUNT | `q10` most-commented questions |
| 5-table join with a tag filter | `q12` reputation ranking among Python answerers (tag is hardcoded to `python`, not a parameter) |
| Compound WHERE | `q13` high-answer-count, unaccepted questions |
| Self-join on a join table | `q14` tag co-occurrence pairs |

Four of these queries (top tags, unanswered questions, user acceptance rate,
tag combinations — `q1`, `q3`, `q9`, `q14`) are used verbatim as the few-shot
examples in
[`src/nlp_layer.py`](../src/nlp_layer.py)'s `SYSTEM_PROMPT`, chosen to cover
the join patterns (single table, two-table, three-table via `post_tags`,
self-join) most likely to generalize to unseen questions.

**Median, deliberately not in SQL**: `q6` (time to first answer) computes
raw per-question deltas in SQL and takes the median in pandas —
SQLite has no `MEDIAN()`/`PERCENTILE_CONT()`. The system prompt notes that
SQLite has no `MEDIAN()`. For the same question the NLP layer wrote its own
pure-SQL median (a window-function or `OFFSET` pattern) and got the same
answer, 0.63 hours.

---

## 🤖 Prompt Architecture

The system prompt ([`src/nlp_layer.py`](../src/nlp_layer.py)) has four parts:

1. **Role + output contract** — "respond ONLY with a valid SQLite SELECT
   query, no markdown fences" — because the app parses the response directly
   as SQL; free text or code fences would break execution.
2. **Schema and notes** — every table and column (a column list, not full
   DDL), plus notes on the non-obvious relationships (`posts_answers.parent_id`
   → question, `post_tags` is the tag join table, `votes.user_id` may be NULL)
   and on the data itself: it ends 2022-09-25, so "recent"/"last month" are
   relative to that date, and 2022 is a partial year.
3. **Four few-shot examples** — see above.
4. **Constraints** — SELECT-only, prefer a `LIMIT` unless the question asks
   for a single aggregate, filter to `>= 2020-01-01` when a date filter is
   relevant.

Without the date notes the model has no way to know the data ends in September
2022; a "last month" filter relative to today's date would return no rows.

**Why schema notes matter more than more examples**: the columns most likely
to cause a wrong join (`parent_id` naming, `is_accepted` being an answer-level
flag rather than a question-level one) are exactly the ones an LLM without
StackOverflow-specific training would guess wrong from column names alone —
that's why they're called out as prose notes rather than left implicit in
the DDL.

---

## 🛡️ Safety Validation

See [`docs/ARCHITECTURE.md`](ARCHITECTURE.md#-safety-model) for the
implementation, including the read-only database connection in the deployed
app. Methodologically: this is a **blocklist**, chosen over a full
SQL-parser allowlist because the threat model here is "LLM occasionally
emits a write statement it shouldn't," not "adversarial user crafts SQL to
evade detection." The tradeoff is explicit, not accidental.

---

## 📊 Evaluation & Limitations

**What ≥80% executability measures**: the generated SQL is syntactically
valid SQLite, references real tables/columns, and passes the safety gate.

**What it does *not* measure**:

1. Whether the query answers the question *correctly*.
2. Generalization. Four of the 20 test questions (Q1, Q3, Q9, Q14) are the
   same four questions used as few-shot examples in the prompt, so they are
   not held out.

On the first point: A query that runs without error but joins the wrong tables
(e.g. counting `comments` when the user asked about `votes`) would still
count as a "pass" under this metric. A proper accuracy evaluation would need
either hand-written expected result sets per test question, or an
execution-match comparison against a reference query — neither is built yet.

**Actual results**: 20/20 questions produced SQL that executed against the
real database. Three were spot-checked for correctness (median time to first
answer, answer acceptance fraction, "last month") and matched the
hand-written suite (0.63 hours, 0.3811, anchored to the data's end date of
2022-09-25). The first run scored 14/20; all 6 failures were a parsing bug in
`generate_sql` (it read only the first response block, which can be a
"thinking" block), not model errors. The other 17 answers have not been
checked for semantic correctness.

The 35 example questions shown in the app were each run once and all return
rows (one was reworded: "asked and answered more than 20 questions" returned
nothing in the 1-in-16 sample, so the threshold became 3). One of them was
also tried on the deployed site. Results are from single runs; model output
is not deterministic.

---

## 📚 Data Scoping Decisions

See [`docs/DATA_SCHEMA.md`](DATA_SCHEMA.md) for the full rationale: the
BigQuery export is limited to 38 popular tags and a 1-in-16 sample (the tag
filter alone is ~2.8M questions), the data ends 2022-09-25 because that is
where the public mirror stops, and `votes.user_id` is nullable (always NULL)
because the real votes table has no voter column (a correction from the
original project spec, which assumed a non-null FK there). Problems found while
loading are listed in [`DATA_QUIRKS.md`](DATA_QUIRKS.md).
