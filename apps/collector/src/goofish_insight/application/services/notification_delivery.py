from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...compat import UTC
from ...models import BuyAlertEvent, NotificationDelivery

PENDING_STATUS = "pending"
SENT_STATUS = "sent"
FAILED_STATUS = "failed"
DEAD_STATUS = "dead"

DASHBOARD_CHANNEL = "dashboard"
NOOP_CHANNEL = "noop"
WEBHOOK_CHANNEL = "webhook"


def normalize_notification_channel(channel: str | None) -> str:
    normalized = str(channel or "").strip().lower()
    if not normalized:
        return DASHBOARD_CHANNEL
    if normalized in {"none", "disabled"}:
        return NOOP_CHANNEL
    return normalized


def build_notification_payload(alert_event: BuyAlertEvent) -> dict[str, Any]:
    return {
        "source": "buy_alert_event",
        "alert_event_id": str(alert_event.id) if alert_event.id is not None else None,
        "alert_channel": str(alert_event.alert_channel or ""),
        "opportunity_id": str(alert_event.opportunity_id),
        "watch_target_id": str(alert_event.watch_target_id),
        "alert_reason": alert_event.alert_reason,
        "alert_payload": dict(alert_event.payload or {}),
    }


def create_notification_delivery_for_alert(
    alert_event: BuyAlertEvent,
    *,
    channel: str | None = None,
    destination: str | None = None,
    now: datetime | None = None,
    max_attempts: int = 3,
) -> NotificationDelivery:
    resolved_channel = normalize_notification_channel(channel or alert_event.alert_channel)
    enqueue_time = now or datetime.now(UTC)
    return NotificationDelivery(
        alert_event_id=str(alert_event.id) if alert_event.id is not None else None,
        channel=resolved_channel,
        destination=destination,
        status=PENDING_STATUS,
        attempt_count=0,
        max_attempts=max(int(max_attempts), 1),
        next_retry_at=enqueue_time,
        payload=build_notification_payload(alert_event),
        metadata_json={"created_from": "buy_alerts.emit_buy_alert_events"},
    )


def fetch_pending_notification_deliveries(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> list[NotificationDelivery]:
    retry_at = now or datetime.now(UTC)
    stmt = (
        select(NotificationDelivery)
        .where(NotificationDelivery.status == PENDING_STATUS)
        .where((NotificationDelivery.next_retry_at.is_(None)) | (NotificationDelivery.next_retry_at <= retry_at))
        .order_by(NotificationDelivery.next_retry_at.asc().nullsfirst(), NotificationDelivery.created_at.asc())
        .limit(max(int(limit), 1))
    )
    return list(session.execute(stmt).scalars().all())


def mark_notification_delivery_sent(
    delivery: NotificationDelivery,
    *,
    now: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> NotificationDelivery:
    sent_at = now or datetime.now(UTC)
    delivery.status = SENT_STATUS
    delivery.sent_at = sent_at
    delivery.last_attempt_at = sent_at
    delivery.next_retry_at = None
    delivery.error_message = None
    if metadata:
        delivery.metadata_json = {**dict(delivery.metadata_json or {}), **metadata}
    return delivery


def mark_notification_delivery_failed(
    delivery: NotificationDelivery,
    *,
    error_message: str,
    now: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> NotificationDelivery:
    failed_at = now or datetime.now(UTC)
    delivery.attempt_count = int(delivery.attempt_count or 0) + 1
    delivery.last_attempt_at = failed_at
    delivery.error_message = str(error_message or "delivery failed")[:2000]
    if delivery.attempt_count >= int(delivery.max_attempts or 1):
        delivery.status = DEAD_STATUS
        delivery.next_retry_at = None
    else:
        delivery.status = PENDING_STATUS
        delivery.next_retry_at = failed_at + timedelta(minutes=2 ** max(delivery.attempt_count - 1, 0))
    if metadata:
        delivery.metadata_json = {**dict(delivery.metadata_json or {}), **metadata}
    return delivery
