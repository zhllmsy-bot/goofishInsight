from __future__ import annotations

import unittest

from goofish_insight.application.services.task_config import (
    TaskConfigError,
    list_task_configs_with_session,
    serialize_task_config,
    upsert_task_config_with_session,
)
from goofish_insight.models import Category, CrawlTask, ProductAttrAuditLog


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
    def __init__(self, *, execute_results=None, categories=None) -> None:
        self.execute_results = list(execute_results or [])
        self.categories = categories or {}
        self.added = []
        self._id_counter = 995

    def execute(self, stmt):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeExecuteResult(rows=[])

    def get(self, model, key):
        if getattr(model, "__name__", "") == "Category":
            return self.categories.get(key)
        return None

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                if getattr(obj, "task_key", None):
                    setattr(obj, "id", self._id_counter)
                else:
                    setattr(obj, "id", f"00000000-0000-0000-0000-{self._id_counter:012d}")
                self._id_counter += 1

    def rollback(self) -> None:
        return None


class TaskConfigServiceTests(unittest.TestCase):
    def test_serialize_task_config_handles_none(self) -> None:
        self.assertIsNone(serialize_task_config(None))

    def test_list_task_configs_with_session_returns_rows(self) -> None:
        row = CrawlTask(
            id=1,
            task_key="apple-core",
            business_domain="apple_m_series",
            display_name="Apple Core",
            keywords=[],
            brand_lexicon=[],
            model_lexicon=[],
            config_lexicon=[],
            paging_limit=5,
        )
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[row])])

        result = list_task_configs_with_session(session)

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["taskKey"], "apple-core")

    def test_upsert_task_config_with_session_creates_task(self) -> None:
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(rows=[]), _FakeExecuteResult(rows=[])],
            categories={"cat-apple": category},
        )

        result = upsert_task_config_with_session(
            session,
            payload={
                "taskKey": "apple-core",
                "displayName": "Apple Core",
                "categoryId": "cat-apple",
                "queries": [{"query": "macbook pro", "pages": 2, "priority": 10}],
                "lexicons": {"BRAND": [{"term": "apple"}]},
            },
            operator_id="ops-bot",
            dry_run=False,
        )

        self.assertEqual(result["task"]["businessDomain"], "apple_computer")
        self.assertTrue(any(isinstance(obj, ProductAttrAuditLog) for obj in session.added))

    def test_upsert_task_config_accepts_legacy_alias_but_canonicalizes_business_domain(self) -> None:
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(rows=[]), _FakeExecuteResult(rows=[])],
            categories={"cat-apple": category},
        )

        result = upsert_task_config_with_session(
            session,
            payload={
                "taskKey": "apple-core",
                "displayName": "Apple Core",
                "categoryId": "cat-apple",
                "businessDomain": "apple_m_series",
                "queries": [{"query": "macbook air", "pages": 2, "priority": 10}],
            },
            operator_id="ops-bot",
            dry_run=False,
        )

        self.assertEqual(result["task"]["businessDomain"], "apple_computer")

    def test_upsert_task_config_rejects_business_domain_from_other_category(self) -> None:
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(rows=[])],
            categories={"cat-apple": category},
        )

        with self.assertRaises(TaskConfigError):
            upsert_task_config_with_session(
                session,
                payload={
                    "taskKey": "apple-core",
                    "displayName": "Apple Core",
                    "categoryId": "cat-apple",
                    "businessDomain": "garmin_watch",
                },
                operator_id="ops-bot",
                dry_run=False,
            )

    def test_upsert_task_config_requires_task_key(self) -> None:
        session = _FakeSession()
        with self.assertRaises(TaskConfigError):
            upsert_task_config_with_session(
                session,
                payload={"displayName": "Missing Key"},
                operator_id="ops-bot",
                dry_run=False,
            )


if __name__ == "__main__":
    unittest.main()
