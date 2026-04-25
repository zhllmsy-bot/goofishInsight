from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from decimal import Decimal

from goofish_insight.application.services.buy_price_baselines import (
    _prune_stale_buy_price_baselines,
    build_buy_price_baseline_explanation,
    build_baseline_key,
    build_buy_price_baselines_with_session,
    upsert_buy_price_baseline_from_pricing_row,
)
from goofish_insight.models import BuyPriceBaseline, Category


class _FakeExecuteResult:
    def __init__(self, row=None, rows=None) -> None:
        self._row = row
        self._rows = list(rows or ([] if row is None else [row]))

    def scalar_one_or_none(self):
        return self._row

    def scalars(self):
        return _FakeScalarResult(self._rows)


class _FakeScalarResult:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, *, execute_results=None) -> None:
        self.execute_results = list(execute_results or [])
        self.added = []
        self.deleted = []

    def execute(self, stmt):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeExecuteResult()

    def add(self, obj) -> None:
        self.added.append(obj)

    def delete(self, obj) -> None:
        self.deleted.append(obj)


class BuyPriceBaselineServiceTests(unittest.TestCase):
    def test_build_baseline_key_prefers_label_and_includes_view(self) -> None:
        key = build_baseline_key(
            pricing_row={
                "label": "MacBook Pro / M5 / 16G / 512G",
                "spec_label": "fallback",
            },
            view="spec",
        )

        self.assertEqual(key, "spec:MacBook Pro / M5 / 16G / 512G")

    def test_upsert_creates_baseline_from_pricing_row(self) -> None:
        session = _FakeSession()
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )

        row = upsert_buy_price_baseline_from_pricing_row(
            session,
            category=category,
            pricing_row={
                "label": "MacBook Pro / M5 / 16G / 512G",
                "product_label": "MacBook Pro / M5",
                "chip_family": "M5",
                "memory_gb": 16,
                "storage_gb": 512,
                "seller_sample_count": 7,
                "unique_seller_count": 4,
                "exact_spec_ratio": 0.85,
                "median_price": 8800,
                "good_value_price": 8000,
                "high_price_floor": 9600,
                "fair_price": 8800,
                "target_buy_ceiling": 8200,
                "reliability_score": 82.35,
                "latest_seen_at": datetime.now(UTC).isoformat(),
            },
            view="spec",
            baseline_date=date(2026, 4, 8),
            build_config={"freshness_days": 30},
        )

        self.assertEqual(session.added, [row])
        self.assertEqual(row.category_id, "cat-apple")
        self.assertEqual(row.baseline_key, "spec:MacBook Pro / M5 / 16G / 512G")
        self.assertEqual(row.memory_gb, 16)
        self.assertEqual(row.storage_gb, 512)
        self.assertEqual(row.sample_size, 7)
        self.assertEqual(row.fair_price, Decimal("8800"))
        self.assertEqual(row.buy_ceiling, Decimal("8200"))
        self.assertEqual(row.confidence, Decimal("0.8235"))
        self.assertEqual(row.payload["build_config"]["freshness_days"], 30)
        self.assertEqual(
            row.payload["pricingTemplate"]["templateKey"],
            "apple_computer|model_name=MacBook Pro / M5|chip_family=M5|memory_gb=16|storage_gb=512",
        )
        self.assertEqual(
            row.payload["pricingTemplate"]["availability"]["availabilityTier"],
            "guidance_ready",
        )
        explanation = build_buy_price_baseline_explanation(row)
        self.assertEqual(explanation["readinessSummary"], "可直接作为买入线参考")
        self.assertEqual(explanation["confidenceSummary"], "高置信")
        self.assertEqual(explanation["sellerSampleCount"], 7)

    def test_upsert_updates_existing_baseline(self) -> None:
        existing = BuyPriceBaseline(
            category_id="cat-apple",
            baseline_key="spec:MacBook Pro / M5",
            baseline_date=date(2026, 4, 8),
            sample_size=1,
        )
        session = _FakeSession(execute_results=[_FakeExecuteResult(existing)])
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )

        row = upsert_buy_price_baseline_from_pricing_row(
            session,
            category=category,
            pricing_row={
                "label": "MacBook Pro / M5",
                "seller_sample_count": 3,
                "fair_price": 9000,
                "target_buy_ceiling": 8400,
            },
            view="spec",
            baseline_date=date(2026, 4, 8),
        )

        self.assertIs(row, existing)
        self.assertEqual(session.added, [])
        self.assertEqual(row.sample_size, 3)
        self.assertEqual(row.fair_price, Decimal("9000"))
        self.assertEqual(row.buy_ceiling, Decimal("8400"))

    def test_baseline_explanation_surfaces_block_reason_label(self) -> None:
        row = BuyPriceBaseline(
            category_id="cat-apple",
            baseline_key="spec:MacBook Pro / M5",
            baseline_date=date(2026, 4, 8),
            sample_size=2,
            confidence=Decimal("0.5500"),
            payload={
                "pricingTemplate": {
                    "availability": {
                        "availabilityTier": "blocked",
                        "pricingBlockReason": "insufficient_seller_samples",
                        "pricingEvidence": {
                            "sellerSampleCount": 2,
                            "uniqueSellerCount": 1,
                            "exactSpecRatio": 1.0,
                            "reliabilityScore": 55.0,
                            "freshnessDays": 1,
                        },
                    }
                }
            },
        )

        explanation = build_buy_price_baseline_explanation(row)

        self.assertEqual(explanation["availabilityReason"], "insufficient_seller_samples")
        self.assertEqual(explanation["availabilityReasonLabel"], "卖家样本数不足")
        self.assertEqual(explanation["readinessSummary"], "暂不建议引用：卖家样本数不足")

    def test_upsert_keeps_product_level_config_dimensions_empty(self) -> None:
        session = _FakeSession()
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )

        row = upsert_buy_price_baseline_from_pricing_row(
            session,
            category=category,
            pricing_row={
                "label": "MacBook Pro / M5",
                "memory_gb": 16,
                "storage_gb": 512,
                "seller_sample_count": 8,
                "fair_price": 9000,
                "target_buy_ceiling": 8400,
            },
            view="product",
            baseline_date=date(2026, 4, 8),
        )

        self.assertIsNone(row.memory_gb)
        self.assertIsNone(row.storage_gb)

    def test_build_rejects_invalid_view(self) -> None:
        session = _FakeSession()

        with self.assertRaises(Exception):
            build_buy_price_baselines_with_session(
                session,
                category_code="apple_computer",
                view="invalid",
            )

    def test_prune_stale_buy_price_baselines_removes_missing_keys(self) -> None:
        keep = BuyPriceBaseline(
            category_id="cat-apple",
            model_catalog_id=None,
            baseline_key="spec:keep",
            baseline_date=date(2026, 4, 10),
        )
        stale = BuyPriceBaseline(
            category_id="cat-apple",
            model_catalog_id=None,
            baseline_key="spec:stale",
            baseline_date=date(2026, 4, 10),
        )
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[keep, stale])])

        deleted = _prune_stale_buy_price_baselines(
            session,
            category_id="cat-apple",
            baseline_date=date(2026, 4, 10),
            baseline_key_prefixes=("spec:",),
            expected_keys={(None, "spec:keep")},
        )

        self.assertEqual(deleted, 1)
        self.assertEqual(session.deleted, [stale])


if __name__ == "__main__":
    unittest.main()
