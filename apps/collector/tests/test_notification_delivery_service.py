from __future__ import annotations

import unittest
from datetime import datetime

from goofish_insight.application.services.notification_delivery import (
    DEAD_STATUS,
    DASHBOARD_CHANNEL,
    NOOP_CHANNEL,
    PENDING_STATUS,
    SENT_STATUS,
    create_notification_delivery_for_alert,
    mark_notification_delivery_failed,
    mark_notification_delivery_sent,
    normalize_notification_channel,
)
from goofish_insight.compat import UTC
from goofish_insight.models import BuyAlertEvent


class NotificationDeliveryServiceTests(unittest.TestCase):
    def test_normalize_notification_channel_maps_aliases(self) -> None:
        self.assertEqual(normalize_notification_channel(None), DASHBOARD_CHANNEL)
        self.assertEqual(normalize_notification_channel(""), DASHBOARD_CHANNEL)
        self.assertEqual(normalize_notification_channel("disabled"), NOOP_CHANNEL)
        self.assertEqual(normalize_notification_channel("none"), NOOP_CHANNEL)
        self.assertEqual(normalize_notification_channel("WEBHOOK"), "webhook")

    def test_create_notification_delivery_for_alert_copies_alert_context(self) -> None:
        now = datetime(2026, 4, 14, 9, 30, tzinfo=UTC)
        alert = BuyAlertEvent(
            id="11111111-1111-1111-1111-111111111111",
            opportunity_id="22222222-2222-2222-2222-222222222222",
            watch_target_id="33333333-3333-3333-3333-333333333333",
            alert_channel="telegram",
            alert_reason="score=88",
            payload={"opportunity": {"current_price": 3200.0}},
        )

        delivery = create_notification_delivery_for_alert(alert, now=now, destination="ops-channel")

        self.assertEqual(delivery.alert_event_id, "11111111-1111-1111-1111-111111111111")
        self.assertEqual(delivery.channel, "telegram")
        self.assertEqual(delivery.destination, "ops-channel")
        self.assertEqual(delivery.status, PENDING_STATUS)
        self.assertEqual(delivery.next_retry_at, now)
        self.assertEqual(delivery.payload["opportunity_id"], "22222222-2222-2222-2222-222222222222")
        self.assertEqual(delivery.payload["alert_payload"]["opportunity"]["current_price"], 3200.0)
        self.assertEqual(delivery.payload["alert_channel"], "telegram")

    def test_mark_notification_delivery_sent_clears_retry_state(self) -> None:
        now = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
        alert = BuyAlertEvent(
            id="11111111-1111-1111-1111-111111111111",
            opportunity_id="22222222-2222-2222-2222-222222222222",
            watch_target_id="33333333-3333-3333-3333-333333333333",
            alert_channel="dashboard",
            payload={},
        )
        delivery = create_notification_delivery_for_alert(alert, now=now)

        mark_notification_delivery_sent(delivery, now=now, metadata={"provider_message_id": "msg-1"})

        self.assertEqual(delivery.status, SENT_STATUS)
        self.assertEqual(delivery.sent_at, now)
        self.assertIsNone(delivery.next_retry_at)
        self.assertEqual(delivery.metadata_json["provider_message_id"], "msg-1")

    def test_mark_notification_delivery_failed_backs_off_and_dead_letters(self) -> None:
        now = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
        alert = BuyAlertEvent(
            id="11111111-1111-1111-1111-111111111111",
            opportunity_id="22222222-2222-2222-2222-222222222222",
            watch_target_id="33333333-3333-3333-3333-333333333333",
            alert_channel="dashboard",
            payload={},
        )
        delivery = create_notification_delivery_for_alert(alert, now=now, max_attempts=2)

        mark_notification_delivery_failed(delivery, error_message="timeout", now=now)

        self.assertEqual(delivery.status, PENDING_STATUS)
        self.assertEqual(delivery.attempt_count, 1)
        self.assertIsNotNone(delivery.next_retry_at)
        self.assertEqual(delivery.error_message, "timeout")

        mark_notification_delivery_failed(delivery, error_message="timeout again", now=now)

        self.assertEqual(delivery.status, DEAD_STATUS)
        self.assertEqual(delivery.attempt_count, 2)
        self.assertIsNone(delivery.next_retry_at)


if __name__ == "__main__":
    unittest.main()
