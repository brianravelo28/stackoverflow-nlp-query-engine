"""Checks that the numbers written in the README and docs match the code, the evaluation files and the database.

The database checks are skipped when stackoverflow.db is not present; everything else runs without it.
"""
import json
import re
import sqlite3
import sys
from math import sqrt
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import add_indexes  # noqa: E402
import nlp_layer  # noqa: E402
import queries  # noqa: E402

DB = ROOT / "stackoverflow.db"
README = (ROOT / "README.md").read_text(encoding="utf-8")
ARCHITECTURE = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
METHODOLOGY = (ROOT / "docs" / "METHODOLOGY.md").read_text(encoding="utf-8")
SCHEMA_DOC = (ROOT / "docs" / "DATA_SCHEMA.md").read_text(encoding="utf-8")
RESULTS = (ROOT / "eval" / "RESULTS.md").read_text(encoding="utf-8")
def _section(text, start, end):
    return text[text.index(start):text.index(end)]


RESULTS_V2 = _section(RESULTS, "## Second test set results", "## First test set results")
RESULTS_V1 = _section(RESULTS, "## First test set results", "## Tuning on the development questions")
APP = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
EXPORT = (ROOT / "data" / "kaggle_export.py").read_text(encoding="utf-8")


def n(value) -> str:
    return f"{value:,}"


def pct(value) -> str:
    return f"{value * 100:.1f}%"


# ------------------------------------------------------------------ app and code settings
def test_limits_in_the_docs_match_the_code():
    max_questions = int(re.search(r"^MAX_QUESTIONS = (\d+)", APP, re.M).group(1))
    assert f"{max_questions} questions" in README and f"{max_questions} questions" in ARCHITECTURE.replace("12 questions per session", "12 questions")
    assert f"{nlp_layer.DAILY_LIMIT} questions a day" in README
    assert f"{nlp_layer.QUERY_TIMEOUT_S} seconds" in README and f"{nlp_layer.QUERY_TIMEOUT_S}-second" in ARCHITECTURE
    assert f"{n(nlp_layer.MAX_ROWS)} rows" in README


def test_model_name_in_the_readme_is_the_default_model():
    assert nlp_layer.MODEL in README


def test_counts_of_queries_indexes_examples_and_tags():
    assert f"{len(queries.QUERIES)} hand-written" in README and f"the {len(queries.QUERIES)}-query suite" in README
    assert f"{len(add_indexes.INDEXES)} indexes" in README and f"{len(add_indexes.INDEXES)} indexes" in ARCHITECTURE
    pool = re.search(r"EXAMPLE_QUESTIONS = \[(.*?)\n\]", APP, re.S).group(1)
    pool_size = len(re.findall(r'^\s+"', pool, re.M))
    shown = int(re.search(r"^SHOWN = (\d+)", APP, re.M).group(1))
    assert f"{shown} random example questions ({pool_size} in the" in README
    tag_regex = re.search(r'TAG_REGEX = r"\(\^\|\\\|\)\((.*?)\)\(\\\|\|\$\)"', EXPORT).group(1)
    assert f"{len(tag_regex.split('|'))} popular" in README


# ------------------------------------------------------------------ evaluation numbers
@pytest.fixture(scope="module")
def test_run():
    scored = json.loads((ROOT / "eval" / "runs" / "test-1.scored.json").read_text(encoding="utf-8"))
    run = json.loads((ROOT / "eval" / "runs" / "test-1.json").read_text(encoding="utf-8"))
    refs = json.loads((ROOT / "eval" / "reference_results.json").read_text(encoding="utf-8"))
    return scored, run, refs


def test_headline_accuracy_is_the_same_everywhere(test_run):
    """The first set: RESULTS.md has the percentage and interval; the README and METHODOLOGY give counts."""
    summary = test_run[0]["summary"]
    questions, runs = summary["questions"], summary["runs"]
    correct_every_run = summary["consistency"]["always"]
    assert summary["mean_accuracy"] == round(correct_every_run / questions, 4)
    assert pct(summary["mean_accuracy"]) in RESULTS
    assert f"for {correct_every_run} in each of {runs} runs" in RESULTS
    assert f"{questions} answerable test questions" in RESULTS
    low, high = _wilson(correct_every_run, questions)
    assert f"{low * 100:.1f}% to {high * 100:.1f}%" in RESULTS
    assert f"{correct_every_run} of {questions} correct in every run" in README
    assert f"correct for {correct_every_run} in each of the {runs} runs" in METHODOLOGY
    assert f"got {correct_every_run} right in each run" in README


def _wilson(k, size, z=1.96):
    p = k / size
    centre = (p + z * z / (2 * size)) / (1 + z * z / size)
    half = z * sqrt(p * (1 - p) / size + z * z / (4 * size * size)) / (1 + z * z / size)
    return centre - half, centre + half


