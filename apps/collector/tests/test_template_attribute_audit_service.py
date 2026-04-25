from __future__ import annotations

import unittest
from unittest.mock import Mock

from goofish_insight.application.services.template_attribute_audit import (
    _merge_template_items,
    _missing_supplements_for_category,
    _resolve_target_category_codes,
)


class TemplateAttributeAuditServiceTests(unittest.TestCase):
    def test_lens_template_reports_missing_lens_series(self) -> None:
        missing = _missing_supplements_for_category(
            category_code="camera_interchangeable_lens",
            prompt_profile="camera_interchangeable_lens_extract_v1",
            current_codes={"brand_name", "model_name", "mount_system", "focal_length_range", "max_aperture"},
        )

        self.assertEqual([item.template_item["attributeCode"] for item in missing], ["lens_series", "generation"])

    def test_camera_body_template_reports_missing_product_line(self) -> None:
        missing = _missing_supplements_for_category(
            category_code="camera_body",
            prompt_profile="camera_body_extract_v1",
            current_codes={"brand_name", "model_name", "mount_system", "sensor_format", "pixel_resolution", "camera_type", "generation"},
        )

        self.assertEqual([item.template_item["attributeCode"] for item in missing], ["product_line"])

    def test_phone_template_reports_missing_canonical_fields(self) -> None:
        missing = _missing_supplements_for_category(
            category_code="phone",
            prompt_profile="smartphone_extract_v1",
            current_codes={"brand_name", "model_name", "generation", "memory_size", "color", "screen_size"},
        )

        self.assertEqual(
            [item.template_item["attributeCode"] for item in missing],
            ["product_line", "memory_gb", "storage_gb", "screen_size_in"],
        )

    def test_merge_template_items_appends_missing_codes_without_replacing_existing_items(self) -> None:
        current_items = [
            {"attributeCode": "brand_name", "isRequired": True, "isFilter": True, "isSearch": True, "isDisplay": True, "sortNo": 10},
            {"attributeCode": "model_name", "isRequired": True, "isFilter": True, "isSearch": True, "isDisplay": True, "sortNo": 20},
        ]
        missing = _missing_supplements_for_category(
            category_code="camera_interchangeable_lens",
            prompt_profile="camera_interchangeable_lens_extract_v1",
            current_codes={"brand_name", "model_name"},
        )

        merged = _merge_template_items(current_items=current_items, missing=missing)

        self.assertEqual(
            [item["attributeCode"] for item in merged],
            ["brand_name", "model_name", "lens_series", "generation"],
        )
        self.assertTrue(any(item["attributeCode"] == "lens_series" and item["sortNo"] == 70 for item in merged))
        self.assertTrue(any(item["attributeCode"] == "generation" and item["sortNo"] == 80 for item in merged))

    def test_prompt_profile_can_supply_missing_attributes_even_when_category_mapping_is_not_present(self) -> None:
        missing = _missing_supplements_for_category(
            category_code="some_future_phone_category",
            prompt_profile="smartphone_extract_v1",
            current_codes={"brand_name", "model_name"},
        )

        self.assertEqual(
            [item.template_item["attributeCode"] for item in missing],
            ["product_line", "memory_gb", "storage_gb", "screen_size_in"],
        )

    def test_resolve_target_category_codes_uses_db_discovery_when_not_explicit(self) -> None:
        session = Mock()
        execute_result = Mock()
        execute_result.scalars.return_value.all.return_value = ["apple_computer", "phone"]
        session.execute.return_value = execute_result

        result = _resolve_target_category_codes(session, category_codes=None)

        self.assertEqual(result, ("apple_computer", "phone"))
        session.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
