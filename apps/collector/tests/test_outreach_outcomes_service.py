from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal

from goofish_insight.application.services.outreach_outcomes import (
    OutreachOutcomeError,
    apply_outreach_outcome,
    serialize_outreach_outcome,
)
from goofish_insight.compat import UTC
from goofish_insight.models import OutreachRecord


class OutreachOutcomeServiceTests(unittest.TestCase):
    def test_apply_outreach_outcome_records_closed_deal(self) -> None:
        row = OutreachRecord(
            id=1,
            item_id="xianyu-1",
            message_text="收吗",
            status="sent",
        )
        closed_at = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)

        apply_outreach_outcome(
            row,
            outcome_status="deal",
            deal_price="3200",
            operator_note="seller accepted",
            closed_at=closed_at,
        )

        self.assertEqual(row.outcome_status, "deal")
        self.assertEqual(row.deal_price, Decimal("3200.00"))
        self.assertEqual(row.closed_at, closed_at)
        self.assertEqual(row.operator_note, "seller accepted")
        serialized = serialize_outreach_outcome(row)
        self.assertEqual(serialized["dealPrice"], "3200.00")

    def test_apply_outreach_outcome_requires_status_and_valid_price(self) -> None:
        row = OutreachRecord(
            id=1,
            item_id="xianyu-1",
            message_text="收吗",
            status="sent",
        )

        with self.assertRaises(OutreachOutcomeError):
            apply_outreach_outcome(row, outcome_status="")

        with self.assertRaises(OutreachOutcomeError):
            apply_outreach_outcome(row, outcome_status="deal", deal_price="not-a-price")


if __name__ == "__main__":
    unittest.main()
