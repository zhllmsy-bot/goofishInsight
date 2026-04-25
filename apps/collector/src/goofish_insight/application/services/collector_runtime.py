from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from ...compat import UTC
from ...db import session_scope
from ...models import CollectorJobCheckpoint, CollectorJobRun


def _clamp_recovery_seconds(
    value: Any,
    *,
    initial_seconds: int,
    max_seconds: int,
) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = initial_seconds
    if resolved < initial_seconds:
        resolved = initial_seconds
    if resolved > max_seconds:
        resolved = max_seconds
    return resolved


def _clamp_optional_recovery_seconds(
    value: Any,
    *,
    initial_seconds: int,
    max_seconds: int,
) -> int | None:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    if resolved <= 0:
        return None
    if resolved < initial_seconds:
        resolved = initial_seconds
    if resolved > max_seconds:
        resolved = max_seconds
    return resolved


def normalize_resident_recovery_state(
    metadata: dict[str, Any] | None,
    *,
    initial_seconds: int,
    max_seconds: int,
) -> dict[str, int | None]:
    payload = dict(metadata or {})
    baseline_seconds = _clamp_recovery_seconds(
        payload.get("recovery_baseline_seconds", payload.get("next_cooldown_seconds")),
        initial_seconds=initial_seconds,
        max_seconds=max_seconds,
    )
    last_applied_cooldown_seconds = _clamp_optional_recovery_seconds(
        payload.get("recovery_last_applied_cooldown_seconds"),
        initial_seconds=initial_seconds,
        max_seconds=max_seconds,
    )
    failed_cooldown_seconds = _clamp_optional_recovery_seconds(
        payload.get("recovery_failed_cooldown_seconds"),
        initial_seconds=initial_seconds,
        max_seconds=max_seconds,
    )
    next_cooldown_seconds = _clamp_recovery_seconds(
        payload.get("next_cooldown_seconds", baseline_seconds),
        initial_seconds=initial_seconds,
        max_seconds=max_seconds,
    )
    return {
        "baseline_seconds": baseline_seconds,
        "last_applied_cooldown_seconds": last_applied_cooldown_seconds,
        "failed_cooldown_seconds": failed_cooldown_seconds,
        "next_cooldown_seconds": next_cooldown_seconds,
    }


def plan_resident_cooldown_after_risk(
    *,
    baseline_seconds: int,
    last_applied_cooldown_seconds: int | None,
    max_seconds: int,
) -> dict[str, int | str | None]:
    resolved_baseline = min(max(int(baseline_seconds), 1), max_seconds)
    resolved_last_applied = None
    if last_applied_cooldown_seconds is not None:
        resolved_last_applied = min(max(int(last_applied_cooldown_seconds), 1), max_seconds)

    if resolved_last_applied is None:
        sleep_seconds = resolved_baseline
        failed_cooldown_seconds = None
        strategy = "reuse_baseline"
    else:
        sleep_seconds = min(resolved_last_applied * 2, max_seconds)
        failed_cooldown_seconds = resolved_last_applied
        strategy = "escalate_after_failed_retry"

    next_cooldown_seconds = min(sleep_seconds * 2, max_seconds)
    return {
        "sleep_seconds": sleep_seconds,
        "failed_cooldown_seconds": failed_cooldown_seconds,
        "next_cooldown_seconds": next_cooldown_seconds,
        "strategy": strategy,
    }


