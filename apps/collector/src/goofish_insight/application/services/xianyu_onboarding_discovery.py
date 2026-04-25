from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import case, select

from ...category_compat import compatible_scope_keys
from ...db import session_scope
from ...models import CrawlTask


class XianyuOnboardingDiscoveryError(RuntimeError):
    """Raised when the onboarding discovery collect cannot be started."""


def run_xianyu_onboarding_discovery(
    *,
    source_keyword: str,
    task_key: str | None = None,
    business_domain: str | None = None,
    pages: int = 1,
    profile_key: str = "default",
    login_wait_seconds: int = 180,
) -> dict[str, Any]:
    resolved_source_keyword = (source_keyword or "").strip()
    if not resolved_source_keyword:
        raise XianyuOnboardingDiscoveryError("source_keyword is required.")

    resolved_profile_key = (profile_key or "default").strip() or "default"
    resolved_pages = max(1, int(pages))
    resolved_login_wait_seconds = max(30, int(login_wait_seconds))

    cli = _load_cli_helpers()
    task = _resolve_discovery_task(
        cli=cli,
        task_key=task_key,
        business_domain=business_domain,
    )
    profile_settings = dict(cli.load_profile_settings(resolved_profile_key) or {})
    settings = cli.get_settings()
    profile_dir = Path(settings.browser_profile_dir) / resolved_profile_key
    channel = str(profile_settings.get("channel", "msedge"))
    headless = bool(profile_settings.get("headless", False))
    configured_cdp_url = profile_settings.get("cdp_url")

    resolved_cdp_url = None
    cdp_fallback_reason = None
    if configured_cdp_url:
        try:
            resolved_cdp_url = cli.resolve_cdp_url(str(configured_cdp_url))
        except Exception as exc:  # pragma: no cover - guarded by tests via fallback assertions
            cdp_fallback_reason = str(exc)

    try:
        if resolved_cdp_url:
            result = cli.run_search_plan_in_attached_tab(
                plan=cli.SearchPlanEntry(
                    task=task,
                    query=resolved_source_keyword,
                    pages=resolved_pages,
                ),
                resolved_cdp_url=resolved_cdp_url,
                channel=channel,
                profile_key=resolved_profile_key,
                profile_dir=profile_dir,
                login_wait_seconds=resolved_login_wait_seconds,
            )
            execution_mode = "attached_cdp"
        else:
            result = cli.run_live_search_capture(
                task=task,
                query=resolved_source_keyword,
                pages=resolved_pages,
                channel=channel,
                headless=headless,
                profile_key=resolved_profile_key,
                profile_dir=profile_dir,
                login_wait_seconds=resolved_login_wait_seconds,
            )
            execution_mode = "persistent_context"
    except Exception as exc:
        raise XianyuOnboardingDiscoveryError(str(exc)) from exc

    return {
        "sourcePlatform": "xianyu",
        "sourceKeyword": resolved_source_keyword,
        "task": {
            "id": getattr(task, "id", None),
            "taskKey": getattr(task, "task_key", None),
            "businessDomain": getattr(task, "business_domain", None),
            "displayName": getattr(task, "display_name", None),
        },
        "profile": {
            "profileKey": resolved_profile_key,
            "channel": channel,
            "headless": headless,
            "configuredCdpUrl": configured_cdp_url,
            "resolvedCdpUrl": resolved_cdp_url,
            "cdpFallbackReason": cdp_fallback_reason,
        },
        "executionMode": execution_mode,
        "loginWaitSeconds": resolved_login_wait_seconds,
        "run": {
            "runId": str(result["run_id"]),
            "pagesSucceeded": int(result["pages_succeeded"]),
            "pagesAttempted": int(result["pages_attempted"]),
        },
    }


def _resolve_discovery_task(
    *,
    cli: SimpleNamespace,
    task_key: str | None,
    business_domain: str | None,
) -> CrawlTask:
    resolved_task_key = (task_key or "").strip()
    if resolved_task_key:
        try:
            return cli.get_task_or_raise(resolved_task_key)
        except Exception as exc:
            raise XianyuOnboardingDiscoveryError(str(exc)) from exc

    resolved_business_domain = (business_domain or "").strip()
    if resolved_business_domain:
        scope_keys = compatible_scope_keys(resolved_business_domain)
        with session_scope() as session:
            stmt = select(CrawlTask).where(CrawlTask.source_platform == "xianyu")
            stmt = stmt.where(CrawlTask.business_domain.in_(scope_keys))
            task = session.execute(
                stmt.order_by(case((CrawlTask.status == "active", 0), else_=1), CrawlTask.id.asc()).limit(1)
            ).scalar_one_or_none()
            if task is not None:
                session.expunge(task)
                return task

    default_task_key = str(cli.get_settings().default_task_key)
    try:
        return cli.get_task_or_raise(default_task_key)
    except Exception as exc:
        raise XianyuOnboardingDiscoveryError(
            f"Unable to resolve discovery task. default_task_key={default_task_key}"
        ) from exc


def _load_cli_helpers() -> SimpleNamespace:
    from ... import cli as collector_cli

    return SimpleNamespace(
        SearchPlanEntry=collector_cli.SearchPlanEntry,
        get_settings=collector_cli.get_settings,
        get_task_or_raise=collector_cli.get_task_or_raise,
        load_profile_settings=collector_cli.load_profile_settings,
        resolve_cdp_url=collector_cli.resolve_cdp_url,
        run_live_search_capture=collector_cli.run_live_search_capture,
        run_search_plan_in_attached_tab=collector_cli.run_search_plan_in_attached_tab,
    )
