from __future__ import annotations

import unittest

from goofish_insight.application.services.seller_classification import (
    SellerClassificationInput,
    classify_seller_profile,
)


class SellerClassificationServiceTests(unittest.TestCase):
    def test_repeated_seller_name_marks_commercial_like(self) -> None:
        result = classify_seller_profile(
            SellerClassificationInput(
                seller_name="锐界严选深圳仓",
                item_count=70,
                active_item_count=18,
                domain_count=2,
            )
        )

        self.assertEqual(result.seller_type, "commercial_like")
        self.assertGreaterEqual(result.confidence, 0.85)
        self.assertIn("item_count>=30", result.signals)

    def test_low_repeat_seller_is_only_private_like_heuristic(self) -> None:
        result = classify_seller_profile(
            SellerClassificationInput(
                seller_name="普通用户",
                item_count=1,
                active_item_count=1,
                domain_count=1,
            )
        )

        self.assertEqual(result.seller_type, "private_like")
        self.assertLess(result.confidence, 0.7)


if __name__ == "__main__":
    unittest.main()
