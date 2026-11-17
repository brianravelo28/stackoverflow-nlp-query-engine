"""Tests for the baseline prompt in eval/run_eval.py (no API key or database needed)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

import nlp_layer  # noqa: E402
import run_eval  # noqa: E402


def test_schema_only_prompt_keeps_the_schema_and_drops_the_rest():
    baseline = run_eval.schema_only_prompt()
    assert "SCHEMA:" in baseline and "posts_questions(" in baseline and "Respond ONLY with a valid SQLite SELECT" in baseline
    for removed in ("NOTES:", "EXAMPLES:", "CONSTRAINTS:", "UNANSWERABLE", "2022-09-25", "parent_id references"):
        assert removed not in baseline


def test_schema_only_prompt_is_a_prefix_of_the_full_prompt():
    assert nlp_layer.SYSTEM_PROMPT.startswith(run_eval.schema_only_prompt().rstrip())


def test_full_prompt_says_what_vote_type_holds_and_the_baseline_does_not():
    for value in ("'UpMod'", "'DownMod'", "'Favorite'", "'BountyStart'", "not numbers"):
        assert value in nlp_layer.SYSTEM_PROMPT
        assert value not in run_eval.schema_only_prompt()
