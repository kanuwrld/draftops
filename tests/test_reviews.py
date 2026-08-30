import json
import tempfile
import unittest
from pathlib import Path

from draftops.pipeline import DraftOpsError
from draftops.reviews import export_approved, record_decision


class ReviewTests(unittest.TestCase):
    def test_records_one_decision_and_exports_only_approved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = root / "queue.json"
            decisions = root / "decisions.jsonl"
            queue.write_text(
                json.dumps(
                    {
                        "run_id": "run_demo",
                        "items": [
                            {
                                "ticket_id": "DEMO-3",
                                "draft_subject": "Re: DEMO-3",
                                "draft_body": "Fictional approved draft",
                            },
                            {
                                "ticket_id": "DEMO-4",
                                "draft_subject": "Re: DEMO-4",
                                "draft_body": "Fictional pending draft",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            event = record_decision(
                queue,
                decisions,
                "DEMO-3",
                "approved",
                "reviewer@example.invalid",
                clock=lambda: "2026-08-30T12:00:00Z",
            )
            repeated = record_decision(
                queue,
                decisions,
                "DEMO-3",
                "approved",
                "reviewer@example.invalid",
            )
            self.assertEqual(repeated, event)
            paths = export_approved(queue, decisions, root / "approved")
            self.assertEqual(len(paths), 1)
            exported = json.loads(paths[0].read_text())
            self.assertFalse(exported["delivery_address_included"])
            with self.assertRaisesRegex(DraftOpsError, "final decision"):
                record_decision(queue, decisions, "DEMO-3", "rejected", "other")


if __name__ == "__main__":
    unittest.main()
