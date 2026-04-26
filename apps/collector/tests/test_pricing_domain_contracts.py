from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from goofish_insight.domain.pricing.contracts import (
    ALERT_STATUSES,
    AVAILABILITY_TIERS,
    COMPLETENESS_STATUSES,
    OPPORTUNITY_STATUSES,
    PRICING_BLOCK_REASONS,
    QUALITY_TIERS,
    PRICING_RECORD_FIELDS,
    BASELINE_EXPLANATION_FIELDS,
    TEMPLATE_GUIDANCE_FIELDS,
    ALERT_EVENT_FIELDS,
    build_contract_field_lines,
    normalize_alert_status,
    normalize_availability_tier,
    normalize_completeness_status,
    normalize_opportunity_status,
    normalize_pricing_block_reason,
    normalize_quality_tier,
    serialize_alert_event,
    serialize_baseline_explanation,
    serialize_pricing_record,
    serialize_template_guidance,
    validate_alert_event,
    validate_baseline_explanation,
    validate_pricing_record,
    validate_template_guidance,
)


class NormalizeAvailabilityTierTests(unittest.TestCase):
    def test_guidance_ready(self) -> None:
        self.assertEqual(normalize_availability_tier("guidance_ready"), "guidance_ready")

    def test_reference_only(self) -> None:
        self.assertEqual(normalize_availability_tier("reference_only"), "reference_only")

    def test_incomplete(self) -> None:
        self.assertEqual(normalize_availability_tier("incomplete"), "incomplete")

    def test_blocked(self) -> None:
        self.assertEqual(normalize_availability_tier("blocked"), "blocked")

    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_availability_tier("GUIDANCE_READY"), "guidance_ready")
        self.assertEqual(normalize_availability_tier("Reference_Only"), "reference_only")

    def test_none_returns_none(self) -> None:
        self.assertIsNone(normalize_availability_tier(None))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(normalize_availability_tier(""))
        self.assertIsNone(normalize_availability_tier("  "))

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(normalize_availability_tier("unknown_tier"))


class NormalizeQualityTierTests(unittest.TestCase):
    def test_tiers_are_normalized(self) -> None:
        self.assertEqual(normalize_quality_tier("a"), "A")
        self.assertEqual(normalize_quality_tier("B"), "B")
        self.assertEqual(normalize_quality_tier(" c "), "C")
        self.assertIsNone(normalize_quality_tier("unknown"))


class NormalizeOpportunityStatusTests(unittest.TestCase):
    def test_open(self) -> None:
        self.assertEqual(normalize_opportunity_status("OPEN"), "OPEN")

    def test_reference_only(self) -> None:
        self.assertEqual(normalize_opportunity_status("REFERENCE_ONLY"), "REFERENCE_ONLY")

    def test_stale(self) -> None:
        self.assertEqual(normalize_opportunity_status("STALE"), "STALE")

    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_opportunity_status("open"), "OPEN")
        self.assertEqual(normalize_opportunity_status("stale"), "STALE")

    def test_none_returns_none(self) -> None:
        self.assertIsNone(normalize_opportunity_status(None))

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(normalize_opportunity_status("UNKNOWN"))


class NormalizeAlertStatusTests(unittest.TestCase):
    def test_pending(self) -> None:
        self.assertEqual(normalize_alert_status("PENDING"), "PENDING")

    def test_sent(self) -> None:
        self.assertEqual(normalize_alert_status("SENT"), "SENT")

    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_alert_status("pending"), "PENDING")

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(normalize_alert_status("UNKNOWN"))


class NormalizeCompletenessStatusTests(unittest.TestCase):
    def test_complete(self) -> None:
        self.assertEqual(normalize_completeness_status("complete"), "complete")

    def test_partial(self) -> None:
        self.assertEqual(normalize_completeness_status("partial"), "partial")

    def test_missing(self) -> None:
        self.assertEqual(normalize_completeness_status("missing"), "missing")

    def test_legacy(self) -> None:
        self.assertEqual(normalize_completeness_status("legacy"), "legacy")

    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_completeness_status("COMPLETE"), "complete")

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(normalize_completeness_status("unknown"))


class NormalizePricingBlockReasonTests(unittest.TestCase):
    def test_template_incomplete(self) -> None:
        self.assertEqual(normalize_pricing_block_reason("template_incomplete"), "template_incomplete")

    def test_insufficient_seller_samples(self) -> None:
        self.assertEqual(normalize_pricing_block_reason("insufficient_seller_samples"), "insufficient_seller_samples")

    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_pricing_block_reason("TEMPLATE_INCOMPLETE"), "template_incomplete")

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(normalize_pricing_block_reason("unknown_reason"))


