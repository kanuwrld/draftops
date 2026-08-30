from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .pipeline import DraftOpsError


Clock = Callable[[], str]


def record_decision(
    queue_path: str | Path,
    decisions_path: str | Path,
    ticket_id: str,
    decision: str,
    actor: str,
    note: str = "",
    clock: Clock | None = None,
) -> dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise DraftOpsError("decision must be approved or rejected")
    if not actor.strip():
        raise DraftOpsError("decision actor is required")
    queue = load_queue(queue_path)
    if not any(item.get("ticket_id") == ticket_id for item in queue["items"]):
        raise DraftOpsError(f"ticket not found in queue: {ticket_id}")
    existing = load_decisions(decisions_path)
    previous = existing.get(ticket_id)
    if previous:
        if previous["decision"] == decision and previous["actor"] == actor.strip():
            return previous
        raise DraftOpsError(f"ticket already has a final decision: {ticket_id}")
    event = {
        "decision_id": "decision_"
        + hashlib.sha256(f"{queue['run_id']}:{ticket_id}".encode()).hexdigest()[:12],
        "run_id": queue["run_id"],
        "ticket_id": ticket_id,
        "decision": decision,
        "actor": actor.strip(),
        "note": note.strip(),
        "decided_at": (clock or _utc_now)(),
    }
    path = Path(decisions_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def export_approved(
    queue_path: str | Path,
    decisions_path: str | Path,
    output: str | Path,
) -> list[Path]:
    queue = load_queue(queue_path)
    decisions = load_decisions(decisions_path)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for item in queue["items"]:
        ticket_id = item["ticket_id"]
        decision = decisions.get(ticket_id)
        if not decision or decision["decision"] != "approved":
            continue
        envelope = {
            "run_id": queue["run_id"],
            "ticket_id": ticket_id,
            "draft": {
                "subject": item["draft_subject"],
                "body": item["draft_body"],
            },
            "approved_by": decision["actor"],
            "approved_at": decision["decided_at"],
            "delivery_address_included": False,
        }
        path = root / f"{_safe_filename(ticket_id)}.approved.json"
        path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def load_queue(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DraftOpsError(f"cannot read queue: {exc}") from exc
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("run_id"), str)
        or not isinstance(value.get("items"), list)
    ):
        raise DraftOpsError("queue has an invalid format")
    return value


def load_decisions(path: str | Path) -> dict[str, dict[str, Any]]:
    decision_path = Path(path)
    if not decision_path.exists():
        return {}
    decisions: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(decision_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DraftOpsError(f"invalid decision JSON at line {line_number}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("ticket_id"), str):
            raise DraftOpsError(f"invalid decision at line {line_number}")
        ticket_id = value["ticket_id"]
        if ticket_id in decisions:
            raise DraftOpsError(f"duplicate decision for ticket: {ticket_id}")
        decisions[ticket_id] = value
    return decisions


def _safe_filename(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
    return safe[:80] or "ticket"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
