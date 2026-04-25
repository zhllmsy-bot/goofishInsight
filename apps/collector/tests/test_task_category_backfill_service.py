from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from goofish_insight.application.services.task_category_backfill import backfill_task_category_bindings


class _FakeScalarRows:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeExecuteResult:
    def __init__(self, *, rows=None, scalar_value=None) -> None:
        self._rows = list(rows or [])
        self._scalar_value = scalar_value

    def scalars(self):
        return _FakeScalarRows(self._rows)

    def scalar_one_or_none(self):
        return self._scalar_value


class _FakeSession:
    def __init__(self, execute_results) -> None:
        self.execute_results = list(execute_results)

    def execute(self, stmt):
        return self.execute_results.pop(0)


class TaskCategoryBackfillServiceTests(unittest.TestCase):
    def test_backfill_task_category_bindings_sets_category_id_from_business_domain(self) -> None:
        task = SimpleNamespace(task_key="apple-production", business_domain="apple_m_series", category_id=None)
        category = SimpleNamespace(id="cat-apple", code="apple_computer")
        session = _FakeSession(
            [
                _FakeExecuteResult(rows=[task]),
                _FakeExecuteResult(scalar_value=category),
            ]
        )

        with patch("goofish_insight.application.services.task_category_backfill.session_scope") as session_scope_mock:
            session_scope_mock.return_value.__enter__.return_value = session
            session_scope_mock.return_value.__exit__.return_value = False
            summary = backfill_task_category_bindings()

        self.assertEqual(summary["processed"], 1)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(task.category_id, "cat-apple")
        self.assertEqual(summary["tasks"][0]["categoryCode"], "apple_computer")


if __name__ == "__main__":
    unittest.main()
