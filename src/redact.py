"""Replace email-like and phone-like strings in post and comment text.

build_db.py applies this to the text columns before they reach the database, so the published
database holds no addresses or phone numbers from the source text. SSH-style git addresses
(git@github.com) are kept: they name a service, not a person.
"""
from __future__ import annotations

import re

import pandas as pd

EMAIL_TOKEN = "[email removed]"
PHONE_TOKEN = "[phone removed]"

# The lookbehind makes a match start at the beginning of the local part; the lookahead keeps git@host.
EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])(?!git@)[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 3-3-4 digit groups joined by spaces, dots or dashes, with an optional country code and parentheses.
PHONE = re.compile(r"(?<![\d.])(?:\+?\d{1,2}[ .-])?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?![\d.]*\d)")


def redact_text(text: str) -> str:
    return PHONE.sub(PHONE_TOKEN, EMAIL.sub(EMAIL_TOKEN, text))


def redact_series(values: pd.Series) -> tuple[pd.Series, int]:
    """Redacted copy of a text column and the number of values that changed. Missing values stay missing."""
    cleaned = values.map(lambda v: redact_text(v) if isinstance(v, str) else v)
    changed = int(sum(isinstance(a, str) and a != b for a, b in zip(values, cleaned)))
    return cleaned, changed
