from __future__ import annotations

import fcntl
import json
import os
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import typer
from sqlalchemy import select

from ...db import session_scope
from ...models import BatchCollectRiskEvent
from .collector_runtime import (
    finish_collector_job_run,
    start_collector_job_run,
    upsert_collector_job_checkpoint,
    upsert_collector_job_run_state,
)
from .browser_guard import (
    build_browser_guard_metadata,
    evaluate_browser_guard_preflight,
    format_browser_guard_preflight_message,
    record_browser_guard_observation,
)
from .browser_guard_analytics import persist_browser_job_attempt
from .quality_metrics import QualityMetricsService

BATCH_COLLECT_ALREADY_RUNNING_EXIT_CODE = 18


def _resolve_batch_query_configs(
    *,
    task_config: dict[str, Any],
    runtime_config: dict[str, Any],
) -> list[dict[str, Any]]:
    runtime_queries = list(runtime_config.get("queries") or [])
    config_queries = list(task_config.get("queries") or [])
    has_materialized_runtime_queries = any(str(query.get("status") or "").upper() != "LEGACY" for query in runtime_queries)

    if has_materialized_runtime_queries:
        return [
            {
                "id": query.get("id"),
                "query": str(query["query"]),
                "pages": int(query.get("pages", task_config.get("paging_limit", 1))),
            }
            for query in runtime_queries
            if str(query.get("query", "")).strip()
        ]

    if config_queries:
        return [
            {
                "id": query.get("id"),
                "query": str(query["query"]),
                "pages": int(query.get("pages", task_config.get("paging_limit", 1))),
            }
            for query in config_queries
            if str(query.get("query", "")).strip()
        ]

    return [
        {
            "id": query.get("id"),
            "query": str(query["query"]),
            "pages": int(query.get("pages", task_config.get("paging_limit", 1))),
        }
        for query in runtime_queries
        if str(query.get("query", "")).strip()
    ]


def _default_batch_collect_lock_path() -> Path:
    return Path("reports/runtime/locks/batch_collect.lock")


@contextmanager
def _batch_collect_process_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError(f"collect-batch already running; lock_path={lock_path}") from exc

    payload = {
        "pid": os.getpid(),
        "acquired_at": datetime.now(UTC).isoformat(),
    }
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    handle.flush()

    try:
        yield
    finally:
        try:
            handle.seek(0)
            handle.truncate()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _clamp_batch_plan_pages_for_run(*, pages: int, max_pages_per_plan: int) -> int:
    resolved_cap = max(int(max_pages_per_plan), 1)
    resolved_pages = int(pages)
    if resolved_pages <= 0:
        return resolved_cap
    return min(resolved_pages, resolved_cap)


def _build_batch_cursor_scope_key(
    *,
    config_path: Path,
    profile_key: str,
    only_task: str | None,
) -> str:
    resolved_config = str(Path(config_path).expanduser().resolve())
    resolved_profile = str(profile_key or "").strip() or "default"
    resolved_only_task = str(only_task or "").strip() or "*"
    return f"{resolved_config}|{resolved_profile}|{resolved_only_task}"


def _load_batch_cursor_state(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"cursors": {}}
    except json.JSONDecodeError:
        return {"cursors": {}}
    if not isinstance(raw, dict):
        return {"cursors": {}}
    raw_cursors = raw.get("cursors")
    if not isinstance(raw_cursors, dict):
        return {"cursors": {}}
    cursors: dict[str, int] = {}
    for key, value in raw_cursors.items():
        try:
            resolved = int(value)
        except (TypeError, ValueError):
            continue
        if resolved < 0:
            continue
        cursors[str(key)] = resolved
    return {"cursors": cursors}


def _save_batch_cursor_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _select_rotating_plan_window(
    *,
    plans: list[Any],
    max_plans_per_run: int,
    cursor_state_path: Path | None,
    scope_key: str,
    checkpoint_mode: str = "eager",
) -> tuple[list[Any], dict[str, Any]]:
    total = len(plans)
    if total <= 0 or max_plans_per_run <= 0 or total <= max_plans_per_run:
        return plans, {
            "selected_count": total,
            "total_count": total,
            "cursor_before": 0,
            "cursor_after": 0 if total <= 0 else total % max(total, 1),
            "state_path": str(cursor_state_path) if cursor_state_path else None,
        }

    window = min(max_plans_per_run, total)
    if cursor_state_path is None:
        selected = plans[:window]
        return selected, {
            "selected_count": len(selected),
            "total_count": total,
            "cursor_before": 0,
            "cursor_after": window % total,
            "state_path": None,
        }

    state = _load_batch_cursor_state(cursor_state_path)
    cursors = state.setdefault("cursors", {})
    cursor_before = int(cursors.get(scope_key, 0) or 0) % total
    selected = [plans[(cursor_before + index) % total] for index in range(window)]
    cursor_after = (cursor_before + window) % total
    if checkpoint_mode == "eager":
        cursors[scope_key] = cursor_after
        state["updated_at"] = datetime.now(UTC).isoformat()
        _save_batch_cursor_state(cursor_state_path, state)
    return selected, {
        "selected_count": len(selected),
        "total_count": total,
        "cursor_before": cursor_before,
        "cursor_after": cursor_after,
        "state_path": str(cursor_state_path),
    }


