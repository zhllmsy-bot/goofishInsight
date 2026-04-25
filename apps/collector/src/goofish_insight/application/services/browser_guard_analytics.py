from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from ...db import session_scope
from ...logging import get_logger
from ...models import BrowserGuardEvent, BrowserJobAttempt
from .collector_browser import infer_auth_state_from_error_message

logger = get_logger(__name__)

TEST_TASK_PREFIXES = ("task-", "smoke-")
_WARNED_MISSING_RELATIONS: set[str] = set()


def _is_missing_relation_error(exc: Exception) -> bool:
    raw = str(exc)
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    return sqlstate == "42P01" or "UndefinedTable" in raw or "does not exist" in raw


def _warn_missing_relation_once(table_name: str) -> None:
    if table_name in _WARNED_MISSING_RELATIONS:
        return
    _WARNED_MISSING_RELATIONS.add(table_name)
    logger.warning(
        "browser guard analytics table missing; migration not applied yet",
        extra={"table_name": table_name},
    )


def normalize_browser_attempt_query(value: str | None) -> str | None:
    normalized = " ".join(str(value or "").strip().split())
    lowered = normalized.lower()
    return lowered or None


def is_browser_guard_test_task(task_key: str | None) -> bool:
    normalized = str(task_key or "").strip().lower()
    if not normalized:
        return False
    return any(normalized.startswith(prefix) for prefix in TEST_TASK_PREFIXES)


def classify_browser_guard_error_signature(error_message: str | None) -> str | None:
    raw = str(error_message or "").strip()
    if not raw:
        return None

    upper = raw.upper()
    if "FAIL_SYS_USER_VALIDATE" in upper:
        return "FAIL_SYS_USER_VALIDATE"
    if "RGV587_ERROR" in upper:
        return "RGV587_ERROR"

    lowered = raw.lower()
    if "executecaptcha" in lowered:
        return "EXECUTE_CAPTCHA"
    if "baxia" in lowered:
        return "BAXIA"
    if "nocaptcha" in lowered:
        return "NO_CAPTCHA"
    if "punish" in lowered:
        return "PUNISH"
    if any(
        token in lowered
        for token in (
            "connect econnrefused",
            "browsertype.connect_over_cdp",
            "target page, context or browser has been closed",
            "connection closed while reading from the driver",
        )
    ):
        return "BROWSER_DISCONNECT"
    if any(token in lowered for token in ("login required", "需要登录", "登录")):
        return "LOGIN_REQUIRED"
    if any(token in lowered for token in ("risk control", "风控")):
        return "RISK_CONTROL_GENERIC"
    return None


