from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from goofish_insight.application.services.catalog_migration_checks import (
    build_catalog_migration_report,
    build_catalog_pricing_dual_read_report,
    build_catalog_scoped_migration_report,
    run_catalog_pricing_dual_read_backfill,
)
from goofish_insight.models import OutboxStatus


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class _FakeOutboxQuery:
    def __init__(self, *, first_row, count_value: int) -> None:
        self._first_row = first_row
        self._count_value = count_value

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._first_row

    def count(self):
        return self._count_value


class _FakeSession:
    def __init__(self, *, revision: str, latest_outbox, pending_outbox_count: int) -> None:
        self.revision = revision
        self.latest_outbox = latest_outbox
        self.pending_outbox_count = pending_outbox_count
        self.query_calls = 0

    def execute(self, stmt):
        return _FakeScalarResult(self.revision)

    def query(self, model):
        self.query_calls += 1
        if self.query_calls == 1:
            return _FakeOutboxQuery(first_row=self.latest_outbox, count_value=self.pending_outbox_count)
        return _FakeOutboxQuery(first_row=self.latest_outbox, count_value=self.pending_outbox_count)


class _FakeOutboxEvent:
    def __init__(self) -> None:
        self.id = "evt-1"
        self.aggregate_id = "spu-1"
        self.status = OutboxStatus.DONE
        self.retry_count = 0
        self.last_error = None
        self.created_at = "2026-04-05T07:00:00+00:00"
        self.updated_at = "2026-04-05T07:01:00+00:00"


class _FakeItem:
    def __init__(self, *, id: str, item_id: str, business_domain: str) -> None:
        self.id = id
        self.item_id = item_id
        self.business_domain = business_domain
        self.title = f"title-{item_id}"
        self.normalized_model_family = "MacBook Air"


class _FakeSpu:
    def __init__(self, *, id: str) -> None:
        self.id = id


class _FakeSku:
    def __init__(self, *, spu_id: str, sku_code: str, price: Decimal) -> None:
        self.spu_id = spu_id
        self.sku_code = sku_code
        self.price = price


