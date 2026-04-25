from __future__ import annotations

import asyncio
import json
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from .compat import UTC
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import urlopen
from uuid import UUID, uuid4

import typer
from sqlalchemy import and_, delete, desc, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError

try:
    from alembic.config import Config as AlembicConfig
except ModuleNotFoundError:
    AlembicConfig = None

try:
    from playwright.sync_api import Response, sync_playwright
except ModuleNotFoundError:
    Response = Any

    def sync_playwright():
        raise RuntimeError("playwright is required for browser collection commands. Install with: pip install playwright")

from .db import session_scope
from .category_compat import compatible_scope_keys, is_analytics_scope, resolve_category_code, token_aliases_for_scope
from .application.services.collector_ingest import (
    CATEGORY_INGEST_GATE_PROFILES,
    CategoryIngestGateProfile,
    ListingCleanupResult,
    PreparedListing,
    RejectedPreparedListing,
    build_intake_review_candidate,
    canonical_signature_text,
    classify_category_ingest_block_reason,
    classify_ingest_block_reason,
    classify_title_length_ingest_block_reason,
    extract_source_numeric_signature_tokens,
    filter_category_profile_prepared_listings_for_ingest,
    filter_suspicious_prepared_listings_for_ingest,
    filter_title_length_prepared_listings_for_ingest,
    load_ingest_rejection_item_ids,
    load_ingest_rejection_item_ids_with_session,
    mark_item_snapshot_timestamp,
    prepare_listings_for_persistence,
    should_allow_suspicious_listing_ingest,
    split_permanently_rejected_prepared_listings,
    touch_item_ingest_rejections,
    title_matches_source_numeric_signature,
    upsert_item_ingest_rejection,
    upsert_item_ingest_rejections,
    should_insert_snapshot,
)
from .application.services.home_feed_rules import (
    FEED_COMMERCIAL_BADGE_TOKENS,
    FeedCardCandidate,
    FeedDetailSellerSnapshot,
    FeedTargetMatch,
    build_feed_detail_url,
    build_feed_outreach_message_text,
    build_feed_target_match,
    classify_feed_detail_seller_snapshot,
    compute_feed_expected_profit_margin_pct,
    determine_feed_candidate_domains,
    feed_target_priority,
    format_feed_message_price,
    infer_scope_from_feed_title,
    match_feed_title_to_task_lexicon,
    normalize_feed_seller_type,
    resolve_feed_collection_scope_domain,
    resolve_feed_seller_type,
    should_open_feed_detail_for_match,
    should_open_feed_detail_for_task,
    should_message_feed_target,
)
from .entrypoints.cli.collect import register_collect_commands
from .entrypoints.cli.feed import register_feed_commands
from .entrypoints.cli.maintenance import register_maintenance_commands
from .entrypoints.cli.mobile import register_mobile_commands
from .entrypoints.cli.pricing import register_pricing_commands
from .application.services.pricing_reporting import write_model_discovery_report
from .entrypoints.cli.review import register_review_commands
from .entrypoints.cli.search import (
    CapturedSearchPayload,
    ManualVerificationRequired,
    SearchPlanEntry,
    SearchPlanOutcome,
    group_batch_plans_by_platform,
)
from .application.services.review_ingest import (
    contains_suspicious_listing_keyword,
    screen_suspicious_intake_candidates,
)
from .application.services.collector_browser import (
    build_manual_verification_transport_message,
    build_search_capture_failure_message,
    classify_payload_status,
    detect_page_risk_control_signal,
    detect_page_risk_control_signal_from_page,
    extract_payload_error,
    infer_auth_state_from_error_message,
    is_browser_disconnect_error,
    is_manual_verification_state,
    should_keep_manual_verification_page_open,
)
from .application.services.browser_guard import record_browser_guard_observation
from .application.services.browser_guard_analytics import persist_browser_job_attempt
from .application.services.collector_runs import capture_run_progress, finalize_run
from .application.services.apple_preprocess import preprocess_apple_items
from .application.services.category_resolution import (
    ResolvedItemCategoryContext,
    backfill_item_category_resolution,
    resolve_item_category_context_with_session,
)
from .application.services.feed_category_resolution import resolve_feed_category_selection_with_session
from .application.services.feed_workflow_runtime import (
    build_category_context_from_item,
    persist_home_feed_item_decision,
    persist_home_feed_item_decision_for_item,
)
from .application.services.task_category_backfill import backfill_task_category_bindings
from .application.services.crawl_task_runtime import (
    build_crawl_task_runtime_config,
    build_crawl_task_runtime_config_with_session,
)
from .application.services.price_backfill import backfill_normalized_prices
from .application.services.seller_classification import classify_seller_types
from .application.services.spec_candidate_queue import load_items_for_enrichment as load_items_for_enrichment_from_queue
from .models import (
    AnalysisReport,
    BrowserSession,
    Category,
    CategoryRuntimeProfile,
    CrawlRun,
    CrawlTask,
    DailyMetric,
    Item,
    ItemIngestRejection,
    OutreachRecord,
    ItemSpecEnrichment,
    ItemSnapshot,
    RawRequest,
    RawResponse,
    SellerProfile,
)
from .normalizers import ExtractedItem, extract_items_from_response, extract_metadata, load_json, normalize_market_price, normalize_title
from .pricing import (
    build_pricing_views,
    decimal_to_float,
    resolve_pricing_record,
    title_is_non_comparable_listing,
    title_matches_domain,
)
from .application.services.pricing_templates import build_pricing_record_template_snapshot
from .specs import SpecEnrichmentCandidate, extract_item_specs, llm_is_configured
from .settings import get_settings

try:
    from .entrypoints.cli.admin import register_admin_commands
except ModuleNotFoundError:
    def register_admin_commands(*_args, **_kwargs):
        return None

app = typer.Typer(no_args_is_help=True)

HOME_FEED_API_PATH = "mtop.taobao.idlehome.home.webpc.feed/1.0"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


def active_template_id_for_category(session, category_id: str | None) -> str | None:
    if not category_id:
        return None
    runtime_profile = session.execute(
        select(CategoryRuntimeProfile)
        .where(CategoryRuntimeProfile.category_id == category_id)
        .where(CategoryRuntimeProfile.status == "ACTIVE")
        .limit(1)
    ).scalar_one_or_none()
    return runtime_profile.active_template_id if runtime_profile is not None else None


STALE_RUNNING_RUN_TIMEOUT = timedelta(minutes=10)


def reconcile_stale_running_runs_with_session(
    session,
    *,
    now: datetime | None = None,
    older_than: timedelta = STALE_RUNNING_RUN_TIMEOUT,
) -> int:
    resolved_now = now or datetime.now(UTC)
    cutoff = resolved_now - older_than
    stale_runs = list(
        session.execute(
            select(CrawlRun).where(func.lower(CrawlRun.status) == "running")
        ).scalars().all()
    )
    recovered = 0
    timeout_minutes = max(int(older_than.total_seconds() // 60), 1)
    for run in stale_runs:
        started_at = getattr(run, "started_at", None)
        if str(getattr(run, "status", "") or "").lower() != "running":
            continue
        if started_at is None or started_at >= cutoff:
            continue
        run.status = "cancelled"
        run.finished_at = resolved_now
        if not getattr(run, "error_message", None):
            run.error_message = (
                f"Recovered stale running run after exceeding {timeout_minutes} minute timeout."
            )
        recovered += 1
    return recovered


def reconcile_stale_running_runs(
    *,
    now: datetime | None = None,
    older_than: timedelta = STALE_RUNNING_RUN_TIMEOUT,
) -> int:
    with session_scope() as session:
        return reconcile_stale_running_runs_with_session(
            session,
            now=now,
            older_than=older_than,
        )


UNBOUNDED_PAGE_SENTINEL = 9999
HOME_FEED_TAB_SEQUENCE = ("猜你喜欢", "个人闲置")
HOME_FEED_TAB_DWELL_MS = 10_000
HOME_FEED_LAST_SELECTED_TAB: str | None = None
DEFAULT_ATTACHED_CDP_PORTS = (9222, 9223, 9333)
SEARCH_PAGE_INTERVAL_MIN_MS = 29_800
SEARCH_PAGE_INTERVAL_MAX_MS = 30_600


def alembic_config():
    if AlembicConfig is None:
        raise RuntimeError("alembic is required for migration commands. Install with: pip install alembic")
    config = AlembicConfig("alembic.ini")
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


def default_config_path() -> Path:
    return get_settings().base_dir / "apps" / "collector" / "configs" / "monitor_tasks.json"


def reports_dir() -> Path:
    path = get_settings().base_dir / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_report_path() -> Path:
    return reports_dir() / "latest-model-discovery.json"


def load_task_config(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or default_config_path())


def load_profile_settings(profile_key: str) -> dict[str, Any]:
    try:
        config = load_task_config()
    except FileNotFoundError:
        return {}
    return config.get("profiles", {}).get(profile_key, {})


def export_task_config_bundle(*, config_path: Path | None = None, include_inactive: bool = False) -> dict[str, Any]:
    try:
        existing_config = load_task_config(config_path) if config_path is not None else load_task_config()
    except FileNotFoundError:
        existing_config = {}

    with session_scope() as session:
        stmt = select(CrawlTask).order_by(CrawlTask.id.asc())
        if not include_inactive:
            stmt = stmt.where(CrawlTask.status == "active")
        tasks = list(session.execute(stmt).scalars())
        exported_tasks: list[dict[str, Any]] = []
        for task in tasks:
            runtime_config = build_crawl_task_runtime_config_with_session(session, task_key=task.task_key)
            exported_tasks.append(
                {
                    "task_key": task.task_key,
                    "source_platform": task.source_platform,
                    "category_id": task.category_id,
                    "business_domain": task.business_domain,
                    "task_type": task.task_type,
                    "display_name": task.display_name,
                    "keywords": list(task.keywords or []),
                    "brand_lexicon": [row["term"] for row in runtime_config["lexicons"].get("BRAND", [])],
                    "model_lexicon": [row["term"] for row in runtime_config["lexicons"].get("MODEL", [])],
                    "config_lexicon": [row["term"] for row in runtime_config["lexicons"].get("CONFIG", [])],
                    "paging_limit": int(task.paging_limit or 1),
                    "profile_key": task.profile_key,
                    "parallel_tabs": int(task.parallel_tabs or 1),
                    "status": task.status,
                    "metadata_json": dict(task.metadata_json or {}),
                    "queries": [
                        {
                            "id": query["id"],
                            "query": query["query"],
                            "pages": int(query.get("pages", task.paging_limit or 1)),
                            "priority": int(query.get("priority", 100)),
                            "status": query.get("status", "ACTIVE"),
                            "metadata": dict(query.get("metadata") or {}),
                        }
                        for query in runtime_config["queries"]
                        if str(query.get("query", "")).strip()
                    ],
                }
            )

    return {
        "profiles": dict(existing_config.get("profiles") or {}),
        "tasks": exported_tasks,
    }


SEED_TASK_DEFAULTS: dict[str, dict[str, Any]] = {
    "garmin_watch": {
        "display_name": "Garmin Watch Monitor",
        "keywords": ["佳明", "garmin", "fenix", "epix", "forerunner"],
        "brand_lexicon": ["佳明", "garmin"],
        "model_lexicon": ["fenix", "epix", "instinct", "forerunner", "venu", "marq", "approach"],
        "config_lexicon": [],
    },
    "apple_computer": {
        "display_name": "Apple Computer Monitor",
        "keywords": ["苹果", "macbook", "mac mini", "mac studio", "m1", "m2", "m3", "m4"],
        "brand_lexicon": ["苹果", "apple"],
        "model_lexicon": ["macbook air", "macbook pro", "mac mini", "mac studio", "imac"],
        "config_lexicon": ["8g", "16g", "18g", "24g", "32g", "36g", "48g", "64g", "512g", "1tb", "2tb"],
    },
    "camera_interchangeable_lens": {
        "display_name": "Interchangeable Lens Monitor",
        "keywords": ["镜头", "尼康", "佳能", "索尼", "腾龙", "适马"],
        "brand_lexicon": ["尼康", "nikon", "佳能", "canon", "索尼", "sony", "腾龙", "tamron", "适马", "sigma"],
        "model_lexicon": ["24-70", "70-200", "50 1.2", "85 1.4", "z 24-70", "rf 24-70", "fe 24-70"],
        "config_lexicon": ["f1.2", "f1.4", "f1.8", "f2.8", "f4"],
    },
    "camera_body": {
        "display_name": "Camera Body Monitor",
        "keywords": ["机身", "相机", "尼康", "佳能", "索尼", "富士"],
        "brand_lexicon": ["尼康", "nikon", "佳能", "canon", "索尼", "sony", "富士", "fujifilm"],
        "model_lexicon": ["z8", "zf", "z6", "a7", "a7c", "r6", "r5", "xt5", "xt4"],
        "config_lexicon": [],
    },
    "graphics_card": {
        "display_name": "Graphics Card Monitor",
        "keywords": ["显卡", "rtx", "rx", "nvidia", "amd"],
        "brand_lexicon": ["英伟达", "nvidia", "amd", "华硕", "微星", "七彩虹", "技嘉", "索泰"],
        "model_lexicon": ["rtx 4090", "rtx 4080", "rtx 4070", "rtx 4060", "rx 7900", "rx 7800", "rx 7700"],
        "config_lexicon": ["8g", "12g", "16g", "20g", "24g"],
    },
    "phone": {
        "display_name": "Phone Monitor",
        "keywords": ["手机", "iphone", "华为", "小米", "vivo", "oppo"],
        "brand_lexicon": ["apple", "苹果", "huawei", "华为", "xiaomi", "小米", "vivo", "oppo", "荣耀", "honor"],
        "model_lexicon": ["iphone 15", "iphone 16", "mate 60", "mate 70", "pura 70", "xiaomi 14", "x200", "find x8"],
        "config_lexicon": ["128g", "256g", "512g", "1tb"],
    },
}


@app.command("seed-task")
def seed_task(
    task_key: str | None = None,
    category_code: str = "garmin_watch",
    business_domain: str | None = None,
    display_name: str | None = None,
) -> None:
    settings = get_settings()
    resolved_task_key = task_key or settings.default_task_key
    requested_scope = category_code or business_domain or "garmin_watch"
    resolved_scope = resolve_category_code(requested_scope)
    default_seed = _seed_defaults_for_scope(resolved_scope)
    resolved_display_name = display_name or str(default_seed["display_name"])
    resolved_category_id = _resolve_category_id_by_code(resolved_scope)
    task_config = {
        "task_key": resolved_task_key,
        "category_id": resolved_category_id,
        "business_domain": resolved_scope,
        "display_name": resolved_display_name,
        "keywords": list(default_seed["keywords"]),
        "brand_lexicon": list(default_seed["brand_lexicon"]),
        "model_lexicon": list(default_seed["model_lexicon"]),
        "config_lexicon": list(default_seed["config_lexicon"]),
        "paging_limit": 5,
    }
    ensure_task(task_config)
    typer.echo(
        f"Created or updated task: {resolved_task_key} "
        f"(scope={resolved_scope}, category_id={resolved_category_id or 'none'})"
    )


@app.command("seed-tasks-from-config")
def seed_tasks_from_config(config_path: Path = typer.Option(default_config_path())) -> None:
    config = load_task_config(config_path)
    for task in config.get("tasks", []):
        ensure_task(task)
        typer.echo(f"Upserted task: {task['task_key']}")


@app.command("ingest-mock")
def ingest_mock(
    path: Path = Path("mock/data.json"),
    task_key: str | None = None,
    source_keyword: str = "garmin",
) -> None:
    settings = get_settings()
    resolved_task_key = task_key or settings.default_task_key
    payload = load_json(path)

    task = get_task_or_raise(resolved_task_key)
    run_id = create_run(task_id=task.id, tab_count=1)
    captured = CapturedSearchPayload(
        page_number=1,
        request_url=f"https://www.goofish.com/search?q={quote_plus(source_keyword)}",
        request_body={"source_keyword": source_keyword},
        request_headers={"source": "mock"},
        response_status=200,
        payload=payload,
        captured_at=datetime.now(UTC),
    )
    persist_captured_payloads(
        run_id=run_id,
        task=task,
        task_query_id=None,
        source_keyword=source_keyword,
        captures=[captured],
        report_type="mock_ingestion",
    )
    finalize_run(run_id=run_id, status="completed", pages_attempted=1, pages_succeeded=1)
    typer.echo(f"Ingested {len(extract_items_from_response(payload))} items for task {resolved_task_key}.")


def _seed_defaults_for_scope(scope: str) -> dict[str, Any]:
    defaults = SEED_TASK_DEFAULTS.get(scope)
    if defaults is not None:
        return defaults
    token_aliases = [token for token in token_aliases_for_scope(scope) if token.strip()]
    keywords = token_aliases[:8]
    return {
        "display_name": f"{scope} Monitor",
        "keywords": keywords,
        "brand_lexicon": keywords[:4],
        "model_lexicon": [],
        "config_lexicon": [],
    }


def _resolve_category_id_by_code(category_code: str | None) -> str | None:
    resolved_code = resolve_category_code(category_code)
    if not resolved_code:
        return None
    with session_scope() as session:
        category = session.execute(
            select(Category).where(Category.code == resolved_code)
        ).scalar_one_or_none()
        return str(category.id) if category is not None else None


def ensure_task(task_config: dict[str, Any]) -> None:
    normalized_scope = resolve_category_code(task_config.get("business_domain"))
    category_id = task_config.get("category_id")
    if category_id is None and normalized_scope:
        category_id = _resolve_category_id_by_code(normalized_scope)

    with session_scope() as session:
        existing = session.execute(
            select(CrawlTask).where(CrawlTask.task_key == task_config["task_key"])
        ).scalar_one_or_none()
        payload = {
            "source_platform": task_config.get("source_platform", "xianyu"),
            "category_id": category_id,
            "business_domain": normalized_scope or task_config["business_domain"],
            "task_type": task_config.get("task_type", "PRODUCTION"),
            "display_name": task_config["display_name"],
            "keywords": task_config.get("keywords", []),
            "brand_lexicon": task_config.get("brand_lexicon", []),
            "model_lexicon": task_config.get("model_lexicon", []),
            "config_lexicon": task_config.get("config_lexicon", []),
            "paging_limit": int(task_config.get("paging_limit", 1)),
            "profile_key": task_config.get("profile_key", "default"),
            "parallel_tabs": int(task_config.get("parallel_tabs", 1)),
            "status": task_config.get("status", "active"),
            "metadata_json": dict(task_config.get("metadata_json") or task_config.get("metadata") or {}),
        }
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
        else:
            session.add(CrawlTask(task_key=task_config["task_key"], **payload))


def get_task_or_raise(task_key: str) -> CrawlTask:
    with session_scope() as session:
        task = session.execute(
            select(CrawlTask).where(CrawlTask.task_key == task_key)
        ).scalar_one_or_none()
        if task is None:
            raise typer.BadParameter(f"Task '{task_key}' not found. Run seed-task first.")
        session.expunge(task)
        return task


def create_run(*, task_id: int, tab_count: int) -> UUID:
    run_id = uuid4()
    reconcile_stale_running_runs()
    with session_scope() as session:
        session.add(
            CrawlRun(
                id=run_id,
                task_id=task_id,
                status="running",
                tab_count=tab_count,
                pages_attempted=0,
                pages_succeeded=0,
            )
        )
    return run_id


def finalize_search_capture_interruption(
    *,
    run_id: UUID,
    captures: dict[int, CapturedSearchPayload],
    attempted_pages: int,
    profile_key: str,
    profile_dir: Path,
    browser_channel: str,
    auth_state: str,
    login_required_at: datetime | None,
    authenticated_at: datetime | None,
) -> None:
    pages_attempted, pages_succeeded = capture_run_progress(
        captures=captures,
        attempted_pages=attempted_pages,
    )
    message = "Interrupted by user."
    finalize_run(
        run_id=run_id,
        status="cancelled",
        pages_attempted=pages_attempted,
        pages_succeeded=pages_succeeded,
        error_message=message,
    )
    upsert_browser_session_state(
        profile_key=profile_key,
        profile_dir=profile_dir,
        browser_channel=browser_channel,
        auth_state=auth_state,
        login_required_at=login_required_at,
        authenticated_at=authenticated_at,
        last_error=message,
    )


def run_live_search_batch(
    *,
    plans: list[SearchPlanEntry],
    channel: str,
    headless: bool,
    cdp_url: str | None,
    parallel_tabs: int,
    profile_key: str,
    profile_dir: Path,
    login_wait_seconds: int,
) -> list[SearchPlanOutcome]:
    if not plans:
        typer.echo("No batch queries found.")
        return []

    profile_dir.mkdir(parents=True, exist_ok=True)
    resolved_cdp_url = resolve_cdp_url(cdp_url)

    def open_browser_page(playwright):
        if resolved_cdp_url:
            browser = playwright.chromium.connect_over_cdp(resolved_cdp_url)
            if not browser.contexts:
                raise RuntimeError(f"No context found on attached browser: {resolved_cdp_url}")
            context = browser.contexts[0]
            page = context.new_page()
            return browser, context, page, True, True

        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel=channel,
            headless=headless,
            viewport={"width": 1440, "height": 960},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        return context, context, page, False, True

    if parallel_tabs > 1:
        if not resolved_cdp_url:
            raise RuntimeError("Parallel tabs require an attached Chrome instance with CDP enabled.")
        return run_parallel_search_batch(
            plans=plans,
            resolved_cdp_url=resolved_cdp_url,
            channel=channel,
            profile_key=profile_key,
            profile_dir=profile_dir,
            login_wait_seconds=login_wait_seconds,
            parallel_tabs=parallel_tabs,
        )

    outcomes: list[SearchPlanOutcome] = []
    with sync_playwright() as playwright:
        owner, context, page, attached, owns_page = open_browser_page(playwright)
        keep_page_open = False
        try:
            for plan in plans:
                if page.is_closed():
                    owner, context, page, attached, owns_page = open_browser_page(playwright)
                typer.echo(f"[{plan.task.task_key}] collecting query: {plan.query}")
                try:
                    result = execute_search_capture_on_page(
                        page=page,
                        task=plan.task,
                        query=plan.query,
                        task_query_id=plan.task_query_id,
                        pages=plan.pages,
                        profile_key=profile_key,
                        profile_dir=profile_dir,
                        browser_channel=channel,
                        login_wait_seconds=login_wait_seconds,
                    )
                    typer.echo(
                        f"[{plan.task.task_key}] completed query: {plan.query} | pages={result['pages_succeeded']}"
                    )
                    outcomes.append(
                        SearchPlanOutcome(
                            plan=plan,
                            status="completed",
                            pages_succeeded=int(result.get("pages_succeeded") or 0),
                            pages_attempted=int(result.get("pages_attempted") or 0),
                            auth_state="authenticated",
                            run_id=result.get("run_id"),
                        )
                    )
                except ManualVerificationRequired as exc:
                    typer.echo(
                        f"[{plan.task.task_key}] manual verification required: {plan.query} | {exc}"
                    )
                    keep_page_open = bool(exc.keep_page_open)
                    outcomes.append(
                        SearchPlanOutcome(
                            plan=plan,
                            status="manual_verification_required",
                            auth_state=exc.auth_state,
                            run_id=exc.run_id,
                            error_message=str(exc),
                        )
                    )
                    if attached and not keep_page_open and owns_page and not page.is_closed():
                        try:
                            page.close()
                        except Exception:
                            pass
                    break
                except Exception as exc:
                    typer.echo(f"[{plan.task.task_key}] query failed: {plan.query} | {exc}")
                    error_message = str(exc)
                    outcomes.append(
                        SearchPlanOutcome(
                            plan=plan,
                            status="failed",
                            auth_state=infer_auth_state_from_error_message(error_message),
                            error_message=error_message,
                        )
                    )
                    if "Target page, context or browser has been closed" in str(exc):
                        try:
                            owner, context, page, attached, owns_page = open_browser_page(playwright)
                        except Exception:
                            pass
                if not page.is_closed():
                    try:
                        page.wait_for_timeout(3000)
                    except Exception:
                        pass
        except KeyboardInterrupt:
            typer.echo("Batch collection interrupted by user.")
        finally:
            try:
                if attached:
                    if not keep_page_open and owns_page and not page.is_closed():
                        page.close()
                else:
                    if not keep_page_open:
                        context.close()
            except Exception:
                pass
    return outcomes


def run_parallel_search_batch(
    *,
    plans: list[SearchPlanEntry],
    resolved_cdp_url: str,
    channel: str,
    profile_key: str,
    profile_dir: Path,
    login_wait_seconds: int,
    parallel_tabs: int,
) -> list[SearchPlanOutcome]:
    worker_count = min(max(parallel_tabs, 1), len(plans))
    typer.echo(f"Running {len(plans)} queries with {worker_count} parallel tabs on the attached Chrome instance.")

    outcomes: list[SearchPlanOutcome] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                run_search_plan_in_attached_tab,
                plan=plan,
                resolved_cdp_url=resolved_cdp_url,
                channel=channel,
                profile_key=profile_key,
                profile_dir=profile_dir,
                login_wait_seconds=login_wait_seconds,
            ): plan
            for plan in plans
        }
        for future in as_completed(futures):
            plan = futures[future]
            try:
                result = future.result()
                typer.echo(
                    f"[{plan.task.task_key}] completed query: {plan.query} | pages={result['pages_succeeded']}"
                )
                outcomes.append(
                    SearchPlanOutcome(
                        plan=plan,
                        status="completed",
                        pages_succeeded=int(result.get("pages_succeeded") or 0),
                        pages_attempted=int(result.get("pages_attempted") or 0),
                        auth_state="authenticated",
                        run_id=result.get("run_id"),
                    )
                )
            except ManualVerificationRequired as exc:
                typer.echo(
                    f"[{plan.task.task_key}] manual verification required: {plan.query} | {exc}"
                )
                outcomes.append(
                    SearchPlanOutcome(
                        plan=plan,
                        status="manual_verification_required",
                        auth_state=exc.auth_state,
                        run_id=exc.run_id,
                        error_message=str(exc),
                    )
                )
            except Exception as exc:
                typer.echo(f"[{plan.task.task_key}] query failed: {plan.query} | {exc}")
                error_message = str(exc)
                outcomes.append(
                    SearchPlanOutcome(
                        plan=plan,
                        status="failed",
                        auth_state=infer_auth_state_from_error_message(error_message),
                        error_message=error_message,
                    )
                )
    return outcomes