def _normalize_checkpoint_mode(value: str | None) -> str:
    resolved = str(value or "").strip().lower() or "eager"
    if resolved not in {"eager", "commit"}:
        raise typer.BadParameter("checkpoint_mode must be eager or commit")
    return resolved


def _normalize_job_phase(value: str | None) -> str:
    resolved = str(value or "").strip().lower() or "batch"
    return resolved


def _commit_rotating_plan_window(
    *,
    cursor_state_path: Path,
    scope_key: str,
    cursor_after: int,
) -> None:
    state = _load_batch_cursor_state(cursor_state_path)
    cursors = state.setdefault("cursors", {})
    cursors[scope_key] = max(int(cursor_after), 0)
    state["updated_at"] = datetime.now(UTC).isoformat()
    _save_batch_cursor_state(cursor_state_path, state)


def _has_non_completed_outcome(outcomes: list[Any]) -> bool:
    return any(str(_extract_outcome_field(outcome, "status", "") or "").strip().lower() != "completed" for outcome in outcomes)


def _summarize_outcomes(outcomes: list[Any]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for outcome in outcomes:
        status = str(_extract_outcome_field(outcome, "status", "") or "unknown").strip().lower() or "unknown"
        counter[status] += 1
    return {
        "completed_count": int(counter.get("completed", 0)),
        "failed_count": int(counter.get("failed", 0)),
        "manual_verification_required_count": int(counter.get("manual_verification_required", 0)),
        "outcome_count": int(sum(counter.values())),
    }


def _record_batch_collect_quality_metrics(
    *,
    now: datetime,
    outcomes: list[Any],
    risk_stats: dict[str, int],
    task_key: str | None,
) -> None:
    outcome_summary = _summarize_outcomes(outcomes)
    outcome_count = int(outcome_summary["outcome_count"])
    if outcome_count <= 0:
        return

    completed_count = int(outcome_summary["completed_count"])
    success_rate = completed_count / outcome_count
    risk_hit_rate = int(risk_stats.get("risk_event_count") or 0) / outcome_count

    QualityMetricsService.record_metric(
        metric_date=now.date(),
        metric_hour=now.hour,
        metric_key="collection_success_rate",
        metric_value=success_rate,
        task_key=task_key,
        metadata={
            "completed_count": completed_count,
            "outcome_count": outcome_count,
        },
    )
    QualityMetricsService.record_metric(
        metric_date=now.date(),
        metric_hour=now.hour,
        metric_key="risk_hit_rate",
        metric_value=risk_hit_rate,
        task_key=task_key,
        metadata={
            "risk_event_count": int(risk_stats.get("risk_event_count") or 0),
            "outcome_count": outcome_count,
        },
    )


def _normalize_risk_query(value: str | None) -> str:
    normalized = " ".join(str(value or "").strip().split())
    return normalized.lower()


def _plan_identity_fields(plan: Any) -> dict[str, str]:
    task_key = str(getattr(getattr(plan, "task", None), "task_key", "") or "").strip() or "*"
    business_domain = str(getattr(getattr(plan, "task", None), "business_domain", "") or "").strip() or ""
    task_query_id_value = getattr(plan, "task_query_id", None)
    task_query_id = str(task_query_id_value).strip() if task_query_id_value is not None else "*"
    query = str(getattr(plan, "query", "") or "").strip()
    return {
        "task_key": task_key,
        "task_query_id": task_query_id or "*",
        "query": query,
        "business_domain": business_domain,
    }


def _build_plan_risk_key(*, scope_key: str, plan: Any) -> str:
    identity = _plan_identity_fields(plan)
    normalized_query = _normalize_risk_query(identity["query"])
    return f"{scope_key}|{identity['task_key']}|{identity['task_query_id']}|{normalized_query}"


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_batch_risk_backoff_state(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"queries": {}}
    except json.JSONDecodeError:
        return {"queries": {}}
    if not isinstance(raw, dict):
        return {"queries": {}}
    raw_queries = raw.get("queries")
    if not isinstance(raw_queries, dict):
        return {"queries": {}}

    queries: dict[str, dict[str, Any]] = {}
    for key, value in raw_queries.items():
        if not isinstance(value, dict):
            continue
        consecutive_risk_hits = 0
        try:
            consecutive_risk_hits = max(int(value.get("consecutive_risk_hits") or 0), 0)
        except (TypeError, ValueError):
            consecutive_risk_hits = 0
        next_retry_at = value.get("next_retry_at")
        if next_retry_at and _parse_iso_datetime(next_retry_at) is None:
            next_retry_at = None
        queries[str(key)] = {
            "consecutive_risk_hits": consecutive_risk_hits,
            "next_retry_at": next_retry_at,
            "last_risk_at": value.get("last_risk_at"),
            "last_success_at": value.get("last_success_at"),
            "last_error": value.get("last_error"),
            "updated_at": value.get("updated_at"),
        }
    return {"queries": queries}


def _save_batch_risk_backoff_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _compute_risk_backoff_seconds(
    *,
    consecutive_risk_hits: int,
    base_seconds: int,
    max_seconds: int,
) -> int:
    resolved_base = max(int(base_seconds), 1)
    resolved_max = max(int(max_seconds), resolved_base)
    exponent = max(int(consecutive_risk_hits) - 1, 0)
    wait_seconds = resolved_base * (2**exponent)
    return min(wait_seconds, resolved_max)


def _filter_plans_by_risk_backoff(
    *,
    plans: list[Any],
    scope_key: str,
    risk_state: dict[str, Any],
    now: datetime,
) -> tuple[list[Any], list[dict[str, Any]]]:
    queries = risk_state.setdefault("queries", {})
    selected: list[Any] = []
    skipped: list[dict[str, Any]] = []
    for plan in plans:
        key = _build_plan_risk_key(scope_key=scope_key, plan=plan)
        entry = queries.get(key)
        if not isinstance(entry, dict):
            selected.append(plan)
            continue
        next_retry_at = _parse_iso_datetime(entry.get("next_retry_at"))
        if next_retry_at is None or next_retry_at <= now:
            selected.append(plan)
            continue
        wait_seconds = max(int((next_retry_at - now).total_seconds()), 1)
        identity = _plan_identity_fields(plan)
        skipped.append(
            {
                "task_key": identity["task_key"],
                "task_query_id": identity["task_query_id"],
                "query": identity["query"],
                "wait_seconds": wait_seconds,
                "next_retry_at": next_retry_at.isoformat(),
            }
        )
    return selected, skipped


def _append_jsonl_record(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _persist_batch_risk_event_to_db(payload: dict[str, Any]) -> bool:
    occurred_at = _parse_iso_datetime(payload.get("occurred_at")) or datetime.now(UTC)
    query = str(payload.get("query") or "").strip() or None
    normalized_query = _normalize_risk_query(query)
    with session_scope() as session:
        session.add(
            BatchCollectRiskEvent(
                event_type=str(payload.get("event_type") or "risk_control"),
                occurred_at=occurred_at,
                scope_key=str(payload.get("scope_key") or ""),
                config_path=str(payload.get("config_path") or "") or None,
                profile_key=str(payload.get("profile_key") or "") or None,
                task_key=str(payload.get("task_key") or "") or None,
                task_query_id=str(payload.get("task_query_id") or "") or None,
                query=query,
                normalized_query=normalized_query or None,
                auth_state=str(payload.get("auth_state") or "") or None,
                consecutive_risk_hits=max(int(payload.get("consecutive_risk_hits") or 0), 0),
                backoff_seconds=int(payload.get("backoff_seconds")) if payload.get("backoff_seconds") is not None else None,
                next_retry_at=_parse_iso_datetime(payload.get("next_retry_at")),
                error_message=str(payload.get("error_message") or "") or None,
                metadata_json=dict(payload),
            )
        )
    return True


def _looks_like_risk_control_error(error_message: str | None) -> bool:
    lowered = str(error_message or "").strip().lower()
    if not lowered:
        return False
    return any(token in lowered for token in ("risk control", "rgv587_error", "baxia", "executecaptcha", "风控"))


def _extract_outcome_field(outcome: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(outcome, dict):
        return outcome.get(field_name, default)
    return getattr(outcome, field_name, default)


def _apply_plan_outcomes_to_risk_backoff_state(
    *,
    outcomes: list[Any],
    scope_key: str,
    risk_state: dict[str, Any],
    now: datetime,
    risk_backoff_base_seconds: int,
    risk_backoff_max_seconds: int,
    risk_event_log_path: Path,
    profile_key: str,
    config_path: Path,
) -> dict[str, int]:
    queries = risk_state.setdefault("queries", {})
    risk_event_count = 0
    recovered_count = 0
    db_persisted_count = 0
    db_persist_failed_count = 0

    for outcome in outcomes:
        plan = _extract_outcome_field(outcome, "plan")
        if plan is None:
            continue
        status = str(_extract_outcome_field(outcome, "status", "") or "").strip().lower()
        auth_state = str(_extract_outcome_field(outcome, "auth_state", "") or "").strip().lower()
        error_message = str(_extract_outcome_field(outcome, "error_message", "") or "").strip() or None
        key = _build_plan_risk_key(scope_key=scope_key, plan=plan)
        identity = _plan_identity_fields(plan)

        if status == "completed":
            existing = queries.get(key)
            if isinstance(existing, dict):
                prior_hits = max(int(existing.get("consecutive_risk_hits") or 0), 0)
                if prior_hits > 0:
                    recovered_count += 1
                existing["consecutive_risk_hits"] = 0
                existing["next_retry_at"] = None
                existing["last_success_at"] = now.isoformat()
                existing["updated_at"] = now.isoformat()
                queries[key] = existing
            continue

        is_risk_control = auth_state == "risk_control" or _looks_like_risk_control_error(error_message)
        if not is_risk_control:
            continue

        existing = queries.get(key) if isinstance(queries.get(key), dict) else {}
        previous_hits = max(int(existing.get("consecutive_risk_hits") or 0), 0)
        current_hits = previous_hits + 1
        wait_seconds = _compute_risk_backoff_seconds(
            consecutive_risk_hits=current_hits,
            base_seconds=risk_backoff_base_seconds,
            max_seconds=risk_backoff_max_seconds,
        )
        next_retry_at = now + timedelta(seconds=wait_seconds)
        existing["consecutive_risk_hits"] = current_hits
        existing["next_retry_at"] = next_retry_at.isoformat()
        existing["last_risk_at"] = now.isoformat()
        existing["last_error"] = error_message
        existing["updated_at"] = now.isoformat()
        queries[key] = existing
        risk_event_count += 1
        event_payload = {
            "occurred_at": now.isoformat(),
            "event_type": "risk_control",
            "scope_key": scope_key,
            "config_path": str(Path(config_path).expanduser().resolve()),
            "profile_key": profile_key,
            "task_key": identity["task_key"],
            "task_query_id": identity["task_query_id"],
            "query": identity["query"],
            "auth_state": auth_state or "risk_control",
            "consecutive_risk_hits": current_hits,
            "backoff_seconds": wait_seconds,
            "next_retry_at": next_retry_at.isoformat(),
            "error_message": error_message,
        }
        _append_jsonl_record(risk_event_log_path, event_payload)
        try:
            if _persist_batch_risk_event_to_db(event_payload):
                db_persisted_count += 1
        except Exception:
            db_persist_failed_count += 1

    risk_state["updated_at"] = now.isoformat()
    return {
        "risk_event_count": risk_event_count,
        "recovered_count": recovered_count,
        "db_persisted_count": db_persisted_count,
        "db_persist_failed_count": db_persist_failed_count,
    }


def _apply_plan_outcomes_to_browser_guard(
    *,
    outcomes: list[Any],
    profile_key: str,
    state_path: Path,
    event_log_path: Path,
    base_seconds: int,
    max_seconds: int,
) -> dict[str, Any]:
    latest_decision: dict[str, Any] = {}
    saw_browser_guard_event = False
    saw_success = False
    for outcome in outcomes:
        plan = _extract_outcome_field(outcome, "plan")
        status = str(_extract_outcome_field(outcome, "status", "") or "").strip().lower()
        auth_state = str(_extract_outcome_field(outcome, "auth_state", "") or "").strip().lower() or None
        error_message = str(_extract_outcome_field(outcome, "error_message", "") or "").strip() or None
        identity = _plan_identity_fields(plan) if plan is not None else {}
        scope_key = "|".join(
            value
            for value in (
                str(identity.get("task_key") or "").strip(),
                str(identity.get("task_query_id") or "").strip(),
                str(identity.get("query") or "").strip(),
            )
            if value
        ) or None

        if status == "completed":
            saw_success = True
            continue

        decision = record_browser_guard_observation(
            profile_key=profile_key,
            feature="collect_batch",
            scope_key=scope_key,
            auth_state=auth_state,
            error_message=error_message,
            state_path=state_path,
            event_log_path=event_log_path,
            base_seconds=base_seconds,
            max_seconds=max_seconds,
        )
        if decision:
            latest_decision = decision
            saw_browser_guard_event = True
            break

    if not saw_browser_guard_event and saw_success:
        latest_decision = record_browser_guard_observation(
            profile_key=profile_key,
            feature="collect_batch",
            auth_state="authenticated",
            state_path=state_path,
            event_log_path=event_log_path,
            base_seconds=base_seconds,
            max_seconds=max_seconds,
        )
    return latest_decision


def _persist_batch_attempt(
    *,
    profile_key: str,
    feature: str,
    stage: str,
    attempt_outcome: str,
    scope_key: str | None,
    task_key: str | None = None,
    task_query_id: str | None = None,
    query: str | None = None,
    business_domain: str | None = None,
    auth_state: str | None = None,
    is_probe: bool = False,
    guard_blocked: bool = False,
    browser_ready: bool | None = None,
    job_run_id=None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> None:
    persist_browser_job_attempt(
        profile_key=profile_key,
        feature=feature,
        stage=stage,
        scope_key=scope_key,
        task_key=task_key,
        task_query_id=task_query_id,
        query=query,
        business_domain=business_domain,
        attempt_outcome=attempt_outcome,
        auth_state=auth_state,
        is_probe=is_probe,
        guard_blocked=guard_blocked,
        browser_ready=browser_ready,
        job_run_id=job_run_id,
        error_message=error_message,
        metadata=metadata,
        occurred_at=occurred_at,
    )


def _persist_batch_attempts_for_outcomes(
    *,
    outcomes: list[Any],
    profile_key: str,
    scope_key: str | None,
    job_run_id,
    stage: str,
    is_probe: bool,
) -> None:
    for outcome in outcomes:
        plan = _extract_outcome_field(outcome, "plan")
        if plan is None:
            continue
        identity = _plan_identity_fields(plan)
        status = str(_extract_outcome_field(outcome, "status", "") or "").strip().lower() or "unknown"
        auth_state = str(_extract_outcome_field(outcome, "auth_state", "") or "").strip().lower() or None
        error_message = str(_extract_outcome_field(outcome, "error_message", "") or "").strip() or None
        attempt_outcome = "completed" if status == "completed" else (auth_state or status or "failed")
        _persist_batch_attempt(
            profile_key=profile_key,
            feature="collect_batch",
            stage=stage,
            scope_key=scope_key,
            task_key=identity.get("task_key"),
            task_query_id=identity.get("task_query_id"),
            query=identity.get("query"),
            business_domain=identity.get("business_domain"),
            attempt_outcome=attempt_outcome,
            auth_state=auth_state,
            is_probe=is_probe,
            job_run_id=job_run_id,
            error_message=error_message,
            metadata={
                "status": status,
                "pages_attempted": _extract_outcome_field(outcome, "pages_attempted"),
                "pages_succeeded": _extract_outcome_field(outcome, "pages_succeeded"),
                "run_id": str(_extract_outcome_field(outcome, "run_id", "") or "") or None,
            },
        )


def _count_active_risk_backoff_entries(*, risk_state: dict[str, Any], now: datetime) -> int:
    queries = risk_state.get("queries")
    if not isinstance(queries, dict):
        return 0
    active = 0
    for value in queries.values():
        if not isinstance(value, dict):
            continue
        next_retry_at = _parse_iso_datetime(value.get("next_retry_at"))
        if next_retry_at and next_retry_at > now:
            active += 1
    return active


def _latest_risk_backoff_metadata(*, risk_state: dict[str, Any], now: datetime) -> dict[str, Any]:
    queries = risk_state.get("queries")
    if not isinstance(queries, dict):
        return {}

    latest_entry: dict[str, Any] | None = None
    latest_next_retry_at: datetime | None = None
    for value in queries.values():
        if not isinstance(value, dict):
            continue
        next_retry_at = _parse_iso_datetime(value.get("next_retry_at"))
        if next_retry_at is None or next_retry_at <= now:
            continue
        if latest_next_retry_at is None or next_retry_at > latest_next_retry_at:
            latest_entry = value
            latest_next_retry_at = next_retry_at

    if latest_entry is None or latest_next_retry_at is None:
        return {}

    cooldown_started_at = _parse_iso_datetime(latest_entry.get("last_risk_at")) or now
    recent_error = str(latest_entry.get("last_error") or "").strip()
    cooldown_seconds = max(int((latest_next_retry_at - cooldown_started_at).total_seconds()), 0)
    summary = f"risk_control / 开始 {cooldown_started_at.isoformat()} / 恢复 {latest_next_retry_at.isoformat()}"
    if recent_error:
        summary = f"{summary} / {recent_error}"
    return {
        "cooldown_reason": "risk_control",
        "cooldown_started_at": cooldown_started_at.isoformat(),
        "recovery_eta": latest_next_retry_at.isoformat(),
        "next_retry_at": latest_next_retry_at.isoformat(),
        "recent_risk_event": summary,
        "cooldown_seconds": cooldown_seconds,
    }


def summarize_batch_risk_event_log(
    *,
    risk_event_log_path: Path,
    lookback_hours: int,
    top_n: int,
    now: datetime,
) -> dict[str, Any]:
    if not risk_event_log_path.exists():
        return {
            "generated_at": now.isoformat(),
            "lookback_hours": lookback_hours,
            "events_path": str(risk_event_log_path),
            "total_events": 0,
            "top_tasks": [],
            "top_queries": [],
            "hourly_distribution": [],
            "note": "event log file not found",
        }

    cutoff = now - timedelta(hours=max(int(lookback_hours), 1))
    task_counter: Counter[str] = Counter()
    query_counter: Counter[str] = Counter()
    hour_counter: Counter[str] = Counter()
    total_events = 0

    with risk_event_log_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            occurred_at = _parse_iso_datetime(payload.get("occurred_at"))
            if occurred_at is None or occurred_at < cutoff:
                continue
            total_events += 1
            task_key = str(payload.get("task_key") or "").strip()
            query = str(payload.get("query") or "").strip()
            if task_key:
                task_counter[task_key] += 1
            if query:
                query_counter[query] += 1
            hour_label = occurred_at.astimezone().strftime("%H:00")
            hour_counter[hour_label] += 1

    return {
        "generated_at": now.isoformat(),
        "lookback_hours": lookback_hours,
        "source": "log",
        "events_path": str(risk_event_log_path),
        "total_events": total_events,
        "top_tasks": [
            {"task_key": task_key, "count": count}
            for task_key, count in task_counter.most_common(top_n)
        ],
        "top_queries": [
            {"query": query, "count": count}
            for query, count in query_counter.most_common(top_n)
        ],
        "hourly_distribution": [
            {"hour": hour, "count": count}
            for hour, count in sorted(hour_counter.items(), key=lambda item: item[0])
        ],
    }


def summarize_batch_risk_event_db(
    *,
    lookback_hours: int,
    top_n: int,
    now: datetime,
) -> dict[str, Any]:
    cutoff = now - timedelta(hours=max(int(lookback_hours), 1))
    task_counter: Counter[str] = Counter()
    query_counter: Counter[str] = Counter()
    hour_counter: Counter[str] = Counter()
    total_events = 0

    with session_scope() as session:
        rows = session.execute(
            select(BatchCollectRiskEvent)
            .where(BatchCollectRiskEvent.occurred_at >= cutoff)
            .order_by(BatchCollectRiskEvent.occurred_at.desc(), BatchCollectRiskEvent.id.desc())
        ).scalars()
        for row in rows:
            total_events += 1
            task_key = str(row.task_key or "").strip()
            query = str(row.query or "").strip()
            if task_key:
                task_counter[task_key] += 1
            if query:
                query_counter[query] += 1
            occurred_at = row.occurred_at.astimezone() if row.occurred_at is not None else now.astimezone()
            hour_label = occurred_at.strftime("%H:00")
            hour_counter[hour_label] += 1

    return {
        "generated_at": now.isoformat(),
        "lookback_hours": lookback_hours,
        "source": "db",
        "total_events": total_events,
        "top_tasks": [
            {"task_key": task_key, "count": count}
            for task_key, count in task_counter.most_common(top_n)
        ],
        "top_queries": [
            {"query": query, "count": count}
            for query, count in query_counter.most_common(top_n)
        ],
        "hourly_distribution": [
            {"hour": hour, "count": count}
            for hour, count in sorted(hour_counter.items(), key=lambda item: item[0])
        ],
    }


def run_collect_batch_orchestration(
    *,
    config_path: Path,
    profile_key: str,
    login_wait_seconds: int,
    only_task: str | None,
    checkpoint_mode: str,
    job_phase: str,
    parallel_tabs: int | None,
    max_plans_per_run: int,
    cursor_state_path: Path | None,
    risk_backoff_state_path: Path,
    risk_event_log_path: Path,
    risk_backoff_base_seconds: int,
    risk_backoff_max_seconds: int,
    max_pages_per_plan: int | None,
    exit_on_risk_event: bool,
    browser_guard_state_path: Path,
    browser_guard_event_log_path: Path,
    browser_guard_base_seconds: int,
    browser_guard_max_seconds: int,
    build_crawl_task_runtime_config,
    ensure_task,
    export_task_config_bundle,
    get_settings,
    get_task_or_raise,
    group_batch_plans_by_platform,
    load_task_config,
    run_live_search_batch,
    search_plan_entry_cls,
) -> None:
    try:
        config = load_task_config(config_path)
    except FileNotFoundError:
        config = {"profiles": {}, "tasks": []}
    resolved_checkpoint_mode = _normalize_checkpoint_mode(checkpoint_mode)
    resolved_job_phase = _normalize_job_phase(job_phase)
    runtime_bundle = export_task_config_bundle(config_path=config_path, include_inactive=False)
    task_bundle = runtime_bundle if runtime_bundle.get("tasks") else config
    profile = config.get("profiles", {}).get(profile_key, {})
    channel = profile.get("channel", "msedge")
    headless = bool(profile.get("headless", False))
    cdp_url = profile.get("cdp_url")
    effective_parallel_tabs = int(parallel_tabs or profile.get("parallel_tabs", 1))
    guard_scope_key = str(only_task or "").strip() or None
    guard_preflight = evaluate_browser_guard_preflight(
        profile_key=profile_key,
        feature="collect_batch",
        scope_key=guard_scope_key,
        state_path=browser_guard_state_path,
        base_seconds=browser_guard_base_seconds,
    )
    if not guard_preflight["allowed"]:
        message = format_browser_guard_preflight_message(guard_preflight)
        _persist_batch_attempt(
            profile_key=profile_key,
            feature="collect_batch",
            stage="preflight",
            attempt_outcome="blocked_by_guard",
            scope_key=guard_scope_key,
            auth_state=guard_preflight.get("auth_state"),
            guard_blocked=True,
            error_message=guard_preflight.get("error_message"),
            metadata={
                "browser_guard": guard_preflight,
                "config_path": str(Path(config_path).expanduser().resolve()),
                "only_task": only_task,
            },
        )
        typer.echo(message)
        upsert_collector_job_run_state(
            job_name="batch_collect",
            phase="preflight",
            status="degraded",
            metadata={
                **build_browser_guard_metadata(guard_preflight),
                "config_path": str(Path(config_path).expanduser().resolve()),
                "profile_key": profile_key,
                "only_task": only_task,
                "guard_message": message,
            },
        )
        return
    plans: list[Any] = []
    for task_config in task_bundle.get("tasks", []):
        task_key = task_config["task_key"]
        if only_task and task_key != only_task:
            continue

        ensure_task(task_config)
        task = get_task_or_raise(task_key)
        runtime_config = build_crawl_task_runtime_config(task_key=task_key)
        for query_config in _resolve_batch_query_configs(
            task_config=task_config,
            runtime_config=runtime_config,
        ):
            query = query_config["query"]
            pages = int(query_config["pages"])
            plans.append(
                search_plan_entry_cls(
                    task=task,
                    query=query,
                    pages=pages,
                    task_query_id=query_config.get("id"),
                )
            )

    batch_lock = _batch_collect_process_lock(_default_batch_collect_lock_path())
    batch_lock_acquired = False
    try:
        batch_lock.__enter__()
        batch_lock_acquired = True
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=BATCH_COLLECT_ALREADY_RUNNING_EXIT_CODE) from exc

    try:
        grouped_plans = group_batch_plans_by_platform(plans)
        xianyu_plans = grouped_plans.pop("xianyu", [])
        initial_xianyu_plan_count = len(xianyu_plans)
        scope_key = _build_batch_cursor_scope_key(
            config_path=config_path,
            profile_key=profile_key,
            only_task=only_task,
        )
        rotation = {
            "selected_count": len(xianyu_plans),
            "total_count": len(xianyu_plans),
            "cursor_before": 0,
            "cursor_after": 0,
            "state_path": str(cursor_state_path) if cursor_state_path else None,
        }
        if max_plans_per_run > 0 and xianyu_plans:
            xianyu_plans, rotation = _select_rotating_plan_window(
                plans=xianyu_plans,
                max_plans_per_run=max_plans_per_run,
                cursor_state_path=cursor_state_path,
                scope_key=scope_key,
                checkpoint_mode=resolved_checkpoint_mode,
            )
            typer.echo(
                "collect-batch window: "
                f"selected={rotation['selected_count']}/{rotation['total_count']} "
                f"cursor={rotation['cursor_before']}->{rotation['cursor_after']} "
                f"state={rotation.get('state_path') or 'none'}"
            )
            upsert_collector_job_checkpoint(
                scope_key=scope_key,
                checkpoint_mode=resolved_checkpoint_mode,
                cursor_pending=int(rotation["cursor_after"]),
                cursor_committed=int(
                    rotation["cursor_after"]
                    if resolved_checkpoint_mode == "eager"
                    else rotation["cursor_before"]
                ),
            )

        risk_state = _load_batch_risk_backoff_state(risk_backoff_state_path)
        xianyu_plans, skipped_by_backoff = _filter_plans_by_risk_backoff(
            plans=xianyu_plans,
            scope_key=scope_key,
            risk_state=risk_state,
            now=datetime.now(UTC),
        )
        if max_pages_per_plan is not None:
            for plan in xianyu_plans:
                plan.pages = _clamp_batch_plan_pages_for_run(
                    pages=plan.pages,
                    max_pages_per_plan=max_pages_per_plan,
                )
        if skipped_by_backoff:
            typer.echo(
                "collect-batch backoff: "
                f"skipped={len(skipped_by_backoff)} "
                f"remaining={len(xianyu_plans)} "
                f"state={risk_backoff_state_path}"
            )

        outcomes: list[Any] = []
        job_run_id = start_collector_job_run(
            job_name="batch_collect",
            phase=resolved_job_phase,
            status="running",
            metadata={
                "config_path": str(Path(config_path).expanduser().resolve()),
                "profile_key": profile_key,
                "only_task": only_task,
                "checkpoint_mode": resolved_checkpoint_mode,
                "parallel_tabs": effective_parallel_tabs,
                "initial_plan_count": initial_xianyu_plan_count,
                "selected_plan_count": int(rotation["selected_count"]),
                "filtered_plan_count": len(xianyu_plans),
                "skipped_by_backoff_count": len(skipped_by_backoff),
                "cursor_before": int(rotation["cursor_before"]),
                "cursor_after": int(rotation["cursor_after"]),
                "cursor_state_path": str(cursor_state_path) if cursor_state_path else None,
                "risk_state_path": str(risk_backoff_state_path),
            },
        )
        risk_stats = {
            "risk_event_count": 0,
            "recovered_count": 0,
            "db_persisted_count": 0,
            "db_persist_failed_count": 0,
        }
        browser_guard_decision: dict[str, Any] = {}
        final_status = "completed"
        final_exit_code = 0

        try:
            if xianyu_plans:
                outcomes = run_live_search_batch(
                    plans=xianyu_plans,
                    channel=channel,
                    headless=headless,
                    cdp_url=cdp_url,
                    parallel_tabs=effective_parallel_tabs,
                    profile_key=profile_key,
                    profile_dir=get_settings().browser_profile_dir / profile_key,
                    login_wait_seconds=login_wait_seconds,
                )
                _persist_batch_attempts_for_outcomes(
                    outcomes=outcomes,
                    profile_key=profile_key,
                    scope_key=scope_key,
                    job_run_id=job_run_id,
                    stage=resolved_job_phase,
                    is_probe=resolved_job_phase == "probe",
                )
                risk_stats = _apply_plan_outcomes_to_risk_backoff_state(
                    outcomes=outcomes,
                    scope_key=scope_key,
                    risk_state=risk_state,
                    now=datetime.now(UTC),
                    risk_backoff_base_seconds=risk_backoff_base_seconds,
                    risk_backoff_max_seconds=risk_backoff_max_seconds,
                    risk_event_log_path=risk_event_log_path,
                    profile_key=profile_key,
                    config_path=config_path,
                )
                browser_guard_decision = _apply_plan_outcomes_to_browser_guard(
                    outcomes=outcomes,
                    profile_key=profile_key,
                    state_path=browser_guard_state_path,
                    event_log_path=browser_guard_event_log_path,
                    base_seconds=browser_guard_base_seconds,
                    max_seconds=browser_guard_max_seconds,
                )
                _save_batch_risk_backoff_state(risk_backoff_state_path, risk_state)
                typer.echo(
                    "collect-batch risk-state: "
                    f"risk_events={risk_stats['risk_event_count']} "
                    f"recoveries={risk_stats['recovered_count']} "
                    f"db_events_ok={risk_stats['db_persisted_count']} "
                    f"db_events_failed={risk_stats['db_persist_failed_count']} "
                    f"active_cooldowns={_count_active_risk_backoff_entries(risk_state=risk_state, now=datetime.now(UTC))} "
                    f"state={risk_backoff_state_path} "
                    f"events={risk_event_log_path}"
                )
                if risk_stats["risk_event_count"] > 0:
                    final_status = "risk_control"
                    final_exit_code = 19 if exit_on_risk_event else 0
                elif _has_non_completed_outcome(outcomes):
                    final_status = "degraded"
            else:
                _persist_batch_attempt(
                    profile_key=profile_key,
                    feature="collect_batch",
                    stage=resolved_job_phase,
                    attempt_outcome="skipped",
                    scope_key=scope_key,
                    is_probe=resolved_job_phase == "probe",
                    job_run_id=job_run_id,
                    metadata={
                        "reason": "no_plans_selected",
                        "only_task": only_task,
                    },
                )
                _save_batch_risk_backoff_state(risk_backoff_state_path, risk_state)

            if cursor_state_path is not None and max_plans_per_run > 0 and int(rotation["selected_count"]) > 0:
                if resolved_checkpoint_mode == "commit" and final_status != "risk_control":
                    _commit_rotating_plan_window(
                        cursor_state_path=cursor_state_path,
                        scope_key=scope_key,
                        cursor_after=int(rotation["cursor_after"]),
                    )
                upsert_collector_job_checkpoint(
                    scope_key=scope_key,
                    checkpoint_mode=resolved_checkpoint_mode,
                    cursor_pending=int(rotation["cursor_after"]),
                    cursor_committed=int(
                        rotation["cursor_after"]
                        if resolved_checkpoint_mode == "eager" or final_status != "risk_control"
                        else rotation["cursor_before"]
                    ),
                )

            _record_batch_collect_quality_metrics(
                now=datetime.now(UTC),
                outcomes=outcomes,
                risk_stats=risk_stats,
                task_key=only_task,
            )

            if exit_on_risk_event and risk_stats["risk_event_count"] > 0:
                raise typer.Exit(code=19)

        except typer.Exit as exc:
            final_exit_code = int(exc.exit_code or final_exit_code or 1)
            if final_exit_code != 0 and final_status == "completed":
                final_status = "failed"
            raise
        except Exception:
            final_status = "failed"
            final_exit_code = 1
            raise
        finally:
            cooldown_metadata = _latest_risk_backoff_metadata(
                risk_state=risk_state,
                now=datetime.now(UTC),
            )
            finish_collector_job_run(
                job_run_id=job_run_id,
                status=final_status,
                phase=resolved_job_phase,
                exit_code=final_exit_code,
                metadata={
                    **_summarize_outcomes(outcomes),
                    **build_browser_guard_metadata(browser_guard_decision),
                    **cooldown_metadata,
                    "risk_event_count": int(risk_stats["risk_event_count"]),
                    "recovered_count": int(risk_stats["recovered_count"]),
                    "db_persisted_count": int(risk_stats["db_persisted_count"]),
                    "db_persist_failed_count": int(risk_stats["db_persist_failed_count"]),
                    "active_cooldowns": _count_active_risk_backoff_entries(
                        risk_state=risk_state,
                        now=datetime.now(UTC),
                    ),
                    "filtered_plan_count": len(xianyu_plans),
                    "skipped_by_backoff_count": len(skipped_by_backoff),
                },
            )

        for platform, unsupported_plans in grouped_plans.items():
            typer.echo(
                f"Skipped {len(unsupported_plans)} query plans for unsupported live collector platform '{platform}'."
            )

        if not xianyu_plans and grouped_plans:
            raise typer.Exit(code=2)
    finally:
        if batch_lock_acquired:
            batch_lock.__exit__(None, None, None)
