from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .models import (
    Classification,
    DraftOpsPolicy,
    PrivacyItem,
    QueueItem,
    RunArtifacts,
    Ticket,
)
from .redact import merge_counts, redact_text


class DraftOpsError(ValueError):
    pass


Clock = Callable[[], str]


def load_tickets(path: str | Path) -> list[Ticket]:
    input_path = Path(path)
    try:
        lines = input_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DraftOpsError(f"cannot read tickets {input_path}: {exc}") from exc
    tickets: list[Ticket] = []
    seen: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DraftOpsError(f"invalid JSON on ticket line {line_number}: {exc.msg}") from exc
        ticket = _parse_ticket(value, line_number)
        if ticket.ticket_id in seen:
            raise DraftOpsError(f"duplicate ticket id: {ticket.ticket_id}")
        seen.add(ticket.ticket_id)
        tickets.append(ticket)
    if not tickets:
        raise DraftOpsError("ticket input is empty")
    return tickets


def load_predictions(path: str | Path | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    prediction_path = Path(path)
    try:
        value = json.loads(prediction_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DraftOpsError(f"cannot read predictions {prediction_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DraftOpsError(f"invalid predictions JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise DraftOpsError("predictions must be an object keyed by ticket id")
    return value


def run_pipeline(
    tickets: Iterable[Ticket],
    policy: DraftOpsPolicy,
    predictions: Mapping[str, Any] | None = None,
    clock: Clock | None = None,
) -> RunArtifacts:
    prediction_map = predictions or {}
    created_at = (clock or _utc_now)()
    queue: list[QueueItem] = []
    privacy: list[PrivacyItem] = []

    for ticket in tickets:
        sanitized_subject, subject_counts = redact_text(ticket.subject, policy.custom_redactions)
        sanitized_body, body_counts = redact_text(ticket.body, policy.custom_redactions)
        _, email_counts = redact_text(ticket.customer_email, policy.custom_redactions)
        counts = merge_counts(subject_counts, body_counts, email_counts)

        if ticket.ticket_id in prediction_map:
            classification = _parse_prediction(
                ticket.ticket_id,
                prediction_map[ticket.ticket_id],
                policy,
            )
        else:
            classification = _classify_with_rules(
                ticket,
                sanitized_subject,
                sanitized_body,
                policy,
            )

        sanitized_draft, draft_counts = redact_text(classification.draft, policy.custom_redactions)
        counts = merge_counts(counts, draft_counts)
        reasons = ["all outbound drafts require human review"]
        if classification.confidence < policy.minimum_confidence:
            reasons.append("confidence is below policy threshold")
        if classification.priority in {"high", "urgent"}:
            reasons.append(f"{classification.priority}-priority ticket")
        if counts:
            reasons.append("personal or policy-defined data was redacted")

        queue.append(
            QueueItem(
                ticket_id=ticket.ticket_id,
                sanitized_subject=sanitized_subject,
                sanitized_body=sanitized_body,
                category=classification.category,
                priority=classification.priority,
                confidence=classification.confidence,
                draft_subject=f"Re: ticket {ticket.ticket_id}",
                draft_body=sanitized_draft,
                source=classification.source,
                status="pending",
                review_reasons=tuple(reasons),
            )
        )
        privacy.append(PrivacyItem(ticket_id=ticket.ticket_id, redactions=counts))

    run_id = _run_id(queue)
    proposals = tuple(_reviewgate_proposal(run_id, item) for item in queue)
    return RunArtifacts(
        run_id=run_id,
        created_at=created_at,
        queue=tuple(queue),
        privacy=tuple(privacy),
        proposals=proposals,
    )


def _parse_ticket(value: Any, line_number: int) -> Ticket:
    if not isinstance(value, dict):
        raise DraftOpsError(f"ticket line {line_number} must be an object")
    ticket_id = value.get("id")
    subject = value.get("subject")
    body = value.get("body")
    email = value.get("customer_email", "")
    if not isinstance(ticket_id, str) or not ticket_id.strip():
        raise DraftOpsError(f"ticket line {line_number} requires a non-empty id")
    if not isinstance(subject, str) or not isinstance(body, str):
        raise DraftOpsError(f"ticket {ticket_id} subject and body must be strings")
    if not isinstance(email, str):
        raise DraftOpsError(f"ticket {ticket_id} customer_email must be a string")
    return Ticket(ticket_id=ticket_id, subject=subject, body=body, customer_email=email)


def _classify_with_rules(
    ticket: Ticket,
    subject: str,
    body: str,
    policy: DraftOpsPolicy,
) -> Classification:
    text = f"{subject}\n{body}".casefold()
    scores: Counter[str] = Counter()
    for category, category_policy in policy.categories.items():
        if category == "other":
            continue
        scores[category] = sum(text.count(keyword) for keyword in category_policy.keywords)
    category, score = max(scores.items(), key=lambda item: (item[1], item[0]), default=("other", 0))
    if score == 0:
        category = "other"
    category_policy = policy.categories[category]
    urgent = any(keyword in text for keyword in policy.urgent_keywords)
    priority = "urgent" if urgent else category_policy.default_priority
    confidence = 0.35 if score == 0 else min(0.95, 0.55 + (score - 1) * 0.1)
    return Classification(
        category=category,
        priority=priority,
        confidence=round(confidence, 2),
        draft=category_policy.reply_template.format(ticket_id=ticket.ticket_id),
        source="rules",
    )


def _parse_prediction(
    ticket_id: str,
    value: Any,
    policy: DraftOpsPolicy,
) -> Classification:
    if not isinstance(value, dict):
        raise DraftOpsError(f"prediction {ticket_id} must be an object")
    category = value.get("category")
    priority = value.get("priority")
    confidence = value.get("confidence")
    draft = value.get("draft")
    if category not in policy.categories:
        raise DraftOpsError(f"prediction {ticket_id} has an unknown category")
    if priority not in {"low", "normal", "high", "urgent"}:
        raise DraftOpsError(f"prediction {ticket_id} has an invalid priority")
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 1
    ):
        raise DraftOpsError(f"prediction {ticket_id} confidence must be between 0 and 1")
    if not isinstance(draft, str) or not draft.strip():
        raise DraftOpsError(f"prediction {ticket_id} draft must be a non-empty string")
    return Classification(
        category=category,
        priority=priority,
        confidence=round(float(confidence), 4),
        draft=draft,
        source="recorded-ai",
    )


def _run_id(queue: list[QueueItem]) -> str:
    safe_fingerprint = [
        {
            "ticket_id": item.ticket_id,
            "category": item.category,
            "priority": item.priority,
            "draft": item.draft_body,
        }
        for item in queue
    ]
    encoded = json.dumps(safe_fingerprint, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return f"run_{hashlib.sha256(encoded).hexdigest()[:12]}"


def _reviewgate_proposal(run_id: str, item: QueueItem) -> dict[str, Any]:
    return {
        "action": "support.reply.draft",
        "target": f"ticket:{item.ticket_id}",
        "payload": {
            "subject": item.draft_subject,
            "body": item.draft_body,
            "metadata": {
                "category": item.category,
                "priority": item.priority,
                "confidence": item.confidence,
                "source": item.source,
            },
        },
        "idempotencyKey": f"{run_id}:{item.ticket_id}:draft-v1",
        "requestedBy": "draftops",
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