def run_search_plan_in_attached_tab(
    *,
    plan: SearchPlanEntry,
    resolved_cdp_url: str,
    channel: str,
    profile_key: str,
    profile_dir: Path,
    login_wait_seconds: int,
) -> dict[str, Any]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(resolved_cdp_url)
        if not browser.contexts:
            raise RuntimeError(f"No context found on attached browser: {resolved_cdp_url}")
        context = browser.contexts[0]
        page = context.new_page()
        keep_page_open = False
        try:
            return execute_search_capture_on_page(
                page=page,
                task=plan.task,
                query=plan.query,
                task_query_id=plan.task_query_id,
                pages=plan.pages,
                profile_key=profile_key,
                profile_dir=profile_dir,
                browser_channel=channel,
                login_wait_seconds=login_wait_seconds,
            )
        except ManualVerificationRequired as exc:
            keep_page_open = bool(exc.keep_page_open)
            raise
        finally:
            try:
                if not keep_page_open and not page.is_closed():
                    page.close()
            except Exception:
                pass


def execute_search_capture_on_page(
    *,
    page,
    task: CrawlTask,
    query: str,
    task_query_id: int | None,
    pages: int,
    profile_key: str,
    profile_dir: Path,
    browser_channel: str,
    login_wait_seconds: int,
) -> dict[str, Any]:
    target_pages = resolve_target_pages(task=task, pages=pages)
    attempted_pages = target_pages or 0
    run_id = create_run(task_id=task.id, tab_count=1)
    captures: dict[int, CapturedSearchPayload] = {}
    persisted_page_numbers: set[int] = set()
    auth_state = "unknown"
    login_required_at: datetime | None = None
    authenticated_at: datetime | None = None
    last_error: str | None = None
    search_url = f"https://www.goofish.com/search?q={quote_plus(query)}"

    def on_response(resp: Response) -> None:
        nonlocal auth_state, login_required_at, authenticated_at, last_error
        if not resp.url.startswith(
            "https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/"
        ):
            return

        try:
            payload = json.loads(resp.text())
        except json.JSONDecodeError as exc:
            last_error = f"invalid_json:{exc}"
            return

        request_body = parse_request_body(resp.request.post_data or "")
        request_headers = dict(resp.request.headers)
        page_number = int(request_body.get("pageNumber", 1) or 1)

        payload_status = classify_payload_status(payload)
        if payload_status == "login_required":
            auth_state = "login_required"
            login_required_at = datetime.now(UTC)
            last_error = extract_payload_error(payload)
            return

        if payload_status == "risk_control":
            auth_state = "risk_control"
            last_error = extract_payload_error(payload)
            return

        if payload.get("api") != "mtop.taobao.idlemtopsearch.pc.search":
            return
        if not isinstance(payload.get("data", {}).get("resultList"), list):
            return

        auth_state = "authenticated"
        authenticated_at = datetime.now(UTC)
        last_error = None
        captures[page_number] = CapturedSearchPayload(
            page_number=page_number,
            request_url=resp.url,
            request_body=request_body,
            request_headers=request_headers,
            response_status=resp.status,
            payload=payload,
            captured_at=datetime.now(UTC),
        )

    def flush_new_pages() -> None:
        persist_new_capture_pages(
            run_id=run_id,
            task=task,
            task_query_id=task_query_id,
            source_keyword=query,
            captures=captures,
            persisted_page_numbers=persisted_page_numbers,
            report_type="live_search_capture",
        )

    page.on("response", on_response)
    try:
        typer.echo(f"Opening {search_url}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

        login_deadline = time.time() + login_wait_seconds
        login_prompt_printed = False
        risk_prompt_printed = False

        while not captures and time.time() < login_deadline:
            risk_control_signal = detect_page_risk_control_signal_from_page(page)
            if risk_control_signal:
                auth_state = "risk_control"
                last_error = last_error or risk_control_signal
            if auth_state == "login_required" and not login_prompt_printed:
                typer.echo("需要登录。请在打开的浏览器里完成闲鱼登录，系统会记录该 profile 的登录态。")
                login_prompt_printed = True
            if auth_state == "risk_control" and not risk_prompt_printed:
                typer.echo("触发闲鱼风控校验，不一定是登录失效。请在浏览器里停留并手动完成可能出现的验证。")
                risk_prompt_printed = True
            page.wait_for_timeout(1000)

        flush_new_pages()

        auto_paginate = pages <= 0
        pagination_deadline = time.time() + pagination_deadline_seconds(
            target_pages=target_pages,
            login_wait_seconds=login_wait_seconds,
        )
        paginate_captured_search_results(
            page=page,
            captures=captures,
            target_pages=target_pages,
            deadline=pagination_deadline,
            auto_paginate=auto_paginate,
            on_new_capture_pages=flush_new_pages,
        )

        flush_new_pages()

        if not captures:
            message = build_search_capture_failure_message(auth_state=auth_state, last_error=last_error)
            finalize_run(
                run_id=run_id,
                status="failed",
                pages_attempted=attempted_pages,
                pages_succeeded=0,
                error_message=message,
            )
            upsert_browser_session_state(
                profile_key=profile_key,
                profile_dir=profile_dir,
                browser_channel=browser_channel,
                auth_state=auth_state,
                login_required_at=login_required_at,
                authenticated_at=authenticated_at,
                last_error=last_error or message,
            )
            if is_manual_verification_state(auth_state):
                raise ManualVerificationRequired(
                    message,
                    auth_state=auth_state,
                    run_id=run_id,
                    keep_page_open=should_keep_manual_verification_page_open(auth_state),
                )
            raise RuntimeError(message)

        ordered, attempted_pages, succeeded_pages = summarize_capture_pages(captures)
        if target_pages is not None:
            ordered = ordered[:target_pages]
            attempted_pages = len(ordered)
            succeeded_pages = sum(1 for capture in ordered if search_results_count(capture.payload) > 0)
        finalize_run(
            run_id=run_id,
            status="completed",
            pages_attempted=attempted_pages,
            pages_succeeded=succeeded_pages,
        )
        upsert_browser_session_state(
            profile_key=profile_key,
            profile_dir=profile_dir,
            browser_channel=browser_channel,
            auth_state=auth_state if auth_state != "unknown" else "authenticated",
            login_required_at=login_required_at,
            authenticated_at=authenticated_at or datetime.now(UTC),
            last_error=last_error,
        )
        return {"run_id": run_id, "pages_succeeded": succeeded_pages, "pages_attempted": attempted_pages}
    except ManualVerificationRequired:
        raise
    except KeyboardInterrupt:
        finalize_search_capture_interruption(
            run_id=run_id,
            captures=captures,
            attempted_pages=attempted_pages,
            profile_key=profile_key,
            profile_dir=profile_dir,
            browser_channel=browser_channel,
            auth_state=auth_state,
            login_required_at=login_required_at,
            authenticated_at=authenticated_at,
        )
        raise
    except Exception as exc:
        error_message = str(exc)
        pages_attempted, pages_succeeded = capture_run_progress(
            captures=captures,
            attempted_pages=attempted_pages,
        )
        if is_manual_verification_state(auth_state) and is_browser_disconnect_error(error_message):
            message = build_manual_verification_transport_message(
                auth_state=auth_state,
                last_error=last_error,
                transport_error=error_message,
            )
            finalize_run(
                run_id=run_id,
                status="failed",
                pages_attempted=pages_attempted,
                pages_succeeded=pages_succeeded,
                error_message=message,
            )
            upsert_browser_session_state(
                profile_key=profile_key,
                profile_dir=profile_dir,
                browser_channel=browser_channel,
                auth_state=auth_state,
                login_required_at=login_required_at,
                authenticated_at=authenticated_at,
                last_error=message,
            )
            raise ManualVerificationRequired(
                message,
                auth_state=auth_state,
                run_id=run_id,
                keep_page_open=False,
            ) from exc
        finalize_run(
            run_id=run_id,
            status="failed",
            pages_attempted=pages_attempted,
            pages_succeeded=pages_succeeded,
            error_message=error_message,
        )
        upsert_browser_session_state(
            profile_key=profile_key,
            profile_dir=profile_dir,
            browser_channel=browser_channel,
            auth_state=auth_state,
            login_required_at=login_required_at,
            authenticated_at=authenticated_at,
            last_error=error_message,
        )
        raise
    finally:
        page.remove_listener("response", on_response)


def run_live_search_capture(
    *,
    task: CrawlTask,
    query: str,
    pages: int,
    channel: str,
    headless: bool,
    profile_key: str,
    profile_dir: Path,
    login_wait_seconds: int,
) -> dict[str, Any]:
    profile_dir.mkdir(parents=True, exist_ok=True)
    target_pages = resolve_target_pages(task=task, pages=pages)
    attempted_pages = target_pages or 0
    run_id = create_run(task_id=task.id, tab_count=1)
    captures: dict[int, CapturedSearchPayload] = {}
    persisted_page_numbers: set[int] = set()
    auth_state = "unknown"
    login_required_at: datetime | None = None
    authenticated_at: datetime | None = None
    last_error: str | None = None
    search_url = f"https://www.goofish.com/search?q={quote_plus(query)}"

    def on_response(resp: Response) -> None:
        nonlocal auth_state, login_required_at, authenticated_at, last_error
        if not resp.url.startswith(
            "https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/"
        ):
            return

        try:
            payload = json.loads(resp.text())
        except json.JSONDecodeError as exc:
            last_error = f"invalid_json:{exc}"
            return

        request_body = parse_request_body(resp.request.post_data or "")
        request_headers = dict(resp.request.headers)
        page_number = int(request_body.get("pageNumber", 1) or 1)

        payload_status = classify_payload_status(payload)
        if payload_status == "login_required":
            auth_state = "login_required"
            login_required_at = datetime.now(UTC)
            last_error = extract_payload_error(payload)
            return

        if payload_status == "risk_control":
            auth_state = "risk_control"
            last_error = extract_payload_error(payload)
            return

        if payload.get("api") != "mtop.taobao.idlemtopsearch.pc.search":
            return
        if not isinstance(payload.get("data", {}).get("resultList"), list):
            return

        auth_state = "authenticated"
        authenticated_at = datetime.now(UTC)
        last_error = None
        captures[page_number] = CapturedSearchPayload(
            page_number=page_number,
            request_url=resp.url,
            request_body=request_body,
            request_headers=request_headers,
            response_status=resp.status,
            payload=payload,
            captured_at=datetime.now(UTC),
        )

    def flush_new_pages() -> None:
        persist_new_capture_pages(
            run_id=run_id,
            task=task,
            source_keyword=query,
            captures=captures,
            persisted_page_numbers=persisted_page_numbers,
            report_type="live_search_capture",
        )

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel=channel,
                headless=headless,
                viewport={"width": 1440, "height": 960},
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.on("response", on_response)

            typer.echo(f"Opening {search_url}")
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

            login_deadline = time.time() + login_wait_seconds
            login_prompt_printed = False
            risk_prompt_printed = False

            while not captures and time.time() < login_deadline:
                risk_control_signal = detect_page_risk_control_signal_from_page(page)
                if risk_control_signal:
                    auth_state = "risk_control"
                    last_error = last_error or risk_control_signal
                if auth_state == "login_required" and not login_prompt_printed:
                    typer.echo("需要登录。请在打开的浏览器里完成闲鱼登录，系统会记录该 profile 的登录态。")
                    login_prompt_printed = True
                if auth_state == "risk_control" and not risk_prompt_printed:
                    typer.echo("触发闲鱼风控校验，不一定是登录失效。请在浏览器里停留并手动完成可能出现的验证。")
                    risk_prompt_printed = True
                page.wait_for_timeout(1000)

            manual_verification_deadline = time.time() + max(login_wait_seconds, 3600)
            while not captures and is_manual_verification_state(auth_state) and time.time() < manual_verification_deadline:
                risk_control_signal = detect_page_risk_control_signal_from_page(page)
                if risk_control_signal:
                    auth_state = "risk_control"
                    last_error = last_error or risk_control_signal
                if auth_state == "login_required" and not login_prompt_printed:
                    typer.echo("需要登录。请在打开的浏览器里完成闲鱼登录，系统会记录该 profile 的登录态。")
                    login_prompt_printed = True
                if auth_state == "risk_control" and not risk_prompt_printed:
                    typer.echo("触发闲鱼风控校验，不一定是登录失效。请在浏览器里停留并手动完成可能出现的验证。")
                    risk_prompt_printed = True
                page.wait_for_timeout(1000)

            flush_new_pages()

            paginate_captured_search_results(
                page=page,
                captures=captures,
                target_pages=target_pages,
                deadline=time.time()
                + pagination_deadline_seconds(
                    target_pages=target_pages,
                    login_wait_seconds=login_wait_seconds,
                ),
                auto_paginate=pages <= 0,
                on_new_capture_pages=flush_new_pages,
            )

            flush_new_pages()
            context.close()

        if not captures:
            if auth_state == "risk_control":
                message = f"No valid search payload captured. Risk control blocked the search: {last_error or 'unknown'}"
            elif auth_state == "login_required":
                message = f"No valid search payload captured. Login is still required: {last_error or 'unknown'}"
            else:
                message = "No valid search payload captured."
            finalize_run(
                run_id=run_id,
                status="failed",
                pages_attempted=attempted_pages,
                pages_succeeded=0,
                error_message=message,
            )
            upsert_browser_session_state(
                profile_key=profile_key,
                profile_dir=profile_dir,
                browser_channel=channel,
                auth_state=auth_state,
                login_required_at=login_required_at,
                authenticated_at=authenticated_at,
                last_error=last_error or message,
            )
            raise RuntimeError(message)

        ordered, attempted_pages, succeeded_pages = summarize_capture_pages(captures)
        if target_pages is not None:
            ordered = ordered[:target_pages]
            attempted_pages = len(ordered)
            succeeded_pages = sum(1 for capture in ordered if search_results_count(capture.payload) > 0)
        finalize_run(
            run_id=run_id,
            status="completed",
            pages_attempted=attempted_pages,
            pages_succeeded=succeeded_pages,
        )
        upsert_browser_session_state(
            profile_key=profile_key,
            profile_dir=profile_dir,
            browser_channel=channel,
            auth_state=auth_state if auth_state != "unknown" else "authenticated",
            login_required_at=login_required_at,
            authenticated_at=authenticated_at or datetime.now(UTC),
            last_error=last_error,
        )
        return {"run_id": run_id, "pages_succeeded": succeeded_pages, "pages_attempted": attempted_pages}
    except Exception as exc:
        finalize_run(
            run_id=run_id,
            status="failed",
            pages_attempted=max(len(captures), attempted_pages),
            pages_succeeded=sum(1 for capture in captures.values() if search_results_count(capture.payload) > 0),
            error_message=str(exc),
        )
        upsert_browser_session_state(
            profile_key=profile_key,
            profile_dir=profile_dir,
            browser_channel=channel,
            auth_state=auth_state,
            login_required_at=login_required_at,
            authenticated_at=authenticated_at,
            last_error=str(exc),
        )
        raise


def persist_new_capture_pages(
    *,
    run_id: UUID,
    task: CrawlTask,
    task_query_id: int | None,
    source_keyword: str,
    captures: dict[int, CapturedSearchPayload],
    persisted_page_numbers: set[int],
    report_type: str,
) -> None:
    new_page_numbers = sorted(page_number for page_number in captures if page_number not in persisted_page_numbers)
    for page_number in new_page_numbers:
        persist_captured_payloads(
            run_id=run_id,
            task=task,
            task_query_id=task_query_id,
            source_keyword=source_keyword,
            captures=[captures[page_number]],
            report_type=report_type,
        )
        persisted_page_numbers.add(page_number)
        typer.echo(
            f"[{task.task_key}] persisted query page: {source_keyword} | page={page_number}"
        )


def persist_captured_payloads(
    *,
    run_id: UUID,
    task: CrawlTask,
    task_query_id: int | None,
    source_keyword: str,
    captures: list[CapturedSearchPayload],
    report_type: str,
) -> None:
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            _persist_captured_payloads_once(
                run_id=run_id,
                task=task,
                task_query_id=task_query_id,
                source_keyword=source_keyword,
                captures=captures,
                report_type=report_type,
            )
            return
        except Exception as exc:
            if not is_retryable_persist_deadlock(exc) or attempt >= max_attempts:
                raise
            wait_seconds = 0.35 * attempt + random.uniform(0.05, 0.2)
            typer.echo(
                f"[{task.task_key}] persist deadlock retry {attempt}/{max_attempts - 1} "
                f"for query {source_keyword} after {wait_seconds:.2f}s"
            )
            time.sleep(wait_seconds)


def _persist_captured_payloads_once(
    *,
    run_id: UUID,
    task: CrawlTask,
    task_query_id: int | None,
    source_keyword: str,
    captures: list[CapturedSearchPayload],
    report_type: str,
) -> None:
    cleanup = prepare_listings_for_persistence(captures)
    ingest_listings, permanently_rejected_item_ids = split_permanently_rejected_prepared_listings(
        source_platform=task.source_platform,
        listings=cleanup.kept,
    )
    ingest_listings, title_length_summary, title_length_rejections = filter_title_length_prepared_listings_for_ingest(
        listings=ingest_listings,
    )
    ingest_listings, suspicious_intake_summary, suspicious_intake_rejections = filter_suspicious_prepared_listings_for_ingest(
        task=task,
        source_keyword=source_keyword,
        listings=ingest_listings,
    )
    ingest_listings, category_gate_summary, category_gate_rejections = filter_category_profile_prepared_listings_for_ingest(
        task=task,
        source_keyword=source_keyword,
        listings=ingest_listings,
    )
    recorded_rejections = [
        *title_length_rejections,
        *suspicious_intake_rejections,
        *category_gate_rejections,
    ]
    if title_length_summary["blocked_count"]:
        typer.echo(
            f"[{task.task_key}] tombstoned {title_length_summary['blocked_count']} overlong-title listings "
            f"for {source_keyword}: {title_length_summary['blocked_reasons']}"
        )
    if category_gate_summary["blocked_count"]:
        typer.echo(
            f"[{task.task_key}] blocked {category_gate_summary['blocked_count']} category-mismatch listings "
            f"for {source_keyword}: {category_gate_summary['blocked_reasons']}"
        )
    ingest_listings = sorted(
        ingest_listings,
        key=lambda listing: (
            listing.extracted.seller_id or "",
            listing.extracted.item_id,
        ),
    )
    total_items = 0
    duplicate_items = cleanup.duplicate_item_count
    rejected_missing_price_count = cleanup.rejected_missing_price_count
    rejected_low_price_count = cleanup.rejected_low_price_count
    skipped_snapshot_count = 0
    unique_sellers: set[str] = set()
    cached_seller_ids: dict[str, int] = {}
    latest_metadata: dict[str, Any] = {}
    raw_retained = not get_settings().prune_raw_after_ingest
    raw_response_ids_by_page: dict[int, UUID] = {}
    touched_permanent_rejection_count = 0
    recorded_rejection_count = 0

    with session_scope() as session:
        touched_permanent_rejection_count = touch_item_ingest_rejections(
            session=session,
            source_platform=task.source_platform,
            item_ids=permanently_rejected_item_ids,
        )
        recorded_rejection_count = upsert_item_ingest_rejections(
            session=session,
            task=task,
            rejected=recorded_rejections,
        )

        for capture in captures:
            metadata = extract_metadata(capture.payload)
            latest_metadata = metadata
            if not raw_retained:
                continue

            raw_request = RawRequest(
                run_id=run_id,
                task_id=task.id,
                task_query_id=task_query_id,
                source_platform=task.source_platform,
                request_url=capture.request_url,
                method="POST",
                request_headers=capture.request_headers,
                request_body=capture.request_body,
                captured_at=capture.captured_at,
            )
            session.add(raw_request)
            session.flush()

            raw_response = RawResponse(
                run_id=run_id,
                task_id=task.id,
                task_query_id=task_query_id,
                source_platform=task.source_platform,
                raw_request_id=raw_request.id,
                api_name=capture.payload.get("api", "mtop.taobao.idlemtopsearch.pc.search"),
                response_status=capture.response_status,
                response_body=capture.payload,
                response_summary=metadata,
                captured_at=capture.captured_at,
            )
            session.add(raw_response)
            session.flush()
            raw_response_ids_by_page[capture.page_number] = raw_response.id

        for listing in ingest_listings:
            extracted = listing.extracted
            total_items += 1
            seller_profile_id = None
            if extracted.seller_id:
                seller_profile_id = cached_seller_ids.get(extracted.seller_id)
                if seller_profile_id is None:
                    seller_profile_id = upsert_seller(
                        session=session,
                        seller_id=extracted.seller_id,
                        seller_name=extracted.seller_name,
                        avatar_url=extracted.seller_avatar_url,
                        region=extracted.area,
                    )
                    cached_seller_ids[extracted.seller_id] = seller_profile_id
                unique_sellers.add(extracted.seller_id)

            raw_response_id = raw_response_ids_by_page.get(listing.page_number) if raw_retained else None
            item_pk = upsert_item(
                session=session,
                task=task,
                task_query_id=task_query_id,
                raw_response_id=raw_response_id,
                seller_profile_id=seller_profile_id,
                extracted=extracted,
                source_keyword=source_keyword,
            )

            if should_insert_snapshot(
                session=session,
                item_id_ref=item_pk,
                extracted=extracted,
            ):
                snapshot_time = datetime.now(UTC)
                snapshot_extra_json = {
                    "source_keyword": source_keyword,
                    "page_number": listing.page_number,
                }
                snapshot_extra_json.update(
                    build_snapshot_template_metadata(
                        task=task,
                        extracted=extracted,
                    )
                )
                session.add(
                    ItemSnapshot(
                        item_id_ref=item_pk,
                        task_query_id=task_query_id,
                        raw_response_id=raw_response_id,
                        price=extracted.price,
                        region=extracted.area,
                        condition_tags=extracted.tags,
                        snapshot_at=snapshot_time,
                        publish_time=extracted.publish_time,
                        extra_json=snapshot_extra_json,
                    )
                )
                mark_item_snapshot_timestamp(session=session, item_id_ref=item_pk, snapshot_time=snapshot_time)
            else:
                skipped_snapshot_count += 1

        session.add(
            DailyMetric(
                metric_date=date.today(),
                business_domain=task.business_domain,
                category_id=task.category_id,
                model_catalog_id=None,
                normalized_model=None,
                listing_count=total_items,
                unique_seller_count=len(unique_sellers),
                metric_payload=latest_metadata,
            )
        )

        session.add(
            AnalysisReport(
                report_type=report_type,
                business_domain=task.business_domain,
                category_id=task.category_id,
                template_id=active_template_id_for_category(session, task.category_id),
                report_date=date.today(),
                title=f"{task.display_name} {report_type}",
                summary=(
                    f"Captured {total_items} items across {len(captures)} payload(s); "
                    f"tombstoned {recorded_rejection_count} garbage listings; "
                    f"blocked {suspicious_intake_summary['blocked_count']} suspicious listings before ingest; "
                    f"blocked {category_gate_summary['blocked_count']} category mismatches."
                ),
                payload={
                    "task_key": task.task_key,
                    "source_keyword": source_keyword,
                    "payload_count": len(captures),
                    "item_count": total_items,
                    "duplicate_item_count": duplicate_items,
                    "rejected_missing_price_count": rejected_missing_price_count,
                    "rejected_low_price_count": rejected_low_price_count,
                    "permanent_rejected_count": len(permanently_rejected_item_ids),
                    "touched_permanent_rejection_count": touched_permanent_rejection_count,
                    "ingest_rejection_recorded_count": recorded_rejection_count,
                    "skipped_snapshot_count": skipped_snapshot_count,
                    "price_reference": float(cleanup.price_reference) if cleanup.price_reference is not None else None,
                    "low_price_floor": float(cleanup.low_price_floor) if cleanup.low_price_floor is not None else None,
                    "title_length_gate_candidate_count": title_length_summary["candidate_count"],
                    "title_length_gate_blocked_count": title_length_summary["blocked_count"],
                    "title_length_gate_blocked_reasons": title_length_summary["blocked_reasons"],
                    "suspicious_keyword_candidate_count": suspicious_intake_summary["candidate_count"],
                    "suspicious_keyword_allowed_count": suspicious_intake_summary["valid_count"],
                    "suspicious_keyword_blocked_count": suspicious_intake_summary["blocked_count"],
                    "suspicious_keyword_blocked_reasons": suspicious_intake_summary["blocked_reasons"],
                    "category_gate_candidate_count": category_gate_summary["candidate_count"],
                    "category_gate_blocked_count": category_gate_summary["blocked_count"],
                    "category_gate_blocked_reasons": category_gate_summary["blocked_reasons"],
                    "raw_retained": raw_retained,
                    "metadata": latest_metadata,
                },
            )
        )


def is_retryable_persist_deadlock(exc: Exception) -> bool:
    queue: list[BaseException] = [exc]
    seen: set[int] = set()

    while queue:
        current = queue.pop(0)
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)

        message = str(current).lower()
        if "deadlock detected" in message or "could not serialize access" in message:
            return True

        if isinstance(current, DBAPIError) and current.orig is not None:
            queue.append(current.orig)

        cause = getattr(current, "__cause__", None)
        if cause is not None:
            queue.append(cause)

        context = getattr(current, "__context__", None)
        if context is not None:
            queue.append(context)

    return False