def test_results_file_details_match_the_scored_run(test_run):
    scored, run, refs = test_run
    summary, items = scored["summary"], scored["items"]
    answerable = [i for i in items if i["category"] != "unanswerable"]
    total_runs = summary["questions"] * summary["runs"]
    passed = [i for i in answerable if i["status"] == "pass"]
    assert f"{round(summary['strict_accuracy'] * total_runs)} of the {total_runs} runs were strict" in RESULTS
    assert f"{n(len(passed))} of {total_runs}" in RESULTS.replace("**", "") or f"{len(passed)} of {total_runs}" in RESULTS.replace("**", "")
    assert f"{summary['pass_kinds']['rounded']} correct runs matched after rounding" in RESULTS
    by_id = {(r["id"], r["run"]): r for r in run["results"]}
    extra = sum(
        len(by_id[(i["id"], i["run"])]["rows"][0])
        > len(next(e for e in refs[i["id"]] if e["label"] == i["matched"])["rows"][0])
        for i in passed
    )
    assert f"{extra} of the {len(passed)} correct runs returned extra columns" in RESULTS
    varied = sum(len({by_id[(q, r)]["sql"] for r in range(summary["runs"])}) > 1 for q in {i["id"] for i in answerable})
    assert f"{varied} of the {summary['questions']} questions" in RESULTS


def test_category_table_in_the_results_file(test_run):
    answerable = [i for i in test_run[0]["items"] if i["category"] != "unanswerable"]
    labels = {"aggregation": "Aggregation", "join": "Join", "absence": "Absence", "date": "Date",
              "window": "Window", "rate": "Rate", "ambiguous": "Ambiguous wording"}
    for category, label in labels.items():
        rows = [i for i in answerable if i["category"] == category]
        row = re.search(rf"^\| {label}[^|]*\| (\d+) \| (\d+) of (\d+) \|$", RESULTS_V1, re.M)
        assert row, label
        assert (int(row.group(1)), int(row.group(2)), int(row.group(3))) == (
            len({i["id"] for i in rows}), sum(i["status"] == "pass" for i in rows), len(rows))


def test_tuning_history_in_the_results_file():
    dev1 = json.loads((ROOT / "eval" / "runs" / "dev-1.scored.json").read_text(encoding="utf-8"))["summary"]
    dev2 = json.loads((ROOT / "eval" / "runs" / "dev-2.scored.json").read_text(encoding="utf-8"))["summary"]
    assert pct(dev1["mean_accuracy"]) in RESULTS and pct(dev1["mean_accuracy"]) in METHODOLOGY
    assert f"| dev-2 | tuned | 30 s | {dev2['mean_accuracy'] * 100:.0f}% |" in RESULTS


def test_question_counts():
    questions = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    dev = [q for q in questions if q["split"] == "dev"]
    test = [q for q in questions if q["split"] == "test"]
    answerable = [q for q in test if q["reference_sql"]]
    assert f"First set:** {len(questions)} questions" in README
    assert "Twenty were used" in README and len(dev) == 20 and len(test) == 40
    assert f"{len(answerable)} answerable" in README and f"{len(test) - len(answerable)} about data" in README
    v2 = json.loads((ROOT / "eval" / "questions_v2.json").read_text(encoding="utf-8"))
    v2_answerable = [q for q in v2 if q["reference_sql"]]
    sentence = f"{len(v2)} questions ({len(v2_answerable)} answerable, {len(v2) - len(v2_answerable)} about data that does not exist)"
    assert sentence in README and sentence in METHODOLOGY
    assert f"{sum(q['written_by'] == 'assistant' for q in v2)} were written by the AI assistant" in README
    assert f"{sum(q['written_by'] == 'owner' for q in v2)} by the author" in README


# ------------------------------------------------------------------ database numbers
needs_db = pytest.mark.skipif(not DB.exists(), reason="stackoverflow.db not present")


@pytest.fixture(scope="module")
def db():
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    yield conn
    conn.close()


@needs_db
def test_row_counts_in_the_readme_and_schema_doc(db):
    counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("users", "tags", "posts_questions", "posts_answers", "post_tags", "comments", "votes")}
    for key, label in (("posts_questions", "questions"), ("posts_answers", "answers"), ("comments", "comments"),
                       ("votes", "votes"), ("users", "users"), ("tags", "tags")):
        assert f"{n(counts[key])} {label}" in README, label
    for table, count in counts.items():
        assert re.search(rf"\| `{table}` \| {re.escape(n(count))} \|", SCHEMA_DOC), table


