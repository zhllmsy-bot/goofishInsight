from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import typer
from typer.testing import CliRunner

from goofish_insight.application.services.browser_guard import (
    evaluate_browser_guard_preflight,
    record_browser_guard_observation,
)
from goofish_insight.application.services.collector_runtime import (
    normalize_resident_recovery_state,
    plan_resident_cooldown_after_risk,
    resolve_resident_cooldown_after_success,
)
from goofish_insight.entrypoints.cli.collect import register_collect_commands
from goofish_insight.entrypoints.cli.feed import register_feed_commands


def _blocked_risk_control_decision(*, feature: str = "collect_batch") -> dict[str, object]:
    return {
        "allowed": False,
        "decision": "cooldown",
        "profile_key": "chrome-attached",
        "feature": feature,
        "scope_key": None,
        "auth_state": "risk_control",
        "source": "guard_state_profile",
        "reason": "profile_cooldown_active",
        "wait_seconds": 600,
        "recommended_sleep_seconds": 600,
        "next_retry_at": "2026-04-16T12:10:00+00:00",
        "cooldown_started_at": "2026-04-16T12:00:00+00:00",
        "error_message": "RGV587_ERROR::SM::哎哟喂,被挤爆啦,请稍后重试",
    }


class BrowserGuardTests(unittest.TestCase):
    def test_resident_recovery_state_defaults_to_initial_baseline(self) -> None:
        normalized = normalize_resident_recovery_state(
            {},
            initial_seconds=600,
            max_seconds=21600,
        )

        self.assertEqual(normalized["baseline_seconds"], 600)
        self.assertIsNone(normalized["last_applied_cooldown_seconds"])
        self.assertIsNone(normalized["failed_cooldown_seconds"])
        self.assertEqual(normalized["next_cooldown_seconds"], 600)

    def test_resident_recovery_risk_reuses_baseline_then_doubles(self) -> None:
        first = plan_resident_cooldown_after_risk(
            baseline_seconds=900,
            last_applied_cooldown_seconds=None,
            max_seconds=21600,
        )
        second = plan_resident_cooldown_after_risk(
            baseline_seconds=900,
            last_applied_cooldown_seconds=first["sleep_seconds"],
            max_seconds=21600,
        )

        self.assertEqual(first["sleep_seconds"], 900)
        self.assertEqual(first["failed_cooldown_seconds"], None)
        self.assertEqual(first["next_cooldown_seconds"], 1800)
        self.assertEqual(first["strategy"], "reuse_baseline")

        self.assertEqual(second["sleep_seconds"], 1800)
        self.assertEqual(second["failed_cooldown_seconds"], 900)
        self.assertEqual(second["next_cooldown_seconds"], 3600)
        self.assertEqual(second["strategy"], "escalate_after_failed_retry")

    def test_resident_recovery_success_after_escalation_moves_baseline_to_midpoint(self) -> None:
        result = resolve_resident_cooldown_after_success(
            baseline_seconds=900,
            last_applied_cooldown_seconds=1800,
            failed_cooldown_seconds=900,
            max_seconds=21600,
        )

        self.assertEqual(result["baseline_seconds"], 1350)
        self.assertEqual(result["next_cooldown_seconds"], 1350)
        self.assertTrue(result["adjusted"])
        self.assertEqual(result["strategy"], "midpoint_after_escalation")

    def test_resident_recovery_success_without_new_risk_keeps_baseline(self) -> None:
        result = resolve_resident_cooldown_after_success(
            baseline_seconds=1200,
            last_applied_cooldown_seconds=None,
            failed_cooldown_seconds=None,
            max_seconds=21600,
        )

        self.assertEqual(result["baseline_seconds"], 1200)
        self.assertEqual(result["next_cooldown_seconds"], 1200)
        self.assertFalse(result["adjusted"])
        self.assertEqual(result["strategy"], "keep_existing_baseline")

    def test_record_risk_control_sets_profile_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "browser_guard_state.json"
            event_log_path = Path(tmp_dir) / "browser_guard_events.jsonl"
            now = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)

            decision = record_browser_guard_observation(
                profile_key="chrome-attached",
                feature="collect_batch",
                auth_state="risk_control",
                error_message="RGV587_ERROR::SM::哎哟喂,被挤爆啦,请稍后重试",
                state_path=state_path,
                event_log_path=event_log_path,
                now=now,
                base_seconds=600,
                max_seconds=21600,
            )

            self.assertFalse(decision["allowed"])
            self.assertEqual(decision["decision"], "cooldown")
            self.assertEqual(decision["wait_seconds"], 600)

            preflight = evaluate_browser_guard_preflight(
                profile_key="chrome-attached",
                feature="collect_batch",
                state_path=state_path,
                now=now + timedelta(minutes=5),
            )

            self.assertFalse(preflight["allowed"])
            self.assertEqual(preflight["decision"], "cooldown")
            self.assertEqual(preflight["auth_state"], "risk_control")
            self.assertTrue(event_log_path.exists())
            self.assertEqual(len(event_log_path.read_text(encoding="utf-8").strip().splitlines()), 1)

    def test_record_authenticated_clears_browser_guard_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "browser_guard_state.json"
            event_log_path = Path(tmp_dir) / "browser_guard_events.jsonl"
            now = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)

            record_browser_guard_observation(
                profile_key="chrome-attached",
                feature="collect_batch",
                auth_state="risk_control",
                error_message="RGV587_ERROR::SM::哎哟喂,被挤爆啦,请稍后重试",
                state_path=state_path,
                event_log_path=event_log_path,
                now=now,
            )
            record_browser_guard_observation(
                profile_key="chrome-attached",
                feature="collect_batch",
                auth_state="authenticated",
                state_path=state_path,
                event_log_path=event_log_path,
                now=now + timedelta(minutes=2),
            )

            preflight = evaluate_browser_guard_preflight(
                profile_key="chrome-attached",
                feature="collect_batch",
                state_path=state_path,
                now=now + timedelta(minutes=2),
            )

            self.assertTrue(preflight["allowed"])
            self.assertEqual(preflight["decision"], "run")

    def test_browser_session_login_required_blocks_preflight(self) -> None:
        now = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)

        preflight = evaluate_browser_guard_preflight(
            profile_key="chrome-attached",
            feature="home_feed",
            browser_session={
                "auth_state": "login_required",
                "last_login_required_at": now.isoformat(),
                "last_authenticated_at": (now - timedelta(minutes=10)).isoformat(),
                "last_error": "需要登录",
                "updated_at": now.isoformat(),
            },
            now=now,
        )

        self.assertFalse(preflight["allowed"])
        self.assertEqual(preflight["decision"], "manual_intervention_required")
        self.assertEqual(preflight["auth_state"], "login_required")


