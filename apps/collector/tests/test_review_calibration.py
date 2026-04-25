from __future__ import annotations

import unittest

from goofish_insight.application.services.review_calibration import (
    CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK,
    CALIBRATION_BUCKET_INVALID,
    CALIBRATION_BUCKET_PENDING_AUDIT,
    CALIBRATION_BUCKET_VALID,
    evaluate_review_calibration_set,
    select_calibration_samples,
)


class ReviewCalibrationTests(unittest.TestCase):
    def test_select_calibration_samples_prioritizes_high_profit_bucket_and_spreads_domains(self) -> None:
        candidates = [
            {
                "item_id": "g-risk",
                "business_domain": "garmin",
                "bucket_tags": [CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK, CALIBRATION_BUCKET_PENDING_AUDIT],
            },
            {
                "item_id": "a-risk",
                "business_domain": "apple_m_series",
                "bucket_tags": [CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK],
            },
            {
                "item_id": "g-valid",
                "business_domain": "garmin",
                "bucket_tags": [CALIBRATION_BUCKET_VALID],
            },
            {
                "item_id": "a-valid",
                "business_domain": "apple_m_series",
                "bucket_tags": [CALIBRATION_BUCKET_VALID],
            },
        ]

        samples, summary = select_calibration_samples(
            candidates=candidates,
            bucket_limits={
                CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK: 2,
                CALIBRATION_BUCKET_PENDING_AUDIT: 1,
                CALIBRATION_BUCKET_VALID: 2,
                CALIBRATION_BUCKET_INVALID: 0,
            },
            seed=7,
        )

        self.assertEqual(summary["picked_counts"][CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK], 2)
        self.assertEqual(samples[0]["bucket"], CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK)
        self.assertEqual(samples[1]["bucket"], CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK)
        self.assertEqual(samples[2]["bucket"], CALIBRATION_BUCKET_VALID)
        self.assertEqual({samples[0]["business_domain"], samples[1]["business_domain"]}, {"garmin", "apple_m_series"})

    def test_evaluate_review_calibration_reports_precision_and_model_lane_observations(self) -> None:
        entries = [
            {
                "bucket": CALIBRATION_BUCKET_VALID,
                "review_prediction": {"status": "valid", "confidence": 0.97, "needs_audit": False},
                "pricing_context": {"is_high_profit_high_risk_candidate": False},
                "annotation": {"review_status": "valid", "pricing_safe": True},
            },
            {
                "bucket": CALIBRATION_BUCKET_VALID,
                "review_prediction": {"status": "valid", "confidence": 0.91, "needs_audit": False},
                "pricing_context": {"is_high_profit_high_risk_candidate": False},
                "annotation": {"review_status": "invalid", "pricing_safe": False},
            },
            {
                "bucket": CALIBRATION_BUCKET_INVALID,
                "review_prediction": {"status": "invalid", "confidence": 0.10, "needs_audit": False},
                "pricing_context": {"is_high_profit_high_risk_candidate": False},
                "annotation": {"review_status": "invalid", "pricing_safe": False},
            },
            {
                "bucket": CALIBRATION_BUCKET_INVALID,
                "review_prediction": {"status": "invalid", "confidence": 0.20, "needs_audit": False},
                "pricing_context": {"is_high_profit_high_risk_candidate": False},
                "annotation": {"review_status": "valid", "pricing_safe": False},
            },
            {
                "bucket": CALIBRATION_BUCKET_PENDING_AUDIT,
                "review_prediction": {"status": "pending_audit", "confidence": None, "needs_audit": True},
                "pricing_context": {"is_high_profit_high_risk_candidate": False},
                "annotation": {"review_status": "valid", "pricing_safe": True},
            },
            {
                "bucket": CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK,
                "review_prediction": {"status": "valid", "confidence": 0.93, "needs_audit": False},
                "pricing_context": {"is_high_profit_high_risk_candidate": True},
                "annotation": {"review_status": "valid", "pricing_safe": False},
            },
        ]

        report = evaluate_review_calibration_set(entries=entries)

        auto_valid = report["current_policy_metrics"]["auto_valid"]
        auto_invalid = report["current_policy_metrics"]["auto_invalid"]
        pricing_pool = report["current_policy_metrics"]["pricing_pool"]

        self.assertEqual(auto_valid["selected_count"], 3)
        self.assertEqual(auto_valid["review_labeled_count"], 3)
        self.assertEqual(auto_valid["precision_valid"], 0.6667)
        self.assertEqual(auto_invalid["selected_count"], 2)
        self.assertEqual(auto_invalid["precision_invalid"], 0.5)
        self.assertEqual(pricing_pool["selected_count"], 1)
        self.assertEqual(pricing_pool["pricing_safe_precision"], 1.0)
        self.assertEqual(report["model_lane_observations"]["dense_second_pass_candidate_count"], 3)
        self.assertEqual(report["model_lane_observations"]["manual_tail_candidate_count"], 1)


if __name__ == "__main__":
    unittest.main()
