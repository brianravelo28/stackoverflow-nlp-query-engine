# Methodology

## Objective

Translate plain-English analytical questions into correct, safe, executable SQL against a normalized
StackOverflow schema, and measure how often the result is right.

**Target**: the generated SQL returns the same rows as a reference query on held-out questions, measured by
execution match. Results: [`eval/RESULTS.md`](../eval/RESULTS.md); design: [Evaluation](#evaluation) below.

---

## Query Suite Design (the 15 queries)

Each of the 15 queries in [`src/queries.py`](../src/queries.py) was chosen to exercise a distinct SQL pattern
the NLP layer would also need to reproduce. All 15 run against the loaded data.

| Pattern | Example query |
|---|---|
| Simple aggregation + join | `q1` top tags by volume |
| Filter + threshold | `q2` users over 1000 reputation |
| NULL filtering | `q3` questions with no accepted answer |
| Aggregation ratio | `q4` avg answers per tag, for tags with at least 50 questions so a tag used once cannot top the list |
| GROUP BY + ORDER BY + LIMIT | `q5` top answerers |
| Date arithmetic (`julianday`) | `q6` time to first answer |
| Filter on a flag (`is_accepted = 1`) | `q7` most accepted answers |
| Conditional SUM (`is_accepted`) | `q9`, `q11` acceptance rates |
| CTE + conditional aggregation across years | `q8` YoY tag growth, using complete years only (2020 vs 2021, since 2022 is partial) and tags with ≥50 prior-year questions, otherwise one-off tags with 1→14 questions top the list. It compares a single year pair on a sample, with no uncertainty estimate |
| HAVING clause (min sample size) | `q9`, `q15`: acceptance rate and avg score with `HAVING COUNT(*) >= 5` to keep single-answer users and tags from skewing rankings |
| Two-table join + COUNT | `q10` most-commented questions |
| 5-table join with a tag filter | `q12` reputation ranking among Python answerers (tag is hardcoded to `python`, not a parameter) |
| Compound WHERE | `q13` high-answer-count, unaccepted questions |
| Self-join on a join table | `q14` tag co-occurrence pairs |

Four of these queries (top tags, unanswered questions, user acceptance rate, tag combinations: `q1`, `q3`,
`q9`, `q14`) are used as the few-shot examples in [`src/nlp_layer.py`](../src/nlp_layer.py)'s `SYSTEM_PROMPT`,
chosen to cover the join patterns (single table, two-table, three-table via `post_tags`, self-join) most
likely to generalize to unseen questions. The `q3` example omits the suite's `LIMIT 50`, because the prompt
now asks for a `LIMIT` only on top-N questions.

**Median, deliberately not in SQL**: `q6` (time to first answer) computes raw per-question deltas in SQL and
takes the median in pandas (0.63 hours), because SQLite has no `MEDIAN()` or `PERCENTILE_CONT()`. The system
prompt says so and tells the model to compute a median with `ROW_NUMBER()` and `COUNT(*) OVER ()` when asked.
In an early spot-check the NLP layer's own pure-SQL median matched the pandas value.

---

## Prompt Architecture

The system prompt ([`src/nlp_layer.py`](../src/nlp_layer.py)) has four parts:

1. **Role + output contract**: "respond ONLY with a valid SQLite SELECT query, no markdown fences", because
   the app runs the response directly as SQL; free text or code fences would break execution.
2. **Schema and notes**: every table and column (a column list, not full DDL), plus notes on the non-obvious
   relationships (`posts_answers.parent_id` → question, `post_tags` is the tag join table, `votes.user_id`
   may be NULL) and on the data itself: it ends 2022-09-25, so "recent" and "last month" are relative to that
   date, and 2022 is a partial year.
3. **Four few-shot examples**: see above.
4. **Constraints**: SELECT only; no date filters the question did not ask for; a `LIMIT` only on top-N
   questions ("the most" means `LIMIT 1`); fast queries (no unneeded joins, aggregate before joining); and
   the reply `SELECT 'UNANSWERABLE: <reason>' AS answer` when the data does not exist in the schema.

Without the date notes the model has no way to know the data ends in September 2022; a "last month" filter
relative to today's date would return no rows.

**Why schema notes matter more than more examples**: the columns most likely to cause a wrong join
(`parent_id` naming, `is_accepted` being an answer-level flag rather than a question-level one) are the ones a
model without StackOverflow-specific knowledge would guess wrong from column names alone. That is why they
are called out as prose notes rather than left implicit in the column list.

**Tuning**: the prompt was adjusted on 20 development questions only. The first run on them (83.3%) showed
two causes of failure: a blanket "filter to 2020 or later" instruction that added needless joins (queries slow
enough to time out) and, in one case, a filter on the wrong table, and a blanket `LIMIT` instruction that
would cut off complete tables. Both lines were replaced, and the `UNANSWERABLE` reply was added. The test
questions were not used in tuning.

**Reading the response**: `generate_sql` joins only the text blocks of the response. The reply can begin with
a non-text "thinking" block even though the code does not request one, and an early version that read only
the first block failed 6 of its first 20 questions for that reason.

---

## Safety Validation

See [`ARCHITECTURE.md`](ARCHITECTURE.md#safety-model) for the implementation: the token-based gate, the
read-only database connection in the deployed app, the 30-second timeout, the 1,000-row cap and the spend
limits. Methodologically, the gate is a **tokenizer-based check**, chosen over a full SQL-parser allowlist
because the threat model here is "the model occasionally emits a write statement it shouldn't", not "an
adversarial user crafts SQL to evade detection". The tradeoff is explicit, and the read-only connection is
the layer that carries the guarantee.

---

## Evaluation

The earlier 20-question executability test was replaced by a held-out accuracy evaluation (`eval/`):

- **Questions**: 60, written for this project: 20 development questions used to tune the prompt, and 40 test
  questions (38 answerable, 2 about data that does not exist) frozen in git before the first scored run.
  None duplicates an app example question or a few-shot example.
- **Reference answers**: hand-written SQL, run against the database and recomputed independently in pandas
  from the raw CSVs (`eval/crosscheck.py`: all 56 answerable questions agree). A few ambiguous questions
  list a second or third accepted reading.
- **Scoring**: execution match. A question passes when the generated SQL returns the same rows as a
  reference. Column names are ignored and extra columns are allowed; order counts only for top-N questions;
  numbers match exactly (whole numbers) or within a small rounding tolerance; rates count as a fraction or a
  percent; months and weekdays count as a name or a number. A strict score counts only exact columns and
  values. Rules live in `eval/score.py` and are tested in `tests/test_scorer.py`.
- **Runs**: each question was run 3 times, since the model rejects a `temperature` setting.

**Result**: on the 38 answerable test questions the generated SQL was correct for 37 in each of the 3 runs
(97.4%). The miss returned the correct values under different group labels. Both unanswerable questions were
declined in every run.

**Limits**: 38 questions is a small set (a 95% interval for 37 of 38 is 86.5% to 99.5%), written for this
schema in the same style as the prompt's examples, so real users may ask vaguer or harder questions. Where
wording is ambiguous only the listed readings count. The data is a 1-in-16 sample, and the scores describe
this database. The full write-up is in [`eval/RESULTS.md`](../eval/RESULTS.md).

---

## Data Scoping Decisions

See [`DATA_SCHEMA.md`](DATA_SCHEMA.md) for the full rationale: the BigQuery export is limited to 38 popular
tags and a 1-in-16 sample (the tag filter alone is ~2.8M questions), the data ends 2022-09-25 because that is
where the public mirror stops, and `votes.user_id` is nullable (always NULL) because the real votes table has
no voter column.
