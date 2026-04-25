from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from goofish_insight.application.services.category_resolution import ResolvedItemCategoryContext
from goofish_insight.application.services.feed_category_resolution import (
    FeedTargetPoolGate,
    resolve_feed_target_pool_gate_with_session,
    resolve_feed_category_selection_with_session,
)
from goofish_insight.models import CrawlTask


class _FakeExecResult:
    def __init__(self, rows=None) -> None:
        self.rows = list(rows or [])

    def scalars(self):
        return list(self.rows)

    def all(self):
        return list(self.rows)


class _FakeSession:
    def __init__(self, execute_results=None) -> None:
        self.execute_results = list(execute_results or [])

    def execute(self, stmt):
        del stmt
        if not self.execute_results:
            raise AssertionError("Unexpected session.execute call.")
        return self.execute_results.pop(0)


class FeedCategoryResolutionServiceTests(unittest.TestCase):
    def make_task(self, domain: str, *, category_id: str) -> CrawlTask:
        return CrawlTask(
            id=1,
            task_key=f"{domain}-task",
            source_platform="xianyu",
            category_id=category_id,
            business_domain=domain,
            display_name=domain,
            keywords=[],
            brand_lexicon=[],
            model_lexicon=[],
            config_lexicon=[],
            paging_limit=5,
        )

    def test_non_target_raw_category_does_not_call_llm(self) -> None:
        gate = FeedTargetPoolGate(
            is_target_pool=False,
            match_key=None,
            match_scope=None,
            candidate_business_domains=(),
            active_candidate_business_domains=(),
            decision_reason="raw_category_not_in_target_pool",
            blocked_by_policy=False,
            signal_counts={},
            signal_sources={},
        )

        with (
            patch(
                "goofish_insight.application.services.feed_category_resolution.resolve_feed_target_pool_gate_with_session",
                return_value=gate,
            ),
            patch(
                "goofish_insight.application.services.feed_category_resolution._classify_feed_business_domain_with_llm"
            ) as classify_mock,
        ):
            selection = resolve_feed_category_selection_with_session(
                SimpleNamespace(),
                title="普通杂物",
                raw_text="普通杂物",
                price=Decimal("100"),
                xianyu_cat_id="1",
                xianyu_tb_cat_id="2",
                xianyu_c_cat_id="3",
                tasks_by_domain={
                    "apple_computer": self.make_task("apple_computer", category_id="cat-apple"),
                },
            )

        self.assertFalse(selection.is_target_pool)
        self.assertIsNone(selection.resolved_business_domain)
        self.assertEqual(selection.decision_source, "raw_category_non_target")
        classify_mock.assert_not_called()

    def test_single_candidate_resolves_without_llm(self) -> None:
        gate = FeedTargetPoolGate(
            is_target_pool=True,
            match_key="CAT:500",
            match_scope="CAT",
            candidate_business_domains=("apple_airpods",),
            active_candidate_business_domains=("apple_airpods",),
            decision_reason="target_pool:CAT:500",
            blocked_by_policy=False,
            signal_counts={"apple_airpods": 100},
            signal_sources={},
        )
        context = ResolvedItemCategoryContext(
            target_category_id="cat-airpods",
            resolved_category_id="cat-airpods",
            resolved_template_id="tpl-airpods",
            category_validation_status="FEED_TARGET_POOL_SINGLE_CANDIDATE",
            category_validation_reason="feed_target_pool_single_candidate:apple_airpods",
            category_validation_confidence=Decimal("1.0000"),
            resolved_business_domain="apple_airpods",
        )

        with (
            patch(
                "goofish_insight.application.services.feed_category_resolution.resolve_feed_target_pool_gate_with_session",
                return_value=gate,
            ),
            patch(
                "goofish_insight.application.services.feed_category_resolution._build_category_context_for_business_domain",
                return_value=context,
            ),
            patch(
                "goofish_insight.application.services.feed_category_resolution._classify_feed_business_domain_with_llm"
            ) as classify_mock,
        ):
            selection = resolve_feed_category_selection_with_session(
                SimpleNamespace(),
                title="AirPods Pro 2",
                raw_text="AirPods Pro 2",
                price=Decimal("899"),
                xianyu_cat_id="1",
                xianyu_tb_cat_id="2",
                xianyu_c_cat_id="3",
                tasks_by_domain={
                    "apple_airpods": self.make_task("apple_airpods", category_id="cat-airpods"),
                },
            )

        self.assertEqual(selection.resolved_business_domain, "apple_airpods")
        self.assertEqual(selection.category_context, context)
        self.assertEqual(selection.decision_source, "raw_category_single_candidate")
        classify_mock.assert_not_called()

    def test_multi_candidate_uses_llm_result_inside_candidate_set(self) -> None:
        gate = FeedTargetPoolGate(
            is_target_pool=True,
            match_key="CAT:500",
            match_scope="CAT",
            candidate_business_domains=("apple_computer", "apple_airpods"),
            active_candidate_business_domains=("apple_computer", "apple_airpods"),
            decision_reason="target_pool:CAT:500",
            blocked_by_policy=False,
            signal_counts={"apple_computer": 100, "apple_airpods": 80},
            signal_sources={},
        )
        context = ResolvedItemCategoryContext(
            target_category_id="cat-apple",
            resolved_category_id="cat-apple",
            resolved_template_id="tpl-apple",
            category_validation_status="FEED_TARGET_POOL_LLM",
            category_validation_reason="feed_target_pool_llm:apple_computer",
            category_validation_confidence=Decimal("0.9200"),
            resolved_business_domain="apple_computer",
        )

        with (
            patch(
                "goofish_insight.application.services.feed_category_resolution.resolve_feed_target_pool_gate_with_session",
                return_value=gate,
            ),
            patch(
                "goofish_insight.application.services.feed_category_resolution.llm_is_configured",
                return_value=True,
            ),
            patch(
                "goofish_insight.application.services.feed_category_resolution._classify_feed_business_domain_with_llm",
                return_value={
                    "selectedBusinessDomain": "apple_computer",
                    "confidence": 0.92,
                    "reason": "标题包含 MacBook Pro / M3 / 512G",
                },
            ) as classify_mock,
            patch(
                "goofish_insight.application.services.feed_category_resolution._build_category_context_for_business_domain",
                return_value=context,
            ),
        ):
            selection = resolve_feed_category_selection_with_session(
                SimpleNamespace(),
                title="MacBook Pro M3 16G 512G",
                raw_text="MacBook Pro M3 16G 512G",
                price=Decimal("10999"),
                xianyu_cat_id="1",
                xianyu_tb_cat_id="2",
                xianyu_c_cat_id="3",
                tasks_by_domain={
                    "apple_computer": self.make_task("apple_computer", category_id="cat-apple"),
                    "apple_airpods": self.make_task("apple_airpods", category_id="cat-airpods"),
                },
            )

        self.assertEqual(selection.resolved_business_domain, "apple_computer")
        self.assertEqual(selection.category_context, context)
        self.assertEqual(selection.decision_source, "raw_category_llm")
        classify_mock.assert_called_once()

    def test_target_pool_gate_honors_block_policy(self) -> None:
        session = _FakeSession(
            execute_results=[
                _FakeExecResult(
                    rows=[
                        SimpleNamespace(
                            match_key="CAT:500",
                            status="ACTIVE",
                            policy_mode="BLOCK",
                            category_id=None,
                        )
                    ]
                ),
                _FakeExecResult(rows=[]),
            ]
        )

        with patch(
            "goofish_insight.application.services.feed_category_resolution._load_candidate_business_domain_counts_with_session"
        ) as history_mock:
            gate = resolve_feed_target_pool_gate_with_session(
                session,
                xianyu_cat_id="500",
                xianyu_tb_cat_id=None,
                xianyu_c_cat_id=None,
                active_business_domains=("apple_computer",),
            )

        self.assertFalse(gate.is_target_pool)
        self.assertTrue(gate.blocked_by_policy)
        self.assertEqual(gate.decision_reason, "raw_cate_blocked:CAT:500")
        history_mock.assert_not_called()

    def test_target_pool_gate_uses_first_specific_scope_with_signals(self) -> None:
        session = _FakeSession(
            execute_results=[
                _FakeExecResult(rows=[]),
                _FakeExecResult(rows=[]),
            ]
        )

        def load_history_counts(*args, **kwargs):
            if kwargs["match_scope"] == "C_CAT":
                return {}
            if kwargs["match_scope"] == "CAT_TB":
                return {"apple_airpods": 5, "apple_computer": 3}
            raise AssertionError(f"Unexpected scope: {kwargs['match_scope']}")

        with (
            patch(
                "goofish_insight.application.services.feed_category_resolution._load_categories_by_id",
                return_value={},
            ),
            patch(
                "goofish_insight.application.services.feed_category_resolution._load_candidate_business_domain_counts_with_session",
                side_effect=load_history_counts,
            ),
        ):
            gate = resolve_feed_target_pool_gate_with_session(
                session,
                xianyu_cat_id="500",
                xianyu_tb_cat_id="600",
                xianyu_c_cat_id="700",
                active_business_domains=("apple_computer", "apple_airpods"),
            )

        self.assertTrue(gate.is_target_pool)
        self.assertEqual(gate.match_scope, "CAT_TB")
        self.assertEqual(gate.candidate_business_domains, ("apple_airpods", "apple_computer"))
        self.assertEqual(gate.active_candidate_business_domains, ("apple_airpods", "apple_computer"))

    def test_target_pool_gate_filters_candidates_to_active_domains(self) -> None:
        session = _FakeSession(
            execute_results=[
                _FakeExecResult(rows=[]),
                _FakeExecResult(rows=[]),
            ]
        )

        with (
            patch(
                "goofish_insight.application.services.feed_category_resolution._load_categories_by_id",
                return_value={},
            ),
            patch(
                "goofish_insight.application.services.feed_category_resolution._load_candidate_business_domain_counts_with_session",
                return_value={"apple_airpods": 5, "graphics_card": 4},
            ),
        ):
            gate = resolve_feed_target_pool_gate_with_session(
                session,
                xianyu_cat_id="500",
                xianyu_tb_cat_id="600",
                xianyu_c_cat_id="700",
                active_business_domains=("apple_airpods",),
            )

        self.assertTrue(gate.is_target_pool)
        self.assertEqual(gate.active_candidate_business_domains, ("apple_airpods",))
        self.assertEqual(gate.candidate_business_domains, ("apple_airpods", "graphics_card"))


if __name__ == "__main__":
    unittest.main()
