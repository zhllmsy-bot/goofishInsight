from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from goofish_analyzer.jobs.model_scores import run_model_scores_job
from goofish_analyzer.services.score_builder import _build_model_score_aggregates


class ModelScoreBuilderTests(unittest.TestCase):
    def test_build_model_score_aggregates_scores_by_model_identity(self) -> None:
        rows = [
            type(
                "Row",
                (),
                {
                    "business_domain": "garmin_watch",
                    "resolved_category_id": "cat-watch",
                    "target_category_id": None,
                    "spec_category_id": None,
                    "model_catalog_id": "model-fenix-8",
                    "spec_model_name": "Fenix 8",
                    "item_normalized_model": None,
                    "item_normalized_model_family": "Fenix",
                    "source_keyword": None,
                    "spec_model_family": "Fenix",
                    "spec_product_line": None,
                    "seller_profile_id": 1,
                    "current_price": Decimal("1000"),
                },
            )(),
            type(
                "Row",
                (),
                {
                    "business_domain": "garmin_watch",
                    "resolved_category_id": "cat-watch",
                    "target_category_id": None,
                    "spec_category_id": None,
                    "model_catalog_id": "model-fenix-8",
                    "spec_model_name": "Fenix 8",
                    "item_normalized_model": None,
                    "item_normalized_model_family": "Fenix",
                    "source_keyword": None,
                    "spec_model_family": "Fenix",
                    "spec_product_line": None,
                    "seller_profile_id": 2,
                    "current_price": Decimal("1200"),
                },
            )(),
            type(
                "Row",
                (),
                {
                    "business_domain": "garmin_watch",
                    "resolved_category_id": "cat-watch",
                    "target_category_id": None,
                    "spec_category_id": None,
                    "model_catalog_id": "model-fenix-8",
                    "spec_model_name": "Fenix 8",
                    "item_normalized_model": None,
                    "item_normalized_model_family": "Fenix",
                    "source_keyword": None,
                    "spec_model_family": "Fenix",
                    "spec_product_line": None,
                    "seller_profile_id": 2,
                    "current_price": Decimal("1400"),
                },
            )(),
        ]

        aggregates = _build_model_score_aggregates(rows)

        self.assertEqual(len(aggregates), 1)
        aggregate = aggregates[0]
        self.assertEqual(aggregate.business_domain, "garmin_watch")
        self.assertEqual(aggregate.category_id, "cat-watch")
        self.assertEqual(aggregate.model_catalog_id, "model-fenix-8")
        self.assertEqual(aggregate.normalized_model, "Fenix 8")
        self.assertEqual(aggregate.normalized_model_family, "Fenix")
        self.assertEqual(aggregate.listing_count, 3)
        self.assertEqual(aggregate.unique_seller_count, 2)
        self.assertEqual(aggregate.median_price, Decimal("1200.00"))
        self.assertEqual(aggregate.p25_price, Decimal("1100.00"))
        self.assertEqual(aggregate.p75_price, Decimal("1300.00"))
        self.assertEqual(aggregate.liquidity_score, Decimal("28.00"))
        self.assertEqual(aggregate.profit_potential_score, Decimal("26.67"))
        self.assertEqual(aggregate.selection_score, Decimal("27.53"))


class ModelScoreJobTests(unittest.TestCase):
    def test_run_model_scores_job_records_job_run_metadata(self) -> None:
        job_run_id = uuid4()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("goofish_analyzer.logging.finish_collector_job_run") as finish_mock,
                patch(
                    "goofish_analyzer.jobs.model_scores.build_model_scores",
                    return_value={"score_date": "2026-04-13", "model_count": 2, "listing_count": 9},
                ) as build_mock,
                patch("goofish_analyzer.logging.QualityMetricsService.record_metric") as record_metric_mock,
                patch("goofish_analyzer.logging.start_collector_job_run", return_value=job_run_id) as start_mock,
            ):
                summary = run_model_scores_job(
                    score_date=date(2026, 4, 13),
                    lock_path=Path(tmp_dir) / "model_scores.lock",
                )

        self.assertEqual(summary["model_count"], 2)
        start_mock.assert_called_once()
        build_mock.assert_called_once()
        finish_mock.assert_called_once()
        self.assertEqual(finish_mock.call_args.kwargs["status"], "completed")
        self.assertEqual(finish_mock.call_args.kwargs["metadata"]["model_count"], 2)
        record_metric_mock.assert_called_once()
        self.assertEqual(record_metric_mock.call_args.kwargs["metric_key"], "analyzer_job_success_rate")
        self.assertEqual(record_metric_mock.call_args.kwargs["task_key"], "analyzer_model_scores")
        self.assertEqual(record_metric_mock.call_args.kwargs["metric_value"], 1.0)
        self.assertEqual(build_mock.call_args.kwargs["source_mode"], "legacy_items")
        self.assertEqual(summary["source_contract"]["source_mode"], "legacy_items")

    def test_run_model_scores_job_logs_and_raises_failures(self) -> None:
        job_run_id = uuid4()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("goofish_analyzer.logging.finish_collector_job_run") as finish_mock,
                patch("goofish_analyzer.jobs.model_scores.build_model_scores", side_effect=RuntimeError("boom")),
                patch("goofish_analyzer.logging.QualityMetricsService.record_metric") as record_metric_mock,
                patch("goofish_analyzer.logging.start_collector_job_run", return_value=job_run_id),
                patch("goofish_analyzer.logging.logger.exception") as log_exception_mock,
            ):
                with self.assertRaises(RuntimeError):
                    run_model_scores_job(
                        score_date=date(2026, 4, 13),
                        lock_path=Path(tmp_dir) / "model_scores.lock",
                    )

        finish_mock.assert_called_once()
        self.assertEqual(finish_mock.call_args.kwargs["status"], "failed")
        self.assertEqual(finish_mock.call_args.kwargs["metadata"], {"error": "boom"})
        record_metric_mock.assert_called_once()
        self.assertEqual(record_metric_mock.call_args.kwargs["metric_value"], 0.0)
        log_exception_mock.assert_called()


if __name__ == "__main__":
    unittest.main()
