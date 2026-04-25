from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace

from goofish_insight.application.services.feed_decision_reporting import build_home_feed_decision_report


class _ScalarResult:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def scalars(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def execute(self, stmt):
        del stmt
        return _ScalarResult(self._rows)


class FeedDecisionReportingTests(unittest.TestCase):
    def test_build_home_feed_decision_report_summarizes_recent_rows(self) -> None:
        rows = [
            SimpleNamespace(
                item_id="1",
                item_id_ref=11,
                decision_stage="category_gate",
                decision_status="skipped_non_target_pool",
                decision_source="raw_category_non_target",
                decision_reason="raw_category_not_in_target_pool",
                resolved_business_domain=None,
                resolved_category_id=None,
                resolved_template_id=None,
                confidence=None,
                current_outreach_status=None,
                match_key="CAT:1",
                match_scope="CAT",
                candidate_business_domains=[],
                active_candidate_business_domains=[],
                updated_at="2026-04-17T00:00:00+00:00",
                source_platform="xianyu",
                payload={"categorySelection": {"targetPoolGate": {"matchKey": "CAT:1"}}},
            ),
            SimpleNamespace(
                item_id="2",
                item_id_ref=12,
                decision_stage="outreach",
                decision_status="sent",
                decision_source="raw_category_single_candidate",
                decision_reason="single_candidate:apple_computer",
                resolved_business_domain="apple_computer",
                resolved_category_id="cat-apple",
                resolved_template_id="tpl-apple",
                confidence=Decimal("1.0000"),
                current_outreach_status="sent",
                match_key="CAT:2",
                match_scope="CAT",
                candidate_business_domains=["apple_computer"],
                active_candidate_business_domains=["apple_computer"],
                updated_at="2026-04-17T00:01:00+00:00",
                source_platform="xianyu",
                payload={},
            ),
        ]

        report = build_home_feed_decision_report(
            _FakeSession(rows),
            lookback_days=7,
            limit=10,
        )

        self.assertEqual(report["decisionCount"], 2)
        self.assertEqual(report["byStage"][0]["decisionStage"], "category_gate")
        self.assertEqual(report["byStatus"][0]["count"], 1)
        self.assertEqual(len(report["recentDecisions"]), 2)

    def test_build_home_feed_decision_report_filters_by_scope(self) -> None:
        rows = [
            SimpleNamespace(
                item_id="1",
                item_id_ref=11,
                decision_stage="outreach",
                decision_status="sent",
                decision_source="raw_category_single_candidate",
                decision_reason="single_candidate:apple_computer",
                resolved_business_domain="apple_computer",
                resolved_category_id="cat-apple",
                resolved_template_id="tpl-apple",
                confidence=Decimal("1.0000"),
                current_outreach_status="sent",
                match_key="CAT:2",
                match_scope="CAT",
                candidate_business_domains=["apple_computer"],
                active_candidate_business_domains=["apple_computer"],
                updated_at="2026-04-17T00:01:00+00:00",
                source_platform="xianyu",
                payload={},
            ),
            SimpleNamespace(
                item_id="2",
                item_id_ref=12,
                decision_stage="outreach",
                decision_status="sent",
                decision_source="raw_category_single_candidate",
                decision_reason="single_candidate:apple_airpods",
                resolved_business_domain="apple_airpods",
                resolved_category_id="cat-airpods",
                resolved_template_id="tpl-airpods",
                confidence=Decimal("1.0000"),
                current_outreach_status="sent",
                match_key="CAT:3",
                match_scope="CAT",
                candidate_business_domains=["apple_airpods"],
                active_candidate_business_domains=["apple_airpods"],
                updated_at="2026-04-17T00:01:00+00:00",
                source_platform="xianyu",
                payload={},
            ),
        ]

        report = build_home_feed_decision_report(
            _FakeSession(rows),
            category_code="apple_airpods",
            lookback_days=7,
            limit=10,
        )

        self.assertEqual(report["decisionCount"], 1)
        self.assertEqual(report["recentDecisions"][0]["resolvedBusinessDomain"], "apple_airpods")


if __name__ == "__main__":
    unittest.main()
