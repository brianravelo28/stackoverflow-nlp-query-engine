# Evaluation results

How often the app's generated SQL returns the right answer, measured on questions the prompt was never tuned on.

There are two test sets. The second is larger and is the main result; the first is kept because it came first.

## Result

On the second test set (113 answerable questions), the app returned the reference answer for 92, 89 and 88 questions in its 3 runs: **79.4% mean accuracy**.
Treating the 113 questions as the sample, a 95% interval around that mean is 71.0% to 85.8%.
All 13 unanswerable questions were declined in every run (39 of 39).

A schema-only baseline prompt, run once, answered 86 of 113 (76.1%, interval 67.5% to 83.0%). On answerable questions the two prompts are inside each other's intervals, so this set does not separate them. The full prompt declined every unanswerable question; the baseline declined 3 of 13 (see [Full prompt against the baseline](#full-prompt-against-the-baseline)).

On the first test set (38 answerable questions) the app was right for 37 in each of 3 runs, and the baseline also got 37. That set is too small to say more (see [First test set results](#first-test-set-results)).

## Setup

| | Second test set | First test set |
|---|---|---|
| Model | `claude-sonnet-5-5` | `claude-sonnet-5-5` |
| Prompt | SHA-256 `197956c6…` (the same prompt as the first set) | SHA-256 `197956c6…` (the prompt in `src/nlp_layer.py` at the code commit below) |
| Code commit | `825a96d` | `e35dc2c` |
| Questions | 126 (113 answerable, 13 unanswerable), frozen at commit `42677b9` before the model saw them | 40 (38 answerable, 2 unanswerable), frozen at commit `789e198` before any scored run |
| Runs | 3 per question, run on 2026-11-17; plus 1 baseline run | 3 per question, run on 2026-10-28; plus 1 baseline run |
| Query limits | 30-second timeout, 1,000-row cap | 30-second timeout, 1,000-row cap |
| Database | the 1-in-16 sample described in the README | the same |

**Who wrote the questions.** Of the 126 second-set questions, 90 were written by the AI assistant used on this project and 36 by the project's author. The reference answers were derived independently by two writers working blind (two separate AI agents given only the question and the database). Where they read a question differently, the author decided, and the accepted readings are stored with the question. A few questions were reworded after that review so that the answer has a clear cut-off. The first test set's questions and reference queries were written for this project and reviewed by its author.

Neither test set was used to tune the prompt, which was tuned on a separate set of 20 development questions (see [Tuning on the development questions](#tuning-on-the-development-questions)). One line was added to the prompt after the second-set runs were seen; that is described under [What the misses were](#what-the-misses-were).

## How answers are scored

A question passes when the query returns the same rows as the reference query. For the first set the reference answers come from hand-written SQL, and each was recomputed independently in pandas from the raw CSVs (`eval/crosscheck.py`: 56 of 56 answerable questions agree). For the second set each reference was derived twice, independently, and the two agreed or the author chose between them.

- Column names are ignored, and extra columns are allowed. A *strict* score counts only the same columns in the same order with exact values.
- The number of rows must match. A longer list, even with the right first rows, fails. This is the strict rule; the [relaxed score](#the-relaxed-score) is shown beside it for questions that do not say how many rows to return.
- Row order matters only for top-N questions, and rows that tie on the ranking number may come in any order.
- Numbers match exactly when both are whole numbers. Otherwise they match within 1e-6, or after rounding the reference to some number of decimals when the rounded value stays within 2% of it.
- Rates may be given as a fraction or a percent. Months and weekdays may be a name or a number.
- Some questions list a second or third accepted reading in the questions file.
- Unanswerable questions pass when the model declines (an error, no rows, or the `UNANSWERABLE:` reply the prompt asks for) and fail when it returns other data.

The rules are in `eval/score.py` and tested in `tests/test_scorer.py` and `tests/test_eval_set2.py`.

## Second test set results

| Category | Questions | Runs correct |
|---|---|---|
| Aggregation | 20 | 57 of 60 |
| Join | 30 | 69 of 90 |
| Absence (no answers, never asked, …) | 10 | 26 of 30 |
| Date | 23 | 53 of 69 |
| Window (ranking, running totals) | 12 | 32 of 36 |
| Rate | 12 | 27 of 36 |
| Ambiguous wording | 6 | 5 of 18 |
| **All answerable** | **113** | **269 of 339** |

The pass or fail outcome was the same in all three runs for 105 of the 113 questions: 86 were right every time and 19 never. The other 8 varied. The SQL differed between runs for 73 of the 113 questions.

Questions written by the assistant passed in 186 of 234 runs (79.5%, 78 questions) and the author's in 83 of 105 runs (79.0%, 35 questions).

### How the answers matched

- 133 of the 339 runs were strict matches (the same columns, in the same order, with exact values).
- 106 of the 269 correct runs returned extra columns, usually a count next to a name.
- 42 correct runs matched after rounding, and 3 gave a rate on the other scale (fraction against percent).

### Full prompt against the baseline

| | Answerable questions right | Unanswerable declined |
|---|---|---|
| Full prompt (3 runs) | 92, 89, 88 of 113 | 39 of 39 |
| Schema-only baseline (1 run) | 86 of 113 | 3 of 13 |

On the same first run, the full prompt got 12 questions right that the baseline missed and the baseline got 6 right that the full prompt missed. That favours the full prompt, but it is a small difference next to the intervals.

The unanswerable gap is large and was expected: the baseline prompt has no instruction to decline, so for 10 of the 13 it answered with other data (the `UNANSWERABLE:` reply is part of the full prompt).

### What the misses were

The 27 questions that were not right in every run, looked at one by one after the runs (nothing in the set or the scorer was changed because of this):

| Cause | Questions | What happened |
|---|---|---|
| The model guessed numeric vote codes | 5: A030, A088, U23 (never right); A040, U22 (sometimes) | It filtered on `vote_type = 2` or `3`, the codes in the original Stack Exchange data, but this database stores text such as `'UpMod'`, so the queries returned nothing or 0. |
| Broken SQL | 2: U31, A061 | "Incomplete input" and "no such column" errors. |
| Right content, wrong number of rows | 10: A015, A024, A028, A083, A085, U12 (never right); A041, A050, A076, A084 (sometimes) | The question gave no N and the model chose a different length from the reference, or laid the answer out differently. |
| A different but defensible reading | 9: A020, A031, A063, A066, A073, A086, U13, U15, U16 | For example distinct askers against questions, the stored `answer_count` against the answer rows that exist, and how weeks are counted. |
| Expected | 1: U25 | The question asks about visible text and the model counts the HTML tags. |

Only the first two rows are plain model errors. The rest mostly measure how a question was worded or read.

**The vote-code fix.** The prompt's schema line listed `vote_type` without saying what it holds. A line was added afterwards (prompt SHA-256 `3b16c366…`) listing the text values. It was checked on five new vote questions that are in neither set, which went from 10 of 15 right to 15 of 15, and on the first set's development questions, which scored 18 of 18 in all three runs with the unanswerable questions still declined (`eval/runs/dev-3.json`). The second-set runs above were made before the change and were not repeated, so they are the before figure.

### The relaxed score

Seven questions (A015, A024, A028, A041, A050, A083, A085) do not say how many rows to return, and the model's longer answers failed the row count although the rows asked for were right. The scorer also reports a relaxed accuracy that counts a longer answer whose first rows match the reference. It was added after the runs were seen, so it is shown beside the headline and never in place of it: **84.7%** for the full prompt and **79.6%** for the baseline.

### Unanswerable questions

All 13 unanswerable questions were declined in every full-prompt run (39 of 39). They cover data the database does not hold: edit history, closed or deleted posts, countries, badge names, bounty amounts, who voted, and similar.

## First test set results

On the 38 answerable test questions, the app returned the reference answer for 37 in each of 3 runs: **97.4% mean accuracy**.
Over 38 questions, a 95% interval for 37 correct is 86.5% to 99.5%.

The one miss, T28, returned the right values under different group labels (see [The one miss](#the-one-miss)).
The two unanswerable test questions were declined in every run.

A schema-only baseline run on the same questions (1 run per question, `eval/runs/baseline-schema-only.json`) also answered 37 of 38, so this set cannot tell the two prompts apart. That is why the second set was built.

| Category | Questions | Runs correct |
|---|---|---|
| Aggregation | 6 | 18 of 18 |
| Join | 8 | 24 of 24 |
| Absence (no answers, never asked, …) | 5 | 15 of 15 |
| Date | 6 | 18 of 18 |
| Window (ranking, running totals) | 5 | 15 of 15 |
| Rate | 6 | 15 of 18 |
| Ambiguous wording | 2 | 6 of 6 |
| **All answerable** | **38** | **111 of 114** |

The pass or fail outcome for each question was the same in all three runs, even though the SQL differed between runs for 14 of the 38 questions.

### How the answers matched

- 61 of the 114 runs were strict matches (the same columns, in the same order, with exact values).
- 36 of the 111 correct runs returned extra columns, usually a count next to a rate.
- 21 correct runs matched after rounding, for example 2.026 for 2.0263.
- 3 runs gave a month as a number ("04") where the reference says "April", and 2 gave a rate on the other scale (fraction against percent).

### The one miss

T28 asks for the average score of the first answer to each question against later answers. The reference labels the two groups `first` and `later`. The model returned `first_answer` and `later_answers` with the same averages (0.998 and 0.987), computed with the same logic. The scorer accepts "first answer" with a space but not the underscored form, so all three runs count as misses. This is a labeling difference in a correct answer. It is counted as a miss here.

### Ambiguous and unanswerable questions

- The two ambiguous test questions (T37, T38) matched the primary reading in every run. No accepted alternate was needed.
- T39 (who voted) and T40 (edit history) ask for data that does not exist. The model declined in all 6 runs. The prompt now gives the exact reply to use, so this checks that the instruction is followed. Before that instruction, the development run declined in free text for one of the two questions, and the scorer failed it.

## Tuning on the development questions

Twenty development questions (18 answerable) were used to adjust the prompt. All three development runs are in `eval/runs/`.

| Run | Prompt | Timeout | Mean accuracy | Main failures |
|---|---|---|---|---|
| dev-1 | first version | 10 s | 83.3% | queries timed out after needless joins; a blanket date filter on the wrong table |
| dev-2 | tuned | 30 s | 100% | none |
| dev-3 | tuned, with the `vote_type` note | 30 s | 100% | none |

Between the first two runs the prompt stopped asking for a blanket date filter and a blanket `LIMIT`, asked for faster queries, and gained the `UNANSWERABLE:` reply. The query timeout went from 10 to 30 seconds, because a correct 11-second query was being cancelled. The third run checks that the `vote_type` note, added after the second test set, changed nothing here.

Two scorer changes were made after seeing development results: accepting different wording for the group labels of D11 and T28, and accepting "questions + answers + comments" as a third reading of D17. The development score is therefore a tuning figure, not a result.

## Limits

- **Sample size.** 113 questions means one question moves the score by 0.9 points, and the interval above is about 7 points either side. A difference of a few points between two prompts cannot be told from chance. The first set (38 questions) moves 2.6 points per question.
- **Authorship.** Most questions and all references were drafted with an AI assistant and reviewed or decided by the project's author, in the same style as the prompt's examples. Real users may ask vaguer or harder questions.
- **Correct means matching the reference.** Where wording is ambiguous, only the listed readings count, and a question that does not say how many rows to return can fail on length alone (see the relaxed score).
- **Equivalences count as correct.** Rounding within 2%, rates on either scale, and month or weekday names versus numbers are all accepted, which is why the strict score (133 of 339 runs on the second set) is lower.
- **One prompt line after the fact.** The `vote_type` note was added after the second-set runs. The runs above predate it, and the questions were not changed.
- **Default sampling.** The model rejects a `temperature` setting, so runs vary between executions. Three runs per question show the variation: 8 of 113 questions changed outcome between runs.
- **Sample data.** The database holds a 1-in-16 sample of questions with 38 tags, from 2020-01-01 to 2022-09-25. The scores describe this database.

## Reproduce

```bash
export ANTHROPIC_API_KEY=your_key_here
python eval/run_eval.py --split test2 --runs 3 --label test2-1   # second set; needs the built database
python eval/score.py eval/runs/test2-1.json --set v2
python eval/run_eval.py --split test --runs 3 --label test-1     # first set
python eval/score.py eval/runs/test-1.json
```

Scoring needs no database or API key because the reference answers are saved in `eval/reference_results_v2.json` and `eval/reference_results.json`.
`python eval/crosscheck.py` re-derives the first set's references in pandas and needs the CSVs in `data/`.

Files: `eval/questions_v2.json` (second set, with reference SQL), `eval/reference_results_v2.json`, `eval/relaxed_v2.json`, `eval/runs/test2-1.json` (what the model returned), `eval/runs/test2-1.scored.json` (per-question verdicts), `eval/runs/test2-baseline-schema-only.json`; and for the first set `eval/questions.json`, `eval/reference_results.json`, `eval/runs/test-1.json`, `eval/runs/test-1.scored.json`.
