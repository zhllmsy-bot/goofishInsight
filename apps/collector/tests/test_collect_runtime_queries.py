from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from goofish_insight.application.services.collector_batch_runtime import (
    _batch_collect_process_lock,
    _clamp_batch_plan_pages_for_run,
    _build_batch_cursor_scope_key,
    _commit_rotating_plan_window,
    _build_plan_risk_key,
    _compute_risk_backoff_seconds,
    _count_active_risk_backoff_entries,
    _filter_plans_by_risk_backoff,
    _load_batch_cursor_state,
    _load_batch_risk_backoff_state,
    _latest_risk_backoff_metadata,
    _normalize_checkpoint_mode,
    _save_batch_risk_backoff_state,
    _apply_plan_outcomes_to_risk_backoff_state,
    _default_batch_collect_lock_path,
    _summarize_outcomes,
    _resolve_batch_query_configs,
    _select_rotating_plan_window,
    summarize_batch_risk_event_log,
)
from goofish_insight.entrypoints.cli.collect import BATCH_COLLECT_ALREADY_RUNNING_EXIT_CODE
from goofish_insight.cli import (
    build_manual_verification_transport_message,
    build_search_capture_failure_message,
    infer_auth_state_from_error_message,
    is_browser_disconnect_error,
    should_keep_manual_verification_page_open,
)


