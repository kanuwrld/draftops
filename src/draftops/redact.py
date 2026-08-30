from __future__ import annotations

import re
from collections import Counter

from .models import RedactionPattern


BUILT_IN_PATTERNS = (
    RedactionPattern(
        "EMAIL",
        r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w-])",
    ),
    RedactionPattern(
        "PHONE",
        r"(?<!\w)(?:\+?\d[\d .()/-]{6,}\d)(?!\w)",
    ),
)


def redact_text(
    text: str,
    custom_patterns: tuple[RedactionPattern, ...] = (),
) -> tuple[str, dict[str, int]]:
    sanitized = text
    counts: Counter[str] = Counter()
    for item in (*BUILT_IN_PATTERNS, *custom_patterns):
        regex = re.compile(item.pattern, re.IGNORECASE)

        def replace(_: re.Match[str]) -> str:
            counts[item.label] += 1
            return f"[{item.label}]"

        sanitized = regex.sub(replace, sanitized)
    return sanitized, dict(sorted(counts.items()))


def merge_counts(*items: dict[str, int]) -> dict[str, int]:
    total: Counter[str] = Counter()
    for item in items:
        total.update(item)
    return dict(sorted(total.items()))
