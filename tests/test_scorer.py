"""Tests for eval/score.py. Uses the committed eval/reference_results.json, so no database is needed."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import score  # noqa: E402

QUESTIONS = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
REFS = json.loads((ROOT / "eval" / "reference_results.json").read_text(encoding="utf-8"))
BY_ID = {q["id"]: q for q in QUESTIONS}
ANSWERABLE = [q["id"] for q in QUESTIONS if q["reference_sql"]]


def rec(rows, **kw):
    return {"run": 0, "rows": [list(r) for r in rows], "error_kind": None, "truncated": False, **kw}


def grade(qid, rows, **kw):
    return score.score_answerable(BY_ID[qid], rec(rows, **kw), REFS[qid])


def ref_rows(qid, label="reference"):
    return next(r["rows"] for r in REFS[qid] if r["label"] == label)


def test_reference_files_cover_every_answerable_question():
    assert len(ANSWERABLE) == 56 and set(REFS) == set(ANSWERABLE)


@pytest.mark.parametrize("qid", ANSWERABLE)
def test_each_reference_and_alternate_passes_strictly(qid):
    for entry in REFS[qid]:
        res = grade(qid, entry["rows"])
        same = [e["label"] for e in REFS[qid] if e["rows"] == entry["rows"]]  # D17's two readings give one answer
        assert res["status"] == "pass" and res["strict"] and res["matched"] in same


@pytest.mark.parametrize("qid", ANSWERABLE)
def test_dropping_a_row_fails(qid):
    rows = ref_rows(qid)
    if len(rows) < 2:
        pytest.skip("single-row answer")
    assert grade(qid, rows[:-1])["status"] == "fail"


@pytest.mark.parametrize("qid", ANSWERABLE)
def test_changing_a_number_fails(qid):
    rows = [list(r) for r in ref_rows(qid)]
    for i, j in ((i, j) for i in range(len(rows)) for j in range(len(rows[i]))):
        if isinstance(rows[i][j], (int, float)):
            rows[i][j] = rows[i][j] + 1 if float(rows[i][j]).is_integer() else rows[i][j] * 1.01
            assert grade(qid, rows)["status"] == "fail"
            return
    pytest.skip("no numbers")


@pytest.mark.parametrize("qid", ANSWERABLE)
def test_row_order_matters_only_for_rankings(qid):
    rows = ref_rows(qid)
    if len(rows) < 2 or len({tuple(r) for r in rows}) < 2:
        pytest.skip("nothing to reorder")
    expected = "fail" if score.Spec(BY_ID[qid]).ordered else "pass"
    assert grade(qid, rows[::-1])["status"] == expected


def test_ranking_questions_are_the_top_n_ones():
    ordered = sorted(i for i in ANSWERABLE if score.Spec(BY_ID[i]).ordered)
    assert ordered == ["D04", "D05", "T07", "T08", "T10", "T11", "T14", "T17", "T35", "T36", "T37"]


def test_extra_and_reordered_columns_pass_but_not_strictly():
    rows = ref_rows("D04")  # (tag_name, comment_count)
    extra = grade("D04", [[*r, "x"] for r in rows])
    swapped = grade("D04", [[r[1], r[0]] for r in rows])
    assert extra["status"] == swapped["status"] == "pass"
    assert not extra["strict"] and not swapped["strict"]


def test_extra_columns_cannot_mix_up_rows():
    rows = [["python", 3], ["java", 2]]
    q = {"id": "Z", "reference_sql": "SELECT 1 LIMIT 2"}
    spec = score.Spec(q)
    assert score.compare(rows, [["java", 2, 0], ["python", 3, 0]], score.Spec({"id": "Z", "reference_sql": "SELECT 1"}))["passed"]
    assert not score.compare(rows, [["python", 2], ["java", 3]], spec)["passed"]


def test_text_comparison_ignores_case_and_spacing():
    assert grade("D17", [["  gordon   LINOFF ", 1295]])["status"] == "pass"


def test_rounding_rules():
    base = ref_rows("T09")[0][0]  # 2.026...
    assert grade("T09", [[round(base, 2)]])["kinds"] == ["rounded"]
    assert grade("T09", [[round(base, 1)]])["status"] == "pass"
    assert grade("T09", [[round(base)]])["status"] == "pass"  # 2 is within 2% of 2.026
    assert grade("T09", [[2.5]])["status"] == "fail"
    n = ref_rows("D01")[0][0]  # a count must be exact
    assert grade("D01", [[n + 1]])["status"] == "fail"
    avg = ref_rows("D02")[0][0]
    assert grade("D02", [[float(round(avg))]])["status"] == "pass"


def test_rates_accept_percent_or_fraction():
    frac = ref_rows("T26")[0][0]
    for value in (frac, frac * 100, round(frac * 100, 1)):
        assert grade("T26", [[value]])["status"] == "pass"
    assert grade("T26", [[frac * 10]])["status"] == "fail"
    pct = ref_rows("T22")[0][0]
    assert grade("T22", [[pct / 100]])["status"] == "pass"
    assert grade("D01", [[ref_rows("D01")[0][0] * 100]])["status"] == "fail"  # not a rate question


def test_months_and_weekdays_in_any_form():
    count = ref_rows("T23")[0][1]
    for month in ("April", "april", "Apr", "04", "4", 4):
        assert grade("T23", [[month, count]])["status"] == "pass"
    assert grade("T23", [["May", count]])["status"] == "fail"
    assert grade("T23", [["2021-04", count]])["status"] == "fail"  # years are combined in this question
    month_row = ref_rows("D10")[0]  # ('2021-MM', n)
    mm = int(month_row[0][-2:])
    assert grade("D10", [[month_row[0], month_row[1]]])["strict"]
    assert grade("D10", [[score.MONTHS[mm - 1].title(), month_row[1]]])["status"] == "pass"
    weekday, wcount = ref_rows("T38", "alt 1")[0]
    for value in ("Wednesday", "wed", 3, "3"):
        assert grade("T38", [[value, wcount]])["matched"] == "alt 1"
    assert grade("T38", [["Thursday", wcount]])["status"] == "fail"


def test_failures_report_a_reason():
    assert grade("D01", [])["reason"] == "empty_result"
    assert grade("D01", [[1], [2]])["reason"] == "row_count"
    assert grade("D04", [[1]] * 10)["reason"] == "too_few_columns"
    assert grade("D01", [[1]])["reason"] == "wrong_values"
    for kind, reason in score.ERROR_REASON.items():
        res = score.score_answerable(BY_ID["D01"], {"run": 0, "error_kind": kind, "error": "x"}, REFS["D01"])
        assert res["status"] == "fail" and res["reason"] == reason
    assert grade("D04", ref_rows("D04")[:5], truncated=True)["reason"] == "truncated_by_cap"


def unans(qid, rows=None, error_kind=None, names=None):
    r = {"run": 0, "error_kind": error_kind, "rows": rows or []}
    return score.score_unanswerable(BY_ID[qid], r, names)


def test_unanswerable_questions():
    assert unans("D20", error_kind="sql")["status"] == "pass"
    assert unans("D20", error_kind="gate")["status"] == "pass"  # a prose refusal is not SQL
    assert unans("D20", rows=[])["status"] == "pass"
    assert unans("D20", rows=[[None]])["status"] == "pass"
    assert unans("D20", rows=[["python", 5]])["reason"] == "substituted_data"
    assert unans("T40", rows=[[1, 0]])["status"] == "fail"
    assert unans("D19", rows=[["alice", 10], ["bob", 8]], names={"alice", "bob"})["reason"] == "named_users"
    assert unans("T39", rows=[[101, 40]], names={"alice"})["status"] == "review"
    assert unans("D19", error_kind="api")["reason"] == "api_error"


def test_summary_counts_runs_and_keeps_unanswerable_apart():
    items = []
    for run in (0, 1):
        items.append(grade("D01", ref_rows("D01")) | {"run": run})
        items.append(grade("D02", [[0]]) | {"run": run} if run == 0 else grade("D02", ref_rows("D02")) | {"run": run})
        items.append(unans("D20", error_kind="sql") | {"run": run})
    s = score.summarize(items)
    assert s["questions"] == 2 and s["runs"] == 2
    assert s["per_run_passed"] == {0: 1, 1: 2}
    assert s["mean_accuracy"] == 0.75
    assert s["consistency"] == {"always": 1, "sometimes": 1}
    assert s["failure_reasons"] == {"wrong_values": 1}
    assert s["unanswerable"] == {"pass": 2}
