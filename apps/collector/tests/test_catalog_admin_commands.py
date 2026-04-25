from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import typer
from typer.testing import CliRunner

from goofish_insight.entrypoints.cli.admin import register_admin_commands


@contextmanager
def _fake_session_scope():
    yield object()


class CatalogAdminCommandTests(unittest.TestCase):
    def test_preview_catalog_signature_command_outputs_signature(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "signature.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "templateItems": [
                            {
                                "attributeCode": "color",
                                "attributeId": "attr-color",
                                "isSale": True,
                                "sortNo": 10,
                            },
                            {
                                "attributeCode": "memory_size",
                                "attributeId": "attr-memory",
                                "isSale": True,
                                "sortNo": 20,
                            },
                        ],
                        "attributes": [
                            {
                                "code": "color",
                                "name": "颜色",
                                "dataType": "ENUM",
                                "isMulti": False,
                            },
                            {
                                "code": "memory_size",
                                "name": "内存",
                                "dataType": "ENUM",
                                "isMulti": False,
                            },
                        ],
                        "selections": [
                            {"attributeCode": "memory_size", "optionCode": "12"},
                            {"attributeCode": "color", "optionCode": "black"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = runner.invoke(app, ["preview-catalog-signature", str(payload_path)])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["raw"], "attr-color:black|attr-memory:12")

    def test_preview_catalog_persist_plan_command_outputs_plan(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "plan.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "requestId": "req-1",
                        "spu": {
                            "id": "spu-1",
                            "categoryId": "cat-phone",
                            "templateId": "tpl-phone-v1",
                            "title": "小米 15",
                            "status": "ACTIVE",
                        },
                        "templateItems": [
                            {
                                "attributeCode": "color",
                                "attributeId": "attr-color",
                                "isSale": True,
                                "sortNo": 10,
                            },
                            {
                                "attributeCode": "memory_size",
                                "attributeId": "attr-memory",
                                "isSale": True,
                                "sortNo": 20,
                            },
                        ],
                        "attributes": [
                            {
                                "code": "color",
                                "name": "颜色",
                                "dataType": "ENUM",
                                "isMulti": False,
                            },
                            {
                                "code": "memory_size",
                                "name": "内存",
                                "dataType": "ENUM",
                                "isMulti": False,
                            },
                        ],
                        "spuAttributes": [],
                        "skus": [
                            {
                                "skuCode": "MI15-BLK-12G",
                                "price": 4599,
                                "stock": 100,
                                "saleAttributes": [
                                    {"attributeCode": "memory_size", "optionCode": "12"},
                                    {"attributeCode": "color", "optionCode": "black"},
                                ],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = runner.invoke(app, ["preview-catalog-persist-plan", str(payload_path)])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["requestId"], "req-1")
        self.assertEqual(payload["skuRows"][0]["salesSignatureRaw"], "attr-color:black|attr-memory:12")

    def test_preview_catalog_backfill_item_command_outputs_preview(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.preview_catalog_backfill_item",
            return_value={
                "itemId": "apple-item-1",
                "businessDomain": "apple_m_series",
                "warnings": [],
                "payload": {
                    "spu": {"title": "MacBook Pro / 14in / M3 Pro"},
                    "skus": [{"skuCode": "LGC-APPLEMS-123"}],
                },
            },
        ) as preview_mock:
            result = runner.invoke(
                app,
                [
                    "preview-catalog-backfill-item",
                    "apple-item-1",
                    "--category-id",
                    "cat-apple",
                    "--template-id",
                    "tpl-apple-v1",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["itemId"], "apple-item-1")
        preview_mock.assert_called_once()
        self.assertEqual(preview_mock.call_args.kwargs["item_id"], "apple-item-1")
        self.assertEqual(preview_mock.call_args.kwargs["category_id"], "cat-apple")
        self.assertEqual(preview_mock.call_args.kwargs["template_id"], "tpl-apple-v1")

    def test_audit_template_attributes_command_outputs_payload(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.build_template_attribute_audit",
            return_value={
                "categoryCount": 2,
                "categoriesWithGaps": 1,
                "missingAttributeCount": 1,
                "categories": [
                    {
                        "categoryCode": "camera_interchangeable_lens",
                        "missingAttributes": [{"attributeCode": "lens_series"}],
                    }
                ],
            },
        ) as audit_mock:
            result = runner.invoke(
                app,
                [
                    "audit-template-attributes",
                    "--category-code",
                    "camera_interchangeable_lens",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["missingAttributeCount"], 1)
        audit_mock.assert_called_once()
        self.assertEqual(
            audit_mock.call_args.kwargs["category_codes"],
            ("camera_interchangeable_lens",),
        )

    def test_preview_catalog_backfill_batch_command_outputs_preview(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.preview_catalog_backfill_batch",
            return_value={
                "businessDomain": "apple_m_series",
                "enrichedOnly": True,
                "total": 2,
                "warningCounts": {"missing_spec_enrichment": 1},
                "items": [
                    {"itemId": "apple-item-1"},
                    {"itemId": "apple-item-2"},
                ],
            },
        ) as preview_mock:
            result = runner.invoke(
                app,
                [
                    "preview-catalog-backfill-batch",
                    "apple_m_series",
                    "--limit",
                    "10",
                    "--offset",
                    "5",
                    "--enriched-only",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["businessDomain"], "apple_m_series")
        preview_mock.assert_called_once()
        self.assertEqual(preview_mock.call_args.kwargs["business_domain"], "apple_computer")
        self.assertEqual(preview_mock.call_args.kwargs["limit"], 10)
        self.assertEqual(preview_mock.call_args.kwargs["offset"], 5)
        self.assertTrue(preview_mock.call_args.kwargs["enriched_only"])

    def test_preview_catalog_backfill_template_command_outputs_preview(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.build_catalog_backfill_template_payload",
            return_value={
                "category": {"code": "garmin_watch"},
                "template": {"id": "tpl-garmin-v1"},
            },
        ) as preview_mock:
            result = runner.invoke(app, ["preview-catalog-backfill-template", "garmin"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["category"]["code"], "garmin_watch")
        preview_mock.assert_called_once_with(business_domain="garmin_watch")

    def test_preview_model_catalog_bootstrap_command_outputs_preview(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.preview_model_catalog_bootstrap",
            return_value={
                "canonicalCategoryCode": "apple_computer",
                "acceptedCount": 2,
                "items": [{"modelCode": "apple_computer_macbook_air_m2"}],
            },
        ) as preview_mock:
            result = runner.invoke(
                app,
                [
                    "preview-model-catalog-bootstrap",
                    "apple_computer",
                    "--min-sample-count",
                    "30",
                    "--limit",
                    "10",
                    "--name-query",
                    "ultra",
                    "--active-only",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["canonicalCategoryCode"], "apple_computer")
        preview_mock.assert_called_once_with(
            business_domain="apple_computer",
            min_sample_count=30,
            limit=10,
            active_only=True,
            name_query="ultra",
        )

    def test_apply_model_catalog_bootstrap_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.apply_model_catalog_bootstrap",
            return_value={
                "canonicalCategoryCode": "garmin_watch",
                "dryRun": False,
                "acceptedCount": 3,
                "import": {"importedCount": 3},
            },
        ) as apply_mock:
            result = runner.invoke(
                app,
                [
                    "apply-model-catalog-bootstrap",
                    "garmin_watch",
                    "--operator-id",
                    "ops-bot",
                    "--min-sample-count",
                    "25",
                    "--limit",
                    "5",
                    "--name-query",
                    "solar",
                    "--apply",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["canonicalCategoryCode"], "garmin_watch")
        self.assertEqual(payload["import"]["importedCount"], 3)
        apply_mock.assert_called_once_with(
            business_domain="garmin_watch",
            operator_id="ops-bot",
            min_sample_count=25,
            limit=5,
            active_only=True,
            name_query="solar",
            dry_run=False,
        )

    def test_summarize_xianyu_raw_categories_command_outputs_summary(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.build_xianyu_raw_category_summary",
            return_value={
                "sourcePlatform": "xianyu",
                "categoryCount": 1,
                "items": [{"xianyuCatId": "50025387", "needsOnboarding": True}],
            },
        ) as summary_mock:
            result = runner.invoke(
                app,
                [
                    "summarize-xianyu-raw-categories",
                    "--source-keyword",
                    "macbookpro14寸m1max",
                    "--unmapped-only",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["sourcePlatform"], "xianyu")
        summary_mock.assert_called_once()
        self.assertEqual(summary_mock.call_args.kwargs["source_keyword"], "macbookpro14寸m1max")
        self.assertTrue(summary_mock.call_args.kwargs["unmapped_only"])

    def test_report_xianyu_raw_category_coverage_command_outputs_summary(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.build_xianyu_raw_category_coverage_report",
            return_value={
                "counts": {"totalItems": 10, "backfillCandidateItems": 3},
                "coverage": {"rawSignalCoverageRatio": 0.6},
                "topUnmappedRawCategories": [],
            },
        ) as report_mock:
            result = runner.invoke(
                app,
                [
                    "report-xianyu-raw-category-coverage",
                    "--source-keyword",
                    "macbookpro14寸m1max",
                    "--unmapped-limit",
                    "8",
                    "--item-scan-limit",
                    "500",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["counts"]["backfillCandidateItems"], 3)
        report_mock.assert_called_once()
        self.assertEqual(report_mock.call_args.kwargs["source_keyword"], "macbookpro14寸m1max")
        self.assertEqual(report_mock.call_args.kwargs["unmapped_limit"], 8)
        self.assertEqual(report_mock.call_args.kwargs["item_scan_limit"], 500)

    def test_draft_xianyu_category_onboarding_command_outputs_draft(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.build_xianyu_category_onboarding_draft",
            return_value={
                "selection": {"xianyuCatId": "50025387"},
                "analysis": {"sampleCount": 5},
                "payload": {"mappings": [{"matchScope": "CAT_TB"}]},
            },
        ) as draft_mock:
            result = runner.invoke(
                app,
                [
                    "draft-xianyu-category-onboarding",
                    "--source-keyword",
                    "macbookpro14寸m1max",
                    "--sample-limit",
                    "10",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["payload"]["mappings"][0]["matchScope"], "CAT_TB")
        draft_mock.assert_called_once()
        self.assertEqual(draft_mock.call_args.kwargs["source_keyword"], "macbookpro14寸m1max")
        self.assertEqual(draft_mock.call_args.kwargs["sample_limit"], 10)

    def test_persist_xianyu_category_onboarding_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "onboarding.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "catalog": {
                            "category": {"code": "apple_m_series", "name": "Apple M 系列电脑", "path": "电脑/Apple", "level": 2},
                            "template": {
                                "version": 1,
                                "status": "PUBLISHED",
                                "effectiveAt": "2026-04-06T00:00:00+00:00",
                                "items": [],
                            },
                            "attributes": [],
                        },
                        "mappings": [{"matchScope": "CAT_TB", "xianyuCatId": "50025387", "xianyuTbCatId": "50014945"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "goofish_insight.entrypoints.cli.admin.persist_xianyu_category_onboarding",
                return_value={
                    "dryRun": False,
                    "categoryId": "cat-1",
                    "templateId": "tpl-1",
                    "mappingCount": 1,
                },
            ) as persist_mock:
                result = runner.invoke(
                    app,
                    [
                        "persist-xianyu-category-onboarding",
                        str(payload_path),
                        "--operator-id",
                        "ops-bot",
                        "--apply",
                    ],
                )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mappingCount"], 1)
        persist_mock.assert_called_once()

    def test_backfill_xianyu_raw_category_signals_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.backfill_xianyu_raw_category_signals",
            return_value={
                "dryRun": False,
                "candidateCount": 2,
                "updatedCount": 1,
                "reasonCounts": {"updated": 1},
                "items": [{"itemId": "apple-item-1", "status": "updated"}],
            },
        ) as backfill_mock:
            result = runner.invoke(
                app,
                [
                    "backfill-xianyu-raw-category-signals",
                    "--source-keyword",
                    "macbookpro14",
                    "--limit",
                    "200",
                    "--apply",
                    "--overwrite",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["updatedCount"], 1)
        backfill_mock.assert_called_once()
        self.assertEqual(backfill_mock.call_args.kwargs["source_keyword"], "macbookpro14")
        self.assertEqual(backfill_mock.call_args.kwargs["limit"], 200)
        self.assertFalse(backfill_mock.call_args.kwargs["dry_run"])
        self.assertTrue(backfill_mock.call_args.kwargs["overwrite"])

    def test_sync_xianyu_onboarding_queue_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.sync_xianyu_category_onboarding_queue",
            return_value={
                "dryRun": False,
                "createdCount": 2,
                "resolvedCount": 1,
                "items": [],
            },
        ) as sync_mock:
            result = runner.invoke(
                app,
                [
                    "sync-xianyu-onboarding-queue",
                    "--operator-id",
                    "ops-bot",
                    "--source-keyword",
                    "macbookpro14",
                    "--item-scan-limit",
                    "500",
                    "--apply",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["createdCount"], 2)
        sync_mock.assert_called_once()
        self.assertEqual(sync_mock.call_args.kwargs["operator_id"], "ops-bot")
        self.assertEqual(sync_mock.call_args.kwargs["source_keyword"], "macbookpro14")
        self.assertEqual(sync_mock.call_args.kwargs["item_scan_limit"], 500)
        self.assertFalse(sync_mock.call_args.kwargs["dry_run"])

    def test_list_xianyu_onboarding_queue_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.list_xianyu_category_onboarding_queue",
            return_value={
                "total": 1,
                "items": [{"matchKey": "C_CAT:126854525", "status": "PENDING"}],
            },
        ) as list_mock:
            result = runner.invoke(
                app,
                [
                    "list-xianyu-onboarding-queue",
                    "--status",
                    "pending",
                    "--limit",
                    "10",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["total"], 1)
        list_mock.assert_called_once()
        self.assertEqual(list_mock.call_args.kwargs["status"], "pending")
        self.assertEqual(list_mock.call_args.kwargs["limit"], 10)

    def test_update_xianyu_onboarding_queue_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.update_xianyu_category_onboarding_queue_status",
            return_value={
                "dryRun": False,
                "queue": {"id": "queue-1", "status": "IN_PROGRESS"},
            },
        ) as update_mock:
            result = runner.invoke(
                app,
                [
                    "update-xianyu-onboarding-queue",
                    "IN_PROGRESS",
                    "--operator-id",
                    "ops-bot",
                    "--queue-id",
                    "queue-1",
                    "--owner-operator-id",
                    "alice",
                    "--status-note",
                    "picked up",
                    "--apply",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["queue"]["status"], "IN_PROGRESS")
        update_mock.assert_called_once()
        self.assertEqual(update_mock.call_args.kwargs["queue_id"], "queue-1")
        self.assertEqual(update_mock.call_args.kwargs["owner_operator_id"], "alice")
        self.assertEqual(update_mock.call_args.kwargs["status_note"], "picked up")
        self.assertFalse(update_mock.call_args.kwargs["dry_run"])

    def test_persist_catalog_backfill_template_command_invokes_service(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.persist_catalog_backfill_template",
            return_value={"categoryId": "cat-1", "templateId": "tpl-1", "dryRun": False},
        ) as persist_mock:
            result = runner.invoke(
                app,
                [
                    "persist-catalog-backfill-template",
                    "garmin",
                    "--operator-id",
                    "ops-bot",
                    "--apply",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["templateId"], "tpl-1")
        self.assertFalse(persist_mock.call_args.kwargs["dry_run"])
        self.assertEqual(persist_mock.call_args.kwargs["business_domain"], "garmin_watch")

    def test_preview_catalog_backfill_template_command_accepts_legacy_business_domain_option(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.build_catalog_backfill_template_payload",
            return_value={"category": {"code": "apple_computer"}},
        ) as preview_mock:
            result = runner.invoke(
                app,
                [
                    "preview-catalog-backfill-template",
                    "--business-domain",
                    "apple_m_series",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        preview_mock.assert_called_once_with(business_domain="apple_computer")

    def test_preview_catalog_backfill_template_command_rejects_conflicting_scope_inputs(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        result = runner.invoke(
            app,
            [
                "preview-catalog-backfill-template",
                "apple_computer",
                "--business-domain",
                "garmin",
            ],
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("conflicts", result.stderr)

    def test_preview_catalog_backfill_template_command_requires_scope_input(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        result = runner.invoke(app, ["preview-catalog-backfill-template"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Provide category_code", result.stderr)

    def test_persist_catalog_backfill_item_command_invokes_service(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.persist_catalog_backfill_item",
            return_value={"spuId": "spu-1", "dryRun": True},
        ) as persist_mock:
            result = runner.invoke(
                app,
                [
                    "persist-catalog-backfill-item",
                    "983778933882",
                    "--operator-id",
                    "ops-bot",
                    "--dry-run",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["spuId"], "spu-1")
        self.assertFalse(persist_mock.call_args.kwargs["allow_warnings"])

    def test_persist_catalog_backfill_batch_command_invokes_service(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.persist_catalog_backfill_batch",
            return_value={"processedCount": 2, "failedCount": 0},
        ) as persist_mock:
            result = runner.invoke(
                app,
                [
                    "persist-catalog-backfill-batch",
                    "apple_m_series",
                    "--operator-id",
                    "ops-bot",
                    "--limit",
                    "2",
                    "--dry-run",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["processedCount"], 2)
        self.assertEqual(persist_mock.call_args.kwargs["business_domain"], "apple_computer")
        self.assertTrue(persist_mock.call_args.kwargs["dry_run"])
        self.assertTrue(persist_mock.call_args.kwargs["enriched_only"])
        self.assertTrue(persist_mock.call_args.kwargs["skip_existing"])

    def test_run_catalog_backfill_migration_command_invokes_service(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.run_catalog_backfill_migration",
            return_value={"processedCount": 10, "failedCount": 0},
        ) as run_mock:
            result = runner.invoke(
                app,
                [
                    "run-catalog-backfill-migration",
                    "apple_m_series",
                    "--operator-id",
                    "ops-bot",
                    "--batch-size",
                    "200",
                    "--apply",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["processedCount"], 10)
        self.assertEqual(run_mock.call_args.kwargs["business_domain"], "apple_computer")
        self.assertEqual(run_mock.call_args.kwargs["batch_size"], 200)
        self.assertFalse(run_mock.call_args.kwargs["dry_run"])

    def test_report_catalog_backfill_reconciliation_command_invokes_service(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.build_catalog_backfill_reconciliation_report",
            return_value={"counts": {"migratedSpuTotal": 4}},
        ) as report_mock:
            result = runner.invoke(
                app,
                [
                    "report-catalog-backfill-reconciliation",
                    "garmin",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["counts"]["migratedSpuTotal"], 4)
        report_mock.assert_called_once_with(business_domain="garmin_watch")

    def test_audit_model_catalog_scope_command_outputs_payload(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.build_model_catalog_scope_audit",
            return_value={
                "categoryCode": "apple_computer",
                "findingCount": 2,
                "resourceCounts": {"alias": 1, "model": 1},
            },
        ) as audit_mock:
            result = runner.invoke(
                app,
                [
                    "audit-model-catalog-scope",
                    "--business-domain",
                    "apple_m_series",
                    "--include-inactive",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["findingCount"], 2)
        audit_mock.assert_called_once()
        self.assertEqual(audit_mock.call_args.kwargs["category_code"], "apple_computer")
        self.assertFalse(audit_mock.call_args.kwargs["active_only"])

    def test_cleanup_model_catalog_scope_command_outputs_payload(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.cleanup_model_catalog_scope_mismatches",
            return_value={
                "categoryCode": "garmin_watch",
                "dryRun": False,
                "cleanedModelCount": 1,
            },
        ) as cleanup_mock:
            result = runner.invoke(
                app,
                [
                    "cleanup-model-catalog-scope",
                    "garmin_watch",
                    "--operator-id",
                    "ops-bot",
                    "--apply",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["cleanedModelCount"], 1)
        cleanup_mock.assert_called_once()
        self.assertEqual(cleanup_mock.call_args.kwargs["category_code"], "garmin_watch")
        self.assertEqual(cleanup_mock.call_args.kwargs["operator_id"], "ops-bot")
        self.assertFalse(cleanup_mock.call_args.kwargs["dry_run"])

    def test_report_feed_pre_ingest_rejections_command_outputs_payload(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.build_feed_pre_ingest_rejection_report",
            return_value={
                "categoryCode": "apple_computer",
                "dbSummary": {"rejectedItemCount": 3},
                "logSummary": {"sampleCount": 2},
            },
        ) as report_mock:
            result = runner.invoke(
                app,
                [
                    "report-feed-pre-ingest-rejections",
                    "--business-domain",
                    "apple_m_series",
                    "--limit",
                    "10",
                    "--sample-limit",
                    "5",
                    "--log-scan-lines",
                    "250",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["dbSummary"]["rejectedItemCount"], 3)
        report_mock.assert_called_once()
        self.assertEqual(report_mock.call_args.kwargs["category_code"], "apple_computer")
        self.assertEqual(report_mock.call_args.kwargs["limit"], 10)
        self.assertEqual(report_mock.call_args.kwargs["sample_limit"], 5)
        self.assertEqual(report_mock.call_args.kwargs["log_scan_lines"], 250)

    def test_persist_catalog_payload_command_invokes_persistence_service(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "persist.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "requestId": "req-persist",
                        "spu": {
                            "categoryId": "00000000-0000-0000-0000-000000000001",
                            "templateId": "00000000-0000-0000-0000-000000000011",
                            "title": "小米 15",
                        },
                        "spuAttributes": [],
                        "skus": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "goofish_insight.entrypoints.cli.admin.persist_catalog_payload",
                return_value={
                    "dryRun": False,
                    "requestId": "req-persist",
                    "spuId": "00000000-0000-0000-0000-000000000099",
                    "skuIds": [],
                    "spuAttributeCount": 0,
                    "skuCount": 0,
                    "skuAttributeCount": 0,
                    "outboxEventId": "00000000-0000-0000-0000-000000000199",
                    "auditLogId": "00000000-0000-0000-0000-000000000299",
                },
            ) as persist_mock:
                result = runner.invoke(
                    app,
                    [
                        "persist-catalog-payload",
                        str(payload_path),
                        "--operator-id",
                        "ops-bot",
                        "--apply",
                    ],
                )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["requestId"], "req-persist")
        persist_mock.assert_called_once()
        self.assertEqual(persist_mock.call_args.kwargs["operator_id"], "ops-bot")
        self.assertFalse(persist_mock.call_args.kwargs["dry_run"])

    def test_replace_catalog_payload_command_invokes_persistence_service(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "replace.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "requestId": "req-replace",
                        "spu": {
                            "id": "00000000-0000-0000-0000-000000000099",
                            "categoryId": "00000000-0000-0000-0000-000000000001",
                            "templateId": "00000000-0000-0000-0000-000000000011",
                            "title": "小米 15",
                        },
                        "spuAttributes": [],
                        "skus": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "goofish_insight.entrypoints.cli.admin.replace_catalog_payload",
                return_value={
                    "dryRun": False,
                    "requestId": "req-replace",
                    "spuId": "00000000-0000-0000-0000-000000000099",
                    "skuIds": [],
                    "spuAttributeCount": 0,
                    "skuCount": 0,
                    "skuAttributeCount": 0,
                    "outboxEventId": "00000000-0000-0000-0000-000000000199",
                    "auditLogId": "00000000-0000-0000-0000-000000000299",
                },
            ) as replace_mock:
                result = runner.invoke(
                    app,
                    [
                        "replace-catalog-payload",
                        str(payload_path),
                        "--operator-id",
                        "ops-bot",
                        "--apply",
                    ],
                )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["requestId"], "req-replace")
        replace_mock.assert_called_once()
        self.assertEqual(replace_mock.call_args.kwargs["operator_id"], "ops-bot")
        self.assertFalse(replace_mock.call_args.kwargs["dry_run"])

    def test_persist_catalog_template_payload_command_invokes_template_service(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "template.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "requestId": "req-template",
                        "category": {
                            "code": "phone",
                            "name": "手机",
                            "path": "electronics/phone",
                            "level": 2,
                        },
                        "attributes": [
                            {
                                "code": "color",
                                "name": "颜色",
                                "dataType": "ENUM",
                                "valueScope": "SKU",
                                "options": [{"optionCode": "black", "optionName": "黑色"}],
                            }
                        ],
                        "template": {
                            "version": 1,
                            "items": [{"attributeCode": "color", "isSale": True}],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "goofish_insight.entrypoints.cli.admin.persist_catalog_template_payload",
                return_value={
                    "dryRun": False,
                    "requestId": "req-template",
                    "categoryId": "00000000-0000-0000-0000-000000000401",
                    "templateId": "00000000-0000-0000-0000-000000000402",
                    "attributeCount": 1,
                    "optionCount": 1,
                    "templateItemCount": 1,
                    "auditLogId": "00000000-0000-0000-0000-000000000499",
                },
            ) as persist_mock:
                result = runner.invoke(
                    app,
                    [
                        "persist-catalog-template-payload",
                        str(payload_path),
                        "--operator-id",
                        "ops-bot",
                        "--apply",
                    ],
                )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["requestId"], "req-template")
        persist_mock.assert_called_once()
        self.assertEqual(persist_mock.call_args.kwargs["operator_id"], "ops-bot")
        self.assertFalse(persist_mock.call_args.kwargs["dry_run"])

    def test_persist_catalog_template_version_command_invokes_service(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "template-version.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "requestId": "req-template-v2",
                        "categoryId": "cat-1",
                        "template": {
                            "version": 2,
                            "items": [{"attributeCode": "color", "isSale": True}],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "goofish_insight.entrypoints.cli.admin.persist_catalog_template_version_payload",
                return_value={
                    "dryRun": False,
                    "requestId": "req-template-v2",
                    "categoryId": "cat-1",
                    "templateId": "tpl-2",
                    "templateVersion": 2,
                    "templateItemCount": 1,
                    "auditLogId": "audit-1",
                },
            ) as persist_mock:
                result = runner.invoke(
                    app,
                    [
                        "persist-catalog-template-version",
                        str(payload_path),
                        "--operator-id",
                        "ops-bot",
                        "--apply",
                    ],
                )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["templateVersion"], 2)
        persist_mock.assert_called_once()
        self.assertEqual(persist_mock.call_args.kwargs["operator_id"], "ops-bot")
        self.assertFalse(persist_mock.call_args.kwargs["dry_run"])

    def test_list_catalog_spus_command_outputs_page(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.admin.session_scope",
                _fake_session_scope,
            ),
            patch(
                "goofish_insight.entrypoints.cli.admin.build_catalog_spu_page",
                return_value={
                    "page": 1,
                    "pageSize": 20,
                    "total": 1,
                    "items": [{"id": "spu-1", "title": "小米 15 Pro"}],
                },
            ) as page_mock,
        ):
            result = runner.invoke(
                app,
                [
                    "list-catalog-spus",
                    "--category-id",
                    "cat-1",
                    "--status",
                    "ACTIVE",
                    "--page",
                    "1",
                    "--page-size",
                    "20",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["total"], 1)
        page_mock.assert_called_once()
        self.assertEqual(page_mock.call_args.kwargs["category_id"], "cat-1")
        self.assertEqual(page_mock.call_args.kwargs["status"], "ACTIVE")

    def test_list_catalog_skus_command_outputs_page(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.admin.session_scope",
                _fake_session_scope,
            ),
            patch(
                "goofish_insight.entrypoints.cli.admin.build_catalog_sku_page",
                return_value={
                    "page": 1,
                    "pageSize": 20,
                    "total": 2,
                    "items": [{"id": "sku-1", "skuCode": "MI15P-BLK-12G"}],
                },
            ) as page_mock,
        ):
            result = runner.invoke(
                app,
                [
                    "list-catalog-skus",
                    "--spu-id",
                    "spu-1",
                    "--status",
                    "ACTIVE",
                    "--page",
                    "1",
                    "--page-size",
                    "20",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["total"], 2)
        page_mock.assert_called_once()
        self.assertEqual(page_mock.call_args.kwargs["spu_id"], "spu-1")
        self.assertEqual(page_mock.call_args.kwargs["status"], "ACTIVE")

    def test_show_catalog_spu_command_outputs_detail(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.admin.session_scope",
                _fake_session_scope,
            ),
            patch(
                "goofish_insight.entrypoints.cli.admin.build_catalog_spu_detail",
                return_value={"spu": {"id": "spu-1", "title": "小米 15"}},
            ) as detail_mock,
        ):
            result = runner.invoke(app, ["show-catalog-spu", "spu-1"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["spu"]["id"], "spu-1")
        detail_mock.assert_called_once()

    def test_show_catalog_template_command_outputs_detail(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.admin.session_scope",
                _fake_session_scope,
            ),
            patch(
                "goofish_insight.entrypoints.cli.admin.build_catalog_template_detail",
                return_value={"template": {"id": "tpl-1", "version": 1}},
            ) as detail_mock,
        ):
            result = runner.invoke(app, ["show-catalog-template", "tpl-1"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["template"]["id"], "tpl-1")
        detail_mock.assert_called_once()

    def test_list_catalog_templates_command_outputs_detail(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.admin.session_scope",
                _fake_session_scope,
            ),
            patch(
                "goofish_insight.entrypoints.cli.admin.build_catalog_category_templates",
                return_value={
                    "category": {"id": "cat-1", "code": "phone"},
                    "templateCount": 2,
                    "latestTemplateId": "tpl-2",
                    "templates": [{"id": "tpl-2", "version": 2}, {"id": "tpl-1", "version": 1}],
                },
            ) as detail_mock,
        ):
            result = runner.invoke(app, ["list-catalog-templates", "cat-1"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["latestTemplateId"], "tpl-2")
        detail_mock.assert_called_once()

    def test_show_catalog_outbox_command_outputs_rows(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.admin.session_scope",
                _fake_session_scope,
            ),
            patch(
                "goofish_insight.entrypoints.cli.admin.build_catalog_outbox_rows",
                return_value=[{"id": "evt-1", "status": "PENDING"}],
            ) as rows_mock,
        ):
            result = runner.invoke(app, ["show-catalog-outbox", "--limit", "5"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["id"], "evt-1")
        rows_mock.assert_called_once()

    def test_process_catalog_outbox_command_invokes_service(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.process_catalog_outbox_events",
            return_value={"dryRun": False, "processedCount": 1, "failedCount": 0, "events": []},
        ) as process_mock:
            result = runner.invoke(app, ["process-catalog-outbox", "--limit", "10", "--apply"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["processedCount"], 1)
        process_mock.assert_called_once_with(limit=10, dry_run=False)

    def test_check_catalog_migration_command_outputs_report(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.admin.session_scope",
                _fake_session_scope,
            ),
            patch(
                "goofish_insight.entrypoints.cli.admin.build_catalog_migration_report",
                return_value={
                    "alembicRevision": "20260405_0008",
                    "checks": [{"name": "alembic_revision_present", "ok": True}],
                },
            ) as report_mock,
        ):
            result = runner.invoke(
                app,
                [
                    "check-catalog-migration",
                    "--category-id",
                    "cat-1",
                    "--spu-id",
                    "spu-1",
                    "--expected-template-id",
                    "tpl-3",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["alembicRevision"], "20260405_0008")
        report_mock.assert_called_once()
        self.assertEqual(report_mock.call_args.kwargs["category_id"], "cat-1")
        self.assertEqual(report_mock.call_args.kwargs["spu_id"], "spu-1")
        self.assertEqual(report_mock.call_args.kwargs["expected_template_id"], "tpl-3")

    def test_check_catalog_scoped_migration_command_outputs_report(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.admin.session_scope",
                _fake_session_scope,
            ),
            patch(
                "goofish_insight.entrypoints.cli.admin.build_catalog_scoped_migration_report",
                return_value={
                    "overallOk": True,
                    "businessDomains": ["apple_m_series", "garmin"],
                    "checks": [{"name": "apple_m_series_coverage_complete", "ok": True}],
                },
            ) as report_mock,
        ):
            result = runner.invoke(
                app,
                [
                    "check-catalog-scoped-migration",
                    "--category-id",
                    "cat-1",
                    "--spu-id",
                    "spu-1",
                    "--expected-template-id",
                    "tpl-3",
                    "--business-domain",
                    "apple_m_series",
                    "--business-domain",
                    "garmin",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["overallOk"])
        self.assertEqual(payload["businessDomains"], ["apple_m_series", "garmin"])
        report_mock.assert_called_once()
        self.assertEqual(report_mock.call_args.kwargs["category_id"], "cat-1")
        self.assertEqual(report_mock.call_args.kwargs["spu_id"], "spu-1")
        self.assertEqual(report_mock.call_args.kwargs["expected_template_id"], "tpl-3")
        self.assertEqual(report_mock.call_args.kwargs["business_domains"], ["apple_m_series", "garmin"])

    def test_check_catalog_pricing_dual_read_command_outputs_report(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.admin.session_scope",
                _fake_session_scope,
            ),
            patch(
                "goofish_insight.entrypoints.cli.admin.build_catalog_pricing_dual_read_report",
                return_value={
                    "overallOk": True,
                    "businessDomains": ["apple_m_series"],
                    "checks": [{"name": "apple_m_series_dual_read_spu_coverage", "ok": True}],
                },
            ) as report_mock,
        ):
            result = runner.invoke(
                app,
                [
                    "check-catalog-pricing-dual-read",
                    "--business-domain",
                    "apple_m_series",
                    "--freshness-days",
                    "14",
                    "--expected-spu-coverage-ratio",
                    "0.95",
                    "--expected-price-match-ratio",
                    "0.97",
                    "--sample-limit",
                    "5",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["overallOk"])
        self.assertEqual(payload["businessDomains"], ["apple_m_series"])
        report_mock.assert_called_once()
        self.assertEqual(report_mock.call_args.kwargs["business_domains"], ["apple_m_series"])
        self.assertEqual(report_mock.call_args.kwargs["freshness_days"], 14)
        self.assertEqual(report_mock.call_args.kwargs["expected_spu_coverage_ratio"], 0.95)
        self.assertEqual(report_mock.call_args.kwargs["expected_price_match_ratio"], 0.97)
        self.assertEqual(report_mock.call_args.kwargs["sample_limit"], 5)

    def test_backfill_catalog_pricing_dual_read_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.admin.session_scope",
                _fake_session_scope,
            ),
            patch(
                "goofish_insight.entrypoints.cli.admin.run_catalog_pricing_dual_read_backfill",
                return_value={
                    "dryRun": False,
                    "businessDomains": ["apple_m_series"],
                    "totalProcessedCount": 2,
                    "domainReports": [],
                },
            ) as backfill_mock,
        ):
            result = runner.invoke(
                app,
                [
                    "backfill-catalog-pricing-dual-read",
                    "--business-domain",
                    "apple_m_series",
                    "--operator-id",
                    "tester",
                    "--freshness-days",
                    "7",
                    "--limit",
                    "2",
                    "--offset",
                    "10",
                    "--apply",
                    "--strict-warnings",
                    "--process-outbox",
                    "--min-spu-attribute-count",
                    "4",
                    "--min-sku-attribute-count",
                    "2",
                    "--sample-limit",
                    "5",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["dryRun"])
        self.assertEqual(payload["totalProcessedCount"], 2)
        backfill_mock.assert_called_once()
        self.assertEqual(backfill_mock.call_args.kwargs["business_domains"], ["apple_m_series"])
        self.assertEqual(backfill_mock.call_args.kwargs["operator_id"], "tester")
        self.assertEqual(backfill_mock.call_args.kwargs["freshness_days"], 7)
        self.assertEqual(backfill_mock.call_args.kwargs["limit"], 2)
        self.assertEqual(backfill_mock.call_args.kwargs["offset"], 10)
        self.assertFalse(backfill_mock.call_args.kwargs["dry_run"])
        self.assertFalse(backfill_mock.call_args.kwargs["allow_warnings"])
        self.assertTrue(backfill_mock.call_args.kwargs["process_outbox"])
        self.assertEqual(backfill_mock.call_args.kwargs["min_spu_attribute_count"], 4)
        self.assertEqual(backfill_mock.call_args.kwargs["min_sku_attribute_count"], 2)
        self.assertEqual(backfill_mock.call_args.kwargs["sample_limit"], 5)

    def test_preview_catalog_template_upgrade_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.preview_catalog_template_upgrade",
            return_value={
                "spuId": "spu-1",
                "targetTemplateId": "tpl-2",
                "requiresSkuPayloadRewrite": True,
            },
        ) as preview_mock:
            result = runner.invoke(app, ["preview-catalog-template-upgrade", "spu-1", "tpl-2"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["targetTemplateId"], "tpl-2")
        preview_mock.assert_called_once_with(spu_id="spu-1", target_template_id="tpl-2")

    def test_preview_catalog_template_replace_plan_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.preview_catalog_template_replace_plan",
            return_value={
                "spuId": "spu-1",
                "targetTemplateId": "tpl-2",
                "readyForReplace": True,
            },
        ) as preview_mock:
            result = runner.invoke(app, ["preview-catalog-template-replace-plan", "spu-1", "tpl-2"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["readyForReplace"])
        preview_mock.assert_called_once_with(spu_id="spu-1", target_template_id="tpl-2")

    def test_apply_catalog_template_upgrade_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.apply_catalog_template_upgrade",
            return_value={
                "dryRun": False,
                "requestId": "req-upgrade",
                "spuId": "spu-1",
                "fromTemplateId": "tpl-1",
                "toTemplateId": "tpl-3",
            },
        ) as apply_mock:
            result = runner.invoke(
                app,
                [
                    "apply-catalog-template-upgrade",
                    "spu-1",
                    "tpl-3",
                    "--operator-id",
                    "ops-bot",
                    "--request-id",
                    "req-upgrade",
                    "--apply",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["toTemplateId"], "tpl-3")
        apply_mock.assert_called_once_with(
            spu_id="spu-1",
            target_template_id="tpl-3",
            operator_id="ops-bot",
            request_id="req-upgrade",
            dry_run=False,
        )

    def test_apply_catalog_template_replace_plan_command_outputs_result(self) -> None:
        app = typer.Typer()
        register_admin_commands(
            app,
            alembic_config=lambda: None,
            discover_attached_browsers=lambda: [],
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.admin.apply_catalog_template_replace_plan",
            return_value={
                "dryRun": False,
                "requestId": "req-replace-plan",
                "spuId": "spu-1",
                "targetTemplateId": "tpl-2",
            },
        ) as apply_mock:
            result = runner.invoke(
                app,
                [
                    "apply-catalog-template-replace-plan",
                    "spu-1",
                    "tpl-2",
                    "--operator-id",
                    "ops-bot",
                    "--request-id",
                    "req-replace-plan",
                    "--apply",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["targetTemplateId"], "tpl-2")
        apply_mock.assert_called_once_with(
            spu_id="spu-1",
            target_template_id="tpl-2",
            operator_id="ops-bot",
            request_id="req-replace-plan",
            dry_run=False,
        )


if __name__ == "__main__":
    unittest.main()
