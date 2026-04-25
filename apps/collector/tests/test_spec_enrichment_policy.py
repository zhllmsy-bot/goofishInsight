from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace

from goofish_insight.application.services.spec_enrichment_policy import should_auto_retry_existing_enrichment
from goofish_insight.models import Item
from goofish_insight.specs import extract_rule_specs


class SpecEnrichmentPolicyTests(unittest.TestCase):
    def test_apple_rule_requires_screen_size_for_macbook_complete(self) -> None:
        item = Item(
            item_id="apple-mbp-no-screen",
            task_id=1,
            business_domain="apple_computer",
            title="MacBook Pro M3 Pro 18G 512G 国行自用",
        )

        candidate = extract_rule_specs(item)

        self.assertEqual(candidate.status, "partial")
        self.assertTrue(candidate.needs_review)
        self.assertIn("screen_size_in", candidate.extraction_payload["contract"]["missingRequiredFields"])

    def test_apple_rule_becomes_complete_when_screen_size_present(self) -> None:
        item = Item(
            item_id="apple-mbp-complete",
            task_id=1,
            business_domain="apple_computer",
            title="MacBook Pro 14寸 M3 Pro 18G 512G 国行自用",
        )

        candidate = extract_rule_specs(item)

        self.assertEqual(candidate.status, "complete")
        self.assertFalse(candidate.needs_review)
        self.assertEqual(candidate.extraction_payload["contract"]["missingRequiredFields"], [])

    def test_apple_rule_parses_noisy_plus_and_storage_words(self) -> None:
        item = Item(
            item_id="apple-mbp-noisy-config",
            task_id=1,
            business_domain="apple_computer",
            title="MacBook Pro 14寸 M4芯片 16G＋512G 电池100%",
        )

        candidate = extract_rule_specs(item)

        self.assertEqual(candidate.memory_gb, 16)
        self.assertEqual(candidate.storage_gb, 512)
        self.assertEqual(candidate.status, "complete")

    def test_apple_rule_normalizes_split_storage_and_legacy_capacity_markers(self) -> None:
        item = Item(
            item_id="apple-mbp-legacy-capacity",
            task_id=1,
            business_domain="apple_computer",
            title="MacBook Pro 14寸 M1 Pro 8+5 12G / 16G内存 / 500G硬盘",
        )

        candidate = extract_rule_specs(item)

        self.assertEqual(candidate.memory_gb, 8)
        self.assertEqual(candidate.storage_gb, 512)

    def test_apple_rule_parses_one_t_storage_words(self) -> None:
        item = Item(
            item_id="apple-air-1tb",
            task_id=1,
            business_domain="apple_computer",
            title="MacBook Air 13寸 M4芯片 16G内存 1T硬盘 国行",
        )

        candidate = extract_rule_specs(item)

        self.assertEqual(candidate.memory_gb, 16)
        self.assertEqual(candidate.storage_gb, 1024)

    def test_garmin_rule_requires_variant_fields_when_signaled(self) -> None:
        item = Item(
            item_id="garmin-complete",
            task_id=1,
            business_domain="garmin_watch",
            title="佳明 Fenix 7 47mm AMOLED Solar 蓝宝石",
        )

        candidate = extract_rule_specs(item)

        self.assertEqual(candidate.status, "complete")
        self.assertFalse(candidate.needs_review)
        self.assertEqual(candidate.display_type, "AMOLED")
        self.assertTrue(candidate.is_solar)

    def test_garmin_rule_uses_model_defaults_for_forerunner_family(self) -> None:
        item = Item(
            item_id="garmin-forerunner-defaults",
            task_id=1,
            business_domain="garmin_watch",
            title="Garmin佳明 Forerunner 265 月光白 国行",
        )

        candidate = extract_rule_specs(item)

        self.assertEqual(candidate.model_name, "Forerunner 265")
        self.assertEqual(candidate.case_size_mm, 46)
        self.assertEqual(candidate.display_type, "AMOLED")
        self.assertEqual(candidate.status, "complete")

    def test_garmin_rule_stays_partial_when_case_size_missing(self) -> None:
        item = Item(
            item_id="garmin-partial",
            task_id=1,
            business_domain="garmin_watch",
            title="佳明 Fenix 7 Solar 国行自用",
        )

        candidate = extract_rule_specs(item)

        self.assertEqual(candidate.status, "partial")
        self.assertTrue(candidate.needs_review)
        self.assertIn("case_size_mm", candidate.extraction_payload["contract"]["missingRequiredFields"])

    def test_auto_retry_skips_partial_when_contract_fields_are_already_complete(self) -> None:
        item = SimpleNamespace(
            business_domain="apple_computer",
            title="MacBook Pro 14寸 M3 Pro 18G 512G",
            condition_tags=[],
        )
        enrichment = SimpleNamespace(
            status="partial",
            confidence=Decimal("0.60"),
            needs_review=True,
            product_line="MacBook Pro",
            chip_family="M3 Pro",
            model_name="MacBook Pro 14in M3 Pro 18G 512G",
            memory_gb=18,
            storage_gb=512,
            screen_size_in=Decimal("14"),
        )

        self.assertFalse(should_auto_retry_existing_enrichment(item=item, enrichment=enrichment))

    def test_auto_retry_keeps_partial_when_required_fields_are_missing(self) -> None:
        item = SimpleNamespace(
            business_domain="garmin_watch",
            title="佳明 Fenix 7 Solar",
            condition_tags=[],
        )
        enrichment = SimpleNamespace(
            status="partial",
            confidence=Decimal("0.60"),
            needs_review=True,
            product_line="Fenix",
            model_name="Fenix 7",
            case_size_mm=None,
            is_solar=True,
            display_type=None,
            edition_tags=["Solar"],
        )

        self.assertTrue(should_auto_retry_existing_enrichment(item=item, enrichment=enrichment))


if __name__ == "__main__":
    unittest.main()