def upsert_browser_session_state(
    *,
    profile_key: str,
    profile_dir: Path,
    browser_channel: str,
    auth_state: str,
    login_required_at: datetime | None,
    authenticated_at: datetime | None,
    last_error: str | None,
) -> None:
    with session_scope() as session:
        stmt = insert(BrowserSession).values(
            profile_key=profile_key,
            profile_dir=str(profile_dir),
            browser_channel=browser_channel,
            auth_state=auth_state or "unknown",
            last_login_required_at=login_required_at,
            last_authenticated_at=authenticated_at,
            last_error=last_error,
            metadata_json={},
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[BrowserSession.profile_key],
            set_={
                "profile_dir": str(profile_dir),
                "browser_channel": browser_channel,
                "auth_state": auth_state or "unknown",
                "last_login_required_at": login_required_at,
                "last_authenticated_at": authenticated_at,
                "last_error": last_error,
            },
        )
        session.execute(stmt)


def cleanup_historical_data(
    *,
    dry_run: bool,
    prune_raw: bool,
    prune_snapshots: bool,
    max_passes: int = 1,
) -> dict[str, Any]:
    pass_limit = 1 if dry_run else max(max_passes, 1)
    passes: list[dict[str, Any]] = []
    totals = {
        "item_delete_count": 0,
        "snapshot_delete_count": 0,
        "spec_delete_count": 0,
        "raw_request_delete_count": 0,
        "raw_response_delete_count": 0,
    }

    for index in range(pass_limit):
        pass_summary = cleanup_historical_pass(
            dry_run=dry_run,
            prune_raw=prune_raw,
            prune_snapshots=prune_snapshots,
        )
        pass_summary["pass_index"] = index + 1
        passes.append(pass_summary)
        for key in totals:
            totals[key] += int(pass_summary.get(key, 0))

        if dry_run:
            break
        if (
            pass_summary["item_delete_count"] == 0
            and pass_summary["snapshot_delete_count"] == 0
            and pass_summary["spec_delete_count"] == 0
            and pass_summary["raw_request_delete_count"] == 0
            and pass_summary["raw_response_delete_count"] == 0
        ):
            break

    return {
        "dry_run": dry_run,
        "prune_raw": prune_raw,
        "prune_snapshots": prune_snapshots,
        "pass_count": len(passes),
        **totals,
        "passes": passes,
    }


def cleanup_historical_pass(*, dry_run: bool, prune_raw: bool, prune_snapshots: bool) -> dict[str, Any]:
    settings = get_settings()
    group_summaries: list[dict[str, Any]] = []

    with session_scope() as session:
        items = list(session.execute(select(Item).order_by(Item.business_domain, Item.source_keyword, Item.id)).scalars())
        grouped_items: dict[tuple[str, str], list[Item]] = defaultdict(list)
        for item in items:
            grouped_items[(item.business_domain, item.source_keyword or "")].append(item)

        delete_item_ids: set[int] = set()
        for (business_domain, source_keyword), group_items in grouped_items.items():
            valid_priced = [item for item in group_items if item.current_price is not None and item.current_price > 0]
            invalid_priced = [item for item in group_items if item.current_price is None or item.current_price <= 0]
            rejected_low_items: list[Item] = []
            price_reference: Decimal | None = None
            low_price_floor: Decimal | None = None

            if len(valid_priced) >= settings.low_price_filter_min_samples:
                numeric_prices = [float(item.current_price) for item in valid_priced if item.current_price is not None]
                mean_price = Decimal(str(round(statistics.mean(numeric_prices), 2)))
                median_price = Decimal(str(round(statistics.median(numeric_prices), 2)))
                price_reference = max(mean_price, median_price)
                low_price_floor = (price_reference * Decimal(str(settings.low_price_filter_ratio))).quantize(
                    Decimal("0.01")
                )
                rejected_low_items = [
                    item for item in valid_priced if item.current_price is not None and item.current_price < low_price_floor
                ]

            delete_item_ids.update(item.id for item in invalid_priced)
            delete_item_ids.update(item.id for item in rejected_low_items)
            group_summaries.append(
                {
                    "business_domain": business_domain,
                    "source_keyword": source_keyword,
                    "total_items": len(group_items),
                    "invalid_price_count": len(invalid_priced),
                    "rejected_low_price_count": len(rejected_low_items),
                    "kept_count": len(group_items) - len(invalid_priced) - len(rejected_low_items),
                    "price_reference": float(price_reference) if price_reference is not None else None,
                    "low_price_floor": float(low_price_floor) if low_price_floor is not None else None,
                }
            )

        duplicate_snapshot_ids: list[int] = []
        if prune_snapshots:
            snapshot_rows = session.execute(
                select(ItemSnapshot)
                .where(~ItemSnapshot.item_id_ref.in_(delete_item_ids) if delete_item_ids else literal(True))
                .order_by(ItemSnapshot.item_id_ref, ItemSnapshot.snapshot_at.desc(), ItemSnapshot.id.desc())
            ).scalars()
            seen_states: dict[int, set[tuple[Any, ...]]] = defaultdict(set)
            for snapshot in snapshot_rows:
                extra_json = snapshot.extra_json or {}
                signature = (
                    str(snapshot.price) if snapshot.price is not None else None,
                    snapshot.region,
                    tuple(snapshot.condition_tags or []),
                    snapshot.publish_time.isoformat() if snapshot.publish_time else None,
                    extra_json.get("source_keyword"),
                )
                if signature in seen_states[snapshot.item_id_ref]:
                    duplicate_snapshot_ids.append(snapshot.id)
                    continue
                seen_states[snapshot.item_id_ref].add(signature)

        raw_requests_count = session.execute(select(func.count()).select_from(RawRequest)).scalar_one()
        raw_responses_count = session.execute(select(func.count()).select_from(RawResponse)).scalar_one()
        snapshots_to_delete_for_items = (
            session.execute(
                select(func.count()).select_from(ItemSnapshot).where(ItemSnapshot.item_id_ref.in_(delete_item_ids))
            ).scalar_one()
            if delete_item_ids
            else 0
        )
        specs_to_delete = (
            session.execute(
                select(func.count()).select_from(ItemSpecEnrichment).where(ItemSpecEnrichment.item_id_ref.in_(delete_item_ids))
            ).scalar_one()
            if delete_item_ids
            else 0
        )

        summary = {
            "dry_run": dry_run,
            "prune_raw": prune_raw,
            "prune_snapshots": prune_snapshots,
            "item_delete_count": len(delete_item_ids),
            "snapshot_delete_count": int(snapshots_to_delete_for_items) + len(duplicate_snapshot_ids),
            "spec_delete_count": int(specs_to_delete),
            "raw_request_delete_count": int(raw_requests_count) if prune_raw else 0,
            "raw_response_delete_count": int(raw_responses_count) if prune_raw else 0,
            "groups": group_summaries,
        }

        if dry_run:
            session.rollback()
            return summary

        if delete_item_ids:
            session.execute(
                update(OutreachRecord)
                .where(OutreachRecord.item_id_ref.in_(delete_item_ids))
                .values(item_id_ref=None)
            )
            session.execute(delete(ItemSpecEnrichment).where(ItemSpecEnrichment.item_id_ref.in_(delete_item_ids)))
            session.execute(delete(ItemSnapshot).where(ItemSnapshot.item_id_ref.in_(delete_item_ids)))
            session.execute(delete(Item).where(Item.id.in_(delete_item_ids)))

        if duplicate_snapshot_ids:
            session.execute(delete(ItemSnapshot).where(ItemSnapshot.id.in_(duplicate_snapshot_ids)))

        if prune_raw:
            session.execute(
                update(Item)
                .where(Item.current_raw_response_id.is_not(None))
                .values(current_raw_response_id=None)
            )
            session.execute(
                update(ItemSnapshot)
                .where(ItemSnapshot.raw_response_id.is_not(None))
                .values(raw_response_id=None)
            )
            session.execute(delete(RawResponse))
            session.execute(delete(RawRequest))

        return summary


