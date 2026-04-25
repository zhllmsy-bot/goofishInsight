from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from goofish_insight.application.services.review_queries import is_review_state_claimable


class ReviewQueryContractTests(unittest.TestCase):
    def test_pending_status_is_claimable(self) -> None:
        self.assertTrue(
            is_review_state_claimable(
                review_status="pending",
                updated_at=None,
                now=datetime(2026, 4, 4, 2, 0, 0, tzinfo=UTC),
                lease_seconds=1800,
            )
        )

    def test_stale_in_progress_status_is_claimable(self) -> None:
        now = datetime(2026, 4, 4, 2, 0, 0, tzinfo=UTC)
        self.assertTrue(
            is_review_state_claimable(
                review_status="in_progress",
                updated_at=now - timedelta(seconds=1900),
                now=now,
                lease_seconds=1800,
            )
        )

    def test_invalid_tail_rows_are_not_claimable(self) -> None:
        now = datetime(2026, 4, 4, 2, 0, 0, tzinfo=UTC)
        self.assertFalse(
            is_review_state_claimable(
                review_status="invalid",
                updated_at=now - timedelta(days=1),
                now=now,
                lease_seconds=1800,
            )
        )


if __name__ == "__main__":
    unittest.main()
