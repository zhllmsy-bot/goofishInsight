from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import socket
import signal
import subprocess
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy import func, select

from ...category_compat import display_label_for_scope, resolve_category_code
from ...compat import UTC
from ...db import session_scope
from ...models import (
    AnalysisReport,
    BatchCollectRiskEvent,
    CollectorJobCheckpoint,
    CollectorJobRun,
    DailyMetric,
    DataQualityMetric,
    ItemReviewV3,
    BuyAlertEvent,
    BuyOpportunity,
    BuyPriceBaseline,
    Category,
    ModelScore,
    NotificationDelivery,
)
from ...settings import get_settings
from .mobile_overlay_vlm import build_overlay_vlm_runtime_status
from .quality_metrics import QualityMetricsService
from .review_queries import count_pending_reviews

SETTINGS = get_settings()
ROOT_DIR = SETTINGS.base_dir
HOME_DIR = Path.home()
LAUNCH_DOMAIN = f"gui/{os.getuid()}"
LAUNCH_AGENTS_DIR = HOME_DIR / "Library" / "LaunchAgents"
LIBRARY_LOGS_DIR = HOME_DIR / "Library" / "Logs"
RUNTIME_HOME = HOME_DIR / "Library" / "Application Support" / "goofish-insight-launchd"
REPORTS_DIR = ROOT_DIR / "reports"
LATEST_TEMPLATE_SMOKE_REPORT_PATH = REPORTS_DIR / "latest-template-mode-smoke.json"
SOURCE_LAUNCHD_DIR = ROOT_DIR / "infra" / "launchd"
LOCAL_QWEN_PYTHON_BIN = os.environ.get("LOCAL_QWEN_PYTHON_BIN", "python")
LOCAL_QWEN_WORKDIR = os.environ.get("LOCAL_QWEN_WORKDIR", str(ROOT_DIR))
QWEN3_MODEL_PATH = os.environ.get("QWEN3_MODEL_PATH", "Qwen3-30B-A3B-MLX-4bit")
QWEN25_MODEL_PATH = os.environ.get("QWEN25_MODEL_PATH", "Qwen2.5-32B-Instruct-4bit-MLX")

BROWSER_FEED_LABEL = "com.admin.goofish-browser-feed-9222"
HOME_FEED_LABEL = "com.admin.goofish-home-feed-watch"
BROWSER_BATCH_LABEL = "com.admin.goofish-browser-batch-9223"
BATCH_LABEL = "com.admin.goofish-batch-collect"
QWEN_LABEL = "com.admin.goofish-qwen3-api-8000"
VLM_LABEL = "com.admin.goofish-qwen25-vl-72b-8020"
LEGACY_REVIEW_V2_LABEL = "com.admin.goofish-review-v2-resident"
REVIEW_V3_RESIDENT_LABEL = "com.admin.goofish-review-v3-resident"
ANALYZER_LABEL = "com.admin.goofish-analyzer-hourly"
CONFLICT_QWEN_LABEL = "com.admin.ecommerce-qwen-api-8000"
REVIEW_V3_DIRECT_SCRIPT = ROOT_DIR / "scripts" / "control-review-v3-direct.sh"
REVIEW_V3_DIRECT_LOG = LIBRARY_LOGS_DIR / "goofish-review-v3-direct.log"
REVIEW_V3_DIRECT_ERR_LOG = LIBRARY_LOGS_DIR / "goofish-review-v3-direct.err.log"
REVIEW_V3_DIRECT_PID = RUNTIME_HOME / "review-v3-direct.pid"
REVIEW_V3_DIRECT_STATE = RUNTIME_HOME / "review-v3-direct-state.json"
REVIEW_V3_RESIDENT_STATE = RUNTIME_HOME / "review-v3-resident-state.json"

SOURCE_BROWSER_FEED_PLIST = SOURCE_LAUNCHD_DIR / f"{BROWSER_FEED_LABEL}.plist"
SOURCE_HOME_FEED_PLIST = SOURCE_LAUNCHD_DIR / f"{HOME_FEED_LABEL}.plist"
SOURCE_BROWSER_BATCH_PLIST = SOURCE_LAUNCHD_DIR / f"{BROWSER_BATCH_LABEL}.plist"
SOURCE_BATCH_PLIST = SOURCE_LAUNCHD_DIR / f"{BATCH_LABEL}.plist"
SOURCE_QWEN_PLIST = SOURCE_LAUNCHD_DIR / f"{QWEN_LABEL}.plist"
SOURCE_LEGACY_REVIEW_V2_PLIST = SOURCE_LAUNCHD_DIR / f"{LEGACY_REVIEW_V2_LABEL}.plist"
SOURCE_VLM_PLIST = SOURCE_LAUNCHD_DIR / f"{VLM_LABEL}.plist"
SOURCE_REVIEW_V3_RESIDENT_PLIST = SOURCE_LAUNCHD_DIR / f"{REVIEW_V3_RESIDENT_LABEL}.plist"
SOURCE_ANALYZER_PLIST = SOURCE_LAUNCHD_DIR / f"{ANALYZER_LABEL}.plist"
HOME_FEED_PLIST = LAUNCH_AGENTS_DIR / f"{HOME_FEED_LABEL}.plist"
BROWSER_FEED_PLIST = LAUNCH_AGENTS_DIR / f"{BROWSER_FEED_LABEL}.plist"
BROWSER_BATCH_PLIST = LAUNCH_AGENTS_DIR / f"{BROWSER_BATCH_LABEL}.plist"
BATCH_PLIST = LAUNCH_AGENTS_DIR / f"{BATCH_LABEL}.plist"
QWEN_PLIST = LAUNCH_AGENTS_DIR / f"{QWEN_LABEL}.plist"
VLM_PLIST = LAUNCH_AGENTS_DIR / f"{VLM_LABEL}.plist"
LEGACY_REVIEW_V2_PLIST = LAUNCH_AGENTS_DIR / f"{LEGACY_REVIEW_V2_LABEL}.plist"
REVIEW_V3_RESIDENT_PLIST = LAUNCH_AGENTS_DIR / f"{REVIEW_V3_RESIDENT_LABEL}.plist"
ANALYZER_PLIST = LAUNCH_AGENTS_DIR / f"{ANALYZER_LABEL}.plist"

SOURCE_BROWSER_RUNTIME_SCRIPT = ROOT_DIR / "scripts" / "ensure-attached-browser-resident.sh"
SOURCE_HOME_FEED_RUNTIME_SCRIPT = ROOT_DIR / "scripts" / "start-home-feed-resident.sh"
SOURCE_BATCH_RUNTIME_SCRIPT = ROOT_DIR / "scripts" / "start-batch-collect-resident.sh"
SOURCE_LEGACY_REVIEW_V2_RUNTIME_SCRIPT = ROOT_DIR / "scripts" / "start-review-v2-resident.sh"
SOURCE_REVIEW_V3_RESIDENT_RUNTIME_SCRIPT = ROOT_DIR / "scripts" / "start-review-v3-resident.sh"
SOURCE_ANALYZER_RUNTIME_SCRIPT = ROOT_DIR / "scripts" / "start-analyzer-resident.sh"

BROWSER_RUNTIME_SCRIPT = RUNTIME_HOME / "ensure-attached-browser-resident.sh"
HOME_FEED_RUNTIME_SCRIPT = RUNTIME_HOME / "start-home-feed-resident.sh"
BATCH_RUNTIME_SCRIPT = RUNTIME_HOME / "start-batch-collect-resident.sh"
LEGACY_REVIEW_V2_RUNTIME_SCRIPT = RUNTIME_HOME / "start-review-v2-resident.sh"
REVIEW_V3_RESIDENT_RUNTIME_SCRIPT = RUNTIME_HOME / "start-review-v3-resident.sh"
ANALYZER_RUNTIME_SCRIPT = RUNTIME_HOME / "start-analyzer-resident.sh"

HOME_FEED_LOG = LIBRARY_LOGS_DIR / "goofish-home-feed-watch.log"
BATCH_LOG = LIBRARY_LOGS_DIR / "goofish-batch-collect.log"
ANALYZER_LOG = LIBRARY_LOGS_DIR / "goofish-analyzer-hourly.log"
VLM_PORT = 8020
VLM_MODEL_PATH = os.environ.get("MOBILE_OVERLAY_VLM_MODEL", "Qwen2.5-VL-72B-Instruct-4bit-MLX")
VLM_DEFAULT_SHARD_TOTAL = 8

MANAGED_LABELS = (
    BROWSER_FEED_LABEL,
    HOME_FEED_LABEL,
    BROWSER_BATCH_LABEL,
    BATCH_LABEL,
    QWEN_LABEL,
    VLM_LABEL,
    LEGACY_REVIEW_V2_LABEL,
    REVIEW_V3_RESIDENT_LABEL,
    ANALYZER_LABEL,
)

MANAGED_LABEL_TO_PLIST: dict[str, Path] = {
    BROWSER_FEED_LABEL: BROWSER_FEED_PLIST,
    HOME_FEED_LABEL: HOME_FEED_PLIST,
    BROWSER_BATCH_LABEL: BROWSER_BATCH_PLIST,
    BATCH_LABEL: BATCH_PLIST,
    QWEN_LABEL: QWEN_PLIST,
    VLM_LABEL: VLM_PLIST,
    LEGACY_REVIEW_V2_LABEL: LEGACY_REVIEW_V2_PLIST,
    REVIEW_V3_RESIDENT_LABEL: REVIEW_V3_RESIDENT_PLIST,
    ANALYZER_LABEL: ANALYZER_PLIST,
}