def upsert_seller(
    *,
    session,
    seller_id: str,
    seller_name: str | None,
    avatar_url: str | None,
    region: str | None,
) -> int:
    stmt = insert(SellerProfile).values(
        seller_id=seller_id,
        seller_name=seller_name,
        avatar_url=avatar_url,
        region=region,
        metadata_json={},
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[SellerProfile.seller_id],
        set_={"seller_name": seller_name, "avatar_url": avatar_url, "region": region},
    ).returning(SellerProfile.id)
    return session.execute(stmt).scalar_one()


def upsert_item(
    *,
    session,
    task: CrawlTask,
    task_query_id: int | None,
    raw_response_id: UUID | None,
    seller_profile_id: int | None,
    extracted: ExtractedItem,
    source_keyword: str,
    preserve_missing_fields: bool = False,
    category_context_override: ResolvedItemCategoryContext | None = None,
) -> int:
    now = datetime.now(UTC)
    existing = session.execute(select(Item).where(Item.item_id == extracted.item_id)).scalar_one_or_none()
    preserve_inactive_invalid = bool(
        existing is not None
        and existing.is_active is False
        and existing.llm_review_status == "invalid"
    )

    merged_task_id = task.id
    merged_task_query_id = task_query_id
    merged_seller_profile_id = seller_profile_id
    merged_raw_response_id = raw_response_id
    merged_source_keyword = source_keyword
    merged_xianyu_cat_id = extracted.cat_id
    merged_xianyu_tb_cat_id = extracted.tb_cat_id
    merged_xianyu_c_cat_id = extracted.c_cat_id
    merged_title = extracted.title
    merged_normalized_brand = extracted.normalized_brand
    merged_normalized_model_family = extracted.normalized_model_family
    merged_normalized_model = extracted.normalized_model
    merged_normalized_chip = extracted.normalized_chip
    merged_normalized_memory_gb = extracted.normalized_memory_gb
    merged_normalized_storage_gb = extracted.normalized_storage_gb
    merged_condition_tags = extracted.tags
    merged_region = extracted.area
    merged_listing_url = extracted.listing_url
    merged_image_urls = [extracted.pic_url] if extracted.pic_url else []
    merged_is_auction = extracted.is_auction
    merged_is_ad = extracted.is_ad
    merged_has_video = extracted.has_video
    merged_current_price = normalize_market_price(
        extracted.price,
        business_domain=task.business_domain,
        model_family=extracted.normalized_model_family,
    )
    merged_publish_time = extracted.publish_time

    if existing is not None and preserve_missing_fields:
        merged_task_id = existing.task_id
        merged_task_query_id = task_query_id or existing.task_query_id
        merged_seller_profile_id = seller_profile_id or existing.seller_profile_id
        merged_raw_response_id = raw_response_id or existing.current_raw_response_id
        merged_source_keyword = (
            existing.source_keyword
            if source_keyword == "home_feed" and existing.source_keyword
            else source_keyword
        )
        merged_xianyu_cat_id = extracted.cat_id or existing.xianyu_cat_id
        merged_xianyu_tb_cat_id = extracted.tb_cat_id or existing.xianyu_tb_cat_id
        merged_xianyu_c_cat_id = extracted.c_cat_id or existing.xianyu_c_cat_id
        merged_title = existing.title or extracted.title
        merged_normalized_brand = extracted.normalized_brand or existing.normalized_brand
        merged_normalized_model_family = extracted.normalized_model_family or existing.normalized_model_family
        merged_normalized_model = extracted.normalized_model or existing.normalized_model
        merged_normalized_chip = extracted.normalized_chip or existing.normalized_chip
        merged_normalized_memory_gb = extracted.normalized_memory_gb or existing.normalized_memory_gb
        merged_normalized_storage_gb = extracted.normalized_storage_gb or existing.normalized_storage_gb
        merged_condition_tags = extracted.tags or existing.condition_tags
        merged_region = extracted.area or existing.region
        merged_listing_url = extracted.listing_url or existing.listing_url
        merged_image_urls = ([extracted.pic_url] if extracted.pic_url else []) or (existing.image_urls or [])
        merged_is_auction = extracted.is_auction or existing.is_auction
        merged_is_ad = extracted.is_ad or existing.is_ad
        merged_has_video = extracted.has_video or existing.has_video
        merged_current_price = (
            normalize_market_price(
                extracted.price,
                business_domain=task.business_domain,
                model_family=extracted.normalized_model_family,
            )
            if extracted.price is not None
            else existing.current_price
        )
        merged_publish_time = extracted.publish_time or existing.publish_time

    should_reset_llm_review = should_reset_llm_review_state(
        existing=existing,
        title=merged_title,
        source_keyword=merged_source_keyword,
        current_price=merged_current_price,
        condition_tags=merged_condition_tags,
        region=merged_region,
        normalized_brand=merged_normalized_brand,
        normalized_model_family=merged_normalized_model_family,
        normalized_model=merged_normalized_model,
        normalized_chip=merged_normalized_chip,
        normalized_memory_gb=merged_normalized_memory_gb,
        normalized_storage_gb=merged_normalized_storage_gb,
    )
    review_reset_fields = (
        {
            "llm_reviewed": False,
            "llm_review_status": "pending",
            "llm_review_reason": None,
            "llm_reviewed_at": None,
            "llm_review_confidence": None,
            "llm_review_input": {},
            "llm_review_input_signature": None,
            "llm_review_needs_audit": False,
            "llm_review_audit_reason": None,
            "llm_review_decision": {},
        }
        if should_reset_llm_review
        else {}
    )

    category_context = category_context_override or resolve_item_category_context_with_session(
        session,
        task=task,
        xianyu_cat_id=merged_xianyu_cat_id,
        xianyu_tb_cat_id=merged_xianyu_tb_cat_id,
        xianyu_c_cat_id=merged_xianyu_c_cat_id,
        title=merged_title,
    )

    stmt = insert(Item).values(
        item_id=extracted.item_id,
        task_id=merged_task_id,
        task_query_id=merged_task_query_id,
        seller_profile_id=merged_seller_profile_id,
        current_raw_response_id=merged_raw_response_id,
        source_platform=task.source_platform,
        business_domain=category_context.resolved_business_domain or task.business_domain,
        target_category_id=category_context.target_category_id,
        resolved_category_id=category_context.resolved_category_id,
        resolved_template_id=category_context.resolved_template_id,
        category_validation_status=category_context.category_validation_status,
        category_validation_reason=category_context.category_validation_reason,
        category_validation_confidence=category_context.category_validation_confidence,
        source_keyword=merged_source_keyword,
        xianyu_cat_id=merged_xianyu_cat_id,
        xianyu_tb_cat_id=merged_xianyu_tb_cat_id,
        xianyu_c_cat_id=merged_xianyu_c_cat_id,
        title=merged_title,
        normalized_brand=merged_normalized_brand,
        normalized_model_family=merged_normalized_model_family,
        normalized_model=merged_normalized_model,
        normalized_chip=merged_normalized_chip,
        normalized_memory_gb=merged_normalized_memory_gb,
        normalized_storage_gb=merged_normalized_storage_gb,
        condition_tags=merged_condition_tags,
        region=merged_region,
        listing_url=merged_listing_url,
        image_urls=merged_image_urls,
        is_auction=merged_is_auction,
        is_ad=merged_is_ad,
        has_video=merged_has_video,
        current_price=merged_current_price,
        publish_time=merged_publish_time,
        last_snapshot_at=now,
        last_seen_at=now,
        is_active=not preserve_inactive_invalid,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Item.item_id],
        set_={
            "task_id": merged_task_id,
            "task_query_id": merged_task_query_id,
            "seller_profile_id": merged_seller_profile_id,
            "current_raw_response_id": merged_raw_response_id,
            "source_platform": task.source_platform,
            "business_domain": category_context.resolved_business_domain or task.business_domain,
            "target_category_id": category_context.target_category_id,
            "resolved_category_id": category_context.resolved_category_id,
            "resolved_template_id": category_context.resolved_template_id,
            "category_validation_status": category_context.category_validation_status,
            "category_validation_reason": category_context.category_validation_reason,
            "category_validation_confidence": category_context.category_validation_confidence,
            "source_keyword": merged_source_keyword,
            "xianyu_cat_id": merged_xianyu_cat_id,
            "xianyu_tb_cat_id": merged_xianyu_tb_cat_id,
            "xianyu_c_cat_id": merged_xianyu_c_cat_id,
            "title": merged_title,
            "normalized_brand": merged_normalized_brand,
            "normalized_model_family": merged_normalized_model_family,
            "normalized_model": merged_normalized_model,
            "normalized_chip": merged_normalized_chip,
            "normalized_memory_gb": merged_normalized_memory_gb,
            "normalized_storage_gb": merged_normalized_storage_gb,
            "condition_tags": merged_condition_tags,
            "region": merged_region,
            "listing_url": merged_listing_url,
            "image_urls": merged_image_urls,
            "is_auction": merged_is_auction,
            "is_ad": merged_is_ad,
            "has_video": merged_has_video,
            "current_price": merged_current_price,
            "publish_time": merged_publish_time,
            "last_seen_at": now,
            "is_active": not preserve_inactive_invalid,
            **review_reset_fields,
        },
    ).returning(Item.id)
    return session.execute(stmt).scalar_one()


def should_reset_llm_review_state(
    *,
    existing: Item | None,
    title: str,
    source_keyword: str | None,
    current_price: Decimal | None,
    condition_tags: list[str],
    region: str | None,
    normalized_brand: str | None,
    normalized_model_family: str | None,
    normalized_model: str | None,
    normalized_chip: str | None,
    normalized_memory_gb: int | None,
    normalized_storage_gb: int | None,
) -> bool:
    if existing is None or not existing.llm_reviewed:
        return False
    if existing.llm_review_status not in {"valid", "pending_audit"}:
        return False

    existing_signature = (
        existing.title,
        existing.source_keyword,
        existing.current_price,
        tuple(existing.condition_tags or []),
        existing.region,
        existing.normalized_brand,
        existing.normalized_model_family,
        existing.normalized_model,
        existing.normalized_chip,
        existing.normalized_memory_gb,
        existing.normalized_storage_gb,
    )
    merged_signature = (
        title,
        source_keyword,
        current_price,
        tuple(condition_tags or []),
        region,
        normalized_brand,
        normalized_model_family,
        normalized_model,
        normalized_chip,
        normalized_memory_gb,
        normalized_storage_gb,
    )
    return existing_signature != merged_signature


def run_home_feed_refresh(
    *,
    cdp_url: str,
    profile_key: str,
    business_domain: str | None,
    max_cards: int,
    max_messages: int,
    min_message_interval_seconds: int,
    freshness_days: int,
    min_sample_points: int,
    message_text: str,
    dry_run: bool,
    require_actionable_band: bool,
    only_within_target_price: bool,
    min_profit_margin_pct: Decimal,
) -> dict[str, Any]:
    guard_scope_key = str(business_domain or "").strip() or None
    attempt_metadata = {
        "business_domain": business_domain,
        "max_cards": max_cards,
        "max_messages": max_messages,
        "dry_run": dry_run,
        "require_actionable_band": require_actionable_band,
        "only_within_target_price": only_within_target_price,
    }
    tasks_by_domain = load_active_tasks_by_domain(business_domain=business_domain)
    if not tasks_by_domain:
        persist_browser_job_attempt(
            profile_key=profile_key,
            feature="home_feed",
            stage="preflight",
            scope_key=guard_scope_key,
            business_domain=business_domain,
            attempt_outcome="failed",
            error_message="No active crawl task found for the requested category scope.",
            metadata=attempt_metadata,
        )
        raise RuntimeError("No active crawl task found for the requested category scope.")

    pricing_views = build_pricing_views(
        business_domain=business_domain,
        freshness_days=freshness_days,
        min_sample_points=min_sample_points,
    )
    pricing_index = build_feed_pricing_index(
        views=pricing_views,
        tasks_by_domain=tasks_by_domain,
    )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            if not browser.contexts:
                raise RuntimeError(f"No context found on attached browser: {cdp_url}")
            context = browser.contexts[0]
            home_page, reused_existing_home_tab = prepare_home_feed_page(context=context)
            cards, tab_switch, feed_capture_meta = extract_home_feed_cards(home_page, max_cards=max_cards)
            summary = process_home_feed_cards(
                context=context,
                cards=cards,
                tasks_by_domain=tasks_by_domain,
                pricing_index=pricing_index,
                business_domain=business_domain,
                max_messages=max_messages,
                min_message_interval_seconds=min_message_interval_seconds,
                message_text=message_text,
                dry_run=dry_run,
                require_actionable_band=require_actionable_band,
                only_within_target_price=only_within_target_price,
                min_profit_margin_pct=min_profit_margin_pct,
                freshness_days=freshness_days,
            )
            summary["profile_key"] = profile_key
            summary["cdp_url"] = cdp_url
            summary["reused_existing_home_tab"] = reused_existing_home_tab
            summary["home_tab_switch"] = tab_switch
            summary.update(feed_capture_meta)
    except Exception as exc:
        guard_decision = record_browser_guard_observation(
            profile_key=profile_key,
            feature="home_feed",
            scope_key=guard_scope_key,
            error_message=str(exc),
        )
        persist_browser_job_attempt(
            profile_key=profile_key,
            feature="home_feed",
            scope_key=guard_scope_key,
            business_domain=business_domain,
            attempt_outcome=str((guard_decision or {}).get("auth_state") or "failed"),
            auth_state=(guard_decision or {}).get("auth_state"),
            error_message=str(exc),
            metadata={
                **attempt_metadata,
                "browser_guard": guard_decision,
            },
        )
        if guard_decision:
            setattr(exc, "browser_guard_decision", guard_decision)
        raise

    if int(summary.get("risk_control_hit_count") or 0) > 0:
        summary["browser_guard"] = record_browser_guard_observation(
            profile_key=profile_key,
            feature="home_feed",
            scope_key=guard_scope_key,
            auth_state="risk_control",
            error_message=summary.get("risk_control_error"),
        )
        persist_browser_job_attempt(
            profile_key=profile_key,
            feature="home_feed",
            scope_key=guard_scope_key,
            business_domain=business_domain,
            attempt_outcome="risk_control",
            auth_state="risk_control",
            error_message=str(summary.get("risk_control_error") or "").strip() or None,
            metadata={
                **attempt_metadata,
                "cards_seen": summary.get("cards_seen"),
                "detail_opened_count": summary.get("detail_opened_count"),
                "message_sent_count": summary.get("message_sent_count"),
                "risk_control_hit_count": summary.get("risk_control_hit_count"),
                "browser_guard": summary.get("browser_guard"),
            },
        )
    else:
        summary["browser_guard"] = record_browser_guard_observation(
            profile_key=profile_key,
            feature="home_feed",
            scope_key=guard_scope_key,
            auth_state="authenticated",
        )
        persist_browser_job_attempt(
            profile_key=profile_key,
            feature="home_feed",
            scope_key=guard_scope_key,
            business_domain=business_domain,
            attempt_outcome="completed",
            auth_state="authenticated",
            metadata={
                **attempt_metadata,
                "cards_seen": summary.get("cards_seen"),
                "detail_opened_count": summary.get("detail_opened_count"),
                "message_sent_count": summary.get("message_sent_count"),
                "risk_control_hit_count": summary.get("risk_control_hit_count"),
                "browser_guard": summary.get("browser_guard"),
            },
        )
    return summary


def build_home_feed_manual_verification_message(*, stage: str, signal: str | None) -> str:
    resolved_signal = str(signal or "").strip() or "unknown"
    return f"Home feed {stage} hit risk control: {resolved_signal}"


def detect_home_feed_manual_verification_signal(page) -> str | None:
    signal = detect_page_risk_control_signal_from_page(page)
    if signal:
        return signal

    try:
        page_url = str(getattr(page, "url", "") or "").strip()
    except Exception:
        page_url = ""
    lowered_url = page_url.lower()
    if any(marker in lowered_url for marker in ("executecaptcha", "baxia", "nocaptcha", "punish")):
        return f"url:{page_url}"
    return None


def raise_if_home_feed_manual_verification(page, *, stage: str) -> None:
    signal = detect_home_feed_manual_verification_signal(page)
    if signal:
        raise RuntimeError(build_home_feed_manual_verification_message(stage=stage, signal=signal))


def build_home_feed_capture_failure_message(*, auth_state: str | None, last_error: str | None) -> str | None:
    if auth_state == "risk_control":
        return f"Home feed capture blocked by risk control: {last_error or 'unknown'}"
    if auth_state == "login_required":
        return f"Home feed capture blocked by login requirement: {last_error or 'unknown'}"
    return None


def prepare_home_feed_page(*, context) -> tuple[Any, bool]:
    home_page = find_existing_home_feed_page(context=context)
    reused_existing_home_tab = home_page is not None

    if home_page is None:
        home_page = context.new_page()
    return home_page, reused_existing_home_tab


def next_home_feed_tab_label() -> str:
    if HOME_FEED_LAST_SELECTED_TAB == HOME_FEED_TAB_SEQUENCE[0]:
        return HOME_FEED_TAB_SEQUENCE[1]
    return HOME_FEED_TAB_SEQUENCE[0]


def switch_home_feed_primary_tab(*, home_page) -> dict[str, Any]:
    global HOME_FEED_LAST_SELECTED_TAB

    preferred_label = next_home_feed_tab_label()
    fallback_label = (
        HOME_FEED_TAB_SEQUENCE[0]
        if preferred_label == HOME_FEED_TAB_SEQUENCE[1]
        else HOME_FEED_TAB_SEQUENCE[1]
    )
    result = home_page.evaluate(
        """
({ preferredLabel, fallbackLabel, labels }) => {
  const normalize = (text) => (text || '').replace(/\\s+/g, '').trim();
  const isVisible = (node) => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 20 && rect.height > 12 && rect.bottom >= 0 && rect.top <= window.innerHeight;
  };
  const isActive = (node) => {
    if (!node) return false;
    const probes = [node, node.parentElement, node.closest('[role=\"tab\"],button,a,div,span')];
    for (const probe of probes) {
      if (!probe) continue;
      const ariaSelected = (probe.getAttribute('aria-selected') || '').toLowerCase();
      if (ariaSelected === 'true') return true;
      const className = ((probe.className || '') + '').toLowerCase();
      if (className.includes('active') || className.includes('selected') || className.includes('current')) {
        return true;
      }
    }
    return false;
  };

  const candidates = new Map();
  const nodes = Array.from(document.querySelectorAll('button,a,div,span,[role=\"tab\"],[role=\"button\"]'));
  for (const node of nodes) {
    const text = normalize(node.textContent);
    if (!labels.includes(text)) continue;
    const clickable = node.closest('[role=\"tab\"],button,a,[role=\"button\"]') || node;
    if (!isVisible(clickable)) continue;
    const top = clickable.getBoundingClientRect().top;
    const existing = candidates.get(text);
    if (!existing || top < existing.top) {
      candidates.set(text, { target: clickable, top });
    }
  }

  const available = Array.from(candidates.keys());
  const activeLabel = available.find((label) => isActive(candidates.get(label)?.target)) || null;
  const targetLabel = candidates.has(preferredLabel)
    ? preferredLabel
    : (candidates.has(fallbackLabel) ? fallbackLabel : null);

  let clicked = false;
  let clickedLabel = null;
  if (targetLabel) {
    const target = candidates.get(targetLabel)?.target;
    if (target) {
      target.click();
      clicked = true;
      clickedLabel = targetLabel;
    }
  }

  return { preferredLabel, fallbackLabel, available, activeLabel, clicked, clickedLabel };
}
""",
        {
            "preferredLabel": preferred_label,
            "fallbackLabel": fallback_label,
            "labels": list(HOME_FEED_TAB_SEQUENCE),
        },
    )

    clicked_label = result.get("clickedLabel")
    active_label = result.get("activeLabel")
    if isinstance(clicked_label, str) and clicked_label:
        HOME_FEED_LAST_SELECTED_TAB = clicked_label
    elif isinstance(active_label, str) and active_label:
        HOME_FEED_LAST_SELECTED_TAB = active_label

    result["dwell_seconds"] = HOME_FEED_TAB_DWELL_MS // 1000
    result["last_selected_label"] = HOME_FEED_LAST_SELECTED_TAB
    return result


