from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from goofish_analyzer.cli import app


class AnalyzerCliBuySideTests(unittest.TestCase):
    def test_run_buy_baselines_forwards_expected_arguments(self) -> None:
        runner = CliRunner()

        with patch(
            "goofish_analyzer.cli.run_buy_baselines_job",
            return_value={"categoryCode": "apple_computer", "baselineCount": 12},
        ) as run_mock:
            result = runner.invoke(
                app,
                [
                    "run-buy-baselines",
                    "--category-code",
                    "apple_computer",
                    "--view",
                    "spec",
                    "--baseline-date",
                    "2026-04-24",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["baselineCount"], 12)
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.kwargs["category_code"], "apple_computer")
        self.assertEqual(run_mock.call_args.kwargs["view"], "spec")
        self.assertEqual(str(run_mock.call_args.kwargs["baseline_date"]), "2026-04-24")

    def test_run_buy_opportunities_forwards_expected_arguments(self) -> None:
        runner = CliRunner()

        with patch(
            "goofish_analyzer.cli.run_buy_opportunities_job",
            return_value={"categoryCode": "garmin_watch", "opportunityCount": 7},
        ) as run_mock:
            result = runner.invoke(
                app,
                [
                    "run-buy-opportunities",
                    "--category-code",
                    "garmin_watch",
                    "--min-opportunity-score",
                    "60",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["opportunityCount"], 7)
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.kwargs["category_code"], "garmin_watch")
        self.assertEqual(run_mock.call_args.kwargs["min_opportunity_score"], 60.0)

    def test_run_buy_alerts_forwards_expected_arguments(self) -> None:
        runner = CliRunner()

        with patch(
            "goofish_analyzer.cli.run_buy_alerts_job",
            return_value={"categoryCode": "apple_computer", "alertCount": 3},
        ) as run_mock:
            result = runner.invoke(
                app,
                [
                    "run-buy-alerts",
                    "--category-code",
                    "apple_computer",
                    "--channel",
                    "dashboard",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["alertCount"], 3)
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.kwargs["category_code"], "apple_computer")
        self.assertEqual(run_mock.call_args.kwargs["channel"], "dashboard")


if __name__ == "__main__":
    unittest.main()
