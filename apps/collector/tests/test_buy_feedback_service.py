from __future__ import annotations

import unittest

from goofish_analyzer.services.buy_feedback import (
    BuyFeedbackError,
    build_feedback_calibration_recommendations,
    feedback_action_for_label,
    feedback_category_for_label,
    is_engagement_feedback,
    record_buy_decision_feedback_with_session,
    opportunity_status_for_feedback_label,
)
from goofish_insight.application.services.buy_feedback import (
    record_buy_decision_feedback_with_session as collector_record_buy_decision_feedback_with_session,
)
from goofish_insight.models import BuyOpportunity, DecisionFeedbackLog


class _FakeSession:
    def __init__(self, opportunity: BuyOpportunity | None) -> None:
        self.opportunity = opportunity
        self.added: list[object] = []

    def get(self, model, key):
        if getattr(model, "__name__", "") == "BuyOpportunity":
            return self.opportunity
        return None

    def add(self, row) -> None:
        self.added.append(row)


class BuyFeedbackServiceTests(unittest.TestCase):
    def test_collector_feedback_exports_reuse_analyzer_service_entrypoints(self) -> None:
        self.assertIs(
            record_buy_decision_feedback_with_session,
            collector_record_buy_decision_feedback_with_session,
        )

    def test_feedback_label_maps_to_opportunity_status(self) -> None:
        self.assertEqual(opportunity_status_for_feedback_label("purchased"), "PURCHASED")
        self.assertEqual(opportunity_status_for_feedback_label("contacted"), "CONTACTED")
        self.assertEqual(opportunity_status_for_feedback_label("not worth it"), "DISMISSED")
        self.assertEqual(opportunity_status_for_feedback_label("wrong_model"), "REJECTED")
        self.assertEqual(opportunity_status_for_feedback_label("keep watching"), "REVIEWED")

    def test_feedback_action_and_category_mapping(self) -> None:
        self.assertEqual(feedback_action_for_label("purchased"), "accept")
        self.assertEqual(feedback_category_for_label("purchased"), "accepted_purchased")

        self.assertEqual(feedback_action_for_label("wrong_model"), "reject")
        self.assertEqual(feedback_category_for_label("wrong_model"), "template_mismatch")

        self.assertEqual(feedback_action_for_label("price_too_high"), "reject")
        self.assertEqual(feedback_category_for_label("price_too_high"), "price_too_high")

        self.assertEqual(feedback_action_for_label("sample_unstable"), "reject")
        self.assertEqual(feedback_category_for_label("sample_unstable"), "sample_unstable")

        self.assertEqual(feedback_action_for_label("trend_unreliable"), "reject")
        self.assertEqual(feedback_category_for_label("trend_unreliable"), "trend_unreliable")

        self.assertEqual(feedback_action_for_label("keep watching"), "neutral")
        self.assertEqual(feedback_category_for_label("keep watching"), "reviewed")

        self.assertEqual(feedback_action_for_label("detail_opened"), "engage")
        self.assertEqual(feedback_category_for_label("listing_opened"), "engaged_listing_opened")
        self.assertTrue(is_engagement_feedback("engagement", "detail_opened"))

    def test_build_feedback_calibration_recommendations(self) -> None:
        quality = {
            "opportunityCount": 40,
            "rejectReasonCounts": {
                "template_mismatch": 10,
                "price_too_high": 8,
                "risk_too_high": 3,
                "sample_unstable": 2,
            },
            "templateMatchErrorCounts": {
                "missing_template_key": 12,
                "degraded_product_match": 4,
            },
            "templateMismatchMissingFieldCounts": {
                "memory_gb": 6,
                "storage_gb": 3,
            },
            "tierStats": {
                "guidance_ready": {
                    "decisionCount": 12,
                },
                "reference_only": {
                    "decisionCount": 9,
                    "acceptanceRate": 0.77,
                },
            },
            "rejectReasonByTierCounts": {
                "guidance_ready": {
                    "price_too_high": 5,
                    "sample_unstable": 3,
                    "trend_unreliable": 2,
                },
                "reference_only": {
                    "sample_unstable": 0,
                    "trend_unreliable": 0,
                },
            },
            "decisionScoreStats": {
                "accept": {"count": 6, "avgRiskScore": 9.0},
                "reject": {"count": 8, "avgRiskScore": 19.5},
            },
        }

        payload = build_feedback_calibration_recommendations(quality)
        self.assertGreater(payload["totalRecommendationCount"], 0)
        self.assertTrue(payload["templateFieldRecommendations"])
        self.assertTrue(payload["thresholdRecommendations"])
        self.assertTrue(payload["rankingRecommendations"])

    def test_record_feedback_with_linkage_sets_alert_candidate_summary(self) -> None:
        opportunity = BuyOpportunity(
            id="opp-1",
            item_id_ref=101,
            watch_target_id="target-1",
            status="OPEN",
            payload={"templateMatchErrorType": "missing_template_key"},
        )
        session = _FakeSession(opportunity)
        with (
            unittest.mock.patch("goofish_analyzer.services.buy_feedback._flush"),
            unittest.mock.patch(
                "goofish_analyzer.services.buy_feedback.link_buy_feedback_to_alert_candidate_with_session",
                return_value={
                    "status": "created",
                    "reason": "candidate_created",
                    "channel": "dashboard",
                    "alertEventId": "alert-1",
                },
            ),
        ):
            result = record_buy_decision_feedback_with_session(
                session,
                opportunity_id="opp-1",
                feedback_type="decision",
                feedback_label="contacted",
                operator_id="tester",
                feedback_note="looks good",
                link_to_alert_candidate=True,
            )

        self.assertEqual(result["alertCandidateLinkage"]["status"], "created")
        self.assertEqual(opportunity.status, "CONTACTED")
        summary = dict((opportunity.payload or {}).get("feedbackSummary") or {})
        self.assertEqual(summary.get("feedbackAction"), "accept")
        self.assertEqual(summary.get("feedbackCategory"), "accepted_contacted")
        self.assertEqual(dict(summary.get("alertCandidateLinkage") or {}).get("status"), "created")
        log_rows = [row for row in session.added if isinstance(row, DecisionFeedbackLog)]
        self.assertEqual(len(log_rows), 1)
        self.assertEqual(log_rows[0].feedback_action, "accept")
        self.assertEqual(log_rows[0].opportunity_status, "CONTACTED")

    def test_record_engagement_feedback_preserves_decision_state(self) -> None:
        opportunity = BuyOpportunity(
            id="opp-1",
            item_id_ref=101,
            watch_target_id="target-1",
            status="OPEN",
            decision=None,
            payload={
                "feedbackSummary": {
                    "feedbackAction": "accept",
                    "feedbackLabel": "contacted",
                }
            },
        )
        session = _FakeSession(opportunity)

        result = record_buy_decision_feedback_with_session(
            session,
            opportunity_id="opp-1",
            feedback_type="engagement",
            feedback_label="detail_opened",
            operator_id="tester",
        )

        self.assertEqual(result["opportunity"]["status"], "OPEN")
        self.assertIsNone(result["opportunity"]["decision"])
        self.assertEqual(opportunity.status, "OPEN")
        self.assertIsNone(opportunity.decision)
        self.assertEqual(dict((opportunity.payload or {}).get("feedbackSummary") or {}).get("feedbackLabel"), "contacted")
        engagement_summary = dict((opportunity.payload or {}).get("engagementSummary") or {})
        self.assertEqual(engagement_summary.get("feedbackAction"), "engage")
        self.assertEqual(engagement_summary.get("feedbackLabel"), "detail_opened")
        log_rows = [row for row in session.added if isinstance(row, DecisionFeedbackLog)]
        self.assertEqual(len(log_rows), 1)
        self.assertEqual(log_rows[0].feedback_action, "engage")

    def test_record_feedback_rejects_invalid_decimal_input(self) -> None:
        opportunity = BuyOpportunity(
            id="opp-1",
            item_id_ref=101,
            watch_target_id="target-1",
            status="OPEN",
            payload={},
        )
        session = _FakeSession(opportunity)

        with self.assertRaisesRegex(BuyFeedbackError, "Invalid decimal value: not-a-number"):
            record_buy_decision_feedback_with_session(
                session,
                opportunity_id="opp-1",
                feedback_type="decision",
                feedback_label="purchased",
                purchase_price="not-a-number",
            )


if __name__ == "__main__":
    unittest.main()