class SerializePricingRecordTests(unittest.TestCase):
    def test_serializes_snake_case_to_camel_case(self) -> None:
        record = {
            "item_id_ref": 42,
            "item_id": "item-123",
            "source_platform": "xianyu",
            "category_code": "apple_computer",
            "seller_key": "seller-1",
            "title": "Mac mini M4",
            "price": 3999.0,
            "last_seen_at": datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
            "brand": "Apple",
            "product_label": "Mac mini / M4",
            "product_line": "Mac mini",
            "model_name": "Mac mini",
            "chip_family": "M4",
            "memory_gb": 16,
            "storage_gb": 256,
            "spec_contract": {"status": "complete"},
            "spec_source": {"source": "stored_spec"},
            "pricing_eligibility": {"pricingReady": True},
            "schema_id": 42,
            "sample_snapshot": {
                "schemaId": 42,
                "sampleState": "eligible",
                "fingerprintHash": "abc12345",
                "sampleQualityScore": 0.91,
            },
        }
        result = serialize_pricing_record(record)

        self.assertEqual(result["itemIdRef"], 42)
        self.assertEqual(result["itemId"], "item-123")
        self.assertEqual(result["sourcePlatform"], "xianyu")
        self.assertEqual(result["categoryCode"], "apple_computer")
        self.assertEqual(result["sellerKey"], "seller-1")
        self.assertEqual(result["title"], "Mac mini M4")
        self.assertEqual(result["price"], 3999.0)
        self.assertEqual(result["lastSeenAt"], "2026-04-19T12:00:00+00:00")
        self.assertEqual(result["brand"], "Apple")
        self.assertEqual(result["productLabel"], "Mac mini / M4")
        self.assertEqual(result["productLine"], "Mac mini")
        self.assertEqual(result["modelName"], "Mac mini")
        self.assertEqual(result["chipFamily"], "M4")
        self.assertEqual(result["memoryGb"], 16)
        self.assertEqual(result["storageGb"], 256)
        self.assertEqual(result["specContract"], {"status": "complete"})
        self.assertEqual(result["specSource"], {"source": "stored_spec"})
        self.assertEqual(result["pricingEligibility"], {"pricingReady": True})
        self.assertEqual(result["schemaId"], 42)
        self.assertEqual(result["sampleSnapshot"]["fingerprintHash"], "abc12345")

    def test_handles_decimal_price(self) -> None:
        record = {"price": Decimal("3999.00"), "screen_size_in": Decimal("14.0")}
        result = serialize_pricing_record(record)
        self.assertEqual(result["price"], 3999.0)
        self.assertEqual(result["screenSizeIn"], 14.0)

    def test_handles_none_values(self) -> None:
        record = {"item_id_ref": 1, "price": None, "region": None}
        result = serialize_pricing_record(record)
        self.assertIsNone(result["price"])
        self.assertIsNone(result["region"])


class SerializeBaselineExplanationTests(unittest.TestCase):
    def test_serializes_snake_case_to_camel_case(self) -> None:
        explanation = {
            "readiness_summary": "可直接作为买入线参考",
            "availability_tier": "guidance_ready",
            "availability_reason": None,
            "availability_reason_label": None,
            "confidence_summary": "高置信",
            "seller_sample_count": 7,
            "unique_seller_count": 4,
            "exact_spec_ratio": 0.92,
            "reliability_score": 82.0,
            "effective_sample_count": 6.5,
            "recency_weighted_sample_count": 5.4,
            "mad": 180.0,
            "confidence_score": 82.0,
            "confidence_reasons": ["样本充足", "价格离群较少"],
            "quality_tier": "B",
            "p15_price": 7600.0,
            "p35_price": 8200.0,
            "p50_price": 8800.0,
            "freshness_days": 3,
        }
        result = serialize_baseline_explanation(explanation)

        self.assertEqual(result["readinessSummary"], "可直接作为买入线参考")
        self.assertEqual(result["availabilityTier"], "guidance_ready")
        self.assertEqual(result["confidenceSummary"], "高置信")
        self.assertEqual(result["sellerSampleCount"], 7)
        self.assertEqual(result["uniqueSellerCount"], 4)
        self.assertEqual(result["exactSpecRatio"], 0.92)
        self.assertEqual(result["reliabilityScore"], 82.0)
        self.assertEqual(result["effectiveSampleCount"], 6.5)
        self.assertEqual(result["recencyWeightedSampleCount"], 5.4)
        self.assertEqual(result["mad"], 180.0)
        self.assertEqual(result["confidenceScore"], 82.0)
        self.assertEqual(result["confidenceReasons"], ["样本充足", "价格离群较少"])
        self.assertEqual(result["qualityTier"], "B")
        self.assertEqual(result["p15Price"], 7600.0)
        self.assertEqual(result["p35Price"], 8200.0)
        self.assertEqual(result["p50Price"], 8800.0)
        self.assertEqual(result["freshnessDays"], 3)


