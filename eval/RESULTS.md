# Evaluation results

How often the app's generated SQL returns the right answer, measured on questions the prompt was never tuned on.

## Result

On the 38 answerable test questions, the app returned the reference answer for 37 in each of 3 runs: **97.4% mean accuracy**.
Over 38 questions, a 95% interval for 37 correct is 86.5% to 99.5%.

The one miss, T28, returned the right values under different group labels (see [The one miss](#the-one-miss)).
The two unanswerable test questions were declined in every run.

## Setup

| | |
|---|---|
| Model | `claude-sonnet-5-5` |
| Prompt | SHA-256 `197956c6…` (the prompt in `src/nlp_layer.py` at the code commit below) |
| Code commit | `e35dc2c` |
| Test questions | 40 (38 answerable, 2 unanswerable), frozen at commit `789e198` before any scored run |
| Runs | 3 per question, run on 2026-10-28 |
| Query limits | 30-second timeout, 1,000-row cap |
| Database | the 1-in-16 sample described in the README |

The test run was the first and only scored run on these questions. The prompt was tuned on a separate set of 20 development questions (see [Tuning on the development questions](#tuning-on-the-development-questions)).

## How answers are scored

A question passes when the query returns the same rows as the reference query. The reference answers come from hand-written SQL, and each was recomputed independently in pandas from the raw CSVs (`eval/crosscheck.py`: 56 of 56 answerable questions agree).

- Column names are ignored, and extra columns are allowed. A *strict* score counts only the same columns in the same order with exact values.
- Row order matters only for top-N questions.
- Numbers match exactly when both are whole numbers. Otherwise they match within 1e-6, or after rounding the reference to some number of decimals when the rounded value stays within 2% of it.
- Rates may be given as a fraction or a percent. Months and weekdays may be a name or a number.
- A few questions list a second or third accepted reading in `eval/questions.json`.
- Unanswerable questions pass when the model declines (an error, no rows, or the `UNANSWERABLE:` reply the prompt asks for) and fail when it returns other data.

The rules are in `eval/score.py` and tested in `tests/test_scorer.py`.

## Test results

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

Twenty development questions (18 answerable) were used to adjust the prompt. Both development runs are in `eval/runs/`.

| Run | Prompt | Timeout | Mean accuracy | Main failures |
|---|---|---|---|---|
| dev-1 | first version | 10 s | 83.3% | queries timed out after needless joins; a blanket date filter on the wrong table |
| dev-2 | tuned | 30 s | 100% | none |

Between the two runs the prompt stopped asking for a blanket date filter and a blanket `LIMIT`, asked for faster queries, and gained the `UNANSWERABLE:` reply. The query timeout went from 10 to 30 seconds, because a correct 11-second query was being cancelled.

Two scorer changes were made after seeing development results: accepting different wording for the group labels of D11 and T28, and accepting "questions + answers + comments" as a third reading of D17. The development score is therefore a tuning figure, not a result.

## Limits

- **Small set.** 38 questions means one question moves the score by 2.6 points. The interval above shows the range.
- **One author, one schema.** The questions and reference queries were written for this project and reviewed by its author, in the same style as the prompt's examples. Real users may ask vaguer or harder questions.
- **Correct means matching the reference.** Where wording is ambiguous, only the listed readings count.
- **Equivalences count as correct.** Rounding within 2%, rates on either scale, and month or weekday names versus numbers are all accepted, which is why the strict score (61 of 114 runs) is lower.
- **Default sampling.** The model rejects a `temperature` setting, so runs vary between executions. Three runs per question show the variation, and it did not change any outcome here.
- **Sample data.** The database holds a 1-in-16 sample of questions with 38 tags, from 2020-01-01 to 2022-09-25. The scores describe this database.

## Reproduce

```bash
export ANTHROPIC_API_KEY=your_key_here
python eval/run_eval.py --split test --runs 3 --label test-1   # needs the built database
python eval/score.py eval/runs/test-1.json
```

Scoring needs no database or API key because the reference answers are saved in `eval/reference_results.json`.
`python eval/crosscheck.py` re-derives the references in pandas and needs the CSVs in `data/`.

Files: `eval/questions.json` (questions and reference SQL), `eval/reference_results.json`, `eval/runs/test-1.json` (what the model returned), `eval/runs/test-1.scored.json` (per-question verdicts).
