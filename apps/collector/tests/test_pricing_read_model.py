from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from goofish_insight.application.services.pricing_read_model import (
    get_baseline_explanation_read_model,
    get_pricing_record_read_model,
    get_pricing_contract_read_model,
    get_template_guidance_read_model,
)
from goofish_insight.models import BuyPriceBaseline


class PricingReadModelTests(unittest.TestCase):
    def test_pricing_record_read_model_includes_template_snapshot_fields(self) -> None:
        record = get_pricing_record_read_model(
            session=None,
            record={
                "category_code": "apple_computer",
                "product_label": "Mac mini / M4",
                "memory_gb": 16,
                "storage_gb": 256,
                "chip_family": "M4",
            },
        )

        self.assertEqual(record["template_key"], "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=16|storage_gb=256")
        self.assertEqual(record["template_label"], "Mac mini / M4")
        self.assertEqual(record["template_availability_tier"], "complete")
        self.assertEqual(record["template_snapshot"]["resolvedFieldValues"]["chip_family"], "M4")

    def test_baseline_explanation_read_model_uses_payload_backing_fields(self) -> None:
        baseline = BuyPriceBaseline(
            id="baseline-1",
            category_id="cat-1",
            model_catalog_id="model-1",
            baseline_key="apple_computer|model_name=Mac mini / M4",
            baseline_date=date(2026, 4, 20),
            fair_price=Decimal("3999.00"),
            median_price=Decimal("4200.00"),
            sample_size=6,
            confidence=Decimal("0.8200"),
            payload={
                "windowDays": 30,
                "missingRate": 0.125,
                "resolvedFields": {"model_name": "Mac mini / M4", "chip_family": "M4"},
                "missingFields": ["screen_size_in"],
                "pricingContract": {"templateKey": "apple_computer|model_name=Mac mini / M4"},
                "computedAt": "2026-04-20T00:00:00+00:00",
                "isActive": True,
                "version": 3,
                "pricingTemplate": {
                    "availability": {
                        "availabilityTier": "guidance_ready",
                        "pricingEvidence": {
                            "sellerSampleCount": 6,
                            "uniqueSellerCount": 4,
                            "exactSpecRatio": 0.9,
                            "reliabilityScore": 84.0,
                            "effectiveSampleCount": 5.7,
                            "recencyWeightedSampleCount": 4.9,
                            "mad": 180.0,
                            "confidenceScore": 84.0,
                            "confidenceReasons": ["样本充足", "价格离群较少"],
                            "qualityTier": "B",
                            "p15Price": 3600.0,
                            "p35Price": 3999.0,
                            "p50Price": 4200.0,
                            "freshnessDays": 2,
                        },
                    }
                },
                "pricing_row": {
                    "effective_sample_count": 5.7,
                    "recency_weighted_sample_count": 4.9,
                    "mad": 180.0,
                    "confidence_score": 84.0,
                    "confidence_reasons": ["样本充足", "价格离群较少"],
                    "quality_tier": "B",
                    "p15_price": 3600.0,
                    "p35_price": 3999.0,
                    "p50_price": 4200.0,
                },
            },
        )

        read_model = get_baseline_explanation_read_model(session=None, baseline=baseline)

        self.assertEqual(read_model["window_days"], 30)
        self.assertEqual(read_model["missing_rate"], 0.125)
        self.assertEqual(read_model["resolved_fields"]["chip_family"], "M4")
        self.assertEqual(read_model["missing_fields"], ["screen_size_in"])
        self.assertEqual(read_model["pricing_contract"]["templateKey"], "apple_computer|model_name=Mac mini / M4")
        self.assertEqual(read_model["computed_at"], "2026-04-20T00:00:00+00:00")
        self.assertEqual(read_model["is_active"], True)
        self.assertEqual(read_model["version"], 3)
        self.assertEqual(read_model["explanation"]["availabilityTier"], "guidance_ready")
        self.assertEqual(read_model["explanation"]["qualityTier"], "B")
        self.assertEqual(read_model["explanation"]["effectiveSampleCount"], 5.7)
        self.assertEqual(read_model["explanation"]["confidenceReasons"], ["样本充足", "价格离群较少"])

    def test_template_guidance_read_model_exposes_contract_subset(self) -> None:
        read_model = get_template_guidance_read_model(
            session=None,
            business_domain="apple_computer",
            selected_filters={
                "product_label": "Mac mini / M4",
                "chip_family": "M4",
                "memory_gb": 16,
                "storage_gb": 256,
            },
            filter_catalog={},
        )

        self.assertEqual(read_model["category_code"], "apple_computer")
        self.assertEqual(read_model["template_key"], "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=16|storage_gb=256")
        self.assertIsNone(read_model["template_label"])
        self.assertEqual(read_model["required_pricing_fields"], ["model_name", "chip_family", "memory_gb", "storage_gb"])
        self.assertEqual(read_model["missing_fields"], [])
        self.assertEqual(read_model["completeness_status"], "complete")

    def test_pricing_contract_read_model_returns_full_contract(self) -> None:
        read_model = get_pricing_contract_read_model(
            session=None,
            business_domain="apple_computer",
            selected_filters={
                "product_label": "Mac mini / M4",
                "chip_family": "M4",
                "memory_gb": 16,
                "storage_gb": 256,
            },
            filter_catalog={},
        )

        self.assertEqual(read_model["categoryCode"], "apple_computer")
        self.assertEqual(read_model["templateCompleteness"]["status"], "complete")
        self.assertEqual(read_model["missingPricingFields"], [])


if __name__ == "__main__":
    unittest.main()
