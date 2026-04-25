from __future__ import annotations

import unittest
from types import SimpleNamespace

from goofish_insight.application.services.category_domain_reconcile import (
    reconcile_item_category_domain_state,
)
from goofish_insight.models import Category, CategoryRuntimeProfile, Item


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
    def __init__(self, items, category_rows, runtime_rows, delete_rowcount: int = 0) -> None:
        self._items = list(items)
        self._category_rows = list(category_rows)
        self._runtime_rows = list(runtime_rows)
        self.delete_rowcount = delete_rowcount
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
            return _FakeDeleteResult(rowcount=self.delete_rowcount)
        raise AssertionError(f"Unexpected statement: {text}")


class CategoryDomainReconcileTests(unittest.TestCase):
    def test_reconcile_restores_blocked_camera_body_item(self) -> None:
        item = Item(
            id=101,
            item_id="item-101",
            task_id=1,
            business_domain="camera_body",
            title="索尼 A7R4A 单机身 快门低",
            is_active=False,
            category_validation_status="BLOCKED",
            category_validation_reason="title_scope_blocked:domain_mismatch",
            resolved_category_id=None,
            resolved_template_id=None,
        )
        session = _FakeSession(
            items=[item],
            category_rows=[("cat-body", "camera_body"), ("cat-lens", "camera_interchangeable_lens")],
            runtime_rows=[("camera_body", "tpl-body"), ("camera_interchangeable_lens", "tpl-lens")],
            delete_rowcount=1,
        )

        summary = reconcile_item_category_domain_state(
            session,
            category_code="camera_body",
            dry_run=False,
        )

        self.assertEqual(summary["restored_count"], 1)
        self.assertEqual(summary["redirected_count"], 0)
        self.assertEqual(summary["blocked_count"], 0)
        self.assertEqual(summary["cleared_rejection_count"], 1)
        self.assertTrue(item.is_active)
        self.assertEqual(item.business_domain, "camera_body")
        self.assertEqual(item.resolved_category_id, "cat-body")
        self.assertEqual(item.resolved_template_id, "tpl-body")
        self.assertEqual(item.category_validation_status, "MATCH_TASK_CATEGORY")
        self.assertEqual(item.category_validation_reason, "title_scope_reconciled:match_task_category")

    def test_reconcile_redirects_legacy_camera_body_override_back_to_body(self) -> None:
        item = Item(
            id=102,
            item_id="item-102",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            title="富士 X-T5 机身 99新",
            is_active=True,
            category_validation_status="OVERRIDE_CATEGORY",
            category_validation_reason="title_scope_override:camera_body_to_lens",
            resolved_category_id="cat-lens",
            resolved_template_id="tpl-lens",
        )
        session = _FakeSession(
            items=[item],
            category_rows=[("cat-body", "camera_body"), ("cat-lens", "camera_interchangeable_lens")],
            runtime_rows=[("camera_body", "tpl-body"), ("camera_interchangeable_lens", "tpl-lens")],
            delete_rowcount=1,
        )

        summary = reconcile_item_category_domain_state(
            session,
            category_code="camera_body",
            dry_run=False,
        )

        self.assertEqual(summary["restored_count"], 1)
        self.assertEqual(item.business_domain, "camera_body")
        self.assertEqual(item.resolved_category_id, "cat-body")
        self.assertEqual(item.resolved_template_id, "tpl-body")

    def test_reconcile_blocks_non_matching_camera_body_item(self) -> None:
        item = Item(
            id=103,
            item_id="item-103",
            task_id=1,
            business_domain="camera_body",
            title="黑卡5 便携相机",
            is_active=True,
            category_validation_status="MATCH_TASK_CATEGORY",
            category_validation_reason="task_bound_category",
            resolved_category_id="cat-body",
            resolved_template_id="tpl-body",
        )
        session = _FakeSession(
            items=[item],
            category_rows=[("cat-body", "camera_body"), ("cat-lens", "camera_interchangeable_lens")],
            runtime_rows=[("camera_body", "tpl-body"), ("camera_interchangeable_lens", "tpl-lens")],
        )

        summary = reconcile_item_category_domain_state(
            session,
            category_code="camera_body",
            dry_run=False,
        )

        self.assertEqual(summary["blocked_count"], 1)
        self.assertFalse(item.is_active)
        self.assertEqual(item.category_validation_status, "BLOCKED")
        self.assertEqual(item.category_validation_reason, "title_scope_blocked:domain_mismatch")

    def test_reconcile_keeps_rental_camera_body_listing_blocked(self) -> None:
        item = Item(
            id=104,
            item_id="item-104",
            task_id=1,
            business_domain="camera_body",
            title="免押出租佳能R5+RF100-500 演唱会专用",
            source_keyword="佳能r5",
            current_price=120,
            is_active=False,
            category_validation_status="BLOCKED",
            category_validation_reason="title_scope_blocked:hard_block:出租",
            resolved_category_id=None,
            resolved_template_id=None,
        )
        session = _FakeSession(
            items=[item],
            category_rows=[("cat-body", "camera_body"), ("cat-lens", "camera_interchangeable_lens")],
            runtime_rows=[("camera_body", "tpl-body"), ("camera_interchangeable_lens", "tpl-lens")],
        )

        summary = reconcile_item_category_domain_state(
            session,
            category_code="camera_body",
            dry_run=False,
        )

        self.assertEqual(summary["blocked_count"], 0)
        self.assertEqual(summary["unchanged_count"], 1)
        self.assertFalse(item.is_active)
        self.assertEqual(item.category_validation_reason, "title_scope_blocked:hard_block:出租")

    def test_reconcile_does_not_block_matching_lens_on_signature_soft_gate(self) -> None:
        item = Item(
            id=105,
            item_id="item-105",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            title="富士xf23f2镜头 有个副厂后盖和uv 略微掉漆",
            source_keyword="富士 xf23",
            current_price=2200,
            is_active=False,
            category_validation_status="BLOCKED",
            category_validation_reason="title_scope_blocked:domain_mismatch",
            resolved_category_id=None,
            resolved_template_id=None,
        )
        session = _FakeSession(
            items=[item],
            category_rows=[("cat-body", "camera_body"), ("cat-lens", "camera_interchangeable_lens")],
            runtime_rows=[("camera_body", "tpl-body"), ("camera_interchangeable_lens", "tpl-lens")],
            delete_rowcount=1,
        )

        summary = reconcile_item_category_domain_state(
            session,
            category_code="camera_interchangeable_lens",
            dry_run=False,
        )

        self.assertEqual(summary["restored_count"], 1)
        self.assertEqual(summary["blocked_count"], 0)
        self.assertTrue(item.is_active)
        self.assertEqual(item.business_domain, "camera_interchangeable_lens")
        self.assertEqual(item.resolved_template_id, "tpl-lens")


if __name__ == "__main__":
    unittest.main()
