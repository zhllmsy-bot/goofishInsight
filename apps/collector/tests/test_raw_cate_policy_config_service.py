from __future__ import annotations

import unittest

from goofish_insight.application.services.raw_cate_policy_config import (
    list_raw_cate_policy_configs_with_session,
    upsert_raw_cate_policy_config_with_session,
)
from goofish_insight.models import (
    Category,
    CategoryAttrTemplate,
    ProductAttrAuditLog,
    TemplateStatus,
    XianyuCategoryMapping,
    XianyuCategoryMatchScope,
    XianyuCategoryOnboardingQueue,
)


class _FakeScalarRows:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeExecuteResult:
    def __init__(self, rows=None, scalar=None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return _FakeScalarRows(self._rows)

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    def __init__(self, *, execute_results=None, categories=None, templates=None, mappings=None) -> None:
        self.execute_results = list(execute_results or [])
        self.categories = categories or {}
        self.templates = templates or {}
        self.mappings = mappings or {}
        self.added = []
        self._id_counter = 998

    def execute(self, stmt):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeExecuteResult(rows=[])

    def get(self, model, key):
        if getattr(model, "__name__", "") == "Category":
            return self.categories.get(key)
        if getattr(model, "__name__", "") == "CategoryAttrTemplate":
            return self.templates.get(key)
        if getattr(model, "__name__", "") == "XianyuCategoryMapping":
            return self.mappings.get(key)
        return None

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                setattr(obj, "id", f"00000000-0000-0000-0000-{self._id_counter:012d}")
                self._id_counter += 1
            if getattr(obj, "__class__", None).__name__ == "XianyuCategoryMapping":
                self.mappings[obj.id] = obj

    def rollback(self) -> None:
        return None


class RawCatePolicyConfigServiceTests(unittest.TestCase):
    def test_list_raw_cate_policy_configs_with_session_returns_queue_snapshot(self) -> None:
        mapping = XianyuCategoryMapping(
            id="map-1",
            match_scope=XianyuCategoryMatchScope.C_CAT,
            match_key="C_CAT:126864783",
            xianyu_c_cat_id="126864783",
            policy_mode="FORCE_TEMPLATE",
            status="ACTIVE",
        )
        queue = XianyuCategoryOnboardingQueue(
            id="queue-1",
            match_scope=XianyuCategoryMatchScope.C_CAT,
            match_key="C_CAT:126864783",
            xianyu_c_cat_id="126864783",
            status="PENDING",
            item_count_snapshot=3,
            sample_titles=["NIKKOR Z 50mm f/1.2 S"],
        )
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[mapping]),
                _FakeExecuteResult(rows=[queue]),
            ]
        )

        result = list_raw_cate_policy_configs_with_session(session)

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["queueSnapshot"]["itemCountSnapshot"], 3)

    def test_upsert_raw_cate_policy_config_with_session_creates_force_template_row(self) -> None:
        category = Category(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="camera/lens",
            level=2,
            status="ACTIVE",
        )
        template = CategoryAttrTemplate(
            id="tpl-lens-v1",
            category_id="cat-lens",
            version=1,
            status=TemplateStatus.PUBLISHED,
        )
        template.category = category
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(scalar=None),
                _FakeExecuteResult(scalar=None),
            ],
            categories={"cat-lens": category},
            templates={"tpl-lens-v1": template},
        )

        result = upsert_raw_cate_policy_config_with_session(
            session,
            payload={
                "matchScope": "C_CAT",
                "xianyuCCatId": "126864783",
                "policyMode": "FORCE_TEMPLATE",
                "templateId": "tpl-lens-v1",
            },
            operator_id="ops-bot",
            dry_run=False,
        )

        self.assertEqual(result["policy"]["policyMode"], "FORCE_TEMPLATE")
        self.assertEqual(result["policy"]["templateId"], "tpl-lens-v1")
        self.assertTrue(any(isinstance(obj, ProductAttrAuditLog) for obj in session.added))


if __name__ == "__main__":
    unittest.main()