def persist_browser_job_attempt(
    *,
    profile_key: str,
    feature: str,
    attempt_outcome: str,
    stage: str = "execute",
    scope_key: str | None = None,
    task_key: str | None = None,
    task_query_id: str | None = None,
    query: str | None = None,
    business_domain: str | None = None,
    auth_state: str | None = None,
    is_probe: bool = False,
    guard_blocked: bool = False,
    browser_ready: bool | None = None,
    job_run_id: UUID | None = None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> bool:
    resolved_auth_state = str(auth_state or "").strip() or infer_auth_state_from_error_message(error_message)
    resolved_task_key = str(task_key or "").strip() or None
    resolved_query = str(query or "").strip() or None
    resolved_scope_key = str(scope_key or "").strip() or None
    resolved_business_domain = str(business_domain or "").strip() or None
    resolved_error_message = str(error_message or "").strip() or None
    resolved_attempt_outcome = str(attempt_outcome or "").strip().lower() or "unknown"
    resolved_stage = str(stage or "").strip().lower() or "execute"
    resolved_profile_key = str(profile_key or "").strip() or "default"
    resolved_feature = str(feature or "").strip().lower() or "unknown"
    resolved_task_query_id = str(task_query_id or "").strip() or None
    resolved_metadata = dict(metadata or {})
    resolved_occurred_at = occurred_at or datetime.now(UTC)

    try:
        with session_scope() as session:
            session.add(
                BrowserJobAttempt(
                    occurred_at=resolved_occurred_at,
                    profile_key=resolved_profile_key,
                    feature=resolved_feature,
                    stage=resolved_stage,
                    scope_key=resolved_scope_key,
                    task_key=resolved_task_key,
                    task_query_id=resolved_task_query_id,
                    query=resolved_query,
                    normalized_query=normalize_browser_attempt_query(resolved_query),
                    business_domain=resolved_business_domain,
                    attempt_outcome=resolved_attempt_outcome,
                    auth_state=resolved_auth_state,
                    is_probe=bool(is_probe),
                    is_test_task=is_browser_guard_test_task(resolved_task_key),
                    guard_blocked=bool(guard_blocked),
                    browser_ready=browser_ready,
                    job_run_id=job_run_id,
                    error_signature=classify_browser_guard_error_signature(resolved_error_message),
                    error_message=resolved_error_message,
                    metadata_json=resolved_metadata,
                )
            )
        return True
    except ProgrammingError as exc:
        if _is_missing_relation_error(exc):
            _warn_missing_relation_once("browser_job_attempt")
            return False
        logger.exception(
            "failed to persist browser job attempt",
            extra={
                "profile_key": resolved_profile_key,
                "feature": resolved_feature,
                "stage": resolved_stage,
                "attempt_outcome": resolved_attempt_outcome,
            },
        )
        return False
    except Exception:
        logger.exception(
            "failed to persist browser job attempt",
            extra={
                "profile_key": resolved_profile_key,
                "feature": resolved_feature,
                "stage": resolved_stage,
                "attempt_outcome": resolved_attempt_outcome,
            },
        )
        return False


def persist_browser_guard_event(
    *,
    profile_key: str,
    feature: str,
    event_type: str,
    auth_state: str | None = None,
    scope_key: str | None = None,
    consecutive_hits: int = 0,
    backoff_seconds: int | None = None,
    next_retry_at: datetime | None = None,
    keep_page_open: bool | None = None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> bool:
    resolved_feature = str(feature or "").strip().lower() or "unknown"
    resolved_profile_key = str(profile_key or "").strip() or "default"
    resolved_event_type = str(event_type or "").strip().lower() or "unknown"
    resolved_auth_state = str(auth_state or "").strip() or infer_auth_state_from_error_message(error_message)
    resolved_scope_key = str(scope_key or "").strip() or None
    resolved_error_message = str(error_message or "").strip() or None
    resolved_metadata = dict(metadata or {})
    resolved_occurred_at = occurred_at or datetime.now(UTC)

    try:
        with session_scope() as session:
            session.add(
                BrowserGuardEvent(
                    occurred_at=resolved_occurred_at,
                    profile_key=resolved_profile_key,
                    feature=resolved_feature,
                    scope_key=resolved_scope_key,
                    event_type=resolved_event_type,
                    auth_state=resolved_auth_state,
                    consecutive_hits=max(int(consecutive_hits or 0), 0),
                    backoff_seconds=backoff_seconds,
                    next_retry_at=next_retry_at,
                    keep_page_open=keep_page_open,
                    error_signature=classify_browser_guard_error_signature(resolved_error_message),
                    error_message=resolved_error_message,
                    metadata_json=resolved_metadata,
                )
            )
        return True
    except ProgrammingError as exc:
        if _is_missing_relation_error(exc):
            _warn_missing_relation_once("browser_guard_event")
            return False
        logger.exception(
            "failed to persist browser guard event",
            extra={
                "profile_key": resolved_profile_key,
                "feature": resolved_feature,
                "event_type": resolved_event_type,
            },
        )
        return False
    except Exception:
        logger.exception(
            "failed to persist browser guard event",
            extra={
                "profile_key": resolved_profile_key,
                "feature": resolved_feature,
                "event_type": resolved_event_type,
            },
        )
        return False


def _fetch_mapping_rows(*, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            return [dict(row) for row in session.execute(text(sql), params).mappings().all()]
    except ProgrammingError as exc:
        if _is_missing_relation_error(exc):
            relation = "browser_job_attempt_or_browser_guard_event"
            if "browser_guard_event" in sql:
                relation = "browser_guard_event"
            elif "browser_job_attempt" in sql:
                relation = "browser_job_attempt"
            _warn_missing_relation_once(relation)
            return []
        raise


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return int(normalized)
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(child) for child in value]
    if isinstance(value, tuple):
        return [_json_safe_value(child) for child in value]
    return value


def build_browser_guard_pattern_report(
    *,
    lookback_hours: int,
    top_n: int,
    now: datetime | None = None,
    profile_key: str | None = None,
    include_tests: bool = False,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    cutoff = resolved_now - timedelta(hours=max(int(lookback_hours), 1))
    params: dict[str, Any] = {"cutoff": cutoff, "top_n": max(int(top_n), 1)}

    attempt_filters = ["occurred_at >= :cutoff"]
    legacy_filters = ["occurred_at >= :cutoff"]
    guard_filters = ["occurred_at >= :cutoff"]
    if profile_key:
        params["profile_key"] = str(profile_key or "").strip()
        attempt_filters.append("profile_key = :profile_key")
        legacy_filters.append("profile_key = :profile_key")
        guard_filters.append("profile_key = :profile_key")
    if not include_tests:
        attempt_filters.append("coalesce(is_test_task, false) = false")
        legacy_filters.append("coalesce(task_key, '') not like 'task-%' and coalesce(task_key, '') not like 'smoke-%'")
        guard_filters.append("coalesce((metadata_json ->> 'is_test_task')::boolean, false) = false")

    attempt_where = " and ".join(attempt_filters)
    legacy_where = " and ".join(legacy_filters)
    guard_where = " and ".join(guard_filters)

    attempt_summary_rows = _fetch_mapping_rows(
        sql=f"""
            select
              count(*) as total_attempts,
              count(*) filter (
                where coalesce(auth_state, '') = 'risk_control'
                   or attempt_outcome in ('risk_control', 'manual_verification_required')
              ) as risk_hits,
              count(*) filter (where attempt_outcome = 'completed') as completed_attempts,
              count(*) filter (where attempt_outcome = 'blocked_by_guard') as blocked_attempts,
              count(*) filter (where guard_blocked) as guard_blocked_attempts,
              count(distinct profile_key) as unique_profiles,
              count(distinct task_key) filter (where task_key is not null and task_key <> '') as unique_tasks,
              count(distinct normalized_query) filter (where normalized_query is not null and normalized_query <> '') as unique_queries,
              min(occurred_at) as first_attempt_at,
              max(occurred_at) as last_attempt_at
            from browser_job_attempt
            where {attempt_where}
        """,
        params=params,
    )
    attempt_summary = attempt_summary_rows[0] if attempt_summary_rows else {}
    total_attempts = int(attempt_summary.get("total_attempts") or 0)
    risk_hits = int(attempt_summary.get("risk_hits") or 0)
    attempt_summary["risk_hit_rate"] = round(risk_hits / total_attempts, 4) if total_attempts > 0 else None

    feature_stage_breakdown = _fetch_mapping_rows(
        sql=f"""
            select
              feature,
              stage,
              count(*) as attempts,
              count(*) filter (
                where coalesce(auth_state, '') = 'risk_control'
                   or attempt_outcome in ('risk_control', 'manual_verification_required')
              ) as risk_hits,
              count(*) filter (where attempt_outcome = 'completed') as completed_attempts,
              count(*) filter (where attempt_outcome = 'failed') as failed_attempts,
              count(*) filter (where guard_blocked or attempt_outcome = 'blocked_by_guard') as blocked_attempts
            from browser_job_attempt
            where {attempt_where}
            group by feature, stage
            order by risk_hits desc, attempts desc, feature, stage
            limit :top_n
        """,
        params=params,
    )
    for row in feature_stage_breakdown:
        attempts = int(row.get("attempts") or 0)
        row["risk_hit_rate"] = round(int(row.get("risk_hits") or 0) / attempts, 4) if attempts > 0 else None

    task_breakdown = _fetch_mapping_rows(
        sql=f"""
            select
              task_key,
              count(*) as attempts,
              count(*) filter (
                where coalesce(auth_state, '') = 'risk_control'
                   or attempt_outcome in ('risk_control', 'manual_verification_required')
              ) as risk_hits,
              count(distinct normalized_query) filter (where normalized_query is not null and normalized_query <> '') as distinct_queries
            from browser_job_attempt
            where {attempt_where}
              and task_key is not null
              and task_key <> ''
            group by task_key
            order by risk_hits desc, attempts desc, task_key
            limit :top_n
        """,
        params=params,
    )
    for row in task_breakdown:
        attempts = int(row.get("attempts") or 0)
        row["risk_hit_rate"] = round(int(row.get("risk_hits") or 0) / attempts, 4) if attempts > 0 else None

    hourly_attempt_distribution = _fetch_mapping_rows(
        sql=f"""
            select
              to_char(occurred_at at time zone 'Asia/Shanghai', 'YYYY-MM-DD HH24:00') as hour_slot,
              count(*) as attempts,
              count(*) filter (
                where coalesce(auth_state, '') = 'risk_control'
                   or attempt_outcome in ('risk_control', 'manual_verification_required')
              ) as risk_hits
            from browser_job_attempt
            where {attempt_where}
            group by 1
            order by hour_slot desc
            limit :top_n
        """,
        params=params,
    )
    for row in hourly_attempt_distribution:
        attempts = int(row.get("attempts") or 0)
        row["risk_hit_rate"] = round(int(row.get("risk_hits") or 0) / attempts, 4) if attempts > 0 else None

    error_signature_breakdown = _fetch_mapping_rows(
        sql=f"""
            select
              error_signature,
              count(*) as attempts
            from browser_job_attempt
            where {attempt_where}
              and error_signature is not null
              and error_signature <> ''
            group by error_signature
            order by attempts desc, error_signature
            limit :top_n
        """,
        params=params,
    )

    recovery_summary = _fetch_mapping_rows(
        sql=f"""
            with risk_events as (
              select id, occurred_at, profile_key, feature
              from browser_guard_event
              where {guard_where}
                and event_type = 'risk_control'
            ),
            recovered_events as (
              select occurred_at, profile_key, feature
              from browser_guard_event
              where {guard_where}
                and event_type = 'recovered'
            ),
            paired as (
              select
                risk_events.feature,
                risk_events.occurred_at as risk_at,
                min(recovered_events.occurred_at) as recovered_at
              from risk_events
              left join recovered_events
                on recovered_events.profile_key = risk_events.profile_key
               and recovered_events.feature = risk_events.feature
               and recovered_events.occurred_at > risk_events.occurred_at
              group by risk_events.id, risk_events.feature, risk_events.occurred_at
            )
            select
              feature,
              count(*) as risk_events,
              count(recovered_at) as recovered_events,
              round(avg(extract(epoch from (recovered_at - risk_at)))::numeric, 2) as avg_recovery_seconds,
              percentile_cont(0.5) within group (
                order by extract(epoch from (recovered_at - risk_at))
              ) filter (where recovered_at is not null) as p50_recovery_seconds
            from paired
            group by feature
            order by risk_events desc, feature
        """,
        params=params,
    )

    legacy_summary_rows = _fetch_mapping_rows(
        sql=f"""
            select
              count(*) as total_events,
              count(distinct task_key) filter (where task_key is not null and task_key <> '') as unique_tasks,
              count(distinct normalized_query) filter (where normalized_query is not null and normalized_query <> '') as unique_queries,
              min(occurred_at) as first_event_at,
              max(occurred_at) as last_event_at
            from batch_collect_risk_event
            where {legacy_where}
        """,
        params=params,
    )
    legacy_summary = legacy_summary_rows[0] if legacy_summary_rows else {}

    legacy_top_tasks = _fetch_mapping_rows(
        sql=f"""
            select
              task_key,
              count(*) as risk_hits,
              count(distinct normalized_query) filter (where normalized_query is not null and normalized_query <> '') as distinct_queries
            from batch_collect_risk_event
            where {legacy_where}
              and task_key is not null
              and task_key <> ''
            group by task_key
            order by risk_hits desc, task_key
            limit :top_n
        """,
        params=params,
    )

    legacy_backoff_distribution = _fetch_mapping_rows(
        sql=f"""
            select
              backoff_seconds,
              count(*) as risk_hits,
              min(consecutive_risk_hits) as min_hits,
              max(consecutive_risk_hits) as max_hits
            from batch_collect_risk_event
            where {legacy_where}
            group by backoff_seconds
            order by risk_hits desc, backoff_seconds
            limit :top_n
        """,
        params=params,
    )

    legacy_hourly_distribution = _fetch_mapping_rows(
        sql=f"""
            select
              to_char(occurred_at at time zone 'Asia/Shanghai', 'YYYY-MM-DD HH24:00') as hour_slot,
              count(*) as risk_hits
            from batch_collect_risk_event
            where {legacy_where}
            group by 1
            order by hour_slot desc
            limit :top_n
        """,
        params=params,
    )

    legacy_gap_rows = _fetch_mapping_rows(
        sql=f"""
            with ordered as (
              select
                occurred_at,
                lag(occurred_at) over (
                  partition by coalesce(profile_key, '<null>')
                  order by occurred_at, id
                ) as previous_occurred_at
              from batch_collect_risk_event
              where {legacy_where}
            )
            select
              count(*) as gap_count,
              round(avg(extract(epoch from (occurred_at - previous_occurred_at)))::numeric, 2) as avg_gap_seconds,
              percentile_cont(0.5) within group (
                order by extract(epoch from (occurred_at - previous_occurred_at))
              ) as p50_gap_seconds,
              percentile_cont(0.9) within group (
                order by extract(epoch from (occurred_at - previous_occurred_at))
              ) as p90_gap_seconds
            from ordered
            where previous_occurred_at is not null
        """,
        params=params,
    )

    note = None
    if total_attempts <= 0:
        note = (
            "browser_job_attempt has no rows for the requested window yet; "
            "attempt-level hit rates will become available after new collector runs."
        )

    return _json_safe_value(
        {
        "generated_at": resolved_now.isoformat(),
        "lookback_hours": int(lookback_hours),
        "profile_key": str(profile_key or "").strip() or None,
        "include_tests": bool(include_tests),
        "attempt_summary": attempt_summary,
        "feature_stage_breakdown": feature_stage_breakdown,
        "task_breakdown": task_breakdown,
        "hourly_attempt_distribution": hourly_attempt_distribution,
        "error_signature_breakdown": error_signature_breakdown,
        "recovery_summary": recovery_summary,
        "legacy_batch_risk_event_summary": {
            **legacy_summary,
            "top_tasks": legacy_top_tasks,
            "backoff_distribution": legacy_backoff_distribution,
            "hourly_distribution": legacy_hourly_distribution,
            "gap_summary": legacy_gap_rows[0] if legacy_gap_rows else {},
        },
        "note": note,
        }
    )
