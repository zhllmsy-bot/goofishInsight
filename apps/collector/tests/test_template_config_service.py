from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight.application.services.template_config import (
    TemplateConfigError,
    preview_template_config_diff_with_session,
    serialize_template_config,
    upsert_template_config_with_session,
)
from goofish_insight.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeScopeType,
    AttributeStatus,
    Category,
    CategoryAttrTemplate,
    CategoryAttrTemplateItem,
    CategoryRuntimeProfile,
    ProductAttrAuditLog,
    TemplateStatus,
)


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

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, *, execute_results=None, categories=None, templates=None) -> None:
        self.execute_results = list(execute_results or [])
        self.categories = categories or {}
        self.templates = templates or {}
        self.added = []
        self.deleted = []
        self._id_counter = 996

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
        if getattr(obj, "__class__", None).__name__ == "CategoryAttrTemplate":
            self.templates[obj.id] = obj

    def delete(self, obj) -> None:
        self.deleted.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                setattr(obj, "id", f"00000000-0000-0000-0000-{self._id_counter:012d}")
                self._id_counter += 1
            if getattr(obj, "__class__", None).__name__ == "CategoryAttrTemplate":
                self.templates[obj.id] = obj

    def rollback(self) -> None:
        return None


class TemplateConfigServiceTests(unittest.TestCase):
    def test_serialize_template_config_marks_active_template(self) -> None:
        category = Category(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="camera/lens",
            level=2,
            status="ACTIVE",
        )
        template = CategoryAttrTemplate(
            id="tpl-lens-v2",
            category_id="cat-lens",
            version=2,
            status=TemplateStatus.PUBLISHED,
        )
        runtime = CategoryRuntimeProfile(
            id="runtime-lens",
            category_id="cat-lens",
            active_template_id="tpl-lens-v2",
            prompt_profile="camera_interchangeable_lens_extract_v1",
            status="ACTIVE",
        )
        template.category = category
        category.runtime_profile = runtime

        payload = serialize_template_config(template, include_items=False, include_diff=False)

        self.assertTrue(payload["isActiveTemplate"])
        self.assertEqual(payload["activePromptProfile"], "camera_interchangeable_lens_extract_v1")

    def test_preview_template_config_diff_with_session_returns_added_codes(self) -> None:
        category = Category(
            id="cat-phone",
            code="phone",
            name="手机",
            path="electronics/phone",
            level=2,
            status="ACTIVE",
        )
        baseline = CategoryAttrTemplate(
            id="tpl-phone-v1",
            category_id="cat-phone",
            version=1,
            status=TemplateStatus.PUBLISHED,
        )
        attr_memory = AttributeDefinition(
            id="attr-memory",
            scope_type=AttributeScopeType.PLATFORM,
            scope_id="platform",
            code="memory_gb",
            name="内存",
            data_type=AttributeDataType.NUMBER,
            value_scope="SKU",
            status=AttributeStatus.ACTIVE,
        )
        baseline_item = CategoryAttrTemplateItem(
            id="item-memory",
            template_id="tpl-phone-v1",
            attribute_id="attr-memory",
            is_required=False,
            is_sale=True,
            is_filter=False,
            is_search=False,
            is_display=True,
            sort_no=10,
        )
        baseline_item.attribute = attr_memory
        baseline.items = [baseline_item]
        baseline.category = category
        runtime = CategoryRuntimeProfile(
            id="runtime-phone",
            category_id="cat-phone",
            active_template_id="tpl-phone-v1",
            prompt_profile="smartphone_extract_v1",
            status="ACTIVE",
        )
        category.runtime_profile = runtime

        session = _FakeSession(categories={"cat-phone": category}, templates={"tpl-phone-v1": baseline})

        payload = preview_template_config_diff_with_session(
            session,
            payload={
                "categoryId": "cat-phone",
                "items": [
                    {"attributeCode": "memory_gb", "isSale": True, "sortNo": 10},
                    {"attributeCode": "storage_gb", "isSale": True, "sortNo": 20},
                ],
            },
        )

        self.assertEqual(payload["addedAttributeCodes"], ["storage_gb"])
        self.assertEqual(payload["compareToTemplateId"], "tpl-phone-v1")

    def test_upsert_template_config_with_session_creates_row(self) -> None:
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        attr_chip = AttributeDefinition(
            id="attr-chip",
            scope_type=AttributeScopeType.PLATFORM,
            scope_id="platform",
            code="chip_family",
            name="芯片系列",
            data_type=AttributeDataType.TEXT,
            value_scope="SPU",
            status=AttributeStatus.ACTIVE,
        )
        attr_memory = AttributeDefinition(
            id="attr-memory",
            scope_type=AttributeScopeType.PLATFORM,
            scope_id="platform",
            code="memory_gb",
            name="内存",
            data_type=AttributeDataType.NUMBER,
            value_scope="SKU",
            status=AttributeStatus.ACTIVE,
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(rows=[attr_chip, attr_memory])],
            categories={"cat-apple": category},
        )

        result = upsert_template_config_with_session(
            session,
            payload={
                "categoryId": "cat-apple",
                "version": 1,
                "status": "DRAFT",
                "items": [
                    {
                        "attributeCode": "chip_family",
                        "isRequired": True,
                        "role": "locking",
                        "weight": 0.25,
                        "enumValues": ["M1", "M2", "M3", "M4"],
                        "sortNo": 10,
                    },
                    {
                        "attributeCode": "memory_gb",
                        "isSale": True,
                        "role": "locking",
                        "weight": 0.15,
                        "normalization": {"unit": "GB"},
                        "sortNo": 20,
                    },
                ],
            },
            operator_id="ops-bot",
            dry_run=False,
        )

        self.assertEqual(result["template"]["categoryCode"], "apple_computer")
        self.assertEqual(result["template"]["itemCount"], 2)
        first_item = result["template"]["items"][0]
        self.assertEqual(first_item["role"], "locking")
        self.assertEqual(first_item["weight"], 0.25)
        self.assertEqual(first_item["enumValues"], ["M1", "M2", "M3", "M4"])
        second_item = result["template"]["items"][1]
        self.assertEqual(second_item["normalization"], {"unit": "GB"})
        self.assertTrue(any(isinstance(obj, ProductAttrAuditLog) for obj in session.added))

    def test_upsert_template_config_can_bind_active_runtime_profile(self) -> None:
        category = Category(
            id="cat-watch",
            code="garmin_watch",
            name="Garmin手表",
            path="wearables/garmin-watch",
            level=2,
            status="ACTIVE",
        )
        attr_case = AttributeDefinition(
            id="attr-case",
            scope_type=AttributeScopeType.PLATFORM,
            scope_id="platform",
            code="case_size_mm",
            name="表径",
            data_type=AttributeDataType.NUMBER,
            value_scope="SPU",
            status=AttributeStatus.ACTIVE,
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(rows=[attr_case])],
            categories={"cat-watch": category},
        )

        with patch(
            "goofish_insight.application.services.template_config.upsert_category_runtime_profile_with_session",
            return_value={"profile": {"categoryId": "cat-watch", "activeTemplateId": "tpl-watch-v1"}},
        ):
            result = upsert_template_config_with_session(
                session,
                payload={
                    "categoryId": "cat-watch",
                    "version": 1,
                    "status": "PUBLISHED",
                    "bindAsActiveTemplate": True,
                    "promptProfile": "garmin_watch_extract_v1",
                    "items": [
                        {"attributeCode": "case_size_mm", "isRequired": True, "sortNo": 10},
                    ],
                },
                operator_id="ops-bot",
                dry_run=False,
            )

        self.assertEqual(result["runtimeProfile"]["categoryId"], "cat-watch")

    def test_upsert_template_config_rejects_ambiguous_attribute_codes_across_scopes(self) -> None:
        category = Category(
            id="cat-phone",
            code="phone",
            name="手机",
            path="electronics/phone",
            level=2,
            status="ACTIVE",
        )
        platform_attr = AttributeDefinition(
            id="attr-platform-color",
            scope_type=AttributeScopeType.PLATFORM,
            scope_id="platform",
            code="color",
            name="颜色",
            data_type=AttributeDataType.TEXT,
            value_scope="SKU",
            status=AttributeStatus.ACTIVE,
        )
        merchant_attr = AttributeDefinition(
            id="attr-merchant-color",
            scope_type=AttributeScopeType.MERCHANT,
            scope_id="merchant-demo",
            code="color",
            name="颜色",
            data_type=AttributeDataType.TEXT,
            value_scope="SKU",
            status=AttributeStatus.ACTIVE,
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(rows=[platform_attr, merchant_attr])],
            categories={"cat-phone": category},
        )

        with self.assertRaises(TemplateConfigError):
            upsert_template_config_with_session(
                session,
                payload={
                    "categoryId": "cat-phone",
                    "version": 1,
                    "status": "DRAFT",
                    "items": [
                        {"attributeCode": "color", "isRequired": True, "sortNo": 10},
                    ],
                },
                operator_id="ops-bot",
                dry_run=False,
            )


if __name__ == "__main__":
    unittest.main()
