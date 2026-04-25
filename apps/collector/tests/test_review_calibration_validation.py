from __future__ import annotations

import unittest

from goofish_insight.application.services.review_calibration import (
    CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK,
    CALIBRATION_BUCKET_VALID,
    validate_review_calibration_entries,
)


class ReviewCalibrationValidationTests(unittest.TestCase):
    def test_validate_review_calibration_entries_flags_bad_annotation_values(self) -> None:
        entries = [
            {
                "sample_id": "cal-0001",
                "bucket": CALIBRATION_BUCKET_VALID,
                "item_id": "item-1",
                "route_hint": "qwen3_first_pass_benchmark",
                "review_prediction": {"status": "valid", "confidence": 0.96, "needs_audit": False},
                "annotation": {"review_status": "vaild", "pricing_safe": True, "risk_level": "mid"},
            },
            {
                "sample_id": "cal-0001",
                "bucket": CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK,
                "item_id": "item-1",
                "route_hint": "dense_or_manual_profit_sensitive",
                "review_prediction": {"status": "pending_audit", "confidence": None, "needs_audit": True},
                "annotation": {"review_status": "invalid", "pricing_safe": True, "risk_level": "high"},
            },
        ]

        summary = validate_review_calibration_entries(entries)

        self.assertFalse(summary["valid"])
        error_codes = {error["code"] for error in summary["errors"]}
        warning_codes = {warning["code"] for warning in summary["warnings"]}
        self.assertIn("invalid_annotation_review_status", error_codes)
        self.assertIn("invalid_annotation_risk_level", error_codes)
        self.assertIn("duplicate_sample_id", error_codes)
        self.assertIn("duplicate_item_id", error_codes)
        self.assertIn("pricing_safe_true_but_human_invalid", warning_codes)
        self.assertNotIn("high_profit_high_risk_marked_not_pricing_safe", warning_codes)


if __name__ == "__main__":
    unittest.main()
