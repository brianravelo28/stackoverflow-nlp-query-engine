"""Tests for the second evaluation set (eval/questions_v2.json, eval/reference_results_v2.json)."""
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import score  # noqa: E402

DB = ROOT / "stackoverflow.db"
V1 = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
V2 = json.loads((ROOT / "eval" / "questions_v2.json").read_text(encoding="utf-8"))
REFS = json.loads((ROOT / "eval" / "reference_results_v2.json").read_text(encoding="utf-8"))
ANSWERABLE = [q for q in V2 if q["reference_sql"]]
needs_db = pytest.mark.skipif(not DB.exists(), reason="stackoverflow.db not present")


def test_the_set_has_the_expected_size_and_authors():
    assert len(V2) == 126 and len(ANSWERABLE) == 113
    assert sum(q["written_by"] == "owner" for q in V2) == 36 and sum(q["written_by"] == "assistant" for q in V2) == 90
    assert {q["split"] for q in V2} == {"test2"}


def test_ids_are_unique_and_do_not_collide_with_set_1():
    ids = [q["id"] for q in V2]
    assert len(ids) == len(set(ids))
    assert not set(ids) & {q["id"] for q in V1}


def test_every_answerable_question_has_reference_rows_and_the_unanswerable_ones_have_none():
    assert set(REFS) == {q["id"] for q in ANSWERABLE}
    for q in V2:
        if q["reference_sql"] is None:
            assert q["category"] == "unanswerable" and not q["alt_sqls"]
        else:
            assert q["category"] != "unanswerable"
            assert all(entry["rows"] for entry in REFS[q["id"]]), q["id"]


def test_the_frozen_first_set_is_not_touched():
    assert len(V1) == 60 and {q["split"] for q in V1} == {"dev", "test"}


@pytest.mark.parametrize("q", ANSWERABLE, ids=[q["id"] for q in ANSWERABLE])
def test_each_reference_and_alternate_passes_strictly(q):
    for entry in REFS[q["id"]]:
        rec = {"run": 0, "rows": entry["rows"], "error_kind": None, "truncated": False}
        res = score.score_answerable(q, rec, REFS[q["id"]])
        assert res["status"] == "pass" and res["strict"], (q["id"], entry["label"])


@pytest.mark.parametrize("q", [q for q in ANSWERABLE if q.get("ordered")], ids=lambda q: q["id"])
def test_ranking_questions_fail_when_the_order_is_reversed(q):
    rows = REFS[q["id"]][0]["rows"]
    if len({tuple(r) for r in rows}) < 2 or len(score.tie_groups(rows)) < 2:
        pytest.skip("nothing to reorder")
    res = score.score_answerable(q, {"run": 0, "rows": rows[::-1], "error_kind": None, "truncated": False}, REFS[q["id"]])
    assert res["status"] == "fail"


def test_decisions_recorded_in_the_questions():
    by_id = {q["id"]: q for q in V2}
    assert "3 most common" in by_id["A027"]["question"] and "top 8" in by_id["A039"]["question"]
    assert REFS["U25"][0]["rows"] == [[22]]  # visible text only; the stored-HTML reading (3) is not an alternate
    assert [[3]] not in [e["rows"] for e in REFS["U25"]]
    assert REFS["U28"][0]["rows"] == [[750]] and REFS["U26"][0]["rows"] == [[11057]] and REFS["U27"][0]["rows"] == [[16802]]
    assert {tuple(map(tuple, e["rows"])) for e in REFS["U06"]} == {((64642,),), ((37767,),)}
    assert by_id["U18"]["reference_sql"] is None and by_id["U18"]["category"] == "unanswerable"


@needs_db
def test_references_rebuild_from_the_sql_exactly():
    rebuilt = score.build_reference_results(V2)
    assert rebuilt == REFS


RELAXED = json.loads((ROOT / "eval" / "relaxed_v2.json").read_text(encoding="utf-8"))


def test_relaxed_questions_are_ranking_questions_without_a_stated_number():
    by_id = {q["id"]: q for q in V2}
    assert set(RELAXED) <= {q["id"] for q in ANSWERABLE}
    for qid in RELAXED:
        text = by_id[qid]["question"].lower()
        assert not re.search(r"(top|first)\s+\d+|\d+\s+(most|best|largest|biggest|highest)", text), qid


def _rec(rows):
    return {"run": 0, "rows": rows, "error_kind": None, "truncated": False}


def test_a_longer_answer_with_matching_first_rows_is_relaxed_only():
    q = next(x for x in V2 if x["id"] == "A015")
    ref = REFS["A015"][0]["rows"]
    longer = _rec(ref + [["extra-tag", 1], ["another-tag", 1]])
    strict = score.score_answerable(q, longer, REFS["A015"])
    relaxed = score.score_answerable(q, longer, REFS["A015"], relaxed=True)
    assert strict["status"] == relaxed["status"] == "fail" and not strict.get("relaxed_pass") and relaxed["relaxed_pass"]
    wrong_start = _rec([["not-a-tag", 1]] + ref[1:] + [["x", 1]])
    assert not score.score_answerable(q, wrong_start, REFS["A015"], relaxed=True).get("relaxed_pass")


def test_the_headline_never_counts_relaxed_passes():
    q = next(x for x in V2 if x["id"] == "A015")
    ref = REFS["A015"][0]["rows"]
    items = [score.score_answerable(q, _rec(ref + [["x", 1]]), REFS["A015"], relaxed=True)]
    s = score.summarize(items)
    assert s["mean_accuracy"] == 0.0 and s["relaxed_mean_accuracy"] == 1.0
