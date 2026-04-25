from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from goofish_insight.application.services.catalog_backfill import (
    build_catalog_backfill_reconciliation_report_with_session,
    CatalogBackfillPreviewError,
    build_catalog_backfill_template_payload,
    ensure_catalog_backfill_template,
    persist_catalog_backfill_batch,
    persist_catalog_backfill_item,
    preview_catalog_backfill_batch_with_session,
    preview_catalog_backfill_item_with_session,
    run_catalog_backfill_migration,
)
from goofish_insight.models import Item, ItemSpecEnrichment, SellerProfile


class _FakeExecuteResult:
    def __init__(self, item: Item | None) -> None:
        self._item = item

    def scalar_one_or_none(self) -> Item | None:
        return self._item


class _FakeScalarRows:
    def __init__(self, rows: list[Item]) -> None:
        self._rows = rows

    def all(self) -> list[Item]:
        return self._rows


class _FakeBatchExecuteResult:
    def __init__(self, *, scalar_value=None, rows: list[Item] | None = None) -> None:
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar_one(self):
        return self._scalar_value

    def scalars(self):
        return _FakeScalarRows(self._rows)


class _FakeSession:
    def __init__(self, item: Item | None) -> None:
        self.item = item

    def execute(self, stmt):
        return _FakeExecuteResult(self.item)


class _FakeBatchSession:
    def __init__(self, *, total: int, rows: list[Item]) -> None:
        self.total = total
        self.rows = rows
        self.statement_count = 0

    def execute(self, stmt):
        self.statement_count += 1
        if self.statement_count == 1:
            return _FakeBatchExecuteResult(scalar_value=self.total)
        return _FakeBatchExecuteResult(rows=self.rows)


class _FakeCountExecuteResult:
    def __init__(self, *, scalar_value=None, rows=None) -> None:
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar_one(self):
        return self._scalar_value

    def scalars(self):
        class _Rows:
            def __init__(self, values):
                self._values = values

            def __iter__(self):
                return iter(self._values)

        return _Rows(self._rows)


class _FakeReportSession:
    def __init__(self, *, category, template, recent_spus) -> None:
        self.category = category
        self.template = template
        self.recent_spus = recent_spus
        self._scalar_values = [12, 5, 3, 0]

    def execute(self, stmt):
        if self._scalar_values:
            return _FakeCountExecuteResult(scalar_value=self._scalar_values.pop(0))
        return _FakeCountExecuteResult(rows=self.recent_spus)

    def get(self, model, key):
        model_name = getattr(model, "__name__", "")
        if model_name == "Category":
            return self.category
        if model_name == "CategoryAttrTemplate":
            return self.template
        return None