REVIEW_RUNTIME_MODELS: dict[str, dict[str, Any]] = {
    "qwen3_30b": {
        "label": "Qwen3 30B",
        "worker_ai_model": QWEN3_MODEL_PATH,
        "expected_model_snippet": "Qwen3-30B-A3B-MLX-4bit",
        "program_arguments": [
            LOCAL_QWEN_PYTHON_BIN,
            "-m",
            "mlx_lm",
            "server",
            "--model",
            QWEN3_MODEL_PATH,
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--use-default-chat-template",
            "--temp",
            "0.0",
            "--max-tokens",
            "1024",
            "--chat-template-args",
            '{"enable_thinking":false}',
        ],
        "working_directory": LOCAL_QWEN_WORKDIR,
    },
    "qwen25_32b": {
        "label": "Qwen2.5 32B",
        "worker_ai_model": QWEN25_MODEL_PATH,
        "expected_model_snippet": "Qwen2.5-32B-Instruct-4bit-MLX",
        "program_arguments": [
            "/bin/zsh",
            str(ROOT_DIR / "scripts/start-local-qwen2.5-32b.sh"),
        ],
        "working_directory": str(ROOT_DIR),
    },
}

REVIEW_RUNTIME_ACTION_TO_MODEL_KEY = {
    "switch_to_qwen3_30b": "qwen3_30b",
    "switch_to_qwen25_32b": "qwen25_32b",
}


class RuntimeControlError(RuntimeError):
    """Raised when a runtime control action cannot be completed."""


def build_runtime_control_panel_data(*, category_code: str | None = None) -> dict[str, Any]:
    normalized_category_code = _normalize_runtime_category_code(category_code)
    loaded_labels = _launchctl_loaded_labels()
    home_feed_group = _build_home_feed_group(loaded_labels)
    batch_collect_group = _build_batch_collect_group(loaded_labels)
    analyzer_group = _build_analyzer_runtime_group(loaded_labels)
    buy_jobs_group = _build_buy_jobs_group(category_code=normalized_category_code)
    local_model_group = _build_local_model_group(loaded_labels)
    vlm_runtime_group = _build_vlm_runtime_group(loaded_labels)
    review_runtime_group = _build_review_runtime_group(loaded_labels)
    review_v3_direct_group = _build_review_v3_direct_group()
    template_smoke_group = _build_template_smoke_group()
    quality_metrics_group = _build_quality_metrics_group()
    return {
        "updatedAt": datetime.now(UTC).isoformat(),
        "groups": [
            _build_market_collectors_group(home_feed_group, batch_collect_group),
            home_feed_group,
            batch_collect_group,
            analyzer_group,
            buy_jobs_group,
            local_model_group,
            vlm_runtime_group,
            review_runtime_group,
            review_v3_direct_group,
            template_smoke_group,
            quality_metrics_group,
        ],
    }


def run_runtime_action(*, target: str, action: str, category_code: str | None = None) -> dict[str, Any]:
    normalized_category_code = _normalize_runtime_category_code(category_code)
    handlers = {
        "market_collectors": _run_market_collectors_action,
        "home_feed": _run_home_feed_action,
        "batch_collect": _run_batch_collect_action,
        "analyzer_runtime": _run_analyzer_runtime_action,
        "local_model": _run_local_model_action,
        "vlm_runtime": _run_vlm_runtime_action,
        "review_runtime": _run_review_runtime_action,
        "review_v3_direct": _run_review_v3_direct_action,
        "buy_jobs": _run_buy_jobs_action,
        "template_smoke": _run_template_smoke_action,
    }
    handler = handlers.get(target)
    if handler is None:
        raise RuntimeControlError(f"Unsupported runtime target: {target}")
    if target == "buy_jobs":
        action_result = _run_buy_jobs_action(action, category_code=normalized_category_code)
    else:
        action_result = handler(action)
    return {
        "ok": True,
        "target": target,
        "action": action,
        "actionResult": action_result,
        "runtime": build_runtime_control_panel_data(category_code=normalized_category_code),
    }


def _build_market_collectors_group(
    home_feed_group: dict[str, Any],
    batch_collect_group: dict[str, Any],
) -> dict[str, Any]:
    checks = [
        {
            "label": "首页 Feed",
            "ok": home_feed_group["status"] == "running",
            "detail": _group_status_detail(home_feed_group["status"]),
        },
        {
            "label": "Batch Collect",
            "ok": batch_collect_group["status"] == "running",
            "detail": _group_status_detail(batch_collect_group["status"]),
        },
    ]
    stats = [
        {
            "label": "Feed 模式",
            "value": home_feed_group["checks"][2]["detail"],
        },
        {
            "label": "Batch 进度",
            "value": batch_collect_group["stats"][0]["value"],
        },
    ]
    return _build_runtime_group(
        key="market_collectors",
        title="采集总控",
        description="一次性控制首页 Feed 和 Batch Collect 两条采集链路，适合日常运维快速拉起或整体停掉 collectors。",
        checks=checks,
        stats=stats,
        actions=_default_runtime_actions(),
    )


def _build_home_feed_group(loaded_labels: set[str]) -> dict[str, Any]:
    browser_loaded = BROWSER_FEED_LABEL in loaded_labels
    worker_loaded = HOME_FEED_LABEL in loaded_labels
    browser_port_ok = _is_local_port_open(9222)
    feed_mode = _load_home_feed_mode()
    feed_summary = _read_last_json_line(HOME_FEED_LOG) or {}
    checks = [
        {
            "label": "9222 浏览器驻留",
            "ok": browser_loaded and browser_port_ok,
            "detail": "CDP 在线" if browser_port_ok else "CDP 未监听",
        },
        {
            "label": "Feed Watch",
            "ok": worker_loaded,
            "detail": "launchd 已加载" if worker_loaded else "launchd 未加载",
        },
        {
            "label": "消息模式",
            "ok": not feed_mode["dry_run"],
            "detail": feed_mode["summary"],
        },
    ]
    stats = [
        {
            "label": "最近循环",
            "value": _format_feed_cycle(feed_summary),
        },
        {
            "label": "最近日志",
            "value": _format_feed_log(feed_summary),
        },
    ]
    return _build_runtime_group(
        key="home_feed",
        title="首页 Feed",
        description="控制 9222 附着浏览器和首页 watch 常驻任务，不会把当前 dashboard 一起打掉。",
        checks=checks,
        stats=stats,
        actions=[
            *_default_runtime_actions(),
            {
                "action": "enable_message_mode",
                "label": "切到消息模式",
                "tone": "secondary",
            },
            {
                "action": "enable_dry_run",
                "label": "切到 Dry Run",
                "tone": "secondary",
            },
        ],
    )


def _build_batch_collect_group(loaded_labels: set[str]) -> dict[str, Any]:
    browser_loaded = BROWSER_BATCH_LABEL in loaded_labels
    worker_loaded = BATCH_LABEL in loaded_labels
    browser_port_ok = _is_local_port_open(9223)
    latest_batch_line = _read_last_text_line(BATCH_LOG)
    runtime_summary = _safe_batch_collect_runtime_summary()
    checks = [
        {
            "label": "9223 浏览器驻留",
            "ok": browser_loaded and browser_port_ok,
            "detail": "CDP 在线" if browser_port_ok else "CDP 未监听",
        },
        {
            "label": "Batch Collect",
            "ok": worker_loaded,
            "detail": "launchd 已加载" if worker_loaded else "launchd 未加载",
        },
    ]
    stats = [
        {
            "label": "作业状态",
            "value": runtime_summary["job_status"],
        },
        {
            "label": "Checkpoint",
            "value": runtime_summary["checkpoint_status"],
        },
        {
            "label": "最近风控",
            "value": runtime_summary["risk_status"],
        },
        {
            "label": "冷却窗口",
            "value": runtime_summary["cooldown_status"],
        },
        {
            "label": "下一次重试",
            "value": runtime_summary["next_retry_status"],
        },
        {
            "label": "最近失败原因",
            "value": runtime_summary["failure_status"],
        },
        {
            "label": "最近风险摘要",
            "value": runtime_summary["risk_event_status"],
        },
        {
            "label": "最近日志",
            "value": latest_batch_line or "暂无 batch 日志",
        },
    ]
    return _build_runtime_group(
        key="batch_collect",
        title="Batch Collect",
        description="控制批量采集浏览器与批处理 worker，用来推进 query page 持续抓取。",
        checks=checks,
        stats=stats,
        actions=_default_runtime_actions(),
    )


def _build_analyzer_runtime_group(loaded_labels: set[str]) -> dict[str, Any]:
    worker_loaded = ANALYZER_LABEL in loaded_labels
    runtime_summary = _safe_analyzer_runtime_summary()
    checks = [
        {
            "label": "Analyzer Hourly",
            "ok": worker_loaded,
            "detail": "launchd 已加载" if worker_loaded else "launchd 未加载",
        },
        {
            "label": "最近作业",
            "ok": runtime_summary["job_ok"],
            "detail": runtime_summary["job_health"],
        },
    ]
    stats = [
        {
            "label": "作业状态",
            "value": runtime_summary["job_status"],
        },
        {
            "label": "指标日期",
            "value": runtime_summary["metric_status"],
        },
        {
            "label": "模型分数",
            "value": runtime_summary.get("score_status", "暂无 model_scores"),
        },
        {
            "label": "分析报告",
            "value": runtime_summary.get("report_status", "暂无 analysis_reports"),
        },
        {
            "label": "最近日志",
            "value": runtime_summary["latest_log"],
        },
    ]
    return _build_runtime_group(
        key="analyzer_runtime",
        title="Analyzer Hourly",
        description="控制 daily_metrics/model_scores/analysis_reports 分析作业，并提供一次性手动触发入口。",
        checks=checks,
        stats=stats,
        actions=[
            *_default_runtime_actions(),
            {
                "action": "run_now",
                "label": "立即跑一次",
                "tone": "secondary",
            },
        ],
    )


