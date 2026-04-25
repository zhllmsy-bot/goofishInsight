from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from goofish_insight.application.services.apple_preprocess import (
    apply_apple_rule_deactivation_review_state,
    infer_apple_deactivation_reason,
    infer_apple_min_plausible_price,
    title_is_legacy_intel_apple,
)


class ApplePreprocessTest(unittest.TestCase):
    def test_infer_apple_min_plausible_price_uses_studio_ultra_floor(self) -> None:
        self.assertEqual(
            infer_apple_min_plausible_price(
                model_family="Mac Studio",
                chip_family="M3 Ultra",
            ),
            Decimal("7000"),
        )

    def test_infer_apple_min_plausible_price_uses_conservative_air_floor(self) -> None:
        self.assertEqual(
            infer_apple_min_plausible_price(
                model_family="MacBook Air",
                chip_family="M1",
            ),
            Decimal("800"),
        )

    def test_low_placeholder_price_is_rejected(self) -> None:
        item = SimpleNamespace(
            business_domain="apple_m_series",
            current_price=Decimal("3.00"),
            normalized_model_family="MacBook Pro",
            normalized_chip="M4 Max",
            title="MacBook Pro 16寸 M4 Max 128G 4T",
        )
        self.assertEqual(
            infer_apple_deactivation_reason(
                item=item,
                inferred={"model_family": "MacBook Pro", "chip": "M4 Max"},
            ),
            "apple_price_below_floor",
        )

    def test_normal_price_is_kept(self) -> None:
        item = SimpleNamespace(
            business_domain="apple_computer",
            current_price=Decimal("8699.00"),
            normalized_model_family="MacBook Pro",
            normalized_chip="M4",
            title="MacBook Pro 14寸 M4 16G 512G",
        )
        self.assertIsNone(
            infer_apple_deactivation_reason(
                item=item,
                inferred={"model_family": "MacBook Pro", "chip": "M4"},
            )
        )

    def test_legacy_intel_mac_is_rejected(self) -> None:
        item = SimpleNamespace(
            business_domain="apple_m_series",
            current_price=Decimal("4500.00"),
            normalized_model_family="MacBook Pro",
            normalized_chip=None,
            title="MacBook Pro 16寸 2019款 Intel Core i9 32G 1TB",
        )
        self.assertTrue(title_is_legacy_intel_apple(item.title))
        self.assertEqual(
            infer_apple_deactivation_reason(
                item=item,
                inferred={"model_family": "MacBook Pro", "chip": None},
            ),
            "apple_non_m_series",
        )

    def test_apple_intelligence_string_does_not_trigger_intel_rule(self) -> None:
        self.assertFalse(
            title_is_legacy_intel_apple(
                "Mac mini M4 支持 Apple Intelligence 16G 256G"
            )
        )

    def test_apply_apple_rule_deactivation_review_state_marks_item_review_complete(self) -> None:
        reviewed_at = datetime(2026, 4, 4, 2, 0, 0, tzinfo=UTC)
        item = SimpleNamespace(
            llm_reviewed=False,
            llm_review_status="pending",
            llm_review_reason=None,
            llm_reviewed_at=None,
            llm_review_confidence=None,
            llm_review_needs_audit=True,
            llm_review_audit_reason="old",
            llm_review_decision={},
        )

        apply_apple_rule_deactivation_review_state(
            item=item,
            reason="apple_non_m_series",
            reviewed_at=reviewed_at,
        )

        self.assertTrue(item.llm_reviewed)
        self.assertEqual(item.llm_review_status, "invalid")
        self.assertEqual(item.llm_review_reason, "apple_non_m_series")
        self.assertEqual(item.llm_reviewed_at, reviewed_at)
        self.assertEqual(item.llm_review_confidence, Decimal("1.0"))
        self.assertFalse(item.llm_review_needs_audit)
        self.assertIsNone(item.llm_review_audit_reason)
        self.assertEqual(
            item.llm_review_decision,
            {
                "review_status": "invalid",
                "invalid_reason": "apple_non_m_series",
                "confidence": 1.0,
                "review_origin": "rule_precheck",
            },
        )


if __name__ == "__main__":
    unittest.main()
