from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

from goofish_analyzer.services.buy_decision_hub import (
    apply_buy_feedback_calibration_with_session,
    build_buy_opportunity_detail_with_session,
    build_buy_opportunity_workbench,
    build_buy_price_baselines_with_session,
    build_buy_watch_targets_with_session,
    record_buy_decision_feedback_with_session,
    refresh_buy_opportunities,
    summarize_template_availability_monitoring_with_session,
)
from goofish_analyzer.services.buy_feedback import (
    record_buy_decision_feedback_with_session as analyzer_record_buy_decision_feedback_with_session,
)
from goofish_analyzer.services.buy_template_monitoring import (
    summarize_template_availability_monitoring_with_session as analyzer_summarize_template_availability_monitoring_with_session,
)
from goofish_analyzer.adapters import (
    BuyAlertEvent,
    BuyDecisionFeedback,
    BuyOpportunity,
    BuyOpportunityRisk,
    BuyPriceBaseline,
    BuyWatchTarget,
)


class _SessionResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_SessionResult":
        return self

    def all(self) -> list[object]:
        return list(self._rows)

    def scalar(self) -> object | None:
        if not self._rows:
            return None
        return _coerce_scalar_row(self._rows[0])

    def scalar_one(self) -> object | None:
        if not self._rows:
            raise AssertionError("No rows in scalar_one()")
        if len(self._rows) != 1:
            raise AssertionError(f"Expected single scalar row, got {len(self._rows)}")
        return _coerce_scalar_row(self._rows[0])

    def scalar_one_or_none(self) -> object | None:
        if not self._rows:
            return None
        if len(self._rows) > 1:
            raise AssertionError(f"Expected scalar row, got {len(self._rows)}")
        return _coerce_scalar_row(self._rows[0])


def _coerce_scalar_row(row: object) -> object:
    if isinstance(row, tuple | list):
        if len(row) != 1:
            raise AssertionError(f"Expected single-value tuple row, got {row!r}")
        return row[0]
    return row


class _FakeSession:
    def __init__(
        self,
        *,
        category: object | None,
        opportunities: list[object],
        baselines: list[object],
        targets: list[object],
        risks: list[object] | None = None,
        alerts: list[object] | None = None,
        feedback_entries: list[object] | None = None,
        items: dict[object, object] | None = None,
    ) -> None:
        self.category = category
        self.opportunities = opportunities
        self.baselines = baselines
        self.targets = targets
        self.risks = risks or []
        self.alerts = alerts or []
        self.feedback_entries = feedback_entries or []
        self.items = items or {}

    def execute(self, statement):
        statement_text = str(statement)
        if "FROM category" in statement_text:
            return _SessionResult([self.category] if self.category is not None else [])
        if "FROM buy_opportunity_risk" in statement_text:
            return _SessionResult(self.risks)
        if "FROM buy_alert_event" in statement_text:
            return _SessionResult(self.alerts)
        if "FROM buy_decision_feedback" in statement_text:
            return _SessionResult(self.feedback_entries)
        if "FROM buy_opportunity" in statement_text:
            return _SessionResult(self.opportunities)
        if "FROM buy_price_baseline" in statement_text:
            return _SessionResult(self.baselines)
        if "FROM buy_watch_target" in statement_text:
            return _SessionResult(self.targets)
        raise AssertionError(f"Unexpected statement: {statement_text}")

    def get(self, model, key):
        model_name = getattr(model, "__name__", "")
        if model_name == "BuyPriceBaseline":
            return next((row for row in self.baselines if str(getattr(row, "id", "")) == str(key)), None)
        if model_name == "BuyWatchTarget":
            return next((row for row in self.targets if str(getattr(row, "id", "")) == str(key)), None)
        if model_name == "Category":
            if self.category is not None and str(getattr(self.category, "id", "")) == str(key):
                return self.category
            return None
        if model_name == "Item":
            return self.items.get(key)
        raise AssertionError(f"Unexpected model.get: {model_name}")


