from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from goofish_insight.application.services.category_resolution import (
    backfill_item_category_resolution_with_session,
    resolve_item_category_context_with_session,
)
from goofish_insight.models import CrawlTask, Item


class _FakeScalarResult:
    def __init__(self, value=None, rows=None) -> None:
        self.value = value
        self.rows = list(rows or [])

    def scalar_one_or_none(self):
        return self.value

    def all(self):
        return list(self.rows)


class _FakeSession:
    def __init__(self, execute_values=None, get_map=None) -> None:
        self.execute_values = list(execute_values or [])
        self.get_map = get_map or {}

    def execute(self, stmt):
        value = self.execute_values.pop(0) if self.execute_values else None
        if isinstance(value, _FakeScalarResult):
            return value
        return _FakeScalarResult(value=value)

    def get(self, model, key):
        return self.get_map.get((getattr(model, "__name__", ""), key))


class CategoryResolutionServiceTests(unittest.TestCase):
    def test_resolve_item_category_context_defaults_to_task_category(self) -> None:
        session = _FakeSession(
            execute_values=[SimpleNamespace(active_template_id="tpl-apple-v1", status="ACTIVE")],
        )
        task = CrawlTask(
            id=1,
            task_key="apple-core",
            category_id="cat-apple",
            business_domain="apple_m_series",
            display_name="Apple Core",
            keywords=[],
            brand_lexicon=[],
            model_lexicon=[],
            config_lexicon=[],
            paging_limit=5,
        )

        with patch(
            "goofish_insight.application.services.category_resolution.resolve_xianyu_category_mapping_with_session",
            return_value=None,
        ):
            context = resolve_item_category_context_with_session(
                session,
                task=task,
                xianyu_c_cat_id="126864783",
            )

        self.assertEqual(context.target_category_id, "cat-apple")
        self.assertEqual(context.resolved_template_id, "tpl-apple-v1")
        self.assertEqual(context.category_validation_status, "MATCH_TASK_CATEGORY")

    def test_resolve_item_category_context_blocks_apple_watch_title_under_apple_computer(self) -> None:
        session = _FakeSession()
        task = CrawlTask(
            id=1,
            task_key="apple-core",
            category_id="cat-apple",
            business_domain="apple_computer",
            display_name="Apple Core",
            keywords=[],
            brand_lexicon=[],
            model_lexicon=[],
            config_lexicon=[],
            paging_limit=5,
        )

        context = resolve_item_category_context_with_session(
            session,
            task=task,
            title="Apple Watch Ultra 2 49mm",
        )

        self.assertEqual(context.target_category_id, "cat-apple")
        self.assertIsNone(context.resolved_category_id)
        self.assertEqual(context.category_validation_status, "BLOCKED")
        self.assertEqual(context.category_validation_reason, "title_scope_blocked:apple_watch_like")
        self.assertEqual(context.resolved_business_domain, "apple_computer")

    def test_resolve_item_category_context_reroutes_camera_body_to_lens(self) -> None:
        session = _FakeSession(
            execute_values=[
                SimpleNamespace(id="cat-lens"),
                SimpleNamespace(active_template_id="tpl-lens-v1", status="ACTIVE"),
            ],
        )
        task = CrawlTask(
            id=1,
            task_key="camera-body-catalog-auto",
            category_id="cat-body",
            business_domain="camera_body",
            display_name="Camera Body",
            keywords=[],
            brand_lexicon=[],
            model_lexicon=[],
            config_lexicon=[],
            paging_limit=5,
        )

        context = resolve_item_category_context_with_session(
            session,
            task=task,
            title="尼康 Z 24-70mm f/2.8 S 镜头 国行",
        )

        self.assertEqual(context.target_category_id, "cat-body")
        self.assertEqual(context.resolved_category_id, "cat-lens")
        self.assertEqual(context.resolved_template_id, "tpl-lens-v1")
        self.assertEqual(context.category_validation_status, "OVERRIDE_CATEGORY")
        self.assertEqual(
            context.category_validation_reason,
            "title_scope_override:camera_body_to_camera_interchangeable_lens",
        )
        self.assertEqual(context.resolved_business_domain, "camera_interchangeable_lens")

    def test_resolve_item_category_context_blocks_ambiguous_camera_body_mismatch(self) -> None:
        session = _FakeSession()
        task = CrawlTask(
            id=1,
            task_key="camera-body-catalog-auto",
            category_id="cat-body",
            business_domain="camera_body",
            display_name="Camera Body",
            keywords=[],
            brand_lexicon=[],
            model_lexicon=[],
            config_lexicon=[],
            paging_limit=5,
        )

        context = resolve_item_category_context_with_session(
            session,
            task=task,
            title="黑卡5 便携相机 非全画幅机身任务",
        )

        self.assertEqual(context.target_category_id, "cat-body")
        self.assertIsNone(context.resolved_category_id)
        self.assertEqual(context.category_validation_status, "BLOCKED")
        self.assertEqual(context.category_validation_reason, "title_scope_blocked:camera_body_mismatch")
        self.assertEqual(context.resolved_business_domain, "camera_body")

    def test_resolve_item_category_context_honors_force_template_policy(self) -> None:
        session = _FakeSession(
            execute_values=[SimpleNamespace(active_template_id="tpl-task-default", status="ACTIVE")],
        )
        task = CrawlTask(
            id=1,
            task_key="lens-core",
            category_id="cat-lens",
            business_domain="camera_interchangeable_lens",
            display_name="Lens Core",
            keywords=[],
            brand_lexicon=[],
            model_lexicon=[],
            config_lexicon=[],
            paging_limit=5,
        )
        mapping = SimpleNamespace(
            id="map-1",
            match_key="C_CAT:126864783",
            policy_mode="FORCE_TEMPLATE",
            template_override_id="tpl-override",
            template_id="tpl-fallback",
            category_id="cat-lens",
        )

        with patch(
            "goofish_insight.application.services.category_resolution.resolve_xianyu_category_mapping_with_session",
            return_value=mapping,
        ):
            context = resolve_item_category_context_with_session(
                session,
                task=task,
                xianyu_c_cat_id="126864783",
            )

        self.assertEqual(context.resolved_template_id, "tpl-override")
        self.assertEqual(context.category_validation_status, "OVERRIDE_TEMPLATE")
        self.assertEqual(context.category_validation_confidence, Decimal("0.9800"))

    def test_backfill_item_category_resolution_updates_missing_fields(self) -> None:
        item = Item(
            id=101,
            item_id="item-101",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            title="Nikon Z 50 1.2 S",
            is_active=True,
        )
        task = CrawlTask(
            id=1,
            task_key="lens-core",
            category_id="cat-lens",
            business_domain="camera_interchangeable_lens",
            display_name="Lens Core",
            keywords=[],
            brand_lexicon=[],
            model_lexicon=[],
            config_lexicon=[],
            paging_limit=5,
        )
        session = _FakeSession(
            execute_values=[
                _FakeScalarResult(rows=[(item, task)]),
                SimpleNamespace(active_template_id="tpl-lens-v1", status="ACTIVE"),
            ],
        )

        with patch(
            "goofish_insight.application.services.category_resolution.resolve_xianyu_category_mapping_with_session",
            return_value=None,
        ):
            summary = backfill_item_category_resolution_with_session(
                session,
                task_key="lens-core",
                dry_run=False,
            )

        self.assertEqual(summary["processed"], 1)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(item.target_category_id, "cat-lens")
        self.assertEqual(item.resolved_category_id, "cat-lens")
        self.assertEqual(item.resolved_template_id, "tpl-lens-v1")
        self.assertEqual(item.category_validation_status, "MATCH_TASK_CATEGORY")
        self.assertEqual(item.business_domain, "camera_interchangeable_lens")


if __name__ == "__main__":
    unittest.main()