def find_existing_home_feed_page(*, context) -> Any | None:
    for page in reversed(context.pages):
        try:
            if page.is_closed():
                continue
            if is_goofish_home_feed_url(page.url):
                return page
        except Exception:
            continue
    return None


def is_goofish_home_feed_url(url: str | None) -> bool:
    if not url:
        return False

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if "goofish.com" not in host:
        return False

    path = (parsed.path or "/").rstrip("/") or "/"
    return path == "/"


def _task_preference_score(task: CrawlTask) -> tuple[int, int, int, int, int, int, int]:
    normalized_scope = resolve_category_code(task.business_domain)
    signal_count = (
        len(task.keywords or [])
        + len(task.brand_lexicon or [])
        + len(task.model_lexicon or [])
        + len(task.config_lexicon or [])
    )
    task_key = str(getattr(task, "task_key", "") or "").strip().lower()
    display_name = str(getattr(task, "display_name", "") or "").strip().lower()
    smoke_penalty = 0 if task_key.startswith("smoke-") or "smoke" in display_name else 1
    production_bonus = 1 if str(getattr(task, "task_type", "") or "").strip().upper() == "PRODUCTION" else 0
    source_bonus = 1 if str(getattr(task, "source_platform", "") or "").strip().lower() == "xianyu" else 0
    normalized_scope = resolve_category_code(task.business_domain)
    return (
        source_bonus,
        production_bonus,
        smoke_penalty,
        1 if task.category_id else 0,
        1 if task.business_domain == normalized_scope else 0,
        signal_count,
        int(task.id or 0),
    )


def load_active_tasks_by_domain(*, business_domain: str | None) -> dict[str, CrawlTask]:
    with session_scope() as session:
        stmt = (
            select(CrawlTask)
            .where(CrawlTask.status == "active")
            .where(CrawlTask.source_platform == "xianyu")
            .order_by(CrawlTask.id.asc())
        )
        scope_keys = compatible_scope_keys(business_domain)
        if scope_keys:
            stmt = stmt.where(CrawlTask.business_domain.in_(scope_keys))
        tasks = list(session.execute(stmt).scalars())

    selected: dict[str, CrawlTask] = {}
    for task in tasks:
        scope = resolve_category_code(task.business_domain) or task.business_domain
        if not is_analytics_scope(scope):
            continue
        existing = selected.get(scope)
        if existing is None or _task_preference_score(task) > _task_preference_score(existing):
            selected[scope] = task
    return selected


