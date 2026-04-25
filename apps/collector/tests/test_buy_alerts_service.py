from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from goofish_insight.application.services.buy_alerts import (
    build_alert_payload,
    build_alert_reason,
    has_active_alert_event,
    is_alert_eligible_opportunity,
    is_positive_alert_feedback_label,
    link_buy_feedback_to_alert_candidate_with_session,
)
from goofish_insight.compat import UTC
from goofish_insight.models import BuyAlertEvent, BuyOpportunity, BuyWatchTarget


class _FakeExecuteResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows) -> None:
        self._rows = rows

    def execute(self, stmt):
        return _FakeExecuteResult(self._rows)


class _FakeLinkSession(_FakeSession):
    def __init__(self, rows, watch_target: BuyWatchTarget | None) -> None:
        super().__init__(rows)
        self.watch_target = watch_target
        self.added: list[object] = []

    def get(self, model, key):
        if getattr(model, "__name__", "") == "BuyWatchTarget":
            return self.watch_target
        return None

    def add(self, row) -> None:
        self.added.append(row)


class BuyAlertServiceTests(unittest.TestCase):
    def test_build_alert_reason_uses_score_and_discount(self) -> None:
        opportunity = BuyOpportunity(
            id="opp-1",
            item_id_ref=123,
            watch_target_id="target-1",
            discount_rate=Decimal("0.1333"),
            opportunity_score=Decimal("72.5"),
        )

        reason = build_alert_reason(opportunity)

        self.assertIn("score=72.5", reason)
        self.assertIn("discount=13.3%", reason)

    def test_build_alert_payload_includes_listing_context(self) -> None:
        opportunity = BuyOpportunity(
            id="opp-1",
            item_id_ref=123,
            watch_target_id="target-1",
            current_price=Decimal("7800"),
            fair_price=Decimal("9000"),
            buy_ceiling=Decimal("8200"),
            discount_rate=Decimal("0.1333"),
            opportunity_score=Decimal("72.5"),
            risk_score=Decimal("8"),
            payload={
                "pricing_record": {
                    "item_id": "xianyu-1",
                    "title": "MacBook Pro M5 16G 512G",
                    "listing_url": "https://example.test/item",
                    "region": "上海",
                }
            },
        )

        payload = build_alert_payload(opportunity)

        self.assertEqual(payload["opportunity"]["current_price"], 7800.0)
        self.assertEqual(payload["listing"]["item_id"], "xianyu-1")
        self.assertEqual(payload["listing"]["region"], "上海")

    def test_has_active_alert_event_uses_pending_and_sent_cooldown(self) -> None:
        opportunity = BuyOpportunity(
            id="opp-1",
            item_id_ref=123,
            watch_target_id="target-1",
        )
        target = BuyWatchTarget(
            id="target-1",
            category_id="cat-apple",
            target_name="default",
            notify_cooldown_minutes=30,
        )
        now = datetime(2026, 4, 8, 12, 0, tzinfo=UTC)

        pending_session = _FakeSession(
            [
                BuyAlertEvent(
                    opportunity_id="opp-1",
                    watch_target_id="target-1",
                    status="PENDING",
                )
            ]
        )
        self.assertTrue(
            has_active_alert_event(
                session=pending_session,
                opportunity=opportunity,
                watch_target=target,
                now=now,
            )
        )

        expired_sent_session = _FakeSession(
            [
                BuyAlertEvent(
                    opportunity_id="opp-1",
                    watch_target_id="target-1",
                    status="SENT",
                    created_at=now - timedelta(minutes=31),
                )
            ]
        )
        self.assertFalse(
            has_active_alert_event(
                session=expired_sent_session,
                opportunity=opportunity,
                watch_target=target,
                now=now,
            )
        )

    def test_positive_feedback_labels_drive_alert_hit_rate(self) -> None:
        self.assertTrue(is_positive_alert_feedback_label("contacted"))
        self.assertTrue(is_positive_alert_feedback_label("purchased"))
        self.assertFalse(is_positive_alert_feedback_label("not_worth_it"))

    def test_alert_eligibility_requires_guidance_ready_template(self) -> None:
        eligible = BuyOpportunity(
            id="opp-open",
            item_id_ref=123,
            watch_target_id="target-1",
            status="OPEN",
            payload={
                "templateAvailabilityTier": "guidance_ready",
                "matchedTemplateKey": "apple_computer|model_name=MacBook Pro / M5|chip_family=M5|memory_gb=16|storage_gb=512",
                "baseline_match_level": "template",
            },
        )
        degraded = BuyOpportunity(
            id="opp-degraded",
            item_id_ref=124,
            watch_target_id="target-1",
            status="REFERENCE_ONLY",
            payload={
                "templateAvailabilityTier": "reference_only",
                "matchedTemplateKey": None,
                "baseline_match_level": "degraded_product",
            },
        )

        self.assertTrue(is_alert_eligible_opportunity(eligible))
        self.assertFalse(is_alert_eligible_opportunity(degraded))

    def test_alert_eligibility_relaxes_when_strict_mode_disabled(self) -> None:
        degraded_open = BuyOpportunity(
            id="opp-degraded-open",
            item_id_ref=124,
            watch_target_id="target-1",
            status="OPEN",
            payload={
                "templateAvailabilityTier": "reference_only",
                "matchedTemplateKey": None,
                "baseline_match_level": "degraded_product",
            },
        )

        with patch(
            "goofish_insight.application.services.template_feature_flags.is_price_template_alert_strict_mode_enabled",
            return_value=False,
        ):
            self.assertTrue(is_alert_eligible_opportunity(degraded_open))

    def test_link_buy_feedback_to_alert_candidate_creates_pending_event(self) -> None:
        opportunity = BuyOpportunity(
            id="opp-link-1",
            item_id_ref=123,
            watch_target_id="target-1",
            status="CONTACTED",
            opportunity_score=Decimal("71.5"),
            discount_rate=Decimal("0.12"),
            payload={
                "templateAvailabilityTier": "guidance_ready",
                "matchedTemplateKey": "apple_computer|model_name=MacBook Pro",
                "baseline_match_level": "template",
                "pricing_record": {"item_id": "xianyu-1", "title": "MacBook Pro"},
            },
        )
        watch_target = BuyWatchTarget(
            id="target-1",
            category_id="cat-apple",
            target_name="default",
            notify_cooldown_minutes=30,
        )
        session = _FakeLinkSession([], watch_target)
        with (
            patch(
                "goofish_insight.application.services.template_feature_flags.is_price_template_alert_strict_mode_enabled",
                return_value=True,
            ),
            patch("goofish_analyzer.services.buy_alerts._flush"),
            patch(
                "goofish_insight.application.services.notification_delivery.create_notification_delivery_for_alert",
                return_value=object(),
            ),
        ):
            result = link_buy_feedback_to_alert_candidate_with_session(
                session,
                opportunity=opportunity,
                status_at_feedback="OPEN",
                linkage_source="buy_feedback:accept",
            )

        self.assertEqual(result["status"], "created")
        self.assertEqual(result["reason"], "candidate_created")
        created_alerts = [row for row in session.added if isinstance(row, BuyAlertEvent)]
        self.assertEqual(len(created_alerts), 1)
        self.assertEqual(created_alerts[0].status, "PENDING")


if __name__ == "__main__":
    unittest.main()
