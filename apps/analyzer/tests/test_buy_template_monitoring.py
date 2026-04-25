from __future__ import annotations

import unittest
from datetime import date, datetime
from unittest.mock import patch

from goofish_analyzer.adapters import BuyOpportunity, BuyPriceBaseline, UTC
from goofish_analyzer.services.buy_template_monitoring import (
    PricingMonitoringError,
    summarize_template_availability_monitoring_with_session,
)


class _SessionResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_SessionResult":
        return self

    def all(self) -> list[object]:
        return list(self._rows)

    def scalar_one_or_none(self) -> object | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, *, category: object | None, baselines: list[object], opportunities: list[object]) -> None:
        self.category = category
        self.baselines = baselines
        self.opportunities = opportunities

    def execute(self, statement):
        statement_text = str(statement)
        if "FROM category" in statement_text:
            return _SessionResult([self.category] if self.category is not None else [])
        if "FROM buy_price_baseline" in statement_text:
            return _SessionResult(self.baselines)
        if "FROM buy_opportunity" in statement_text:
            return _SessionResult(self.opportunities)
        raise AssertionError(f"Unexpected statement: {statement_text}")


class BuyTemplateMonitoringTests(unittest.TestCase):
    def test_summarize_template_availability_monitoring_returns_counts_and_flags(self) -> None:
        category = type("Category", (), {"id": "cat-apple", "code": "apple_computer"})()
        baselines = [
            BuyPriceBaseline(
                id="baseline-1",
                category_id="cat-apple",
                baseline_key="template:apple|a",
                baseline_date=date(2026, 4, 21),
                sample_size=8,
                payload={"pricingTemplate": {"availability": {"availabilityTier": "guidance_ready"}}},
            ),
            BuyPriceBaseline(
                id="baseline-2",
                category_id="cat-apple",
                baseline_key="template:apple|b",
                baseline_date=date(2026, 4, 20),
                sample_size=5,
                payload={"pricingTemplate": {"availability": {"availabilityTier": "reference_only"}}},
            ),
        ]
        opportunities = [
            BuyOpportunity(
                id="opp-1",
                item_id_ref=1001,
                watch_target_id="target-1",
                category_id="cat-apple",
                status="OPEN",
                last_detected_at=datetime(2026, 4, 21, 10, 0, tzinfo=UTC),
                payload={"templateAvailabilityTier": "guidance_ready"},
            ),
            BuyOpportunity(
                id="opp-2",
                item_id_ref=1002,
                watch_target_id="target-1",
                category_id="cat-apple",
                status="REFERENCE_ONLY",
                last_detected_at=datetime(2026, 4, 21, 10, 5, tzinfo=UTC),
                payload={"templateAvailabilityTier": "reference_only"},
            ),
        ]
        session = _FakeSession(
            category=category,
            baselines=baselines,
            opportunities=opportunities,
        )

        with (
            patch(
                "goofish_analyzer.services.buy_template_monitoring.is_price_template_contract_enabled",
                return_value=True,
            ),
            patch(
                "goofish_analyzer.services.buy_template_monitoring.is_price_template_dashboard_enabled",
                return_value=True,
            ),
            patch(
                "goofish_analyzer.services.buy_template_monitoring.is_price_template_opportunity_enabled",
                return_value=False,
            ),
            patch(
                "goofish_analyzer.services.buy_template_monitoring.is_price_template_trend_enabled",
                return_value=True,
            ),
            patch(
                "goofish_analyzer.services.buy_template_monitoring.is_price_template_alert_strict_mode_enabled",
                return_value=False,
            ),
        ):
            payload = summarize_template_availability_monitoring_with_session(
                session,
                category_code="apple_computer",
                window_days=30,
            )

        self.assertEqual(payload["categoryCode"], "apple_computer")
        self.assertEqual(payload["baseline"]["count"], 2)
        self.assertEqual(payload["baseline"]["tierCounts"]["guidance_ready"], 1)
        self.assertEqual(payload["opportunity"]["count"], 2)
        self.assertEqual(payload["opportunity"]["statusCounts"]["OPEN"], 1)
        self.assertEqual(payload["featureFlags"]["priceTemplateOpportunityEnabled"], False)
        self.assertEqual(payload["featureFlags"]["priceTemplateAlertStrictMode"], False)

    def test_summarize_template_availability_monitoring_raises_on_missing_category(self) -> None:
        session = _FakeSession(category=None, baselines=[], opportunities=[])

        with self.assertRaises(PricingMonitoringError):
            summarize_template_availability_monitoring_with_session(
                session,
                category_code="missing_category",
                window_days=7,
            )


if __name__ == "__main__":
    unittest.main()
