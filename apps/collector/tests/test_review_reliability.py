from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest

from goofish_insight.cli import should_reset_llm_review_state
from goofish_insight.application.services.review_apply import (
    classify_review_audit_requirement,
    coerce_review_spec_confidence,
    sync_review_spec_confidence,
)


class ReviewReliabilityTests(unittest.TestCase):
    def test_classify_review_audit_requirement_queues_field_corrections(self) -> None:
        needs_audit, audit_reason = classify_review_audit_requirement(
            review_status="valid",
            entry={
                "item_id": "abc",
                "not_match_field": [{"field_key": "spec.display_type", "true_value": "AMOLED"}],
            },
        )

        self.assertTrue(needs_audit)
        self.assertEqual(audit_reason, "field_corrections")

    def test_classify_review_audit_requirement_queues_invalidations(self) -> None:
        needs_audit, audit_reason = classify_review_audit_requirement(
            review_status="invalid",
            entry={
                "item_id": "abc",
                "invalid_reason": "non_target",
                "not_match_field": [],
            },
        )

        self.assertTrue(needs_audit)
        self.assertEqual(audit_reason, "invalidated_by_llm")

    def test_classify_review_audit_requirement_allows_rule_precheck_invalidations(self) -> None:
        needs_audit, audit_reason = classify_review_audit_requirement(
            review_status="invalid",
            entry={
                "item_id": "abc",
                "invalid_reason": "garbage",
                "review_origin": "rule_precheck",
                "not_match_field": [],
            },
        )

        self.assertFalse(needs_audit)
        self.assertIsNone(audit_reason)

    def test_coerce_review_spec_confidence_normalizes_to_fraction(self) -> None:
        self.assertEqual(coerce_review_spec_confidence(0.9731), Decimal("0.97"))
        self.assertEqual(coerce_review_spec_confidence(97), Decimal("0.97"))
        self.assertIsNone(coerce_review_spec_confidence(None))

    def test_sync_review_spec_confidence_applies_to_llm_review_rows(self) -> None:
        spec = SimpleNamespace(extractor_type="llm_review", confidence=None)
        item = SimpleNamespace(llm_review_confidence=Decimal("0.9731"))

        sync_review_spec_confidence(spec=spec, item=item)

        self.assertEqual(spec.confidence, Decimal("0.97"))

    def test_sync_review_spec_confidence_skips_non_review_extractors(self) -> None:
        spec = SimpleNamespace(extractor_type="hybrid", confidence=None)
        item = SimpleNamespace(llm_review_confidence=Decimal("0.9731"))

        sync_review_spec_confidence(spec=spec, item=item)

        self.assertIsNone(spec.confidence)

    def test_should_reset_llm_review_when_review_input_changes(self) -> None:
        existing = SimpleNamespace(
            llm_reviewed=True,
            llm_review_status="valid",
            title="Garmin Fenix 8",
            source_keyword="fenix 8",
            current_price=Decimal("5200"),
            condition_tags=["95新"],
            region="Shanghai",
            normalized_brand="Garmin",
            normalized_model_family="Fenix",
            normalized_model="Fenix 8",
            normalized_chip=None,
            normalized_memory_gb=None,
            normalized_storage_gb=None,
        )

        self.assertTrue(
            should_reset_llm_review_state(
                existing=existing,
                title="Garmin Fenix 8 AMOLED",
                source_keyword="fenix 8",
                current_price=Decimal("5200"),
                condition_tags=["95新"],
                region="Shanghai",
                normalized_brand="Garmin",
                normalized_model_family="Fenix",
                normalized_model="Fenix 8",
                normalized_chip=None,
                normalized_memory_gb=None,
                normalized_storage_gb=None,
            )
        )

    def test_should_not_reset_llm_review_when_review_input_is_unchanged(self) -> None:
        existing = SimpleNamespace(
            llm_reviewed=True,
            llm_review_status="valid",
            title="MacBook Pro 14 M3 Pro",
            source_keyword="macbook pro 14 m3 pro",
            current_price=Decimal("11800"),
            condition_tags=["99新"],
            region="Beijing",
            normalized_brand="Apple",
            normalized_model_family="MacBook Pro",
            normalized_model="MacBook Pro 14",
            normalized_chip="M3 Pro",
            normalized_memory_gb=18,
            normalized_storage_gb=512,
        )

        self.assertFalse(
            should_reset_llm_review_state(
                existing=existing,
                title="MacBook Pro 14 M3 Pro",
                source_keyword="macbook pro 14 m3 pro",
                current_price=Decimal("11800"),
                condition_tags=["99新"],
                region="Beijing",
                normalized_brand="Apple",
                normalized_model_family="MacBook Pro",
                normalized_model="MacBook Pro 14",
                normalized_chip="M3 Pro",
                normalized_memory_gb=18,
                normalized_storage_gb=512,
            )
        )

    def test_should_not_reset_invalid_review_state(self) -> None:
        existing = SimpleNamespace(
            llm_reviewed=True,
            llm_review_status="invalid",
            title="MacBook parts machine",
            source_keyword="macbook",
            current_price=Decimal("500"),
            condition_tags=["配件机"],
            region="Hangzhou",
            normalized_brand="Apple",
            normalized_model_family="MacBook Pro",
            normalized_model="MacBook Pro 14",
            normalized_chip="M1 Pro",
            normalized_memory_gb=16,
            normalized_storage_gb=512,
        )

        self.assertFalse(
            should_reset_llm_review_state(
                existing=existing,
                title="MacBook parts machine updated",
                source_keyword="macbook",
                current_price=Decimal("600"),
                condition_tags=["配件机"],
                region="Hangzhou",
                normalized_brand="Apple",
                normalized_model_family="MacBook Pro",
                normalized_model="MacBook Pro 14",
                normalized_chip="M1 Pro",
                normalized_memory_gb=16,
                normalized_storage_gb=512,
            )
        )

    def test_should_reset_pending_audit_when_review_input_changes(self) -> None:
        existing = SimpleNamespace(
            llm_reviewed=True,
            llm_review_status="pending_audit",
            title="Garmin Fenix 8",
            source_keyword="fenix 8",
            current_price=Decimal("5200"),
            condition_tags=["95新"],
            region="Shanghai",
            normalized_brand="Garmin",
            normalized_model_family="Fenix",
            normalized_model="Fenix 8",
            normalized_chip=None,
            normalized_memory_gb=None,
            normalized_storage_gb=None,
        )

        self.assertTrue(
            should_reset_llm_review_state(
                existing=existing,
                title="Garmin Fenix 8 Pro",
                source_keyword="fenix 8",
                current_price=Decimal("5200"),
                condition_tags=["95新"],
                region="Shanghai",
                normalized_brand="Garmin",
                normalized_model_family="Fenix",
                normalized_model="Fenix 8",
                normalized_chip=None,
                normalized_memory_gb=None,
                normalized_storage_gb=None,
            )
        )


if __name__ == "__main__":
    unittest.main()
