from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from goofish_insight.application.services import runtime_controls
from goofish_insight.application.services.runtime_controls import (
    RuntimeControlError,
    build_runtime_control_panel_data,
    run_runtime_action,
)


class RuntimeControlsTests(unittest.TestCase):
    def test_build_runtime_control_panel_data_reports_running_services(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._launchctl_loaded_labels",
                return_value={
                    "com.admin.goofish-browser-feed-9222",
                    "com.admin.goofish-home-feed-watch",
                    "com.admin.goofish-browser-batch-9223",
                    "com.admin.goofish-batch-collect",
                    "com.admin.goofish-analyzer-hourly",
                    "com.admin.goofish-qwen3-api-8000",
                    "com.admin.goofish-qwen25-vl-72b-8020",
                    "com.admin.goofish-review-v3-resident",
                },
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._is_local_port_open",
                side_effect=lambda port: port in {9222, 9223, 8000, 8020},
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._load_home_feed_mode",
                return_value={"dry_run": False, "max_messages": 1, "summary": "真实消息 / 每轮最多 1 条"},
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._read_last_json_line",
                side_effect=[
                    {
                        "watch_cycle": 12,
                        "visible_card_count": 6,
                        "target_match_count": 1,
                        "message_sent_count": 1,
                        "generated_at": "2026-04-05T05:50:37+00:00",
                        "updated_item_count": 2,
                        "price_changed_count": 1,
                        "snapshot_inserted_count": 1,
                    },
                    {
                        "batch_index": 111,
                        "pending_after": 1539,
                        "worker_stats": {"quarantined_low_confidence_count": 64},
                    },
                ],
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._read_last_text_line",
                return_value="[apple-m-series] persisted query page: mac mini m4 16g 256g | page=11",
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._safe_batch_collect_runtime_summary",
                return_value={
                    "job_status": "batch / running / 开始 13:45:00",
                    "checkpoint_status": "commit / pending 12 / committed 10",
                    "risk_status": "13:40:00 / 连续 2 次 / 退避 1200s",
                    "cooldown_status": "risk_after_batch / 开始 13:40:00 / 恢复 14:00:00",
                    "next_retry_status": "14:00:00 / 剩余 600s",
                    "failure_status": "batch_exit_code=19",
                    "risk_event_status": "reason=risk_after_batch; cooldown=1200s",
                },
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._safe_analyzer_runtime_summary",
                return_value={
                    "job_ok": True,
                    "job_health": "最近作业正常",
                    "job_status": "daily_metrics / completed / 结束 13:30:00",
                    "metric_status": "2026-04-13 / 4 行",
                    "latest_log": "daily_metrics complete",
                },
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._safe_quality_metrics_summary",
                return_value={
                    "collection_success_rate": "92.0%",
                    "risk_hit_rate": "6.0%",
                    "review_pass_rate": "88.0%",
                    "price_anomaly_rate": "4.0%",
                    "last_updated": runtime_controls.datetime.now(runtime_controls.UTC).isoformat(),
                },
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._load_vlm_download_status",
                return_value={"present": 8, "total": 8, "complete": True, "size": "42.3GB"},
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._fetch_vlm_health",
                return_value={"status": "healthy", "loaded_model": "Qwen2.5-VL-72B-Instruct-4bit-MLX"},
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._load_review_runtime_model_selection",
                return_value={"key": "qwen3_30b", "label": "Qwen3 30B"},
            ),
            patch(
                "goofish_insight.application.services.runtime_controls.build_overlay_vlm_runtime_status",
                return_value={
                    "enabled": True,
                    "thinking_enabled": True,
                    "queue": {
                        "pending_jobs": 2,
                        "active_job_id": "job-abcdef12",
                    },
                },
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._safe_pending_review_v3_second_pass",
                return_value=12,
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._load_review_v3_resident_state",
                return_value={
                    "phase": "second_pass",
                    "last_status": "completed",
                    "output_path": "/tmp/review-v3-resident.json",
                },
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._review_v3_resident_latest_output_path",
                return_value=Path("/tmp/review-v3-resident.json"),
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._review_v3_direct_is_running",
                return_value=True,
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._load_review_v3_direct_state",
                return_value={"phase": "second_pass", "output_path": "/tmp/review-v3.json"},
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._review_v3_direct_latest_output_path",
                return_value=Path("/tmp/review-v3.json"),
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._load_latest_template_smoke_report",
                return_value={
                    "generatedAt": runtime_controls.datetime.now(runtime_controls.UTC).isoformat(),
                    "overallStatus": "pass",
                    "checkCount": 14,
                },
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._safe_buy_jobs_runtime_summary",
                return_value={
                    "category_code": "apple_computer",
                    "scope_detail": "Apple电脑 (apple_computer)",
                    "latest_baseline_at": runtime_controls.datetime.now(runtime_controls.UTC),
                    "latest_opportunity_at": runtime_controls.datetime.now(runtime_controls.UTC),
                    "latest_alert_at": runtime_controls.datetime.now(runtime_controls.UTC),
                    "recent_baseline_count": 4,
                    "recent_opportunity_count": 7,
                    "recent_alert_count": 2,
                    "latest_baseline_detail": "2026-04-22 10:00:00",
                    "latest_opportunity_detail": "2026-04-22 09:00:00",
                    "latest_alert_detail": "2026-04-22 08:00:00",
                },
            ) as buy_summary_mock,
        ):
            payload = build_runtime_control_panel_data(category_code="apple_computer")

        self.assertEqual(len(payload["groups"]), 11)
        group_map = {group["key"]: group for group in payload["groups"]}
        self.assertEqual(group_map["market_collectors"]["status"], "running")
        self.assertEqual(group_map["home_feed"]["status"], "running")
        self.assertEqual(group_map["batch_collect"]["status"], "running")
        self.assertEqual(group_map["analyzer_runtime"]["status"], "running")
        self.assertEqual(group_map["buy_jobs"]["status"], "running")
        self.assertEqual(group_map["local_model"]["status"], "running")
        self.assertEqual(group_map["vlm_runtime"]["status"], "running")
        self.assertEqual(group_map["review_runtime"]["status"], "running")
        self.assertEqual(group_map["review_v3_direct"]["status"], "running")
        self.assertEqual(group_map["template_smoke"]["status"], "running")
        self.assertEqual(group_map["quality_metrics"]["status"], "running")
        self.assertIn("第 12 轮", group_map["home_feed"]["stats"][0]["value"])
        batch_stats = {entry["label"]: entry["value"] for entry in group_map["batch_collect"]["stats"]}
        self.assertEqual(batch_stats["作业状态"], "batch / running / 开始 13:45:00")
        self.assertEqual(batch_stats["Checkpoint"], "commit / pending 12 / committed 10")
        self.assertEqual(batch_stats["最近风控"], "13:40:00 / 连续 2 次 / 退避 1200s")
        self.assertEqual(batch_stats["冷却窗口"], "risk_after_batch / 开始 13:40:00 / 恢复 14:00:00")
        self.assertEqual(batch_stats["下一次重试"], "14:00:00 / 剩余 600s")
        self.assertEqual(batch_stats["最近失败原因"], "batch_exit_code=19")
        self.assertEqual(batch_stats["最近风险摘要"], "reason=risk_after_batch; cooldown=1200s")
        self.assertEqual(group_map["analyzer_runtime"]["stats"][0]["value"], "daily_metrics / completed / 结束 13:30:00")
        self.assertEqual(group_map["analyzer_runtime"]["stats"][1]["value"], "2026-04-13 / 4 行")
        self.assertIn("12", group_map["review_runtime"]["stats"][0]["value"])
        self.assertIn("completed", group_map["review_runtime"]["stats"][2]["value"])
        self.assertIn("12", group_map["review_v3_direct"]["stats"][0]["value"])
        self.assertEqual(group_map["local_model"]["stats"][1]["value"], "Qwen3 30B")
        self.assertEqual(group_map["vlm_runtime"]["stats"][0]["value"], "42.3GB")
        self.assertEqual(group_map["quality_metrics"]["stats"][0]["value"], "92.0%")
        self.assertTrue(
            any(action["action"] == "enable_message_mode" for action in group_map["home_feed"]["actions"])
        )
        self.assertTrue(
            any(action["action"] == "run_now" for action in group_map["analyzer_runtime"]["actions"])
        )
        self.assertTrue(
            any(action["action"] == "switch_to_qwen25_32b" for action in group_map["local_model"]["actions"])
        )
        self.assertTrue(any(action["action"] == "start" for action in group_map["vlm_runtime"]["actions"]))
        self.assertTrue(
            any(action["action"] == "start_second_pass" for action in group_map["review_v3_direct"]["actions"])
        )
        self.assertTrue(
            any(action["action"] == "run_smoke" for action in group_map["template_smoke"]["actions"])
        )
        self.assertTrue(any(action["action"] == "build-buy-baselines" for action in group_map["buy_jobs"]["actions"]))
        self.assertTrue(
            any(action["action"] == "refresh-buy-opportunities" for action in group_map["buy_jobs"]["actions"])
        )
        self.assertTrue(any(action["action"] == "emit-buy-alerts" for action in group_map["buy_jobs"]["actions"]))
        self.assertEqual(group_map["buy_jobs"]["stats"][0]["label"], "类目作用域")
        self.assertEqual(group_map["buy_jobs"]["stats"][0]["value"], "Apple电脑 (apple_computer)")
        self.assertEqual(group_map["buy_jobs"]["stats"][4]["label"], "24h基线增量")
        self.assertEqual(group_map["buy_jobs"]["stats"][4]["value"], "4 条")
        self.assertEqual(group_map["buy_jobs"]["stats"][5]["label"], "24h机会增量")
        self.assertEqual(group_map["buy_jobs"]["stats"][5]["value"], "7 条")
        self.assertEqual(group_map["buy_jobs"]["stats"][6]["label"], "24h提醒增量")
        self.assertEqual(group_map["buy_jobs"]["stats"][6]["value"], "2 条")
        buy_summary_mock.assert_called_once_with(category_code="apple_computer")

    def test_run_runtime_action_rejects_unknown_target(self) -> None:
        with self.assertRaises(RuntimeControlError):
            run_runtime_action(target="unknown", action="start")

    def test_run_runtime_action_dispatches_to_expected_handler(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._run_batch_collect_action",
                return_value=None,
            ) as action_mock,
            patch(
                "goofish_insight.application.services.runtime_controls.build_runtime_control_panel_data",
                return_value={"groups": []},
            ),
        ):
            payload = run_runtime_action(target="batch_collect", action="restart")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["target"], "batch_collect")
        self.assertEqual(payload["action"], "restart")
        action_mock.assert_called_once_with("restart")

    def test_run_runtime_action_dispatches_analyzer_handler(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._run_analyzer_runtime_action",
                return_value=None,
            ) as action_mock,
            patch(
                "goofish_insight.application.services.runtime_controls.build_runtime_control_panel_data",
                return_value={"groups": []},
            ),
        ):
            payload = run_runtime_action(target="analyzer_runtime", action="run_now")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["target"], "analyzer_runtime")
        self.assertEqual(payload["action"], "run_now")
        action_mock.assert_called_once_with("run_now")

    def test_run_runtime_action_dispatches_review_v3_direct_handler(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._run_review_v3_direct_action",
                return_value=None,
            ) as action_mock,
            patch(
                "goofish_insight.application.services.runtime_controls.build_runtime_control_panel_data",
                return_value={"groups": []},
            ),
        ):
            payload = run_runtime_action(target="review_v3_direct", action="start_second_pass")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["target"], "review_v3_direct")
        self.assertEqual(payload["action"], "start_second_pass")
        action_mock.assert_called_once_with("start_second_pass")

    def test_run_runtime_action_dispatches_review_runtime_handler(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._run_review_runtime_action",
                return_value=None,
            ) as action_mock,
            patch(
                "goofish_insight.application.services.runtime_controls.build_runtime_control_panel_data",
                return_value={"groups": []},
            ),
        ):
            payload = run_runtime_action(target="review_runtime", action="restart")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["target"], "review_runtime")
        self.assertEqual(payload["action"], "restart")
        action_mock.assert_called_once_with("restart")

    def test_run_runtime_action_dispatches_template_smoke_handler(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._run_template_smoke_action",
                return_value={"overallStatus": "pass", "checkCount": 14},
            ) as action_mock,
            patch(
                "goofish_insight.application.services.runtime_controls.build_runtime_control_panel_data",
                return_value={"groups": []},
            ),
        ):
            payload = run_runtime_action(target="template_smoke", action="run_smoke")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["target"], "template_smoke")
        self.assertEqual(payload["action"], "run_smoke")
        self.assertEqual(payload["actionResult"]["overallStatus"], "pass")
        action_mock.assert_called_once_with("run_smoke")

    def test_run_runtime_action_dispatches_buy_jobs_handler(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._run_buy_jobs_action",
                return_value={
                    "action": "build-buy-baselines",
                    "categoryCode": "apple_computer",
                    "exit_code": 0,
                    "result": {"ok": True},
                },
            ) as action_mock,
            patch(
                "goofish_insight.application.services.runtime_controls.build_runtime_control_panel_data",
                return_value={"groups": []},
            ),
        ):
            payload = run_runtime_action(
                target="buy_jobs",
                action="build-buy-baselines",
                category_code="apple_computer",
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["target"], "buy_jobs")
        self.assertEqual(payload["action"], "build-buy-baselines")
        self.assertEqual(payload["actionResult"]["result"]["ok"], True)
        action_mock.assert_called_once_with("build-buy-baselines", category_code="apple_computer")

    def test_run_home_feed_mode_action_updates_plist_and_restarts_when_loaded(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._update_plist_environment",
                return_value=None,
            ) as update_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._run_home_feed_action",
                return_value=None,
            ) as restart_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._launchctl_loaded_labels",
                return_value={"com.admin.goofish-home-feed-watch"},
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._home_feed_plist_paths",
                return_value=[Path("/tmp/source.plist"), Path("/tmp/target.plist")],
            ),
        ):
            runtime_controls._set_home_feed_mode(dry_run=False, max_messages=1)

        self.assertEqual(update_mock.call_count, 2)
        restart_mock.assert_called_once_with("restart")

    def test_switch_local_model_profile_updates_plists_and_restarts_loaded_services_only(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._review_runtime_qwen_plist_paths",
                return_value=[Path("/tmp/qwen-source.plist"), Path("/tmp/qwen-target.plist")],
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._review_runtime_worker_plist_paths",
                return_value=[Path("/tmp/worker-source.plist"), Path("/tmp/worker-target.plist")],
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._update_review_runtime_model_service",
                return_value=None,
            ) as qwen_update_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._update_plist_environment",
                return_value=None,
            ) as worker_update_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._launchctl_loaded_labels",
                return_value={"com.admin.goofish-qwen3-api-8000"},
            ),
            patch(
                "goofish_insight.application.services.runtime_controls._stop_labels",
                return_value=None,
            ) as stop_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._bootout_label",
                return_value=None,
            ) as bootout_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._launchctl_run",
                return_value=None,
            ) as launchctl_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._start_label",
                return_value=None,
            ) as start_label_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._prepare_legacy_review_v2_runtime",
                return_value=None,
            ),
            patch("goofish_insight.application.services.runtime_controls.time.sleep", return_value=None),
        ):
            runtime_controls._set_local_model_profile("qwen25_32b")

        self.assertEqual(qwen_update_mock.call_count, 2)
        self.assertEqual(worker_update_mock.call_count, 2)
        stop_mock.assert_called_once_with("com.admin.goofish-review-v2-resident", "com.admin.goofish-qwen3-api-8000")
        self.assertGreaterEqual(bootout_mock.call_count, 1)
        self.assertGreaterEqual(launchctl_mock.call_count, 2)
        start_label_mock.assert_called_once_with(
            "com.admin.goofish-qwen3-api-8000",
            runtime_controls.QWEN_PLIST,
        )

    def test_run_vlm_runtime_start_installs_and_bootstraps_launch_agent(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._sync_launch_agent_file",
                return_value=None,
            ) as ensure_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._launchctl_run",
                return_value=None,
            ) as launchctl_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._start_label",
                return_value=None,
            ) as start_mock,
        ):
            runtime_controls._run_vlm_runtime_action("start")

        ensure_mock.assert_called_once_with(runtime_controls.SOURCE_VLM_PLIST, runtime_controls.VLM_PLIST)
        self.assertEqual(
            launchctl_mock.call_args_list[0],
            unittest.mock.call(
                "bootout",
                f"{runtime_controls.LAUNCH_DOMAIN}/{runtime_controls.VLM_LABEL}",
                check=False,
            ),
        )
        self.assertIn(
            unittest.mock.call(
                "enable",
                f"{runtime_controls.LAUNCH_DOMAIN}/{runtime_controls.VLM_LABEL}",
                check=False,
            ),
            launchctl_mock.call_args_list,
        )
        start_mock.assert_called_once_with(runtime_controls.VLM_LABEL, runtime_controls.VLM_PLIST)

    def test_run_review_runtime_start_bootstraps_v3_resident(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.runtime_controls._prepare_review_v3_runtime",
                return_value=None,
            ) as prepare_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._stop_review_v3_direct_batch",
                return_value=None,
            ) as stop_direct_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._stop_labels",
                return_value=None,
            ) as stop_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._ensure_service_file",
                return_value=None,
            ) as ensure_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._launchctl_run",
                return_value=None,
            ) as launchctl_mock,
            patch(
                "goofish_insight.application.services.runtime_controls._start_label",
                return_value=None,
            ) as start_mock,
        ):
            runtime_controls._run_review_runtime_action("start")

        prepare_mock.assert_called_once_with()
        stop_direct_mock.assert_called_once_with()
        stop_mock.assert_called_once_with("com.admin.goofish-review-v2-resident")
        ensure_mock.assert_called_once_with(runtime_controls.REVIEW_V3_RESIDENT_PLIST)
        launchctl_mock.assert_called_once_with(
            "enable",
            f"{runtime_controls.LAUNCH_DOMAIN}/{runtime_controls.REVIEW_V3_RESIDENT_LABEL}",
            check=False,
        )
        start_mock.assert_called_once_with(
            runtime_controls.REVIEW_V3_RESIDENT_LABEL,
            runtime_controls.REVIEW_V3_RESIDENT_PLIST,
        )


if __name__ == "__main__":
    unittest.main()
