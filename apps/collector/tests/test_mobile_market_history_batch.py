from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goofish_insight.application.services.mobile_market_history import MobileMarketSnapshot
from goofish_insight.application.services.mobile_market_history_batch import (
    TASK_STATUS_BLOCKED_INPUT,
    TASK_STATUS_DONE,
    build_mainstream_bulk_queue,
    default_queue_state_path,
    load_queue_state,
    model_query_candidates,
    run_bulk_market_history,
    save_queue_state,
)


class MobileMarketHistoryBatchTests(unittest.TestCase):
    def test_model_query_candidates_cover_compact_and_family_forms(self) -> None:
        apple_candidates = model_query_candidates(
            business_domain="apple_m_series",
            model_name="MacBook Air M2 8G 256G",
        )
        garmin_candidates = model_query_candidates(
            business_domain="garmin",
            model_name="Fenix 8",
        )

        self.assertIn("macbook air m2 8g 256g", apple_candidates)
        self.assertIn("macbookairm28g256g", apple_candidates)
        self.assertIn("macbook air m2", apple_candidates)
        self.assertIn("fenix8", garmin_candidates)
        self.assertIn("garmin fenix 8", garmin_candidates)
        canonical_garmin_candidates = model_query_candidates(
            business_domain="garmin_watch",
            model_name="Fenix 8",
        )
        self.assertIn("garmin fenix 8", canonical_garmin_candidates)

    @patch("goofish_insight.application.services.mobile_market_history_batch.build_top_models")
    def test_build_mainstream_bulk_queue_from_top_models(self, mock_build_top_models) -> None:
        mock_build_top_models.return_value = [
            {
                "business_domain": "garmin",
                "model_name": "Fenix 8",
                "listing_count": 123,
                "seller_count": 77,
                "avg_price": 4567.0,
                "last_seen_at": None,
            }
        ]

        state = build_mainstream_bulk_queue(top_n=1)

        self.assertEqual(len(state.tasks), 1)
        self.assertEqual(state.tasks[0].task_id, "garmin_watch:fenix-8")
        self.assertEqual(state.tasks[0].business_domain, "garmin_watch")
        self.assertEqual(state.tasks[0].status, "pending")
        self.assertGreaterEqual(len(state.tasks[0].query_candidates), 2)

    def test_run_bulk_market_history_marks_done_after_success(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="mobile-bulk-state-"))
        state_path = temp_dir / "state.json"
        state_payload = {
            "generated_at": "2026-04-01T00:00:00+00:00",
            "source": {"type": "test"},
            "summary": {},
            "tasks": [
                {
                    "task_id": "garmin:fenix-8",
                    "business_domain": "garmin",
                    "model_name": "Fenix 8",
                    "query_candidates": ["fenix8"],
                    "listing_count": 10,
                    "seller_count": 8,
                    "avg_price": 4999.0,
                    "last_seen_at": None,
                    "status": "pending",
                    "attempt_count": 0,
                    "success_count": 0,
                    "last_attempted_query": None,
                    "last_output_path": None,
                    "last_report_id": None,
                    "last_error": None,
                    "last_snapshot_summary": None,
                    "updated_at": "2026-04-01T00:00:00+00:00",
                    "events": [],
                }
            ],
        }
        state_path.write_text(json.dumps(state_payload), encoding="utf-8")

        snapshot = MobileMarketSnapshot(
            captured_at="2026-04-01T00:00:00+00:00",
            activity="x",
            state="market",
            query="fenix8",
            xml_path="/tmp/x.xml",
            screenshot_path="/tmp/x.png",
            recent_avg_price_7d=4999,
        )

        output_path = temp_dir / "snapshot.json"
        output_path.write_text("{}", encoding="utf-8")

        with (
            patch("goofish_insight.application.services.mobile_market_history_batch.collect_mobile_market_history", return_value=snapshot) as mock_collect,
            patch("goofish_insight.application.services.mobile_market_history_batch.persist_mobile_market_history", return_value=output_path),
            patch("goofish_insight.application.services.mobile_market_history_batch.save_mobile_market_history_report", return_value=99),
        ):
            result = run_bulk_market_history(path=state_path, max_tasks=1, persist_report=True)

        state = load_queue_state(state_path)
        self.assertEqual(result["tasks_completed"], 1)
        self.assertEqual(state.tasks[0].status, TASK_STATUS_DONE)
        self.assertEqual(state.tasks[0].last_report_id, 99)
        mock_collect.assert_called_once_with(
            query="fenix8",
            serial=None,
            max_scrolls=0,
            reset_to_home=True,
        )

    def test_run_bulk_market_history_marks_blocked_when_capture_fails(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="mobile-bulk-state-"))
        state_path = temp_dir / "state.json"
        state_payload = {
            "generated_at": "2026-04-01T00:00:00+00:00",
            "source": {"type": "test"},
            "summary": {},
            "tasks": [
                {
                    "task_id": "apple:mac-mini-m4",
                    "business_domain": "apple_m_series",
                    "model_name": "Mac mini M4",
                    "query_candidates": ["mac mini m4"],
                    "listing_count": 10,
                    "seller_count": 8,
                    "avg_price": 4999.0,
                    "last_seen_at": None,
                    "status": "pending",
                    "attempt_count": 0,
                    "success_count": 0,
                    "last_attempted_query": None,
                    "last_output_path": None,
                    "last_report_id": None,
                    "last_error": None,
                    "last_snapshot_summary": None,
                    "updated_at": "2026-04-01T00:00:00+00:00",
                    "events": [],
                }
            ],
        }
        state_path.write_text(json.dumps(state_payload), encoding="utf-8")

        with patch(
            "goofish_insight.application.services.mobile_market_history_batch.collect_mobile_market_history",
            side_effect=RuntimeError("Unable to advance to the market page automatically."),
        ):
            result = run_bulk_market_history(path=state_path, max_tasks=1, persist_report=False)

        state = load_queue_state(state_path)
        self.assertEqual(result["tasks_blocked"], 1)
        self.assertEqual(state.tasks[0].status, TASK_STATUS_BLOCKED_INPUT)


if __name__ == "__main__":
    unittest.main()
