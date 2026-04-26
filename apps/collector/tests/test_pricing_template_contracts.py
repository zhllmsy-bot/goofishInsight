from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from goofish_insight.application.services.pricing_templates import (
    annotate_visible_filter_fields,
    build_pricing_contract,
    build_template_key,
)
from goofish_insight.application.services.pricing_thresholds import (
    build_pricing_availability_summary,
    evaluate_pricing_availability,
)


def _template_detail(category_code: str, template_id: str, version: int, attribute_codes: list[str]) -> dict:
    return {
        "category": {"code": category_code, "id": f"cat-{category_code}"},
        "template": {"id": template_id, "version": version},
        "items": [{"attributeCode": code} for code in attribute_codes],
    }


class PricingTemplateContractTests(unittest.TestCase):
    def test_apple_contract_requires_screen_size_for_macbook(self) -> None:
        contract = build_pricing_contract(
            business_domain="apple_computer",
            selected_filters={
                "product_label": "MacBook Pro / 14in / M4 Pro",
                "chip_family": "M4 Pro",
                "screen_size_in": None,
                "memory_gb": 24,
                "storage_gb": 512,
            },
            filter_catalog={},
            template_detail=_template_detail(
                "apple_computer",
                "tpl-apple",
                1,
                ["model_name", "chip_family", "screen_size_in", "memory_gb", "storage_gb"],
            ),
        )

        self.assertEqual(contract["templateCompleteness"]["status"], "partial")
        self.assertIn("screen_size_in", contract["requiredPricingFields"])
        self.assertIn("screen_size_in", contract["missingPricingFields"])

    def test_garmin_contract_requires_variant_dimensions_when_multiple_options_exist(self) -> None:
        contract = build_pricing_contract(
            business_domain="garmin_watch",
            selected_filters={
                "product_label": "Fenix 8",
                "case_size_mm": 47,
                "display_type": None,
                "is_solar": None,
            },
            filter_catalog={
                "display_type_options": [{"value": "AMOLED"}, {"value": "MIP"}],
                "is_solar_options": [{"value": "true"}, {"value": "false"}],
            },
            template_detail=_template_detail(
                "garmin_watch",
                "tpl-garmin",
                1,
                ["model_name", "case_size_mm", "display_type", "is_solar"],
            ),
        )

        self.assertEqual(contract["templateCompleteness"]["status"], "partial")
        self.assertIn("display_type", contract["requiredPricingFields"])
        self.assertIn("is_solar", contract["requiredPricingFields"])

    def test_camera_contract_surfaces_unsupported_dashboard_fields(self) -> None:
        contract = build_pricing_contract(
            business_domain="camera_body",
            selected_filters={
                "product_label": "Sony A7C II",
                "spec_label": None,
            },
            filter_catalog={},
            template_detail=_template_detail(
                "camera_body",
                "tpl-camera",
                4,
                ["brand_name", "model_name", "mount_system", "sensor_format"],
            ),
        )

        self.assertEqual(contract["templateCompleteness"]["status"], "partial")
        self.assertIn("brand_name", contract["unsupportedPricingFields"])
        self.assertIn("mount_system", contract["unsupportedPricingFields"])
        self.assertIn("sensor_format", contract["unsupportedPricingFields"])

    def test_visible_filter_fields_are_annotated_with_pricing_role(self) -> None:
        fields = [
            {"key": "product_label", "label": "产品"},
            {"key": "chip_family", "label": "芯片"},
            {"key": "memory_gb", "label": "内存"},
            {"key": "storage_gb", "label": "硬盘"},
            {"key": "spec_label", "label": "精确规格"},
        ]
        contract = build_pricing_contract(
            business_domain="apple_computer",
            selected_filters={
                "product_label": "Mac mini / M4",
                "chip_family": "M4",
                "memory_gb": 16,
                "storage_gb": 256,
                "screen_size_in": None,
            },
            filter_catalog={},
            template_detail=_template_detail(
                "apple_computer",
                "tpl-apple",
                1,
                ["model_name", "chip_family", "memory_gb", "storage_gb"],
            ),
        )

        annotated = annotate_visible_filter_fields(fields, pricing_contract=contract)
        roles = {row["key"]: row["pricingRole"] for row in annotated}

        self.assertEqual(roles["product_label"], "required")
        self.assertEqual(roles["chip_family"], "required")
        self.assertEqual(roles["memory_gb"], "required")
        self.assertEqual(roles["storage_gb"], "required")
        self.assertIsNone(roles["spec_label"])

    def test_complete_contract_exposes_template_key_preview(self) -> None:
        contract = build_pricing_contract(
            business_domain="apple_computer",
            selected_filters={
                "product_label": "Mac mini / M4",
                "chip_family": "M4",
                "memory_gb": 16,
                "storage_gb": 256,
                "screen_size_in": None,
            },
            filter_catalog={},
            template_detail=_template_detail(
                "apple_computer",
                "tpl-apple",
                1,
                ["model_name", "chip_family", "memory_gb", "storage_gb"],
            ),
        )

        self.assertEqual(
            contract["templateKeyPreview"],
            "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=16|storage_gb=256",
        )

    def test_build_template_key_normalizes_boolean_and_whitespace(self) -> None:
        key = build_template_key(
            category_code="garmin_watch",
            pricing_key_fields=("model_name", "case_size_mm", "is_solar"),
            selected_values={
                "model_name": " Fenix   8 ",
                "case_size_mm": 47,
                "is_solar": True,
            },
        )

        self.assertEqual(
            key,
            "garmin_watch|model_name=Fenix 8|case_size_mm=47|is_solar=true",
        )

    def test_build_pricing_contract_returns_legacy_when_feature_flag_disabled(self) -> None:
        with patch(
            "goofish_insight.application.services.pricing_templates.is_price_template_contract_enabled",
            return_value=False,
        ):
            contract = build_pricing_contract(
                business_domain="apple_computer",
                selected_filters={
                    "product_label": "Mac mini / M4",
                    "chip_family": "M4",
                    "memory_gb": 16,
                    "storage_gb": 256,
                },
                filter_catalog={},
                template_detail=_template_detail(
                    "apple_computer",
                    "tpl-apple",
                    1,
                    ["model_name", "chip_family", "memory_gb", "storage_gb"],
                ),
            )
        self.assertEqual(contract["contractSource"], "legacy_feature_flag_disabled")
        self.assertEqual(contract["templateCompleteness"]["status"], "legacy")
        self.assertTrue(contract["templateCompleteness"]["isComplete"])

    def test_pricing_thresholds_gate_guidance_ready(self) -> None:
        payload = evaluate_pricing_availability(
            template_complete=True,
            seller_sample_count=6,
            unique_seller_count=4,
            exact_spec_ratio=0.92,
            reliability_score=75.0,
            latest_seen_at=datetime(2026, 4, 9, 12, 0, tzinfo=UTC),
            as_of=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(payload["availabilityTier"], "guidance_ready")
        self.assertTrue(payload["pricingAvailable"])

    def test_pricing_thresholds_block_incomplete_templates(self) -> None:
        payload = evaluate_pricing_availability(
            template_complete=False,
            seller_sample_count=10,
            unique_seller_count=5,
            exact_spec_ratio=0.95,
            reliability_score=88.0,
            latest_seen_at=datetime(2026, 4, 9, 12, 0, tzinfo=UTC),
            as_of=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(payload["availabilityTier"], "incomplete")
        self.assertEqual(payload["pricingBlockReason"], "template_incomplete")

    def test_pricing_thresholds_include_human_readable_summary(self) -> None:
        payload = evaluate_pricing_availability(
            template_complete=True,
            seller_sample_count=2,
            unique_seller_count=1,
            exact_spec_ratio=0.40,
            reliability_score=58.0,
            latest_seen_at=datetime(2026, 4, 9, 12, 0, tzinfo=UTC),
            as_of=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(payload["pricingBlockReasonLabel"], "卖家样本数不足")
        self.assertEqual(payload["pricingSummary"]["readinessSummary"], "暂不建议引用：卖家样本数不足")

    def test_build_pricing_availability_summary_marks_guidance_ready(self) -> None:
        summary = build_pricing_availability_summary(
            availability_tier="guidance_ready",
            pricing_block_reason=None,
            evidence={
                "sellerSampleCount": 7,
                "reliabilityScore": 82.0,
                "effectiveSampleCount": 6.5,
                "recencyWeightedSampleCount": 5.4,
                "mad": 180.0,
                "confidenceScore": 82.0,
                "confidenceReasons": ["样本充足", "价格离群较少"],
                "qualityTier": "B",
                "p15Price": 7600.0,
                "p35Price": 8200.0,
                "p50Price": 8800.0,
            },
        )

        self.assertEqual(summary["readinessSummary"], "可直接按价格指导口径使用")
        self.assertEqual(summary["sellerSampleCount"], 7)
        self.assertEqual(summary["effectiveSampleCount"], 6.5)
        self.assertEqual(summary["qualityTier"], "B")
        self.assertEqual(summary["confidenceReasons"], ["样本充足", "价格离群较少"])


if __name__ == "__main__":
    unittest.main()
