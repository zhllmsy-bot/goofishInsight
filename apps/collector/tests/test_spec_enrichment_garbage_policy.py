from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace

from goofish_insight.application.services.spec_enrichment_policy import apply_spec_enrichment_contract


class SpecEnrichmentGarbagePolicyTests(unittest.TestCase):
    def test_rejects_apple_watch_in_apple_computer_domain(self) -> None:
        item = SimpleNamespace(
            business_domain="apple_computer",
            title="Apple Watch Series 10 46mm GPS 版",
            condition_tags=[],
        )
        candidate = SimpleNamespace(
            status="partial",
            confidence=Decimal("0.95"),
            needs_review=False,
            evidence={},
            extraction_payload={},
            edition_tags=[],
            product_line=None,
            chip_family=None,
            memory_gb=None,
            storage_gb=None,
            model_name="Apple Watch Series 10",
            screen_size_in=Decimal("46.0"),
        )

        result = apply_spec_enrichment_contract(item=item, candidate=candidate, source="llm")

        self.assertEqual(result.status, "unresolved")
        self.assertTrue(result.needs_review)
        self.assertEqual((result.evidence or {}).get("reason"), "non_target_apple_watch")
        self.assertIsNone(getattr(result, "screen_size_in", None))

    def test_rejects_invalid_screen_size_in_apple_computer(self) -> None:
        item = SimpleNamespace(
            business_domain="apple_computer",
            title="MacBook Pro 2021 16 inch M1 Pro 16+512",
            condition_tags=[],
        )
        candidate = SimpleNamespace(
            status="partial",
            confidence=Decimal("0.95"),
            needs_review=False,
            evidence={},
            extraction_payload={},
            edition_tags=[],
            product_line="MacBook Pro",
            chip_family="M1 Pro",
            memory_gb=16,
            storage_gb=512,
            model_name="MacBook Pro 2021",
            screen_size_in=Decimal("46.0"),
        )

        result = apply_spec_enrichment_contract(item=item, candidate=candidate, source="rule")

        self.assertEqual(result.status, "unresolved")
        self.assertTrue(result.needs_review)
        self.assertEqual((result.evidence or {}).get("reason"), "invalid_screen_size_in")
        self.assertIsNone(getattr(result, "screen_size_in", None))


if __name__ == "__main__":
    unittest.main()

