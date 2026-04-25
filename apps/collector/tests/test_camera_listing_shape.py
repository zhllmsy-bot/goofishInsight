from __future__ import annotations

import unittest

from goofish_insight.application.services.camera_listing_shape import (
    audit_camera_listing_shapes,
    evaluate_camera_listing_shape,
    repair_camera_listing_shapes,
)
from goofish_insight.models import Item


class _FakeScalarResult:
    def __init__(self, rows=None) -> None:
        self._rows = list(rows or [])

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self


class _FakeDeleteResult:
    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount


class _FakeSession:
    def __init__(self, items, category_rows=None, runtime_rows=None, delete_rowcount: int = 0) -> None:
        self._items = list(items)
        self._category_rows = list(category_rows or [])
        self._runtime_rows = list(runtime_rows or [])
        self._delete_rowcount = delete_rowcount
        self.delete_calls = 0

    def execute(self, stmt):
        text = str(stmt)
        if "FROM items" in text:
            return _FakeScalarResult(rows=self._items)
        if "category_runtime_profile" in text:
            return _FakeScalarResult(rows=self._runtime_rows)
        if "FROM category" in text and "category_runtime_profile" not in text:
            return _FakeScalarResult(rows=self._category_rows)
        if "DELETE FROM item_ingest_rejection" in text:
            self.delete_calls += 1
            return _FakeDeleteResult(rowcount=self._delete_rowcount)
        raise AssertionError(f"Unexpected statement: {text}")


