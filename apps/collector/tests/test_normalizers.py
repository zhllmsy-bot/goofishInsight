from __future__ import annotations

from decimal import Decimal
import unittest

from goofish_insight.normalizers import (
    compute_price_sanity_score,
    extract_price,
    normalize_market_price,
    normalize_title,
)


class NormalizerTests(unittest.TestCase):
    def test_normalize_market_price_converts_obvious_fen_values(self) -> None:
        self.assertEqual(
            normalize_market_price(
                Decimal("620017"),
                business_domain="apple_m_series",
                model_family="Mac Studio",
            ),
            Decimal("6200.17"),
        )
        self.assertEqual(normalize_market_price(Decimal("20500")), Decimal("20500"))
        self.assertEqual(
            normalize_market_price(
                Decimal("16609"),
                business_domain="garmin",
                model_family="Fenix",
            ),
            Decimal("1660.90"),
        )
        self.assertEqual(
            normalize_market_price(
                Decimal("90012"),
                business_domain="garmin",
                model_family="Fenix",
            ),
            Decimal("900.12"),
        )

    def test_extract_price_applies_market_price_normalization(self) -> None:
        self.assertEqual(
            extract_price([{"type": "integer", "text": "900011"}]),
            Decimal("9000.11"),
        )
        self.assertEqual(
            extract_price([{"type": "integer", "text": "6599"}]),
            Decimal("6599"),
        )

    def test_normalize_title_uses_rule_alias_for_short_apple_model_family(self) -> None:
        normalized = normalize_title("自用 MBP M3 Pro 18G 512G 国行")

        self.assertEqual(normalized["brand"], "Apple")
        self.assertEqual(normalized["model_family"], "MacBook Pro")
        self.assertEqual(normalized["chip"], "M3")
        self.assertEqual(normalized["memory_gb"], 18)
        self.assertEqual(normalized["storage_gb"], 512)

    def test_normalize_title_uses_rule_alias_for_chinese_garmin_family(self) -> None:
        normalized = normalize_title("佳明飞耐时8 51mm 蓝宝石太阳能")

        self.assertEqual(normalized["brand"], "Garmin")
        self.assertEqual(normalized["model_family"], "Fenix")

    def test_compute_price_sanity_score_uses_manual_fallback_when_samples_insufficient(self) -> None:
        score = compute_price_sanity_score(
            price=Decimal("1200"),
            category_code="garmin_watch",
            historical_prices=[Decimal("1100"), Decimal("1300"), Decimal("1400")],
        )

        self.assertEqual(score["method"], "manual_fallback")
        self.assertEqual(score["verdict"], "normal")
        self.assertGreater(score["score"], 0.0)
        self.assertEqual(score["sample_count"], 3)
        self.assertEqual(score["range_low"], 300.0)
        self.assertEqual(score["range_high"], 30000.0)

    def test_compute_price_sanity_score_uses_historical_quantile_when_samples_enough(self) -> None:
        historical = [Decimal(str(1000 + index * 5)) for index in range(120)]
        score = compute_price_sanity_score(
            price=Decimal("1800"),
            category_code="apple_computer",
            historical_prices=historical,
        )

        self.assertEqual(score["method"], "historical_quantile")
        self.assertEqual(score["verdict"], "high_outlier")
        self.assertLess(score["score"], 0.7)
        self.assertEqual(score["sample_count"], 120)

    def test_compute_price_sanity_score_marks_invalid_when_price_missing(self) -> None:
        score = compute_price_sanity_score(
            price=None,
            category_code="apple_computer",
            historical_prices=[],
        )

        self.assertEqual(score["method"], "manual_fallback")
        self.assertEqual(score["verdict"], "invalid_price")
        self.assertEqual(score["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
