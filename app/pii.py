from __future__ import annotations

import hashlib
import re
from typing import Any

PII_PATTERNS: dict[str, str] = {
    "email": r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])",
    # Covers common Vietnamese mobile/landline formatting, including spaces,
    # dots, dashes and an optional parenthesised area code.
    "phone_vn": (
        r"(?<!\d)(?:"
        r"(?:0|\+84\s?)(?:\(?\d{2,3}\)?)(?:[ .-]?\d){7,8}"
        r")(?!\d)"
    ),
    "cccd": r"\b\d{12}\b",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
}


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in PII_PATTERNS.items():
        safe = re.sub(pattern, f"[REDACTED_{name.upper()}]", safe)
    return safe


def scrub_value(value: Any) -> Any:
    """Recursively scrub strings in structured log values.

    Log payloads often contain nested dictionaries/lists and exception details;
    scrubbing only the first payload level would leave an easy PII escape path.
    The function returns a new structure so callers do not mutate application
    objects that may still be in use.
    """

    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {key: scrub_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_value(item) for item in value)
    return value


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