class CameraListingShapeTests(unittest.TestCase):
    def test_evaluate_body_bundle_for_body_first_kit_listing(self) -> None:
        decision = evaluate_camera_listing_shape(
            current_category_code="camera_interchangeable_lens",
            title="富士 X-T20 微单，带原装18-55镜头 99新",
        )

        self.assertEqual(decision.shape, "body_bundle")
        self.assertEqual(decision.recommended_action, "redirect")
        self.assertEqual(decision.target_category_code, "camera_body")

    def test_evaluate_body_only_when_title_says_no_lens_only_body(self) -> None:
        decision = evaluate_camera_listing_shape(
            current_category_code="camera_body",
            title="索尼 A7M3 没有镜头和转接环，只有机身",
        )

        self.assertEqual(decision.shape, "body_only")
        self.assertEqual(decision.recommended_action, "keep")
        self.assertEqual(decision.target_category_code, "camera_body")

    def test_evaluate_lens_only_for_explicit_lens_listing(self) -> None:
        decision = evaluate_camera_listing_shape(
            current_category_code="camera_body",
            title="富士 XF23mm F2 镜头 成色很好",
        )

        self.assertEqual(decision.shape, "lens_only")
        self.assertEqual(decision.recommended_action, "redirect")
        self.assertEqual(decision.target_category_code, "camera_interchangeable_lens")

    def test_evaluate_lens_only_for_z_mount_compact_lens_signature(self) -> None:
        decision = evaluate_camera_listing_shape(
            current_category_code="camera_interchangeable_lens",
            title="出尼康z35 1.8S，二手购入，无箱说，镜头功能正常",
        )

        self.assertEqual(decision.shape, "lens_only")
        self.assertEqual(decision.recommended_action, "keep")

    def test_evaluate_lens_only_for_compatibility_body_mentions(self) -> None:
        decision = evaluate_camera_listing_shape(
            current_category_code="camera_interchangeable_lens",
            title="唯卓仕20mm F1.8 Z卡口镜头，尼康Z口，适合Z6/Z7微单",
        )

        self.assertEqual(decision.shape, "lens_only")
        self.assertEqual(decision.recommended_action, "keep")

    def test_evaluate_lens_only_for_lens_slang_signature(self) -> None:
        decision = evaluate_camera_listing_shape(
            current_category_code="camera_interchangeable_lens",
            title="出自用索尼G大师50 1.4 无拆无修无磕碰",
        )

        self.assertEqual(decision.shape, "lens_only")
        self.assertEqual(decision.recommended_action, "keep")

    def test_evaluate_rental_listing_blocks(self) -> None:
        decision = evaluate_camera_listing_shape(
            current_category_code="camera_body",
            title="免押出租佳能R5+RF100-500 演唱会拍摄",
        )

        self.assertEqual(decision.shape, "rental_or_service")
        self.assertEqual(decision.recommended_action, "block")

    def test_evaluate_commercial_menu_blocks(self) -> None:
        decision = evaluate_camera_listing_shape(
            current_category_code="camera_interchangeable_lens",
            title="全新尼康Z6III微单机身 单机10999 搭配24-70 15999 搭配50 17999 现货",
        )

        self.assertEqual(decision.shape, "commercial_menu")
        self.assertEqual(decision.recommended_action, "block")

    def test_audit_camera_listing_shapes_summarizes_actions(self) -> None:
        session = _FakeSession(
            items=[
                Item(
                    id=1,
                    item_id="item-1",
                    task_id=1,
                    business_domain="camera_interchangeable_lens",
                    title="富士 X-T20 微单，带原装18-55镜头 99新",
                    is_active=True,
                ),
                Item(
                    id=2,
                    item_id="item-2",
                    task_id=1,
                    business_domain="camera_body",
                    title="富士 XF23mm F2 镜头 成色很好",
                    is_active=True,
                ),
                Item(
                    id=3,
                    item_id="item-3",
                    task_id=1,
                    business_domain="camera_body",
                    title="免押出租佳能R5+RF100-500 演唱会拍摄",
                    is_active=True,
                ),
            ]
        )

        summary = audit_camera_listing_shapes(session, active_only=True, sample_limit=5)

        self.assertEqual(summary["scanned"], 3)
        self.assertEqual(summary["action_counts"]["redirect"], 2)
        self.assertEqual(summary["action_counts"]["block"], 1)
        self.assertEqual(len(summary["samples"]["redirect"]), 2)
        self.assertEqual(len(summary["samples"]["block"]), 1)

    def test_repair_camera_listing_shapes_redirects_and_blocks(self) -> None:
        body_bundle_item = Item(
            id=11,
            item_id="item-11",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            title="出一台佳能RP，带原厂RF 24-105镜头",
            is_active=True,
            category_validation_status="MATCH_TASK_CATEGORY",
            category_validation_reason="task_bound_category",
            resolved_category_id="cat-lens",
            resolved_template_id="tpl-lens",
        )
        rental_item = Item(
            id=12,
            item_id="item-12",
            task_id=1,
            business_domain="camera_body",
            title="出租索尼A7M4 免押租机",
            is_active=True,
            category_validation_status="MATCH_TASK_CATEGORY",
            category_validation_reason="task_bound_category",
            resolved_category_id="cat-body",
            resolved_template_id="tpl-body",
        )
        session = _FakeSession(
            items=[body_bundle_item, rental_item],
            category_rows=[("cat-body", "camera_body"), ("cat-lens", "camera_interchangeable_lens")],
            runtime_rows=[("camera_body", "tpl-body"), ("camera_interchangeable_lens", "tpl-lens")],
            delete_rowcount=2,
        )

        summary = repair_camera_listing_shapes(session, dry_run=False, min_confidence=0.9)

        self.assertEqual(summary["redirected_count"], 1)
        self.assertEqual(summary["blocked_count"], 1)
        self.assertEqual(summary["cleared_rejection_count"], 2)
        self.assertEqual(body_bundle_item.business_domain, "camera_body")
        self.assertEqual(body_bundle_item.category_validation_status, "OVERRIDE_CATEGORY")
        self.assertEqual(
            body_bundle_item.category_validation_reason,
            "camera_shape_redirect:camera_interchangeable_lens_to_camera_body:body_bundle",
        )
        self.assertFalse(rental_item.is_active)
        self.assertEqual(rental_item.category_validation_status, "BLOCKED")
        self.assertEqual(rental_item.category_validation_reason, "camera_shape_blocked:rental_or_service")


if __name__ == "__main__":
    unittest.main()