@needs_db
def test_other_numbers_in_the_schema_doc(db):
    on_questions = db.execute("SELECT COUNT(*) FROM comments WHERE post_id IN (SELECT post_id FROM posts_questions)").fetchone()[0]
    on_answers = db.execute("SELECT COUNT(*) FROM comments WHERE post_id IN (SELECT post_id FROM posts_answers)").fetchone()[0]
    assert f"{n(on_questions)} comments are on questions, {n(on_answers)} on answers" in SCHEMA_DOC
    votes_on_answers = db.execute("SELECT COUNT(*) FROM votes WHERE post_id IN (SELECT post_id FROM posts_answers)").fetchone()[0]
    assert f"{n(votes_on_answers)} of the votes are on answers" in SCHEMA_DOC
    for vote_type, count in db.execute("SELECT vote_type, COUNT(*) FROM votes GROUP BY vote_type"):
        if vote_type in ("UpMod", "AcceptedByOriginator", "DownMod", "Favorite", "16", "11", "15", "10"):
            assert f"`{vote_type}` ({n(count)})" in SCHEMA_DOC, vote_type
    used = db.execute("SELECT COUNT(DISTINCT tag_id) FROM post_tags").fetchone()[0]
    assert f"About {used / 1000:.1f}K distinct tags" in SCHEMA_DOC


@needs_db
def test_redaction_counts_in_the_schema_doc_and_nothing_left_behind(db):
    import redact
    columns = [("posts_questions", "title"), ("posts_questions", "body"), ("posts_answers", "body"), ("comments", "body")]
    counts = {}
    for table, column in columns:
        counts[(table, column)] = db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} LIKE '%[email removed]%' OR {column} LIKE '%[phone removed]%'").fetchone()[0]
    total = sum(counts.values())
    doc = " ".join(SCHEMA_DOC.split())  # ignore line wrapping
    assert f"{n(total)} values contain a replacement" in doc
    assert (f"{counts[('posts_questions', 'title')]} titles, {counts[('posts_questions', 'body')]} question bodies, "
            f"{counts[('posts_answers', 'body')]} answer bodies and {counts[('comments', 'body')]} comments") in doc
    for table, column in columns:  # only a text with an @ can hold an address; check those rows
        for (text,) in db.execute(f"SELECT {column} FROM {table} WHERE {column} LIKE '%@%'"):
            assert redact.redact_text(text) == text, f"{table}.{column} still holds a redactable string"


@needs_db
def test_dates_in_the_docs_match_the_data(db):
    first, last = db.execute("SELECT MIN(date(creation_date)), MAX(date(creation_date)) FROM posts_questions").fetchone()
    assert first == "2020-01-01" and "2020-01-01 to 2022-09-25" in README
    assert last <= "2022-09-25"


# ------------------------------------------------------------------ second test set
@pytest.fixture(scope="module")
def second_set():
    runs = ROOT / "eval" / "runs"
    full = json.loads((runs / "test2-1.scored.json").read_text(encoding="utf-8"))
    base = json.loads((runs / "test2-baseline-schema-only.scored.json").read_text(encoding="utf-8"))
    run = json.loads((runs / "test2-1.json").read_text(encoding="utf-8"))
    refs = json.loads((ROOT / "eval" / "reference_results_v2.json").read_text(encoding="utf-8"))
    return full, base, run, refs


def test_second_set_headline_numbers(second_set):
    full, base, _, _ = second_set
    s, b = full["summary"], base["summary"]
    questions = s["questions"]
    per_run = ", ".join(str(s["per_run_passed"][str(r)]) for r in range(s["runs"]))
    assert f"for {per_run.rsplit(', ', 1)[0]} and {per_run.rsplit(', ', 1)[1]} questions" in RESULTS
    mean = sum(s["per_run_passed"].values()) / (questions * s["runs"])  # from the counts, not the rounded summary
    base_mean = sum(b["per_run_passed"].values()) / (questions * b["runs"])
    assert f"**{pct(mean)} mean accuracy**" in RESULTS
    assert f"On the second test set ({questions} answerable questions)" in RESULTS
    low, high = _wilson(mean * questions, questions)
    assert f"{low * 100:.1f}% to {high * 100:.1f}%" in RESULTS
    blow, bhigh = _wilson(base_mean * questions, questions)
    assert f"answered {round(base_mean * questions)} of {questions} ({pct(base_mean)}, interval {blow * 100:.1f}% to {bhigh * 100:.1f}%)" in RESULTS
    assert s["unanswerable"] == {"pass": 39} and "(39 of 39)" in RESULTS
    for text in (README, METHODOLOGY):
        assert pct(mean) in text and f"{low * 100:.1f}% to {high * 100:.1f}%" in text
        assert f"{per_run.rsplit(', ', 1)[0]} and {per_run.rsplit(', ', 1)[1]}" in text
        assert f"{round(base_mean * questions)} of {questions}" in text
        assert f"{questions} answerable questions" in text
    assert b["unanswerable"] == {"pass": 3, "fail": 10} and "baseline declined 3 of 13" in RESULTS


