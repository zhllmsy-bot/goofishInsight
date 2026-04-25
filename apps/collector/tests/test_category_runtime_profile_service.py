from __future__ import annotations

import unittest
from types import SimpleNamespace

from goofish_insight.application.services.category_runtime_profile import (
    CategoryRuntimeProfileError,
    list_category_runtime_profiles_with_session,
    serialize_category_runtime_profile,
    upsert_category_runtime_profile_with_session,
)
from goofish_insight.models import Category, CategoryAttrTemplate, CategoryRuntimeProfile, ProductAttrAuditLog


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
    def __init__(self, *, execute_results=None, categories=None, templates=None) -> None:
        self.execute_results = list(execute_results or [])
        self.categories = categories or {}
        self.templates = templates or {}
        self.added = []
        self._id_counter = 900

    def execute(self, stmt):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeExecuteResult(rows=[])

    def get(self, model, key):
        if getattr(model, "__name__", "") == "Category":
            return self.categories.get(key)
        if getattr(model, "__name__", "") == "CategoryAttrTemplate":
            return self.templates.get(key)
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


class CategoryRuntimeProfileServiceTests(unittest.TestCase):
    def test_upsert_category_runtime_profile_with_session_creates_row(self) -> None:
        category = Category(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="摄影器材/镜头/可换镜头",
            level=2,
            status="ACTIVE",
        )
        template = CategoryAttrTemplate(
            id="tpl-lens-v1",
            category_id="cat-lens",
            version=1,
            status="DRAFT",
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(rows=[])],
            categories={"cat-lens": category},
            templates={"tpl-lens-v1": template},
        )

        result = upsert_category_runtime_profile_with_session(
            session,
            payload={
                "categoryId": "cat-lens",
                "activeTemplateId": "tpl-lens-v1",
                "promptProfile": "lens_extract_v1",
                "extractorProfile": "default",
                "validatorProfile": "lens_basic_v1",
            },
            operator_id="ops-bot",
            dry_run=False,
        )

        created_rows = [obj for obj in session.added if isinstance(obj, CategoryRuntimeProfile)]
        self.assertEqual(len(created_rows), 1)
        self.assertEqual(result["profile"]["categoryId"], "cat-lens")
        self.assertEqual(result["profile"]["activeTemplateId"], "tpl-lens-v1")
        self.assertEqual(result["profile"]["promptProfile"], "lens_extract_v1")
        self.assertTrue(any(isinstance(obj, ProductAttrAuditLog) for obj in session.added))

    def test_upsert_category_runtime_profile_with_session_updates_existing_row(self) -> None:
        category = Category(
            id="cat-phone",
            code="smartphone",
            name="手机",
            path="数码设备/手机",
            level=2,
            status="ACTIVE",
        )
        existing = CategoryRuntimeProfile(
            id="profile-phone",
            category_id="cat-phone",
            active_template_id=None,
            prompt_profile="phone_extract_v1",
            status="ACTIVE",
            metadata_json={"source": "seed"},
        )
        existing.category = category
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(rows=[existing])],
            categories={"cat-phone": category},
        )

        result = upsert_category_runtime_profile_with_session(
            session,
            payload={
                "categoryId": "cat-phone",
                "promptProfile": "phone_extract_v2",
                "metadata": {"source": "manual"},
            },
            operator_id="ops-bot",
            dry_run=False,
        )

        self.assertEqual(existing.prompt_profile, "phone_extract_v2")
        self.assertEqual(existing.metadata_json, {"source": "manual"})
        self.assertEqual(result["profile"]["id"], "profile-phone")

    def test_upsert_category_runtime_profile_with_session_rejects_foreign_template(self) -> None:
        category = Category(
            id="cat-body",
            code="camera_body",
            name="相机机身",
            path="摄影器材/相机/机身",
            level=2,
            status="ACTIVE",
        )
        template = CategoryAttrTemplate(
            id="tpl-lens-v2",
            category_id="cat-lens",
            version=2,
            status="DRAFT",
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(rows=[])],
            categories={"cat-body": category},
            templates={"tpl-lens-v2": template},
        )

        with self.assertRaises(CategoryRuntimeProfileError):
            upsert_category_runtime_profile_with_session(
                session,
                payload={
                    "categoryId": "cat-body",
                    "activeTemplateId": "tpl-lens-v2",
                    "promptProfile": "camera_body_extract_v1",
                },
                operator_id="ops-bot",
                dry_run=False,
            )

    def test_list_category_runtime_profiles_with_session_returns_serialized_rows(self) -> None:
        category = Category(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="摄影器材/镜头/可换镜头",
            level=2,
            status="ACTIVE",
        )
        template = CategoryAttrTemplate(
            id="tpl-lens-v1",
            category_id="cat-lens",
            version=1,
            status="DRAFT",
        )
        row = CategoryRuntimeProfile(
            id="profile-lens",
            category_id="cat-lens",
            active_template_id="tpl-lens-v1",
            prompt_profile="lens_extract_v1",
            status="ACTIVE",
            metadata_json={"phase": 1},
        )
        row.category = category
        row.active_template = template
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[row])])

        result = list_category_runtime_profiles_with_session(session)

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["categoryCode"], "camera_interchangeable_lens")
        self.assertEqual(result["items"][0]["activeTemplateVersion"], 1)

    def test_serialize_category_runtime_profile_handles_none(self) -> None:
        self.assertIsNone(serialize_category_runtime_profile(None))


if __name__ == "__main__":
    unittest.main()
