from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight.application.services.category_config import (
    CategoryConfigError,
    list_category_configs_with_session,
    serialize_category_config,
    upsert_category_config_with_session,
)
from goofish_insight.models import Category, CategoryAttrTemplate, ProductAttrAuditLog


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
        self._id_counter = 980

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
                setattr(obj, "id", f"00000000-0000-0000-0000-{self._id_counter:012d}")
                self._id_counter += 1

    def rollback(self) -> None:
        return None


class CategoryConfigServiceTests(unittest.TestCase):
    def test_serialize_category_config_uses_compat_labels(self) -> None:
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        template = CategoryAttrTemplate(
            id="tpl-apple-v1",
            category_id="cat-apple",
            version=1,
            status="DRAFT",
        )
        category.templates = [template]

        payload = serialize_category_config(category)

        self.assertEqual(payload["legacyBusinessDomains"], ["apple_m_series", "apple_computer"])
        self.assertEqual(payload["recommendedPromptProfile"], "apple_computer_extract_v1")
        self.assertEqual(payload["templateCount"], 1)

    def test_list_category_configs_with_session_returns_sorted_rows(self) -> None:
        lens = Category(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="camera/lens",
            level=2,
            status="ACTIVE",
        )
        apple = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[lens, apple])])

        result = list_category_configs_with_session(session)

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][0]["code"], "apple_computer")

    def test_upsert_category_config_with_session_creates_category_and_runtime(self) -> None:
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[]), _FakeExecuteResult(rows=[])])

        with patch(
            "goofish_insight.application.services.category_config.upsert_category_runtime_profile_with_session",
            return_value={"profile": {"categoryId": "cat-apple", "promptProfile": "apple_computer_extract_v1"}},
        ):
            result = upsert_category_config_with_session(
                session,
                payload={
                    "categoryId": "cat-apple",
                    "code": "apple_computer",
                    "name": "Apple电脑",
                    "path": "computers/apple-computer",
                    "level": 2,
                    "promptProfile": "apple_computer_extract_v1",
                },
                operator_id="ops-bot",
                dry_run=False,
            )

        self.assertEqual(result["category"]["code"], "apple_computer")
        self.assertTrue(any(isinstance(obj, ProductAttrAuditLog) for obj in session.added))

    def test_upsert_category_config_requires_prompt_profile_when_runtime_fields_present(self) -> None:
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[]), _FakeExecuteResult(rows=[])])

        with self.assertRaises(CategoryConfigError):
            upsert_category_config_with_session(
                session,
                payload={
                    "code": "custom_camera",
                    "name": "自定义相机",
                    "path": "camera/custom",
                    "level": 2,
                    "activeTemplateId": "tpl-1",
                },
                operator_id="ops-bot",
                dry_run=False,
            )


if __name__ == "__main__":
    unittest.main()
