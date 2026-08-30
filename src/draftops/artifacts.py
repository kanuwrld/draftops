from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import RunArtifacts


def write_artifacts(artifacts: RunArtifacts, output: str | Path) -> None:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    queue_document = {
        "run_id": artifacts.run_id,
        "created_at": artifacts.created_at,
        "mode": "draft-only",
        "items": [asdict(item) for item in artifacts.queue],
    }
    privacy_document = {
        "run_id": artifacts.run_id,
        "stores_original_values": False,
        "tickets": [asdict(item) for item in artifacts.privacy],
    }
    (root / "queue.json").write_text(
        json.dumps(queue_document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "privacy-report.json").write_text(
        json.dumps(privacy_document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "reviewgate-proposals.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in artifacts.proposals),
        encoding="utf-8",
    )
    (root / "RUN.md").write_text(_render_run(artifacts), encoding="utf-8")


def _render_run(artifacts: RunArtifacts) -> str:
    rows = [
        "# DraftOps review queue",
        "",
        f"Run: `{artifacts.run_id}`  ",
        f"Created: `{artifacts.created_at}`  ",
        "Mode: **draft-only**",
        "",
        "No message has been sent. Every item requires a named human decision.",
        "",
        "| Ticket | Category | Priority | Confidence | Source |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for item in artifacts.queue:
        rows.append(
            f"| `{item.ticket_id}` | {item.category} | {item.priority} | "
            f"{item.confidence:.2f} | {item.source} |"
        )
    total_redactions = sum(sum(item.redactions.values()) for item in artifacts.privacy)
    rows.extend(
        [
            "",
            f"Redactions recorded: **{total_redactions}**. The privacy report stores counts, not original values.",
            "",
        ]
    )
    return "\n".join(rows)