class CollectRuntimeQueryTests(unittest.TestCase):
    def test_default_batch_collect_lock_path_points_to_runtime_lock(self) -> None:
        self.assertEqual(str(_default_batch_collect_lock_path()), "reports/runtime/locks/batch_collect.lock")

    def test_batch_collect_process_lock_rejects_second_holder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = Path(tmp_dir) / "batch_collect.lock"
            with _batch_collect_process_lock(lock_path):
                with self.assertRaisesRegex(RuntimeError, "collect-batch already running"):
                    with _batch_collect_process_lock(lock_path):
                        self.fail("expected second lock acquisition to fail")

        self.assertEqual(BATCH_COLLECT_ALREADY_RUNNING_EXIT_CODE, 18)

    def test_is_browser_disconnect_error_matches_closed_page_and_cdp_refused(self) -> None:
        self.assertTrue(
            is_browser_disconnect_error("Page.wait_for_timeout: Target page, context or browser has been closed")
        )
        self.assertTrue(
            is_browser_disconnect_error("BrowserType.connect_over_cdp: connect ECONNREFUSED 127.0.0.1:9223")
        )
        self.assertFalse(is_browser_disconnect_error("No valid search payload captured."))

    def test_build_manual_verification_transport_message_keeps_risk_context(self) -> None:
        message = build_manual_verification_transport_message(
            auth_state="risk_control",
            last_error="dom:请依次连出",
            transport_error="Target page, context or browser has been closed",
        )

        self.assertIn("Risk control blocked the search", message)
        self.assertIn("dom:请依次连出", message)
        self.assertIn("transport_error=Target page, context or browser has been closed", message)

    def test_infer_auth_state_from_error_message_detects_transport_wrapped_risk_message(self) -> None:
        message = build_search_capture_failure_message(
            auth_state="risk_control",
            last_error="iframe:https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/",
        )
        wrapped = f"{message} | transport_error=Target page, context or browser has been closed"

        self.assertEqual(infer_auth_state_from_error_message(wrapped), "risk_control")

    def test_manual_verification_page_policy_keeps_login_not_risk_control(self) -> None:
        self.assertTrue(should_keep_manual_verification_page_open("login_required"))
        self.assertFalse(should_keep_manual_verification_page_open("risk_control"))
        self.assertFalse(should_keep_manual_verification_page_open(None))

    def test_clamp_batch_plan_pages_for_run_caps_positive_pages(self) -> None:
        self.assertEqual(_clamp_batch_plan_pages_for_run(pages=5, max_pages_per_plan=1), 1)
        self.assertEqual(_clamp_batch_plan_pages_for_run(pages=2, max_pages_per_plan=3), 2)

    def test_clamp_batch_plan_pages_for_run_converts_unbounded_pages(self) -> None:
        self.assertEqual(_clamp_batch_plan_pages_for_run(pages=0, max_pages_per_plan=1), 1)
        self.assertEqual(_clamp_batch_plan_pages_for_run(pages=-1, max_pages_per_plan=2), 2)

    def test_resolve_batch_query_configs_prefers_materialized_runtime_queries(self) -> None:
        result = _resolve_batch_query_configs(
            task_config={
                "paging_limit": 5,
                "queries": [{"query": "legacy file query", "pages": 1}],
            },
            runtime_config={
                "queries": [
                    {"query": "db query 1", "pages": 0, "status": "ACTIVE"},
                    {"query": "db query 2", "pages": 3, "status": "ACTIVE"},
                ]
            },
        )

        self.assertEqual([row["query"] for row in result], ["db query 1", "db query 2"])
        self.assertEqual(result[0]["pages"], 0)
        self.assertEqual(result[0]["id"], None)

    def test_resolve_batch_query_configs_falls_back_to_file_queries_when_runtime_is_legacy(self) -> None:
        result = _resolve_batch_query_configs(
            task_config={
                "paging_limit": 8,
                "queries": [{"query": "file query", "pages": 0, "id": 11}],
            },
            runtime_config={
                "queries": [
                    {"query": "legacy keyword query", "pages": 8, "status": "LEGACY"},
                ]
            },
        )

        self.assertEqual(result, [{"id": 11, "query": "file query", "pages": 0}])

    def test_resolve_batch_query_configs_falls_back_to_legacy_runtime_queries_when_file_queries_absent(self) -> None:
        result = _resolve_batch_query_configs(
            task_config={"paging_limit": 6},
            runtime_config={
                "queries": [
                    {"query": "legacy runtime query", "pages": 6, "status": "LEGACY"},
                ]
            },
        )

        self.assertEqual(result, [{"id": None, "query": "legacy runtime query", "pages": 6}])

    def test_select_rotating_plan_window_without_state_file_uses_first_slice(self) -> None:
        plans = ["q1", "q2", "q3", "q4", "q5"]

        selected, rotation = _select_rotating_plan_window(
            plans=plans,
            max_plans_per_run=3,
            cursor_state_path=None,
            scope_key="scope-a",
        )

        self.assertEqual(selected, ["q1", "q2", "q3"])
        self.assertEqual(rotation["selected_count"], 3)
        self.assertEqual(rotation["total_count"], 5)
        self.assertEqual(rotation["cursor_before"], 0)
        self.assertEqual(rotation["cursor_after"], 3)
        self.assertIsNone(rotation["state_path"])

    def test_select_rotating_plan_window_with_state_file_rotates_and_wraps(self) -> None:
        plans = ["q1", "q2", "q3", "q4", "q5"]
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "batch_cursor_state.json"

            selected_first, first_rotation = _select_rotating_plan_window(
                plans=plans,
                max_plans_per_run=2,
                cursor_state_path=state_path,
                scope_key="scope-a",
            )
            selected_second, second_rotation = _select_rotating_plan_window(
                plans=plans,
                max_plans_per_run=2,
                cursor_state_path=state_path,
                scope_key="scope-a",
            )
            selected_third, third_rotation = _select_rotating_plan_window(
                plans=plans,
                max_plans_per_run=2,
                cursor_state_path=state_path,
                scope_key="scope-a",
            )

        self.assertEqual(selected_first, ["q1", "q2"])
        self.assertEqual(first_rotation["cursor_before"], 0)
        self.assertEqual(first_rotation["cursor_after"], 2)

        self.assertEqual(selected_second, ["q3", "q4"])
        self.assertEqual(second_rotation["cursor_before"], 2)
        self.assertEqual(second_rotation["cursor_after"], 4)

        self.assertEqual(selected_third, ["q5", "q1"])
        self.assertEqual(third_rotation["cursor_before"], 4)
        self.assertEqual(third_rotation["cursor_after"], 1)

    def test_select_rotating_plan_window_commit_mode_does_not_advance_file_until_commit(self) -> None:
        plans = ["q1", "q2", "q3", "q4"]
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "batch_cursor_state.json"

            selected, rotation = _select_rotating_plan_window(
                plans=plans,
                max_plans_per_run=2,
                cursor_state_path=state_path,
                scope_key="scope-a",
                checkpoint_mode="commit",
            )
            initial_state = _load_batch_cursor_state(state_path)
            _commit_rotating_plan_window(
                cursor_state_path=state_path,
                scope_key="scope-a",
                cursor_after=rotation["cursor_after"],
            )
            committed_state = _load_batch_cursor_state(state_path)

        self.assertEqual(selected, ["q1", "q2"])
        self.assertEqual(initial_state["cursors"], {})
        self.assertEqual(committed_state["cursors"]["scope-a"], 2)

    def test_select_rotating_plan_window_uses_independent_scopes(self) -> None:
        plans = ["q1", "q2", "q3", "q4", "q5"]
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "batch_cursor_state.json"
            config_path = Path(tmp_dir) / "monitor_tasks.json"

            scope_a = _build_batch_cursor_scope_key(
                config_path=config_path,
                profile_key="chrome-attached",
                only_task="task-a",
            )
            scope_b = _build_batch_cursor_scope_key(
                config_path=config_path,
                profile_key="chrome-attached",
                only_task="task-b",
            )

            _select_rotating_plan_window(
                plans=plans,
                max_plans_per_run=2,
                cursor_state_path=state_path,
                scope_key=scope_a,
            )
            selected_scope_b, rotation_scope_b = _select_rotating_plan_window(
                plans=plans,
                max_plans_per_run=2,
                cursor_state_path=state_path,
                scope_key=scope_b,
            )

        self.assertEqual(selected_scope_b, ["q1", "q2"])
        self.assertEqual(rotation_scope_b["cursor_before"], 0)
        self.assertEqual(rotation_scope_b["cursor_after"], 2)

    def test_compute_risk_backoff_seconds_doubles_and_caps(self) -> None:
        self.assertEqual(
            _compute_risk_backoff_seconds(consecutive_risk_hits=1, base_seconds=600, max_seconds=3600),
            600,
        )
        self.assertEqual(
            _compute_risk_backoff_seconds(consecutive_risk_hits=2, base_seconds=600, max_seconds=3600),
            1200,
        )
        self.assertEqual(
            _compute_risk_backoff_seconds(consecutive_risk_hits=3, base_seconds=600, max_seconds=3600),
            2400,
        )
        self.assertEqual(
            _compute_risk_backoff_seconds(consecutive_risk_hits=4, base_seconds=600, max_seconds=3600),
            3600,
        )

    def test_normalize_checkpoint_mode_accepts_eager_and_commit(self) -> None:
        self.assertEqual(_normalize_checkpoint_mode("eager"), "eager")
        self.assertEqual(_normalize_checkpoint_mode("COMMIT"), "commit")

    def test_filter_plans_by_risk_backoff_skips_active_cooldown_entries(self) -> None:
        now = datetime(2026, 4, 12, 8, 0, tzinfo=UTC)
        scope_key = "scope-a"
        plan_a = SimpleNamespace(task=SimpleNamespace(task_key="task-a"), task_query_id=1, query="q1")
        plan_b = SimpleNamespace(task=SimpleNamespace(task_key="task-a"), task_query_id=2, query="q2")
        plan_c = SimpleNamespace(task=SimpleNamespace(task_key="task-b"), task_query_id=3, query="q3")
        state = {"queries": {}}
        state["queries"][_build_plan_risk_key(scope_key=scope_key, plan=plan_a)] = {
            "consecutive_risk_hits": 2,
            "next_retry_at": (now + timedelta(minutes=15)).isoformat(),
        }
        state["queries"][_build_plan_risk_key(scope_key=scope_key, plan=plan_b)] = {
            "consecutive_risk_hits": 1,
            "next_retry_at": (now - timedelta(minutes=1)).isoformat(),
        }

        selected, skipped = _filter_plans_by_risk_backoff(
            plans=[plan_a, plan_b, plan_c],
            scope_key=scope_key,
            risk_state=state,
            now=now,
        )

        self.assertEqual([plan.query for plan in selected], ["q2", "q3"])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["query"], "q1")
        self.assertGreater(skipped[0]["wait_seconds"], 0)

    def test_apply_plan_outcomes_to_risk_backoff_state_records_events_and_recovery(self) -> None:
        now = datetime(2026, 4, 12, 8, 0, tzinfo=UTC)
        scope_key = "scope-a"
        plan = SimpleNamespace(task=SimpleNamespace(task_key="task-a"), task_query_id=9, query="fenix 8")
        state = {"queries": {}}

        with tempfile.TemporaryDirectory() as tmp_dir:
            event_path = Path(tmp_dir) / "risk_events.jsonl"
            state_path = Path(tmp_dir) / "risk_state.json"

            first_stats = _apply_plan_outcomes_to_risk_backoff_state(
                outcomes=[
                    {
                        "plan": plan,
                        "status": "manual_verification_required",
                        "auth_state": "risk_control",
                        "error_message": "Risk control blocked",
                    }
                ],
                scope_key=scope_key,
                risk_state=state,
                now=now,
                risk_backoff_base_seconds=600,
                risk_backoff_max_seconds=21600,
                risk_event_log_path=event_path,
                profile_key="chrome-attached",
                config_path=Path("/tmp/monitor_tasks.json"),
            )

            self.assertEqual(first_stats["risk_event_count"], 1)
            key = _build_plan_risk_key(scope_key=scope_key, plan=plan)
            entry = state["queries"][key]
            self.assertEqual(entry["consecutive_risk_hits"], 1)
            first_retry_at = datetime.fromisoformat(entry["next_retry_at"])
            self.assertEqual(int((first_retry_at - now).total_seconds()), 600)
            self.assertEqual(len(event_path.read_text(encoding="utf-8").strip().splitlines()), 1)

            second_stats = _apply_plan_outcomes_to_risk_backoff_state(
                outcomes=[
                    {
                        "plan": plan,
                        "status": "manual_verification_required",
                        "auth_state": "risk_control",
                        "error_message": "Risk control blocked again",
                    }
                ],
                scope_key=scope_key,
                risk_state=state,
                now=now + timedelta(minutes=10),
                risk_backoff_base_seconds=600,
                risk_backoff_max_seconds=21600,
                risk_event_log_path=event_path,
                profile_key="chrome-attached",
                config_path=Path("/tmp/monitor_tasks.json"),
            )
            self.assertEqual(second_stats["risk_event_count"], 1)
            entry = state["queries"][key]
            self.assertEqual(entry["consecutive_risk_hits"], 2)
            second_retry_at = datetime.fromisoformat(entry["next_retry_at"])
            self.assertEqual(
                int((second_retry_at - (now + timedelta(minutes=10))).total_seconds()),
                1200,
            )

            recovery_stats = _apply_plan_outcomes_to_risk_backoff_state(
                outcomes=[
                    {
                        "plan": plan,
                        "status": "completed",
                        "auth_state": "authenticated",
                        "error_message": None,
                    }
                ],
                scope_key=scope_key,
                risk_state=state,
                now=now + timedelta(minutes=40),
                risk_backoff_base_seconds=600,
                risk_backoff_max_seconds=21600,
                risk_event_log_path=event_path,
                profile_key="chrome-attached",
                config_path=Path("/tmp/monitor_tasks.json"),
            )
            self.assertEqual(recovery_stats["risk_event_count"], 0)
            self.assertEqual(recovery_stats["recovered_count"], 1)
            entry = state["queries"][key]
            self.assertEqual(entry["consecutive_risk_hits"], 0)
            self.assertIsNone(entry["next_retry_at"])

            _save_batch_risk_backoff_state(state_path, state)
            loaded = _load_batch_risk_backoff_state(state_path)
            self.assertEqual(loaded["queries"][key]["consecutive_risk_hits"], 0)
            self.assertEqual(
                _count_active_risk_backoff_entries(risk_state=loaded, now=now + timedelta(hours=2)),
                0,
            )

            summary = summarize_batch_risk_event_log(
                risk_event_log_path=event_path,
                lookback_hours=48,
                top_n=5,
                now=now + timedelta(hours=1),
            )
            self.assertEqual(summary["total_events"], 2)
            self.assertEqual(summary["top_tasks"][0]["task_key"], "task-a")
            self.assertEqual(summary["top_queries"][0]["query"], "fenix 8")

    def test_latest_risk_backoff_metadata_reports_active_cooldown(self) -> None:
        now = datetime(2026, 4, 12, 8, 0, tzinfo=UTC)
        state = {
            "queries": {
                "scope|task|1|fenix": {
                    "consecutive_risk_hits": 1,
                    "next_retry_at": (now + timedelta(minutes=10)).isoformat(),
                    "last_risk_at": now.isoformat(),
                    "last_error": "Risk control blocked",
                }
            }
        }

        metadata = _latest_risk_backoff_metadata(risk_state=state, now=now)

        self.assertEqual(metadata["cooldown_reason"], "risk_control")
        self.assertEqual(metadata["cooldown_started_at"], now.isoformat())
        self.assertEqual(metadata["next_retry_at"], (now + timedelta(minutes=10)).isoformat())
        self.assertEqual(metadata["cooldown_seconds"], 600)
        self.assertIn("Risk control blocked", metadata["recent_risk_event"])

    def test_summarize_outcomes_counts_statuses(self) -> None:
        summary = _summarize_outcomes(
            [
                {"status": "completed"},
                {"status": "failed"},
                {"status": "manual_verification_required"},
                {"status": "completed"},
            ]
        )

        self.assertEqual(summary["completed_count"], 2)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["manual_verification_required_count"], 1)
        self.assertEqual(summary["outcome_count"], 4)


if __name__ == "__main__":
    unittest.main()