def _build_buy_jobs_group(*, category_code: str | None = None) -> dict[str, Any]:
    summary = _safe_buy_jobs_runtime_summary(category_code=category_code)
    checks = [
        {
            "label": "基线更新记录",
            "ok": summary["latest_baseline_at"] is not None,
            "detail": summary["latest_baseline_detail"],
        },
        {
            "label": "机会更新记录",
            "ok": summary["latest_opportunity_at"] is not None,
            "detail": summary["latest_opportunity_detail"],
        },
        {
            "label": "提醒更新记录",
            "ok": summary["latest_alert_at"] is not None,
            "detail": summary["latest_alert_detail"],
        },
    ]
    stats = [
        {
            "label": "类目作用域",
            "value": summary["scope_detail"],
        },
        {
            "label": "最近基线",
            "value": summary["latest_baseline_detail"],
        },
        {
            "label": "最近机会",
            "value": summary["latest_opportunity_detail"],
        },
        {
            "label": "最近提醒",
            "value": summary["latest_alert_detail"],
        },
        {
            "label": "24h基线增量",
            "value": f"{summary['recent_baseline_count']} 条",
        },
        {
            "label": "24h机会增量",
            "value": f"{summary['recent_opportunity_count']} 条",
        },
        {
            "label": "24h提醒增量",
            "value": f"{summary['recent_alert_count']} 条",
        },
    ]
    return _build_runtime_group(
        key="buy_jobs",
        title="Buy Jobs",
        description="统一控制买方链路运行与产出观察：基线生成、机会刷新、提醒发放，支持按当前类目上下文手动触发各阶段任务。",
        checks=checks,
        stats=stats,
        actions=[
            {
                "action": "build-buy-baselines",
                "label": "生成买方基线",
                "tone": "secondary",
            },
            {
                "action": "refresh-buy-opportunities",
                "label": "刷新机会",
                "tone": "secondary",
            },
            {
                "action": "emit-buy-alerts",
                "label": "发起告警",
                "tone": "primary",
            },
        ],
    )


def _build_local_model_group(loaded_labels: set[str]) -> dict[str, Any]:
    model_loaded = QWEN_LABEL in loaded_labels
    model_port_ok = _is_local_port_open(8000)
    configured_model = _load_review_runtime_model_selection()
    model_name = _fetch_model_name()

    # VLM 72B 状态
    vlm_loaded = VLM_LABEL in loaded_labels
    vlm_port_ok = _is_local_port_open(VLM_PORT)
    download_status = _load_vlm_download_status()
    health = _fetch_vlm_health()
    queue_status = build_overlay_vlm_runtime_status()
    loaded_model = health.get("loaded_model") if health else None

    checks = [
        {
            "label": "本机模型服务",
            "ok": model_loaded and model_port_ok,
            "detail": "8000 在线" if model_port_ok else "8000 未监听",
        },
        {
            "label": "配置已同步",
            "ok": configured_model["key"] != "unknown",
            "detail": configured_model["label"],
        },
        {
            "label": "72B 文件完整",
            "ok": download_status["complete"],
            "detail": f'{download_status["present"]}/{download_status["total"]} 分片',
        },
        {
            "label": "VLM 服务",
            "ok": vlm_loaded and vlm_port_ok,
            "detail": f"{VLM_PORT} 在线" if vlm_port_ok else f"{VLM_PORT} 未监听",
        },
    ]
    stats = [
        {
            "label": "当前服务模型",
            "value": model_name or "未知",
        },
        {
            "label": "已配置模型",
            "value": configured_model["label"],
        },
        {
            "label": "VLM 模型",
            "value": Path(loaded_model).name if loaded_model else "未加载",
        },
        {
            "label": "截图队列",
            "value": f'pending={queue_status["queue"]["pending_jobs"]}',
        },
        {
            "label": "Thinking",
            "value": "已开启" if queue_status["thinking_enabled"] else "已关闭",
        },
    ]
    return _build_runtime_group(
        key="local_model",
        title="本机模型切换",
        description="独立控制 127.0.0.1:8000 的本机模型档位和 8020 VLM 72B 服务，不把模型切换和 Review Runtime 绑成同一个能力。",
        checks=checks,
        stats=stats,
        actions=[
            {
                "action": "switch_to_qwen3_30b",
                "label": "切到 Qwen3 30B",
                "tone": "secondary",
            },
            {
                "action": "switch_to_qwen25_32b",
                "label": "切到 Qwen2.5 32B",
                "tone": "secondary",
            },
            {
                "action": "start_vlm",
                "label": "启动 VLM",
                "tone": "secondary",
            },
            {
                "action": "stop_vlm",
                "label": "停止 VLM",
                "tone": "secondary",
            },
            {
                "action": "restart_vlm",
                "label": "重启 VLM",
                "tone": "secondary",
            },
        ],
    )


def _build_vlm_runtime_group(loaded_labels: set[str]) -> dict[str, Any]:
    vlm_loaded = VLM_LABEL in loaded_labels
    vlm_port_ok = _is_local_port_open(VLM_PORT)
    download_status = _load_vlm_download_status()
    health = _fetch_vlm_health()
    queue_status = build_overlay_vlm_runtime_status()
    loaded_model = health.get("loaded_model") if health else None
    checks = [
        {
            "label": "72B 文件完整",
            "ok": download_status["complete"],
            "detail": f'{download_status["present"]}/{download_status["total"]} 分片',
        },
        {
            "label": "VLM 服务",
            "ok": vlm_loaded and vlm_port_ok,
            "detail": f"{VLM_PORT} 在线" if vlm_port_ok else f"{VLM_PORT} 未监听",
        },
    ]
    stats = [
        {
            "label": "模型目录",
            "value": download_status["size"],
        },
        {
            "label": "已加载模型",
            "value": Path(loaded_model).name if loaded_model else "未加载",
        },
        {
            "label": "接口能力",
            "value": "/v1/responses / v1/chat/completions",
        },
        {
            "label": "截图队列",
            "value": (
                f'pending={queue_status["queue"]["pending_jobs"]}'
                + (
                    f' / active={queue_status["queue"]["active_job_id"][:8]}'
                    if queue_status["queue"]["active_job_id"]
                    else ""
                )
            ),
        },
        {
            "label": "Thinking",
            "value": "已开启" if queue_status["thinking_enabled"] else "已关闭",
        },
    ]
    return _build_runtime_group(
        key="vlm_runtime",
        title="VLM 72B Runtime",
        description="独立控制 Qwen2.5-VL-72B 的本机视觉模型服务，用于截图识别等多模态场景。",
        checks=checks,
        stats=stats,
        actions=_default_runtime_actions(),
    )


def _build_review_runtime_group(loaded_labels: set[str]) -> dict[str, Any]:
    resident_loaded = REVIEW_V3_RESIDENT_LABEL in loaded_labels
    pending_reviews = _safe_pending_review_v3_second_pass()
    current_state = _load_review_v3_resident_state()
    latest_output = _review_v3_resident_latest_output_path(current_state)
    last_status = str(current_state.get("last_status") or ("running" if resident_loaded else "idle"))
    checks = [
        {
            "label": "Resident 脚本",
            "ok": REVIEW_V3_RESIDENT_RUNTIME_SCRIPT.exists() or SOURCE_REVIEW_V3_RESIDENT_RUNTIME_SCRIPT.exists(),
            "detail": (
                "脚本已安装"
                if REVIEW_V3_RESIDENT_RUNTIME_SCRIPT.exists() or SOURCE_REVIEW_V3_RESIDENT_RUNTIME_SCRIPT.exists()
                else "脚本缺失"
            ),
        },
        {
            "label": "模型直连",
            "ok": bool(SETTINGS.ai_base_url and SETTINGS.ai_model and SETTINGS.ai_api_key),
            "detail": f"{SETTINGS.ai_provider} / {SETTINGS.ai_model}" if SETTINGS.ai_model else "未配置 AI 模型",
        },
        {
            "label": "Resident 任务",
            "ok": resident_loaded,
            "detail": "launchd 已加载" if resident_loaded else "launchd 未加载",
        },
    ]
    stats = [
        {
            "label": "待二次清洗",
            "value": str(pending_reviews) if pending_reviews is not None else "读取失败",
        },
        {
            "label": "当前阶段",
            "value": str(current_state.get("phase") or ("second_pass" if resident_loaded else "idle")),
        },
        {
            "label": "Resident 状态",
            "value": last_status,
        },
        {
            "label": "最近输出",
            "value": latest_output.name if latest_output is not None else "尚未运行",
        },
    ]
    return _build_runtime_group(
        key="review_runtime",
        title="Review V3 常驻",
        description="默认 review 主路径。常驻轮询 V3 的 second-pass 队列，直接对接模型并回写现有 items.llm_review_* 兼容字段。",
        checks=checks,
        stats=stats,
        actions=_default_runtime_actions(),
    )


def _build_review_v3_direct_group() -> dict[str, Any]:
    running = _review_v3_direct_is_running()
    pending_second_pass = _safe_pending_review_v3_second_pass()
    current_state = _load_review_v3_direct_state()
    latest_output = _review_v3_direct_latest_output_path(current_state)
    checks = [
        {
            "label": "脚本就绪",
            "ok": REVIEW_V3_DIRECT_SCRIPT.exists(),
            "detail": "脚本已安装" if REVIEW_V3_DIRECT_SCRIPT.exists() else "脚本缺失",
        },
        {
            "label": "模型直连",
            "ok": bool(SETTINGS.ai_base_url and SETTINGS.ai_model and SETTINGS.ai_api_key),
            "detail": f"{SETTINGS.ai_provider} / {SETTINGS.ai_model}" if SETTINGS.ai_model else "未配置 AI 模型",
        },
        {
            "label": "Batch 任务",
            "ok": running,
            "detail": "正在运行" if running else "当前空闲",
        },
    ]
    stats = [
        {
            "label": "待二次清洗",
            "value": str(pending_second_pass) if pending_second_pass is not None else "读取失败",
        },
        {
            "label": "当前阶段",
            "value": str(current_state.get("phase") or ("second_pass" if running else "idle")),
        },
        {
            "label": "最近输出",
            "value": latest_output.name if latest_output is not None else "尚未运行",
        },
    ]
    return _build_runtime_group(
        key="review_v3_direct",
        title="Review V3 批跑",
        description="一键手动跑一次 V3 batch。适合小批量验证、应急重试和 prompt 调试，不作为默认常驻链路。",
        checks=checks,
        stats=stats,
        actions=[
            {"action": "start_second_pass", "label": "跑二次清洗", "tone": "primary"},
            {"action": "stop", "label": "停止", "tone": "danger"},
        ],
    )


