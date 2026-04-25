from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from goofish_analyzer.jobs.analysis_reports import run_analysis_reports_job
from goofish_analyzer.services.report_builder import _build_analysis_report_payloads


class AnalysisReportBuilderTests(unittest.TestCase):
    def test_build_analysis_report_payloads_summarizes_daily_metrics_and_top_models(self) -> None:
        daily_metrics = [
            type(
                "DailyMetricRow",
                (),
                {
                    "business_domain": "garmin_watch",
                    "category_id": "cat-watch",
                    "listing_count": 10,
                    "unique_seller_count": 6,
                },
            )()
        ]
        model_scores = [
            type(
                "ModelScoreRow",
                (),
                {
                    "business_domain": "garmin_watch",
                    "category_id": "cat-watch",
                    "normalized_model": "Fenix 8",
                    "normalized_model_family": "Fenix",
                    "model_catalog_id": "model-fenix-8",
                    "selection_score": Decimal("88.50"),
                    "liquidity_score": Decimal("80.00"),
                    "profit_potential_score": Decimal("95.00"),
                    "score_reason": {"listing_count": 10},
                },
            )(),
            type(
                "ModelScoreRow",
                (),
                {
                    "business_domain": "garmin_watch",
                    "category_id": "cat-watch",
                    "normalized_model": "Forerunner 965",
                    "normalized_model_family": "Forerunner",
                    "model_catalog_id": "model-fr-965",
                    "selection_score": Decimal("60.00"),
                    "liquidity_score": Decimal("70.00"),
                    "profit_potential_score": Decimal("40.00"),
                    "score_reason": {"listing_count": 5},
                },
            )(),
        ]

        reports = _build_analysis_report_payloads(
            report_date=date(2026, 4, 13),
            daily_metrics=daily_metrics,
            model_scores=model_scores,
        )

        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertEqual(report.business_domain, "garmin_watch")
        self.assertEqual(report.category_id, "cat-watch")
        self.assertIn("Fenix 8", report.summary)
        self.assertEqual(report.payload["total_listing_count"], 10)
        self.assertEqual(report.payload["top_models"][0]["normalized_model"], "Fenix 8")
        self.assertEqual(report.payload["top_models"][0]["selection_score"], "88.50")


class AnalysisReportsJobTests(unittest.TestCase):
    def test_run_analysis_reports_job_records_job_run_metadata(self) -> None:
        job_run_id = uuid4()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("goofish_analyzer.logging.finish_collector_job_run") as finish_mock,
                patch(
                    "goofish_analyzer.jobs.analysis_reports.build_analysis_reports",
                    return_value={"report_date": "2026-04-13", "report_count": 1},
                ) as build_mock,
                patch("goofish_analyzer.logging.QualityMetricsService.record_metric") as record_metric_mock,
                patch("goofish_analyzer.logging.start_collector_job_run", return_value=job_run_id) as start_mock,
            ):
                summary = run_analysis_reports_job(
                    report_date=date(2026, 4, 13),
                    lock_path=Path(tmp_dir) / "analysis_reports.lock",
                )

        self.assertEqual(summary["report_count"], 1)
        start_mock.assert_called_once()
        build_mock.assert_called_once()
        finish_mock.assert_called_once()
        self.assertEqual(finish_mock.call_args.kwargs["status"], "completed")
        self.assertEqual(finish_mock.call_args.kwargs["metadata"]["report_count"], 1)
        record_metric_mock.assert_called_once()
        self.assertEqual(record_metric_mock.call_args.kwargs["metric_key"], "analyzer_job_success_rate")
        self.assertEqual(record_metric_mock.call_args.kwargs["task_key"], "analyzer_analysis_reports")
        self.assertEqual(record_metric_mock.call_args.kwargs["metric_value"], 1.0)
        self.assertEqual(build_mock.call_args.kwargs["source_mode"], "legacy_items")
        self.assertEqual(summary["source_contract"]["source_mode"], "legacy_items")

    def test_run_analysis_reports_job_logs_and_raises_failures(self) -> None:
        job_run_id = uuid4()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("goofish_analyzer.logging.finish_collector_job_run") as finish_mock,
                patch("goofish_analyzer.jobs.analysis_reports.build_analysis_reports", side_effect=RuntimeError("boom")),
                patch("goofish_analyzer.logging.QualityMetricsService.record_metric") as record_metric_mock,
                patch("goofish_analyzer.logging.start_collector_job_run", return_value=job_run_id),
                patch("goofish_analyzer.logging.logger.exception") as log_exception_mock,
            ):
                with self.assertRaises(RuntimeError):
                    run_analysis_reports_job(
                        report_date=date(2026, 4, 13),
                        lock_path=Path(tmp_dir) / "analysis_reports.lock",
                    )

        finish_mock.assert_called_once()
        self.assertEqual(finish_mock.call_args.kwargs["status"], "failed")
        self.assertEqual(finish_mock.call_args.kwargs["metadata"], {"error": "boom"})
        record_metric_mock.assert_called_once()
        self.assertEqual(record_metric_mock.call_args.kwargs["metric_value"], 0.0)
        log_exception_mock.assert_called()


if __name__ == "__main__":
    unittest.main()