class BrowserGuardCommandTests(unittest.TestCase):
    def _build_collect_app(self) -> typer.Typer:
        app = typer.Typer()
        register_collect_commands(
            app,
            build_crawl_task_runtime_config=lambda **_kwargs: {},
            search_plan_entry_cls=lambda **kwargs: kwargs,
            default_config_path=lambda: Path("apps/collector/configs/monitor_tasks.json"),
            ensure_task=lambda *_args, **_kwargs: None,
            export_task_config_bundle=lambda **_kwargs: {"tasks": []},
            get_settings=lambda: type("Settings", (), {"default_task_key": "task-a", "browser_profile_dir": Path("/tmp")})(),
            get_task_or_raise=lambda *_args, **_kwargs: type("Task", (), {"id": 1, "task_key": "task-a"})(),
            group_batch_plans_by_platform=lambda plans: {"xianyu": plans},
            load_profile_settings=lambda *_args, **_kwargs: {},
            load_task_config=lambda *_args, **_kwargs: {"profiles": {}, "tasks": []},
            run_live_search_batch=lambda **_kwargs: [],
            run_live_search_capture=lambda **_kwargs: {},
            write_model_discovery_report=lambda **_kwargs: Path("/tmp/report.json"),
        )
        return app

    def test_preflight_browser_job_shell_output_is_script_friendly(self) -> None:
        app = self._build_collect_app()
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.collect.evaluate_browser_guard_preflight",
            return_value=_blocked_risk_control_decision(),
        ):
            result = runner.invoke(
                app,
                [
                    "preflight-browser-job",
                    "--profile-key",
                    "chrome-attached",
                    "--feature",
                    "collect_batch",
                    "--output-format",
                    "shell",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("GUARD_ALLOWED=0", result.stdout)
        self.assertIn("GUARD_DECISION=cooldown", result.stdout)

    def test_preflight_browser_job_json_includes_message(self) -> None:
        app = self._build_collect_app()
        runner = CliRunner()

        result = runner.invoke(
            app,
            [
                "preflight-browser-job",
                "--profile-key",
                "__codex_test__",
                "--feature",
                "collect_batch",
            ],
        )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"], "run")
        self.assertIn("Browser guard ready", payload["message"])

    def test_preflight_browser_job_can_require_browser_cdp_ready(self) -> None:
        app = self._build_collect_app()
        runner = CliRunner()

        with (
            patch(
                "goofish_insight.entrypoints.cli.collect.evaluate_browser_guard_preflight",
                return_value={
                    "allowed": True,
                    "decision": "run",
                    "profile_key": "chrome-attached",
                    "feature": "collect_batch",
                    "scope_key": None,
                    "auth_state": "authenticated",
                    "source": "browser_guard",
                    "reason": "ready",
                    "wait_seconds": 0,
                    "recommended_sleep_seconds": 0,
                    "next_retry_at": None,
                    "cooldown_started_at": None,
                    "error_message": None,
                },
            ),
            patch(
                "goofish_insight.entrypoints.cli.collect._is_browser_cdp_ready",
                return_value=False,
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "preflight-browser-job",
                    "--profile-key",
                    "chrome-attached",
                    "--feature",
                    "collect_batch",
                    "--cdp-url",
                    "http://127.0.0.1:9223",
                    "--require-browser-ready",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"], "browser_unavailable")
        self.assertEqual(payload["cdp_url"], "http://127.0.0.1:9223")
        self.assertIn("attached browser unavailable", payload["message"])

    def test_report_browser_guard_patterns_command_outputs_service_payload(self) -> None:
        app = self._build_collect_app()
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.collect.build_browser_guard_pattern_report",
            return_value={"generated_at": "2026-04-17T10:00:00+00:00", "attempt_summary": {"total_attempts": 8}},
        ):
            result = runner.invoke(app, ["report-browser-guard-patterns", "--lookback-hours", "24"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["attempt_summary"]["total_attempts"], 8)

    def test_set_collector_runtime_state_persists_next_cooldown_seconds(self) -> None:
        app = self._build_collect_app()
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.collect.upsert_collector_job_run_state",
            return_value="job-run-1",
        ) as upsert_mock:
            result = runner.invoke(
                app,
                [
                    "set-collector-runtime-state",
                    "--job-name",
                    "batch_collect",
                    "--phase",
                    "cooldown",
                    "--status",
                    "degraded",
                    "--cooldown-seconds",
                    "600",
                    "--next-cooldown-seconds",
                    "1200",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        metadata = upsert_mock.call_args.kwargs["metadata"]
        self.assertEqual(metadata["cooldown_seconds"], 600)
        self.assertEqual(metadata["next_cooldown_seconds"], 1200)

    def test_get_collector_runtime_state_outputs_latest_payload(self) -> None:
        app = self._build_collect_app()
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.collect.get_latest_collector_job_run_state",
            return_value={
                "job_run_id": "job-run-1",
                "job_name": "batch_collect",
                "phase": "cooldown",
                "status": "degraded",
                "metadata": {"next_cooldown_seconds": 2400},
            },
        ):
            result = runner.invoke(app, ["get-collector-runtime-state", "--job-name", "batch_collect"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["metadata"]["next_cooldown_seconds"], 2400)

    def test_refresh_home_feed_uses_browser_guard_preflight(self) -> None:
        app = typer.Typer()
        run_home_feed_refresh = Mock(return_value={"status": "should_not_run"})
        register_feed_commands(
            app,
            load_profile_settings=lambda *_args, **_kwargs: {"cdp_url": "http://127.0.0.1:9222"},
            resolve_cdp_url=lambda value: value,
            run_home_feed_refresh=run_home_feed_refresh,
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.feed.evaluate_browser_guard_preflight",
            return_value=_blocked_risk_control_decision(feature="home_feed"),
        ):
            result = runner.invoke(
                app,
                [
                    "refresh-home-feed",
                    "--profile-key",
                    "chrome-attached",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "blocked_by_browser_guard")
        self.assertEqual(payload["browser_guard"]["decision"], "cooldown")
        run_home_feed_refresh.assert_not_called()

    def test_watch_home_feed_uses_browser_guard_preflight_each_cycle(self) -> None:
        app = typer.Typer()
        run_home_feed_refresh = Mock(return_value={"status": "should_not_run"})
        register_feed_commands(
            app,
            load_profile_settings=lambda *_args, **_kwargs: {"cdp_url": "http://127.0.0.1:9222"},
            resolve_cdp_url=lambda value: value,
            run_home_feed_refresh=run_home_feed_refresh,
        )
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.feed.evaluate_browser_guard_preflight",
            return_value=_blocked_risk_control_decision(feature="home_feed"),
        ):
            result = runner.invoke(
                app,
                [
                    "watch-home-feed",
                    "--profile-key",
                    "chrome-attached",
                    "--max-cycles",
                    "1",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn('"status": "blocked_by_browser_guard"', result.stdout)
        self.assertIn('"decision": "cooldown"', result.stdout)
        run_home_feed_refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
