from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from goofish_insight.application.services.feed_pre_ingest_reporting import (
    build_feed_pre_ingest_rejection_report,
)
from goofish_insight.models import ItemIngestRejection


class _FakeScalarRows:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeExecuteResult:
    def __init__(self, rows=None) -> None:
        self._rows = rows or []

    def scalars(self):
        return _FakeScalarRows(self._rows)


class _FakeSession:
    def __init__(self, *, execute_results=None) -> None:
        self.execute_results = list(execute_results or [])

    def execute(self, stmt):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeExecuteResult(rows=[])


class FeedPreIngestReportingTests(unittest.TestCase):
    def test_build_feed_pre_ingest_rejection_report_merges_db_counts_and_log_samples(self) -> None:
        apple_row = ItemIngestRejection(
            source_platform="xianyu",
            item_id="apple-1",
            business_domain="apple_m_series",
            category_id="cat-apple",
            rejection_stage="feed_pre_ingest_template",
            rejection_reason="missing_target_view",
            hit_count=3,
            first_rejected_at=datetime(2026, 4, 16, 8, 0, tzinfo=UTC),
            last_rejected_at=datetime(2026, 4, 16, 9, 0, tzinfo=UTC),
        )
        phone_row = ItemIngestRejection(
            source_platform="xianyu",
            item_id="phone-1",
            business_domain="phone",
            category_id="cat-phone",
            rejection_stage="feed_pre_ingest_template",
            rejection_reason="missing_template",
            hit_count=2,
            first_rejected_at=datetime(2026, 4, 16, 7, 0, tzinfo=UTC),
            last_rejected_at=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
        )
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[apple_row, phone_row]),
            ]
        )

        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "feed.jsonl"
            log_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "generated_at": "2026-04-16T10:00:00+00:00",
                                "items": [
                                    {
                                        "item_id": "phone-2",
                                        "title": "iPhone 15",
                                        "status": "skipped_pre_ingest_template_rejected",
                                        "reason": "missing_template",
                                        "business_domain": "phone",
                                        "mapped_business_domain": "phone",
                                    },
                                    {
                                        "item_id": "apple-2",
                                        "title": "Apple Watch Ultra 2",
                                        "status": "skipped_pre_ingest_template_rejected",
                                        "reason": "missing_target_view",
                                        "business_domain": "apple_m_series",
                                        "mapped_business_domain": "apple_computer",
                                        "pre_ingest_template_id": "tpl-apple",
                                        "pre_ingest_category_id": "cat-apple",
                                    },
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "generated_at": "2026-04-16T11:00:00+00:00",
                                "items": [
                                    {
                                        "item_id": "apple-3",
                                        "title": "Apple Watch S10",
                                        "price": 2999,
                                        "status": "skipped_pre_ingest_template_rejected",
                                        "reason": "missing_target_view",
                                        "business_domain": "apple_computer",
                                        "mapped_business_domain": "apple_computer",
                                        "pre_ingest_template_id": "tpl-apple",
                                        "pre_ingest_category_id": "cat-apple",
                                    },
                                    {
                                        "item_id": "apple-4",
                                        "title": "MacBook Pro M4",
                                        "status": "persisted",
                                        "business_domain": "apple_computer",
                                    },
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            detail = build_feed_pre_ingest_rejection_report(
                session,
                category_code="apple_computer",
                limit=5,
                sample_limit=5,
                log_scan_lines=50,
                log_path=log_path,
            )

        self.assertEqual(detail["categoryCode"], "apple_computer")
        self.assertEqual(detail["scopeKeys"], ["apple_computer", "apple_m_series"])
        self.assertEqual(detail["dbSummary"]["rejectedItemCount"], 1)
        self.assertEqual(detail["dbSummary"]["totalHitCount"], 3)
        self.assertEqual(detail["byBusinessDomain"][0]["businessDomain"], "apple_computer")
        self.assertEqual(detail["byReason"][0]["reason"], "missing_target_view")
        self.assertEqual(len(detail["recentRejections"]), 1)
        self.assertEqual(detail["recentRejections"][0]["itemId"], "apple-1")
        self.assertEqual(detail["logSummary"]["sampleCount"], 2)
        self.assertEqual(detail["logSummary"]["sampleReasonCounts"], {"missing_target_view": 2})
        sample_ids = [sample["itemId"] for sample in detail["logSummary"]["samples"]]
        self.assertEqual(sample_ids, ["apple-3", "apple-2"])