def build_feed_pricing_index(
    *,
    views: dict[str, list[dict[str, Any]]],
    tasks_by_domain: dict[str, CrawlTask],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    index: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for view_name in ("spec", "product"):
        for row in views.get(view_name, []):
            domain = row["business_domain"]
            if domain not in tasks_by_domain:
                continue
            domain_index = index.setdefault(domain, {"spec": {}, "product": {}})
            domain_index[view_name].setdefault(row["label"], row)
    return index


def extract_home_feed_cards(page, *, max_cards: int) -> tuple[list[FeedCardCandidate], dict[str, Any], dict[str, Any]]:
    captured_payloads: list[dict[str, Any]] = []
    reload_attempted = False
    auth_state = "unknown"
    last_error: str | None = None

    def on_response(response: Response) -> None:
        nonlocal auth_state, last_error
        if HOME_FEED_API_PATH not in response.url:
            return
        try:
            payload = response.json()
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        payload_status = classify_payload_status(payload)
        if payload_status == "login_required":
            auth_state = "login_required"
            last_error = extract_payload_error(payload)
            return
        if payload_status == "risk_control":
            auth_state = "risk_control"
            last_error = extract_payload_error(payload)
            return
        captured_payloads.append(payload)

    page.on("response", on_response)
    try:
        if not is_goofish_home_feed_url(page.url):
            page.goto("https://www.goofish.com/", wait_until="domcontentloaded", timeout=60000)
        tab_switch = switch_home_feed_primary_tab(home_page=page)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(HOME_FEED_TAB_DWELL_MS)
        raise_if_home_feed_manual_verification(page, stage="page")
        if not captured_payloads:
            reload_attempted = True
            page.reload(wait_until="domcontentloaded", timeout=60000)
            tab_switch = switch_home_feed_primary_tab(home_page=page)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(HOME_FEED_TAB_DWELL_MS)
            raise_if_home_feed_manual_verification(page, stage="page")
    finally:
        page.remove_listener("response", on_response)

    capture_failure = build_home_feed_capture_failure_message(auth_state=auth_state, last_error=last_error)
    if capture_failure and not captured_payloads:
        raise RuntimeError(capture_failure)

    api_cards = extract_home_feed_cards_from_api_payloads(captured_payloads, max_cards=max_cards)
    if api_cards:
        return api_cards, tab_switch, {
            "feed_capture_source": "api",
            "api_reload_attempted": reload_attempted,
            "api_response_count": len(captured_payloads),
            "api_card_count": len(api_cards),
            "candidate_card_count": len(api_cards),
        }

    dom_cards = extract_home_feed_cards_from_dom(page, max_cards=max_cards)
    if dom_cards:
        return dom_cards, tab_switch, {
            "feed_capture_source": "dom",
            "api_reload_attempted": reload_attempted,
            "api_response_count": len(captured_payloads),
            "api_card_count": 0,
            "candidate_card_count": len(dom_cards),
        }

    manual_verification_signal = detect_home_feed_manual_verification_signal(page)
    if manual_verification_signal:
        raise RuntimeError(build_home_feed_manual_verification_message(stage="page", signal=manual_verification_signal))
    if capture_failure:
        raise RuntimeError(capture_failure)
    return dom_cards, tab_switch, {
        "feed_capture_source": "dom",
        "api_reload_attempted": reload_attempted,
        "api_response_count": len(captured_payloads),
        "api_card_count": 0,
        "candidate_card_count": len(dom_cards),
    }


def extract_home_feed_cards_from_api_payloads(
    payloads: list[dict[str, Any]],
    *,
    max_cards: int,
) -> list[FeedCardCandidate]:
    cards: list[FeedCardCandidate] = []
    seen_item_ids: set[str] = set()
    for payload in payloads:
        for card in parse_home_feed_api_payload(payload):
            if card.item_id in seen_item_ids:
                continue
            seen_item_ids.add(card.item_id)
            cards.append(card)
            if len(cards) >= max_cards:
                return cards
    return cards


def parse_home_feed_api_payload(payload: dict[str, Any]) -> list[FeedCardCandidate]:
    data = payload.get("data") or {}
    rows = data.get("cardList") or []
    cards: list[FeedCardCandidate] = []
    for index, row in enumerate(rows, start=1):
        card = build_feed_card_candidate_from_api_row(row, position=index)
        if card is not None:
            cards.append(card)
    return cards


def build_feed_card_candidate_from_api_row(
    row: dict[str, Any],
    *,
    position: int,
) -> FeedCardCandidate | None:
    card_data = dict(row.get("cardData") or {})
    detail_params = dict(card_data.get("detailParams") or {})
    attribute_map = dict(card_data.get("attributeMap") or {})
    dislike_params = dict(card_data.get("dislikeTrackParams") or {})
    item_id = str(
        detail_params.get("itemId")
        or dislike_params.get("item_id")
        or dislike_params.get("id")
        or ""
    ).strip()
    if not item_id:
        return None

    category_id = str(
        card_data.get("categoryId")
        or attribute_map.get("catId")
        or ""
    ).strip() or None
    tb_cat_id = str(attribute_map.get("tbCatId") or "").strip() or None
    c_cat_id = str(attribute_map.get("cCatId") or "").strip() or None
    title = str(detail_params.get("title") or "").strip()
    if not title:
        return None

    tag_texts = extract_feed_api_tag_texts(card_data.get("fishTags") or {})
    hot_point_text = str((card_data.get("hotPoint") or {}).get("text") or "").strip()
    raw_text = " ".join(
        part
        for part in (
            title,
            hot_point_text,
            *tag_texts,
        )
        if str(part).strip()
    ).strip() or title

    price = parse_feed_price_value(
        detail_params.get("soldPrice")
        or attribute_map.get("firstPrice")
        or attribute_map.get("soldPrice")
    )

    return FeedCardCandidate(
        item_id=item_id,
        category_id=category_id,
        tb_cat_id=tb_cat_id,
        c_cat_id=c_cat_id,
        listing_url=build_feed_detail_url(item_id=item_id, category_id=category_id),
        title=title,
        raw_text=raw_text,
        price=price,
        position=position,
    )


def extract_feed_api_tag_texts(fish_tags: dict[str, Any]) -> tuple[str, ...]:
    texts: list[str] = []
    for slot in fish_tags.values():
        if not isinstance(slot, dict):
            continue
        for tag in slot.get("tagList") or []:
            if not isinstance(tag, dict):
                continue
            content = str((tag.get("data") or {}).get("content") or "").strip()
            if content:
                texts.append(content)
    deduped: list[str] = []
    for text in texts:
        if text not in deduped:
            deduped.append(text)
    return tuple(deduped)


def parse_feed_price_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    return Decimal(match.group(1)).quantize(Decimal("0.01"))


def extract_home_feed_cards_from_dom(page, *, max_cards: int) -> list[FeedCardCandidate]:
    raw_rows = page.evaluate(
        """
(maxCards) => {
  const textValue = (node) => ((node && node.textContent) || '').replace(/\\s+/g, ' ').trim();
  const collectRows = (selector) => Array.from(document.querySelectorAll(selector))
    .filter((node) => {
      const href = node.href || node.getAttribute('href') || '';
      if (!href.includes('/item?id=')) return false;
      const rect = node.getBoundingClientRect();
      return rect.width > 120 && rect.height > 80 && rect.top < window.innerHeight + 40 && rect.bottom > 120;
    })
    .map((node) => {
      const url = new URL(node.href || node.getAttribute('href'), location.href);
      const rect = node.getBoundingClientRect();
      const titleNode = node.querySelector("[class*='row1-wrap-title--'], [class*='main-title--']");
      const priceNode = node.querySelector("[class*='row3-wrap-price--'], [class*='price-wrap--']");
      return {
        item_id: url.searchParams.get('id'),
        category_id: url.searchParams.get('categoryId'),
        listing_url: url.toString(),
        raw_text: textValue(node),
        title_text: textValue(titleNode),
        price_text: textValue(priceNode),
        top: rect.top,
        left: rect.left,
      };
    });

  let rows = collectRows("a[class*='feeds-item-wrap--']");
  if (!rows.length) {
    rows = collectRows("a[href*='/item?id=']");
  }

  rows.sort((left, right) => {
    if (left.top === right.top) return left.left - right.left;
    return left.top - right.top;
  });

  const seen = new Set();
  const output = [];
  for (const row of rows) {
    if (!row.item_id || seen.has(row.item_id)) continue;
    seen.add(row.item_id);
    output.push(row);
    if (output.length >= maxCards) break;
  }
  return output;
}
""",
        max_cards,
    )

    cards: list[FeedCardCandidate] = []
    for index, row in enumerate(raw_rows, start=1):
        raw_text = str(row.get("raw_text") or "").strip()
        if not raw_text:
            continue
        cards.append(
            FeedCardCandidate(
                item_id=str(row["item_id"]),
                category_id=str(row.get("category_id") or "").strip() or None,
                tb_cat_id=None,
                c_cat_id=None,
                listing_url=str(row.get("listing_url") or "").strip() or None,
                title=derive_feed_card_title(str(row.get("title_text") or raw_text)),
                raw_text=raw_text,
                price=parse_feed_price(str(row.get("price_text") or raw_text)),
                position=index,
            )
        )
    return cards


def derive_feed_card_title(raw_text: str) -> str:
    text = re.sub(r"\s+", " ", raw_text).strip()
    price_match = re.search(r"[¥￥]\s*\d+(?:\.\d+)?(?:万)?", text, re.IGNORECASE)
    title = text[: price_match.start()] if price_match else text
    title = re.sub(r"\d+\s*(?:分钟|小时|天)(?:内发布|前来过|前)", "", title, flags=re.IGNORECASE)
    title = re.sub(r"来闲鱼\d+年.*$", "", title, flags=re.IGNORECASE)
    return title.strip(" -|/") or text[:128]


def parse_feed_price(raw_text: str) -> Decimal | None:
    match = re.search(r"[¥￥]\s*(\d+(?:\.\d+)?)(万)?", raw_text, re.IGNORECASE)
    if not match:
        return None
    value = Decimal(match.group(1))
    if match.group(2):
        value *= Decimal("10000")
    return value.quantize(Decimal("0.01"))


def process_home_feed_cards(
    *,
    context,
    cards: list[FeedCardCandidate],
    tasks_by_domain: dict[str, CrawlTask],
    pricing_index: dict[str, dict[str, dict[str, dict[str, Any]]]],
    business_domain: str | None,
    max_messages: int,
    min_message_interval_seconds: int,
    message_text: str,
    dry_run: bool,
    require_actionable_band: bool,
    only_within_target_price: bool,
    min_profit_margin_pct: Decimal,
    freshness_days: int,
) -> dict[str, Any]:
    item_ids = [card.item_id for card in cards]
    summary_rows: list[dict[str, Any]] = []
    message_sent_count = 0
    price_changed_count = 0
    snapshot_inserted_count = 0
    updated_item_count = 0
    local_entry_count = 0
    local_enrichment_count = 0
    local_enrichment_unresolved_count = 0
    target_match_count = 0
    skipped_existing_outreach_count = 0
    skipped_non_target_count = 0
    skipped_unmapped_category_count = 0
    skipped_missing_domain_task_count = 0
    skipped_outside_collection_scope_count = 0
    skipped_commercial_seller_count = 0
    skipped_unknown_seller_count = 0
    skipped_suspicious_intake_count = 0
    skipped_pre_ingest_template_count = 0
    skipped_ingest_rejection_count = 0
    skipped_low_profit_margin_count = 0
    skipped_message_cap_count = 0
    risk_control_hit_count = 0
    risk_control_blocked_count = 0
    risk_control_error: str | None = None
    risk_control_active = False
    touched_permanent_rejection_count = 0
    recorded_ingest_rejection_count = 0
    feed_source_platform = next(
        (task.source_platform for task in tasks_by_domain.values() if task.source_platform),
        "xianyu",
    )

    with session_scope() as session:
        existing_items = load_existing_items_map(session=session, item_ids=item_ids)
        seller_profiles = load_seller_profiles_map(
            session=session,
            seller_profile_ids=[
                item.seller_profile_id
                for item in existing_items.values()
                if item.seller_profile_id is not None
            ],
        )
        outreach_status = load_outreach_status_map(session=session, item_ids=item_ids)
        ingest_rejection_item_ids = load_ingest_rejection_item_ids_with_session(
            session=session,
            source_platform=feed_source_platform,
            item_ids=item_ids,
        )
        touched_permanent_rejection_count = touch_item_ingest_rejections(
            session=session,
            source_platform=feed_source_platform,
            item_ids=list(ingest_rejection_item_ids),
        )

        for card in cards:
            existing_item = existing_items.get(card.item_id)
            is_existing_item = existing_item is not None
            current_outreach_status = outreach_status.get(card.item_id)
            mapped_domain = (
                resolve_category_code(getattr(existing_item, "business_domain", None))
                or getattr(existing_item, "business_domain", None)
                if existing_item is not None
                else None
            )
            category_selection = None
            needs_category_selection = (not is_existing_item) or not mapped_domain
            if card.item_id in ingest_rejection_item_ids:
                persist_home_feed_item_decision(
                    session=session,
                    item_id=card.item_id,
                    item_id_ref=int(existing_item.id) if existing_item is not None and existing_item.id is not None else None,
                    source_platform=feed_source_platform,
                    decision_stage="entry_gate",
                    decision_status="skipped_ingest_rejected",
                    current_outreach_status=current_outreach_status,
                    category_context=build_category_context_from_item(existing_item),
                    extra_payload={"reason": "permanent_rejection"},
                )
                skipped_ingest_rejection_count += 1
                summary_rows.append(
                    {
                        "item_id": card.item_id,
                        "title": card.title,
                        "price": decimal_to_float(card.price),
                        "status": "skipped_ingest_rejected",
                        "reason": "permanent_rejection",
                    }
                )
                continue

            if current_outreach_status in {"sent", "sending"}:
                persist_home_feed_item_decision(
                    session=session,
                    item_id=card.item_id,
                    item_id_ref=int(existing_item.id) if existing_item is not None and existing_item.id is not None else None,
                    source_platform=feed_source_platform,
                    decision_stage="outreach_gate",
                    decision_status="existing_outreach",
                    current_outreach_status=current_outreach_status,
                    category_context=build_category_context_from_item(existing_item),
                    extra_payload={"messageStatus": current_outreach_status},
                )
                skipped_existing_outreach_count += 1
                summary_rows.append(
                    {
                        "item_id": card.item_id,
                        "title": card.title,
                        "price": decimal_to_float(card.price),
                        "status": "existing_outreach",
                        "message_status": current_outreach_status,
                        "business_domain": mapped_domain,
                    }
                )
                continue

            if needs_category_selection:
                category_selection = resolve_feed_category_selection_with_session(
                    session,
                    title=card.title,
                    raw_text=card.raw_text,
                    price=card.price,
                    xianyu_cat_id=card.category_id,
                    xianyu_tb_cat_id=card.tb_cat_id,
                    xianyu_c_cat_id=card.c_cat_id,
                    tasks_by_domain=tasks_by_domain,
                )
                mapped_domain = category_selection.resolved_business_domain
                if not category_selection.is_target_pool:
                    persist_home_feed_item_decision(
                        session=session,
                        item_id=card.item_id,
                        item_id_ref=int(existing_item.id) if existing_item is not None and existing_item.id is not None else None,
                        source_platform=feed_source_platform,
                        decision_stage="category_gate",
                        decision_status="skipped_non_target_pool",
                        current_outreach_status=current_outreach_status,
                        category_selection=category_selection,
                    )
                    skipped_unmapped_category_count += 1
                    summary_rows.append(
                        {
                            "item_id": card.item_id,
                            "title": card.title,
                            "price": decimal_to_float(card.price),
                            "status": "skipped_non_target_pool",
                            "reason": category_selection.decision_reason,
                            "candidate_business_domains": list(category_selection.candidate_business_domains),
                        }
                    )
                    continue
                if mapped_domain is None:
                    persist_home_feed_item_decision(
                        session=session,
                        item_id=card.item_id,
                        item_id_ref=int(existing_item.id) if existing_item is not None and existing_item.id is not None else None,
                        source_platform=feed_source_platform,
                        decision_stage="category_gate",
                        decision_status="skipped_category_unresolved",
                        current_outreach_status=current_outreach_status,
                        category_selection=category_selection,
                    )
                    skipped_missing_domain_task_count += 1
                    summary_rows.append(
                        {
                            "item_id": card.item_id,
                            "title": card.title,
                            "price": decimal_to_float(card.price),
                            "status": "skipped_category_unresolved",
                            "reason": category_selection.decision_reason,
                            "candidate_business_domains": list(category_selection.candidate_business_domains),
                            "active_candidate_business_domains": list(
                                category_selection.active_candidate_business_domains
                            ),
                            "category_decision_source": category_selection.decision_source,
                        }
                    )
                    continue

            match = match_home_feed_target(
                card=card,
                existing_item=existing_item,
                tasks_by_domain=tasks_by_domain,
                pricing_index=pricing_index,
                business_domain=business_domain,
                require_actionable_band=require_actionable_band,
                mapped_domain=mapped_domain,
            )
            if match is not None:
                target_match_count += 1

            chosen_task = resolve_feed_task(
                session=session,
                existing_item=existing_item,
                match=match,
                tasks_by_domain=tasks_by_domain,
                mapped_domain=mapped_domain,
            )
            collection_scope_domain = resolve_feed_collection_scope_domain(
                mapped_domain=mapped_domain,
                tasks_by_domain=tasks_by_domain,
            )
            within_collection_scope = should_open_feed_detail_for_task(
                mapped_domain=collection_scope_domain,
                task=chosen_task,
                tasks_by_domain=tasks_by_domain,
            )
            detail_eligible = should_open_feed_detail_for_match(
                mapped_domain=collection_scope_domain,
                task=chosen_task,
                match=match,
                tasks_by_domain=tasks_by_domain,
            )
            if chosen_task is None:
                if mapped_domain is not None:
                    skipped_missing_domain_task_count += 1
                    skipped_status = "skipped_missing_domain_task"
                else:
                    skipped_non_target_count += 1
                    skipped_status = "skipped_non_target"
                persist_home_feed_item_decision(
                    session=session,
                    item_id=card.item_id,
                    item_id_ref=int(existing_item.id) if existing_item is not None and existing_item.id is not None else None,
                    source_platform=feed_source_platform,
                    decision_stage="task_resolution",
                    decision_status=skipped_status,
                    current_outreach_status=current_outreach_status,
                    category_selection=category_selection,
                    extra_payload={"mappedBusinessDomain": mapped_domain},
                )
                summary_rows.append(
                    {
                        "item_id": card.item_id,
                        "title": card.title,
                        "price": decimal_to_float(card.price),
                        "mapped_business_domain": mapped_domain,
                        "status": skipped_status,
                    }
                )
                continue

            extracted = build_feed_extracted_item(card=card)
            gate_stage, gate_reason = classify_ingest_block_reason(
                task=chosen_task,
                source_keyword="home_feed",
                extracted=extracted,
            )
            if gate_reason is not None:
                upsert_item_ingest_rejection(
                    session=session,
                    source_platform=chosen_task.source_platform,
                    item_id=extracted.item_id,
                    business_domain=chosen_task.business_domain,
                    category_id=chosen_task.category_id,
                    rejection_stage=f"feed_{gate_stage or 'ingest_gate'}",
                    rejection_reason=gate_reason,
                )
                persist_home_feed_item_decision(
                    session=session,
                    item_id=extracted.item_id,
                    item_id_ref=int(existing_item.id) if existing_item is not None and existing_item.id is not None else None,
                    source_platform=chosen_task.source_platform,
                    decision_stage="ingest_gate",
                    decision_status="skipped_ingest_rejected",
                    current_outreach_status=current_outreach_status,
                    category_selection=category_selection,
                    extra_payload={
                        "rejectionStage": f"feed_{gate_stage or 'ingest_gate'}",
                        "rejectionReason": gate_reason,
                    },
                )
                recorded_ingest_rejection_count += 1
                skipped_ingest_rejection_count += 1
                summary_rows.append(
                    {
                        "item_id": card.item_id,
                        "title": card.title,
                        "price": decimal_to_float(card.price),
                        "business_domain": chosen_task.business_domain,
                        "status": "skipped_ingest_rejected",
                        "reason": gate_reason,
                    }
                )
                continue

            allowed_to_ingest, blocked_reason = should_allow_suspicious_listing_ingest(
                business_domain=chosen_task.business_domain,
                source_keyword="home_feed",
                extracted=extracted,
            )
            if not allowed_to_ingest:
                upsert_item_ingest_rejection(
                    session=session,
                    source_platform=chosen_task.source_platform,
                    item_id=extracted.item_id,
                    business_domain=chosen_task.business_domain,
                    category_id=chosen_task.category_id,
                    rejection_stage="feed_suspicious_intake",
                    rejection_reason=blocked_reason or "review_failed",
                )
                persist_home_feed_item_decision(
                    session=session,
                    item_id=extracted.item_id,
                    item_id_ref=int(existing_item.id) if existing_item is not None and existing_item.id is not None else None,
                    source_platform=chosen_task.source_platform,
                    decision_stage="suspicious_intake",
                    decision_status="skipped_llm_intake_invalid",
                    current_outreach_status=current_outreach_status,
                    category_selection=category_selection,
                    extra_payload={"rejectionReason": blocked_reason or "review_failed"},
                )
                recorded_ingest_rejection_count += 1
                skipped_suspicious_intake_count += 1
                summary_rows.append(
                    {
                        "item_id": card.item_id,
                        "title": card.title,
                        "price": decimal_to_float(card.price),
                        "business_domain": chosen_task.business_domain,
                        "status": "skipped_llm_intake_invalid",
                        "reason": blocked_reason,
                    }
                )
                continue
            pre_ingest_spec_candidate = None
            if not is_existing_item:
                pre_ingest_spec_candidate = build_feed_pre_ingest_spec_candidate(
                    task=chosen_task,
                    extracted=extracted,
                    category_context_override=category_selection.category_context if category_selection else None,
                )
                if category_selection is not None:
                    pre_ingest_spec_candidate.extraction_payload = {
                        **dict(pre_ingest_spec_candidate.extraction_payload or {}),
                        "feedCategorySelection": dict(category_selection.decision_payload or {}),
                    }
                pre_ingest_rejection_reason = feed_pre_ingest_template_rejection_reason(
                    candidate=pre_ingest_spec_candidate,
                )
                if pre_ingest_rejection_reason is not None:
                    upsert_item_ingest_rejection(
                        session=session,
                        source_platform=chosen_task.source_platform,
                        item_id=extracted.item_id,
                        business_domain=chosen_task.business_domain,
                        category_id=chosen_task.category_id,
                        rejection_stage="feed_pre_ingest_template",
                        rejection_reason=pre_ingest_rejection_reason,
                    )
                    persist_home_feed_item_decision(
                        session=session,
                        item_id=extracted.item_id,
                        item_id_ref=int(existing_item.id) if existing_item is not None and existing_item.id is not None else None,
                        source_platform=chosen_task.source_platform,
                        decision_stage="template_enrichment",
                        decision_status="skipped_pre_ingest_template_rejected",
                        current_outreach_status=current_outreach_status,
                        category_selection=category_selection,
                        category_context=category_selection.category_context if category_selection is not None else None,
                        extra_payload={
                            "rejectionReason": pre_ingest_rejection_reason,
                            "templateId": pre_ingest_spec_candidate.template_id,
                            "categoryId": pre_ingest_spec_candidate.category_id,
                            "candidateStatus": pre_ingest_spec_candidate.status,
                        },
                    )
                    recorded_ingest_rejection_count += 1
                    skipped_pre_ingest_template_count += 1
                    summary_rows.append(
                        {
                            "item_id": card.item_id,
                            "title": card.title,
                            "price": decimal_to_float(card.price),
                            "business_domain": chosen_task.business_domain,
                            "mapped_business_domain": mapped_domain,
                            "status": "skipped_pre_ingest_template_rejected",
                            "reason": pre_ingest_rejection_reason,
                            "pre_ingest_template_id": pre_ingest_spec_candidate.template_id,
                            "pre_ingest_category_id": pre_ingest_spec_candidate.category_id,
                        }
                    )
                    continue
            previous_price = existing_item.current_price if existing_item is not None else None
            item_pk = upsert_item(
                session=session,
                task=chosen_task,
                task_query_id=None,
                raw_response_id=None,
                seller_profile_id=existing_item.seller_profile_id if existing_item is not None else None,
                extracted=extracted,
                source_keyword="home_feed",
                preserve_missing_fields=True,
                category_context_override=category_selection.category_context if category_selection else None,
            )
            updated_item_count += 1
            persisted_item = session.get(Item, item_pk)
            if persisted_item is not None:
                persist_home_feed_item_decision_for_item(
                    session=session,
                    item=persisted_item,
                    decision_stage="category_resolution",
                    decision_status="resolved_ready_for_enrichment",
                    current_outreach_status=current_outreach_status,
                    category_selection=category_selection,
                    extra_payload={
                        "entryMode": "existing_item" if is_existing_item else "new_local_entry",
                    },
                )
            local_enrichment = None
            if not is_existing_item:
                local_entry_count += 1
                if pre_ingest_spec_candidate is not None:
                    local_enrichment = upsert_item_spec_enrichment_candidate_for_item(
                        session=session,
                        item_id_ref=item_pk,
                        candidate=pre_ingest_spec_candidate,
                    )
                else:
                    local_enrichment = upsert_item_spec_enrichment_for_item(
                        session=session,
                        item_id_ref=item_pk,
                        allow_llm=True,
                    )
                if local_enrichment is not None:
                    persist_home_feed_item_decision_for_item(
                        session=session,
                        item=persisted_item if persisted_item is not None else session.get(Item, item_pk),
                        decision_stage="template_enrichment",
                        decision_status=f"local_enrichment_{local_enrichment.status}",
                        current_outreach_status=current_outreach_status,
                        category_selection=category_selection,
                        extra_payload={
                            "enrichmentStatus": local_enrichment.status,
                            "enrichmentConfidence": decimal_to_float(local_enrichment.confidence),
                            "needsReview": local_enrichment.needs_review,
                        },
                    )
                    local_enrichment_count += 1
                    if local_enrichment.status in {"unresolved", "failed"}:
                        local_enrichment_unresolved_count += 1

            inserted_snapshot = False
            if should_insert_snapshot(
                session=session,
                item_id_ref=item_pk,
                extracted=extracted,
            ):
                snapshot_time = datetime.now(UTC)
                snapshot_extra_json = {
                    "source_keyword": "home_feed",
                    "position": card.position,
                }
                snapshot_extra_json.update(
                    build_snapshot_template_metadata(
                        task=chosen_task,
                        extracted=extracted,
                    )
                )
                session.add(
                    ItemSnapshot(
                        item_id_ref=item_pk,
                        task_query_id=None,
                        raw_response_id=None,
                        price=extracted.price,
                        region=extracted.area,
                        condition_tags=extracted.tags,
                        snapshot_at=snapshot_time,
                        publish_time=extracted.publish_time,
                        extra_json=snapshot_extra_json,
                    )
                )
                mark_item_snapshot_timestamp(session=session, item_id_ref=item_pk, snapshot_time=snapshot_time)
                snapshot_inserted_count += 1
                inserted_snapshot = True

            if previous_price is not None and extracted.price is not None and previous_price != extracted.price:
                price_changed_count += 1

            seller_profile = (
                seller_profiles.get(int(existing_item.seller_profile_id))
                if existing_item is not None and existing_item.seller_profile_id is not None
                else None
            )
            seller_name = seller_profile.seller_name if seller_profile is not None else None
            seller_id = seller_profile.seller_id if seller_profile is not None else None
            seller_type = resolve_feed_seller_type(
                card=card,
                existing_item=existing_item,
                seller_profiles=seller_profiles,
            )
            seller_type_source = (
                "seller_profile"
                if seller_profile is not None and normalize_feed_seller_type((seller_profile.metadata_json or {}).get("sellerType"))
                else "feed_card"
            )
            detail_snapshot: FeedDetailSellerSnapshot | None = None
            detail_fetch_error = None
            detail_page = None
            if current_outreach_status in {"sent", "sending"}:
                skipped_existing_outreach_count += 1
                should_message = False
                message_gate_reason = "existing_outreach"
            elif risk_control_active:
                detail_fetch_error = risk_control_error
                should_message = False
                message_gate_reason = "risk_control"
            elif not within_collection_scope:
                skipped_outside_collection_scope_count += 1
                should_message = False
                message_gate_reason = "outside_collection_scope"
            elif not detail_eligible:
                should_message = False
                message_gate_reason = "not_target"
            else:
                should_prefetch_detail = (
                    message_sent_count < max_messages
                    and (
                        not require_actionable_band
                        or (match is not None and match.target_buy_ceiling is not None)
                    )
                )
                if should_prefetch_detail:
                    try:
                        detail_page = open_feed_detail_page(
                            context=context,
                            item_id=card.item_id,
                            category_id=card.category_id,
                            listing_url=card.listing_url,
                        )
                        detail_snapshot = extract_feed_detail_seller_snapshot(detail_page=detail_page)
                        if detail_snapshot is not None:
                            seller_name = detail_snapshot.seller_name or seller_name
                            seller_id = detail_snapshot.seller_id or seller_id
                            detail_seller_type, detail_signals = classify_feed_detail_seller_snapshot(snapshot=detail_snapshot)
                            if detail_seller_type is not None:
                                seller_type = detail_seller_type
                                seller_type_source = "detail_page"
                                persist_feed_detail_seller_snapshot(
                                    session=session,
                                    item_pk=item_pk,
                                    existing_item=persisted_item,
                                    seller_profiles=seller_profiles,
                                    snapshot=detail_snapshot,
                                    seller_type=detail_seller_type,
                                    seller_type_signals=detail_signals,
                                )
                            else:
                                seller_type_source = "detail_page_unknown"
                    except Exception as exc:
                        detail_fetch_error = str(exc)
                        detected_auth_state = infer_auth_state_from_error_message(detail_fetch_error)
                        if detected_auth_state == "risk_control":
                            risk_control_hit_count += 1
                            risk_control_error = risk_control_error or detail_fetch_error
                            risk_control_active = True
                            seller_type_source = "detail_page_risk_control"
                        else:
                            seller_type_source = "detail_page_error"

                if risk_control_active and detail_fetch_error and infer_auth_state_from_error_message(detail_fetch_error) == "risk_control":
                    should_message = False
                    message_gate_reason = "risk_control"
                else:
                    should_message, message_gate_reason = should_message_feed_target(
                        card=card,
                        match=match,
                        seller_type=seller_type,
                        max_messages=max_messages,
                        sent_count=message_sent_count,
                        require_actionable_band=require_actionable_band,
                        only_within_target_price=only_within_target_price,
                        min_profit_margin_pct=min_profit_margin_pct,
                    )
                    if message_gate_reason == "seller_commercial_like":
                        skipped_commercial_seller_count += 1
                    elif message_gate_reason == "seller_type_unknown":
                        skipped_unknown_seller_count += 1
                    elif message_gate_reason == "below_min_profit_margin":
                        skipped_low_profit_margin_count += 1
                    elif message_gate_reason == "message_cap_reached":
                        skipped_message_cap_count += 1
            if message_gate_reason == "risk_control":
                risk_control_blocked_count += 1

            message_status = "not_target"
            message_error = None
            rendered_message_text = build_feed_outreach_message_text(
                card=card,
                match=match,
                message_template=message_text,
            )
            if should_message:
                if dry_run:
                    message_status = "dry_run"
                else:
                    try:
                        send_home_feed_message(
                            context=context,
                            item_id=card.item_id,
                            category_id=card.category_id,
                            listing_url=card.listing_url,
                            message_text=rendered_message_text,
                            detail_page=detail_page,
                        )
                        detail_page = None
                        message_status = "sent"
                        message_sent_count += 1
                        if message_sent_count < max_messages:
                            time.sleep(min_message_interval_seconds)
                    except Exception as exc:
                        message_status = "failed"
                        message_error = str(exc)
                        if infer_auth_state_from_error_message(message_error) == "risk_control":
                            risk_control_hit_count += 1
                            risk_control_error = risk_control_error or message_error
                            risk_control_active = True
                            message_status = "risk_control"

                if not dry_run:
                    upsert_outreach_record(
                        session=session,
                        item_id=card.item_id,
                        item_id_ref=item_pk,
                        business_domain=chosen_task.business_domain,
                        category_id=chosen_task.category_id,
                        model_catalog_id=(
                            str(match.pricing_row.get("model_catalog_id"))
                            if match is not None and match.pricing_row is not None and match.pricing_row.get("model_catalog_id")
                            else None
                        ),
                        target_label=match.label if match is not None else None,
                        message_text=rendered_message_text,
                        feed_price=card.price,
                        target_buy_ceiling=match.target_buy_ceiling if match is not None else None,
                        status=message_status,
                        error_message=message_error,
                        sent_at=datetime.now(UTC) if message_status == "sent" else None,
                    )
                    outreach_status[card.item_id] = message_status
            elif message_gate_reason == "existing_outreach":
                message_status = "existing_outreach"
            elif message_gate_reason == "below_min_profit_margin":
                message_status = "below_min_profit_margin"
            elif message_gate_reason == "above_target_price":
                message_status = "above_target_price"
            elif message_gate_reason == "outside_collection_scope":
                message_status = "outside_collection_scope"
            elif message_gate_reason == "not_actionable":
                message_status = "not_actionable"
            elif message_gate_reason == "seller_commercial_like":
                message_status = "seller_commercial_like"
            elif message_gate_reason == "seller_type_unknown":
                message_status = "seller_type_unknown"
            elif message_gate_reason == "missing_price_reference":
                message_status = "missing_price_reference"
            elif message_gate_reason == "missing_safe_price":
                message_status = "missing_safe_price"
            elif message_gate_reason == "message_cap_reached":
                message_status = "message_cap_reached"
            elif message_gate_reason == "risk_control":
                message_status = "risk_control"

            summary_rows.append(
                {
                    "item_id": card.item_id,
                    "title": card.title,
                    "price": decimal_to_float(card.price),
                    "business_domain": chosen_task.business_domain,
                    "mapped_business_domain": mapped_domain,
                    "entry_mode": "existing_item" if is_existing_item else "new_local_entry",
                    "resolved_category_id": str(persisted_item.resolved_category_id) if persisted_item is not None and persisted_item.resolved_category_id else None,
                    "resolved_template_id": str(persisted_item.resolved_template_id) if persisted_item is not None and persisted_item.resolved_template_id else None,
                    "category_decision_source": category_selection.decision_source if category_selection is not None else None,
                    "category_decision_reason": category_selection.decision_reason if category_selection is not None else None,
                    "category_candidate_business_domains": (
                        list(category_selection.candidate_business_domains) if category_selection is not None else None
                    ),
                    "category_active_candidate_business_domains": (
                        list(category_selection.active_candidate_business_domains)
                        if category_selection is not None
                        else None
                    ),
                    "target_view": match.view if match is not None else None,
                    "target_label": match.label if match is not None else None,
                    "target_buy_ceiling": decimal_to_float(match.target_buy_ceiling) if match is not None else None,
                    "fair_price": decimal_to_float(match.fair_price) if match is not None else None,
                    "local_enrichment_status": local_enrichment.status if local_enrichment is not None else None,
                    "local_enrichment_confidence": decimal_to_float(local_enrichment.confidence) if local_enrichment is not None else None,
                    "seller_id": seller_id,
                    "seller_name": seller_name,
                    "seller_type": seller_type,
                    "seller_type_source": seller_type_source,
                    "detail_level_token_count": detail_snapshot.level_token_count if detail_snapshot is not None else None,
                    "message_text": rendered_message_text,
                    "expected_profit_floor": decimal_to_float(match.expected_profit_floor) if match is not None else None,
                    "expected_profit_margin_pct": decimal_to_float(
                        compute_feed_expected_profit_margin_pct(card=card, match=match)
                    ),
                    "min_profit_margin_pct": decimal_to_float(min_profit_margin_pct),
                    "price_changed": previous_price != extracted.price if previous_price is not None else False,
                    "snapshot_inserted": inserted_snapshot,
                    "message_status": message_status,
                    "message_error": message_error,
                    "detail_fetch_error": detail_fetch_error,
                }
            )
            if persisted_item is not None:
                persist_home_feed_item_decision_for_item(
                    session=session,
                    item=persisted_item,
                    decision_stage="outreach",
                    decision_status=message_status or "not_attempted",
                    current_outreach_status=outreach_status.get(card.item_id),
                    category_selection=category_selection,
                    extra_payload={
                        "targetLabel": match.label if match is not None else None,
                        "detailEligible": detail_eligible,
                        "withinCollectionScope": within_collection_scope,
                        "messageError": message_error,
                        "detailFetchError": detail_fetch_error,
                    },
                )
            close_page_quietly(detail_page)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "business_domain": business_domain,
        "dry_run": dry_run,
        "freshness_days": freshness_days,
        "visible_card_count": len(cards),
        "updated_item_count": updated_item_count,
        "local_entry_count": local_entry_count,
        "local_enrichment_count": local_enrichment_count,
        "local_enrichment_unresolved_count": local_enrichment_unresolved_count,
        "target_match_count": target_match_count,
        "price_changed_count": price_changed_count,
        "snapshot_inserted_count": snapshot_inserted_count,
        "message_sent_count": message_sent_count,
        "skipped_existing_outreach_count": skipped_existing_outreach_count,
        "skipped_non_target_count": skipped_non_target_count,
        "skipped_unmapped_category_count": skipped_unmapped_category_count,
        "skipped_non_target_pool_count": skipped_unmapped_category_count,
        "skipped_missing_domain_task_count": skipped_missing_domain_task_count,
        "skipped_category_unresolved_count": skipped_missing_domain_task_count,
        "skipped_outside_collection_scope_count": skipped_outside_collection_scope_count,
        "skipped_commercial_seller_count": skipped_commercial_seller_count,
        "skipped_unknown_seller_count": skipped_unknown_seller_count,
        "skipped_ingest_rejection_count": skipped_ingest_rejection_count,
        "touched_permanent_rejection_count": touched_permanent_rejection_count,
        "recorded_ingest_rejection_count": recorded_ingest_rejection_count,
        "skipped_suspicious_intake_count": skipped_suspicious_intake_count,
        "skipped_pre_ingest_template_count": skipped_pre_ingest_template_count,
        "skipped_low_profit_margin_count": skipped_low_profit_margin_count,
        "skipped_message_cap_count": skipped_message_cap_count,
        "risk_control_hit_count": risk_control_hit_count,
        "risk_control_blocked_count": risk_control_blocked_count,
        "risk_control_error": risk_control_error,
        "items": summary_rows,
    }


