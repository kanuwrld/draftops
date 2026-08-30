from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .artifacts import write_artifacts
from .pipeline import DraftOpsError, load_predictions, load_tickets, run_pipeline
from .policy import PolicyError, load_policy
from .reviews import export_approved, record_decision


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="draftops",
        description="Create privacy-aware, draft-only support review queues.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    process = commands.add_parser("process", help="process ticket JSONL into review artifacts")
    process.add_argument("tickets", type=Path)
    process.add_argument("--policy", required=True, type=Path)
    process.add_argument("--predictions", type=Path, help="recorded AI outputs keyed by ticket id")
    process.add_argument("--out", required=True, type=Path)

    decide = commands.add_parser("decide", help="record one final human decision")
    decide.add_argument("queue", type=Path)
    decide.add_argument("ticket_id")
    choice = decide.add_mutually_exclusive_group(required=True)
    choice.add_argument("--approve", action="store_true")
    choice.add_argument("--reject", action="store_true")
    decide.add_argument("--actor", required=True)
    decide.add_argument("--note", default="")
    decide.add_argument("--decisions", required=True, type=Path)

    export = commands.add_parser("export", help="export approved drafts without delivery addresses")
    export.add_argument("queue", type=Path)
    export.add_argument("--decisions", required=True, type=Path)
    export.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "process":
            artifacts = run_pipeline(
                load_tickets(args.tickets),
                load_policy(args.policy),
                load_predictions(args.predictions),
            )
            write_artifacts(artifacts, args.out)
            print(
                json.dumps(
                    {
                        "run_id": artifacts.run_id,
                        "mode": "draft-only",
                        "tickets": len(artifacts.queue),
                        "output": str(args.out),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "decide":
            event = record_decision(
                args.queue,
                args.decisions,
                args.ticket_id,
                "approved" if args.approve else "rejected",
                args.actor,
                args.note,
            )
            print(json.dumps(event, ensure_ascii=False))
            return 0
        if args.command == "export":
            paths = export_approved(args.queue, args.decisions, args.out)
            print(json.dumps({"approved_exports": len(paths), "output": str(args.out)}))
            return 0
        raise DraftOpsError("unknown command")
    except (DraftOpsError, PolicyError, OSError) as exc:
        print(f"draftops: {exc}", file=sys.stderr)
        return 2
