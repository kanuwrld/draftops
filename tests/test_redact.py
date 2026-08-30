import unittest

from draftops.models import RedactionPattern
from draftops.redact import redact_text


class RedactionTests(unittest.TestCase):
    def test_redacts_email_phone_and_custom_identifier(self) -> None:
        sanitized, counts = redact_text(
            "Contact alex@example.invalid or +49 151 23456789 about ORD-10420.",
            (RedactionPattern("ORDER_ID", r"\bORD-\d{4,}\b"),),
        )
        self.assertEqual(
            sanitized,
            "Contact [EMAIL] or [PHONE] about [ORDER_ID].",
        )
        self.assertEqual(counts, {"EMAIL": 1, "ORDER_ID": 1, "PHONE": 1})

    def test_report_never_contains_original_values(self) -> None:
        sanitized, counts = redact_text("secret.person@example.invalid")
        self.assertNotIn("secret.person", sanitized)
        self.assertNotIn("secret.person", repr(counts))


if __name__ == "__main__":
    unittest.main()
