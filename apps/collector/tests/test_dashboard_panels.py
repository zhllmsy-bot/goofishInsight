from __future__ import annotations

import unittest
from datetime import UTC, datetime

from goofish_insight.application.services.dashboard_panels import build_market_focus


class DashboardPanelsTests(unittest.TestCase):
    def test_build_market_focus_does_not_promote_single_sample_premium_group(self) -> None:
        pricing_records = [
            {
                "business_domain": "apple_computer",
                "brand": "Apple",
                "product_label": "Mac mini / M4",
                "spec_label": None,
                "price": 3850.0,
                "seller_key": "seller-a",
                "item_id": "a",
                "title": "Mac mini M4",
                "last_seen_at": None,
                "exact_spec_ready": True,
                "spec_confidence": 0.95,
            },
            {
                "business_domain": "apple_computer",
                "brand": "Apple",
                "product_label": "Mac mini / M4",
                "spec_label": None,
                "price": 3900.0,
                "seller_key": "seller-b",
                "item_id": "b",
                "title": "Mac mini M4",
                "last_seen_at": None,
                "exact_spec_ready": True,
                "spec_confidence": 0.95,
            },
            {
                "business_domain": "apple_computer",
                "brand": "Apple",
                "product_label": "Mac mini / M4",
                "spec_label": None,
                "price": 3950.0,
                "seller_key": "seller-c",
                "item_id": "c",
                "title": "Mac mini M4",
                "last_seen_at": None,
                "exact_spec_ready": True,
                "spec_confidence": 0.95,
            },
            {
                "business_domain": "apple_computer",
                "brand": "Apple",
                "product_label": "MacBook Pro / M4 Max",
                "spec_label": None,
                "price": 36700.0,
                "seller_key": "seller-z",
                "item_id": "z",
                "title": "MacBook Pro M4 Max",
                "last_seen_at": None,
                "exact_spec_ready": True,
                "spec_confidence": 0.95,
            },
        ]

        cards = build_market_focus(
            pricing_records=pricing_records,
            filters={},
            min_sample_points=4,
        )

        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[2]["title"], "高客单重点")
        self.assertTrue(cards[2]["empty"])

    def test_build_market_focus_includes_pricing_availability_summary(self) -> None:
        now = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
        pricing_records = [
            {
                "business_domain": "apple_computer",
                "brand": "Apple",
                "product_label": "MacBook Pro / M5",
                "spec_label": "MacBook Pro / M5 / 16G / 512G",
                "price": 7200.0,
                "seller_key": "seller-a",
                "item_id": "a",
                "title": "MacBook Pro M5 16G 512G",
                "last_seen_at": now,
                "first_seen_at": datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
                "publish_time": datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
                "exact_spec_ready": True,
                "spec_confidence": 0.95,
                "screen_size_in": 14.2,
                "chip_family": "M5",
                "memory_gb": 16,
                "storage_gb": 512,
            },
            {
                "business_domain": "apple_computer",
                "brand": "Apple",
                "product_label": "MacBook Pro / M5",
                "spec_label": "MacBook Pro / M5 / 16G / 512G",
                "price": 7300.0,
                "seller_key": "seller-b",
                "item_id": "b",
                "title": "MacBook Pro M5 16G 512G",
                "last_seen_at": datetime(2026, 4, 10, 11, 0, tzinfo=UTC),
                "first_seen_at": datetime(2026, 4, 8, 11, 0, tzinfo=UTC),
                "publish_time": datetime(2026, 4, 8, 11, 0, tzinfo=UTC),
                "exact_spec_ready": True,
                "spec_confidence": 0.95,
                "screen_size_in": 14.2,
                "chip_family": "M5",
                "memory_gb": 16,
                "storage_gb": 512,
            },
            {
                "business_domain": "apple_computer",
                "brand": "Apple",
                "product_label": "MacBook Pro / M5",
                "spec_label": "MacBook Pro / M5 / 16G / 512G",
                "price": 7400.0,
                "seller_key": "seller-c",
                "item_id": "c",
                "title": "MacBook Pro M5 16G 512G",
                "last_seen_at": datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
                "first_seen_at": datetime(2026, 4, 8, 10, 0, tzinfo=UTC),
                "publish_time": datetime(2026, 4, 8, 10, 0, tzinfo=UTC),
                "exact_spec_ready": True,
                "spec_confidence": 0.95,
                "screen_size_in": 14.2,
                "chip_family": "M5",
                "memory_gb": 16,
                "storage_gb": 512,
            },
            {
                "business_domain": "apple_computer",
                "brand": "Apple",
                "product_label": "MacBook Pro / M5",
                "spec_label": "MacBook Pro / M5 / 16G / 512G",
                "price": 7600.0,
                "seller_key": "seller-d",
                "item_id": "d",
                "title": "MacBook Pro M5 16G 512G",
                "last_seen_at": datetime(2026, 4, 10, 9, 0, tzinfo=UTC),
                "first_seen_at": datetime(2026, 4, 8, 9, 0, tzinfo=UTC),
                "publish_time": datetime(2026, 4, 8, 9, 0, tzinfo=UTC),
                "exact_spec_ready": True,
                "spec_confidence": 0.95,
                "screen_size_in": 14.2,
                "chip_family": "M5",
                "memory_gb": 16,
                "storage_gb": 512,
            },
        ]

        cards = build_market_focus(
            pricing_records=pricing_records,
            filters={},
            min_sample_points=3,
            pricing_contract={"templateCompleteness": {"isComplete": True}},
        )

        visible_cards = [card for card in cards if not card["empty"]]
        self.assertTrue(visible_cards)
        self.assertEqual(
            visible_cards[0]["pricingAvailabilitySummary"]["readinessSummary"],
            "仅参考：样本达基础线但未到指导线",
        )


if __name__ == "__main__":
    unittest.main()
