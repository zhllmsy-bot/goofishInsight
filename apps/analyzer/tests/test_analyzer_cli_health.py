from __future__ import annotations

import json
import unittest
from contextlib import nullcontext
from datetime import UTC, date, datetime
from unittest.mock import patch

from typer.testing import CliRunner

from goofish_analyzer.cli import app


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, mapping: dict[str, object | None]) -> None:
        self._mapping = mapping

    def execute(self, statement):
        text = str(statement)
        for key, value in self._mapping.items():
            if key in text:
                return _ScalarResult(value)
        raise AssertionError(f"Unexpected statement: {text}")


class AnalyzerCliHealthTests(unittest.TestCase):
    def test_health_includes_buy_side_latest_outputs(self) -> None:
        runner = CliRunner()
        fake_session = _FakeSession(
            {
                "FROM daily_metrics": date(2026, 4, 20),
                "FROM model_scores": date(2026, 4, 19),
                "FROM analysis_reports": date(2026, 4, 18),
                "FROM buy_price_baseline": date(2026, 4, 17),
                "FROM buy_opportunity": datetime(2026, 4, 20, 8, 30, tzinfo=UTC),
                "FROM buy_alert_event": datetime(2026, 4, 20, 9, 0, tzinfo=UTC),
            }
        )

        with patch("goofish_analyzer.cli.session_scope", return_value=nullcontext(fake_session)):
            result = runner.invoke(app, ["health"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["health_status"], "healthy")
        self.assertEqual(payload["latest_outputs"]["daily_metrics"], "2026-04-20")
        self.assertEqual(payload["latest_buy_outputs"]["buy_price_baselines"], "2026-04-17")
        self.assertEqual(
            payload["latest_buy_outputs"]["buy_opportunities"],
            "2026-04-20T08:30:00+00:00",
        )
        self.assertEqual(
            payload["latest_buy_outputs"]["buy_alert_events"],
            "2026-04-20T09:00:00+00:00",
        )

    def test_status_marks_unknown_when_analyzer_outputs_are_empty_but_keeps_buy_side_visibility(self) -> None:
        runner = CliRunner()
        fake_session = _FakeSession(
            {
                "FROM daily_metrics": None,
                "FROM model_scores": None,
                "FROM analysis_reports": None,
                "FROM buy_price_baseline": date(2026, 4, 21),
                "FROM buy_opportunity": None,
                "FROM buy_alert_event": None,
            }
        )

        with patch("goofish_analyzer.cli.session_scope", return_value=nullcontext(fake_session)):
            result = runner.invoke(app, ["status"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["health"]["health_status"], "unknown")
        self.assertEqual(payload["health"]["latest_outputs"]["analysis_reports"], None)
        self.assertEqual(payload["health"]["latest_buy_outputs"]["buy_price_baselines"], "2026-04-21")
        self.assertEqual(payload["health"]["latest_buy_outputs"]["buy_opportunities"], None)


if __name__ == "__main__":
    unittest.main()
