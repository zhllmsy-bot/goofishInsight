from __future__ import annotations

import unittest
from decimal import Decimal

from goofish_insight.application.services.category_resolution import ResolvedItemCategoryContext
from goofish_insight.application.services.feed_category_resolution import FeedCategorySelection
from goofish_insight.application.services.feed_workflow_runtime import (
    build_category_context_from_item,
    build_home_feed_decision_payload,
    persist_home_feed_item_decision,
)
from goofish_insight.models import Item


class _CaptureSession:
    def __init__(self) -> None:
        self.executed = []

    def execute(self, stmt):
        self.executed.append(stmt)
        return None


class FeedWorkflowRuntimeTests(unittest.TestCase):
    def test_build_home_feed_decision_payload_merges_selection_and_extra_payload(self) -> None:
        selection = FeedCategorySelection(
            is_target_pool=True,
            candidate_business_domains=("apple_computer", "apple_airpods"),
            active_candidate_business_domains=("apple_computer", "apple_airpods"),
            resolved_business_domain="apple_computer",
            category_context=ResolvedItemCategoryContext(
                target_category_id="cat-apple",
                resolved_category_id="cat-apple",
                resolved_template_id="tpl-apple",
                category_validation_status="FEED_TARGET_POOL_LLM",
                category_validation_reason="feed_target_pool_llm:apple_computer",
                category_validation_confidence=Decimal("0.9200"),
                resolved_business_domain="apple_computer",
            ),
            decision_source="raw_category_llm",
            decision_reason="标题包含 MacBook Pro / M3",
            decision_payload={"targetPoolGate": {"matchKey": "CAT:500"}},
        )

        payload = build_home_feed_decision_payload(
            category_selection=selection,
            extra_payload={"detailEligible": True},
        )

        self.assertEqual(payload["categorySelection"]["targetPoolGate"]["matchKey"], "CAT:500")
        self.assertTrue(payload["detailEligible"])

    def test_build_category_context_from_item_uses_item_resolution_fields(self) -> None:
        item = Item(
            id=1,
            item_id="abc",
            task_id=1,
            business_domain="apple_airpods",
            target_category_id="cat-airpods",
            resolved_category_id="cat-airpods",
            resolved_template_id="tpl-airpods",
            category_validation_status="FEED_TARGET_POOL_SINGLE_CANDIDATE",
            category_validation_reason="feed_target_pool_single_candidate:apple_airpods",
            category_validation_confidence=Decimal("1.0000"),
            title="AirPods Pro 2",
            is_active=True,
        )

        context = build_category_context_from_item(item)

        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.resolved_business_domain, "apple_airpods")
        self.assertEqual(context.resolved_template_id, "tpl-airpods")
        self.assertEqual(context.category_validation_confidence, Decimal("1.0000"))

    def test_persist_home_feed_item_decision_executes_upsert_statement(self) -> None:
        session = _CaptureSession()
        selection = FeedCategorySelection(
            is_target_pool=True,
            candidate_business_domains=("apple_computer",),
            active_candidate_business_domains=("apple_computer",),
            resolved_business_domain="apple_computer",
            category_context=ResolvedItemCategoryContext(
                target_category_id="cat-apple",
                resolved_category_id="cat-apple",
                resolved_template_id="tpl-apple",
                category_validation_status="FEED_TARGET_POOL_SINGLE_CANDIDATE",
                category_validation_reason="feed_target_pool_single_candidate:apple_computer",
                category_validation_confidence=Decimal("1.0000"),
                resolved_business_domain="apple_computer",
            ),
            decision_source="raw_category_single_candidate",
            decision_reason="single_candidate:apple_computer",
            decision_payload={"targetPoolGate": {"matchKey": "CAT:500", "matchScope": "CAT"}},
        )

        persist_home_feed_item_decision(
            session=session,
            item_id="item-123",
            source_platform="xianyu",
            decision_stage="category_gate",
            decision_status="resolved_ready_for_enrichment",
            category_selection=selection,
        )

        self.assertEqual(len(session.executed), 1)


if __name__ == "__main__":
    unittest.main()
