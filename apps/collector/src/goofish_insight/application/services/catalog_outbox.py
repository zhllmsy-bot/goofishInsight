from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...compat import UTC
from ...db import session_scope
from ...models import OutboxEvent, OutboxStatus, ProductSpu
from .catalog_queries import build_catalog_spu_detail

CATALOG_OUTBOX_EVENT_TYPE = "catalog.product_spu_changed"
CATALOG_OUTBOX_AGGREGATE_TYPE = "product_spu"


class CatalogOutboxProcessingError(RuntimeError):
    pass


def process_catalog_outbox_events(
    *,
    limit: int = 20,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = process_catalog_outbox_events_with_session(
            session,
            limit=limit,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def process_catalog_outbox_events_with_session(
    session: Session,
    *,
    limit: int = 20,
    dry_run: bool = False,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    events = _load_pending_catalog_outbox_events(session, limit=limit, now=now)
    summary = {
        "dryRun": dry_run,
        "requestedLimit": limit,
        "eventCount": len(events),
        "processedCount": 0,
        "failedCount": 0,
        "events": [],
    }

    for event in events:
        event.status = OutboxStatus.PROCESSING
        session.flush()
        try:
            result = _process_catalog_outbox_event(session, event, now=now)
            event.payload = {
                **dict(event.payload or {}),
                "_consumer": {
                    "catalogOutbox": result,
                },
            }
            event.status = OutboxStatus.DONE
            event.last_error = None
            event.next_retry_at = None
            summary["processedCount"] += 1
            summary["events"].append(
                {
                    "eventId": event.id,
                    "aggregateId": event.aggregate_id,
                    "status": "processed" if not dry_run else "would_process",
                    "result": result,
                }
            )
        except Exception as exc:
            _mark_outbox_event_failed(event, exc, now=now)
            summary["failedCount"] += 1
            summary["events"].append(
                {
                    "eventId": event.id,
                    "aggregateId": event.aggregate_id,
                    "status": "failed",
                    "error": str(exc),
                }
            )

        session.flush()

    return summary


def build_catalog_outbox_rows(session: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = session.execute(
        select(OutboxEvent)
        .where(
            OutboxEvent.event_type == CATALOG_OUTBOX_EVENT_TYPE,
            OutboxEvent.aggregate_type == CATALOG_OUTBOX_AGGREGATE_TYPE,
        )
        .order_by(OutboxEvent.created_at.desc())
        .limit(limit)
    ).scalars()

    return [
        {
            "id": event.id,
            "eventType": event.event_type,
            "aggregateType": event.aggregate_type,
            "aggregateId": event.aggregate_id,
            "eventVersion": event.event_version,
            "status": event.status.value,
            "retryCount": event.retry_count,
            "lastError": event.last_error,
            "nextRetryAt": event.next_retry_at,
            "createdAt": event.created_at,
            "updatedAt": event.updated_at,
        }
        for event in rows
    ]


def _load_pending_catalog_outbox_events(
    session: Session,
    *,
    limit: int,
    now: datetime,
) -> list[OutboxEvent]:
    if limit <= 0:
        raise CatalogOutboxProcessingError("limit must be greater than 0.")

    rows = session.execute(
        select(OutboxEvent)
        .where(
            OutboxEvent.event_type == CATALOG_OUTBOX_EVENT_TYPE,
            OutboxEvent.aggregate_type == CATALOG_OUTBOX_AGGREGATE_TYPE,
            OutboxEvent.status.in_([OutboxStatus.PENDING, OutboxStatus.FAILED]),
            or_(
                OutboxEvent.next_retry_at.is_(None),
                OutboxEvent.next_retry_at <= now,
            ),
        )
        .order_by(OutboxEvent.created_at.asc())
        .limit(limit)
    ).scalars()
    return list(rows)


def _process_catalog_outbox_event(
    session: Session,
    event: OutboxEvent,
    *,
    now: datetime,
) -> dict[str, Any]:
    spu = session.get(ProductSpu, event.aggregate_id)
    if spu is None:
        raise CatalogOutboxProcessingError(f"SPU not found for outbox event: {event.aggregate_id}")

    detail = build_catalog_spu_detail(session, event.aggregate_id)
    if detail is None:
        raise CatalogOutboxProcessingError(
            f"Unable to build SPU detail for outbox event: {event.aggregate_id}"
        )

    snapshot = dict(detail["spu"]["attrSnapshotJson"] or {})
    if snapshot.get("spuId") != spu.id:
        raise CatalogOutboxProcessingError(
            f"Snapshot spuId mismatch for event {event.id}: {snapshot.get('spuId')} != {spu.id}"
        )

    return {
        "processedAt": now.isoformat(),
        "spuId": spu.id,
        "skuCount": len(detail["skus"]),
        "snapshotSkuCount": len(snapshot.get("skus") or []),
        "templateId": spu.template_id,
    }


def _mark_outbox_event_failed(
    event: OutboxEvent,
    exc: Exception,
    *,
    now: datetime,
) -> None:
    next_retry_count = event.retry_count + 1
    event.retry_count = next_retry_count
    event.last_error = str(exc)[:1000]
    event.next_retry_at = now + timedelta(minutes=min(5 * next_retry_count, 60))
    event.status = OutboxStatus.DEAD if next_retry_count >= 5 else OutboxStatus.FAILED
