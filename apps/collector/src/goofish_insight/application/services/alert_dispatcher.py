from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ...compat import UTC
from ...db import session_scope
from ...models import BuyAlertEvent, NotificationDelivery
from ...settings import get_settings
from .alert_router import AlertDeliveryError, AlertRoutingError, resolve_alert_route, send_webhook_delivery
from .notification_delivery import (
    DASHBOARD_CHANNEL,
    DEAD_STATUS,
    NOOP_CHANNEL,
    PENDING_STATUS,
    SENT_STATUS,
    fetch_pending_notification_deliveries,
    mark_notification_delivery_failed,
    mark_notification_delivery_sent,
    normalize_notification_channel,
)


def dispatch_notification_deliveries(
    *,
    limit: int = 50,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        deliveries = fetch_pending_notification_deliveries(
            session,
            now=now,
            limit=limit,
        )
        results = [
            dispatch_notification_delivery_with_session(
                session,
                delivery,
                dry_run=dry_run,
                now=now,
            )
            for delivery in deliveries
        ]
        if dry_run:
            session.rollback()
        return {
            "dryRun": dry_run,
            "candidateCount": len(deliveries),
            "sentCount": sum(1 for row in results if row["status"] == SENT_STATUS),
            "pendingCount": sum(1 for row in results if row["status"] == PENDING_STATUS),
            "deadCount": sum(1 for row in results if row["status"] == DEAD_STATUS),
            "items": results,
        }


def dispatch_notification_delivery_with_session(
    session: Session,
    delivery: NotificationDelivery,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    dispatch_at = now or datetime.now(UTC)
    channel = normalize_notification_channel(delivery.channel)
    delivery.channel = channel

    if channel in {DASHBOARD_CHANNEL, NOOP_CHANNEL}:
        mode = "dashboard_noop" if channel == DASHBOARD_CHANNEL else "noop"
        mark_notification_delivery_sent(
            delivery,
            now=dispatch_at,
            metadata={
                "dispatcher": "alert_dispatcher",
                "delivery_mode": mode,
                "dry_run": bool(dry_run),
            },
        )
        if channel == DASHBOARD_CHANNEL:
            _mark_alert_event_sent(session, delivery, sent_at=dispatch_at)
        detail = "dashboard notification recorded" if channel == DASHBOARD_CHANNEL else "notification skipped by noop channel"
        return _serialize_dispatch_result(delivery, detail=detail)

    settings = get_settings()
    try:
        route = resolve_alert_route(
            channel=channel,
            destination=delivery.destination,
            settings=settings,
        )
    except AlertRoutingError as exc:
        mark_notification_delivery_failed(
            delivery,
            error_message=str(exc),
            now=dispatch_at,
            metadata={
                "dispatcher": "alert_dispatcher",
                "delivery_mode": "routing_error",
                "dry_run": bool(dry_run),
            },
        )
        return _serialize_dispatch_result(delivery, detail=delivery.error_message)

    if dry_run:
        mark_notification_delivery_sent(
            delivery,
            now=dispatch_at,
            metadata={
                "dispatcher": "alert_dispatcher",
                "delivery_mode": "webhook_dry_run",
                "dry_run": True,
                "destination": route.destination,
            },
        )
        _mark_alert_event_sent(session, delivery, sent_at=dispatch_at)
        return _serialize_dispatch_result(delivery, detail="webhook dry-run: skipped network send")

    try:
        send_result = send_webhook_delivery(
            route=route,
            delivery=delivery,
            now=dispatch_at,
        )
    except AlertDeliveryError as exc:
        mark_notification_delivery_failed(
            delivery,
            error_message=str(exc),
            now=dispatch_at,
            metadata={
                "dispatcher": "alert_dispatcher",
                "delivery_mode": "webhook",
                "destination": route.destination,
                "dry_run": False,
            },
        )
        return _serialize_dispatch_result(delivery, detail=delivery.error_message)

    mark_notification_delivery_sent(
        delivery,
        now=dispatch_at,
        metadata={
            "dispatcher": "alert_dispatcher",
            "delivery_mode": "webhook",
            "destination": route.destination,
            "status_code": int(send_result["status_code"]),
            "provider_message_id": send_result.get("provider_message_id"),
            "response_excerpt": send_result.get("response_excerpt"),
            "dry_run": False,
        },
    )
    _mark_alert_event_sent(session, delivery, sent_at=dispatch_at)
    return _serialize_dispatch_result(
        delivery,
        detail=f"webhook delivered ({send_result['status_code']})",
    )


def _mark_alert_event_sent(session: Session, delivery: NotificationDelivery, *, sent_at: datetime) -> None:
    if not delivery.alert_event_id:
        return
    alert = session.get(BuyAlertEvent, str(delivery.alert_event_id))
    if alert is None:
        return
    alert.status = "SENT"
    alert.sent_at = sent_at


def _serialize_dispatch_result(delivery: NotificationDelivery, *, detail: str | None = None) -> dict[str, Any]:
    metadata = dict(delivery.metadata_json or {})
    return {
        "id": str(delivery.id),
        "alertEventId": str(delivery.alert_event_id) if delivery.alert_event_id else None,
        "channel": delivery.channel,
        "status": delivery.status,
        "attemptCount": int(delivery.attempt_count or 0),
        "nextRetryAt": delivery.next_retry_at.isoformat() if delivery.next_retry_at else None,
        "providerMessageId": metadata.get("provider_message_id"),
        "deliveryMode": metadata.get("delivery_mode"),
        "destination": metadata.get("destination") or delivery.destination,
        "detail": detail,
    }
