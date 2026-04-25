from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from goofish_insight.application.services.review_v3_mapping import V3_STATUS_REJECTED_STATIC_GUARD
from goofish_insight.application.services.review_v3_pipeline import (
    apply_review_v3_business_domain_override,
    build_review_v3_compat_payload,
    coerce_first_pass_features,
    coerce_second_pass_payload,
    evaluate_static_guard,
    extract_json_items,
    extract_json_object,
    resolve_review_v3_target_context,
)


class ReviewV3PipelineTests(unittest.TestCase):
    def test_build_review_v3_compat_payload_maps_valid_result_to_existing_item_fields(self) -> None:
        item_row = SimpleNamespace(item_id="123", business_domain="apple_computer")
        compat = build_review_v3_compat_payload(
            item_row=item_row,
            business_domain="phone",
            payload={
                "pipeline_version": "v3",
                "resolution_status": "VALID_READY_FOR_PRICING",
                "stage_status": "first_pass_complete",
                "model_catalog_id": "model-1",
                "first_pass_confidence": Decimal("0.9000"),
                "extracted_features": {"model_hint": "iPhone 16"},
            },
        )

        self.assertTrue(compat["llm_reviewed"])
        self.assertEqual(compat["llm_review_status"], "valid")
        self.assertEqual(compat["llm_review_confidence"], Decimal("0.9500"))
        self.assertFalse(compat["llm_review_needs_audit"])
        self.assertEqual(compat["llm_review_input"]["business_domain"], "phone")
        self.assertEqual(compat["llm_review_decision"]["engine"], "review_v3")

    def test_build_review_v3_compat_payload_maps_manual_result_to_pending_audit(self) -> None:
        item_row = SimpleNamespace(item_id="123", business_domain="camera_body")
        compat = build_review_v3_compat_payload(
            item_row=item_row,
            business_domain="camera_body",
            payload={
                "pipeline_version": "v3",
                "resolution_status": "MANUAL_AUDIT_REQUIRED",
                "stage_status": "second_pass_complete",
                "reject_reason": "feature_conflict",
                "first_pass_confidence": Decimal("0.9000"),
            },
        )

        self.assertTrue(compat["llm_reviewed"])
        self.assertEqual(compat["llm_review_status"], "pending_audit")
        self.assertTrue(compat["llm_review_needs_audit"])
        self.assertIsNone(compat["llm_review_confidence"])
        self.assertEqual(compat["llm_review_audit_reason"], "feature_conflict")

    def test_resolve_review_v3_target_context_prefers_profile_category_and_active_template(self) -> None:
        category = SimpleNamespace(id="phone-category")

        class _Result:
            def __init__(self, value):
                self._value = value

            def scalar_one_or_none(self):
                return self._value

        session = Mock()
        session.execute.side_effect = [_Result(category), _Result("phone-template")]
        item_row = SimpleNamespace(
            resolved_category_id="legacy-apple-category",
            resolved_template_id="legacy-apple-template",
            business_domain="apple_computer",
        )

        category_id, template_id = resolve_review_v3_target_context(
            session,
            item_row=item_row,
            business_domain="phone",
        )

        self.assertEqual(category_id, "phone-category")
        self.assertEqual(template_id, "phone-template")
        session.get.assert_not_called()

    def test_static_guard_rejects_overlong_title(self) -> None:
        result = evaluate_static_guard({"title": "a" * 501})
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], V3_STATUS_REJECTED_STATIC_GUARD)

    def test_static_guard_allows_normal_sell_post_with_optional_exchange(self) -> None:
        result = evaluate_static_guard(
            {
                "title": "出苹果MacBook Pro 14寸 M5 16G 512G，上海面交可优惠，有mac mini的也可以找我置换~"
            }
        )
        self.assertIsNone(result)

    def test_static_guard_rejects_explicit_recovery_exchange_shop_post(self) -> None:
        result = evaluate_static_guard(
            {
                "title": "苹果 iPad Air 6 128G，常年回收本店所有机型，支持回收置换，以旧换新"
            }
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], V3_STATUS_REJECTED_STATIC_GUARD)

    def test_extract_json_object_strips_markdown_fence(self) -> None:
        payload = extract_json_object("```json\n{\"brand\": \"尼康\"}\n```")
        self.assertEqual(payload["brand"], "尼康")

    def test_extract_json_items_reads_items_array(self) -> None:
        payload = extract_json_items(
            "```json\n{\"items\":[{\"item_id\":\"1\",\"brand\":\"Sony\"},{\"item_id\":\"2\",\"brand\":\"Canon\"}]}\n```"
        )
        self.assertEqual([entry["item_id"] for entry in payload], ["1", "2"])

    def test_coerce_first_pass_features_normalizes_numeric_fields(self) -> None:
        payload = coerce_first_pass_features(
            {
                "is_main_product": 1,
                "is_flawless": "true",
                "confidence_score": "0.88",
                "memory_gb": "18",
                "storage_gb": "512",
                "case_size_mm": "47",
            }
        )
        self.assertTrue(payload["is_main_product"])
        self.assertTrue(payload["is_flawless"])
        self.assertEqual(payload["memory_gb"], 18)
        self.assertEqual(payload["storage_gb"], 512)
        self.assertEqual(payload["case_size_mm"], 47)
        self.assertAlmostEqual(payload["confidence_score"], 0.88)

    def test_coerce_second_pass_payload_promotes_resolved_model_code(self) -> None:
        payload = coerce_second_pass_payload(
            {
                "is_resolved": False,
                "needs_human": False,
                "resolved_model_code": "nikon_z_70_200_f28_vr_s",
            }
        )
        self.assertTrue(payload["is_resolved"])
        self.assertEqual(payload["resolved_model_code"], "nikon_z_70_200_f28_vr_s")

    def test_apply_business_domain_override_keeps_source_domain(self) -> None:
        rows = apply_review_v3_business_domain_override(
            rows_by_id={
                "1": {"item_id": "1", "business_domain": "apple_computer"},
                "2": {"item_id": "2", "business_domain": "apple_computer"},
            },
            item_ids=["1", "2"],
            business_domain="phone",
        )
        self.assertEqual(rows[0]["business_domain"], "phone")
        self.assertEqual(rows[0]["source_business_domain"], "apple_computer")
        self.assertEqual(rows[1]["business_domain"], "phone")

    def test_apply_business_domain_override_leaves_rows_unchanged_when_missing_override(self) -> None:
        rows = apply_review_v3_business_domain_override(
            rows_by_id={"1": {"item_id": "1", "business_domain": "apple_computer"}},
            item_ids=["1"],
            business_domain=None,
        )
        self.assertEqual(rows[0]["business_domain"], "apple_computer")
        self.assertNotIn("source_business_domain", rows[0])


if __name__ == "__main__":
    unittest.main()