def _build_template_smoke_group() -> dict[str, Any]:
    latest_report = _load_latest_template_smoke_report()
    overall_status = str(latest_report.get("overallStatus") or "").strip().lower()
    generated_at = _parse_iso_datetime(latest_report.get("generatedAt"))
    age_minutes = None
    if generated_at is not None:
        age_minutes = max(int((datetime.now(UTC) - generated_at).total_seconds() // 60), 0)
    has_report = bool(latest_report)
    checks = [
        {
            "label": "最近 Smoke 报告",
            "ok": has_report,
            "detail": "已找到 latest-template-mode-smoke.json" if has_report else "尚未生成 smoke 报告",
        },
        {
            "label": "模板模式结果",
            "ok": overall_status == "pass",
            "detail": f"overallStatus={overall_status or 'unknown'}",
        },
        {
            "label": "报告时效",
            "ok": age_minutes is not None and age_minutes <= 180,
            "detail": f"{age_minutes} 分钟前" if age_minutes is not None else "缺少 generatedAt",
        },
    ]
    stats = [
        {
            "label": "最后结果",
            "value": overall_status or "unknown",
        },
        {
            "label": "检查项",
            "value": str(latest_report.get("checkCount") or 0),
        },
        {
            "label": "报告文件",
            "value": LATEST_TEMPLATE_SMOKE_REPORT_PATH.name if has_report else "未生成",
        },
    ]
    return _build_runtime_group(
        key="template_smoke",
        title="Template Smoke",
        description="一键执行模板模式 smoke，校验开关、价格合同、机会分流、趋势对齐，并落盘最新报告。",
        checks=checks,
        stats=stats,
        actions=[
            {"action": "run_smoke", "label": "执行 Smoke", "tone": "primary"},
        ],
    )


def _build_quality_metrics_group() -> dict[str, Any]:
    """Build quality metrics group for W8 data quality monitoring."""
    metrics = _safe_quality_metrics_summary()
    last_updated = metrics.get("last_updated")
    age_minutes = None
    if last_updated:
        try:
            updated_dt = datetime.fromisoformat(last_updated)
            age_minutes = max(int((datetime.now(UTC) - updated_dt).total_seconds() // 60), 0)
        except (ValueError, TypeError):
            pass

    success_rate_str = metrics.get("collection_success_rate", "暂无数据")
    risk_rate_str = metrics.get("risk_hit_rate", "暂无数据")
    review_rate_str = metrics.get("review_pass_rate", "暂无数据")
    price_anomaly_rate_str = metrics.get("price_anomaly_rate", "暂无数据")
    analyzer_rate_str = metrics.get("analyzer_job_success_rate", "暂无数据")
    notification_delivery_str = metrics.get("notification_delivery_status", "暂无数据")
    launchd_health = _safe_launchd_health_summary()

    # Parse percentage values for status determination
    try:
        success_rate = float(success_rate_str.rstrip("%")) if "%" in success_rate_str else None
        risk_rate = float(risk_rate_str.rstrip("%")) if "%" in risk_rate_str else None
    except (ValueError, AttributeError):
        success_rate = None
        risk_rate = None

    checks = [
        {
            "label": "采集成功率",
            "ok": success_rate is not None and success_rate >= 85,
            "detail": success_rate_str,
        },
        {
            "label": "风控命中率",
            "ok": risk_rate is not None and risk_rate <= 10,
            "detail": risk_rate_str,
        },
        {
            "label": "指标时效",
            "ok": age_minutes is not None and age_minutes <= 120,
            "detail": f"{age_minutes} 分钟前" if age_minutes is not None else "暂无数据",
        },
        {
            "label": "launchd 探针",
            "ok": bool(launchd_health["ok"]),
            "detail": launchd_health["detail"],
        },
    ]
    stats = [
        {
            "label": "采集成功率",
            "value": success_rate_str,
        },
        {
            "label": "风控命中率",
            "value": risk_rate_str,
        },
        {
            "label": "审核通过率",
            "value": review_rate_str,
        },
        {
            "label": "价格异常率",
            "value": price_anomaly_rate_str,
        },
        {
            "label": "Analyzer 成功率",
            "value": analyzer_rate_str,
        },
        {
            "label": "告警投递",
            "value": notification_delivery_str,
        },
        {
            "label": "launchd 已加载",
            "value": launchd_health["loaded_status"],
        },
    ]
    return _build_runtime_group(
        key="quality_metrics",
        title="数据质量",
        description="实时监控采集、风控、审核等关键指标，为 Phase 1 baseline 冻结提供数据支撑。",
        checks=checks,
        stats=stats,
        actions=[],
    )


def _build_runtime_group(
    *,
    key: str,
    title: str,
    description: str,
    checks: list[dict[str, Any]],
    stats: list[dict[str, str]],
    actions: list[dict[str, str]],
) -> dict[str, Any]:
    ok_count = sum(1 for check in checks if check["ok"])
    if ok_count == len(checks):
        status = "running"
    elif ok_count == 0:
        status = "stopped"
    else:
        status = "degraded"
    return {
        "key": key,
        "title": title,
        "description": description,
        "status": status,
        "checks": checks,
        "stats": stats,
        "actions": actions,
    }


def _default_runtime_actions() -> list[dict[str, str]]:
    return [
        {"action": "start", "label": "启动", "tone": "primary"},
        {"action": "restart", "label": "重启", "tone": "secondary"},
        {"action": "stop", "label": "停止", "tone": "danger"},
    ]


def _run_market_collectors_action(action: str) -> None:
    if action == "start":
        _run_batch_collect_action("start")
        _run_home_feed_action("start")
        return
    if action == "stop":
        _run_home_feed_action("stop")
        _run_batch_collect_action("stop")
        return
    if action == "restart":
        _run_home_feed_action("restart")
        _run_batch_collect_action("restart")
        return
    raise RuntimeControlError(f"Unsupported market_collectors action: {action}")


def _run_home_feed_action(action: str) -> None:
    if action == "start":
        _prepare_home_feed_runtime()
        _start_service_pair(
            primary_label=BROWSER_FEED_LABEL,
            primary_plist=BROWSER_FEED_PLIST,
            secondary_label=HOME_FEED_LABEL,
            secondary_plist=HOME_FEED_PLIST,
            delay_seconds=4.0,
        )
        return
    if action == "stop":
        _stop_labels(HOME_FEED_LABEL, BROWSER_FEED_LABEL)
        return
    if action == "restart":
        _stop_labels(HOME_FEED_LABEL, BROWSER_FEED_LABEL)
        time.sleep(1.0)
        _run_home_feed_action("start")
        return
    if action == "enable_message_mode":
        _set_home_feed_mode(dry_run=False, max_messages=1)
        return
    if action == "enable_dry_run":
        _set_home_feed_mode(dry_run=True, max_messages=0)
        return
    raise RuntimeControlError(f"Unsupported home_feed action: {action}")


def _run_batch_collect_action(action: str) -> None:
    if action == "start":
        _prepare_batch_collect_runtime()
        _start_service_pair(
            primary_label=BROWSER_BATCH_LABEL,
            primary_plist=BROWSER_BATCH_PLIST,
            secondary_label=BATCH_LABEL,
            secondary_plist=BATCH_PLIST,
            delay_seconds=4.0,
        )
        return
    if action == "stop":
        _stop_labels(BATCH_LABEL, BROWSER_BATCH_LABEL)
        return
    if action == "restart":
        _stop_labels(BATCH_LABEL, BROWSER_BATCH_LABEL)
        time.sleep(1.0)
        _run_batch_collect_action("start")
        return
    raise RuntimeControlError(f"Unsupported batch_collect action: {action}")


def _run_analyzer_runtime_action(action: str) -> None:
    if action == "start":
        _prepare_analyzer_runtime()
        _start_label(ANALYZER_LABEL, ANALYZER_PLIST)
        return
    if action == "stop":
        _stop_labels(ANALYZER_LABEL)
        return
    if action == "restart":
        _stop_labels(ANALYZER_LABEL)
        time.sleep(1.0)
        _run_analyzer_runtime_action("start")
        return
    if action == "run_now":
        _prepare_analyzer_runtime()
        _run_command([str(ANALYZER_RUNTIME_SCRIPT)], timeout_seconds=180.0)
        return
    raise RuntimeControlError(f"Unsupported analyzer_runtime action: {action}")


def _run_local_model_action(action: str) -> None:
    model_key = REVIEW_RUNTIME_ACTION_TO_MODEL_KEY.get(action)
    if model_key is not None:
        _set_local_model_profile(model_key)
        return
    # VLM 72B 动作
    if action == "start_vlm":
        _prepare_vlm_runtime()
        _bootout_label(VLM_LABEL)
        time.sleep(0.5)
        _launchctl_run("enable", f"{LAUNCH_DOMAIN}/{VLM_LABEL}", check=False)
        _start_label(VLM_LABEL, VLM_PLIST)
        return
    if action == "stop_vlm":
        _stop_labels(VLM_LABEL)
        return
    if action == "restart_vlm":
        _stop_labels(VLM_LABEL)
        time.sleep(1.0)
        _run_local_model_action("start_vlm")
        return
    raise RuntimeControlError(f"Unsupported local_model action: {action}")


def _run_vlm_runtime_action(action: str) -> None:
    if action == "start":
        _prepare_vlm_runtime()
        _bootout_label(VLM_LABEL)
        _launchctl_run("enable", f"{LAUNCH_DOMAIN}/{VLM_LABEL}", check=False)
        _start_label(VLM_LABEL, VLM_PLIST)
        return
    if action == "stop":
        _stop_labels(VLM_LABEL)
        return
    if action == "restart":
        _stop_labels(VLM_LABEL)
        time.sleep(1.0)
        _run_vlm_runtime_action("start")
        return
    raise RuntimeControlError(f"Unsupported vlm_runtime action: {action}")


def _run_review_runtime_action(action: str) -> None:
    if action == "start":
        _prepare_review_v3_runtime()
        _stop_review_v3_direct_batch()
        _stop_labels(LEGACY_REVIEW_V2_LABEL)
        _ensure_service_file(REVIEW_V3_RESIDENT_PLIST)
        _launchctl_run("enable", f"{LAUNCH_DOMAIN}/{REVIEW_V3_RESIDENT_LABEL}", check=False)
        _start_label(REVIEW_V3_RESIDENT_LABEL, REVIEW_V3_RESIDENT_PLIST)
        return
    if action == "stop":
        _stop_labels(REVIEW_V3_RESIDENT_LABEL)
        return
    if action == "restart":
        _stop_labels(REVIEW_V3_RESIDENT_LABEL)
        time.sleep(1.0)
        _run_review_runtime_action("start")
        return
    raise RuntimeControlError(f"Unsupported review_runtime action: {action}")


def _run_review_v3_direct_action(action: str) -> None:
    if action == "start_second_pass":
        _start_review_v3_direct_batch("second_pass")
        return
    if action == "stop":
        _stop_review_v3_direct_batch()
        return
    raise RuntimeControlError(f"Unsupported review_v3_direct action: {action}")


def _run_buy_jobs_action(action: str, *, category_code: str | None = None) -> dict[str, Any]:
    if action == "build-buy-baselines":
        return _run_buy_jobs_command("build-buy-baselines", category_code=category_code)
    if action == "refresh-buy-opportunities":
        return _run_buy_jobs_command("refresh-buy-opportunities", category_code=category_code)
    if action == "emit-buy-alerts":
        return _run_buy_jobs_command("emit-buy-alerts", category_code=category_code)
    raise RuntimeControlError(f"Unsupported buy_jobs action: {action}")


def _run_buy_jobs_command(action: str, *, category_code: str | None = None) -> dict[str, Any]:
    command = [
        _resolve_runtime_python(),
        "-m",
        "goofish_insight.cli",
        action,
    ]
    if category_code:
        command.extend(["--category-code", category_code])
    result = _run_command(
        command,
        timeout_seconds=900.0,
    )
    output = result.stdout.strip()
    try:
        parsed = json.loads(output) if output else {}
    except json.JSONDecodeError:
        parsed = {"stdout": output}
    return {
        "action": action,
        "categoryCode": category_code,
        "exit_code": result.returncode,
        "result": parsed,
    }


def _run_template_smoke_action(action: str) -> dict[str, Any]:
    if action != "run_smoke":
        raise RuntimeControlError(f"Unsupported template_smoke action: {action}")
    from .pricing_reporting import run_template_mode_smoke, write_template_smoke_report

    report = run_template_mode_smoke(
        base_url="http://127.0.0.1:8791",
        category_code="apple_computer",
        window_days=30,
        limit=20,
        pricing_view="spec",
        pricing_scope="all",
        pricing_limit=20,
        pricing_freshness_days=30,
        heartbeat_days=14,
        pricing_min_samples=4,
    )
    report_path = write_template_smoke_report(report=report, output=None)
    return {
        "overallStatus": report.get("overallStatus"),
        "checkCount": int(report.get("checkCount") or 0),
        "reportPath": str(report_path),
    }


def _start_service_pair(
    *,
    primary_label: str,
    primary_plist: Path,
    secondary_label: str,
    secondary_plist: Path,
    delay_seconds: float,
) -> None:
    _ensure_service_file(primary_plist)
    _ensure_service_file(secondary_plist)
    _launchctl_run("enable", f"{LAUNCH_DOMAIN}/{primary_label}", check=False)
    _launchctl_run("enable", f"{LAUNCH_DOMAIN}/{secondary_label}", check=False)
    _start_label(primary_label, primary_plist)
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    _start_label(secondary_label, secondary_plist)


def _stop_labels(*labels: str) -> None:
    for label in labels:
        _launchctl_run("disable", f"{LAUNCH_DOMAIN}/{label}", check=False)
        _bootout_label(label)


def _ensure_service_file(plist_path: Path) -> None:
    if not plist_path.exists():
        raise RuntimeControlError(f"LaunchAgent not installed: {plist_path}")


def _prepare_home_feed_runtime() -> None:
    _sync_launch_agent_file(SOURCE_BROWSER_FEED_PLIST, BROWSER_FEED_PLIST)
    _sync_launch_agent_file(SOURCE_HOME_FEED_PLIST, HOME_FEED_PLIST)
    _sync_runtime_script(SOURCE_BROWSER_RUNTIME_SCRIPT, BROWSER_RUNTIME_SCRIPT)
    _sync_runtime_script(SOURCE_HOME_FEED_RUNTIME_SCRIPT, HOME_FEED_RUNTIME_SCRIPT)


def _prepare_batch_collect_runtime() -> None:
    _sync_launch_agent_file(SOURCE_BROWSER_BATCH_PLIST, BROWSER_BATCH_PLIST)
    _sync_launch_agent_file(SOURCE_BATCH_PLIST, BATCH_PLIST)
    _sync_runtime_script(SOURCE_BROWSER_RUNTIME_SCRIPT, BROWSER_RUNTIME_SCRIPT)
    _sync_runtime_script(SOURCE_BATCH_RUNTIME_SCRIPT, BATCH_RUNTIME_SCRIPT)


def _prepare_analyzer_runtime() -> None:
    _sync_launch_agent_file(SOURCE_ANALYZER_PLIST, ANALYZER_PLIST)
    _sync_runtime_script(SOURCE_ANALYZER_RUNTIME_SCRIPT, ANALYZER_RUNTIME_SCRIPT)


def _prepare_legacy_review_v2_runtime() -> None:
    _sync_launch_agent_file(SOURCE_QWEN_PLIST, QWEN_PLIST)
    _sync_launch_agent_file(SOURCE_LEGACY_REVIEW_V2_PLIST, LEGACY_REVIEW_V2_PLIST)
    _sync_runtime_script(SOURCE_LEGACY_REVIEW_V2_RUNTIME_SCRIPT, LEGACY_REVIEW_V2_RUNTIME_SCRIPT)


def _prepare_review_runtime() -> None:
    """Legacy compatibility shim for callers that still patch the old helper name."""
    _prepare_legacy_review_v2_runtime()


def _prepare_review_v3_runtime() -> None:
    _sync_launch_agent_file(SOURCE_REVIEW_V3_RESIDENT_PLIST, REVIEW_V3_RESIDENT_PLIST)
    _sync_runtime_script(SOURCE_REVIEW_V3_RESIDENT_RUNTIME_SCRIPT, REVIEW_V3_RESIDENT_RUNTIME_SCRIPT)


def _prepare_vlm_runtime() -> None:
    _sync_launch_agent_file(SOURCE_VLM_PLIST, VLM_PLIST)


def _safe_pending_review_v3_second_pass() -> int | None:
    try:
        with session_scope() as session:
            rows = session.execute(
                select(ItemReviewV3.candidate_payload).where(ItemReviewV3.resolution_status == "PENDING_REVIEW")
            ).scalars()
            count = 0
            for payload in rows:
                if isinstance(payload, list) and payload:
                    count += 1
            return count
    except Exception:
        return None


def _safe_batch_collect_runtime_summary() -> dict[str, str]:
    summary = {
        "job_status": "等待作业状态写入",
        "checkpoint_status": "暂无 checkpoint",
        "risk_status": "暂无风控记录",
        "cooldown_status": "未处于冷却",
        "next_retry_status": "暂无重试计划",
        "failure_status": "暂无失败原因",
        "risk_event_status": "暂无风险摘要",
    }
    try:
        with session_scope() as session:
            latest_job = session.execute(
                select(CollectorJobRun)
                .where(CollectorJobRun.job_name == "batch_collect")
                .order_by(CollectorJobRun.started_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            latest_checkpoint = session.execute(
                select(CollectorJobCheckpoint)
                .order_by(CollectorJobCheckpoint.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            latest_risk = session.execute(
                select(BatchCollectRiskEvent)
                .order_by(BatchCollectRiskEvent.occurred_at.desc(), BatchCollectRiskEvent.id.desc())
                .limit(1)
            ).scalar_one_or_none()
    except Exception:
        return summary

    if latest_job is not None:
        summary["job_status"] = _format_batch_collect_job_status(latest_job)
        summary.update(_format_batch_collect_runtime_metadata(latest_job.metadata_json))
    if latest_checkpoint is not None:
        summary["checkpoint_status"] = _format_batch_collect_checkpoint_status(latest_checkpoint)
    if latest_risk is not None:
        summary["risk_status"] = _format_batch_collect_risk_status(latest_risk)
        if summary["risk_event_status"] == "暂无风险摘要":
            summary["risk_event_status"] = summary["risk_status"]
    return summary


def _safe_analyzer_runtime_summary() -> dict[str, Any]:
    summary = {
        "job_ok": False,
        "job_health": "暂无 analyzer 作业",
        "job_status": "暂无作业状态",
        "metric_status": "暂无 daily_metrics",
        "score_status": "暂无 model_scores",
        "report_status": "暂无 analysis_reports",
        "latest_log": _read_last_text_line(ANALYZER_LOG) or "暂无 analyzer 日志",
    }
    try:
        with session_scope() as session:
            latest_job = session.execute(
                select(CollectorJobRun)
                .where(
                    CollectorJobRun.job_name.in_(
                        [
                            "analyzer_daily_metrics",
                            "analyzer_model_scores",
                            "analyzer_analysis_reports",
                        ]
                    )
                )
                .order_by(CollectorJobRun.started_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            latest_daily_metric = session.execute(
                select(DailyMetric.metric_date)
                .order_by(DailyMetric.metric_date.desc())
                .limit(1)
            ).scalar_one_or_none()
            latest_daily_metric_count = (
                int(
                    session.execute(
                        select(func.count())
                        .select_from(DailyMetric)
                        .where(DailyMetric.metric_date == latest_daily_metric)
                    ).scalar_one()
                )
                if latest_daily_metric is not None
                else 0
            )
            latest_model_score_date = session.execute(
                select(ModelScore.score_date)
                .order_by(ModelScore.score_date.desc())
                .limit(1)
            ).scalar_one_or_none()
            latest_model_score_count = (
                int(
                    session.execute(
                        select(func.count())
                        .select_from(ModelScore)
                        .where(ModelScore.score_date == latest_model_score_date)
                    ).scalar_one()
                )
                if latest_model_score_date is not None
                else 0
            )
            latest_report_date = session.execute(
                select(AnalysisReport.report_date)
                .where(AnalysisReport.report_type == "market_daily_summary")
                .order_by(AnalysisReport.report_date.desc())
                .limit(1)
            ).scalar_one_or_none()
            latest_report_count = (
                int(
                    session.execute(
                        select(func.count())
                        .select_from(AnalysisReport)
                        .where(AnalysisReport.report_date == latest_report_date)
                        .where(AnalysisReport.report_type == "market_daily_summary")
                    ).scalar_one()
                )
                if latest_report_date is not None
                else 0
            )
    except Exception:
        return summary

    if latest_job is not None:
        summary["job_status"] = _format_batch_collect_job_status(latest_job)
        summary["job_ok"] = str(latest_job.status or "").lower() in {"completed", "running"}
        summary["job_health"] = "最近作业正常" if summary["job_ok"] else f"最近作业 {latest_job.status}"
    if latest_daily_metric is not None:
        summary["metric_status"] = f"{latest_daily_metric.isoformat()} / {latest_daily_metric_count} 行"
    if latest_model_score_date is not None:
        summary["score_status"] = f"{latest_model_score_date.isoformat()} / {latest_model_score_count} 行"
    if latest_report_date is not None:
        summary["report_status"] = f"{latest_report_date.isoformat()} / {latest_report_count} 行"
    return summary


def _safe_launchd_health_summary() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["launchctl", "print", LAUNCH_DOMAIN],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "launchctl query failed").strip()
            return {
                "ok": False,
                "detail": detail[:120] or "launchctl 查询失败",
                "loaded_status": "查询失败",
            }
        loaded_count = len(_launchctl_loaded_labels())
        return {
            "ok": True,
            "detail": "launchctl 可查询",
            "loaded_status": f"{loaded_count}/{len(MANAGED_LABELS)}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "detail": str(exc)[:120] or "launchctl 探针异常",
            "loaded_status": "探针异常",
        }


def _safe_quality_metrics_summary() -> dict[str, Any]:
    """Get latest quality metrics summary for W8 dashboard."""
    summary = {
        "collection_success_rate": "暂无数据",
        "risk_hit_rate": "暂无数据",
        "review_pass_rate": "暂无数据",
        "price_anomaly_rate": "暂无数据",
        "analyzer_job_success_rate": "暂无数据",
        "notification_delivery_status": "暂无数据",
        "last_updated": None,
    }
    try:
        with session_scope() as session:
            # Get latest collection success rate
            latest_success = session.execute(
                select(DataQualityMetric)
                .where(DataQualityMetric.metric_key == "collection_success_rate")
                .order_by(DataQualityMetric.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            # Get latest risk hit rate
            latest_risk = session.execute(
                select(DataQualityMetric)
                .where(DataQualityMetric.metric_key == "risk_hit_rate")
                .order_by(DataQualityMetric.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            # Get latest review pass rate
            latest_review = session.execute(
                select(DataQualityMetric)
                .where(DataQualityMetric.metric_key == "review_pass_rate")
                .order_by(DataQualityMetric.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            latest_price_anomaly = session.execute(
                select(DataQualityMetric)
                .where(DataQualityMetric.metric_key == "price_anomaly_rate")
                .order_by(DataQualityMetric.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            latest_analyzer = session.execute(
                select(DataQualityMetric)
                .where(DataQualityMetric.metric_key == "analyzer_job_success_rate")
                .order_by(DataQualityMetric.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            latest_delivery = session.execute(
                select(NotificationDelivery)
                .order_by(NotificationDelivery.updated_at.desc(), NotificationDelivery.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            pending_delivery_count = int(
                session.execute(
                    select(func.count())
                    .select_from(NotificationDelivery)
                    .where(NotificationDelivery.status == "pending")
                ).scalar_one()
            )
            dead_delivery_count = int(
                session.execute(
                    select(func.count())
                    .select_from(NotificationDelivery)
                    .where(NotificationDelivery.status == "dead")
                ).scalar_one()
            )

            if latest_success:
                summary["collection_success_rate"] = f"{float(latest_success.metric_value):.1%}"
                summary["last_updated"] = latest_success.created_at.isoformat()

            if latest_risk:
                summary["risk_hit_rate"] = f"{float(latest_risk.metric_value):.1%}"

            if latest_review:
                summary["review_pass_rate"] = f"{float(latest_review.metric_value):.1%}"

            if latest_price_anomaly:
                summary["price_anomaly_rate"] = f"{float(latest_price_anomaly.metric_value):.1%}"

            if latest_analyzer:
                summary["analyzer_job_success_rate"] = f"{float(latest_analyzer.metric_value):.1%}"
            if latest_delivery:
                summary["notification_delivery_status"] = (
                    f"{latest_delivery.status} / pending {pending_delivery_count} / dead {dead_delivery_count}"
                )
            else:
                summary["notification_delivery_status"] = (
                    f"pending {pending_delivery_count} / dead {dead_delivery_count}"
                )

    except Exception:
        pass

    return summary


def _safe_buy_jobs_runtime_summary(*, category_code: str | None = None) -> dict[str, Any]:
    normalized_category_code = _normalize_runtime_category_code(category_code)
    summary = {
        "category_code": normalized_category_code,
        "scope_detail": _runtime_scope_detail(normalized_category_code),
        "latest_baseline_at": None,
        "latest_opportunity_at": None,
        "latest_alert_at": None,
        "recent_baseline_count": 0,
        "recent_opportunity_count": 0,
        "recent_alert_count": 0,
        "latest_baseline_detail": "暂无记录",
        "latest_opportunity_detail": "暂无记录",
        "latest_alert_detail": "暂无记录",
    }
    now = datetime.now(UTC)
    window = now - timedelta(hours=24)
    try:
        with session_scope() as session:
            category_id = _resolve_category_id_for_runtime_scope(
                session,
                category_code=normalized_category_code,
            )
            if normalized_category_code and category_id is None:
                return summary
            baseline_query = select(func.max(BuyPriceBaseline.created_at))
            opportunity_query = select(func.max(BuyOpportunity.last_detected_at))
            alert_query = select(func.max(BuyAlertEvent.created_at))
            recent_baseline_query = select(func.count()).select_from(BuyPriceBaseline).where(
                BuyPriceBaseline.created_at >= window
            )
            recent_opportunity_query = select(func.count()).select_from(BuyOpportunity).where(
                BuyOpportunity.last_detected_at >= window
            )
            recent_alert_query = select(func.count()).select_from(BuyAlertEvent).where(
                BuyAlertEvent.created_at >= window
            )
            if category_id is not None:
                baseline_query = baseline_query.where(BuyPriceBaseline.category_id == category_id)
                opportunity_query = opportunity_query.where(BuyOpportunity.category_id == category_id)
                alert_query = alert_query.join(
                    BuyOpportunity,
                    BuyOpportunity.id == BuyAlertEvent.opportunity_id,
                ).where(BuyOpportunity.category_id == category_id)
                recent_baseline_query = recent_baseline_query.where(BuyPriceBaseline.category_id == category_id)
                recent_opportunity_query = recent_opportunity_query.where(BuyOpportunity.category_id == category_id)
                recent_alert_query = recent_alert_query.join(
                    BuyOpportunity,
                    BuyOpportunity.id == BuyAlertEvent.opportunity_id,
                ).where(BuyOpportunity.category_id == category_id)

            summary["latest_baseline_at"] = session.execute(baseline_query).scalar_one_or_none()
            summary["latest_opportunity_at"] = session.execute(opportunity_query).scalar_one_or_none()
            summary["latest_alert_at"] = session.execute(alert_query).scalar_one_or_none()
            summary["recent_baseline_count"] = int(
                session.execute(recent_baseline_query).scalar_one()
            )
            summary["recent_opportunity_count"] = int(
                session.execute(recent_opportunity_query).scalar_one()
            )
            summary["recent_alert_count"] = int(
                session.execute(recent_alert_query).scalar_one()
            )
    except Exception:
        return summary

    if summary["latest_baseline_at"] is not None:
        summary["latest_baseline_detail"] = _format_runtime_datetime(
            summary["latest_baseline_at"], "暂无记录"
        )
    if summary["latest_opportunity_at"] is not None:
        summary["latest_opportunity_detail"] = _format_runtime_datetime(
            summary["latest_opportunity_at"], "暂无记录"
        )
    if summary["latest_alert_at"] is not None:
        summary["latest_alert_detail"] = _format_runtime_datetime(
            summary["latest_alert_at"], "暂无记录"
        )
    return summary


def _normalize_runtime_category_code(category_code: str | None) -> str | None:
    normalized = resolve_category_code(category_code)
    return normalized or None


def _resolve_category_id_for_runtime_scope(session, *, category_code: str | None) -> str | None:
    if not category_code:
        return None
    category = session.execute(select(Category).where(Category.code == category_code)).scalar_one_or_none()
    return str(category.id) if category is not None else None


def _runtime_scope_detail(category_code: str | None) -> str:
    if not category_code:
        return "全部类目"
    return f"{display_label_for_scope(category_code)} ({category_code})"


def _review_v3_direct_pid() -> int | None:
    try:
        raw = REVIEW_V3_DIRECT_PID.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _review_v3_direct_is_running() -> bool:
    pid = _review_v3_direct_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _load_review_v3_direct_state() -> dict[str, Any]:
    try:
        return json.loads(REVIEW_V3_DIRECT_STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_review_v3_resident_state() -> dict[str, Any]:
    try:
        return json.loads(REVIEW_V3_RESIDENT_STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_review_v3_direct_state(payload: dict[str, Any]) -> None:
    RUNTIME_HOME.mkdir(parents=True, exist_ok=True)
    REVIEW_V3_DIRECT_STATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _review_v3_direct_latest_output_path(state: dict[str, Any] | None = None) -> Path | None:
    state = state or {}
    output_path = str(state.get("output_path") or "").strip()
    if output_path:
        candidate = Path(output_path)
        if candidate.exists():
            return candidate
    candidates = sorted(
        REPORTS_DIR.glob("review-v3-direct-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _review_v3_resident_latest_output_path(state: dict[str, Any] | None = None) -> Path | None:
    state = state or {}
    output_path = str(state.get("output_path") or "").strip()
    if output_path:
        candidate = Path(output_path)
        if candidate.exists():
            return candidate
    candidates = sorted(
        REPORTS_DIR.glob("review-v3-resident-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _start_review_v3_direct_batch(phase: str) -> None:
    if not REVIEW_V3_DIRECT_SCRIPT.exists():
        raise RuntimeControlError("Review V3 direct 脚本不存在。")
    if _review_v3_direct_is_running():
        raise RuntimeControlError("Review V3 Direct 已在运行，请先停止当前任务。")
    RUNTIME_HOME.mkdir(parents=True, exist_ok=True)
    LIBRARY_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_path = REPORTS_DIR / f"review-v3-direct-{phase}-{timestamp}.json"
    stdout_handle = REVIEW_V3_DIRECT_LOG.open("ab")
    stderr_handle = REVIEW_V3_DIRECT_ERR_LOG.open("ab")
    env = os.environ.copy()
    env.update(
        {
            "OUTPUT_PATH": str(output_path),
            "AI_TIMEOUT_SEC": env.get("AI_TIMEOUT_SEC", "90"),
            "LIMIT": env.get("REVIEW_V3_DIRECT_LIMIT", env.get("REVIEW_V3_COZELOOP_LIMIT", "50")),
        }
    )
    process = subprocess.Popen(
        [str(REVIEW_V3_DIRECT_SCRIPT), "second-pass" if phase == "second_pass" else "first-pass"],
        cwd=str(ROOT_DIR),
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        start_new_session=True,
    )
    stdout_handle.close()
    stderr_handle.close()
    REVIEW_V3_DIRECT_PID.write_text(str(process.pid), encoding="utf-8")
    _save_review_v3_direct_state(
        {
            "pid": process.pid,
            "phase": phase,
            "output_path": str(output_path),
            "started_at": datetime.now(UTC).isoformat(),
        }
    )


def _stop_review_v3_direct_batch() -> None:
    pid = _review_v3_direct_pid()
    if pid is not None:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
    REVIEW_V3_DIRECT_PID.unlink(missing_ok=True)


def _sync_launch_agent_file(source_path: Path, target_path: Path) -> None:
    _sync_file_if_needed(source_path, target_path, mode=0o644, render_launchd_template=True)


def _sync_runtime_script(source_path: Path, target_path: Path) -> None:
    _sync_file_if_needed(source_path, target_path, mode=0o755)


def _sync_file_if_needed(
    source_path: Path,
    target_path: Path,
    *,
    mode: int,
    render_launchd_template: bool = False,
) -> None:
    if not source_path.exists():
        raise RuntimeControlError(f"Missing runtime file: {source_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = source_path.read_bytes()
    if render_launchd_template:
        source_bytes = _render_launchd_template(source_bytes)
    if target_path.exists():
        try:
            if source_bytes == target_path.read_bytes():
                target_path.chmod(mode)
                return
        except OSError:
            pass
    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    temp_path.write_bytes(source_bytes)
    temp_path.chmod(mode)
    temp_path.replace(target_path)


def _render_launchd_template(source_bytes: bytes) -> bytes:
    text = source_bytes.decode("utf-8")
    replacements = {
        "__GOOFISH_ROOT_DIR__": str(ROOT_DIR),
        "__GOOFISH_RUNTIME_HOME__": str(RUNTIME_HOME),
        "__GOOFISH_LOG_DIR__": str(LIBRARY_LOGS_DIR),
        "__GOOFISH_PYTHON_BIN__": os.environ.get("GOOFISH_PYTHON_BIN", str(ROOT_DIR / ".venv" / "bin" / "python")),
        "__GOOFISH_NODE_BIN__": os.environ.get("GOOFISH_NODE_BIN", "node"),
        "__LOCAL_QWEN_PYTHON_BIN__": LOCAL_QWEN_PYTHON_BIN,
        "__LOCAL_QWEN_WORKDIR__": LOCAL_QWEN_WORKDIR,
        "__QWEN3_MODEL_PATH__": QWEN3_MODEL_PATH,
        "__QWEN25_VL_MODEL_PATH__": VLM_MODEL_PATH,
    }
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text.encode("utf-8")


def _start_label(label: str, plist_path: Path) -> None:
    if _is_label_loaded(label):
        _launchctl_run("kickstart", "-k", f"{LAUNCH_DOMAIN}/{label}")
        return
    completed = _launchctl_run("load", str(plist_path), check=False)
    if completed.returncode == 0 or _is_label_loaded(label):
        return
    stderr = completed.stderr.strip()
    stdout = completed.stdout.strip()
    message = stderr or stdout or f"launchctl load failed for {label}"
    raise RuntimeControlError(message)


def _bootout_label(label: str) -> None:
    _launchctl_run("bootout", f"{LAUNCH_DOMAIN}/{label}", check=False)
    plist_path = MANAGED_LABEL_TO_PLIST.get(label)
    if plist_path is not None:
        _launchctl_run("bootout", LAUNCH_DOMAIN, str(plist_path), check=False)
        _launchctl_run("unload", str(plist_path), check=False)


def _launchctl_loaded_labels() -> set[str]:
    return {label for label in MANAGED_LABELS if _is_label_loaded(label)}


def _is_label_loaded(label: str) -> bool:
    """Check if a specific label is loaded using launchctl print."""
    try:
        result = subprocess.run(
            ["launchctl", "print", f"{LAUNCH_DOMAIN}/{label}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Exit code 0 means service exists
        return result.returncode == 0
    except Exception:
        return False


def _launchctl_run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run_command(["launchctl", *args], check=check)


def _run_command(command: list[str], *, check: bool = True, timeout_seconds: float = 30.0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(ROOT_DIR),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        message = stderr or stdout or f"Command failed: {' '.join(command)}"
        raise RuntimeControlError(message)
    return completed


def _resolve_runtime_python() -> str:
    venv_python = ROOT_DIR / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable


def _is_local_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _read_last_json_line(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    line = _read_last_text_line(path)
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _read_last_text_line(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    last_line: str | None = None
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                last_line = line
    return last_line


def _load_latest_template_smoke_report() -> dict[str, Any]:
    try:
        raw = LATEST_TEMPLATE_SMOKE_REPORT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_home_feed_mode() -> dict[str, Any]:
    target_path = HOME_FEED_PLIST if HOME_FEED_PLIST.exists() else SOURCE_HOME_FEED_PLIST
    if not target_path.exists():
        return {"dry_run": True, "max_messages": 0, "summary": "未找到 launchd 配置"}
    payload = _load_launchd_plist_payload(target_path)
    env = payload.get("EnvironmentVariables", {})
    dry_run = str(env.get("DRY_RUN", "1")) != "0"
    max_messages = int(str(env.get("MAX_MESSAGES", "0")) or "0")
    mode_label = "真实消息" if not dry_run else "Dry Run"
    return {
        "dry_run": dry_run,
        "max_messages": max_messages,
        "summary": f"{mode_label} / 每轮最多 {max_messages} 条",
    }


def _set_home_feed_mode(*, dry_run: bool, max_messages: int) -> None:
    for path in _home_feed_plist_paths():
        _update_plist_environment(
            path,
            {
                "DRY_RUN": "1" if dry_run else "0",
                "MAX_MESSAGES": str(max_messages),
            },
        )
    if HOME_FEED_LABEL in _launchctl_loaded_labels():
        _run_home_feed_action("restart")


def _update_plist_environment(path: Path, updates: dict[str, str]) -> None:
    with path.open("rb") as handle:
        payload = plistlib.load(handle)
    environment = payload.setdefault("EnvironmentVariables", {})
    for key, value in updates.items():
        environment[key] = value
    with path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)


def _home_feed_plist_paths() -> list[Path]:
    return [path for path in (SOURCE_HOME_FEED_PLIST, HOME_FEED_PLIST) if path.exists()]


def _review_runtime_qwen_plist_paths() -> list[Path]:
    return [path for path in (SOURCE_QWEN_PLIST, QWEN_PLIST) if path.exists()]


def _legacy_review_v2_worker_plist_paths() -> list[Path]:
    return [path for path in (SOURCE_LEGACY_REVIEW_V2_PLIST, LEGACY_REVIEW_V2_PLIST) if path.exists()]


def _review_runtime_worker_plist_paths() -> list[Path]:
    """Legacy compatibility shim for callers that still patch the old helper name."""
    return _legacy_review_v2_worker_plist_paths()


def _load_vlm_download_status() -> dict[str, Any]:
    model_dir = Path(VLM_MODEL_PATH)
    shards = sorted(model_dir.glob("model-*.safetensors")) if model_dir.exists() else []
    total = _infer_vlm_shard_total(shards)
    size = _human_size_for_path(model_dir)
    return {
        "present": len(shards),
        "total": total,
        "complete": len(shards) >= total,
        "size": size,
    }


def _infer_vlm_shard_total(shards: list[Path]) -> int:
    if not shards:
        return VLM_DEFAULT_SHARD_TOTAL
    for shard in shards:
        match = re.search(r"-of-(\d+)\.safetensors$", shard.name)
        if match is not None:
            return int(match.group(1))
    return VLM_DEFAULT_SHARD_TOTAL


def _fetch_vlm_health() -> dict[str, Any] | None:
    if not _is_local_port_open(VLM_PORT):
        return None
    try:
        with urlopen(f"http://127.0.0.1:{VLM_PORT}/health", timeout=1.5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        return None


def _human_size_for_path(path: Path) -> str:
    if not path.exists():
        return "未下载"
    total_bytes = 0
    if path.is_file():
        total_bytes = path.stat().st_size
    else:
        for child in path.rglob("*"):
            if child.is_file():
                total_bytes += child.stat().st_size
    if total_bytes <= 0:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(total_bytes)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)}{units[unit_index]}"
    return f"{size:.1f}{units[unit_index]}"


def _load_review_runtime_model_selection() -> dict[str, str]:
    qwen_path = QWEN_PLIST if QWEN_PLIST.exists() else SOURCE_QWEN_PLIST
    worker_path = LEGACY_REVIEW_V2_PLIST if LEGACY_REVIEW_V2_PLIST.exists() else SOURCE_LEGACY_REVIEW_V2_PLIST
    if not qwen_path.exists() or not worker_path.exists():
        return {"key": "unknown", "label": "未知"}

    qwen_payload = _load_launchd_plist_payload(qwen_path)
    worker_payload = _load_launchd_plist_payload(worker_path)

    program_arguments = [str(value) for value in qwen_payload.get("ProgramArguments", [])]
    worker_env = worker_payload.get("EnvironmentVariables", {})
    worker_ai_model = str(worker_env.get("AI_MODEL", ""))

    for key, config in REVIEW_RUNTIME_MODELS.items():
        expected_arguments = [str(value) for value in config["program_arguments"]]
        if program_arguments == expected_arguments or worker_ai_model == config["worker_ai_model"]:
            return {"key": key, "label": str(config["label"])}

    fallback = Path(worker_ai_model).name if worker_ai_model else "自定义"
    return {"key": "custom", "label": fallback}


def _set_local_model_profile(model_key: str) -> None:
    config = REVIEW_RUNTIME_MODELS.get(model_key)
    if config is None:
        raise RuntimeControlError(f"Unsupported review runtime model: {model_key}")

    _prepare_legacy_review_v2_runtime()
    qwen_paths = _review_runtime_qwen_plist_paths()
    worker_paths = _legacy_review_v2_worker_plist_paths()
    if not qwen_paths or not worker_paths:
        raise RuntimeControlError("Review runtime launchd 配置不存在，无法切换模型")

    for path in qwen_paths:
        _update_review_runtime_model_service(path, config)
    for path in worker_paths:
        _update_plist_environment(
            path,
            {
                "AI_MODEL": str(config["worker_ai_model"]),
                "EXPECTED_MODEL_SNIPPET": str(config["expected_model_snippet"]),
            },
        )

    loaded_labels = _launchctl_loaded_labels()
    model_loaded = QWEN_LABEL in loaded_labels
    worker_loaded = LEGACY_REVIEW_V2_LABEL in loaded_labels
    if not model_loaded and not worker_loaded:
        return

    _stop_labels(LEGACY_REVIEW_V2_LABEL, QWEN_LABEL)
    time.sleep(1.0)

    if model_loaded or worker_loaded:
        _bootout_label(CONFLICT_QWEN_LABEL)
        _launchctl_run("disable", f"{LAUNCH_DOMAIN}/{CONFLICT_QWEN_LABEL}", check=False)
        _launchctl_run("enable", f"{LAUNCH_DOMAIN}/{QWEN_LABEL}", check=False)
        _start_label(QWEN_LABEL, QWEN_PLIST)
    if worker_loaded:
        _launchctl_run("enable", f"{LAUNCH_DOMAIN}/{LEGACY_REVIEW_V2_LABEL}", check=False)
        _start_label(LEGACY_REVIEW_V2_LABEL, LEGACY_REVIEW_V2_PLIST)


def _update_review_runtime_model_service(path: Path, config: dict[str, Any]) -> None:
    with path.open("rb") as handle:
        payload = plistlib.load(handle)
    payload["ProgramArguments"] = list(config["program_arguments"])
    payload["WorkingDirectory"] = str(config["working_directory"])
    with path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)


def _load_launchd_plist_payload(path: Path) -> dict[str, Any]:
    payload_bytes = path.read_bytes()
    if path.parent == SOURCE_LAUNCHD_DIR:
        payload_bytes = _render_launchd_template(payload_bytes)
    return plistlib.loads(payload_bytes)


def _latest_legacy_review_v2_log_path() -> Path | None:
    candidates = sorted(REPORTS_DIR.glob("llm-review-v2-worker-*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _safe_pending_reviews_legacy_v2() -> int | None:
    try:
        return count_pending_reviews(business_domain=None)
    except Exception:
        return None


def _fetch_model_name() -> str | None:
    if not _is_local_port_open(8000):
        return None
    try:
        with urlopen("http://127.0.0.1:8000/v1/models", timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        return None
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None
    model_id = data[0].get("id")
    if not model_id:
        return None
    return Path(str(model_id)).name


def _format_feed_cycle(payload: dict[str, Any]) -> str:
    if not payload:
        return "暂无 feed 周期"
    watch_cycle = payload.get("watch_cycle")
    visible_card_count = payload.get("visible_card_count")
    target_match_count = payload.get("target_match_count")
    message_sent_count = payload.get("message_sent_count")
    return (
        f"第 {watch_cycle or '-'} 轮 / {visible_card_count or 0} 卡 / "
        f"{target_match_count or 0} 命中 / {message_sent_count or 0} 发送"
    )


def _format_feed_log(payload: dict[str, Any]) -> str:
    if not payload:
        return "暂无 feed 日志"
    generated_at = payload.get("generated_at")
    updated_item_count = payload.get("updated_item_count")
    price_changed_count = payload.get("price_changed_count")
    snapshot_inserted_count = payload.get("snapshot_inserted_count")
    timestamp = _format_timestamp(generated_at)
    return (
        f"{timestamp} / 更新 {updated_item_count or 0} / "
        f"改价 {price_changed_count or 0} / 快照 {snapshot_inserted_count or 0}"
    )


def _format_review_event(payload: dict[str, Any] | None, log_path: Path | None) -> str:
    if not payload:
        return log_path.name if log_path else "暂无 worker 日志"
    batch_index = payload.get("batch_index")
    pending_after = payload.get("pending_after")
    worker_stats = payload.get("worker_stats") or {}
    unresolved_count = worker_stats.get("quarantined_low_confidence_count")
    return (
        f"第 {batch_index or '-'} 批 / pending_after {pending_after or '-'} / "
        f"低置信 {unresolved_count or 0}"
    )


def _format_batch_collect_job_status(job_run: CollectorJobRun) -> str:
    phase = str(job_run.phase or "-").strip() or "-"
    status = str(job_run.status or "-").strip() or "-"
    if job_run.finished_at is not None:
        return f"{phase} / {status} / 结束 {_format_timestamp(job_run.finished_at.isoformat())}"
    return f"{phase} / {status} / 开始 {_format_timestamp(job_run.started_at.isoformat())}"


def _format_batch_collect_checkpoint_status(checkpoint: CollectorJobCheckpoint) -> str:
    return (
        f'{checkpoint.checkpoint_mode} / pending {checkpoint.cursor_pending} / '
        f'committed {checkpoint.cursor_committed}'
    )


def _format_batch_collect_risk_status(event: BatchCollectRiskEvent) -> str:
    occurred_at = event.occurred_at.isoformat() if event.occurred_at else None
    backoff_seconds = int(event.backoff_seconds or 0)
    return (
        f'{_format_timestamp(occurred_at)} / 连续 {int(event.consecutive_risk_hits or 0)} 次 / '
        f'退避 {backoff_seconds}s'
    )


def _format_batch_collect_runtime_metadata(metadata: Any) -> dict[str, str]:
    payload = dict(metadata or {}) if isinstance(metadata, dict) else {}
    cooldown_reason = str(payload.get("cooldown_reason") or "").strip()
    cooldown_started_at = _parse_iso_datetime(payload.get("cooldown_started_at"))
    recovery_eta = _parse_iso_datetime(payload.get("recovery_eta"))
    next_retry_at = _parse_iso_datetime(payload.get("next_retry_at"))
    recent_failure_reason = str(payload.get("recent_failure_reason") or "").strip()
    recent_risk_event = str(payload.get("recent_risk_event") or "").strip()
    next_cooldown_seconds = payload.get("next_cooldown_seconds")
    try:
        resolved_next_cooldown_seconds = max(int(next_cooldown_seconds), 0)
    except (TypeError, ValueError):
        resolved_next_cooldown_seconds = 0

    cooldown_status = "未处于冷却"
    if cooldown_reason or cooldown_started_at or recovery_eta:
        reason_label = cooldown_reason or "unknown"
        start_label = _format_timestamp(cooldown_started_at.isoformat() if cooldown_started_at else None)
        eta_label = _format_timestamp(recovery_eta.isoformat() if recovery_eta else None)
        cooldown_status = f"{reason_label} / 开始 {start_label} / 恢复 {eta_label}"
        if resolved_next_cooldown_seconds > 0:
            cooldown_status += f" / 下次冷静 {resolved_next_cooldown_seconds}s"

    next_retry_status = "暂无重试计划"
    if next_retry_at is not None:
        now = datetime.now(UTC)
        remaining_seconds = int((next_retry_at - now).total_seconds())
        if remaining_seconds > 0:
            next_retry_status = f"{_format_timestamp(next_retry_at.isoformat())} / 剩余 {remaining_seconds}s"
        else:
            next_retry_status = f"{_format_timestamp(next_retry_at.isoformat())} / 可立即重试"

    return {
        "cooldown_status": cooldown_status,
        "next_retry_status": next_retry_status,
        "failure_status": recent_failure_reason or "暂无失败原因",
        "risk_event_status": recent_risk_event or "暂无风险摘要",
    }


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%H:%M:%S")
    except ValueError:
        return value


def _format_runtime_datetime(value: datetime | None, fallback: str) -> str:
    if value is None:
        return fallback
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _group_status_detail(status: str) -> str:
    if status == "running":
        return "运行中"
    if status == "degraded":
        return "部分可用"
    if status == "stopped":
        return "已停止"
    return status
