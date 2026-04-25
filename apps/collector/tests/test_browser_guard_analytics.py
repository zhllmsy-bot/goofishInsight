from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight.application.services.browser_guard_analytics import (
    build_browser_guard_pattern_report,
    classify_browser_guard_error_signature,
    is_browser_guard_test_task,
)


class BrowserGuardAnalyticsTests(unittest.TestCase):
    def test_classify_browser_guard_error_signature_detects_known_patterns(self) -> None:
        self.assertEqual(
            classify_browser_guard_error_signature("RGV587_ERROR::SM::哎哟喂,被挤爆啦,请稍后重试"),
            "RGV587_ERROR",
        )
        self.assertEqual(
            classify_browser_guard_error_signature("BrowserType.connect_over_cdp: connect ECONNREFUSED 127.0.0.1:9223"),
            "BROWSER_DISCONNECT",
        )
        self.assertEqual(
            classify_browser_guard_error_signature("需要登录后继续"),
            "LOGIN_REQUIRED",
        )

    def test_is_browser_guard_test_task_detects_smoke_and_task_prefixes(self) -> None:
        self.assertTrue(is_browser_guard_test_task("task-a"))
        self.assertTrue(is_browser_guard_test_task("smoke-home-feed"))
        self.assertFalse(is_browser_guard_test_task("garmin-fenix"))

    def test_build_browser_guard_pattern_report_adds_note_when_attempts_missing(self) -> None:
        side_effect = [
            [{"total_attempts": 0, "risk_hits": 0}],
            [],
            [],
            [],
            [],
            [],
            [{"total_events": 3}],
            [],
            [],
            [],
            [{"gap_count": 0}],
        ]
        with patch(
            "goofish_insight.application.services.browser_guard_analytics._fetch_mapping_rows",
            side_effect=side_effect,
        ):
            report = build_browser_guard_pattern_report(
                lookback_hours=24,
                top_n=5,
            )

        self.assertIn("browser_job_attempt has no rows", report["note"])
        self.assertEqual(report["attempt_summary"]["total_attempts"], 0)
        self.assertEqual(report["legacy_batch_risk_event_summary"]["total_events"], 3)


if __name__ == "__main__":
    unittest.main()
