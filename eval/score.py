"""Score a run of the NLP layer against the reference answers (execution match).

A prediction passes when it returns the same rows as the reference, whatever the SQL
looks like. Rules (names of columns are never compared):
  - every reference column must appear in the prediction; extra columns are allowed
    (the strict score counts only the same columns in the same order)
  - row order matters only for ranking questions (reference SQL ends in LIMIT n, n > 1)
  - numbers match within 1e-6, or after rounding the reference to 0-6 decimals when the
    rounded value stays within 2% of it; whole-number references must match exactly
  - rate questions also accept the value times 100 (or divided by 100)
  - month and weekday questions accept names, numbers and 'YYYY-MM' interchangeably
  - alternate reference answers are listed in questions.json; any one may match
  - the unanswerable questions are scored apart and left out of the headline

Input is a run file written by eval/run_eval.py:
  {"meta": {...}, "results": [{"id", "run", "sql", "error_kind", "error", "columns", "rows", "truncated"}]}
error_kind is null, "api", "gate", "timeout" or "sql".

Usage (from the repo root):
  python eval/score.py --build-refs          # run the reference SQL once, save eval/reference_results.json
  python eval/score.py eval/runs/NAME.json   # score a run (add --split dev|test)
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "questions.json"
REFERENCE_RESULTS = ROOT / "eval" / "reference_results.json"
DB = ROOT / "stackoverflow.db"

# Scorer-side settings, keyed by question id so questions.json stays untouched.
PERCENT_IDS = {"D12", "D13", "T17", "T22", "T26", "T27", "T29", "T30", "T31"}
MONTH_IDS = {"T23": False, "D10": True, "D15": True}  # id -> also accept 'YYYY-MM'
WEEKDAY_IDS = {"T38"}
MAX_MAPPINGS = 200

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]  # SQLite %w: 0 = Sunday


# ------------------------------------------------------------------ cells
def _text(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip()).casefold()
    return re.sub(r"^(\d{4}-\d{2}-\d{2})[ t]00:00:00(\.0+)?$", r"\1", s)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _name_index(s: str, names: list[str]) -> int | None:
    s = s.rstrip(".")
    for i, n in enumerate(names):
        if s == n or s == n[:3]:
            return i
    return None


def canon_month(v, allow_ym: bool) -> int | None:
    if _is_num(v):
        return int(v) if float(v).is_integer() and 1 <= v <= 12 else None
    if not isinstance(v, str):
        return None
    s = _text(v)
    m = re.fullmatch(r"\d{4}-(\d{2})", s)
    if m:
        return int(m.group(1)) if allow_ym and 1 <= int(m.group(1)) <= 12 else None
    if re.fullmatch(r"\d{1,2}", s):
        return int(s) if 1 <= int(s) <= 12 else None
    i = _name_index(s, MONTHS)
    return None if i is None else i + 1


def canon_weekday(v) -> int | None:
    if _is_num(v):
        return int(v) if float(v).is_integer() and 0 <= v <= 6 else None
    if not isinstance(v, str):
        return None
    s = _text(v)
    if re.fullmatch(r"[0-6]", s):
        return int(s)
    return _name_index(s, WEEKDAYS)


def _close(r: float, g: float) -> bool:
    if r.is_integer() and g.is_integer():  # counts and ids must match exactly
        return r == g
    return math.isclose(r, g, rel_tol=1e-6, abs_tol=1e-9)


def _rounded(r: float, g: float) -> bool:
    """g is r rounded to some number of decimals, without losing more than 2% of r."""
    if r == 0 or r.is_integer() or abs(g - r) / abs(r) > 0.02:
        return False
    return any(abs(round(r, d) - g) <= 1e-9 * max(1.0, abs(g)) for d in range(7))


class Spec:
    def __init__(self, q: dict):
        self.percent = q["id"] in PERCENT_IDS
        self.month_ym = MONTH_IDS.get(q["id"])  # None: no month handling
        self.weekday = q["id"] in WEEKDAY_IDS
        m = re.search(r"\bLIMIT\s+(\d+)\s*$", q["reference_sql"] or "", re.I)
        self.ordered = bool(m and int(m.group(1)) > 1)


def cell_kind(ref, got, spec: Spec) -> str | None:
    """How `got` matches `ref`: 'exact', 'rounded', 'percent', 'month', 'weekday', or None."""
    if ref is None or got is None:
        return "exact" if ref is None and got is None else None
    if _is_num(ref) and _is_num(got):
        r, g = float(ref), float(got)
        if _close(r, g):
            return "exact"
        if _rounded(r, g):
            return "rounded"
        if spec.percent and any(_close(r * f, g) or _rounded(r * f, g) for f in (100.0, 0.01)):
            return "percent"
        return None
    if isinstance(ref, str) and isinstance(got, str) and _text(ref) == _text(got):
        return "exact"
    if spec.month_ym is not None:
        a, b = canon_month(ref, spec.month_ym), canon_month(got, spec.month_ym)
        if a is not None and a == b:
            return "month"
    if spec.weekday:
        a, b = canon_weekday(ref), canon_weekday(got)
        if a is not None and a == b:
            return "weekday"
    return None


# ------------------------------------------------------------------ tables
def _rows_match(ref_rows, got_rows, spec: Spec) -> set[str] | None:
    """Kinds used when every ref row matches a got row (same position if ordered), else None."""
    kinds: set[str] = set()

    def row_kinds(a, b):
        out = [cell_kind(x, y, spec) for x, y in zip(a, b)]
        return None if None in out else out

    if spec.ordered:
        for a, b in zip(ref_rows, got_rows):
            k = row_kinds(a, b)
            if k is None:
                return None
            kinds.update(k)
        return kinds
    free = list(range(len(got_rows)))
    for a in ref_rows:
        for j in free:
            k = row_kinds(a, got_rows[j])
            if k is not None:
                kinds.update(k)
                free.remove(j)
                break
        else:
            return None
    return kinds


def compare(ref_rows, got_rows, spec: Spec) -> dict:
    """Match one reference table against a prediction. Returns {passed, reason, kinds, strict}."""
    k = len(ref_rows[0]) if ref_rows else 0
    m = len(got_rows[0]) if got_rows else 0
    if not got_rows:
        return {"passed": False, "reason": "empty_result"}
    if len(got_rows) != len(ref_rows):
        return {"passed": False, "reason": "row_count", "detail": f"got {len(got_rows)} rows, expected {len(ref_rows)}"}
    if m < k:
        return {"passed": False, "reason": "too_few_columns", "detail": f"got {m} columns, expected {k}"}

    def column(rows, j):
        return [(r[j],) for r in rows]

    candidates = []
    for j in range(k):
        ok = [i for i in range(m) if _rows_match(column(ref_rows, j), column(got_rows, i), spec) is not None]
        if not ok:
            return {"passed": False, "reason": "wrong_values", "detail": f"no returned column matches reference column {j + 1}"}
        candidates.append(ok)
    for n, mapping in enumerate(itertools.product(*candidates)):
        if n >= MAX_MAPPINGS:
            break
        if len(set(mapping)) < k:
            continue
        kinds = _rows_match(ref_rows, [tuple(r[i] for i in mapping) for r in got_rows], spec)
        if kinds is not None:
            strict = m == k and list(mapping) == list(range(k)) and kinds <= {"exact"}
            return {"passed": True, "kinds": sorted(kinds), "strict": strict}
    return {"passed": False, "reason": "wrong_values", "detail": "columns match one by one but not as rows"}


# ------------------------------------------------------------------ one prediction
ERROR_REASON = {"api": "api_error", "gate": "gate_blocked", "timeout": "timeout", "sql": "sql_error"}


def score_answerable(q: dict, rec: dict, refs: list[dict]) -> dict:
    out = {"id": q["id"], "split": q["split"], "category": q["category"], "run": rec.get("run", 0)}
    if rec.get("error_kind"):
        return {**out, "status": "fail", "reason": ERROR_REASON.get(rec["error_kind"], "sql_error"),
                "detail": (rec.get("error") or "")[:200]}
    got = [tuple(r) for r in rec["rows"]]
    spec = Spec(q)
    best = None
    for ref in refs:
        res = compare([tuple(r) for r in ref["rows"]], got, spec)
        if res["passed"]:
            return {**out, "status": "pass", "matched": ref["label"], "kinds": res["kinds"], "strict": res["strict"]}
        best = best or res
    if rec.get("truncated"):
        best = {"reason": "truncated_by_cap", **{k: v for k, v in best.items() if k != "reason"}}
    return {**out, "status": "fail", "reason": best["reason"], "detail": best.get("detail", "")}


def score_unanswerable(q: dict, rec: dict, user_names: set[str] | None = None) -> dict:
    """pass: declined (error or no data); fail: substituted another column or named voters; review: needs a person."""
    out = {"id": q["id"], "split": q["split"], "category": q["category"], "run": rec.get("run", 0)}
    if rec.get("error_kind") == "api":
        return {**out, "status": "fail", "reason": "api_error", "detail": (rec.get("error") or "")[:200]}
    rows = rec.get("rows") or []
    if rec.get("error_kind") or not rows or all(v is None for r in rows for v in r):
        return {**out, "status": "pass", "reason": "declined"}
    if q["id"] in ("D19", "T39"):
        names = user_names or set()
        for j in range(len(rows[0])):
            vals = [r[j] for r in rows if isinstance(r[j], str)]
            if vals and sum(v in names for v in vals) * 2 >= len(vals):
                return {**out, "status": "fail", "reason": "named_users"}
        return {**out, "status": "review", "reason": "returned_rows"}
    return {**out, "status": "fail", "reason": "substituted_data"}


# ------------------------------------------------------------------ whole run
def load_reference_results(questions: list[dict]) -> dict[str, list[dict]]:
    """{question id: [{label, rows}]} for the reference and each alternate."""
    if REFERENCE_RESULTS.exists():
        return json.loads(REFERENCE_RESULTS.read_text(encoding="utf-8"))
    return build_reference_results(questions)


def build_reference_results(questions: list[dict]) -> dict[str, list[dict]]:
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    out = {}
    for q in questions:
        if q["reference_sql"] is None:
            continue
        sqls = [("reference", q["reference_sql"])] + [(f"alt {i + 1}", s) for i, s in enumerate(q["alt_sqls"])]
        out[q["id"]] = [{"label": label, "rows": [list(r) for r in conn.execute(sql).fetchall()]} for label, sql in sqls]
    return out


def score_run(run: dict, questions: list[dict], refs: dict, split: str | None = None, user_names=None) -> list[dict]:
    by_id = {q["id"]: q for q in questions}
    items = []
    for rec in run["results"]:
        q = by_id[rec["id"]]
        if split and q["split"] != split:
            continue
        if q["reference_sql"] is None:
            items.append(score_unanswerable(q, rec, user_names))
        else:
            items.append(score_answerable(q, rec, refs[q["id"]]))
    return items


def summarize(items: list[dict]) -> dict:
    ans = [i for i in items if i["category"] != "unanswerable"]
    runs = sorted({i["run"] for i in ans})
    per_run = {r: sum(i["status"] == "pass" for i in ans if i["run"] == r) for r in runs}
    ids = sorted({i["id"] for i in ans})
    n_q = len(ids)
    consistency = Counter()
    for qid in ids:
        passes = [i["status"] == "pass" for i in ans if i["id"] == qid]
        consistency["always" if all(passes) else "never" if not any(passes) else "sometimes"] += 1
    by_cat = defaultdict(lambda: [0, 0])
    for i in ans:
        by_cat[i["category"]][1] += 1
        by_cat[i["category"]][0] += i["status"] == "pass"
    passed = [i for i in ans if i["status"] == "pass"]
    unans = [i for i in items if i["category"] == "unanswerable"]
    return {
        "questions": n_q, "runs": len(runs),
        "per_run_passed": per_run,
        "accuracy_by_run": {r: round(p / n_q, 4) for r, p in per_run.items()} if n_q else {},
        "mean_accuracy": round(sum(per_run.values()) / (n_q * len(runs)), 4) if n_q and runs else None,
        "strict_accuracy": round(sum(i["strict"] for i in passed) / (n_q * len(runs)), 4) if n_q and runs else None,
        "consistency": dict(consistency),
        "by_category": {c: f"{p}/{t}" for c, (p, t) in sorted(by_cat.items())},
        "pass_kinds": dict(Counter(k for i in passed for k in i["kinds"] if k != "exact")),
        "failure_reasons": dict(Counter(i["reason"] for i in ans if i["status"] == "fail")),
        "unanswerable": dict(Counter(i["status"] for i in unans)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_file", nargs="?")
    ap.add_argument("--split", choices=["dev", "test"])
    ap.add_argument("--build-refs", action="store_true")
    ap.add_argument("--details", action="store_true", help="print every failing item")
    ap.add_argument("--out", help="write per-item verdicts and the summary here as JSON")
    args = ap.parse_args()
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if args.build_refs:
        refs = build_reference_results(questions)
        REFERENCE_RESULTS.write_text(json.dumps(refs, indent=1), encoding="utf-8")
        print(f"wrote {REFERENCE_RESULTS.relative_to(ROOT)}: {len(refs)} questions")
        return
    if not args.run_file:
        ap.error("give a run file or --build-refs")
    run = json.loads(Path(args.run_file).read_text(encoding="utf-8"))
    user_names = None
    if DB.exists():
        conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
        user_names = {r[0] for r in conn.execute("SELECT display_name FROM users")}
    items = score_run(run, questions, load_reference_results(questions), args.split, user_names)
    summary = summarize(items)
    print(json.dumps(summary, indent=2))
    if args.details:
        for i in items:
            if i["status"] != "pass":
                print(f"{i['id']} run {i['run']}: {i['status']} {i.get('reason', '')} {i.get('detail', '')}")
    if args.out:
        Path(args.out).write_text(json.dumps({"meta": run.get("meta"), "summary": summary, "items": items}, indent=1),
                                  encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
