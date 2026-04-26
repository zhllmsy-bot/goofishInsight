from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...compat import UTC
from ...db import session_scope
from ...models import OutboxEvent, OutboxStatus
from .buy_opportunities import refresh_buy_opportunities_with_session
from .buy_price_baselines import build_buy_price_baselines_with_session
from .collector_runtime import finish_collector_job_run, start_collector_job_run
from .spec_enrichment_runtime import run_spec_enrichment_batch_with_session

BUY_JOB_AGGREGATE_TYPE = "buy_job"
BUY_JOB_ENRICH_SPECS = "buy.enrich_spec"
BUY_JOB_BUILD_BASELINES = "buy.build_baseline"
BUY_JOB_REFRESH_OPPORTUNITIES = "buy.refresh_opportunity"
BUY_JOB_TYPES = {
    BUY_JOB_ENRICH_SPECS,
    BUY_JOB_BUILD_BASELINES,
    BUY_JOB_REFRESH_OPPORTUNITIES,
}
DEFAULT_DEBOUNCE_MINUTES = 10


class BuyJobRuntimeError(RuntimeError):
    pass


def schedule_spec_enrichment_job(
    *,
    business_domain: str | None = None,
    item_id: str | None = None,
    limit: int = 50,
    force: bool = False,
    allow_llm: bool = True,
    debounce_minutes: int = 0,
    requested_by: str = "manual",
) -> dict[str, Any]:
    with session_scope() as session:
        return schedule_spec_enrichment_job_with_session(
            session,
            business_domain=business_domain,
            item_id=item_id,
            limit=limit,
            force=force,
            allow_llm=allow_llm,
            debounce_minutes=debounce_minutes,
            requested_by=requested_by,
        )


def schedule_buy_baseline_job(
    *,
    category_code: str | None = None,
    business_domain: str | None = None,
    view: str = "all",
    freshness_days: int = 30,
    min_sample_points: int = 4,
    debounce_minutes: int = DEFAULT_DEBOUNCE_MINUTES,
    requested_by: str = "manual",
) -> dict[str, Any]:
    with session_scope() as session:
        return schedule_buy_baseline_job_with_session(
            session,
            category_code=category_code,
            business_domain=business_domain,
            view=view,
            freshness_days=freshness_days,
            min_sample_points=min_sample_points,
            debounce_minutes=debounce_minutes,
            requested_by=requested_by,
        )


def schedule_buy_opportunity_refresh_job(
    *,
    category_code: str | None = None,
    business_domain: str | None = None,
    freshness_days: int = 30,
    min_discount_rate: float = 0.02,
    min_opportunity_score: float = 35.0,
    debounce_minutes: int = DEFAULT_DEBOUNCE_MINUTES,
    requested_by: str = "manual",
) -> dict[str, Any]:
    with session_scope() as session:
        return schedule_buy_opportunity_refresh_job_with_session(
            session,
            category_code=category_code,
            business_domain=business_domain,
            freshness_days=freshness_days,
            min_discount_rate=min_discount_rate,
            min_opportunity_score=min_opportunity_score,
            debounce_minutes=debounce_minutes,
            requested_by=requested_by,
        )


def schedule_spec_enrichment_job_with_session(
    session: Session,
    *,
    business_domain: str | None = None,
    item_id: str | None = None,
    limit: int = 50,
    force: bool = False,
    allow_llm: bool = True,
    debounce_minutes: int = 0,
    requested_by: str = "manual",
) -> dict[str, Any]:
    normalized_scope = _normalize_optional_string(business_domain)
    item_scope = _normalize_optional_string(item_id)
    dedupe_key = f"scope={normalized_scope or 'all'}|item={item_scope or 'batch'}|limit={int(limit)}|force={bool(force)}"
    payload = {
        "businessDomain": normalized_scope,
        "itemId": item_scope,
        "limit": max(int(limit), 1),
        "force": bool(force),
        "allowLlm": bool(allow_llm),
        "followupDebounceMinutes": DEFAULT_DEBOUNCE_MINUTES,
    }
    return schedule_buy_job_request_with_session(
        session,
        job_type=BUY_JOB_ENRICH_SPECS,
        payload=payload,
        dedupe_key=dedupe_key,
        debounce_minutes=debounce_minutes,
        requested_by=requested_by,
    )


