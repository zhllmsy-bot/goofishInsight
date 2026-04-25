from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from goofish_insight.application.services.buy_opportunities import (
    baseline_keys_for_pricing_record,
    classify_buy_opportunity_status,
    compute_opportunity_metrics,
    risk_findings_for_opportunity,
    serialize_buy_opportunity,
    select_best_baseline_for_pricing_record,
    select_watch_target_for_pricing_record,
    stale_open_opportunity_ids,
    template_match_error_type_for_context,
    _json_safe_value,
)
from goofish_insight.compat import UTC
from goofish_insight.models import BuyOpportunity, BuyPriceBaseline, BuyWatchTarget


class BuyOpportunityServiceTests(unittest.TestCase):
    def test_baseline_keys_prefer_spec_then_product_then_brand(self) -> None:
        keys = baseline_keys_for_pricing_record(
            {
                "business_domain": "apple_computer",
                "category_code": "apple_computer",
                "spec_label": "MacBook Pro / M5 / 16G / 512G",
                "product_label": "MacBook Pro / M5",
                "brand": "Apple",
                "chip_family": "M5",
                "memory_gb": 16,
                "storage_gb": 512,
            }
        )

        self.assertEqual(
            keys,
            [
                ("template", "template:apple_computer|model_name=MacBook Pro / M5|chip_family=M5|memory_gb=16|storage_gb=512"),
                ("spec", "spec:MacBook Pro / M5 / 16G / 512G"),
                ("product", "product:MacBook Pro / M5"),
                ("brand", "brand:Apple"),
            ],
        )

    def test_select_best_baseline_falls_back_to_product(self) -> None:
        product_baseline = BuyPriceBaseline(
            id="baseline-product",
            category_id="cat-apple",
            baseline_key="product:MacBook Pro / M5",
            baseline_date=date(2026, 4, 8),
            sample_size=8,
            fair_price=Decimal("9000"),
            buy_ceiling=Decimal("8200"),
        )
        brand_baseline = BuyPriceBaseline(
            id="baseline-brand",
            category_id="cat-apple",
            baseline_key="brand:Apple",
            baseline_date=date(2026, 4, 8),
            sample_size=20,
            fair_price=Decimal("8800"),
            buy_ceiling=Decimal("8100"),
        )

        result = select_best_baseline_for_pricing_record(
            record={
                "spec_label": "MacBook Pro / M5 / 16G / 512G",
                "product_label": "MacBook Pro / M5",
                "brand": "Apple",
            },
            baselines_by_key={
                (None, "product:MacBook Pro / M5"): product_baseline,
                (None, "brand:Apple"): brand_baseline,
            },
        )

        self.assertIsNotNone(result)
        baseline, match_level, match_key = result
        self.assertIs(baseline, product_baseline)
        self.assertEqual(match_level, "degraded_product")
        self.assertEqual(match_key, "product:MacBook Pro / M5")

    def test_classify_buy_opportunity_status_requires_guidance_ready_template(self) -> None:
        self.assertEqual(
            classify_buy_opportunity_status(
                match_level="template",
                matched_template_key="apple_computer|model_name=MacBook Pro / M5|chip_family=M5|memory_gb=16|storage_gb=512",
                template_availability_tier="guidance_ready",
            ),
            "OPEN",
        )
        self.assertEqual(
            classify_buy_opportunity_status(
                match_level="degraded_product",
                matched_template_key="apple_computer|model_name=MacBook Pro / M5|chip_family=M5|memory_gb=16|storage_gb=512",
                template_availability_tier="guidance_ready",
            ),
            "REFERENCE_ONLY",
        )
        self.assertEqual(
            classify_buy_opportunity_status(
                match_level="spec",
                matched_template_key=None,
                template_availability_tier="guidance_ready",
            ),
            "REFERENCE_ONLY",
        )

    def test_template_match_error_type_for_context(self) -> None:
        self.assertEqual(
            template_match_error_type_for_context(
                match_level="degraded_product",
                matched_template_key="apple_computer|model_name=Mac mini / M4",
                template_availability_tier="guidance_ready",
            ),
            "degraded_product_match",
        )
        self.assertEqual(
            template_match_error_type_for_context(
                match_level="template",
                matched_template_key=None,
                template_availability_tier="guidance_ready",
            ),
            "missing_template_key",
        )
        self.assertEqual(
            template_match_error_type_for_context(
                match_level="template",
                matched_template_key="apple_computer|model_name=Mac mini / M4",
                template_availability_tier="reference_only",
            ),
            "availability_reference_only",
        )
        self.assertIsNone(
            template_match_error_type_for_context(
                match_level="template",
                matched_template_key="apple_computer|model_name=Mac mini / M4",
                template_availability_tier="guidance_ready",
            )
        )

    def test_template_gates_can_be_disabled_by_feature_flag(self) -> None:
        with patch(
            "goofish_analyzer.services.buy_opportunities.is_price_template_opportunity_enabled",
            return_value=False,
        ):
            self.assertEqual(
                classify_buy_opportunity_status(
                    match_level="degraded_product",
                    matched_template_key=None,
                    template_availability_tier="reference_only",
                ),
                "OPEN",
            )
            self.assertIsNone(
                template_match_error_type_for_context(
                    match_level="degraded_product",
                    matched_template_key=None,
                    template_availability_tier="reference_only",
                )
            )

    def test_select_best_baseline_prefers_template_key(self) -> None:
        template_baseline = BuyPriceBaseline(
            id="baseline-template",
            category_id="cat-apple",
            baseline_key="spec:MacBook Pro / M5 / 16G / 512G",
            baseline_date=date(2026, 4, 8),
            sample_size=8,
            fair_price=Decimal("9000"),
            buy_ceiling=Decimal("8200"),
        )

        result = select_best_baseline_for_pricing_record(
            record={
                "business_domain": "apple_computer",
                "category_code": "apple_computer",
                "spec_label": "MacBook Pro / M5 / 16G / 512G",
                "product_label": "MacBook Pro / M5",
                "brand": "Apple",
                "chip_family": "M5",
                "memory_gb": 16,
                "storage_gb": 512,
            },
            baselines_by_key={
                (None, "template:apple_computer|model_name=MacBook Pro / M5|chip_family=M5|memory_gb=16|storage_gb=512"): template_baseline,
            },
        )

        self.assertIsNotNone(result)
        baseline, match_level, match_key = result
        self.assertIs(baseline, template_baseline)
        self.assertEqual(match_level, "template")
        self.assertEqual(
            match_key,
            "template:apple_computer|model_name=MacBook Pro / M5|chip_family=M5|memory_gb=16|storage_gb=512",
        )

    def test_select_watch_target_prefers_specific_match(self) -> None:
        generic = BuyWatchTarget(
            id="target-generic",
            category_id="cat-apple",
            target_name="generic",
            profile_key="default",
            status="ACTIVE",
        )
        specific = BuyWatchTarget(
            id="target-specific",
            category_id="cat-apple",
            model_catalog_id="model-m5-pro",
            target_name="specific",
            profile_key="default",
            status="ACTIVE",
            desired_memory_gb=16,
        )

        target = select_watch_target_for_pricing_record(
            record={
                "model_catalog_id": "model-m5-pro",
                "memory_gb": 16,
                "storage_gb": 512,
            },
            watch_targets=[generic, specific],
        )

        self.assertIs(target, specific)

    def test_watch_target_supports_pricing_selector_metadata(self) -> None:
        selector_target = BuyWatchTarget(
            id="target-selector",
            category_id="cat-apple",
            target_name="selector",
            profile_key="default",
            status="ACTIVE",
            metadata_json={"pricingSelector": {"memory_gb": 16, "storage_gb": 512}},
        )

        target = select_watch_target_for_pricing_record(
            record={
                "business_domain": "apple_computer",
                "category_code": "apple_computer",
                "product_label": "MacBook Pro / M5",
                "memory_gb": 16,
                "storage_gb": 512,
            },
            watch_targets=[selector_target],
        )

        self.assertIs(target, selector_target)

    def test_compute_metrics_marks_good_price_opportunity(self) -> None:
        metrics = compute_opportunity_metrics(
            current_price=7800,
            fair_price=Decimal("9000"),
            buy_ceiling=Decimal("8200"),
            confidence=Decimal("0.82"),
            sample_size=8,
        )

        self.assertTrue(metrics["isPriceOpportunity"])
        self.assertGreater(metrics["discountRate"], Decimal("0.10"))
        self.assertGreater(metrics["opportunityScore"], 50)
        self.assertLess(metrics["riskScore"], 10)

    def test_risk_findings_include_low_sample_and_confidence(self) -> None:
        baseline = BuyPriceBaseline(
            category_id="cat-apple",
            baseline_key="spec:MacBook Pro / M5",
            baseline_date=date(2026, 4, 8),
            sample_size=2,
            confidence=Decimal("0.4"),
        )

        findings = risk_findings_for_opportunity(
            baseline=baseline,
            metrics={"riskScore": 45},
        )

        self.assertEqual(
            {finding["risk_code"] for finding in findings},
            {"LOW_SAMPLE_SIZE", "LOW_BASELINE_CONFIDENCE", "HIGH_COMPUTED_RISK"},
        )

    def test_json_safe_value_converts_datetime_and_decimal(self) -> None:
        payload = _json_safe_value(
            {
                "captured_at": datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
                "price": Decimal("12.34"),
            }
        )

        self.assertEqual(payload["captured_at"], "2026-04-08T12:00:00+00:00")
        self.assertEqual(payload["price"], 12.34)

    def test_stale_open_opportunity_ids_returns_rows_missing_from_latest_refresh(self) -> None:
        stale_ids = stale_open_opportunity_ids(
            rows=[
                ("opp-live", 101, "target-default"),
                ("opp-stale", 102, "target-default"),
                ("opp-other", 103, "target-other"),
            ],
            live_keys={
                (101, "target-default"),
                (103, "target-other"),
            },
        )

        self.assertEqual(stale_ids, ["opp-stale"])

    def test_serialize_buy_opportunity_surfaces_explanation_payloads(self) -> None:
        row = BuyOpportunity(
            id="opp-1",
            item_id_ref=101,
            watch_target_id="target-1",
            category_id="cat-1",
            status="OPEN",
            payload={
                "pricingEligibility": {"pricingReady": True},
                "specContract": {"status": "complete"},
                "feedbackSummary": {
                    "feedbackAction": "accept",
                    "feedbackCategory": "accepted_contacted",
                    "alertCandidateLinkage": {"status": "created"},
                },
            },
        )

        payload = serialize_buy_opportunity(row)

        self.assertEqual(payload["pricingEligibility"]["pricingReady"], True)
        self.assertEqual(payload["specContract"]["status"], "complete")
        self.assertEqual(payload["feedbackSummary"]["feedbackAction"], "accept")
        self.assertEqual(payload["feedbackSummary"]["feedbackCategory"], "accepted_contacted")
        self.assertEqual(payload["feedbackSummary"]["alertCandidateLinkage"]["status"], "created")


if __name__ == "__main__":
    unittest.main()
