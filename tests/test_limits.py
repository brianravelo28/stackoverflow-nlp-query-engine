"""Tests for the daily question cap and API-error handling in src/nlp_layer.py."""
import sys
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import nlp_layer  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_counter(monkeypatch):
    monkeypatch.setattr(nlp_layer, "_daily", {"day": None, "count": 0})
    monkeypatch.setattr(nlp_layer, "DAILY_LIMIT", 3)
    monkeypatch.setattr(nlp_layer, "_today", lambda: "2026-10-28")


def test_daily_limit_trips_after_limit_questions():
    for _ in range(3):
        assert not nlp_layer.daily_limit_reached()
        nlp_layer.count_daily_question()
    assert nlp_layer.daily_limit_reached()


def test_daily_limit_resets_on_a_new_day(monkeypatch):
    for _ in range(3):
        nlp_layer.count_daily_question()
    assert nlp_layer.daily_limit_reached()
    monkeypatch.setattr(nlp_layer, "_today", lambda: "2026-10-29")
    assert not nlp_layer.daily_limit_reached()
    nlp_layer.count_daily_question()
    assert nlp_layer._daily["count"] == 1


def _client_raising(exc):
    def create(**kwargs):
        raise exc
    return SimpleNamespace(messages=SimpleNamespace(create=create))


@pytest.mark.parametrize("exc", [
    anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")),
    anthropic.RateLimitError("slow down", response=httpx.Response(429, request=httpx.Request("POST", "https://x")), body=None),
    anthropic.AuthenticationError("bad key sk-secret", response=httpx.Response(401, request=httpx.Request("POST", "https://x")), body=None),
])
def test_api_failures_become_a_safe_message(monkeypatch, exc):
    monkeypatch.setattr(nlp_layer, "get_client", lambda: _client_raising(exc))
    with pytest.raises(nlp_layer.GenerationError) as info:
        nlp_layer.generate_sql("anything")
    assert "unavailable" in str(info.value) and "sk-secret" not in str(info.value)


def test_decline_reason_reads_the_unanswerable_convention():
    import pandas as pd
    assert nlp_layer.decline_reason(pd.DataFrame({"answer": ["UNANSWERABLE: no salary data"]})) == "no salary data"
    assert nlp_layer.decline_reason(pd.DataFrame({"answer": ["a normal text answer"]})) is None
    assert nlp_layer.decline_reason(pd.DataFrame({"a": ["UNANSWERABLE: x"], "b": [1]})) is None
    assert nlp_layer.decline_reason(pd.DataFrame({"answer": ["UNANSWERABLE: x", "y"]})) is None