def schedule_buy_baseline_job_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    business_domain: str | None = None,
    view: str = "all",
    freshness_days: int = 30,
    min_sample_points: int = 4,
    debounce_minutes: int = DEFAULT_DEBOUNCE_MINUTES,
    requested_by: str = "manual",
) -> dict[str, Any]:
    normalized_category = _normalize_optional_string(category_code)
    normalized_scope = normalized_category or _normalize_optional_string(business_domain)
    dedupe_key = f"scope={normalized_scope or 'all'}|view={view}|freshness={int(freshness_days)}|min_samples={int(min_sample_points)}"
    payload = {
        "categoryCode": normalized_category,
        "businessDomain": _normalize_optional_string(business_domain),
        "view": str(view or "all").strip().lower() or "all",
        "freshnessDays": max(int(freshness_days), 1),
        "minSamplePoints": max(int(min_sample_points), 1),
    }
    return schedule_buy_job_request_with_session(
        session,
        job_type=BUY_JOB_BUILD_BASELINES,
        payload=payload,
        dedupe_key=dedupe_key,
        debounce_minutes=debounce_minutes,
        requested_by=requested_by,
    )


def schedule_buy_opportunity_refresh_job_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    business_domain: str | None = None,
    freshness_days: int = 30,
    min_discount_rate: float = 0.02,
    min_opportunity_score: float = 35.0,
    debounce_minutes: int = DEFAULT_DEBOUNCE_MINUTES,
    requested_by: str = "manual",
) -> dict[str, Any]:
    normalized_category = _normalize_optional_string(category_code)
    normalized_scope = normalized_category or _normalize_optional_string(business_domain)
    dedupe_key = (
        f"scope={normalized_scope or 'all'}|freshness={int(freshness_days)}"
        f"|min_discount={round(float(min_discount_rate), 4)}|min_score={round(float(min_opportunity_score), 2)}"
    )
    payload = {
        "categoryCode": normalized_category,
        "businessDomain": _normalize_optional_string(business_domain),
        "freshnessDays": max(int(freshness_days), 1),
        "minDiscountRate": float(min_discount_rate),
        "minOpportunityScore": float(min_opportunity_score),
    }
    return schedule_buy_job_request_with_session(
        session,
        job_type=BUY_JOB_REFRESH_OPPORTUNITIES,
        payload=payload,
        dedupe_key=dedupe_key,
        debounce_minutes=debounce_minutes,
        requested_by=requested_by,
    )


def schedule_buy_job_request_with_session(
    session: Session,
    *,
    job_type: str,
    payload: dict[str, Any],
    dedupe_key: str,
    debounce_minutes: int,
    requested_by: str,
) -> dict[str, Any]:
    if job_type not in BUY_JOB_TYPES:
        raise BuyJobRuntimeError(f"Unsupported job type: {job_type}")
    due_at = datetime.now(UTC) + timedelta(minutes=max(int(debounce_minutes), 0))
    normalized_payload = {
        **dict(payload or {}),
        "dedupeKey": str(dedupe_key),
        "requestedBy": str(requested_by or "manual"),
        "requestedAt": datetime.now(UTC).isoformat(),
    }
    existing = _find_active_buy_job_event(
        session,
        job_type=job_type,
        dedupe_key=dedupe_key,
    )
    if existing is None:
        event = OutboxEvent(
            id=str(uuid4()),
            event_type=job_type,
            aggregate_type=BUY_JOB_AGGREGATE_TYPE,
            aggregate_id=str(uuid4()),
            payload=normalized_payload,
            status=OutboxStatus.PENDING,
            next_retry_at=due_at,
        )
        session.add(event)
        session.flush()
        return _serialize_buy_job_event(event, queued=True, deduped=False)

    existing.payload = {
        **dict(existing.payload or {}),
        **normalized_payload,
    }
    existing.status = OutboxStatus.PENDING
    existing.last_error = None
    existing.next_retry_at = due_at
    session.flush()
    return _serialize_buy_job_event(existing, queued=False, deduped=True)


def build_buy_job_rows(*, limit: int = 20) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.aggregate_type == BUY_JOB_AGGREGATE_TYPE)
            .where(OutboxEvent.event_type.in_(tuple(sorted(BUY_JOB_TYPES))))
            .order_by(OutboxEvent.created_at.desc())
            .limit(max(int(limit), 1))
        ).scalars()
        return [_serialize_buy_job_event(row) for row in rows]


