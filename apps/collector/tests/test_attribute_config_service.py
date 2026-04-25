from __future__ import annotations

import unittest

from goofish_insight.application.services.attribute_config import (
    AttributeConfigError,
    list_attribute_configs_with_session,
    serialize_attribute_config,
    upsert_attribute_config_with_session,
)
from goofish_insight.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeScopeType,
    AttributeStatus,
    ProductAttrAuditLog,
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


class _FakeSession:
    def __init__(self, *, execute_results=None, attributes=None) -> None:
        self.execute_results = list(execute_results or [])
        self.attributes = attributes or {}
        self.added = []
        self._id_counter = 990

    def execute(self, stmt):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeExecuteResult(rows=[])

    def get(self, model, key):
        if getattr(model, "__name__", "") == "AttributeDefinition":
            return self.attributes.get(key)
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


class AttributeConfigServiceTests(unittest.TestCase):
    def test_serialize_attribute_config_handles_options_and_refs(self) -> None:
        row = AttributeDefinition(
            id="attr-memory",
            scope_type=AttributeScopeType.PLATFORM,
            scope_id="platform",
            code="memory_gb",
            name="内存",
            data_type=AttributeDataType.NUMBER,
            value_scope="SKU",
            is_multi=False,
            status=AttributeStatus.ACTIVE,
        )

        payload = serialize_attribute_config(row)

        self.assertEqual(payload["code"], "memory_gb")
        self.assertEqual(payload["dataType"], "NUMBER")
        self.assertEqual(payload["optionCount"], 0)

    def test_list_attribute_configs_with_session_returns_rows(self) -> None:
        row = AttributeDefinition(
            id="attr-memory",
            scope_type=AttributeScopeType.PLATFORM,
            scope_id="platform",
            code="memory_gb",
            name="内存",
            data_type=AttributeDataType.NUMBER,
            value_scope="SKU",
            is_multi=False,
            status=AttributeStatus.ACTIVE,
        )
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[row])])

        result = list_attribute_configs_with_session(session)

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["code"], "memory_gb")

    def test_upsert_attribute_config_with_session_creates_row(self) -> None:
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[]), _FakeExecuteResult(rows=[])])

        result = upsert_attribute_config_with_session(
            session,
            payload={
                "code": "device_color",
                "name": "颜色",
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": "ENUM",
                "valueScope": "SALE",
                "status": "ACTIVE",
                "options": [
                    {"optionCode": "black", "optionName": "黑色"},
                    {"optionCode": "white", "optionName": "白色"},
                ],
            },
            operator_id="ops-bot",
            dry_run=False,
        )

        self.assertEqual(result["attribute"]["code"], "device_color")
        self.assertTrue(any(isinstance(obj, ProductAttrAuditLog) for obj in session.added))

    def test_upsert_attribute_config_rejects_missing_code(self) -> None:
        session = _FakeSession()
        with self.assertRaises(AttributeConfigError):
            upsert_attribute_config_with_session(
                session,
                payload={
                    "name": "颜色",
                    "dataType": "ENUM",
                    "valueScope": "SALE",
                },
                operator_id="ops-bot",
                dry_run=False,
            )

    def test_serialize_attribute_config_marks_default_common_attribute(self) -> None:
        row = AttributeDefinition(
            id="attr-brand",
            scope_type=AttributeScopeType.PLATFORM,
            scope_id="platform",
            code="brand_name",
            name="品牌名称",
            data_type=AttributeDataType.TEXT,
            value_scope="SPU",
            is_multi=False,
            status=AttributeStatus.ACTIVE,
            validation_schema={},
        )

        payload = serialize_attribute_config(row)

        self.assertTrue(payload["isCommon"])

    def test_upsert_attribute_config_with_is_common_updates_validation_schema(self) -> None:
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[]), _FakeExecuteResult(rows=[])])

        result = upsert_attribute_config_with_session(
            session,
            payload={
                "code": "warranty_state",
                "name": "保修状态",
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "status": "ACTIVE",
                "isCommon": True,
            },
            operator_id="ops-bot",
            dry_run=False,
        )

        self.assertTrue(result["attribute"]["isCommon"])
        self.assertEqual(result["attribute"]["validationSchema"]["runtimeCommon"], True)


if __name__ == "__main__":
    unittest.main()
