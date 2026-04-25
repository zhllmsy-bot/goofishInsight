from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from goofish_analyzer.cli import _resolve_run_dates
from goofish_analyzer.jobs.daily_metrics import run_daily_metrics_job
from goofish_analyzer.services.metrics_builder import _build_daily_metric_aggregates, _percentile_decimal


class DailyMetricsBuilderTests(unittest.TestCase):
    def test_percentile_decimal_interpolates_and_quantizes(self) -> None:
        values = [Decimal("100"), Decimal("200"), Decimal("400"), Decimal("800")]
        self.assertEqual(_percentile_decimal(values, 0.5), Decimal("300.00"))
        self.assertEqual(_percentile_decimal(values, 0.25), Decimal("175.00"))
        self.assertEqual(_percentile_decimal(values, 0.75), Decimal("500.00"))

    def test_build_daily_metric_aggregates_groups_by_domain_and_category(self) -> None:
        rows = [
            type("Row", (), {"business_domain": "garmin_watch", "resolved_category_id": "cat-a", "target_category_id": None, "seller_profile_id": 1, "current_price": Decimal("1000")})(),
            type("Row", (), {"business_domain": "garmin_watch", "resolved_category_id": "cat-a", "target_category_id": None, "seller_profile_id": 2, "current_price": Decimal("1200")})(),
            type("Row", (), {"business_domain": "apple_computer", "resolved_category_id": None, "target_category_id": "cat-b", "seller_profile_id": 2, "current_price": None})(),
        ]

        aggregates = _build_daily_metric_aggregates(rows)

        self.assertEqual(len(aggregates), 2)
        first = aggregates[0]
        second = aggregates[1]
        self.assertEqual(first.business_domain, "apple_computer")
        self.assertEqual(first.category_id, "cat-b")
        self.assertEqual(first.priced_listing_count, 0)
        self.assertEqual(second.business_domain, "garmin_watch")
        self.assertEqual(second.category_id, "cat-a")
        self.assertEqual(second.listing_count, 2)
        self.assertEqual(second.unique_seller_count, 2)
        self.assertEqual(second.median_price, Decimal("1100.00"))


class DailyMetricsJobTests(unittest.TestCase):
    def test_run_daily_metrics_job_records_job_run_metadata(self) -> None:
        job_run_id = uuid4()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("goofish_analyzer.logging.finish_collector_job_run") as finish_mock,
                patch(
                    "goofish_analyzer.jobs.daily_metrics.build_daily_metrics",
                    return_value={"metric_date": "2026-04-13", "group_count": 3, "listing_count": 10},
                ) as build_mock,
                patch(
                    "goofish_analyzer.adapters.QualityMetricsService.refresh_operational_quality_metrics",
                    return_value={"review_pass_rate": {"recorded": True}},
                ) as refresh_quality_mock,
                patch("goofish_analyzer.logging.QualityMetricsService.record_metric") as record_metric_mock,
                patch("goofish_analyzer.logging.start_collector_job_run", return_value=job_run_id) as start_mock,
            ):
                summary = run_daily_metrics_job(
                    metric_date=date(2026, 4, 13),
                    lock_path=Path(tmp_dir) / "daily_metrics.lock",
                )

        self.assertEqual(summary["group_count"], 3)
        self.assertIn("quality_metrics", summary)
        start_mock.assert_called_once()
        build_mock.assert_called_once()
        refresh_quality_mock.assert_called_once()
        finish_mock.assert_called_once()
        self.assertEqual(finish_mock.call_args.kwargs["status"], "completed")
        self.assertEqual(finish_mock.call_args.kwargs["metadata"]["group_count"], 3)
        record_metric_mock.assert_called_once()
        self.assertEqual(record_metric_mock.call_args.kwargs["metric_key"], "analyzer_job_success_rate")
        self.assertEqual(record_metric_mock.call_args.kwargs["metric_value"], 1.0)
        self.assertEqual(build_mock.call_args.kwargs["source_mode"], "legacy_items")
        self.assertEqual(summary["source_contract"]["source_mode"], "legacy_items")

    def test_run_daily_metrics_job_logs_and_raises_failures(self) -> None:
        job_run_id = uuid4()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("goofish_analyzer.logging.finish_collector_job_run") as finish_mock,
                patch("goofish_analyzer.jobs.daily_metrics.build_daily_metrics", side_effect=RuntimeError("boom")),
                patch("goofish_analyzer.logging.QualityMetricsService.record_metric") as record_metric_mock,
                patch("goofish_analyzer.logging.start_collector_job_run", return_value=job_run_id),
                patch("goofish_analyzer.logging.logger.exception") as log_exception_mock,
            ):
                with self.assertRaises(RuntimeError):
                    run_daily_metrics_job(
                        metric_date=date(2026, 4, 13),
                        lock_path=Path(tmp_dir) / "daily_metrics.lock",
                    )

        finish_mock.assert_called_once()
        self.assertEqual(finish_mock.call_args.kwargs["status"], "failed")
        self.assertEqual(finish_mock.call_args.kwargs["metadata"], {"error": "boom"})
        record_metric_mock.assert_called_once()
        self.assertEqual(record_metric_mock.call_args.kwargs["metric_value"], 0.0)
        log_exception_mock.assert_called()


class AnalyzerCliCatchUpTests(unittest.TestCase):
    def test_resolve_run_dates_uses_earliest_missing_output_date(self) -> None:
        latest_by_job = {
            "daily_metrics": date(2026, 4, 14),
            "model_scores": date(2026, 4, 13),
            "analysis_reports": date(2026, 4, 12),
        }

        with patch(
            "goofish_analyzer.cli._latest_output_date",
            side_effect=lambda *, job, business_domain, category_id: latest_by_job[job],
        ):
            dates = _resolve_run_dates(
                jobs_to_run=["daily_metrics", "model_scores", "analysis_reports"],
                target_date=date(2026, 4, 15),
                catch_up=True,
                catch_up_lookback_days=7,
                business_domain=None,
                category_id=None,
            )

        self.assertEqual(dates, [date(2026, 4, 13), date(2026, 4, 14), date(2026, 4, 15)])

    def test_resolve_run_dates_without_catch_up_returns_target_only(self) -> None:
        dates = _resolve_run_dates(
            jobs_to_run=["daily_metrics"],
            target_date=date(2026, 4, 15),
            catch_up=False,
            catch_up_lookback_days=7,
            business_domain=None,
            category_id=None,
        )

        self.assertEqual(dates, [date(2026, 4, 15)])

    def test_cli_imports_use_adapters_boundary(self) -> None:
        from goofish_analyzer import adapters

        self.assertTrue(hasattr(adapters, "session_scope"))
        self.assertTrue(hasattr(adapters, "BuyOpportunity"))
        self.assertTrue(hasattr(adapters, "resolve_category_code"))
