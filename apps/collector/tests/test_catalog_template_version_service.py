from __future__ import annotations

import unittest

from goofish_insight.application.services.catalog_template_version import (
    CatalogTemplateVersionError,
    persist_catalog_template_version_payload_with_session,
)
from goofish_insight.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeScopeType,
    Category,
    CategoryAttrTemplate,
    CategoryAttrTemplateItem,
    ProductAttrAuditLog,
)


class _FakeScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalarRows(self._rows)

    def scalar_one_or_none(self):
        if not self._rows:
            return None
        return self._rows[0]


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self._id_counter = 500
        self.categories: dict[str, Category] = {}
        self.templates_by_id: dict[str, CategoryAttrTemplate] = {}
        self.attribute_rows: list[AttributeDefinition] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            current_id = getattr(obj, "id", None)
            if current_id is None:
                setattr(obj, "id", f"00000000-0000-0000-0000-{self._id_counter:012d}")
                self._id_counter += 1

    def get(self, model, key: str):
        if model is Category:
            return self.categories.get(key)
        if model is CategoryAttrTemplate:
            return self.templates_by_id.get(key)
        return None

    def execute(self, stmt):
        text_stmt = str(stmt)
        if "FROM attribute_definition" in text_stmt:
            return _FakeScalarResult(self.attribute_rows)
        if "FROM category_attr_template" in text_stmt:
            return _FakeScalarResult([])
        raise AssertionError(f"Unexpected statement: {text_stmt}")


class CatalogTemplateVersionServiceTests(unittest.TestCase):
    def test_persist_catalog_template_version_payload_with_session_creates_version(self) -> None:
        session = _FakeSession()
        category = Category(
            id="00000000-0000-0000-0000-000000000001",
            code="phone",
            name="手机",
            path="electronics/phone",
            level=2,
            status="ACTIVE",
        )
        session.categories[category.id] = category
        session.attribute_rows = [
            AttributeDefinition(
                id="00000000-0000-0000-0000-000000000021",
                scope_id="platform",
                code="color",
                name="颜色",
                data_type=AttributeDataType.ENUM,
                value_scope="SKU",
                is_multi=False,
            ),
            AttributeDefinition(
                id="00000000-0000-0000-0000-000000000022",
                scope_id="platform",
                code="memory_size",
                name="内存",
                data_type=AttributeDataType.ENUM,
                value_scope="SKU",
                is_multi=False,
            ),
        ]

        result = persist_catalog_template_version_payload_with_session(
            session,
            payload={
                "requestId": "req-template-v2",
                "categoryId": category.id,
                "template": {
                    "version": 2,
                    "status": "PUBLISHED",
                    "items": [
                        {"attributeCode": "color", "isRequired": True, "isSale": True, "sortNo": 10},
                        {"attributeCode": "memory_size", "isRequired": True, "isSale": False, "sortNo": 20},
                    ],
                },
            },
            operator_id="ops-bot",
        )

        self.assertEqual(result["requestId"], "req-template-v2")
        self.assertEqual(result["categoryId"], category.id)
        self.assertEqual(result["templateVersion"], 2)
        added_types = [type(obj) for obj in session.added]
        self.assertIn(CategoryAttrTemplate, added_types)
        self.assertIn(CategoryAttrTemplateItem, added_types)
        self.assertIn(ProductAttrAuditLog, added_types)

    def test_persist_catalog_template_version_payload_requires_existing_category(self) -> None:
        session = _FakeSession()

        with self.assertRaises(CatalogTemplateVersionError):
            persist_catalog_template_version_payload_with_session(
                session,
                payload={
                    "categoryId": "00000000-0000-0000-0000-000000000001",
                    "template": {
                        "version": 2,
                        "items": [{"attributeCode": "color"}],
                    },
                },
                operator_id="ops-bot",
            )

    def test_persist_catalog_template_version_can_bind_ambiguous_attribute_by_id(self) -> None:
        session = _FakeSession()
        category = Category(
            id="00000000-0000-0000-0000-000000000001",
            code="phone",
            name="手机",
            path="electronics/phone",
            level=2,
            status="ACTIVE",
        )
        session.categories[category.id] = category
        session.attribute_rows = [
            AttributeDefinition(
                id="00000000-0000-0000-0000-000000000021",
                scope_type=AttributeScopeType.PLATFORM,
                scope_id="platform",
                code="color",
                name="颜色",
                data_type=AttributeDataType.ENUM,
                value_scope="SKU",
                is_multi=False,
            ),
            AttributeDefinition(
                id="00000000-0000-0000-0000-000000000022",
                scope_type=AttributeScopeType.MERCHANT,
                scope_id="merchant-demo",
                code="color",
                name="颜色",
                data_type=AttributeDataType.ENUM,
                value_scope="SKU",
                is_multi=False,
            ),
        ]

        result = persist_catalog_template_version_payload_with_session(
            session,
            payload={
                "requestId": "req-template-v3",
                "categoryId": category.id,
                "template": {
                    "version": 3,
                    "status": "PUBLISHED",
                    "items": [
                        {
                            "attributeId": "00000000-0000-0000-0000-000000000022",
                            "attributeCode": "color",
                            "isRequired": True,
                            "isSale": True,
                            "sortNo": 10,
                        },
                    ],
                },
            },
            operator_id="ops-bot",
        )

        added_template_items = [obj for obj in session.added if isinstance(obj, CategoryAttrTemplateItem)]
        self.assertEqual(result["templateVersion"], 3)
        self.assertEqual(len(added_template_items), 1)
        self.assertEqual(added_template_items[0].attribute_id, "00000000-0000-0000-0000-000000000022")


if __name__ == "__main__":
    unittest.main()
