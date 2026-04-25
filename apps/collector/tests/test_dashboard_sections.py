from __future__ import annotations

import unittest
from unittest.mock import patch
from decimal import Decimal

from goofish_insight.application.services.dashboard_sections import (
    DashboardSectionOptions,
    build_dashboard_base_context,
    build_dashboard_hero_section_data,
)
from goofish_insight.application.services.dashboard_queries import (
    _build_catalog_pricing_record,
    dashboard_pricing_read_cache_signature,
)


class DashboardSectionsTests(unittest.TestCase):
    def test_catalog_pricing_record_builds_apple_dimensions_and_labels(self) -> None:
        spu = unittest.mock.Mock()
        spu.id = "spu-apple-1"
        spu.category_id = "cat-apple"
        spu.template_id = "tpl-apple"
        spu.merchant_id = "seller-1"
        spu.brand_id = "Apple"
        spu.title = "MacBook Pro"
        spu.created_at = None
        spu.updated_at = None
        spu.attr_snapshot_json = {
            "attributes": [
                {"attributeCode": "product_line", "valueType": "TEXT", "value": "MacBook Pro"},
                {"attributeCode": "model_name", "valueType": "TEXT", "value": "M3 Pro"},
                {"attributeCode": "chip_family", "valueType": "TEXT", "value": "M3"},
                {"attributeCode": "screen_size_in", "valueType": "NUMBER", "value": 14},
            ]
        }
        sku = unittest.mock.Mock()
        sku.sku_code = "SKU-APPLE-1"
        sku.price = 9999
        sku.updated_at = None
        sku.attr_snapshot_json = {
            "attributes": [
                {"attributeCode": "memory_gb", "valueType": "NUMBER", "value": 18},
                {"attributeCode": "storage_gb", "valueType": "NUMBER", "value": 512},
            ],
            "saleAttributes": [],
        }

        record = _build_catalog_pricing_record(
            spu=spu,
            sku=sku,
            category_code="apple_computer",
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["business_domain"], "apple_computer")
        self.assertEqual(record["brand"], "Apple")
        self.assertEqual(record["memory_gb"], 18)
        self.assertEqual(record["storage_gb"], 512)
        self.assertTrue(record["product_label"])
        self.assertTrue(record["spec_label"])

    def test_catalog_pricing_record_rejects_apple_watch_in_apple_computer(self) -> None:
        spu = unittest.mock.Mock()
        spu.id = "spu-apple-watch-1"
        spu.category_id = "cat-apple"
        spu.template_id = "tpl-apple"
        spu.merchant_id = "seller-1"
        spu.brand_id = "Apple"
        spu.title = "Apple Watch Series 10"
        spu.created_at = None
        spu.updated_at = None
        spu.attr_snapshot_json = {
            "attributes": [
                {"attributeCode": "model_name", "valueType": "TEXT", "value": "Apple Watch Series 10"},
                {"attributeCode": "screen_size_in", "valueType": "NUMBER", "value": 46},
            ]
        }
        sku = unittest.mock.Mock()
        sku.sku_code = "SKU-WATCH-1"
        sku.price = 1600
        sku.updated_at = None
        sku.attr_snapshot_json = {"attributes": [], "saleAttributes": []}

        record = _build_catalog_pricing_record(
            spu=spu,
            sku=sku,
            category_code="apple_computer",
        )

        self.assertIsNone(record)

    def test_catalog_pricing_record_normalizes_messy_apple_product_line(self) -> None:
        spu = unittest.mock.Mock()
        spu.id = "spu-apple-2"
        spu.category_id = "cat-apple"
        spu.template_id = "tpl-apple"
        spu.merchant_id = "seller-2"
        spu.brand_id = "Apple"
        spu.title = "Mac mini M4"
        spu.created_at = None
        spu.updated_at = None
        spu.attr_snapshot_json = {
            "attributes": [
                {"attributeCode": "product_line", "valueType": "TEXT", "value": "Mac mini M4"},
                {"attributeCode": "model_name", "valueType": "TEXT", "value": "Mac mini M4"},
                {"attributeCode": "chip_family", "valueType": "TEXT", "value": "M4"},
            ]
        }
        sku = unittest.mock.Mock()
        sku.sku_code = "SKU-APPLE-2"
        sku.price = 3999
        sku.updated_at = None
        sku.attr_snapshot_json = {
            "attributes": [
                {"attributeCode": "memory_gb", "valueType": "NUMBER", "value": 16},
                {"attributeCode": "storage_gb", "valueType": "NUMBER", "value": 256},
            ],
            "saleAttributes": [],
        }

        record = _build_catalog_pricing_record(
            spu=spu,
            sku=sku,
            category_code="apple_computer",
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["product_line"], "Mac mini")
        self.assertEqual(record["product_label"], "Mac mini / M4")

    def test_catalog_pricing_record_normalizes_apple_screen_bucket_and_chip_family(self) -> None:
        spu = unittest.mock.Mock()
        spu.id = "spu-apple-2b"
        spu.category_id = "cat-apple"
        spu.template_id = "tpl-apple"
        spu.merchant_id = "seller-2b"
        spu.brand_id = "Apple"
        spu.title = "MacBook Pro 14.3in"
        spu.created_at = None
        spu.updated_at = None
        spu.attr_snapshot_json = {
            "attributes": [
                {"attributeCode": "product_line", "valueType": "TEXT", "value": "MacBook Pro"},
                {"attributeCode": "model_name", "valueType": "TEXT", "value": "MacBook Pro 14.3in"},
                {"attributeCode": "chip_family", "valueType": "TEXT", "value": "Apple M4 Pro"},
                {"attributeCode": "screen_size_in", "valueType": "NUMBER", "value": Decimal("14.3")},
            ]
        }
        sku = unittest.mock.Mock()
        sku.sku_code = "SKU-APPLE-2B"
        sku.price = 8999
        sku.updated_at = None
        sku.attr_snapshot_json = {
            "attributes": [
                {"attributeCode": "memory_gb", "valueType": "NUMBER", "value": 18},
                {"attributeCode": "storage_gb", "valueType": "NUMBER", "value": 512},
            ],
            "saleAttributes": [],
        }

        record = _build_catalog_pricing_record(
            spu=spu,
            sku=sku,
            category_code="apple_computer",
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["chip_family"], "M4 Pro")
        self.assertEqual(record["screen_size_in"], 14.0)
        self.assertEqual(record["product_label"], "MacBook Pro / 14in / M4 Pro")
        self.assertEqual(record["spec_label"], "MacBook Pro / 14in / M4 Pro / 18G / 512G")

    def test_catalog_pricing_record_rejects_invalid_macbook_air_chip_or_screen(self) -> None:
        base_spu = unittest.mock.Mock()
        base_spu.category_id = "cat-apple"
        base_spu.template_id = "tpl-apple"
        base_spu.merchant_id = "seller-air"
        base_spu.brand_id = "Apple"
        base_spu.created_at = None
        base_spu.updated_at = None
        base_sku = unittest.mock.Mock()
        base_sku.sku_code = "SKU-AIR-1"
        base_sku.price = 6999
        base_sku.updated_at = None
        base_sku.attr_snapshot_json = {
            "attributes": [
                {"attributeCode": "memory_gb", "valueType": "NUMBER", "value": 16},
                {"attributeCode": "storage_gb", "valueType": "NUMBER", "value": 512},
            ],
            "saleAttributes": [],
        }

        invalid_cases = (
            {
                "spu_id": "spu-air-pro-chip",
                "title": "MacBook Air 13in M4 Pro",
                "screen_size": 13,
                "chip_family": "M4 Pro",
            },
            {
                "spu_id": "spu-air-24in",
                "title": "MacBook Air 24in M3",
                "screen_size": 24,
                "chip_family": "M3",
            },
        )
        for case in invalid_cases:
            spu = unittest.mock.Mock()
            spu.id = case["spu_id"]
            spu.category_id = base_spu.category_id
            spu.template_id = base_spu.template_id
            spu.merchant_id = base_spu.merchant_id
            spu.brand_id = base_spu.brand_id
            spu.title = case["title"]
            spu.created_at = base_spu.created_at
            spu.updated_at = base_spu.updated_at
            spu.attr_snapshot_json = {
                "attributes": [
                    {"attributeCode": "product_line", "valueType": "TEXT", "value": "MacBook Air"},
                    {"attributeCode": "model_name", "valueType": "TEXT", "value": case["title"]},
                    {"attributeCode": "chip_family", "valueType": "TEXT", "value": case["chip_family"]},
                    {"attributeCode": "screen_size_in", "valueType": "NUMBER", "value": case["screen_size"]},
                ]
            }

            record = _build_catalog_pricing_record(
                spu=spu,
                sku=base_sku,
                category_code="apple_computer",
            )

            self.assertIsNone(record)

    def test_catalog_pricing_record_rejects_messy_apple_title_without_product_line_match(self) -> None:
        spu = unittest.mock.Mock()
        spu.id = "spu-apple-3"
        spu.category_id = "cat-apple"
        spu.template_id = "tpl-apple"
        spu.merchant_id = "seller-3"
        spu.brand_id = "Apple"
        spu.title = "M4 16GB 256GB 感兴趣的话点我想要"
        spu.created_at = None
        spu.updated_at = None
        spu.attr_snapshot_json = {
            "attributes": [
                {"attributeCode": "product_line", "valueType": "TEXT", "value": "M4 16GB 256GB 感兴趣的话点我想要"},
                {"attributeCode": "model_name", "valueType": "TEXT", "value": "M4 16GB 256GB 感兴趣的话点我想要"},
                {"attributeCode": "chip_family", "valueType": "TEXT", "value": "M4"},
            ]
        }
        sku = unittest.mock.Mock()
        sku.sku_code = "SKU-APPLE-3"
        sku.price = 3999
        sku.updated_at = None
        sku.attr_snapshot_json = {"attributes": [], "saleAttributes": []}

        record = _build_catalog_pricing_record(
            spu=spu,
            sku=sku,
            category_code="apple_computer",
        )

        self.assertIsNone(record)

    def test_dashboard_pricing_read_cache_signature_reflects_env(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "DASHBOARD_PRICING_READ_MODE": "catalog_primary",
                "DASHBOARD_PRICING_LEGACY_FALLBACK_ENABLED": "false",
            },
            clear=False,
        ):
            signature = dashboard_pricing_read_cache_signature()

        self.assertEqual(signature, ("catalog_primary", False))

    def test_base_context_uses_freshness_window_for_pricing_records(self) -> None:
        options = DashboardSectionOptions(
            business_domain="apple_computer",
            limit=36,
            pricing_view="product",
            pricing_scope="actionable",
            pricing_limit=12,
            pricing_freshness_days=30,
            heartbeat_days=3,
            pricing_min_samples=4,
            raw_filters={},
        )

        normalized_filters = {
            "product_label": None,
            "spec_label": None,
            "display_type": None,
            "case_size_mm": None,
            "is_solar": None,
            "chip_family": None,
            "screen_size_in": None,
            "memory_gb": None,
            "storage_gb": None,
        }

        with (
            patch(
                "goofish_insight.application.services.dashboard_sections.get_ttl_cached_payload",
                side_effect=lambda **kwargs: kwargs["builder"](),
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections._normalize_selected_filters",
                return_value=normalized_filters,
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.load_dashboard_pricing_records",
                return_value={
                    "records": [],
                    "readMode": "catalog_primary",
                    "readSource": "catalog",
                    "fallbackUsed": False,
                    "fallbackReason": None,
                    "catalogRecordCount": 0,
                    "legacyRecordCount": 0,
                    "legacyFallbackEnabled": True,
                },
            ) as load_records_mock,
            patch(
                "goofish_insight.application.services.dashboard_sections.build_filter_catalog",
                return_value={},
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.build_visible_filter_fields",
                return_value=[],
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.build_pricing_contract",
                return_value={"templateCompleteness": {"isComplete": False}},
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.annotate_visible_filter_fields",
                return_value=[],
            ),
        ):
            payload = build_dashboard_base_context(object(), options=options)

        self.assertEqual(payload["pricing_records"], [])
        load_records_mock.assert_called_once()
        self.assertEqual(load_records_mock.call_args.kwargs["business_domain"], "apple_computer")
        self.assertEqual(load_records_mock.call_args.kwargs["category_code"], "apple_computer")
        self.assertEqual(load_records_mock.call_args.kwargs["freshness_days"], 30)
        self.assertIsNone(load_records_mock.call_args.kwargs["heartbeat_days"])
        self.assertEqual(payload["pricing_read_source"], "catalog")
        self.assertFalse(payload["pricing_fallback_used"])

    def test_base_context_keeps_legacy_scope_but_calls_pricing_with_canonical_category(self) -> None:
        options = DashboardSectionOptions(
            business_domain="apple_m_series",
            limit=36,
            pricing_view="product",
            pricing_scope="actionable",
            pricing_limit=12,
            pricing_freshness_days=30,
            heartbeat_days=3,
            pricing_min_samples=4,
            raw_filters={},
        )

        normalized_filters = {
            "product_label": None,
            "spec_label": None,
            "display_type": None,
            "case_size_mm": None,
            "is_solar": None,
            "chip_family": None,
            "screen_size_in": None,
            "memory_gb": None,
            "storage_gb": None,
        }

        with (
            patch(
                "goofish_insight.application.services.dashboard_sections.get_ttl_cached_payload",
                side_effect=lambda **kwargs: kwargs["builder"](),
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections._normalize_selected_filters",
                return_value=normalized_filters,
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.load_dashboard_pricing_records",
                return_value={
                    "records": [],
                    "readMode": "dual",
                    "readSource": "legacy",
                    "fallbackUsed": True,
                    "fallbackReason": "catalog_empty",
                    "catalogRecordCount": 0,
                    "legacyRecordCount": 12,
                    "legacyFallbackEnabled": True,
                },
            ) as load_records_mock,
            patch(
                "goofish_insight.application.services.dashboard_sections.build_filter_catalog",
                return_value={},
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.build_visible_filter_fields",
                return_value=[],
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.build_pricing_contract",
                return_value={"templateCompleteness": {"isComplete": False}},
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.annotate_visible_filter_fields",
                return_value=[],
            ),
        ):
            build_dashboard_base_context(object(), options=options)

        load_records_mock.assert_called_once()
        self.assertEqual(load_records_mock.call_args.kwargs["business_domain"], "apple_m_series")
        self.assertEqual(load_records_mock.call_args.kwargs["category_code"], "apple_computer")

    def test_base_context_exposes_read_mode_and_fallback_metadata(self) -> None:
        options = DashboardSectionOptions(
            business_domain="garmin",
            limit=36,
            pricing_view="product",
            pricing_scope="actionable",
            pricing_limit=12,
            pricing_freshness_days=30,
            heartbeat_days=3,
            pricing_min_samples=4,
            raw_filters={},
        )
        normalized_filters = {
            "product_label": None,
            "spec_label": None,
            "display_type": None,
            "case_size_mm": None,
            "is_solar": None,
            "chip_family": None,
            "screen_size_in": None,
            "memory_gb": None,
            "storage_gb": None,
        }
        with (
            patch(
                "goofish_insight.application.services.dashboard_sections.get_ttl_cached_payload",
                side_effect=lambda **kwargs: kwargs["builder"](),
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections._normalize_selected_filters",
                return_value=normalized_filters,
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.load_dashboard_pricing_records",
                return_value={
                    "records": [],
                    "readMode": "dual",
                    "readSource": "legacy",
                    "fallbackUsed": True,
                    "fallbackReason": "catalog_empty",
                    "catalogRecordCount": 0,
                    "legacyRecordCount": 8,
                    "legacyFallbackEnabled": True,
                },
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.build_filter_catalog",
                return_value={},
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.build_visible_filter_fields",
                return_value=[],
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.build_pricing_contract",
                return_value={"templateCompleteness": {"isComplete": False}},
            ),
            patch(
                "goofish_insight.application.services.dashboard_sections.annotate_visible_filter_fields",
                return_value=[],
            ),
        ):
            payload = build_dashboard_base_context(object(), options=options)

        self.assertEqual(payload["pricing_read_mode"], "dual")
        self.assertEqual(payload["pricing_read_source"], "legacy")
        self.assertTrue(payload["pricing_fallback_used"])
        self.assertEqual(payload["pricing_fallback_reason"], "catalog_empty")
        self.assertEqual(payload["pricing_legacy_record_count"], 8)

    def test_hero_section_reports_canonical_category_code_for_legacy_scope(self) -> None:
        options = DashboardSectionOptions(
            business_domain="apple_m_series",
            limit=36,
            pricing_view="product",
            pricing_scope="actionable",
            pricing_limit=12,
            pricing_freshness_days=30,
            heartbeat_days=3,
            pricing_min_samples=4,
            raw_filters={},
        )

        with patch(
            "goofish_insight.application.services.dashboard_sections.build_dashboard_overview_context",
            return_value={"overview": {"total_items": 12}},
        ):
            payload = build_dashboard_hero_section_data(object(), options=options)

        self.assertEqual(payload["selected_domain"], "apple_m_series")
        self.assertEqual(payload["selected_category_code"], "apple_computer")


if __name__ == "__main__":
    unittest.main()
