from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from goofish_insight.application.services.alert_dispatcher import dispatch_notification_delivery_with_session
from goofish_insight.application.services.notification_delivery import (
    DEAD_STATUS,
    PENDING_STATUS,
    SENT_STATUS,
    create_notification_delivery_for_alert,
)
from goofish_insight.compat import UTC
from goofish_insight.models import BuyAlertEvent


class _FakeSession:
    def __init__(self, alert: BuyAlertEvent | None) -> None:
        self.alert = alert

    def get(self, model, key):
        if model is BuyAlertEvent and self.alert is not None and str(self.alert.id) == str(key):
            return self.alert
        return None


class AlertDispatcherServiceTests(unittest.TestCase):
    def test_dashboard_delivery_marks_delivery_and_alert_sent(self) -> None:
        now = datetime(2026, 4, 14, 11, 0, tzinfo=UTC)
        alert = BuyAlertEvent(
            id="11111111-1111-1111-1111-111111111111",
            opportunity_id="22222222-2222-2222-2222-222222222222",
            watch_target_id="33333333-3333-3333-3333-333333333333",
            alert_channel="dashboard",
            status="PENDING",
            payload={},
        )
        delivery = create_notification_delivery_for_alert(alert, now=now)

        result = dispatch_notification_delivery_with_session(_FakeSession(alert), delivery, now=now)

        self.assertEqual(result["status"], SENT_STATUS)
        self.assertEqual(delivery.status, SENT_STATUS)
        self.assertEqual(alert.status, "SENT")
        self.assertEqual(alert.sent_at, now)
        self.assertIsNone(delivery.next_retry_at)

    def test_unsupported_delivery_channel_uses_retry_then_dead_letter(self) -> None:
        now = datetime(2026, 4, 14, 11, 0, tzinfo=UTC)
        alert = BuyAlertEvent(
            id="11111111-1111-1111-1111-111111111111",
            opportunity_id="22222222-2222-2222-2222-222222222222",
            watch_target_id="33333333-3333-3333-3333-333333333333",
            alert_channel="telegram",
            status="PENDING",
            payload={},
        )
        delivery = create_notification_delivery_for_alert(alert, now=now, max_attempts=2)

        first = dispatch_notification_delivery_with_session(_FakeSession(alert), delivery, now=now)

        self.assertEqual(first["status"], PENDING_STATUS)
        self.assertEqual(delivery.attempt_count, 1)
        self.assertIsNotNone(delivery.next_retry_at)
        self.assertEqual(alert.status, "PENDING")

        second = dispatch_notification_delivery_with_session(_FakeSession(alert), delivery, now=now)

        self.assertEqual(second["status"], DEAD_STATUS)
        self.assertEqual(delivery.status, DEAD_STATUS)
        self.assertIsNone(delivery.next_retry_at)

    def test_webhook_delivery_marks_delivery_sent(self) -> None:
        now = datetime(2026, 4, 14, 11, 0, tzinfo=UTC)
        alert = BuyAlertEvent(
            id="11111111-1111-1111-1111-111111111111",
            opportunity_id="22222222-2222-2222-2222-222222222222",
            watch_target_id="33333333-3333-3333-3333-333333333333",
            alert_channel="webhook",
            status="PENDING",
            payload={},
        )
        delivery = create_notification_delivery_for_alert(
            alert,
            now=now,
            destination="https://hooks.example.test/alerts",
        )

        with patch(
            "goofish_insight.application.services.alert_dispatcher.send_webhook_delivery",
            return_value={
                "status_code": 202,
                "provider_message_id": "provider-123",
                "response_excerpt": "accepted",
            },
        ) as send_mock:
            result = dispatch_notification_delivery_with_session(_FakeSession(alert), delivery, now=now)

        send_mock.assert_called_once()
        self.assertEqual(result["status"], SENT_STATUS)
        self.assertEqual(result["providerMessageId"], "provider-123")
        self.assertEqual(delivery.status, SENT_STATUS)
        self.assertEqual(delivery.metadata_json["provider_message_id"], "provider-123")
        self.assertEqual(alert.status, "SENT")

    def test_webhook_dry_run_marks_delivery_without_network(self) -> None:
        now = datetime(2026, 4, 14, 11, 0, tzinfo=UTC)
        alert = BuyAlertEvent(
            id="11111111-1111-1111-1111-111111111111",
            opportunity_id="22222222-2222-2222-2222-222222222222",
            watch_target_id="33333333-3333-3333-3333-333333333333",
            alert_channel="webhook",
            status="PENDING",
            payload={},
        )
        delivery = create_notification_delivery_for_alert(
            alert,
            now=now,
            destination="https://hooks.example.test/alerts",
        )

        with patch(
            "goofish_insight.application.services.alert_dispatcher.send_webhook_delivery"
        ) as send_mock:
            result = dispatch_notification_delivery_with_session(
                _FakeSession(alert),
                delivery,
                dry_run=True,
                now=now,
            )

        send_mock.assert_not_called()
        self.assertEqual(result["status"], SENT_STATUS)
        self.assertEqual(delivery.metadata_json["delivery_mode"], "webhook_dry_run")
        self.assertTrue(delivery.metadata_json["dry_run"])


if __name__ == "__main__":
    unittest.main()
