from __future__ import annotations

import unittest
from decimal import Decimal

from goofish_insight.application.services.buy_dashboard import (
    serialize_buy_workbench_opportunity,
    serialize_buy_workbench_baseline,
)
from goofish_insight.models import BuyOpportunity, BuyPriceBaseline


class BuyDashboardServiceTests(unittest.TestCase):
    def test_serialize_opportunity_uses_pricing_record_payload(self) -> None:
        row = BuyOpportunity(
            id="opp-1",
            item_id_ref=123,
            watch_target_id="target-1",
            status="OPEN",
            current_price=Decimal("7800"),
            fair_price=Decimal("9000"),
            buy_ceiling=Decimal("8200"),
            opportunity_score=Decimal("72.5"),
            payload={
                "baseline_match_level": "spec",
                "baseline_match_key": "spec:MacBook Pro / M5",
                "pricing_record": {
                    "item_id": "xianyu-1",
                    "title": "MacBook Pro M5 16G 512G",
                    "listing_url": "https://example.test/item",
                    "region": "上海",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.88,
                    "schema_id": 42,
                    "sample_snapshot": {
                        "schemaId": 42,
                        "sampleState": "eligible",
                        "fingerprintHash": "fp-abc12345",
                        "sampleQualityScore": 0.93,
                    },
                    "pricing_eligibility": {
                        "pricingReady": True,
                        "specSource": {"present": True, "extractorType": "hybrid", "isShadow": False, "pricingUsable": True},
                        "reviewGate": {"passed": True},
                        "specGate": {"passed": True},
                    },
                    "spec_contract": {
                        "status": "complete",
                        "missingRequiredFields": [],
                    },
                },
                "feedbackSummary": {
                    "feedbackAction": "watch",
                    "feedbackLabel": "contacted",
                    "recordedAt": "2026-04-26T03:00:00+00:00",
                },
            },
        )

        payload = serialize_buy_workbench_opportunity(row)

        self.assertEqual(payload["title"], "MacBook Pro M5 16G 512G")
        self.assertEqual(payload["currentPrice"], 7800.0)
        self.assertEqual(payload["baselineMatchLevel"], "spec")
        self.assertEqual(payload["exactSpecReady"], True)
        self.assertEqual(payload["specConfidence"], 0.88)
        self.assertEqual(payload["pricingEligibility"]["pricingReady"], True)
        self.assertEqual(payload["specSource"]["pricingUsable"], True)
        self.assertEqual(payload["specContract"]["status"], "complete")
        self.assertEqual(payload["schemaId"], 42)
        self.assertEqual(payload["sampleSnapshot"]["fingerprintHash"], "fp-abc12345")
        self.assertEqual(payload["feedbackSummary"]["feedbackLabel"], "contacted")
        self.assertEqual(payload["explanation"]["readinessSummary"], "可直接按价格池口径判断")
        self.assertEqual(payload["explanation"]["reviewGateSummary"], "review ready")
        self.assertEqual(payload["explanation"]["specGateSummary"], "spec ready")

    def test_serialize_opportunity_surfaces_missing_required_field_reason(self) -> None:
        row = BuyOpportunity(
            id="opp-2",
            item_id_ref=124,
            watch_target_id="target-1",
            status="REFERENCE_ONLY",
            current_price=Decimal("7800"),
            fair_price=Decimal("9000"),
            buy_ceiling=Decimal("8200"),
            opportunity_score=Decimal("52.5"),
            payload={
                "templateGuidanceReady": False,
                "pricing_record": {
                    "item_id": "xianyu-2",
                    "title": "MacBook Pro M5 Pro 18G 512G",
                    "pricing_eligibility": {
                        "pricingReady": False,
                        "reviewGate": {"passed": True},
                        "specGate": {"passed": False, "reasonLabel": "规格置信度低于价格池门槛"},
                    },
                    "spec_contract": {
                        "status": "partial",
                        "missingRequiredFields": ["screen_size_in"],
                    },
                },
            },
        )

        payload = serialize_buy_workbench_opportunity(row)

        self.assertEqual(payload["explanation"]["readinessSummary"], "仅参考：缺 screen_size_in")
        self.assertEqual(payload["explanation"]["missingRequiredFields"], ["screen_size_in"])

    def test_serialize_baseline_includes_readiness_explanation(self) -> None:
        row = BuyPriceBaseline(
            id="baseline-1",
            category_id="cat-apple",
            baseline_key="spec:MacBook Pro / M5 / 16G / 512G",
            baseline_date=None,
            sample_size=7,
            fair_price=Decimal("9000"),
            buy_ceiling=Decimal("8200"),
            confidence=Decimal("0.8235"),
            payload={
                "pricingTemplate": {
                    "availability": {
                        "availabilityTier": "guidance_ready",
                        "pricingBlockReason": None,
                        "pricingEvidence": {
                            "sellerSampleCount": 7,
                            "uniqueSellerCount": 4,
                            "exactSpecRatio": 0.85,
                            "reliabilityScore": 82.35,
                            "freshnessDays": 1,
                        },
                    }
                }
            },
        )

        payload = serialize_buy_workbench_baseline(row)

        self.assertEqual(payload["explanation"]["readinessSummary"], "可直接作为买入线参考")
        self.assertEqual(payload["explanation"]["confidenceSummary"], "高置信")
        self.assertEqual(payload["explanation"]["reliabilityScore"], 82.35)


if __name__ == "__main__":
    unittest.main()