class SerializeTemplateGuidanceTests(unittest.TestCase):
    def test_serializes_snake_case_to_camel_case(self) -> None:
        guidance = {
            "category_code": "apple_computer",
            "template_key": "apple_computer|model_name=Mac mini / M4|chip_family=M4",
            "template_label": "Mac mini / M4",
            "resolved_field_values": {"model_name": "Mac mini / M4", "chip_family": "M4"},
            "required_pricing_fields": ["model_name", "chip_family"],
            "pricing_key_fields": ["model_name", "chip_family", "memory_gb", "storage_gb"],
            "missing_fields": [],
            "completeness_status": "complete",
            "unsupported_pricing_fields": [],
        }
        result = serialize_template_guidance(guidance)

        self.assertEqual(result["categoryCode"], "apple_computer")
        self.assertEqual(result["templateKey"], "apple_computer|model_name=Mac mini / M4|chip_family=M4")
        self.assertEqual(result["templateLabel"], "Mac mini / M4")
        self.assertEqual(result["resolvedFieldValues"], {"model_name": "Mac mini / M4", "chip_family": "M4"})
        self.assertEqual(result["requiredPricingFields"], ["model_name", "chip_family"])
        self.assertEqual(result["pricingKeyFields"], ["model_name", "chip_family", "memory_gb", "storage_gb"])
        self.assertEqual(result["missingFields"], [])
        self.assertEqual(result["completenessStatus"], "complete")


class SerializeAlertEventTests(unittest.TestCase):
    def test_serializes_snake_case_to_camel_case(self) -> None:
        alert = {
            "id": "alert-1",
            "opportunity_id": "opp-1",
            "watch_target_id": "target-1",
            "alert_channel": "dashboard",
            "alert_reason": "buy opportunity score=75.0, discount=12.5%",
            "status": "PENDING",
            "sent_at": datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
            "payload": {"source": "test"},
        }
        result = serialize_alert_event(alert)

        self.assertEqual(result["id"], "alert-1")
        self.assertEqual(result["opportunityId"], "opp-1")
        self.assertEqual(result["watchTargetId"], "target-1")
        self.assertEqual(result["alertChannel"], "dashboard")
        self.assertEqual(result["alertReason"], "buy opportunity score=75.0, discount=12.5%")
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["sentAt"], "2026-04-19T12:00:00+00:00")
        self.assertEqual(result["payload"], {"source": "test"})


class ValidatePricingRecordTests(unittest.TestCase):
    def test_valid_record_has_no_errors(self) -> None:
        record = {
            "item_id_ref": 1,
            "item_id": "item-1",
            "source_platform": "xianyu",
            "category_code": "apple_computer",
            "seller_key": "seller-1",
            "title": "Mac mini M4",
            "price": 3999.0,
            "last_seen_at": datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
            "brand": "Apple",
            "product_label": "Mac mini / M4",
        }
        errors = validate_pricing_record(record)
        self.assertEqual(errors, [])

    def test_missing_required_field(self) -> None:
        record = {"item_id_ref": 1}
        errors = validate_pricing_record(record)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("item_id" in e for e in errors))
        self.assertTrue(any("category_code" in e for e in errors))


class ValidateBaselineExplanationTests(unittest.TestCase):
    def test_valid_explanation_has_no_errors(self) -> None:
        explanation = {
            "readiness_summary": "可直接作为买入线参考",
            "confidence_summary": "高置信",
        }
        errors = validate_baseline_explanation(explanation)
        self.assertEqual(errors, [])

    def test_invalid_availability_tier(self) -> None:
        explanation = {
            "readiness_summary": "test",
            "confidence_summary": "test",
            "availability_tier": "invalid_tier",
        }
        errors = validate_baseline_explanation(explanation)
        self.assertTrue(any("availability_tier" in e for e in errors))


