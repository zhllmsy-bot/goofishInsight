from __future__ import annotations

import unittest
from decimal import Decimal

from goofish_insight.application.services.quality_metrics import (
    _decimal_to_float,
    build_price_anomaly_rate_stats,
    build_review_pass_rate_stats,
)


class QualityMetricsServiceTests(unittest.TestCase):
    def test_decimal_to_float_preserves_zero(self) -> None:
        self.assertEqual(_decimal_to_float(Decimal("0")), 0.0)
        self.assertEqual(_decimal_to_float(Decimal("1.25")), 1.25)
        self.assertIsNone(_decimal_to_float(None))

    def test_build_review_pass_rate_stats_uses_terminal_v3_statuses(self) -> None:
        stats = build_review_pass_rate_stats(
            [
                "VALID_READY_FOR_PRICING",
                "REJECTED_ACCESSORY",
                "PENDING_REVIEW",
                "MANUAL_AUDIT_REQUIRED",
                "unknown",
            ]
        )

        self.assertEqual(stats["pass_count"], 1)
        self.assertEqual(stats["terminal_count"], 3)
        self.assertAlmostEqual(stats["pass_rate"], 1 / 3)

    def test_build_price_anomaly_rate_stats_counts_collection_payload_rejections(self) -> None:
        stats = build_price_anomaly_rate_stats(
            [
                {
                    "item_count": 8,
                    "rejected_missing_price_count": 1,
                    "rejected_low_price_count": 1,
                    "category_gate_blocked_reasons": {
                        "price_floor": 2,
                        "signature_mismatch": 9,
                    },
                },
                {
                    "item_count": 2,
                    "rejected_missing_price_count": 0,
                    "rejected_low_price_count": 1,
                },
            ]
        )

        self.assertEqual(stats["item_count"], 10)
        self.assertEqual(stats["missing_price_count"], 1)
        self.assertEqual(stats["rejected_low_price_count"], 2)
        self.assertEqual(stats["category_price_floor_count"], 2)
        self.assertEqual(stats["anomaly_count"], 5)
        self.assertEqual(stats["observed_count"], 15)
        self.assertAlmostEqual(stats["anomaly_rate"], 5 / 15)


if __name__ == "__main__":
    unittest.main()
