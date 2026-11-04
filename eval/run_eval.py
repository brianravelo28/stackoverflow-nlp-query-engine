"""Ask the NLP layer every evaluation question and save what it returned.

Each question goes through the same path as the app: generate_sql, the SQL gate,
the query timeout and the row cap. The run file is rewritten after every call, so
an interrupted run can be continued with --resume. Score it with eval/score.py.

Usage (from the repo root, with ANTHROPIC_API_KEY set):
  python eval/run_eval.py --split dev --runs 3 --label dev-1
  python eval/run_eval.py --split test --runs 3 --label test-1   # refuses to run with uncommitted changes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import nlp_layer  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.json"
RUNS_DIR = ROOT / "eval" / "runs"
DB = ROOT / "stackoverflow.db"
API_ATTEMPTS = 3


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def error_kind(message: str) -> str:
    if "timed out" in message:
        return "timeout"
    return "gate" if message.startswith("Error:") else "sql"


def ask(question: str, conn: sqlite3.Connection) -> dict:
    out = {"sql": None, "error_kind": None, "error": None, "columns": [], "rows": [], "truncated": False}
    for attempt in range(1, API_ATTEMPTS + 1):
        try:
            out["sql"] = nlp_layer.generate_sql(question)
            break
        except nlp_layer.GenerationError as e:
            if attempt == API_ATTEMPTS:
                return {**out, "error_kind": "api", "error": str(e)}
            time.sleep(5 * attempt)
    df, error = nlp_layer.validate_and_execute(out["sql"], conn)
    if error:
        return {**out, "error_kind": error_kind(error), "error": error}
    out["columns"] = [str(c) for c in df.columns]
    out["rows"] = df.astype(object).where(df.notna(), None).values.tolist()
    out["truncated"] = bool(df.attrs.get("truncated"))
    return out


def save(path: Path, run: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(run, indent=1), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", required=True)
    ap.add_argument("--ids", help="comma-separated question ids, to rerun a few")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true", help="test split only: run despite uncommitted changes")
    args = ap.parse_args()

    dirty = bool(git("status", "--porcelain", "--", "src", "eval/questions.json", "eval/score.py"))
    if args.split == "test" and dirty and not args.allow_dirty:
        sys.exit("Refusing a test run with uncommitted changes in src/ or eval/. Commit first so the run records a clean hash.")
    questions = [q for q in json.loads(QUESTIONS.read_text(encoding="utf-8")) if q["split"] == args.split]
    if args.ids:
        wanted = set(args.ids.split(","))
        questions = [q for q in questions if q["id"] in wanted]

    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"{args.label}.json"
    if path.exists() and not args.resume:
        sys.exit(f"{path.relative_to(ROOT)} exists; pick another label or pass --resume")
    run = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "meta": {
            "label": args.label, "split": args.split, "runs": args.runs, "model": nlp_layer.MODEL,
            "prompt_sha256": hashlib.sha256(nlp_layer.SYSTEM_PROMPT.encode()).hexdigest(),
            "git_commit": git("rev-parse", "HEAD"), "uncommitted_changes": dirty,
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "query_timeout_s": nlp_layer.QUERY_TIMEOUT_S, "max_rows": nlp_layer.MAX_ROWS,
        },
        "results": [],
    }
    done = {(r["id"], r["run"]) for r in run["results"]}
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, check_same_thread=False)

    total = len(questions) * args.runs
    for n in range(args.runs):
        for q in questions:
            if (q["id"], n) in done:
                continue
            run["results"].append({"id": q["id"], "run": n, **ask(q["question"], conn)})
            save(path, run)
            last = run["results"][-1]
            status = last["error_kind"] or f"{len(last['rows'])} rows"
            print(f"[{len(run['results'])}/{total}] {q['id']} run {n}: {status}", flush=True)
    run["meta"]["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save(path, run)
    print(f"saved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