class ValidateTemplateGuidanceTests(unittest.TestCase):
    def test_valid_guidance_has_no_errors(self) -> None:
        guidance = {"category_code": "apple_computer"}
        errors = validate_template_guidance(guidance)
        self.assertEqual(errors, [])

    def test_invalid_completeness_status(self) -> None:
        guidance = {
            "category_code": "apple_computer",
            "completeness_status": "invalid",
        }
        errors = validate_template_guidance(guidance)
        self.assertTrue(any("completeness_status" in e for e in errors))


class ValidateAlertEventTests(unittest.TestCase):
    def test_valid_alert_has_no_errors(self) -> None:
        alert = {
            "id": "alert-1",
            "opportunity_id": "opp-1",
            "watch_target_id": "target-1",
            "alert_channel": "dashboard",
            "alert_reason": "test",
            "status": "PENDING",
        }
        errors = validate_alert_event(alert)
        self.assertEqual(errors, [])

    def test_invalid_alert_status(self) -> None:
        alert = {
            "id": "alert-1",
            "opportunity_id": "opp-1",
            "watch_target_id": "target-1",
            "alert_channel": "dashboard",
            "alert_reason": "test",
            "status": "INVALID",
        }
        errors = validate_alert_event(alert)
        self.assertTrue(any("status" in e for e in errors))


class BuildContractFieldLinesTests(unittest.TestCase):
    def test_produces_lines_for_all_contracts(self) -> None:
        lines = build_contract_field_lines()
        self.assertTrue(any("Pricing Record Fields" in line for line in lines))
        self.assertTrue(any("Baseline Explanation Fields" in line for line in lines))
        self.assertTrue(any("Template Guidance Fields" in line for line in lines))
        self.assertTrue(any("Alert Event Fields" in line for line in lines))

    def test_required_fields_marked_with_asterisk(self) -> None:
        lines = build_contract_field_lines()
        required_lines = [line for line in lines if line.strip().startswith("*")]
        self.assertTrue(len(required_lines) > 0)


class ContractConstantsTests(unittest.TestCase):
    def test_availability_tiers_are_complete(self) -> None:
        self.assertEqual(AVAILABILITY_TIERS, {"guidance_ready", "reference_only", "incomplete", "blocked"})

    def test_quality_tiers_are_complete(self) -> None:
        self.assertEqual(QUALITY_TIERS, {"A", "B", "C", "D"})

    def test_opportunity_statuses_are_complete(self) -> None:
        self.assertEqual(OPPORTUNITY_STATUSES, {"OPEN", "REFERENCE_ONLY", "STALE", "CLOSED"})

    def test_alert_statuses_are_complete(self) -> None:
        self.assertEqual(ALERT_STATUSES, {"PENDING", "SENT", "FAILED", "CANCELLED"})

    def test_completeness_statuses_are_complete(self) -> None:
        self.assertEqual(COMPLETENESS_STATUSES, {"complete", "partial", "missing", "legacy"})

    def test_pricing_block_reasons_are_complete(self) -> None:
        self.assertIn("template_incomplete", PRICING_BLOCK_REASONS)
        self.assertIn("insufficient_seller_samples", PRICING_BLOCK_REASONS)
        self.assertIn("stale_pricing_evidence", PRICING_BLOCK_REASONS)

    def test_pricing_record_fields_has_required_entries(self) -> None:
        self.assertIn("item_id_ref", PRICING_RECORD_FIELDS)
        self.assertIn("price", PRICING_RECORD_FIELDS)
        self.assertIn("brand", PRICING_RECORD_FIELDS)
        self.assertIn("product_label", PRICING_RECORD_FIELDS)
        self.assertTrue(PRICING_RECORD_FIELDS["item_id_ref"]["required"])
        self.assertTrue(PRICING_RECORD_FIELDS["price"]["required"])

    def test_baseline_explanation_fields_has_required_entries(self) -> None:
        self.assertIn("readiness_summary", BASELINE_EXPLANATION_FIELDS)
        self.assertIn("confidence_summary", BASELINE_EXPLANATION_FIELDS)
        self.assertTrue(BASELINE_EXPLANATION_FIELDS["readiness_summary"]["required"])

    def test_template_guidance_fields_has_required_entries(self) -> None:
        self.assertIn("category_code", TEMPLATE_GUIDANCE_FIELDS)
        self.assertTrue(TEMPLATE_GUIDANCE_FIELDS["category_code"]["required"])

    def test_alert_event_fields_has_required_entries(self) -> None:
        self.assertIn("id", ALERT_EVENT_FIELDS)
        self.assertIn("opportunity_id", ALERT_EVENT_FIELDS)
        self.assertTrue(ALERT_EVENT_FIELDS["id"]["required"])


if __name__ == "__main__":
    unittest.main()
