from __future__ import annotations

import unittest
from contextlib import contextmanager

from goofish_insight.application.services.catalog_template import (
    CatalogTemplatePersistenceError,
    persist_catalog_template_payload,
    persist_catalog_template_payload_with_session,
)
from goofish_insight.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeOption,
    AttributeScopeType,
    AttributeStatus,
    Category,
    CategoryAttrTemplate,
    CategoryAttrTemplateItem,
    ProductAttrAuditLog,
)


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.rollback_called = False
        self._id_counter = 400
        self._existing: dict[tuple[type, str], object] = {}
        self._execute_results: list[object | None] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            current_id = getattr(obj, "id", None)
            if current_id is None:
                setattr(obj, "id", f"00000000-0000-0000-0000-{self._id_counter:012d}")
                self._id_counter += 1

    def get(self, model, key: str):
        return self._existing.get((model, key))

    def execute(self, stmt):
        class _FakeExecuteResult:
            def __init__(self, value):
                self.value = value

            def scalar_one_or_none(self):
                return self.value

        if self._execute_results:
            return _FakeExecuteResult(self._execute_results.pop(0))
        return _FakeExecuteResult(None)

    def rollback(self) -> None:
        self.rollback_called = True


class CatalogTemplateServiceTests(unittest.TestCase):
    def test_persist_catalog_template_payload_with_session_builds_metadata_rows(self) -> None:
        session = _FakeSession()
        payload = {
            "requestId": "req-template-1",
            "category": {
                "code": "phone",
                "name": "手机",
                "path": "electronics/phone",
                "level": 2,
                "status": "ACTIVE",
            },
            "attributes": [
                {
                    "code": "color",
                    "name": "颜色",
                    "dataType": "ENUM",
                    "valueScope": "SKU",
                    "isMulti": False,
                    "status": "ACTIVE",
                    "options": [
                        {"optionCode": "black", "optionName": "黑色", "sortNo": 10},
                        {"optionCode": "white", "optionName": "白色", "sortNo": 20},
                    ],
                },
                {
                    "code": "screen_size",
                    "name": "屏幕尺寸",
                    "dataType": "NUMBER",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "status": "ACTIVE",
                    "options": [],
                },
            ],
            "template": {
                "version": 1,
                "status": "PUBLISHED",
                "publishedBy": "ops-bot",
                "items": [
                    {"attributeCode": "color", "isRequired": True, "isSale": True, "sortNo": 10},
                    {"attributeCode": "screen_size", "isRequired": False, "sortNo": 20},
                ],
            },
        }

        result = persist_catalog_template_payload_with_session(
            session,
            payload=payload,
            operator_id="ops-bot",
        )

        self.assertEqual(result["requestId"], "req-template-1")
        self.assertEqual(result["attributeCount"], 2)
        self.assertEqual(result["optionCount"], 2)
        self.assertEqual(result["templateItemCount"], 2)

        added_types = [type(obj) for obj in session.added]
        self.assertIn(Category, added_types)
        self.assertIn(AttributeDefinition, added_types)
        self.assertIn(AttributeOption, added_types)
        self.assertIn(CategoryAttrTemplate, added_types)
        self.assertIn(CategoryAttrTemplateItem, added_types)
        self.assertIn(ProductAttrAuditLog, added_types)

    def test_persist_catalog_template_payload_rolls_back_in_dry_run_mode(self) -> None:
        session = _FakeSession()

        @contextmanager
        def fake_session_scope():
            yield session

        payload = {
            "requestId": "req-template-dry-run",
            "category": {
                "code": "phone",
                "name": "手机",
                "path": "electronics/phone",
                "level": 2,
            },
            "attributes": [
                {
                    "code": "color",
                    "name": "颜色",
                    "dataType": "ENUM",
                    "valueScope": "SKU",
                    "options": [{"optionCode": "black", "optionName": "黑色"}],
                }
            ],
            "template": {
                "version": 1,
                "items": [{"attributeCode": "color", "isSale": True}],
            },
        }

        from unittest.mock import patch

        with patch(
            "goofish_insight.application.services.catalog_template.session_scope",
            fake_session_scope,
        ):
            result = persist_catalog_template_payload(
                payload=payload,
                operator_id="ops-bot",
                dry_run=True,
            )

        self.assertTrue(result["dryRun"])
        self.assertTrue(session.rollback_called)

    def test_persist_catalog_template_payload_rejects_duplicate_attribute_code(self) -> None:
        session = _FakeSession()
        payload = {
            "category": {
                "code": "phone",
                "name": "手机",
                "path": "electronics/phone",
                "level": 2,
            },
            "attributes": [
                {
                    "code": "color",
                    "name": "颜色",
                    "dataType": "ENUM",
                    "valueScope": "SKU",
                    "options": [],
                },
                {
                    "code": "color",
                    "name": "颜色-重复",
                    "dataType": "ENUM",
                    "valueScope": "SKU",
                    "options": [],
                },
            ],
            "template": {
                "version": 1,
                "items": [{"attributeCode": "color"}],
            },
        }

        with self.assertRaises(CatalogTemplatePersistenceError):
            persist_catalog_template_payload_with_session(
                session,
                payload=payload,
                operator_id="ops-bot",
            )

    def test_persist_catalog_template_payload_reuses_existing_attribute_definition(self) -> None:
        session = _FakeSession()
        existing_attribute = AttributeDefinition(
            id="00000000-0000-0000-0000-000000000901",
            scope_type=AttributeScopeType.PLATFORM,
            scope_id="platform",
            code="product_line",
            name="产品线",
            data_type=AttributeDataType.TEXT,
            value_scope="SPU",
            is_multi=False,
            unit=None,
            status=AttributeStatus.ACTIVE,
        )
        session._execute_results = [existing_attribute]
        payload = {
            "requestId": "req-template-reuse-1",
            "category": {
                "code": "garmin-watch",
                "name": "佳明手表",
                "path": "wearables/garmin-watch",
                "level": 2,
            },
            "attributes": [
                {
                    "code": "product_line",
                    "name": "产品线",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "options": [],
                }
            ],
            "template": {
                "version": 1,
                "items": [{"attributeCode": "product_line"}],
            },
        }

        result = persist_catalog_template_payload_with_session(
            session,
            payload=payload,
            operator_id="ops-bot",
        )

        self.assertEqual(result["attributeCount"], 1)
        self.assertEqual(sum(isinstance(obj, AttributeDefinition) for obj in session.added), 0)


if __name__ == "__main__":
    unittest.main()