class BuyDecisionHubTests(unittest.TestCase):
    def test_build_buy_opportunity_workbench_assembles_buy_side_summary(self) -> None:
        category = type("Category", (), {"id": "cat-apple", "code": "apple_computer"})()
        opportunity = BuyOpportunity(
            id="opp-1",
            item_id_ref=101,
            watch_target_id="target-1",
            category_id="cat-apple",
            status="OPEN",
            opportunity_score=Decimal("68.2"),
            risk_score=Decimal("9.8"),
            payload={
                "pricing_record": {
                    "title": "MacBook Pro M5 Pro 16G 512G",
                    "item_id": "item-101",
                    "listing_url": "https://example.com/item-101",
                    "region": "上海",
                    "spec_confidence": 0.88,
                },
                "baseline_match_level": "template",
                "baseline_match_key": "template:apple_computer|model_name=MacBook Pro / M5",
            },
        )
        baseline = BuyPriceBaseline(
            id="baseline-1",
            category_id="cat-apple",
            baseline_key="template:apple_computer|model_name=MacBook Pro / M5",
            baseline_date=date(2026, 4, 18),
            sample_size=9,
            fair_price=Decimal("9600"),
            buy_ceiling=Decimal("8800"),
            confidence=Decimal("0.84"),
        )
        target = BuyWatchTarget(
            id="target-1",
            category_id="cat-apple",
            target_name="apple_computer:default",
            profile_key="default",
            status="ACTIVE",
        )
        session = _FakeSession(
            category=category,
            opportunities=[opportunity],
            baselines=[baseline],
            targets=[target],
        )

        with (
            patch(
                "goofish_analyzer.services.buy_decision_hub.summarize_buy_alert_hit_rate_with_session",
                return_value={"hitRate": 0.5, "alertCount": 4, "hitCount": 2},
            ),
            patch(
                "goofish_analyzer.services.buy_decision_hub.summarize_buy_feedback_quality_with_session",
                return_value={"feedbackCount": 3, "acceptCount": 2, "rejectCount": 1},
            ),
            patch(
                "goofish_analyzer.services.buy_decision_hub.summarize_buy_feedback_calibration_with_session",
                return_value={"recommendations": {"totalRecommendationCount": 2}},
            ),
            patch(
                "goofish_analyzer.services.buy_decision_hub.summarize_buy_outcome_funnel_with_session",
                return_value={
                    "alertedOpportunityCount": 4,
                    "openedOpportunityCount": 3,
                    "contactedOpportunityCount": 2,
                    "purchasedOpportunityCount": 1,
                    "roiEvidenceCount": 1,
                    "alertToOpenRate": 0.75,
                    "alertToContactRate": 0.5,
                    "openToContactRate": 0.6667,
                    "contactToPurchaseRate": 0.5,
                    "averageExpectedRoiRate": 0.12,
                },
            ),
            patch(
                "goofish_analyzer.services.buy_decision_hub.build_buy_data_value_report_with_session",
                return_value={
                    "summary": {
                        "itemCount": 100,
                        "opportunityCount": 12,
                        "feedbackCount": 3,
                        "dataValueScore": 42.0,
                    },
                    "diagnosis": {"statusLabel": "价值闭环学习中"},
                    "stages": [],
                    "categoryBreakdown": [],
                    "recommendations": [],
                },
            ),
            patch(
                "goofish_analyzer.services.buy_decision_hub.build_buy_opportunity_explanation",
                return_value={"readinessSummary": "ready"},
            ),
            patch(
                "goofish_analyzer.services.buy_decision_hub.build_buy_price_baseline_explanation",
                return_value={"readinessSummary": "baseline ready"},
            ),
        ):
            payload = build_buy_opportunity_workbench(session, category_code="apple_computer", limit=20)

        self.assertEqual(payload["categoryCode"], "apple_computer")
        self.assertEqual(payload["summary"]["opportunityCount"], 1)
        self.assertEqual(payload["summary"]["alertHitCount"], 2)
        self.assertEqual(payload["summary"]["feedbackCount"], 3)
        self.assertEqual(payload["summary"]["calibrationRecommendationCount"], 2)
        self.assertEqual(payload["summary"]["todayOpportunityCount"], 1)
        self.assertEqual(payload["outcomeFunnel"]["openedOpportunityCount"], 3)
        self.assertEqual(payload["outcomeFunnel"]["purchasedOpportunityCount"], 1)
        self.assertEqual(payload["outcomeFunnel"]["roiEvidenceCount"], 1)
        self.assertEqual(payload["dataValue"]["summary"]["dataValueScore"], 42.0)
        self.assertEqual(payload["dailyOpportunityPack"]["summary"]["northStar"], "把 OPEN 机会消化成反馈、联系、成交和 ROI 证据")
        self.assertEqual(payload["dailyOpportunityPack"]["summary"]["packOpportunityCount"], 1)
        self.assertEqual(payload["dailyOpportunityPack"]["groups"][0]["key"], "act_now")
        self.assertEqual(payload["dailyOpportunityPack"]["groups"][0]["tasks"][0]["opportunity"]["id"], "opp-1")
        self.assertEqual(payload["opportunities"][0]["title"], "MacBook Pro M5 Pro 16G 512G")
        self.assertEqual(payload["baselines"][0]["baselineKey"], "template:apple_computer|model_name=MacBook Pro / M5")

    def test_apply_buy_feedback_calibration_with_session_updates_runtime_config_and_rebuilds(self) -> None:
        category = type("Category", (), {"id": "cat-apple", "code": "apple_computer"})()

        with (
            patch(
                "goofish_analyzer.services.buy_feedback._resolve_optional_category",
                return_value=category,
            ),
            patch(
                "goofish_analyzer.services.buy_feedback.summarize_buy_feedback_calibration_with_session",
                return_value={
                    "categoryCode": "apple_computer",
                    "windowDays": 30,
                    "effectiveCalibrationConfig": {
                        "pricingThresholds": {
                            "referenceOnly": {
                                "seller_sample_count": 3,
                                "unique_seller_count": 2,
                                "exact_spec_ratio": 0.65,
                                "reliability_score": 60.0,
                                "freshness_days": 14,
                            },
                            "guidanceReady": {
                                "seller_sample_count": 5,
                                "unique_seller_count": 3,
                                "exact_spec_ratio": 0.8,
                                "reliability_score": 70.0,
                                "freshness_days": 14,
                            },
                        },
                        "opportunityScoring": {
                            "buyCeilingTightenPct": 0.0,
                            "riskPenaltyWeight": 0.2,
                        },
                    },
                    "recommendations": {
                        "templateFieldRecommendations": [
                            {
                                "id": "template_field_memory_gb",
                                "title": "补字段",
                                "summary": "manual",
                                "recommendedAction": "manual",
                            }
                        ],
                        "thresholdRecommendations": [
                            {
                                "id": "threshold_guidance_sample_count",
                                "title": "提高样本门槛",
                                "summary": "sample unstable",
                                "recommendedAction": "raise",
                                "evidence": {
                                    "suggestedThreshold": 6,
                                },
                            },
                            {
                                "id": "threshold_buy_ceiling_margin",
                                "title": "收紧买入线",
                                "summary": "too high",
                                "recommendedAction": "tighten",
                                "evidence": {
                                    "suggestedTightenPct": 4.0,
                                },
                            },
                        ],
                        "rankingRecommendations": [
                            {
                                "id": "ranking_risk_penalty_weight",
                                "title": "提高风险权重",
                                "summary": "risk gap",
                                "recommendedAction": "raise risk penalty",
                                "evidence": {
                                    "suggestedPenaltyWeight": 0.25,
                                },
                            }
                        ],
                    },
                },
            ),
            patch(
                "goofish_analyzer.services.buy_feedback.upsert_buy_side_calibration_config_with_session",
                return_value={
                    "effectiveConfig": {
                        "pricingThresholds": {
                            "referenceOnly": {"seller_sample_count": 3},
                            "guidanceReady": {"seller_sample_count": 6},
                        },
                        "opportunityScoring": {
                            "buyCeilingTightenPct": 4.0,
                            "riskPenaltyWeight": 0.25,
                        },
                    },
                    "profile": {"id": "profile-1"},
                },
            ) as upsert_mock,
            patch(
                "goofish_analyzer.services.buy_feedback.build_buy_price_baselines_with_session",
                return_value={"baselineCount": 11},
            ),
            patch(
                "goofish_analyzer.services.buy_feedback.refresh_buy_opportunities_with_session",
                return_value={"opportunityCount": 7},
            ),
        ):
            payload = apply_buy_feedback_calibration_with_session(
                object(),
                category_code="apple_computer",
                window_days=30,
                operator_id="ops-bot",
            )

        self.assertEqual(payload["appliedRecommendationCount"], 3)
        self.assertEqual(payload["skippedRecommendationCount"], 1)
        self.assertEqual(payload["baselineRebuild"]["baselineCount"], 11)
        self.assertEqual(payload["opportunityRefresh"]["opportunityCount"], 7)
        upsert_kwargs = upsert_mock.call_args.kwargs
        self.assertEqual(upsert_kwargs["category"].code, "apple_computer")
        self.assertEqual(
            upsert_kwargs["config_patch"],
            {
                "pricingThresholds": {
                    "guidanceReady": {
                        "seller_sample_count": 6,
                    },
                },
                "opportunityScoring": {
                    "buyCeilingTightenPct": 4.0,
                    "riskPenaltyWeight": 0.25,
                },
            },
        )

    def test_build_buy_watch_targets_with_session_returns_watch_target_summary(self) -> None:
        category = type("Category", (), {"id": "cat-apple", "code": "apple_computer"})()
        target = BuyWatchTarget(
            id="target-1",
            category_id="cat-apple",
            target_name="apple_computer:default",
            profile_key="default",
            status="ACTIVE",
        )
        session = _FakeSession(
            category=category,
            opportunities=[],
            baselines=[],
            targets=[target],
        )

        payload = build_buy_watch_targets_with_session(
            session,
            category_code="apple_computer",
            status="ACTIVE",
            limit=20,
        )

        self.assertEqual(payload["categoryCode"], "apple_computer")
        self.assertEqual(payload["summary"]["watchTargetCount"], 1)
        self.assertEqual(payload["summary"]["activeWatchTargetCount"], 1)
        self.assertEqual(payload["watchTargets"][0]["targetName"], "apple_computer:default")

    def test_build_buy_price_baselines_with_session_returns_latest_summary(self) -> None:
        category = type("Category", (), {"id": "cat-apple", "code": "apple_computer"})()
        baseline = BuyPriceBaseline(
            id="baseline-1",
            category_id="cat-apple",
            baseline_key="template:apple",
            baseline_date=date(2026, 4, 20),
            sample_size=12,
            fair_price=Decimal("7600"),
            buy_ceiling=Decimal("7200"),
            confidence=Decimal("0.86"),
        )
        session = _FakeSession(
            category=category,
            opportunities=[],
            baselines=[baseline],
            targets=[],
        )

        payload = build_buy_price_baselines_with_session(
            session,
            category_code="apple_computer",
            limit=20,
        )

        self.assertEqual(payload["summary"]["baselineCount"], 1)
        self.assertEqual(payload["summary"]["baselineDateFrom"], "2026-04-20")
        self.assertEqual(payload["summary"]["baselineDateTo"], "2026-04-20")
        self.assertEqual(payload["baselines"][0]["baselineKey"], "template:apple")

    def test_build_buy_opportunity_detail_assembles_evidence_chain(self) -> None:
        category = type("Category", (), {"id": "cat-apple", "code": "apple_computer"})()
        opportunity = BuyOpportunity(
            id="opp-1",
            item_id_ref=101,
            watch_target_id="target-1",
            category_id="cat-apple",
            baseline_id="baseline-1",
            status="OPEN",
            decision="contacted",
            decision_note="准备私聊砍价",
            opportunity_score=Decimal("78.2"),
            risk_score=Decimal("11.6"),
            current_price=Decimal("6999"),
            fair_price=Decimal("7600"),
            buy_ceiling=Decimal("7200"),
            discount_rate=Decimal("0.0791"),
            payload={
                "pricing_record": {
                    "title": "MacBook Pro M5 Pro 16G 512G",
                    "item_id": "xy-101",
                    "listing_url": "https://example.com/item-101",
                    "region": "上海",
                    "spec_confidence": 0.88,
                },
                "feedbackSummary": {
                    "feedbackAction": "accept",
                    "feedbackLabel": "contacted",
                },
                "matchedTemplateKey": "apple:m5:16:512",
                "matchedTemplateLabel": "MacBook Pro / M5 Pro / 16G / 512G",
                "matchedFieldValues": {"memory_gb": "16", "storage_gb": "512"},
                "templateAvailabilityTier": "guidance_ready",
                "metrics": {"sampleSize": 9, "exactSpecRatio": 0.78},
            },
        )
        baseline = BuyPriceBaseline(
            id="baseline-1",
            category_id="cat-apple",
            baseline_key="template:apple_computer|model_name=MacBook Pro / M5",
            baseline_date=date(2026, 4, 18),
            sample_size=9,
            fair_price=Decimal("7600"),
            buy_ceiling=Decimal("7200"),
            confidence=Decimal("0.84"),
        )
        target = BuyWatchTarget(
            id="target-1",
            category_id="cat-apple",
            target_name="apple_computer:default",
            profile_key="default",
            status="ACTIVE",
        )
        risk = BuyOpportunityRisk(
            id="risk-1",
            opportunity_id="opp-1",
            risk_code="LOW_SAMPLE_SIZE",
            risk_level="high",
            detail="样本仍偏少，需要人工复核。",
            evidence_json={"sample_size": 3},
        )
        alert = BuyAlertEvent(
            id="alert-1",
            opportunity_id="opp-1",
            watch_target_id="target-1",
            alert_channel="dashboard",
            alert_reason="buy opportunity score=78.2, discount=7.9%",
            status="SENT",
            payload={"source": "test"},
        )
        feedback_entry = BuyDecisionFeedback(
            id="feedback-1",
            opportunity_id="opp-1",
            feedback_type="decision",
            feedback_label="contacted",
            operator_id="local",
            feedback_note="已私聊卖家",
            payload={"feedbackAction": "accept"},
        )
        open_feedback_entry = BuyDecisionFeedback(
            id="feedback-open",
            opportunity_id="opp-1",
            feedback_type="engagement",
            feedback_label="detail_opened",
            operator_id="local",
            feedback_note="打开详情页",
            created_at=datetime(2026, 4, 24, 11, 0, tzinfo=UTC),
            payload={"feedbackAction": "engage"},
        )
        purchase_feedback_entry = BuyDecisionFeedback(
            id="feedback-2",
            opportunity_id="opp-1",
            feedback_type="decision",
            feedback_label="purchased",
            operator_id="local",
            feedback_note="已成交",
            purchase_price=Decimal("6800"),
            expected_resale_price=Decimal("7600"),
            created_at=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
            payload={"feedbackAction": "accept"},
        )
        item = type("Item", (), {"item_id": "xy-101"})()
        session = _FakeSession(
            category=category,
            opportunities=[opportunity],
            baselines=[baseline],
            targets=[target],
            risks=[risk],
            alerts=[alert],
            feedback_entries=[purchase_feedback_entry, open_feedback_entry, feedback_entry],
            items={101: item},
        )

        with (
            patch(
                "goofish_analyzer.services.buy_decision_hub.build_buy_opportunity_explanation",
                return_value={"readinessSummary": "可以动作"},
            ),
            patch(
                "goofish_analyzer.services.buy_decision_hub.build_buy_price_baseline_explanation",
                return_value={"readinessSummary": "基线稳定"},
            ),
        ):
            payload = build_buy_opportunity_detail_with_session(
                session,
                opportunity_id="opp-1",
                category_code="apple_computer",
            )

        assert payload is not None
        self.assertEqual(payload["categoryCode"], "apple_computer")
        self.assertEqual(payload["opportunity"]["id"], "opp-1")
        self.assertEqual(payload["opportunity"]["itemId"], "xy-101")
        self.assertEqual(payload["opportunity"]["decisionNote"], "准备私聊砍价")
        self.assertEqual(payload["watchTarget"]["targetName"], "apple_computer:default")
        self.assertEqual(payload["baseline"]["baselineKey"], "template:apple_computer|model_name=MacBook Pro / M5")
        self.assertEqual(payload["risks"][0]["riskCode"], "LOW_SAMPLE_SIZE")
        self.assertEqual(payload["alertEvents"][0]["id"], "alert-1")
        self.assertEqual(payload["feedbackEntries"][0]["feedbackLabel"], "purchased")
        self.assertEqual(payload["outcomeProof"]["alertEventCount"], 1)
        self.assertEqual(payload["outcomeProof"]["openFeedbackCount"], 1)
        self.assertEqual(payload["outcomeProof"]["contactFeedbackCount"], 1)
        self.assertEqual(payload["outcomeProof"]["purchaseFeedbackCount"], 1)
        self.assertTrue(payload["outcomeProof"]["hasOpenEvidence"])
        self.assertTrue(payload["outcomeProof"]["hasRoiEvidence"])
        self.assertEqual(payload["outcomeProof"]["purchasePrice"], 6800.0)
        self.assertEqual(payload["outcomeProof"]["expectedResalePrice"], 7600.0)
        self.assertEqual(payload["outcomeProof"]["estimatedProfit"], 800.0)

    def test_feedback_and_refresh_exports_are_analyzer_owned(self) -> None:
        self.assertIs(
            record_buy_decision_feedback_with_session,
            analyzer_record_buy_decision_feedback_with_session,
        )
        from goofish_analyzer.services.buy_opportunities import refresh_buy_opportunities as analyzer_refresh
        self.assertIs(
            refresh_buy_opportunities,
            analyzer_refresh,
        )
        self.assertIs(
            summarize_template_availability_monitoring_with_session,
            analyzer_summarize_template_availability_monitoring_with_session,
        )


if __name__ == "__main__":
    unittest.main()