class CatalogMigrationChecksTests(unittest.TestCase):
    def test_build_catalog_migration_report_builds_pass_checks(self) -> None:
        session = _FakeSession(
            revision="20260405_0008",
            latest_outbox=_FakeOutboxEvent(),
            pending_outbox_count=0,
        )

        with (
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_category_templates",
                return_value={"templateCount": 3, "latestTemplateId": "tpl-3"},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_spu_page",
                return_value={"page": 1, "pageSize": 20, "total": 1, "items": [{"id": "spu-1"}]},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_sku_page",
                return_value={"page": 1, "pageSize": 20, "total": 2, "items": [{"id": "sku-1"}]},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_spu_detail",
                return_value={
                    "spu": {
                        "id": "spu-1",
                        "categoryId": "cat-1",
                        "templateId": "tpl-3",
                        "title": "小米 15 Pro",
                        "status": "ACTIVE",
                        "attrSnapshotJson": {"skus": [{}, {}]},
                    },
                    "skus": [{}, {}],
                },
            ),
        ):
            result = build_catalog_migration_report(
                session,
                category_id="cat-1",
                spu_id="spu-1",
                expected_template_id="tpl-3",
            )

        self.assertEqual(result["alembicRevision"], "20260405_0008")
        self.assertEqual(result["spuDetail"]["skuCount"], 2)
        self.assertTrue(all(check["ok"] for check in result["checks"]))

    def test_build_catalog_migration_report_marks_pending_outbox_as_not_ok(self) -> None:
        session = _FakeSession(
            revision="20260405_0008",
            latest_outbox=_FakeOutboxEvent(),
            pending_outbox_count=1,
        )

        with (
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_spu_page",
                return_value={"page": 1, "pageSize": 20, "total": 1, "items": [{"id": "spu-1"}]},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_sku_page",
                return_value={"page": 1, "pageSize": 20, "total": 0, "items": []},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_spu_detail",
                return_value={
                    "spu": {
                        "id": "spu-1",
                        "categoryId": "cat-1",
                        "templateId": "tpl-3",
                        "title": "小米 15 Pro",
                        "status": "ACTIVE",
                        "attrSnapshotJson": {"skus": []},
                    },
                    "skus": [],
                },
            ),
        ):
            result = build_catalog_migration_report(
                session,
                spu_id="spu-1",
            )

        outbox_check = next(check for check in result["checks"] if check["name"] == "catalog_outbox_cleared")
        self.assertFalse(outbox_check["ok"])

    def test_build_catalog_scoped_migration_report_marks_all_checks_ok(self) -> None:
        session = _FakeSession(
            revision="20260405_0008",
            latest_outbox=_FakeOutboxEvent(),
            pending_outbox_count=0,
        )

        with (
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_migration_report",
                return_value={"checks": [{"name": "demo_ok", "ok": True}]},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_backfill_reconciliation_report_with_session",
                side_effect=[
                    {
                        "businessDomain": "apple_m_series",
                        "target": {"categoryExists": True, "templateExists": True},
                        "counts": {
                            "legacyEnrichedItemTotal": 10,
                            "migratedSpuTotal": 10,
                            "pendingOutboxTotal": 0,
                        },
                        "coverageRatio": 1.0,
                    },
                    {
                        "businessDomain": "garmin",
                        "target": {"categoryExists": True, "templateExists": True},
                        "counts": {
                            "legacyEnrichedItemTotal": 5,
                            "migratedSpuTotal": 5,
                            "pendingOutboxTotal": 0,
                        },
                        "coverageRatio": 1.0,
                    },
                ],
            ),
        ):
            result = build_catalog_scoped_migration_report(
                session,
                business_domains=["apple_m_series", "garmin"],
            )

        self.assertTrue(result["overallOk"])
        self.assertEqual(len(result["backfillReconciliation"]), 2)
        self.assertTrue(all(check["ok"] for check in result["checks"]))

    def test_build_catalog_scoped_migration_report_marks_incomplete_domain_not_ok(self) -> None:
        session = _FakeSession(
            revision="20260405_0008",
            latest_outbox=_FakeOutboxEvent(),
            pending_outbox_count=0,
        )

        with (
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_migration_report",
                return_value={"checks": [{"name": "demo_ok", "ok": True}]},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_backfill_reconciliation_report_with_session",
                return_value={
                    "businessDomain": "apple_m_series",
                    "target": {"categoryExists": True, "templateExists": True},
                    "counts": {
                        "legacyEnrichedItemTotal": 10,
                        "migratedSpuTotal": 9,
                        "pendingOutboxTotal": 1,
                    },
                    "coverageRatio": 0.9,
                },
            ),
        ):
            result = build_catalog_scoped_migration_report(
                session,
                business_domains=["apple_m_series"],
            )

        self.assertFalse(result["overallOk"])
        failed_checks = [check for check in result["checks"] if not check["ok"]]
        self.assertEqual({check["name"] for check in failed_checks}, {"apple_m_series_coverage_complete", "apple_m_series_outbox_cleared"})

    def test_build_catalog_pricing_dual_read_report_marks_price_mismatch_not_ok(self) -> None:
        item_1 = _FakeItem(id="item-ref-1", item_id="1001", business_domain="apple_m_series")
        item_2 = _FakeItem(id="item-ref-2", item_id="1002", business_domain="apple_m_series")

        with (
            patch(
                "goofish_insight.application.services.catalog_migration_checks.load_pricing_records",
                return_value=[
                    {
                        "item_id_ref": "item-ref-1",
                        "item_id": "1001",
                        "title": "MacBook Air M3 16G 512G",
                        "price": 3000.0,
                        "product_line": "MacBook Air",
                    },
                    {
                        "item_id_ref": "item-ref-2",
                        "item_id": "1002",
                        "title": "MacBook Air M3 16G 1T",
                        "price": 3500.0,
                        "product_line": "MacBook Air",
                    },
                ],
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._load_items_by_internal_id",
                return_value={"item-ref-1": item_1, "item-ref-2": item_2},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._legacy_spu_id",
                side_effect=lambda _domain, item_id: f"spu-{item_id}",
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._legacy_sku_code",
                side_effect=lambda _domain, item_id: f"sku-{item_id}",
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._load_catalog_rows_by_spu_id",
                return_value={
                    "spus": {
                        "spu-1001": _FakeSpu(id="spu-1001"),
                        "spu-1002": _FakeSpu(id="spu-1002"),
                    },
                    "skus": {
                        ("spu-1001", "sku-1001"): _FakeSku(
                            spu_id="spu-1001",
                            sku_code="sku-1001",
                            price=Decimal("3000.00"),
                        ),
                        ("spu-1002", "sku-1002"): _FakeSku(
                            spu_id="spu-1002",
                            sku_code="sku-1002",
                            price=Decimal("3600.00"),
                        ),
                    },
                },
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._resolve_catalog_rollback_artifact",
                return_value={
                    "path": "/tmp/catalog_dual_read_rollback.sh",
                    "exists": True,
                    "executable": True,
                },
            ),
        ):
            result = build_catalog_pricing_dual_read_report(
                object(),
                business_domains=["apple_m_series"],
                expected_spu_coverage_ratio=1.0,
                expected_price_match_ratio=1.0,
            )

        self.assertFalse(result["overallOk"])
        self.assertEqual(result["reportFormatVersion"], "catalog-dual-read-diff-v1")
        self.assertIn("diffReport", result)
        self.assertIn("rollbackArtifact", result)
        domain_report = result["domainReports"][0]
        self.assertEqual(domain_report["spuCoverageRatio"], 1.0)
        self.assertEqual(domain_report["priceParityRatio"], 0.5)
        self.assertEqual(domain_report["contractParityRatio"], 1.0)
        self.assertEqual(domain_report["priceMismatchSamples"][0]["reason"], "price_mismatch")
        failed_checks = [check["name"] for check in result["checks"] if not check["ok"]]
        self.assertEqual(failed_checks, ["apple_m_series_dual_read_price_parity"])

    def test_build_catalog_pricing_dual_read_report_marks_contract_mismatch_not_ok(self) -> None:
        item = _FakeItem(id="item-ref-1", item_id="1001", business_domain="apple_m_series")

        with (
            patch(
                "goofish_insight.application.services.catalog_migration_checks.load_pricing_records",
                return_value=[
                    {
                        "item_id_ref": "item-ref-1",
                        "item_id": "1001",
                        "title": "MacBook Air M3 16G 512G",
                        "price": 3000.0,
                        "product_line": "MacBook Air",
                    }
                ],
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._load_items_by_internal_id",
                return_value={"item-ref-1": item},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._legacy_spu_id",
                side_effect=lambda _domain, item_id: f"spu-{item_id}",
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._legacy_sku_code",
                side_effect=lambda _domain, item_id: f"sku-{item_id}",
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._load_catalog_rows_by_spu_id",
                return_value={
                    "spus": {"spu-1001": _FakeSpu(id="spu-1001")},
                    "skus": {
                        ("spu-1001", "sku-1001"): _FakeSku(
                            spu_id="spu-1001",
                            sku_code="sku-1001",
                            price=Decimal("3000.00"),
                        )
                    },
                },
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks.build_catalog_pricing_contract_row",
                return_value={
                    "businessDomain": "apple_computer",
                    "itemId": "1001",
                    "spuId": "spu-1001",
                    "skuCode": "sku-1001",
                    "title": "MacBook Air M3 16G 512G",
                    "price": 3000.0,
                },
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._resolve_catalog_rollback_artifact",
                return_value={
                    "path": "/tmp/catalog_dual_read_rollback.sh",
                    "exists": True,
                    "executable": True,
                },
            ),
        ):
            result = build_catalog_pricing_dual_read_report(
                object(),
                business_domains=["apple_m_series"],
                expected_spu_coverage_ratio=1.0,
                expected_price_match_ratio=1.0,
            )

        self.assertFalse(result["overallOk"])
        domain_report = result["domainReports"][0]
        self.assertEqual(domain_report["contractComparedCount"], 1)
        self.assertEqual(domain_report["contractMismatchCount"], 1)
        self.assertEqual(domain_report["contractParityRatio"], 0.0)
        self.assertEqual(domain_report["contractMismatchSamples"][0]["reason"], "contract_mismatch")
        failed_checks = [check["name"] for check in result["checks"] if not check["ok"]]
        self.assertEqual(failed_checks, ["apple_m_series_dual_read_contract_parity"])

    def test_run_catalog_pricing_dual_read_backfill_processes_missing_spu_candidates(self) -> None:
        item_1 = _FakeItem(id="item-ref-1", item_id="1001", business_domain="apple_computer")
        item_2 = _FakeItem(id="item-ref-2", item_id="1002", business_domain="apple_computer")

        with (
            patch(
                "goofish_insight.application.services.catalog_migration_checks.load_pricing_records",
                return_value=[
                    {"item_id_ref": "item-ref-1", "item_id": "1001", "title": "MacBook Pro M4 16+512", "price": 8800.0},
                    {"item_id_ref": "item-ref-2", "item_id": "1002", "title": "MacBook Air M2 16+512", "price": 5200.0},
                ],
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._load_items_by_internal_id",
                return_value={"item-ref-1": item_1, "item-ref-2": item_2},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._legacy_spu_id",
                side_effect=lambda domain, item_id: f"spu-{domain}-{item_id}",
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._legacy_sku_code",
                side_effect=lambda domain, item_id: f"sku-{domain}-{item_id}",
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._load_catalog_rows_by_spu_id",
                return_value={"spus": {}, "skus": {}},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks.preview_catalog_backfill_item",
                return_value={
                    "warnings": ["missing_spec_enrichment", "used_rule_spec_fallback"],
                    "payload": {"spuAttributes": [{"attributeCode": "product_line"}]},
                    "persistPlan": {"skuAttributeRows": [{"attributeCode": "memory_gb"}, {"attributeCode": "storage_gb"}]},
                },
            ) as preview_mock,
            patch(
                "goofish_insight.application.services.catalog_migration_checks.persist_catalog_backfill_item",
                return_value={"spuId": "spu-1001", "skuCount": 1, "skuAttributeCount": 2},
            ) as persist_mock,
        ):
            result = run_catalog_pricing_dual_read_backfill(
                object(),
                business_domains=["apple_m_series"],
                limit=1,
                dry_run=True,
                allow_warnings=True,
            )

        self.assertTrue(result["dryRun"])
        self.assertEqual(result["totalCandidateMissingSpuCount"], 2)
        self.assertEqual(result["totalAttemptedCount"], 1)
        self.assertEqual(result["totalProcessedCount"], 1)
        domain_report = result["domainReports"][0]
        self.assertEqual(domain_report["warningCounts"]["missing_spec_enrichment"], 1)
        self.assertEqual(domain_report["items"][0]["status"], "would_backfill")
        preview_mock.assert_called_once_with(item_id="1001")
        persist_mock.assert_called_once_with(
            item_id="1001",
            operator_id="catalog-pricing-dual-read",
            dry_run=True,
            allow_warnings=True,
        )

    def test_run_catalog_pricing_dual_read_backfill_skips_low_spu_attribute_count(self) -> None:
        item_1 = _FakeItem(id="item-ref-1", item_id="1001", business_domain="garmin")

        with (
            patch(
                "goofish_insight.application.services.catalog_migration_checks.load_pricing_records",
                return_value=[
                    {"item_id_ref": "item-ref-1", "item_id": "1001", "title": "Garmin Forerunner 265", "price": 1999.0},
                ],
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._load_items_by_internal_id",
                return_value={"item-ref-1": item_1},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._legacy_spu_id",
                side_effect=lambda domain, item_id: f"spu-{domain}-{item_id}",
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._legacy_sku_code",
                side_effect=lambda domain, item_id: f"sku-{domain}-{item_id}",
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks._load_catalog_rows_by_spu_id",
                return_value={"spus": {}, "skus": {}},
            ),
            patch(
                "goofish_insight.application.services.catalog_migration_checks.preview_catalog_backfill_item",
                return_value={
                    "warnings": [],
                    "payload": {"spuAttributes": [{"attributeCode": "product_line"}]},
                    "persistPlan": {"skuAttributeRows": []},
                },
            ) as preview_mock,
            patch(
                "goofish_insight.application.services.catalog_migration_checks.persist_catalog_backfill_item",
            ) as persist_mock,
        ):
            result = run_catalog_pricing_dual_read_backfill(
                object(),
                business_domains=["garmin"],
                limit=1,
                dry_run=True,
                allow_warnings=False,
                min_spu_attribute_count=2,
            )

        self.assertTrue(result["dryRun"])
        self.assertEqual(result["totalSkippedCount"], 1)
        domain_report = result["domainReports"][0]
        self.assertEqual(domain_report["items"][0]["status"], "skipped_low_spu_attribute_count")
        preview_mock.assert_called_once_with(item_id="1001")
        persist_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
