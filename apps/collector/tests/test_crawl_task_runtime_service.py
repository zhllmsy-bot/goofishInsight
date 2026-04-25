from __future__ import annotations

import unittest
from datetime import datetime

from goofish_insight.application.services.crawl_task_runtime import (
    CrawlTaskRuntimeError,
    build_crawl_task_runtime_config_with_session,
)
from goofish_insight.compat import UTC
from goofish_insight.models import CrawlTask, CrawlTaskLexicon, CrawlTaskQuery


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


class CrawlTaskRuntimeServiceTests(unittest.TestCase):
    def test_build_crawl_task_runtime_config_with_session_falls_back_to_legacy_arrays(self) -> None:
        task = CrawlTask(
            id=11,
            task_key="lens-discovery",
            source_platform="xianyu",
            business_domain="camera_interchangeable_lens",
            display_name="Lens Discovery",
            keywords=["尼康 z 50 1.2", "尼康 z 24-70 2.8"],
            brand_lexicon=["尼康", "nikon"],
            model_lexicon=["z 50 1.2 s"],
            config_lexicon=["1.2", "2.8"],
            paging_limit=3,
            profile_key="chrome-attached",
            parallel_tabs=2,
            task_type="DISCOVERY",
            metadata_json={"phase": 1},
        )
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[task]),
                _FakeExecuteResult(rows=[]),
                _FakeExecuteResult(rows=[]),
            ]
        )

        result = build_crawl_task_runtime_config_with_session(session, task_key="lens-discovery")

        self.assertEqual(result["task"]["taskKey"], "lens-discovery")
        self.assertEqual(result["task"]["profileKey"], "chrome-attached")
        self.assertEqual(len(result["queries"]), 2)
        self.assertEqual(result["queries"][0]["status"], "LEGACY")
        self.assertEqual(result["lexicons"]["BRAND"][0]["term"], "尼康")

    def test_build_crawl_task_runtime_config_with_session_prefers_new_tables(self) -> None:
        task = CrawlTask(
            id=21,
            task_key="apple-production",
            source_platform="xianyu",
            business_domain="apple_m_series",
            display_name="Apple Production",
            keywords=["legacy query"],
            brand_lexicon=["apple"],
            model_lexicon=["macbook pro"],
            config_lexicon=["16g"],
            paging_limit=5,
        )
        query_row = CrawlTaskQuery(
            id=201,
            task_id=21,
            query_text="macbook pro 14 m4 16g 512g",
            pages=0,
            priority=20,
            status="ACTIVE",
            last_run_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
            metadata_json={"source": "db"},
        )
        lexicon_row = CrawlTaskLexicon(
            id=301,
            task_id=21,
            lexicon_type="MODEL",
            term="macbook pro 14",
            priority=10,
            status="ACTIVE",
            metadata_json={"source": "db"},
        )
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[task]),
                _FakeExecuteResult(rows=[query_row]),
                _FakeExecuteResult(rows=[lexicon_row]),
            ]
        )

        result = build_crawl_task_runtime_config_with_session(session, task_key="apple-production")

        self.assertEqual(len(result["queries"]), 1)
        self.assertEqual(result["queries"][0]["query"], "macbook pro 14 m4 16g 512g")
        self.assertEqual(result["queries"][0]["status"], "ACTIVE")
        self.assertEqual(result["lexicons"]["MODEL"][0]["term"], "macbook pro 14")
        self.assertNotIn("BRAND", result["lexicons"])

    def test_build_crawl_task_runtime_config_with_session_requires_existing_task(self) -> None:
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[])])

        with self.assertRaises(CrawlTaskRuntimeError):
            build_crawl_task_runtime_config_with_session(session, task_key="missing-task")


if __name__ == "__main__":
    unittest.main()