def process_buy_job_events(
    *,
    limit: int = 20,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = process_buy_job_events_with_session(
            session,
            limit=limit,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def process_buy_job_events_with_session(
    session: Session,
    *,
    limit: int = 20,
    dry_run: bool = False,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    events = _load_due_buy_job_events(session, limit=max(int(limit), 1), now=now)
    summary = {
        "dryRun": bool(dry_run),
        "requestedLimit": max(int(limit), 1),
        "eventCount": len(events),
        "processedCount": 0,
        "failedCount": 0,
        "events": [],
    }
    for event in events:
        event.status = OutboxStatus.PROCESSING
        session.flush()
        job_run_id = None
        if not dry_run:
            job_run_id = start_collector_job_run(
                job_name=_collector_job_name_for_event(event.event_type),
                phase="queue",
                metadata={"eventId": event.id, "jobType": event.event_type},
            )
        try:
            result = _process_buy_job_event(session, event)
            event.payload = {
                **dict(event.payload or {}),
                "_consumer": {"buyJob": result},
            }
            event.status = OutboxStatus.DONE
            event.last_error = None
            event.next_retry_at = None
            if job_run_id is not None:
                finish_collector_job_run(
                    job_run_id=job_run_id,
                    status="completed",
                    phase="done",
                    exit_code=0,
                    metadata={"result": result},
                )
            summary["processedCount"] += 1
            summary["events"].append(
                {
                    "eventId": event.id,
                    "jobType": event.event_type,
                    "status": "processed" if not dry_run else "would_process",
                    "result": result,
                }
            )
        except Exception as exc:
            _mark_buy_job_event_failed(event, exc)
            if job_run_id is not None:
                finish_collector_job_run(
                    job_run_id=job_run_id,
                    status="failed",
                    phase="retry",
                    exit_code=1,
                    metadata={"error": str(exc)},
                )
            summary["failedCount"] += 1
            summary["events"].append(
                {
                    "eventId": event.id,
                    "jobType": event.event_type,
                    "status": "failed",
                    "error": str(exc),
                }
            )
        session.flush()
    return summary


def _process_buy_job_event(session: Session, event: OutboxEvent) -> dict[str, Any]:
    payload = dict(event.payload or {})
    if event.event_type == BUY_JOB_ENRICH_SPECS:
        result = run_spec_enrichment_batch_with_session(
            session,
            business_domain=_normalize_optional_string(payload.get("businessDomain")),
            item_id=_normalize_optional_string(payload.get("itemId")),
            limit=max(int(payload.get("limit") or 50), 1),
            force=bool(payload.get("force")),
            allow_llm=bool(payload.get("allowLlm", True)),
        )
        if result.get("processed"):
            schedule_buy_baseline_job_with_session(
                session,
                category_code=_normalize_optional_string(payload.get("categoryCode")),
                business_domain=_normalize_optional_string(payload.get("businessDomain")),
                debounce_minutes=max(int(payload.get("followupDebounceMinutes") or DEFAULT_DEBOUNCE_MINUTES), 0),
                requested_by=f"buy_job:{event.event_type}",
            )
        return result
    if event.event_type == BUY_JOB_BUILD_BASELINES:
        result = build_buy_price_baselines_with_session(
            session,
            category_code=_normalize_optional_string(payload.get("categoryCode")),
            business_domain=_normalize_optional_string(payload.get("businessDomain")),
            view=_normalize_optional_string(payload.get("view")) or "all",
            freshness_days=max(int(payload.get("freshnessDays") or 30), 1),
            min_sample_points=max(int(payload.get("minSamplePoints") or 4), 1),
        )
        schedule_buy_opportunity_refresh_job_with_session(
            session,
            category_code=_normalize_optional_string(payload.get("categoryCode")),
            business_domain=_normalize_optional_string(payload.get("businessDomain")),
            freshness_days=max(int(payload.get("freshnessDays") or 30), 1),
            debounce_minutes=DEFAULT_DEBOUNCE_MINUTES,
            requested_by=f"buy_job:{event.event_type}",
        )
        return result
    if event.event_type == BUY_JOB_REFRESH_OPPORTUNITIES:
        return refresh_buy_opportunities_with_session(
            session,
            category_code=_normalize_optional_string(payload.get("categoryCode")),
            business_domain=_normalize_optional_string(payload.get("businessDomain")),
            freshness_days=max(int(payload.get("freshnessDays") or 30), 1),
            min_discount_rate=float(payload.get("minDiscountRate") or 0.02),
            min_opportunity_score=float(payload.get("minOpportunityScore") or 35.0),
        )
    raise BuyJobRuntimeError(f"Unsupported job type: {event.event_type}")


def _find_active_buy_job_event(
    session: Session,
    *,
    job_type: str,
    dedupe_key: str,
) -> OutboxEvent | None:
    rows = list(
        session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.aggregate_type == BUY_JOB_AGGREGATE_TYPE)
            .where(OutboxEvent.event_type == job_type)
            .where(OutboxEvent.status.in_((OutboxStatus.PENDING, OutboxStatus.PROCESSING, OutboxStatus.FAILED)))
            .order_by(OutboxEvent.created_at.desc())
        )
        .scalars()
        .all()
    )
    for row in rows:
        if str(dict(row.payload or {}).get("dedupeKey") or "") == str(dedupe_key):
            return row
    return None


def _load_due_buy_job_events(session: Session, *, limit: int, now: datetime) -> list[OutboxEvent]:
    return list(
        session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.aggregate_type == BUY_JOB_AGGREGATE_TYPE)
            .where(OutboxEvent.event_type.in_(tuple(sorted(BUY_JOB_TYPES))))
            .where(OutboxEvent.status.in_((OutboxStatus.PENDING, OutboxStatus.FAILED)))
            .where(or_(OutboxEvent.next_retry_at.is_(None), OutboxEvent.next_retry_at <= now))
            .order_by(OutboxEvent.next_retry_at.asc().nullsfirst(), OutboxEvent.created_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def _mark_buy_job_event_failed(event: OutboxEvent, exc: Exception) -> None:
    now = datetime.now(UTC)
    retry_count = int(event.retry_count or 0) + 1
    event.retry_count = retry_count
    event.last_error = str(exc)[:1000]
    event.next_retry_at = now + timedelta(minutes=min(5 * retry_count, 60))
    event.status = OutboxStatus.DEAD if retry_count >= 5 else OutboxStatus.FAILED


def _collector_job_name_for_event(job_type: str) -> str:
    if job_type == BUY_JOB_ENRICH_SPECS:
        return "enrich-specs"
    if job_type == BUY_JOB_BUILD_BASELINES:
        return "build-buy-baselines"
    if job_type == BUY_JOB_REFRESH_OPPORTUNITIES:
        return "refresh-buy-opportunities"
    return "buy-job"


def _serialize_buy_job_event(
    event: OutboxEvent,
    *,
    queued: bool | None = None,
    deduped: bool | None = None,
) -> dict[str, Any]:
    payload = dict(event.payload or {})
    return {
        "eventId": event.id,
        "jobType": event.event_type,
        "status": event.status.value if hasattr(event.status, "value") else str(event.status),
        "queued": queued,
        "deduped": deduped,
        "dedupeKey": payload.get("dedupeKey"),
        "requestedBy": payload.get("requestedBy"),
        "requestedAt": payload.get("requestedAt"),
        "nextRetryAt": event.next_retry_at.isoformat() if event.next_retry_at else None,
        "retryCount": int(event.retry_count or 0),
        "lastError": event.last_error,
        "payload": payload,
        "createdAt": event.created_at.isoformat() if getattr(event, "created_at", None) else None,
        "updatedAt": event.updated_at.isoformat() if getattr(event, "updated_at", None) else None,
    }


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "BUY_JOB_BUILD_BASELINES",
    "BUY_JOB_ENRICH_SPECS",
    "BUY_JOB_REFRESH_OPPORTUNITIES",
    "BuyJobRuntimeError",
    "build_buy_job_rows",
    "process_buy_job_events",
    "process_buy_job_events_with_session",
    "schedule_buy_baseline_job",
    "schedule_buy_baseline_job_with_session",
    "schedule_buy_opportunity_refresh_job",
    "schedule_buy_opportunity_refresh_job_with_session",
    "schedule_spec_enrichment_job",
    "schedule_spec_enrichment_job_with_session",
]
