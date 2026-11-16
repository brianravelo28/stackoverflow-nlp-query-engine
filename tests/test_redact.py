"""Tests for the email and phone redaction in src/redact.py."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from redact import EMAIL_TOKEN, PHONE_TOKEN, redact_series, redact_text  # noqa: E402


@pytest.mark.parametrize("text, expected", [
    ("write to jane.doe+so@gmail.com today", f"write to {EMAIL_TOKEN} today"),
    ("a@b.co and c_d@e-f.example.org", f"{EMAIL_TOKEN} and {EMAIL_TOKEN}"),
    ("mailto:someone@example.com.", f"mailto:{EMAIL_TOKEN}."),
    ("author_email='me@host.io',", f"author_email='{EMAIL_TOKEN}',"),
])
def test_emails_are_replaced(text, expected):
    assert redact_text(text) == expected


@pytest.mark.parametrize("text", [
    "git clone git@github.com:user/repo.git",
    "git@gitlab.com:group/project.git",
    "@Override public void run()",
    "import '@angular/core'",
    "npm install @types/node",
    "decorator @app.route('/')",
    "user@localhost has no top-level domain",
    "no address here",
])
def test_non_addresses_are_kept(text):
    assert redact_text(text) == text


@pytest.mark.parametrize("text, expected", [
    ("call 555-123-4567 now", f"call {PHONE_TOKEN} now"),
    ("(555) 123 4567", f"{PHONE_TOKEN}"),
    ("+1 555.123.4567 or 555 123 4567", f"{PHONE_TOKEN} or {PHONE_TOKEN}"),
])
def test_phone_numbers_are_replaced(text, expected):
    assert redact_text(text) == expected


@pytest.mark.parametrize("text", [
    "created 2021-03-15 14:11:59",
    "version 1.2.3 and build 20210315",
    "ip 192.168.100.1 and port 8080",
    "id 1234567890123",
    "a 12-34-56 style code",
])
def test_other_numbers_are_kept(text):
    assert redact_text(text) == text


def test_series_counts_changed_values_and_keeps_missing():
    values = pd.Series(["plain", "mail me@x.com", None, "555-123-4567", "me@x.com 555-123-4567"])
    cleaned, changed = redact_series(values)
    assert changed == 3
    assert cleaned.iloc[0] == "plain" and pd.isna(cleaned.iloc[2])
    assert cleaned.iloc[4] == f"{EMAIL_TOKEN} {PHONE_TOKEN}"
    assert values.iloc[1] == "mail me@x.com"  # the input is not modified