class CatalogBackfillServiceTests(unittest.TestCase):
    def test_build_catalog_backfill_template_payload_accepts_canonical_category_code(self) -> None:
        result = build_catalog_backfill_template_payload(business_domain="apple_computer")

        self.assertEqual(result["category"]["code"], "apple_computer")
        self.assertEqual(result["template"]["id"], "33333333-3333-3333-3333-333333333401")

    def test_preview_catalog_backfill_item_with_session_builds_apple_payload(self) -> None:
        seller = SellerProfile(seller_id="seller-apple-1")
        item = Item(
            item_id="apple-item-1",
            task_id=1,
            business_domain="apple_m_series",
            title="MacBook Pro M3 Pro 18G 512G",
            normalized_brand="Apple",
            normalized_model_family="MacBook Pro",
            normalized_model="MacBook Pro",
            normalized_chip="M3 Pro",
            normalized_memory_gb=18,
            normalized_storage_gb=512,
            current_price=Decimal("8999.00"),
            is_active=True,
        )
        item.seller = seller
        item.spec_enrichment = ItemSpecEnrichment(
            business_domain="apple_m_series",
            extractor_type="rule",
            extractor_version="v1",
            status="complete",
            brand="Apple",
            product_line="MacBook Pro",
            model_name="MacBook Pro",
            chip_family="M3 Pro",
            screen_size_in=Decimal("14.0"),
            cpu_cores=12,
            gpu_cores=18,
            memory_gb=18,
            storage_gb=512,
        )

        result = preview_catalog_backfill_item_with_session(
            _FakeSession(item),
            item_id="apple-item-1",
        )

        self.assertEqual(result["businessDomain"], "apple_m_series")
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["target"]["categoryCode"], "apple_computer")
        self.assertEqual(
            result["payload"]["spu"]["title"],
            "MacBook Pro / 14in / M3 Pro / 12C CPU / 18C GPU / 18G / 512G",
        )
        self.assertEqual(result["payload"]["spu"]["merchantId"], "seller-apple-1")
        self.assertEqual(result["payload"]["skus"][0]["price"], 8999)
        self.assertTrue(result["payload"]["skus"][0]["skuCode"].startswith("LGC-APPLEMSE-"))
        self.assertEqual(len(result["persistPlan"]["skuAttributeRows"]), 2)

    def test_preview_catalog_backfill_item_with_session_uses_garmin_fallbacks(self) -> None:
        seller = SellerProfile(seller_id="seller-garmin-1")
        item = Item(
            item_id="garmin-item-1",
            task_id=1,
            business_domain="garmin",
            title="佳明 Fenix 7",
            normalized_brand="Garmin",
            normalized_model_family="Fenix",
            normalized_model="Fenix 7",
            current_price=Decimal("2999.00"),
            is_active=False,
        )
        item.seller = seller
        item.spec_enrichment = None

        result = preview_catalog_backfill_item_with_session(
            _FakeSession(item),
            item_id="garmin-item-1",
        )

        self.assertEqual(result["businessDomain"], "garmin")
        self.assertIn("missing_spec_enrichment", result["warnings"])
        self.assertIn("used_rule_spec_fallback", result["warnings"])
        self.assertIn("missing_display_type", result["warnings"])
        self.assertIn("missing_case_size_mm", result["warnings"])
        self.assertEqual(result["payload"]["spu"]["title"], "Fenix 7")
        self.assertEqual(result["payload"]["spu"]["status"], "INACTIVE")
        self.assertEqual(result["payload"]["skus"][0]["price"], 2999)
        self.assertEqual(len(result["persistPlan"]["spuAttributeRows"]), 3)

    def test_preview_catalog_backfill_item_with_session_uses_rule_fallback_for_missing_apple_spec(self) -> None:
        item = Item(
            item_id="apple-item-rule-fallback",
            task_id=1,
            business_domain="apple_computer",
            title="MacBook Pro14 M4芯片 10+10 16+512的深空灰",
            normalized_brand="Apple",
            current_price=Decimal("5200.00"),
            is_active=True,
        )
        item.spec_enrichment = None

        result = preview_catalog_backfill_item_with_session(
            _FakeSession(item),
            item_id="apple-item-rule-fallback",
        )

        self.assertIn("missing_spec_enrichment", result["warnings"])
        self.assertIn("used_rule_spec_fallback", result["warnings"])
        self.assertIn("used_rule_memory_storage_fallback", result["warnings"])
        self.assertNotIn("missing_memory_gb", result["warnings"])
        self.assertNotIn("missing_storage_gb", result["warnings"])
        self.assertEqual(result["target"]["categoryCode"], "apple_computer")
        self.assertIn("MacBook Pro", result["payload"]["spu"]["title"])
        self.assertIn("M4", result["payload"]["spu"]["title"])
        self.assertEqual(len(result["persistPlan"]["skuAttributeRows"]), 2)

    def test_preview_catalog_backfill_item_with_session_uses_garmin_model_defaults(self) -> None:
        item = Item(
            item_id="garmin-defaults-1",
            task_id=1,
            business_domain="garmin",
            title="Garmin Forerunner 265S",
            normalized_brand="Garmin",
            normalized_model_family="Forerunner",
            normalized_model="Forerunner 265S",
            current_price=Decimal("1899.00"),
            is_active=True,
        )
        item.spec_enrichment = None

        result = preview_catalog_backfill_item_with_session(
            _FakeSession(item),
            item_id="garmin-defaults-1",
        )

        self.assertIn("used_model_default_display_type", result["warnings"])
        self.assertIn("used_model_default_case_size_mm", result["warnings"])
        self.assertNotIn("missing_display_type", result["warnings"])
        self.assertNotIn("missing_case_size_mm", result["warnings"])
        spu_attributes = list(result["payload"]["spuAttributes"])
        display_rows = [row for row in spu_attributes if row.get("attributeCode") == "display_type"]
        case_rows = [row for row in spu_attributes if row.get("attributeCode") == "case_size_mm"]
        self.assertEqual(display_rows[0]["textValue"], "AMOLED")
        self.assertEqual(case_rows[0]["numberValue"], 42)

    def test_preview_catalog_backfill_item_with_session_rejects_unsupported_domain(self) -> None:
        item = Item(
            item_id="bike-item-1",
            task_id=1,
            business_domain="bike",
            title="自行车",
            current_price=Decimal("500.00"),
            is_active=True,
        )

        with self.assertRaises(CatalogBackfillPreviewError):
            preview_catalog_backfill_item_with_session(
                _FakeSession(item),
                item_id="bike-item-1",
            )

    def test_preview_catalog_backfill_item_with_session_prefers_dynamic_catalog_attributes(self) -> None:
        item = Item(
            item_id="apple-item-dynamic-1",
            task_id=1,
            business_domain="apple_m_series",
            title="MacBook Pro",
            normalized_brand="Apple",
            current_price=Decimal("8999.00"),
            is_active=True,
        )
        item.spec_enrichment = ItemSpecEnrichment(
            business_domain="apple_m_series",
            extractor_type="llm",
            extractor_version="v1",
            status="complete",
            extraction_payload={
                "catalogAttributes": {
                    "spuAttributes": [
                        {"attributeCode": "product_line", "textValue": "MacBook Pro"},
                        {"attributeCode": "model_name", "textValue": "MacBook Pro"},
                        {"attributeCode": "chip_family", "textValue": "M3 Pro"},
                        {"attributeCode": "screen_size_in", "numberValue": 14, "normalizedNumberValue": 14, "unit": "inch"},
                        {"attributeCode": "cpu_cores", "numberValue": 12, "normalizedNumberValue": 12},
                        {"attributeCode": "gpu_cores", "numberValue": 18, "normalizedNumberValue": 18},
                    ],
                    "skuAttributes": [
                        {"attributeCode": "memory_gb", "numberValue": 18, "normalizedNumberValue": 18, "unit": "GB"},
                        {"attributeCode": "storage_gb", "numberValue": 512, "normalizedNumberValue": 512, "unit": "GB"},
                    ],
                    "saleAttributes": [],
                }
            },
        )

        result = preview_catalog_backfill_item_with_session(
            _FakeSession(item),
            item_id="apple-item-dynamic-1",
        )

        self.assertEqual(
            result["payload"]["spu"]["title"],
            "MacBook Pro / 14in / M3 Pro / 12C CPU / 18C GPU / 18G / 512G",
        )
        self.assertEqual(len(result["payload"]["spuAttributes"]), 6)
        self.assertEqual(len(result["payload"]["skus"][0]["attributes"]), 2)

    def test_preview_catalog_backfill_item_with_session_prefers_xianyu_category_mapping(self) -> None:
        item = Item(
            item_id="mapped-item-1",
            task_id=1,
            business_domain="apple_m_series",
            title="MacBook Pro 16G",
            normalized_brand="Apple",
            normalized_model_family="MacBook Pro",
            normalized_model="MacBook Pro",
            normalized_memory_gb=16,
            current_price=Decimal("7999.00"),
            is_active=True,
            xianyu_c_cat_id="c-9001",
            xianyu_cat_id="cat-9001",
            xianyu_tb_cat_id="tb-9001",
        )
        item.spec_enrichment = ItemSpecEnrichment(
            business_domain="apple_m_series",
            extractor_type="llm",
            extractor_version="v1",
            status="complete",
            extraction_payload={
                "catalogAttributes": {
                    "spuAttributes": [
                        {"attributeCode": "product_line", "textValue": "MacBook Pro"},
                        {"attributeCode": "model_name", "textValue": "MacBook Pro"},
                    ],
                    "skuAttributes": [
                        {"attributeCode": "memory_gb", "numberValue": 16, "normalizedNumberValue": 16, "unit": "GB"},
                    ],
                    "saleAttributes": [],
                }
            },
        )

        mapped_template_detail = {
            "category": {
                "id": "dynamic-category-1",
                "code": "xianyu_laptop",
                "name": "笔记本电脑",
                "path": "electronics/laptop",
                "level": 2,
            },
            "template": {
                "id": "dynamic-template-1",
                "version": 3,
            },
            "items": [
                {
                    "attributeCode": "product_line",
                    "attributeName": "Product Line",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 10,
                },
                {
                    "attributeCode": "model_name",
                    "attributeName": "Model Name",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 20,
                },
                {
                    "attributeCode": "memory_gb",
                    "attributeName": "Memory",
                    "dataType": "NUMBER",
                    "valueScope": "SKU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 30,
                    "unit": "GB",
                },
            ],
        }

        with patch(
            "goofish_insight.application.services.catalog_backfill.resolve_xianyu_category_mapping_with_session",
            return_value=type(
                "MappingStub",
                (),
                {"category_id": "dynamic-category-1", "template_id": "dynamic-template-1"},
            )(),
        ), patch(
            "goofish_insight.application.services.catalog_backfill.build_catalog_template_detail",
            return_value=mapped_template_detail,
        ):
            result = preview_catalog_backfill_item_with_session(
                _FakeSession(item),
                item_id="mapped-item-1",
            )

        self.assertEqual(result["target"]["categoryId"], "dynamic-category-1")
        self.assertEqual(result["target"]["categoryCode"], "xianyu_laptop")
        self.assertEqual(result["target"]["templateId"], "dynamic-template-1")
        self.assertEqual(result["payload"]["spu"]["templateId"], "dynamic-template-1")
        self.assertEqual(result["payload"]["spu"]["title"], "MacBook Pro / 16G")
        self.assertEqual(len(result["payload"]["spuAttributes"]), 2)
        self.assertEqual(len(result["payload"]["skus"][0]["attributes"]), 1)

    def test_preview_catalog_backfill_batch_with_session_returns_summary_and_warning_counts(self) -> None:
        apple_item = Item(
            item_id="apple-item-1",
            task_id=1,
            business_domain="apple_m_series",
            title="Mac mini M4",
            normalized_brand="Apple",
            normalized_model_family="Mac mini",
            normalized_model="Mac mini",
            normalized_chip="M4",
            normalized_memory_gb=16,
            normalized_storage_gb=256,
            current_price=Decimal("3299.00"),
            is_active=True,
        )
        apple_item.spec_enrichment = ItemSpecEnrichment(
            business_domain="apple_m_series",
            extractor_type="rule",
            extractor_version="v1",
            status="complete",
            product_line="Mac mini",
            model_name="Mac mini",
            chip_family="M4",
            memory_gb=16,
            storage_gb=256,
        )

        partial_item = Item(
            item_id="apple-item-2",
            task_id=1,
            business_domain="apple_m_series",
            title="MacBook Air",
            normalized_brand="Apple",
            normalized_model_family="MacBook Air",
            normalized_model="MacBook Air",
            current_price=Decimal("4999.00"),
            is_active=True,
        )
        partial_item.spec_enrichment = None

        result = preview_catalog_backfill_batch_with_session(
            _FakeBatchSession(total=2, rows=[apple_item, partial_item]),
            business_domain="apple_m_series",
            limit=20,
            offset=0,
            enriched_only=True,
        )

        self.assertEqual(result["businessDomain"], "apple_m_series")
        self.assertTrue(result["enrichedOnly"])
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["itemId"], "apple-item-1")
        self.assertEqual(result["items"][1]["itemId"], "apple-item-2")
        self.assertEqual(result["warningCounts"]["missing_spec_enrichment"], 1)

    def test_build_catalog_backfill_template_payload_returns_blueprint_payload(self) -> None:
        payload = build_catalog_backfill_template_payload(business_domain="garmin")

        self.assertEqual(payload["category"]["code"], "garmin_watch")
        self.assertEqual(payload["template"]["id"], "22222222-2222-2222-2222-222222222401")
        self.assertEqual(len(payload["attributes"]), 7)
        self.assertEqual(payload["template"]["status"], "PUBLISHED")

    def test_persist_catalog_backfill_item_requires_clean_preview_by_default(self) -> None:
        with patch(
            "goofish_insight.application.services.catalog_backfill.preview_catalog_backfill_item",
            return_value={
                "warnings": ["missing_spec_enrichment"],
                "payload": {"requestId": "req-1"},
            },
        ):
            with self.assertRaises(CatalogBackfillPreviewError):
                persist_catalog_backfill_item(
                    item_id="apple-item-1",
                    operator_id="ops-bot",
                    dry_run=True,
                )

    def test_persist_catalog_backfill_item_invokes_catalog_persistence(self) -> None:
        with patch(
            "goofish_insight.application.services.catalog_backfill.preview_catalog_backfill_item",
            return_value={
                "warnings": [],
                "payload": {"requestId": "req-2"},
            },
        ), patch(
            "goofish_insight.application.services.catalog_backfill.persist_catalog_payload",
            return_value={"spuId": "spu-1", "dryRun": True},
        ) as persist_mock:
            result = persist_catalog_backfill_item(
                item_id="apple-item-1",
                operator_id="ops-bot",
                dry_run=True,
            )

        self.assertEqual(result["spuId"], "spu-1")
        persist_mock.assert_called_once()
        self.assertTrue(persist_mock.call_args.kwargs["dry_run"])

    def test_persist_catalog_backfill_batch_aggregates_results(self) -> None:
        with patch(
            "goofish_insight.application.services.catalog_backfill.preview_catalog_backfill_batch",
            return_value={
                "businessDomain": "apple_m_series",
                "limit": 2,
                "offset": 0,
                "enrichedOnly": True,
                "warningCounts": {},
                "items": [
                    {"itemId": "apple-item-1"},
                    {"itemId": "apple-item-2"},
                ],
            },
        ), patch(
            "goofish_insight.application.services.catalog_backfill.persist_catalog_backfill_item",
            side_effect=[
                {"spuId": "spu-1", "skuCount": 1, "outboxEventId": "evt-1"},
                RuntimeError("broken item"),
            ],
        ):
            result = persist_catalog_backfill_batch(
                business_domain="apple_m_series",
                operator_id="ops-bot",
                limit=2,
                dry_run=True,
            )

        self.assertEqual(result["candidateCount"], 2)
        self.assertEqual(result["processedCount"], 1)
        self.assertEqual(result["skippedCount"], 0)
        self.assertEqual(result["failedCount"], 1)
        self.assertEqual(result["applyMode"], "dry_run")
        self.assertEqual(result["wouldApplyCount"], 1)
        self.assertEqual(result["appliedCount"], 0)
        self.assertEqual(result["items"][0]["status"], "processed")
        self.assertEqual(result["items"][0]["applyState"], "would_apply")
        self.assertEqual(result["items"][1]["status"], "failed")

    def test_persist_catalog_backfill_batch_skips_existing_spu_errors(self) -> None:
        with patch(
            "goofish_insight.application.services.catalog_backfill.preview_catalog_backfill_batch",
            return_value={
                "businessDomain": "garmin",
                "limit": 1,
                "offset": 0,
                "enrichedOnly": True,
                "warningCounts": {},
                "items": [{"itemId": "garmin-item-1"}],
            },
        ), patch(
            "goofish_insight.application.services.catalog_backfill.persist_catalog_backfill_item",
            side_effect=RuntimeError("SPU already exists: spu-1"),
        ):
            result = persist_catalog_backfill_batch(
                business_domain="garmin",
                operator_id="ops-bot",
                dry_run=True,
                skip_existing=True,
            )

        self.assertEqual(result["processedCount"], 0)
        self.assertEqual(result["skippedCount"], 1)
        self.assertEqual(result["failedCount"], 0)
        self.assertEqual(result["items"][0]["status"], "skipped_existing")
        self.assertEqual(result["items"][0]["skipReason"], "existing_spu")
        self.assertEqual(result["skipReasonCounts"]["existing_spu"], 1)

    def test_ensure_catalog_backfill_template_returns_existing_when_present(self) -> None:
        with patch(
            "goofish_insight.application.services.catalog_backfill.session_scope",
        ) as session_scope_mock:
            class _Ctx:
                def __enter__(self_inner):
                    class _Session:
                        def get(self, model, key):
                            return object()

                    return _Session()

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            session_scope_mock.return_value = _Ctx()

            result = ensure_catalog_backfill_template(
                business_domain="garmin",
                operator_id="ops-bot",
                dry_run=False,
            )

        self.assertEqual(result["status"], "existing")
        self.assertEqual(result["templateId"], "22222222-2222-2222-2222-222222222401")

    def test_run_catalog_backfill_migration_aggregates_batches(self) -> None:
        with patch(
            "goofish_insight.application.services.catalog_backfill.ensure_catalog_backfill_template",
            return_value={"status": "existing"},
        ), patch(
            "goofish_insight.application.services.catalog_backfill.preview_catalog_backfill_batch",
            return_value={"total": 3, "businessDomain": "garmin"},
        ), patch(
            "goofish_insight.application.services.catalog_backfill.persist_catalog_backfill_batch",
            side_effect=[
                {"limit": 2, "candidateCount": 2, "processedCount": 1, "skippedCount": 1, "failedCount": 0, "items": []},
                {"limit": 2, "candidateCount": 1, "processedCount": 1, "skippedCount": 0, "failedCount": 0, "items": []},
            ],
        ), patch(
            "goofish_insight.application.services.catalog_backfill._drain_catalog_outbox",
            return_value={"passes": 1, "processedCount": 2, "failedCount": 0},
        ), patch(
            "goofish_insight.application.services.catalog_backfill.build_catalog_backfill_reconciliation_report",
            return_value={"counts": {"migratedSpuTotal": 2}},
        ):
            result = run_catalog_backfill_migration(
                business_domain="garmin",
                operator_id="ops-bot",
                batch_size=2,
                dry_run=False,
            )

        self.assertEqual(result["processedCount"], 2)
        self.assertEqual(result["skippedCount"], 1)
        self.assertEqual(result["failedCount"], 0)
        self.assertEqual(result["outboxProcessedCount"], 4)
        self.assertEqual(result["outboxFailedCount"], 0)
        self.assertEqual(result["outboxSuccessRate"], 1.0)
        self.assertEqual(result["skipReasonCounts"], {})
        self.assertEqual(result["batchesRun"], 2)

    def test_build_catalog_backfill_reconciliation_report_with_session_returns_counts(self) -> None:
        category = type("CategoryStub", (), {"id": "cat-1"})()
        template = type("TemplateStub", (), {"id": "tpl-1"})()
        recent_spu = type(
            "SpuStub",
            (),
            {
                "id": "spu-1",
                "title": "Mac mini / M4 / 16G / 256G",
                "status": type("StatusStub", (), {"value": "ACTIVE"})(),
                "merchant_id": "merchant-1",
                "skus": [object()],
                "updated_at": "2026-04-05T10:00:00+08:00",
            },
        )()

        result = build_catalog_backfill_reconciliation_report_with_session(
            _FakeReportSession(category=category, template=template, recent_spus=[recent_spu]),
            business_domain="apple_m_series",
        )

        self.assertEqual(result["counts"]["legacyItemTotal"], 12)
        self.assertEqual(result["counts"]["legacyEnrichedItemTotal"], 5)
        self.assertEqual(result["counts"]["migratedSpuTotal"], 3)
        self.assertEqual(result["coverageRatio"], 0.6)


if __name__ == "__main__":
    unittest.main()