def resolve_resident_cooldown_after_success(
    *,
    baseline_seconds: int,
    last_applied_cooldown_seconds: int | None,
    failed_cooldown_seconds: int | None,
    max_seconds: int,
) -> dict[str, int | str | bool]:
    resolved_baseline = min(max(int(baseline_seconds), 1), max_seconds)
    resolved_last_applied = None
    if last_applied_cooldown_seconds is not None:
        resolved_last_applied = min(max(int(last_applied_cooldown_seconds), 1), max_seconds)
    resolved_failed = None
    if failed_cooldown_seconds is not None:
        resolved_failed = min(max(int(failed_cooldown_seconds), 1), max_seconds)

    adjusted = False
    strategy = "keep_existing_baseline"
    next_baseline = resolved_baseline
    if resolved_last_applied is not None:
        if resolved_failed is not None and resolved_last_applied > resolved_failed:
            next_baseline = min((resolved_failed + resolved_last_applied) // 2, max_seconds)
            adjusted = next_baseline != resolved_baseline
            strategy = "midpoint_after_escalation"
        elif resolved_last_applied > resolved_baseline:
            next_baseline = resolved_last_applied
            adjusted = True
            strategy = "adopt_successful_wait"
        else:
            next_baseline = resolved_baseline
            strategy = "confirm_baseline"

    if next_baseline < 1:
        next_baseline = 1
    return {
        "baseline_seconds": next_baseline,
        "last_applied_cooldown_seconds": 0,
        "failed_cooldown_seconds": 0,
        "next_cooldown_seconds": next_baseline,
        "adjusted": adjusted,
        "strategy": strategy,
    }


def _latest_active_job_run(
    *,
    session,
    job_name: str,
) -> CollectorJobRun | None:
    return session.execute(
        select(CollectorJobRun)
        .where(CollectorJobRun.job_name == job_name)
        .where(CollectorJobRun.finished_at.is_(None))
        .order_by(CollectorJobRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _latest_active_or_recent_job_run(
    *,
    session,
    job_name: str,
) -> CollectorJobRun | None:
    job_run = _latest_active_job_run(session=session, job_name=job_name)
    if job_run is not None:
        return job_run
    return session.execute(
        select(CollectorJobRun)
        .where(CollectorJobRun.job_name == job_name)
        .order_by(CollectorJobRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def start_collector_job_run(
    *,
    job_name: str,
    phase: str,
    status: str = "running",
    metadata: dict[str, Any] | None = None,
) -> UUID:
    job_run_id = uuid4()
    with session_scope() as session:
        session.add(
            CollectorJobRun(
                id=job_run_id,
                job_name=job_name,
                phase=phase,
                status=status,
                metadata_json=metadata or {},
            )
        )
    return job_run_id


def finish_collector_job_run(
    *,
    job_run_id: UUID | None,
    status: str,
    phase: str | None = None,
    exit_code: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if job_run_id is None:
        return
    with session_scope() as session:
        job_run = session.get(CollectorJobRun, job_run_id)
        if job_run is None:
            return
        job_run.status = status
        if phase is not None:
            job_run.phase = phase
        job_run.exit_code = exit_code
        job_run.finished_at = datetime.now(UTC)
        if metadata:
            merged = dict(job_run.metadata_json or {})
            merged.update(metadata)
            job_run.metadata_json = merged


def upsert_collector_job_run_state(
    *,
    job_name: str,
    phase: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    job_run_id: UUID | None = None,
    exit_code: int | None = None,
    finished: bool = False,
) -> UUID:
    now = datetime.now(UTC)
    with session_scope() as session:
        job_run: CollectorJobRun | None = None
        if job_run_id is not None:
            job_run = session.get(CollectorJobRun, job_run_id)
        if job_run is None:
            job_run = _latest_active_job_run(session=session, job_name=job_name)
        if job_run is None:
            job_run = CollectorJobRun(
                id=job_run_id or uuid4(),
                job_name=job_name,
                phase=phase,
                status=status,
                metadata_json=dict(metadata or {}),
            )
            if exit_code is not None:
                job_run.exit_code = exit_code
            if finished:
                job_run.finished_at = now
            session.add(job_run)
            return job_run.id

        job_run.phase = phase
        job_run.status = status
        if metadata:
            merged = dict(job_run.metadata_json or {})
            merged.update(metadata)
            job_run.metadata_json = merged
        if exit_code is not None:
            job_run.exit_code = exit_code
        if finished:
            job_run.finished_at = now
        return job_run.id


def get_latest_collector_job_run_state(
    *,
    job_name: str,
) -> dict[str, Any] | None:
    with session_scope() as session:
        job_run = _latest_active_or_recent_job_run(session=session, job_name=job_name)
        if job_run is None:
            return None
        return {
            "job_run_id": str(job_run.id),
            "job_name": job_run.job_name,
            "phase": job_run.phase,
            "status": job_run.status,
            "started_at": job_run.started_at.isoformat() if job_run.started_at else None,
            "finished_at": job_run.finished_at.isoformat() if job_run.finished_at else None,
            "exit_code": job_run.exit_code,
            "metadata": dict(job_run.metadata_json or {}),
        }


def upsert_collector_job_checkpoint(
    *,
    scope_key: str,
    checkpoint_mode: str,
    cursor_pending: int,
    cursor_committed: int,
) -> None:
    with session_scope() as session:
        checkpoint = session.get(CollectorJobCheckpoint, scope_key)
        if checkpoint is None:
            checkpoint = CollectorJobCheckpoint(
                scope_key=scope_key,
                checkpoint_mode=checkpoint_mode,
                cursor_pending=cursor_pending,
                cursor_committed=cursor_committed,
            )
            session.add(checkpoint)
            return
        checkpoint.checkpoint_mode = checkpoint_mode
        checkpoint.cursor_pending = cursor_pending
        checkpoint.cursor_committed = cursor_committed
        checkpoint.updated_at = datetime.now(UTC)