def test_second_set_category_table(second_set):
    answerable = [i for i in second_set[0]["items"] if i["category"] != "unanswerable"]
    labels = {"aggregation": "Aggregation", "join": "Join", "absence": "Absence", "date": "Date",
              "window": "Window", "rate": "Rate", "ambiguous": "Ambiguous wording"}
    for category, label in labels.items():
        rows = [i for i in answerable if i["category"] == category]
        row = re.search(rf"^\| {label}[^|]*\| (\d+) \| (\d+) of (\d+) \|$", RESULTS_V2, re.M)
        assert row, label
        assert (int(row.group(1)), int(row.group(2)), int(row.group(3))) == (
            len({i["id"] for i in rows}), sum(i["status"] == "pass" for i in rows), len(rows))
    passed = sum(i["status"] == "pass" for i in answerable)
    assert f"**{len({i['id'] for i in answerable})}** | **{passed} of {len(answerable)}**" in RESULTS_V2


def test_second_set_details(second_set):
    full, _, run, refs = second_set
    s, items = full["summary"], full["items"]
    answerable = [i for i in items if i["category"] != "unanswerable"]
    passed = [i for i in answerable if i["status"] == "pass"]
    total = s["questions"] * s["runs"]
    assert f"{round(s['strict_accuracy'] * total)} of the {total} runs were strict" in RESULTS_V2
    assert f"{s['pass_kinds']['rounded']} correct runs matched after rounding" in RESULTS_V2
    by_id = {(r["id"], r["run"]): r for r in run["results"]}
    extra = sum(len(by_id[(i["id"], i["run"])]["rows"][0])
                > len(next(e for e in refs[i["id"]] if e["label"] == i["matched"])["rows"][0]) for i in passed)
    assert f"{extra} of the {len(passed)} correct runs returned extra columns" in RESULTS_V2
    ids = {i["id"] for i in answerable}
    varied = sum(len({by_id[(q, r)]["sql"] for r in range(s["runs"])}) > 1 for q in ids)
    assert f"The SQL differed between runs for {varied} of the {len(ids)} questions" in RESULTS_V2
    assert f"{s['consistency']['always']} were right every time and {s['consistency']['never']} never" in RESULTS_V2
    sometimes = s["consistency"]["sometimes"]
    assert f"The other {sometimes} varied" in RESULTS_V2 and f"{sometimes} of {len(ids)} questions changed outcome" in RESULTS


def test_second_set_author_split_and_relaxed_numbers(second_set):
    full, base, _, _ = second_set
    questions = {q["id"]: q for q in json.loads((ROOT / "eval" / "questions_v2.json").read_text(encoding="utf-8"))}
    answerable = [i for i in full["items"] if i["category"] != "unanswerable"]
    for who in ("assistant", "owner"):
        rows = [i for i in answerable if questions[i["id"]]["written_by"] == who]
        ids = {i["id"] for i in rows}
        k = sum(i["status"] == "pass" for i in rows)
        assert f"{k} of {len(rows)} runs ({k / len(rows) * 100:.1f}%, {len(ids)} questions)" in RESULTS_V2
    def relaxed_mean(scored):  # from the counts, not the rounded summary
        rows = [i for i in scored["items"] if i["category"] != "unanswerable"]
        return sum(i["status"] == "pass" or i.get("relaxed_pass", False) for i in rows) / len(rows)
    assert f"**{pct(relaxed_mean(full))}** for the full prompt" in RESULTS_V2
    assert f"**{pct(relaxed_mean(base))}** for the baseline" in RESULTS_V2
    relaxed = json.loads((ROOT / "eval" / "relaxed_v2.json").read_text(encoding="utf-8"))
    assert f"Seven questions ({', '.join(relaxed)})" in RESULTS_V2 and len(relaxed) == 7
    assert "Of the 126 second-set questions, 90 were written by the AI assistant" in RESULTS and len(questions) == 126
    assert sum(q["written_by"] == "assistant" for q in questions.values()) == 90


def test_dev_3_row_and_the_prompt_hash_in_the_results_file():
    dev3 = json.loads((ROOT / "eval" / "runs" / "dev-3.scored.json").read_text(encoding="utf-8"))["summary"]
    assert f"| dev-3 | tuned, with the `vote_type` note | 30 s | {dev3['mean_accuracy'] * 100:.0f}% |" in RESULTS
    assert dev3["consistency"] == {"always": 18}
    import hashlib
    now = hashlib.sha256(nlp_layer.SYSTEM_PROMPT.encode()).hexdigest()
    assert f"`{now[:8]}…`" in RESULTS
    run = json.loads((ROOT / "eval" / "runs" / "test2-1.json").read_text(encoding="utf-8"))
    assert f"`{run['meta']['prompt_sha256'][:8]}…`" in RESULTS
