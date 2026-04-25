from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from ...compat import UTC
from ...models import NotificationDelivery
from ...settings import Settings, get_settings
from .notification_delivery import DASHBOARD_CHANNEL, NOOP_CHANNEL, WEBHOOK_CHANNEL, normalize_notification_channel


class AlertRoutingError(RuntimeError):
    pass


class AlertDeliveryError(RuntimeError):
    pass


@dataclass(slots=True)
class AlertRoute:
    channel: str
    delivery_mode: str
    destination: str | None
    timeout_seconds: float
    headers: dict[str, str]
    webhook_secret: str | None = None


def resolve_alert_route(
    *,
    channel: str | None,
    destination: str | None,
    settings: Settings | None = None,
) -> AlertRoute:
    resolved_channel = normalize_notification_channel(channel)
    if resolved_channel == DASHBOARD_CHANNEL:
        return AlertRoute(
            channel=resolved_channel,
            delivery_mode="dashboard_noop",
            destination=None,
            timeout_seconds=0.0,
            headers={},
        )
    if resolved_channel == NOOP_CHANNEL:
        return AlertRoute(
            channel=resolved_channel,
            delivery_mode="noop",
            destination=None,
            timeout_seconds=0.0,
            headers={},
        )
    if resolved_channel != WEBHOOK_CHANNEL:
        raise AlertRoutingError(f"unsupported notification channel: {channel}")

    active_settings = settings or get_settings()
    endpoint = str(destination or active_settings.alert_webhook_url or "").strip()
    if not endpoint:
        raise AlertRoutingError("webhook channel requires destination or ALERT_WEBHOOK_URL")

    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = str(active_settings.alert_webhook_auth_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    timeout_seconds = float(max(int(active_settings.alert_webhook_timeout_sec), 1))
    secret = str(active_settings.alert_webhook_secret or "").strip() or None
    return AlertRoute(
        channel=resolved_channel,
        delivery_mode="webhook",
        destination=endpoint,
        timeout_seconds=timeout_seconds,
        headers=headers,
        webhook_secret=secret,
    )


def send_webhook_delivery(
    *,
    route: AlertRoute,
    delivery: NotificationDelivery,
    now: datetime | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if route.delivery_mode != "webhook" or not route.destination:
        raise AlertDeliveryError("route is not a webhook route")

    sent_at = now or datetime.now(UTC)
    payload = _build_webhook_payload(delivery=delivery, sent_at=sent_at)
    request_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    headers = dict(route.headers)
    if route.webhook_secret:
        headers["X-Goofish-Signature"] = _build_webhook_signature(route.webhook_secret, request_bytes)

    own_client = client is None
    active_client = client or httpx.Client(timeout=route.timeout_seconds)
    try:
        response = active_client.post(route.destination, content=request_bytes, headers=headers)
    except httpx.TimeoutException as exc:
        raise AlertDeliveryError(f"webhook timeout after {route.timeout_seconds:.1f}s") from exc
    except httpx.HTTPError as exc:
        raise AlertDeliveryError(f"webhook transport error: {exc}") from exc
    finally:
        if own_client:
            active_client.close()

    if response.status_code < 200 or response.status_code >= 300:
        raise AlertDeliveryError(f"webhook http {response.status_code}: {_response_excerpt(response)}")

    provider_message_id = _extract_provider_message_id(response)
    return {
        "status_code": int(response.status_code),
        "provider_message_id": provider_message_id,
        "response_excerpt": _response_excerpt(response),
    }


def _build_webhook_payload(*, delivery: NotificationDelivery, sent_at: datetime) -> dict[str, Any]:
    return {
        "event_type": "buy_alert_notification",
        "sent_at": sent_at.isoformat(),
        "delivery": {
            "id": str(delivery.id),
            "alert_event_id": str(delivery.alert_event_id) if delivery.alert_event_id else None,
            "channel": str(delivery.channel or ""),
            "destination": delivery.destination,
            "attempt_count": int(delivery.attempt_count or 0),
            "max_attempts": int(delivery.max_attempts or 0),
            "created_at": delivery.created_at.isoformat() if delivery.created_at else None,
        },
        "payload": dict(delivery.payload or {}),
    }


def _build_webhook_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _extract_provider_message_id(response: httpx.Response) -> str | None:
    for header in ("x-goofish-message-id", "x-request-id", "x-correlation-id"):
        value = response.headers.get(header)
        if value:
            return value

    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("provider_message_id", "message_id", "messageId", "request_id", "requestId", "id"):
        value = payload.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def _response_excerpt(response: httpx.Response, *, limit: int = 240) -> str:
    text = (response.text or "").strip()
    if not text:
        return "empty-response"
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."