def load_existing_items_map(*, session, item_ids: list[str]) -> dict[str, Item]:
    if not item_ids:
        return {}
    rows = session.execute(select(Item).where(Item.item_id.in_(item_ids))).scalars()
    return {item.item_id: item for item in rows}


def load_seller_profiles_map(*, session, seller_profile_ids: list[int]) -> dict[int, SellerProfile]:
    normalized_ids = sorted({int(value) for value in seller_profile_ids if value is not None})
    if not normalized_ids:
        return {}
    rows = session.execute(select(SellerProfile).where(SellerProfile.id.in_(normalized_ids))).scalars()
    return {int(profile.id): profile for profile in rows}


def load_outreach_status_map(*, session, item_ids: list[str]) -> dict[str, str]:
    if not item_ids:
        return {}
    rows = session.execute(
        select(OutreachRecord.item_id, OutreachRecord.status).where(OutreachRecord.item_id.in_(item_ids))
    ).all()
    return {item_id: status for item_id, status in rows}

def match_home_feed_target(
    *,
    card: FeedCardCandidate,
    existing_item: Item | None,
    tasks_by_domain: dict[str, CrawlTask],
    pricing_index: dict[str, dict[str, dict[str, dict[str, Any]]]],
    business_domain: str | None,
    require_actionable_band: bool,
    mapped_domain: str | None = None,
) -> FeedTargetMatch | None:
    candidate_domains = determine_feed_candidate_domains(
        card=card,
        existing_item=existing_item,
        tasks_by_domain=tasks_by_domain,
        business_domain=business_domain,
        mapped_domain=mapped_domain,
    )
    fallback_match: FeedTargetMatch | None = None

    for domain in candidate_domains:
        task = tasks_by_domain.get(domain)
        if task is None:
            continue

        candidate_record = build_feed_candidate_record(card=card, task=task)
        if candidate_record is not None:
            domain_targets = pricing_index.get(domain, {})
            spec_row = domain_targets.get("spec", {}).get(candidate_record["spec_label"])
            product_row = domain_targets.get("product", {}).get(candidate_record["product_label"])
            ranked_rows = []
            if spec_row is not None:
                ranked_rows.append(("spec", spec_row))
            if product_row is not None:
                ranked_rows.append(("product", product_row))
            ranked_rows.sort(key=lambda entry: feed_target_priority(entry[0], entry[1]), reverse=True)
            for view_name, row in ranked_rows:
                if require_actionable_band and not row["is_actionable"]:
                    continue
                return build_feed_target_match(
                    task=task,
                    view=view_name,
                    row=row,
                )

        lexicon_match = match_feed_title_to_task_lexicon(card.title, task)
        if lexicon_match and fallback_match is None and not require_actionable_band:
            fallback_match = FeedTargetMatch(
                business_domain=domain,
                task=task,
                view="lexicon",
                label=lexicon_match,
                product_label=None,
                spec_label=None,
                target_buy_ceiling=None,
                fair_price=None,
                expected_profit_floor=None,
                is_actionable=False,
                pricing_row=None,
            )

    return fallback_match


def build_feed_candidate_record(*, card: FeedCardCandidate, task: CrawlTask) -> dict[str, Any] | None:
    extracted = build_feed_extracted_item(card=card)
    return build_pricing_record_from_extracted(task=task, extracted=extracted)


def build_pricing_record_from_extracted(
    *,
    task: CrawlTask,
    extracted: ExtractedItem,
) -> dict[str, Any] | None:
    transient_item = build_transient_item(task=task, extracted=extracted)
    return resolve_pricing_record(transient_item, None)


def build_snapshot_template_metadata(
    *,
    task: CrawlTask,
    extracted: ExtractedItem,
) -> dict[str, Any]:
    pricing_record = build_pricing_record_from_extracted(
        task=task,
        extracted=extracted,
    )
    if pricing_record is None:
        return {}
    template_snapshot = build_pricing_record_template_snapshot(
        business_domain=pricing_record.get("business_domain") or task.business_domain,
        record=pricing_record,
    )
    metadata: dict[str, Any] = {}
    template_key = str(template_snapshot.get("templateKey") or "").strip()
    if template_key:
        metadata["template_key"] = template_key
    completeness = str(template_snapshot.get("completenessStatus") or "").strip()
    if completeness:
        metadata["template_completeness"] = completeness
    return metadata


def build_feed_extracted_item(*, card: FeedCardCandidate) -> ExtractedItem:
    normalized = normalize_title(card.title)
    inferred_business_domain = infer_scope_from_feed_title(card.title)
    return ExtractedItem(
        item_id=card.item_id,
        title=card.title,
        price=normalize_market_price(
            card.price,
            business_domain=inferred_business_domain,
            model_family=normalized["model_family"],
        ),
        pic_url=None,
        seller_name=None,
        seller_avatar_url=None,
        area=None,
        publish_time=None,
        tags=[],
        seller_id=None,
        c_cat_id=card.c_cat_id,
        cat_id=card.category_id,
        tb_cat_id=card.tb_cat_id,
        is_auction=False,
        is_ad=False,
        has_video=False,
        listing_url=build_feed_detail_url(
            item_id=card.item_id,
            category_id=card.category_id,
            listing_url=card.listing_url,
        ),
        normalized_brand=normalized["brand"],
        normalized_model_family=normalized["model_family"],
        normalized_model=normalized["model"],
        normalized_chip=normalized["chip"],
        normalized_memory_gb=normalized["memory_gb"],
        normalized_storage_gb=normalized["storage_gb"],
    )


def build_transient_item(
    *,
    task: CrawlTask,
    extracted: ExtractedItem,
    category_context_override: ResolvedItemCategoryContext | None = None,
) -> Item:
    now = datetime.now(UTC)
    category_context = category_context_override
    business_domain = (
        category_context.resolved_business_domain
        if category_context is not None and category_context.resolved_business_domain
        else task.business_domain
    )
    target_category_id = (
        category_context.target_category_id
        if category_context is not None and category_context.target_category_id is not None
        else task.category_id
    )
    resolved_category_id = (
        category_context.resolved_category_id
        if category_context is not None and category_context.resolved_category_id is not None
        else task.category_id
    )
    resolved_template_id = (
        category_context.resolved_template_id
        if category_context is not None
        else None
    )
    category_validation_status = (
        category_context.category_validation_status
        if category_context is not None
        else ("PENDING" if not task.category_id else "MATCH_TASK_CATEGORY")
    )
    category_validation_reason = (
        category_context.category_validation_reason
        if category_context is not None
        else (None if not task.category_id else "transient_task_category")
    )
    category_validation_confidence = (
        category_context.category_validation_confidence
        if category_context is not None
        else (None if not task.category_id else Decimal("1.0000"))
    )
    return Item(
        item_id=extracted.item_id,
        task_id=task.id,
        task_query_id=None,
        source_platform=task.source_platform,
        business_domain=business_domain,
        target_category_id=target_category_id,
        resolved_category_id=resolved_category_id,
        resolved_template_id=resolved_template_id,
        category_validation_status=category_validation_status,
        category_validation_reason=category_validation_reason,
        category_validation_confidence=category_validation_confidence,
        source_keyword="home_feed",
        title=extracted.title,
        normalized_brand=extracted.normalized_brand,
        normalized_model_family=extracted.normalized_model_family,
        normalized_model=extracted.normalized_model,
        normalized_chip=extracted.normalized_chip,
        normalized_memory_gb=extracted.normalized_memory_gb,
        normalized_storage_gb=extracted.normalized_storage_gb,
        condition_tags=extracted.tags,
        region=extracted.area,
        listing_url=extracted.listing_url,
        image_urls=[extracted.pic_url] if extracted.pic_url else [],
        is_auction=extracted.is_auction,
        is_ad=extracted.is_ad,
        has_video=extracted.has_video,
        current_price=extracted.price,
        publish_time=extracted.publish_time,
        first_seen_at=now,
        last_seen_at=now,
        last_snapshot_at=None,
        is_active=True,
    )


def build_feed_pre_ingest_spec_candidate(
    *,
    task: CrawlTask,
    extracted: ExtractedItem,
    category_context_override: ResolvedItemCategoryContext | None = None,
) -> SpecEnrichmentCandidate:
    transient_item = build_transient_item(
        task=task,
        extracted=extracted,
        category_context_override=category_context_override,
    )
    return extract_item_specs(transient_item, allow_llm=True)


def feed_pre_ingest_template_rejection_reason(
    *,
    candidate: SpecEnrichmentCandidate,
) -> str | None:
    evidence = dict(candidate.evidence or {})
    payload = dict(candidate.extraction_payload or {})
    policy_rejection = payload.get("rejected_by_policy")
    reason = str(evidence.get("reason") or "").strip()
    if not reason and isinstance(policy_rejection, dict):
        reason = str(policy_rejection.get("reason") or "").strip()
    if reason.startswith("non_target_"):
        return reason
    if str(candidate.status or "").strip().lower() == "failed":
        return "template_resolution_failed"
    return None


def resolve_feed_task(
    *,
    session,
    existing_item: Item | None,
    match: FeedTargetMatch | None,
    tasks_by_domain: dict[str, CrawlTask],
    mapped_domain: str | None = None,
) -> CrawlTask | None:
    if existing_item is not None:
        for scope_key in compatible_scope_keys(existing_item.business_domain):
            task = tasks_by_domain.get(resolve_category_code(scope_key) or scope_key)
            if task is not None:
                return task
        return session.get(CrawlTask, existing_item.task_id)
    if match is not None:
        return match.task
    if mapped_domain is not None:
        task = tasks_by_domain.get(resolve_category_code(mapped_domain) or mapped_domain)
        if task is not None:
            return task
    return None


def open_feed_detail_page(
    *,
    context,
    item_id: str,
    category_id: str | None = None,
    listing_url: str | None = None,
):
    detail_url = build_feed_detail_url(item_id=item_id, category_id=category_id, listing_url=listing_url)
    detail_page = context.new_page()
    try:
        detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)
        detail_page.wait_for_timeout(3000)
        raise_if_home_feed_manual_verification(detail_page, stage="detail page")
        return detail_page
    except Exception:
        close_page_quietly(detail_page)
        raise


def extract_feed_detail_seller_snapshot(*, detail_page) -> FeedDetailSellerSnapshot | None:
    raise_if_home_feed_manual_verification(detail_page, stage="detail page")
    payload = detail_page.evaluate(
        """
() => {
  const text = (node) => ((node && node.textContent) || '').replace(/\\s+/g, ' ').trim();
  const root =
    document.querySelector("[class*='item-user-container--']") ||
    document.querySelector("[class*='item-user-info-container--']")?.closest("[class*='item-user-container--']");
  if (!root) return null;

  const uniq = (values) => Array.from(new Set(values.filter(Boolean)));
  const parseIntMatch = (pattern, value) => {
    const match = value.match(pattern);
    return match && match[1] ? Number.parseInt(match[1], 10) : null;
  };
  const parseParam = (href, key) => {
    if (!href) return null;
    try {
      return new URL(href, location.href).searchParams.get(key);
    } catch (error) {
      return null;
    }
  };

  const profileAnchor =
    root.closest("a[href*='/personal?userId=']") ||
    document.querySelector("a[href*='/personal?userId=']");
  const chatAnchor = document.querySelector("a[href*='/im?'][href*='peerUserId=']");
  const labelTexts = uniq(Array.from(root.querySelectorAll("[class*='label']")).map(text));
  const badgeTexts = uniq(
    Array.from(root.querySelectorAll("[class*='fish-shop'], [class*='badge'], [class*='tag']")).map(text),
  );
  const levelNode = root.querySelector("[class*='item-user-info-level--']");
  const levelTexts = levelNode ? uniq(Array.from(levelNode.children).map(text)) : [];
  const rootText = text(root);

  return {
    sellerId:
      parseParam(profileAnchor ? profileAnchor.href : null, "userId") ||
      parseParam(chatAnchor ? chatAnchor.href : null, "peerUserId"),
    sellerName:
      text(root.querySelector("[class*='item-user-info-nick--']")) ||
      text(root.querySelector("[class*='item-user-info-main--']")) ||
      null,
    region: labelTexts.find((value) => /市|省|区|县|自治区/.test(value)) || labelTexts[0] || null,
    lastActiveLabel: labelTexts.find((value) => value.includes("来过")) || null,
    soldCount: parseIntMatch(/卖出\\s*(\\d+)\\s*件宝贝/, rootText),
    yearsOnPlatform: parseIntMatch(/来闲鱼\\s*(\\d+)\\s*年/, rootText),
    reviewRatePct: parseIntMatch(/好评率\\s*(\\d+)%/, rootText),
    levelTokenCount: levelNode ? levelNode.children.length : null,
    levelTexts,
    badgeTexts,
    profileUrl: profileAnchor ? profileAnchor.href : null,
  };
}
"""
    )
    if not payload:
        return None
    return FeedDetailSellerSnapshot(
        seller_id=str(payload.get("sellerId") or "").strip() or None,
        seller_name=str(payload.get("sellerName") or "").strip() or None,
        region=str(payload.get("region") or "").strip() or None,
        last_active_label=str(payload.get("lastActiveLabel") or "").strip() or None,
        sold_count=int(payload["soldCount"]) if payload.get("soldCount") is not None else None,
        years_on_platform=int(payload["yearsOnPlatform"]) if payload.get("yearsOnPlatform") is not None else None,
        review_rate_pct=int(payload["reviewRatePct"]) if payload.get("reviewRatePct") is not None else None,
        level_token_count=int(payload["levelTokenCount"]) if payload.get("levelTokenCount") is not None else None,
        level_texts=tuple(str(value).strip() for value in payload.get("levelTexts") or [] if str(value).strip()),
        badge_texts=tuple(str(value).strip() for value in payload.get("badgeTexts") or [] if str(value).strip()),
        profile_url=str(payload.get("profileUrl") or "").strip() or None,
    )


def persist_feed_detail_seller_snapshot(
    *,
    session,
    item_pk: int,
    existing_item: Item | None,
    seller_profiles: dict[int, SellerProfile],
    snapshot: FeedDetailSellerSnapshot,
    seller_type: str | None,
    seller_type_signals: list[str],
) -> int | None:
    if not snapshot.seller_id:
        return existing_item.seller_profile_id if existing_item is not None else None

    seller_profile_id = upsert_seller(
        session=session,
        seller_id=snapshot.seller_id,
        seller_name=snapshot.seller_name,
        avatar_url=None,
        region=snapshot.region,
    )

    item = session.get(Item, item_pk)
    if item is not None and item.seller_profile_id != seller_profile_id:
        item.seller_profile_id = seller_profile_id
    if existing_item is not None:
        existing_item.seller_profile_id = seller_profile_id

    seller_profile = session.get(SellerProfile, seller_profile_id)
    if seller_profile is not None and seller_type in {"commercial_like", "private_like"}:
        metadata_json = dict(seller_profile.metadata_json or {})
        metadata_json.update(
            {
                "sellerType": seller_type,
                "sellerTypeConfidence": 0.9 if seller_type == "commercial_like" else 0.7,
                "sellerTypeSignals": seller_type_signals,
                "sellerTypeSource": "detail_page_v2",
                "detailLevelTokenCount": snapshot.level_token_count,
                "detailLevelTexts": list(snapshot.level_texts),
                "detailBadgeTexts": list(snapshot.badge_texts),
                "detailSoldCount": snapshot.sold_count,
                "detailYearsOnPlatform": snapshot.years_on_platform,
                "detailReviewRatePct": snapshot.review_rate_pct,
                "detailProfileUrl": snapshot.profile_url,
            }
        )
        seller_profile.metadata_json = metadata_json
        seller_profiles[int(seller_profile_id)] = seller_profile
    return seller_profile_id


def close_page_quietly(page) -> None:
    try:
        if page is not None and not page.is_closed():
            page.close()
    except Exception:
        pass


def send_home_feed_message(
    *,
    context,
    item_id: str,
    category_id: str | None,
    listing_url: str | None,
    message_text: str,
    detail_page=None,
) -> None:
    if detail_page is None:
        detail_page = open_feed_detail_page(
            context=context,
            item_id=item_id,
            category_id=category_id,
            listing_url=listing_url,
        )
    chat_page = None
    try:
        chat_page = open_chat_page_from_detail_page(detail_page=detail_page, context=context)
        send_message_in_chat(chat_page=chat_page, message_text=message_text)
    finally:
        if chat_page is not None and chat_page is not detail_page:
            close_page_quietly(chat_page)
        close_page_quietly(detail_page)


def open_chat_page_from_detail_page(*, detail_page, context):
    if "/im?" in detail_page.url:
        raise_if_home_feed_manual_verification(detail_page, stage="chat page")
        return detail_page

    raise_if_home_feed_manual_verification(detail_page, stage="detail page")
    existing_pages = set(context.pages)
    locators = [
        detail_page.locator("a[class*='want--']").first,
        detail_page.get_by_text("聊一聊").first,
        detail_page.get_by_text("联系卖家").first,
        detail_page.get_by_text("私聊").first,
    ]

    clicked = False
    for locator in locators:
        try:
            if locator.count() < 1:
                continue
            locator.click(timeout=3000)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        raise_if_home_feed_manual_verification(detail_page, stage="detail page")
        raise RuntimeError("No chat entry button found on the listing detail page.")

    deadline = time.time() + 8
    while time.time() < deadline:
        raise_if_home_feed_manual_verification(detail_page, stage="detail page")
        if "/im?" in detail_page.url:
            raise_if_home_feed_manual_verification(detail_page, stage="chat page")
            return detail_page
        for page in context.pages:
            if page in existing_pages:
                continue
            if "/im?" in page.url:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                raise_if_home_feed_manual_verification(page, stage="chat page")
                return page
        detail_page.wait_for_timeout(250)

    raise_if_home_feed_manual_verification(detail_page, stage="detail page")
    raise RuntimeError("Chat page did not open after clicking the detail page contact entry.")


