from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import CategoryPolicy, DraftOpsPolicy, RedactionPattern


class PolicyError(ValueError):
    pass


PRIORITIES = {"low", "normal", "high", "urgent"}


def load_policy(path: str | Path) -> DraftOpsPolicy:
    policy_path = Path(path)
    try:
        value = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PolicyError(f"cannot read policy {policy_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(
            f"invalid policy JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return validate_policy(value)


def validate_policy(value: Any) -> DraftOpsPolicy:
    if not isinstance(value, dict) or not isinstance(value.get("version"), int):
        raise PolicyError("policy requires an integer version")
    confidence = value.get("minimum_confidence", 0.6)
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        raise PolicyError("minimum_confidence must be between 0 and 1")

    urgent_keywords = value.get("urgent_keywords", [])
    if not _string_list(urgent_keywords):
        raise PolicyError("urgent_keywords must be a string array")

    raw_categories = value.get("categories")
    if not isinstance(raw_categories, dict) or not raw_categories:
        raise PolicyError("categories must be a non-empty object")
    categories: dict[str, CategoryPolicy] = {}
    for name, raw in raw_categories.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(raw, dict):
            raise PolicyError("each category must have a non-empty name and object policy")
        keywords = raw.get("keywords", [])
        priority = raw.get("default_priority")
        template = raw.get("reply_template")
        if not _string_list(keywords):
            raise PolicyError(f"category {name}.keywords must be a string array")
        if priority not in PRIORITIES:
            raise PolicyError(f"category {name}.default_priority is invalid")
        if not isinstance(template, str) or not template.strip():
            raise PolicyError(f"category {name}.reply_template must be a non-empty string")
        try:
            template.format(ticket_id="DEMO")
        except (KeyError, ValueError) as exc:
            raise PolicyError(
                f"category {name}.reply_template may use only {{ticket_id}}: {exc}"
            ) from exc
        categories[name] = CategoryPolicy(
            keywords=tuple(item.casefold() for item in keywords),
            default_priority=priority,
            reply_template=template,
        )
    if "other" not in categories:
        raise PolicyError("categories must include an 'other' fallback")

    raw_redactions = value.get("custom_redactions", [])
    if not isinstance(raw_redactions, list):
        raise PolicyError("custom_redactions must be an array")
    redactions: list[RedactionPattern] = []
    seen_labels: set[str] = set()
    for index, raw in enumerate(raw_redactions):
        if not isinstance(raw, dict):
            raise PolicyError(f"custom_redactions[{index}] must be an object")
        label = raw.get("label")
        pattern = raw.get("pattern")
        if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", label):
            raise PolicyError(f"custom_redactions[{index}].label is invalid")
        if label.casefold() in seen_labels:
            raise PolicyError(f"duplicate custom redaction label: {label}")
        if not isinstance(pattern, str):
            raise PolicyError(f"custom_redactions[{index}].pattern must be a string")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise PolicyError(f"invalid redaction regex {label}: {exc}") from exc
        seen_labels.add(label.casefold())
        redactions.append(RedactionPattern(label=label.upper(), pattern=pattern))

    return DraftOpsPolicy(
        version=value["version"],
        minimum_confidence=float(confidence),
        urgent_keywords=tuple(item.casefold() for item in urgent_keywords),
        categories=categories,
        custom_redactions=tuple(redactions),
    )


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)
