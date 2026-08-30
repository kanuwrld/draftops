from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RedactionPattern:
    label: str
    pattern: str


@dataclass(frozen=True)
class CategoryPolicy:
    keywords: tuple[str, ...]
    default_priority: str
    reply_template: str


@dataclass(frozen=True)
class DraftOpsPolicy:
    version: int
    minimum_confidence: float
    urgent_keywords: tuple[str, ...]
    categories: dict[str, CategoryPolicy]
    custom_redactions: tuple[RedactionPattern, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    subject: str
    body: str
    customer_email: str = ""


@dataclass(frozen=True)
class Classification:
    category: str
    priority: str
    confidence: float
    draft: str
    source: str


@dataclass(frozen=True)
class QueueItem:
    ticket_id: str
    sanitized_subject: str
    sanitized_body: str
    category: str
    priority: str
    confidence: float
    draft_subject: str
    draft_body: str
    source: str
    status: str
    review_reasons: tuple[str, ...]


@dataclass(frozen=True)
class PrivacyItem:
    ticket_id: str
    redactions: dict[str, int]


@dataclass(frozen=True)
class RunArtifacts:
    run_id: str
    created_at: str
    queue: tuple[QueueItem, ...]
    privacy: tuple[PrivacyItem, ...]
    proposals: tuple[dict[str, Any], ...]
