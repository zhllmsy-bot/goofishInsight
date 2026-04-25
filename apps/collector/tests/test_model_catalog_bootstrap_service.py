from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight.application.services.model_catalog_bootstrap import (
    _normalize_bootstrap_row,
    _parse_apple_title_bootstrap_row,
    apply_model_catalog_bootstrap,
    preview_model_catalog_bootstrap_with_session,
)
from goofish_insight.models import Category


class _FakeCategoryExecuteResult:
    def __init__(self, category: Category | None) -> None:
        self._category = category

    def scalar_one_or_none(self) -> Category | None:
        return self._category


class _FakeSession:
    def __init__(self, category: Category | None) -> None:
        self.category = category

    def execute(self, stmt):
        return _FakeCategoryExecuteResult(self.category)


class ModelCatalogBootstrapServiceTests(unittest.TestCase):
    def test_preview_model_catalog_bootstrap_filters_listing_copy(self) -> None:
        category = Category(
            id="33333333-3333-3333-3333-333333333101",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        session = _FakeSession(category)

        with patch(
            "goofish_insight.application.services.model_catalog_bootstrap._load_bootstrap_rows",
            return_value=[
                {
                    "modelName": "MacBook Air M2 8G 256G",
                    "seriesName": "MacBook Air",
                    "chipFamily": "M2",
                    "memoryGb": 8,
                    "storageGb": 256,
                    "sampleCount": 120,
                    "lastSeenAt": "2026-04-11T09:00:00+08:00",
                },
                {
                    "modelName": "MacBook Air M2 8G 256G 包邮私聊",
                    "seriesName": "MacBook Air",
                    "chipFamily": "M2",
                    "memoryGb": 8,
                    "storageGb": 256,
                    "sampleCount": 35,
                    "lastSeenAt": "2026-04-11T09:00:00+08:00",
                },
            ],
        ):
            detail = preview_model_catalog_bootstrap_with_session(
                session,
                business_domain="apple_computer",
                min_sample_count=20,
                active_only=True,
            )

        self.assertEqual(detail["canonicalCategoryCode"], "apple_computer")
        self.assertEqual(detail["acceptedCount"], 1)
        self.assertEqual(detail["rejectedCount"], 1)
        self.assertEqual(detail["items"][0]["brandName"], "Apple")
        self.assertEqual(detail["items"][0]["modelName"], "MacBook Air M2 8G 256G")
        self.assertEqual(detail["rejections"][0]["reason"], "contains_listing_copy")

    def test_apply_model_catalog_bootstrap_forwards_preview_items(self) -> None:
        preview_payload = {
            "businessDomain": "garmin_watch",
            "canonicalCategoryCode": "garmin_watch",
            "minSampleCount": 20,
            "activeOnly": True,
            "nameQuery": None,
            "candidateCount": 1,
            "acceptedCount": 1,
            "rejectedCount": 0,
            "items": [{"modelCode": "garmin_watch_fenix_8", "modelName": "Fenix 8"}],
            "rejections": [],
        }
        with patch(
            "goofish_insight.application.services.model_catalog_bootstrap.preview_model_catalog_bootstrap",
            return_value=preview_payload,
        ), patch(
            "goofish_insight.application.services.model_catalog_bootstrap.import_model_configs",
            return_value={"importedCount": 1},
        ) as import_mock:
            detail = apply_model_catalog_bootstrap(
                business_domain="garmin_watch",
                operator_id="ops-bot",
                min_sample_count=20,
                dry_run=True,
            )

        self.assertEqual(detail["canonicalCategoryCode"], "garmin_watch")
        self.assertEqual(detail["import"]["importedCount"], 1)
        import_mock.assert_called_once_with(
            payload={"items": preview_payload["items"]},
            operator_id="ops-bot",
            dry_run=True,
        )

    def test_preview_model_catalog_bootstrap_applies_name_query(self) -> None:
        category = Category(
            id="22222222-2222-2222-2222-222222222101",
            code="garmin_watch",
            name="Garmin手表",
            path="wearables/garmin-watch",
            level=2,
            status="ACTIVE",
        )
        session = _FakeSession(category)

        with patch(
            "goofish_insight.application.services.model_catalog_bootstrap._load_bootstrap_rows",
            return_value=[
                {
                    "modelName": "Fenix 8 AMOLED",
                    "seriesName": "Fenix",
                    "chipFamily": None,
                    "memoryGb": None,
                    "storageGb": None,
                    "sampleCount": 103,
                    "lastSeenAt": "2026-04-11T09:00:00+08:00",
                },
                {
                    "modelName": "Forerunner 265",
                    "seriesName": "Forerunner",
                    "chipFamily": None,
                    "memoryGb": None,
                    "storageGb": None,
                    "sampleCount": 88,
                    "lastSeenAt": "2026-04-11T09:00:00+08:00",
                },
            ],
        ):
            detail = preview_model_catalog_bootstrap_with_session(
                session,
                business_domain="garmin_watch",
                min_sample_count=20,
                active_only=True,
                name_query="amoled",
            )

        self.assertEqual(detail["acceptedCount"], 1)
        self.assertEqual(detail["nameQuery"], "amoled")
        self.assertEqual(detail["items"][0]["modelName"], "Fenix 8 AMOLED")

    def test_preview_model_catalog_bootstrap_collapses_duplicate_model_names(self) -> None:
        category = Category(
            id="33333333-3333-3333-3333-333333333101",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        session = _FakeSession(category)

        with patch(
            "goofish_insight.application.services.model_catalog_bootstrap._load_bootstrap_rows",
            return_value=[
                {
                    "modelName": "Mac mini M4",
                    "seriesName": "Mac mini",
                    "chipFamily": "M4",
                    "memoryGb": None,
                    "storageGb": None,
                    "sampleCount": 120,
                    "lastSeenAt": "2026-04-11T09:00:00+08:00",
                },
                {
                    "modelName": "Mac mini M4",
                    "seriesName": "Mac mini",
                    "chipFamily": "M4",
                    "memoryGb": 16,
                    "storageGb": 256,
                    "sampleCount": 30,
                    "lastSeenAt": "2026-04-11T10:00:00+08:00",
                },
            ],
        ):
            detail = preview_model_catalog_bootstrap_with_session(
                session,
                business_domain="apple_computer",
                min_sample_count=20,
                active_only=True,
            )

        self.assertEqual(detail["acceptedCount"], 1)
        self.assertEqual(detail["items"][0]["modelName"], "Mac mini M4")
        self.assertEqual(detail["items"][0]["metadata"]["sampleCount"], 150)
        self.assertEqual(detail["items"][0]["metadata"]["memoryGb"], 16)
        self.assertEqual(detail["items"][0]["metadata"]["storageGb"], 256)

    def test_normalize_bootstrap_row_canonicalizes_long_tactix_listing(self) -> None:
        row = _normalize_bootstrap_row(
            canonical_category_code="garmin_watch",
            row={
                "modelName": "佳明Tactix 8 AMOLED炫彩版户外运动腕表，国行正品51mm大屏钛合金表圈设计蓝宝石玻璃镜面",
                "seriesName": None,
                "chipFamily": None,
                "memoryGb": None,
                "storageGb": None,
                "sampleCount": 22,
                "lastSeenAt": "2026-04-11T09:00:00+08:00",
            },
        )

        self.assertEqual(row["modelName"], "Tactix 8 AMOLED")
        self.assertEqual(row["seriesName"], "Tactix")

    def test_normalize_bootstrap_row_preserves_instinct_2x_solar_variant(self) -> None:
        row = _normalize_bootstrap_row(
            canonical_category_code="garmin_watch",
            row={
                "modelName": "Instinct 2X Solar",
                "seriesName": "Instinct",
                "chipFamily": None,
                "memoryGb": None,
                "storageGb": None,
                "sampleCount": 7,
                "lastSeenAt": "2026-04-11T09:00:00+08:00",
            },
        )

        self.assertEqual(row["modelName"], "Instinct 2X Solar")
        self.assertEqual(row["seriesName"], "Instinct")

    def test_normalize_bootstrap_row_canonicalizes_tactix7_amoled_variant(self) -> None:
        row = _normalize_bootstrap_row(
            canonical_category_code="garmin_watch",
            row={
                "modelName": "Garmin佳明泰铁时Tactix7pro AMOLED 51mm碳黑旗舰版",
                "seriesName": None,
                "chipFamily": None,
                "memoryGb": None,
                "storageGb": None,
                "sampleCount": 12,
                "lastSeenAt": "2026-04-11T09:00:00+08:00",
            },
        )

        self.assertEqual(row["modelName"], "Tactix 7 AMOLED")
        self.assertEqual(row["seriesName"], "Tactix")

    def test_parse_apple_title_bootstrap_row_extracts_ultra_variant(self) -> None:
        row = _parse_apple_title_bootstrap_row("96GB Mac Studio M3 Ultra 1TB 全新未拆封")
        assert row is not None
        self.assertEqual(row["modelName"], "Mac Studio M3 Ultra 96G 1024G")
        self.assertEqual(row["seriesName"], "Mac Studio")
        self.assertEqual(row["chipFamily"], "M3 Ultra")
        self.assertEqual(row["memoryGb"], 96)
        self.assertEqual(row["storageGb"], 1024)

    def test_parse_apple_title_bootstrap_row_ignores_apple_watch_ultra(self) -> None:
        row = _parse_apple_title_bootstrap_row("Apple Watch Ultra 3 黑色钛金属表壳")
        self.assertIsNone(row)

    def test_parse_apple_title_bootstrap_row_ignores_invalid_memory_bucket(self) -> None:
        row = _parse_apple_title_bootstrap_row("Mac Studio M3 Ultra 12G 16TB 国行")
        assert row is not None
        self.assertEqual(row["chipFamily"], "M3 Ultra")
        self.assertIsNone(row["memoryGb"])
        self.assertEqual(row["storageGb"], 16384)


if __name__ == "__main__":
    unittest.main()