def send_message_in_chat(*, chat_page, message_text: str) -> None:
    raise_if_home_feed_manual_verification(chat_page, stage="chat page")
    textarea = chat_page.locator("textarea").first
    try:
        textarea.wait_for(timeout=15000)
    except Exception:
        raise_if_home_feed_manual_verification(chat_page, stage="chat page")
        raise
    textarea.fill(message_text)

    send_button = chat_page.get_by_role("button", name=re.compile(r"发\s*送"))
    if send_button.count() > 0:
        send_button.first.click(timeout=5000)
    else:
        textarea.press("Enter")
    chat_page.wait_for_timeout(1500)
    raise_if_home_feed_manual_verification(chat_page, stage="chat page")


def upsert_outreach_record(
    *,
    session,
    item_id: str,
    item_id_ref: int | None,
    business_domain: str | None,
    category_id: str | None,
    model_catalog_id: str | None,
    target_label: str | None,
    message_text: str,
    feed_price: Decimal | None,
    target_buy_ceiling: Decimal | None,
    status: str,
    error_message: str | None,
    sent_at: datetime | None,
) -> None:
    stmt = insert(OutreachRecord).values(
        item_id=item_id,
        item_id_ref=item_id_ref,
        business_domain=business_domain,
        category_id=category_id,
        model_catalog_id=model_catalog_id,
        source="home_feed",
        target_label=target_label,
        message_text=message_text,
        feed_price=feed_price,
        target_buy_ceiling=target_buy_ceiling,
        status=status,
        error_message=error_message,
        sent_at=sent_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[OutreachRecord.item_id],
        set_={
            "item_id_ref": item_id_ref,
            "business_domain": business_domain,
            "category_id": category_id,
            "model_catalog_id": model_catalog_id,
            "source": "home_feed",
            "target_label": target_label,
            "message_text": message_text,
            "feed_price": feed_price,
            "target_buy_ceiling": target_buy_ceiling,
            "status": status,
            "error_message": error_message,
            "sent_at": sent_at,
        },
    )
    session.execute(stmt)


def float_to_decimal(value: float | int | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"))


def parse_request_body(post_data: str) -> dict[str, Any]:
    if not post_data:
        return {}

    parsed = parse_qs(post_data, keep_blank_values=True)
    raw_data = parsed.get("data", [None])[0]
    if raw_data is None:
        return {key: values[0] if len(values) == 1 else values for key, values in parsed.items()}

    try:
        return json.loads(raw_data)
    except json.JSONDecodeError:
        return {"raw_data": raw_data}


def click_search_results_next_page(page) -> bool:
    return bool(
        page.evaluate(
            """
() => {
  const isUsable = (button) => {
    if (!button) return false;
    if (button.disabled || button.getAttribute("aria-disabled") === "true") return false;
    const className = String(button.className || "").toLowerCase();
    if (className.includes("disabled")) return false;
    const style = window.getComputedStyle(button);
    if (style.pointerEvents === "none") return false;
    if (Number(style.opacity || "1") < 0.45) return false;
    const rect = button.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  const topButtons = Array.from(
    document.querySelectorAll("button[class*='search-page-tiny-arrow-container']")
  ).filter((button) => {
    const rect = button.getBoundingClientRect();
    return rect.top >= 0 && rect.top < 260;
  });
  const topNextButton = topButtons[1];
  if (isUsable(topNextButton)) {
    topNextButton.click();
    return true;
  }

  const nextButtons = Array.from(
    document.querySelectorAll("button[class*='search-pagination-arrow-container']")
  );
  const nextButton = nextButtons[1];
  if (isUsable(nextButton)) {
    nextButton.click();
    return true;
  }

  const active = document.querySelector("div[class*='search-pagination-page-box-active']");
  const current = active ? Number((active.textContent || "").trim()) : NaN;
  if (!Number.isNaN(current)) {
    const nextPage = Array.from(
      document.querySelectorAll("div[class*='search-pagination-page-box']")
    ).find((node) => (node.textContent || "").trim() === String(current + 1));
    if (nextPage) {
      nextPage.click();
      return true;
    }
  }

  return false;
}
"""
        )
    )


def resolve_target_pages(*, task: CrawlTask, pages: int) -> int | None:
    if pages > 0:
        return pages
    return None


def pagination_deadline_seconds(*, target_pages: int | None, login_wait_seconds: int) -> int:
    if target_pages is None:
        return max(login_wait_seconds, 3600)
    return max(login_wait_seconds, target_pages * 25)


def paginate_captured_search_results(
    *,
    page,
    captures: dict[int, CapturedSearchPayload],
    target_pages: int | None,
    deadline: float,
    auto_paginate: bool,
    on_new_capture_pages: Callable[[], None] | None = None,
) -> None:
    stall_count = 0

    while time.time() < deadline:
        if target_pages is not None and len(captures) >= target_pages:
            break
        if has_empty_search_results(captures):
            break

        known_pages = set(captures)
        previous_page = read_search_results_page_number(page)
        clicked_next = False

        try:
            wait_for_search_results_pagination(page)
            wait_for_human_page_interval(page)
            clicked_next = click_search_results_next_page(page)
            if clicked_next:
                wait_for_search_results_page_change(page, previous_page, timeout_seconds=8)
                page.wait_for_timeout(random.randint(350, 650))
        except Exception:
            clicked_next = False

        progressed = wait_for_capture_progress(page, captures, known_pages, timeout_seconds=8)
        if progressed:
            if on_new_capture_pages is not None:
                on_new_capture_pages()
            stall_count = 0
        else:
            stall_count += 1

        if auto_paginate and len(captures) > 0 and not clicked_next:
            break
        if stall_count >= 2:
            break


def summarize_capture_pages(captures: dict[int, CapturedSearchPayload]) -> tuple[list[CapturedSearchPayload], int, int]:
    ordered = [captures[key] for key in sorted(captures)]
    attempted = len(ordered)
    succeeded = sum(1 for capture in ordered if search_results_count(capture.payload) > 0)
    return ordered, attempted, succeeded


def search_page_interval_ms() -> int:
    return random.randint(SEARCH_PAGE_INTERVAL_MIN_MS, SEARCH_PAGE_INTERVAL_MAX_MS)


def wait_for_human_page_interval(page) -> None:
    page.wait_for_timeout(search_page_interval_ms())


def has_empty_search_results(captures: dict[int, CapturedSearchPayload]) -> bool:
    return any(search_results_count(capture.payload) == 0 for capture in captures.values())


def search_results_count(payload: dict[str, Any]) -> int:
    result_list = payload.get("data", {}).get("resultList")
    return len(result_list) if isinstance(result_list, list) else 0


def wait_for_search_results_pagination(page) -> None:
    page.wait_for_function(
        """
() => {
  const topButtons = document.querySelectorAll("button[class*='search-page-tiny-arrow-container']");
  const bottomButtons = document.querySelectorAll("button[class*='search-pagination-arrow-container']");
  return topButtons.length >= 2 || bottomButtons.length >= 2;
}
""",
        timeout=5000,
    )


def read_search_results_page_number(page) -> int | None:
    current = page.evaluate(
        """
() => {
  const topPager = Array.from(document.querySelectorAll("div,span")).find((node) => {
    const text = (node.textContent || "").trim();
    if (!/^\\d+\\/\\d+$/.test(text)) return false;
    const rect = node.getBoundingClientRect();
    return rect.top >= 0 && rect.top < 260;
  });
  if (topPager) {
    const currentPage = Number((topPager.textContent || "").trim().split("/")[0]);
    return Number.isNaN(currentPage) ? null : currentPage;
  }

  const active = document.querySelector("div[class*='search-pagination-page-box-active']");
  if (!active) return null;
  const currentPage = Number((active.textContent || "").trim());
  return Number.isNaN(currentPage) ? null : currentPage;
}
"""
    )
    return int(current) if isinstance(current, (int, float)) else None


def wait_for_search_results_page_change(page, previous_page: int | None, timeout_seconds: int) -> bool:
    if previous_page is None:
        return False

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        current_page = read_search_results_page_number(page)
        if current_page is not None and current_page != previous_page:
            return True
        page.wait_for_timeout(250)
    return False


def wait_for_capture_progress(
    page,
    captures: dict[int, CapturedSearchPayload],
    known_pages: set[int],
    timeout_seconds: int,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if set(captures) != known_pages:
            return True
        page.wait_for_timeout(250)
    return False


def resolve_cdp_url(cdp_url: str | None) -> str | None:
    if cdp_url is None:
        return None
    if cdp_url != "auto":
        return cdp_url

    candidates = discover_attached_browsers()
    if candidates:
        return candidates[0]["cdp_url"]

    fallback_cdp_url = discover_default_cdp_url()
    if fallback_cdp_url is not None:
        return fallback_cdp_url

    raise RuntimeError("No attachable Chrome instance found. Start Chrome with a remote debugging port first.")


def discover_default_cdp_url() -> str | None:
    for port in DEFAULT_ATTACHED_CDP_PORTS:
        cdp_url = f"http://127.0.0.1:{port}"
        if fetch_cdp_tabs(cdp_url) is not None:
            return cdp_url
    return None


def discover_attached_browsers() -> list[dict[str, Any]]:
    if shutil.which("powershell") is None:
        candidates: list[dict[str, Any]] = []
        for port in DEFAULT_ATTACHED_CDP_PORTS:
            cdp_url = f"http://127.0.0.1:{port}"
            tabs = fetch_cdp_tabs(cdp_url)
            if tabs is None:
                continue
            candidates.append(
                {
                    "process_id": None,
                    "cdp_url": cdp_url,
                    "goofish_tab_count": sum(1 for tab in tabs if tab["is_goofish"]),
                    "tabs": tabs,
                }
            )
        candidates.sort(key=lambda item: (item["goofish_tab_count"], len(item["tabs"])), reverse=True)
        return candidates

    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -match '--remote-debugging-port=' } | "
        "Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return []

    payload = json.loads(completed.stdout)
    rows = payload if isinstance(payload, list) else [payload]
    candidates: list[dict[str, Any]] = []
    seen_ports: set[int] = set()

    for row in rows:
        command_line = row.get("CommandLine") or ""
        match = re.search(r"--remote-debugging-port=(\d+)", command_line)
        if not match:
            continue
        port = int(match.group(1))
        if port in seen_ports:
            continue
        seen_ports.add(port)
        cdp_url = f"http://127.0.0.1:{port}"
        tabs = fetch_cdp_tabs(cdp_url)
        if tabs is None:
            continue
        candidates.append(
            {
                "process_id": row.get("ProcessId"),
                "cdp_url": cdp_url,
                "goofish_tab_count": sum(1 for tab in tabs if tab["is_goofish"]),
                "tabs": tabs,
            }
        )

    candidates.sort(key=lambda item: (item["goofish_tab_count"], len(item["tabs"])), reverse=True)
    return candidates


def fetch_cdp_tabs(cdp_url: str) -> list[dict[str, Any]] | None:
    try:
        with urlopen(f"{cdp_url}/json/list", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    tabs: list[dict[str, Any]] = []
    for tab in payload:
        url = tab.get("url", "")
        tabs.append(
            {
                "id": tab.get("id"),
                "type": tab.get("type"),
                "title": tab.get("title"),
                "url": url,
                "is_goofish": "goofish.com" in url,
            }
        )
    return tabs


def load_items_for_enrichment(
    *,
    business_domain: str | None,
    item_id: str | None,
    limit: int,
    force: bool,
) -> list[int]:
    return load_items_for_enrichment_from_queue(
        business_domain=business_domain,
        item_id=item_id,
        limit=limit,
        force=force,
        session_factory=session_scope,
    )


def enrich_single_item(*, db_item_id: int, allow_llm: bool) -> dict[str, Any]:
    with session_scope() as session:
        item = session.get(Item, db_item_id)
        if item is None:
            raise RuntimeError(f"Item {db_item_id} not found.")

        candidate = upsert_item_spec_enrichment_for_item(
            session=session,
            item_id_ref=db_item_id,
            allow_llm=allow_llm,
        )
        if candidate is None:
            raise RuntimeError(f"Item {db_item_id} disappeared during enrichment.")

        confidence = float(candidate.confidence) if candidate.confidence is not None else None
        return {
            "item_id": item.item_id,
            "status": candidate.status,
            "confidence": confidence,
            "model_name": candidate.model_name,
            "extractor_type": candidate.extractor_type,
        }


def upsert_item_spec_enrichment_for_item(
    *,
    session,
    item_id_ref: int,
    allow_llm: bool,
):
    item = session.get(Item, item_id_ref)
    if item is None:
        return None

    candidate = extract_item_specs(item, allow_llm=allow_llm)
    return upsert_item_spec_enrichment_candidate_for_item(
        session=session,
        item_id_ref=item_id_ref,
        candidate=candidate,
    )


def upsert_item_spec_enrichment_candidate_for_item(
    *,
    session,
    item_id_ref: int,
    candidate: SpecEnrichmentCandidate,
):
    item = session.get(Item, item_id_ref)
    if item is None:
        return None
    payload = candidate.to_record(item=item)
    upsert_stmt = insert(ItemSpecEnrichment).values(**payload)
    excluded = upsert_stmt.excluded
    session.execute(
        upsert_stmt.on_conflict_do_update(
            constraint="uq_item_spec_enrichments_item_id_ref",
            set_={
                "business_domain": excluded.business_domain,
                "category_id": excluded.category_id,
                "template_id": excluded.template_id,
                "model_catalog_id": excluded.model_catalog_id,
                "extractor_type": excluded.extractor_type,
                "extractor_version": excluded.extractor_version,
                "llm_provider": excluded.llm_provider,
                "llm_model": excluded.llm_model,
                "status": excluded.status,
                "confidence": excluded.confidence,
                "needs_review": excluded.needs_review,
                "brand": excluded.brand,
                "product_line": excluded.product_line,
                "model_family": excluded.model_family,
                "model_name": excluded.model_name,
                "generation": excluded.generation,
                "case_size_mm": excluded.case_size_mm,
                "is_solar": excluded.is_solar,
                "display_type": excluded.display_type,
                "screen_size_in": excluded.screen_size_in,
                "chip_family": excluded.chip_family,
                "cpu_model": excluded.cpu_model,
                "cpu_cores": excluded.cpu_cores,
                "gpu_cores": excluded.gpu_cores,
                "memory_gb": excluded.memory_gb,
                "storage_gb": excluded.storage_gb,
                "edition_tags": excluded.edition_tags,
                "evidence": excluded.evidence,
                "extraction_payload": excluded.extraction_payload,
                "updated_at": func.now(),
            },
        )
    )
    propagate_specs_to_item(item=item, payload=payload)
    return candidate


def _coerce_backfill_confidence(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        numeric = Decimal(str(value))
    except Exception:
        return None
    if numeric > 1:
        numeric /= Decimal("100")
    numeric = max(Decimal("0"), min(numeric, Decimal("1")))
    return numeric.quantize(Decimal("0.01"))


def _extract_confidence_from_payload(payload: dict[str, Any] | None) -> Decimal | None:
    if not isinstance(payload, dict):
        return None
    direct_value = payload.get("confidence")
    if direct_value is None:
        direct_value = payload.get("self_confidence")
    return _coerce_backfill_confidence(direct_value)


def backfill_spec_confidence(
    *,
    dry_run: bool = False,
    limit: int | None = None,
    extractor_type: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "extractor_type": extractor_type,
        "scanned": 0,
        "updated": 0,
        "skipped_no_source": 0,
        "sources": {},
    }
    with session_scope() as session:
        stmt = (
            select(ItemSpecEnrichment, Item)
            .join(Item, Item.id == ItemSpecEnrichment.item_id_ref)
            .where(ItemSpecEnrichment.confidence.is_(None))
            .order_by(ItemSpecEnrichment.updated_at.desc(), ItemSpecEnrichment.id.desc())
        )
        if extractor_type:
            stmt = stmt.where(ItemSpecEnrichment.extractor_type == extractor_type)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = session.execute(stmt).all()
        summary["scanned"] = len(rows)
        source_counts: dict[str, int] = defaultdict(int)
        for spec, item in rows:
            desired_confidence = _extract_confidence_from_payload(spec.extraction_payload)
            confidence_source = "extraction_payload"
            if desired_confidence is None:
                desired_confidence = _extract_confidence_from_payload(spec.evidence)
                confidence_source = "evidence"
            if desired_confidence is None and (spec.extractor_type or "").strip().lower() == "llm_review":
                desired_confidence = _coerce_backfill_confidence(item.llm_review_confidence)
                confidence_source = "item_llm_review_confidence"
            if desired_confidence is None:
                summary["skipped_no_source"] += 1
                continue
            spec.confidence = desired_confidence
            source_counts[confidence_source] += 1
            summary["updated"] += 1
        summary["sources"] = dict(sorted(source_counts.items()))
        if dry_run:
            session.rollback()
    return summary


def propagate_specs_to_item(*, item: Item, payload: dict[str, Any]) -> None:
    if payload.get("brand"):
        item.normalized_brand = payload["brand"]
    if payload.get("product_line") or payload.get("model_family"):
        item.normalized_model_family = payload.get("model_family") or payload.get("product_line")
    if payload.get("model_name"):
        item.normalized_model = payload["model_name"]
    if payload.get("chip_family"):
        item.normalized_chip = payload["chip_family"]
    if payload.get("memory_gb") is not None:
        item.normalized_memory_gb = payload["memory_gb"]
    if payload.get("storage_gb") is not None:
        item.normalized_storage_gb = payload["storage_gb"]


register_admin_commands(
    app,
    alembic_config=alembic_config,
    discover_attached_browsers=discover_attached_browsers,
)
register_collect_commands(
    app,
    build_crawl_task_runtime_config=build_crawl_task_runtime_config,
    search_plan_entry_cls=SearchPlanEntry,
    default_config_path=default_config_path,
    ensure_task=ensure_task,
    export_task_config_bundle=export_task_config_bundle,
    get_settings=get_settings,
    get_task_or_raise=get_task_or_raise,
    group_batch_plans_by_platform=group_batch_plans_by_platform,
    load_profile_settings=load_profile_settings,
    load_task_config=load_task_config,
    run_live_search_batch=run_live_search_batch,
    run_live_search_capture=run_live_search_capture,
    write_model_discovery_report=write_model_discovery_report,
)
register_feed_commands(
    app,
    load_profile_settings=load_profile_settings,
    resolve_cdp_url=resolve_cdp_url,
    run_home_feed_refresh=run_home_feed_refresh,
)
register_maintenance_commands(
    app,
    backfill_spec_confidence=backfill_spec_confidence,
    backfill_item_category_resolution=backfill_item_category_resolution,
    backfill_task_category_bindings=backfill_task_category_bindings,
    preprocess_apple_items=preprocess_apple_items,
    backfill_normalized_prices=backfill_normalized_prices,
    cleanup_historical_data=cleanup_historical_data,
    enrich_single_item=enrich_single_item,
    get_settings=get_settings,
    classify_seller_types=classify_seller_types,
    llm_is_configured=llm_is_configured,
    load_items_for_enrichment=load_items_for_enrichment,
)
register_mobile_commands(app)
register_pricing_commands(app)
register_review_commands(app)


if __name__ == "__main__":
    app()
