import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from draftops.models import Ticket
from draftops.pipeline import DraftOpsError, load_tickets, run_pipeline
from draftops.policy import validate_policy


POLICY = validate_policy(
    {
        "version": 1,
        "minimum_confidence": 0.6,
        "urgent_keywords": ["charged twice"],
        "custom_redactions": [{"label": "order_id", "pattern": r"\bORD-\d{4,}\b"}],
        "categories": {
            "billing": {
                "keywords": ["charged", "invoice", "refund"],
                "default_priority": "high",
                "reply_template": "We will review the billing request for {ticket_id} before any account action.",
            },
            "other": {
                "keywords": [],
                "default_priority": "normal",
                "reply_template": "A specialist will review ticket {ticket_id}.",
            },
        },
    }
)


class PipelineTests(unittest.TestCase):
    def test_rules_pipeline_is_redacted_and_pending(self) -> None:
        artifacts = run_pipeline(
            [
                Ticket(
                    ticket_id="DEMO-1",
                    subject="Charged twice for ORD-10420",
                    body="Call +49 151 23456789 or demo@example.invalid.",
                    customer_email="demo@example.invalid",
                )
            ],
            POLICY,
            clock=lambda: "2026-08-30T12:00:00Z",
        )
        item = artifacts.queue[0]
        serialized = json.dumps(asdict(item))
        self.assertEqual(item.category, "billing")
        self.assertEqual(item.priority, "urgent")
        self.assertEqual(item.status, "pending")
        self.assertNotIn("demo@example.invalid", serialized)
        self.assertNotIn("23456789", serialized)
        self.assertEqual(artifacts.proposals[0]["action"], "support.reply.draft")
        self.assertEqual(artifacts.privacy[0].redactions["EMAIL"], 2)

    def test_recorded_ai_draft_is_sanitized_again(self) -> None:
        artifacts = run_pipeline(
            [Ticket(ticket_id="DEMO-2", subject="Question", body="Hello")],
            POLICY,
            predictions={
                "DEMO-2": {
                    "category": "other",
                    "priority": "normal",
                    "confidence": 0.88,
                    "draft": "Please email agent@example.invalid with ORD-55555.",
                }
            },
        )
        item = artifacts.queue[0]
        self.assertEqual(item.source, "recorded-ai")
        self.assertEqual(item.draft_body, "Please email [EMAIL] with [ORDER_ID].")

    def test_duplicate_ticket_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tickets.jsonl"
            path.write_text(
                '{"id":"same","subject":"a","body":"b"}\n'
                '{"id":"same","subject":"c","body":"d"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DraftOpsError, "duplicate ticket id"):
                load_tickets(path)


if __name__ == "__main__":
    unittest.main()
