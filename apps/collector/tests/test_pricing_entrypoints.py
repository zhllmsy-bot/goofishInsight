from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import typer
from typer.testing import CliRunner

from goofish_insight.application.services.pricing_reporting import run_template_mode_smoke
from goofish_insight.entrypoints.cli.pricing import register_pricing_commands


@contextmanager
def _fake_session_scope():
    yield object()


class PricingEntrypointTests(unittest.TestCase):
    def test_show_price_bands_outputs_pricing_availability_summary(self) -> None:
        app = typer.Typer()
        register_pricing_commands(app)
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.pricing.build_pricing_views",
            return_value={
                "spec": [
                    {
                        "view": "spec",
                        "category_code": "apple_computer",
                        "brand": "Apple",
                        "product_label": "MacBook Pro / M5",
                        "spec_label": "MacBook Pro / M5 / 16G / 512G",
                        "seller_sample_count": 6,
                        "unique_seller_count": 4,
                        "exact_spec_ratio": 0.88,
                        "reliability_score": 82.0,
                        "latest_seen_at": datetime.now(UTC).isoformat(),
                        "is_actionable": True,
                    }
                ]
            },
        ), patch(
            "goofish_insight.application.services.pricing_reporting.session_scope",
            _fake_session_scope,
        ), patch(
            "goofish_insight.application.services.pricing_reporting.build_pricing_contract",
            return_value={"templateCompleteness": {"isComplete": True}},
        ):
            result = runner.invoke(
                app,
                [
                    "show-price-bands",
                    "--category-code",
                    "apple_computer",
                    "--view",
                    "spec",
                    "--limit",
                    "1",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["pricingAvailability"]["availabilityTier"], "guidance_ready")
        self.assertEqual(payload[0]["pricingAvailabilitySummary"]["readinessSummary"], "可直接按价格指导口径使用")

    def test_show_spec_summary_outputs_block_reason_summary(self) -> None:
        app = typer.Typer()
        register_pricing_commands(app)
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.pricing.build_spec_summary",
            return_value=[
                {
                    "category_code": "apple_computer",
                    "seller_sample_count": 2,
                    "unique_seller_count": 1,
                    "exact_spec_ratio": 0.4,
                    "reliability_score": 55.0,
                    "latest_seen_at": datetime.now(UTC).isoformat(),
                }
            ],
        ), patch(
            "goofish_insight.application.services.pricing_reporting.session_scope",
            _fake_session_scope,
        ), patch(
            "goofish_insight.application.services.pricing_reporting.build_pricing_contract",
            return_value={"templateCompleteness": {"isComplete": True}},
        ):
            result = runner.invoke(
                app,
                [
                    "show-spec-summary",
                    "--category-code",
                    "apple_computer",
                    "--limit",
                    "1",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["pricingAvailability"]["pricingBlockReason"], "insufficient_seller_samples")
        self.assertEqual(
            payload[0]["pricingAvailabilitySummary"]["readinessSummary"],
            "暂不建议引用：卖家样本数不足",
        )

    def test_show_buy_feedback_summary_outputs_missing_field_breakdown(self) -> None:
        app = typer.Typer()
        register_pricing_commands(app)
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.pricing.summarize_buy_feedback_quality",
            return_value={
                "categoryCode": "apple_computer",
                "windowDays": 30,
                "asOf": "2026-04-22T10:00:00+00:00",
                "feedbackCount": 18,
                "acceptCount": 9,
                "rejectCount": 9,
                "rejectReasonCounts": {"too_high": 4, "template mismatch": 5},
                "templateMatchErrorCounts": {"price_anomaly": 2},
                "templateMismatchMissingFieldCounts": {"memory_gb": 2, "storage_gb": 3},
            },
        ), patch(
            "goofish_insight.entrypoints.cli.pricing.summarize_buy_feedback_calibration",
            return_value={
                "categoryCode": "apple_computer",
                "asOf": "2026-04-22T10:00:00+00:00",
                "templateMismatchMissRate": 0.28,
            },
        ):
            result = runner.invoke(
                app,
                [
                    "show-buy-feedback-summary",
                    "--category-code",
                    "apple_computer",
                    "--window-days",
                    "30",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["feedbackCount"], 18)
        self.assertEqual(payload["acceptCount"], 9)
        self.assertEqual(payload["templateMismatchMissingFieldCounts"], {"memory_gb": 2, "storage_gb": 3})
        self.assertEqual(payload["feedbackCalibration"]["templateMismatchMissRate"], 0.28)

    def test_apply_buy_feedback_calibration_outputs_rebuild_summary(self) -> None:
        app = typer.Typer()
        register_pricing_commands(app)
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.pricing.apply_buy_feedback_calibration",
            return_value={
                "categoryCode": "apple_computer",
                "appliedRecommendationCount": 2,
                "baselineRebuild": {"baselineCount": 10},
                "opportunityRefresh": {"opportunityCount": 6},
            },
        ) as apply_mock:
            result = runner.invoke(
                app,
                [
                    "apply-buy-feedback-calibration",
                    "--category-code",
                    "apple_computer",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["appliedRecommendationCount"], 2)
        self.assertEqual(payload["baselineRebuild"]["baselineCount"], 10)
        apply_mock.assert_called_once_with(
            category_code="apple_computer",
            window_days=30,
            operator_id=None,
            recommendation_ids=None,
            dry_run=False,
        )

    def test_run_template_mode_smoke_builds_pass_report(self) -> None:
        def _fake_http_get_json(*, base_url, path, params=None):
            if path == "/api/buy/template-monitoring":
                return {
                    "ok": True,
                    "statusCode": 200,
                    "path": path,
                    "payload": {
                        "featureFlags": {
                            "priceTemplateContractEnabled": True,
                            "priceTemplateDashboardEnabled": True,
                            "priceTemplateOpportunityEnabled": True,
                            "priceTemplateTrendEnabled": True,
                            "priceTemplateAlertStrictMode": True,
                        },
                        "baseline": {
                            "tierCounts": {
                                "guidance_ready": 8,
                                "reference_only": 4,
                                "blocked": 10,
                                "incomplete": 12,
                            }
                        },
                        "opportunity": {
                            "tierCounts": {
                                "guidance_ready": 2,
                                "reference_only": 10,
                                "blocked": 7,
                                "incomplete": 1,
                            }
                        },
                    },
                }
            if path == "/api/buy/opportunities":
                return {
                    "ok": True,
                    "statusCode": 200,
                    "path": path,
                    "payload": {
                        "summary": {
                            "opportunityCount": 20,
                            "feedbackCount": 3,
                            "calibrationRecommendationCount": 2,
                        }
                    },
                }
            if path == "/api/dashboard/sections/filters":
                return {
                    "ok": True,
                    "statusCode": 200,
                    "path": path,
                    "payload": {
                        "filter_catalog": {
                            "product_options": [{"value": "Mac mini / M4"}],
                            "chip_family_options": [{"value": "M4"}],
                            "memory_options": [{"value": 16}],
                            "storage_options": [{"value": 256}],
                        }
                    },
                }
            if path == "/api/dashboard/sections/pricing":
                product_label = str((params or {}).get("product_label") or "").strip()
                if product_label:
                    return {
                        "ok": True,
                        "statusCode": 200,
                        "path": path,
                        "payload": {
                            "pricing_contract": {
                                "requiredSelectorFields": ["product_label", "chip_family", "memory_gb", "storage_gb"],
                                "templateCompleteness": {"status": "complete"},
                                "missingPricingFields": [],
                                "templateKeyPreview": (
                                    "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=16|storage_gb=256"
                                ),
                            }
                        },
                    }
                return {
                    "ok": True,
                    "statusCode": 200,
                    "path": path,
                    "payload": {
                        "pricing_contract": {
                            "requiredSelectorFields": ["product_label", "chip_family", "memory_gb", "storage_gb"],
                            "templateCompleteness": {"status": "partial"},
                            "missingPricingFields": ["product_label", "chip_family", "memory_gb", "storage_gb"],
                            "templateKeyPreview": None,
                        }
                    },
                }
            if path == "/api/dashboard/sections/insights":
                return {
                    "ok": True,
                    "statusCode": 200,
                    "path": path,
                    "payload": {
                        "domain_trend_cards": [
                            {
                                "templateKey": "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=16|storage_gb=256"
                            }
                        ]
                    },
                }
            return {"ok": False, "statusCode": 404, "path": path, "payload": {}, "error": "not mocked"}

        with patch(
            "goofish_insight.application.services.pricing_reporting._http_get_json",
            side_effect=_fake_http_get_json,
        ):
            report = run_template_mode_smoke(
                base_url="http://127.0.0.1:8791",
                category_code="apple_computer",
                window_days=30,
                limit=20,
                pricing_view="spec",
                pricing_scope="all",
                pricing_limit=20,
                pricing_freshness_days=30,
                heartbeat_days=14,
                pricing_min_samples=4,
            )

        self.assertEqual(report["overallStatus"], "pass")
        self.assertGreater(report["checkCount"], 5)

    def test_smoke_template_mode_command_fails_on_warn_when_requested(self) -> None:
        app = typer.Typer()
        register_pricing_commands(app)
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.pricing.run_template_mode_smoke",
            return_value={
                "generatedAt": "2026-04-11T00:00:00+00:00",
                "overallStatus": "warn",
                "checkCount": 1,
                "checks": [{"name": "x", "status": "warn", "detail": "warning"}],
            },
        ), patch(
            "goofish_insight.entrypoints.cli.pricing.write_template_smoke_report",
            return_value=Path("/tmp/template-mode-smoke.json"),
        ):
            result = runner.invoke(
                app,
                ["smoke-template-mode", "--fail-on-warn"],
            )

        self.assertEqual(result.exit_code, 1)

    def test_record_buy_feedback_command_forwards_alert_candidate_linkage_flag(self) -> None:
        app = typer.Typer()
        register_pricing_commands(app)
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.pricing.record_buy_decision_feedback",
            return_value={
                "dryRun": False,
                "opportunity": {"id": "opp-1", "status": "CONTACTED", "decision": "contacted"},
                "alertCandidateLinkage": {"status": "created"},
            },
        ) as feedback_mock:
            result = runner.invoke(
                app,
                [
                    "record-buy-feedback",
                    "opp-1",
                    "contacted",
                    "--link-to-alert-candidate",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        feedback_mock.assert_called_once()
        self.assertTrue(feedback_mock.call_args.kwargs["link_to_alert_candidate"])
        payload = json.loads(result.stdout)
        self.assertEqual(payload["alertCandidateLinkage"]["status"], "created")

    def test_queue_buy_baselines_command_schedules_job(self) -> None:
        app = typer.Typer()
        register_pricing_commands(app)
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.pricing.schedule_buy_baseline_job",
            return_value={"eventId": "event-1", "jobType": "buy.build_baseline"},
        ) as queue_mock:
            result = runner.invoke(
                app,
                [
                    "queue-buy-baselines",
                    "--category-code",
                    "apple_computer",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        queue_mock.assert_called_once()
        payload = json.loads(result.stdout)
        self.assertEqual(payload["eventId"], "event-1")

    def test_process_buy_jobs_command_outputs_summary(self) -> None:
        app = typer.Typer()
        register_pricing_commands(app)
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.pricing.process_buy_job_events",
            return_value={"eventCount": 1, "processedCount": 1, "failedCount": 0},
        ) as process_mock:
            result = runner.invoke(
                app,
                [
                    "process-buy-jobs",
                    "--limit",
                    "5",
                    "--no-dry-run",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        process_mock.assert_called_once_with(limit=5, dry_run=False)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["processedCount"], 1)


if __name__ == "__main__":
    unittest.main()
