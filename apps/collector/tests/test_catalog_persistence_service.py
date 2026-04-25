from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from goofish_insight.application.services.catalog_persistence import (
    CatalogMetadata,
    CatalogPersistenceError,
    persist_catalog_payload,
    persist_catalog_payload_with_session,
    replace_catalog_payload_with_session,
)
from goofish_insight.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeOption,
    CategoryAttrTemplate,
    OutboxEvent,
    ProductAttrAuditLog,
    ProductSku,
    ProductSkuAttrValue,
    ProductSpu,
    ProductSpuAttrValue,
)


def _build_metadata() -> CatalogMetadata:
    template = CategoryAttrTemplate(
        id="00000000-0000-0000-0000-000000000011",
        category_id="00000000-0000-0000-0000-000000000001",
        version=1,
    )
    color = AttributeDefinition(
        id="00000000-0000-0000-0000-000000000021",
        scope_id="platform",
        code="color",
        name="颜色",
        data_type=AttributeDataType.ENUM,
        value_scope="SKU",
        is_multi=False,
    )
    memory_size = AttributeDefinition(
        id="00000000-0000-0000-0000-000000000022",
        scope_id="platform",
        code="memory_size",
        name="内存",
        data_type=AttributeDataType.ENUM,
        value_scope="SKU",
        is_multi=False,
    )
    screen_size = AttributeDefinition(
        id="00000000-0000-0000-0000-000000000023",
        scope_id="platform",
        code="screen_size",
        name="屏幕尺寸",
        data_type=AttributeDataType.NUMBER,
        value_scope="SPU",
        is_multi=False,
    )
    black = AttributeOption(
        id="00000000-0000-0000-0000-000000000031",
        attribute_id=color.id,
        option_code="black",
        option_name="黑色",
    )
    memory_12 = AttributeOption(
        id="00000000-0000-0000-0000-000000000032",
        attribute_id=memory_size.id,
        option_code="12",
        option_name="12GB",
    )
    return CatalogMetadata(
        template=template,
        template_items=[
            {
                "attributeCode": "color",
                "attributeId": color.id,
                "isSale": True,
                "sortNo": 10,
            },
            {
                "attributeCode": "memory_size",
                "attributeId": memory_size.id,
                "isSale": True,
                "sortNo": 20,
            },
            {
                "attributeCode": "screen_size",
                "attributeId": screen_size.id,
                "isSale": False,
                "sortNo": 30,
            },
        ],
        attributes=[
            {"code": "color", "name": "颜色", "dataType": "ENUM", "isMulti": False},
            {"code": "memory_size", "name": "内存", "dataType": "ENUM", "isMulti": False},
            {"code": "screen_size", "name": "屏幕尺寸", "dataType": "NUMBER", "isMulti": False},
        ],
        attribute_map={
            "color": color,
            "memory_size": memory_size,
            "screen_size": screen_size,
        },
        option_code_map={
            ("color", "black"): black,
            ("memory_size", "12"): memory_12,
        },
        option_id_map={
            ("color", black.id): black,
            ("memory_size", memory_12.id): memory_12,
        },
        category_code="phone",
    )


def _build_apple_metadata() -> CatalogMetadata:
    template = CategoryAttrTemplate(
        id="33333333-3333-3333-3333-333333333401",
        category_id="33333333-3333-3333-3333-333333333101",
        version=1,
    )
    model_name = AttributeDefinition(
        id="33333333-3333-3333-3333-333333333501",
        scope_id="platform",
        code="model_name",
        name="型号",
        data_type=AttributeDataType.TEXT,
        value_scope="SPU",
        is_multi=False,
    )
    screen_size = AttributeDefinition(
        id="33333333-3333-3333-3333-333333333502",
        scope_id="platform",
        code="screen_size_in",
        name="屏幕尺寸",
        data_type=AttributeDataType.NUMBER,
        value_scope="SPU",
        is_multi=False,
    )
    return CatalogMetadata(
        template=template,
        template_items=[
            {
                "attributeCode": "model_name",
                "attributeId": model_name.id,
                "isSale": False,
                "sortNo": 10,
            },
            {
                "attributeCode": "screen_size_in",
                "attributeId": screen_size.id,
                "isSale": False,
                "sortNo": 20,
            },
        ],
        attributes=[
            {"code": "model_name", "name": "型号", "dataType": "TEXT", "isMulti": False},
            {"code": "screen_size_in", "name": "屏幕尺寸", "dataType": "NUMBER", "isMulti": False},
        ],
        attribute_map={
            "model_name": model_name,
            "screen_size_in": screen_size,
        },
        option_code_map={},
        option_id_map={},
        category_code="apple_computer",
    )


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.rollback_called = False
        self._id_counter = 100
        self._existing_spus: dict[str, ProductSpu] = {}

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            current_id = getattr(obj, "id", None)
            if current_id is None:
                setattr(obj, "id", f"00000000-0000-0000-0000-{self._id_counter:012d}")
                self._id_counter += 1

    def get(self, model, key: str):
        if model is ProductSpu:
            return self._existing_spus.get(key)
        return None

    def delete(self, obj: object) -> None:
        self.deleted.append(obj)

    def rollback(self) -> None:
        self.rollback_called = True


class CatalogPersistenceServiceTests(unittest.TestCase):
    def test_persist_catalog_payload_with_session_builds_models(self) -> None:
        session = _FakeSession()
        payload = {
            "requestId": "req-1",
            "spu": {
                "categoryId": "00000000-0000-0000-0000-000000000001",
                "templateId": "00000000-0000-0000-0000-000000000011",
                "merchantId": "merchant-1",
                "brandId": "brand-1",
                "title": "小米 15",
                "status": "ACTIVE",
            },
            "spuAttributes": [
                {"attributeCode": "screen_size", "numberValue": 6.36, "unit": "inch"}
            ],
            "skus": [
                {
                    "skuCode": "MI15-BLK-12G",
                    "price": 4599,
                    "stock": 100,
                    "status": "ACTIVE",
                    "saleAttributes": [
                        {"attributeCode": "memory_size", "optionCode": "12"},
                        {"attributeCode": "color", "optionCode": "black"},
                    ],
                }
            ],
        }

        with patch(
            "goofish_insight.application.services.catalog_persistence._load_catalog_metadata",
            return_value=_build_metadata(),
        ):
            result = persist_catalog_payload_with_session(
                session,
                payload=payload,
                operator_id="ops-bot",
            )

        self.assertEqual(result["requestId"], "req-1")
        self.assertEqual(result["skuCount"], 1)
        self.assertEqual(result["spuAttributeCount"], 1)
        self.assertEqual(result["skuAttributeCount"], 2)
        self.assertTrue(result["spuId"])
        self.assertEqual(len(result["skuIds"]), 1)

        added_types = [type(obj) for obj in session.added]
        self.assertIn(ProductSpu, added_types)
        self.assertIn(ProductSku, added_types)
        self.assertIn(ProductSpuAttrValue, added_types)
        self.assertIn(ProductSkuAttrValue, added_types)
        self.assertIn(OutboxEvent, added_types)
        self.assertIn(ProductAttrAuditLog, added_types)

        spu_rows = [obj for obj in session.added if isinstance(obj, ProductSpu)]
        self.assertEqual(spu_rows[0].attr_snapshot_json["spuId"], result["spuId"])

        sku_attr_rows = [obj for obj in session.added if isinstance(obj, ProductSkuAttrValue)]
        self.assertEqual(
            {row.option_id for row in sku_attr_rows},
            {
                "00000000-0000-0000-0000-000000000031",
                "00000000-0000-0000-0000-000000000032",
            },
        )

    def test_persist_catalog_payload_rolls_back_in_dry_run_mode(self) -> None:
        session = _FakeSession()

        @contextmanager
        def fake_session_scope():
            yield session

        payload = {
            "requestId": "req-dry-run",
            "spu": {
                "categoryId": "00000000-0000-0000-0000-000000000001",
                "templateId": "00000000-0000-0000-0000-000000000011",
                "title": "小米 15",
            },
            "spuAttributes": [],
            "skus": [],
        }

        with patch(
            "goofish_insight.application.services.catalog_persistence._load_catalog_metadata",
            return_value=_build_metadata(),
        ), patch(
            "goofish_insight.application.services.catalog_persistence.session_scope",
            fake_session_scope,
        ):
            result = persist_catalog_payload(
                payload=payload,
                operator_id="ops-bot",
                dry_run=True,
            )

        self.assertTrue(session.rollback_called)
        self.assertTrue(result["dryRun"])

    def test_persist_catalog_payload_rejects_unknown_attribute_code(self) -> None:
        session = _FakeSession()
        payload = {
            "spu": {
                "categoryId": "00000000-0000-0000-0000-000000000001",
                "templateId": "00000000-0000-0000-0000-000000000011",
                "title": "小米 15",
            },
            "spuAttributes": [{"attributeCode": "battery_size", "numberValue": 5400}],
            "skus": [],
        }

        with patch(
            "goofish_insight.application.services.catalog_persistence._load_catalog_metadata",
            return_value=_build_metadata(),
        ):
            with self.assertRaises(CatalogPersistenceError):
                persist_catalog_payload_with_session(
                    session,
                    payload=payload,
                    operator_id="ops-bot",
                )

    def test_persist_catalog_payload_rejects_cross_category_apple_watch(self) -> None:
        session = _FakeSession()
        payload = {
            "spu": {
                "categoryId": "33333333-3333-3333-3333-333333333101",
                "templateId": "33333333-3333-3333-3333-333333333401",
                "title": "Apple Watch Series 10",
                "status": "ACTIVE",
            },
            "spuAttributes": [
                {"attributeCode": "model_name", "textValue": "Apple Watch Series 10"},
                {"attributeCode": "screen_size_in", "numberValue": 46, "unit": "inch"},
            ],
            "skus": [
                {
                    "skuCode": "WATCH-S10",
                    "price": 1600,
                    "stock": 1,
                    "status": "ACTIVE",
                    "saleAttributes": [],
                    "attributes": [],
                }
            ],
        }

        with patch(
            "goofish_insight.application.services.catalog_persistence._load_catalog_metadata",
            return_value=_build_apple_metadata(),
        ):
            with self.assertRaises(CatalogPersistenceError):
                persist_catalog_payload_with_session(
                    session,
                    payload=payload,
                    operator_id="ops-bot",
                )

    def test_replace_catalog_payload_with_session_reuses_spu_id(self) -> None:
        session = _FakeSession()
        existing_spu = ProductSpu(
            id="00000000-0000-0000-0000-000000000099",
            category_id="00000000-0000-0000-0000-000000000001",
            template_id="00000000-0000-0000-0000-000000000011",
            title="旧标题",
            attr_snapshot_json={"spuId": "00000000-0000-0000-0000-000000000099"},
        )
        old_sku = ProductSku(
            id="00000000-0000-0000-0000-000000000199",
            spu_id=existing_spu.id,
            sku_code="OLD-SKU",
            sales_signature_raw="old",
            sales_signature_hash="old",
            price=1,
            stock=1,
            attr_snapshot_json={},
        )
        old_sku.attributes = [
            ProductSkuAttrValue(
                id="00000000-0000-0000-0000-000000000299",
                sku_id=old_sku.id,
                attribute_id="00000000-0000-0000-0000-000000000021",
                value_seq=0,
                option_id="00000000-0000-0000-0000-000000000031",
            )
        ]
        existing_spu.skus = [old_sku]
        existing_spu.attributes = [
            ProductSpuAttrValue(
                id="00000000-0000-0000-0000-000000000399",
                spu_id=existing_spu.id,
                attribute_id="00000000-0000-0000-0000-000000000023",
                value_seq=0,
                number_value=6.1,
            )
        ]
        session._existing_spus[existing_spu.id] = existing_spu

        payload = {
            "requestId": "req-replace",
            "spu": {
                "id": existing_spu.id,
                "categoryId": "00000000-0000-0000-0000-000000000001",
                "templateId": "00000000-0000-0000-0000-000000000011",
                "merchantId": "merchant-2",
                "brandId": "brand-2",
                "title": "新标题",
                "status": "ACTIVE",
            },
            "spuAttributes": [
                {"attributeCode": "screen_size", "numberValue": 6.36, "unit": "inch"}
            ],
            "skus": [
                {
                    "skuCode": "MI15-BLK-12G",
                    "price": 4599,
                    "stock": 100,
                    "status": "ACTIVE",
                    "saleAttributes": [
                        {"attributeCode": "memory_size", "optionCode": "12"},
                        {"attributeCode": "color", "optionCode": "black"},
                    ],
                }
            ],
        }

        with patch(
            "goofish_insight.application.services.catalog_persistence._load_catalog_metadata",
            return_value=_build_metadata(),
        ):
            result = replace_catalog_payload_with_session(
                session,
                payload=payload,
                operator_id="ops-bot",
            )

        self.assertEqual(result["spuId"], existing_spu.id)
        self.assertEqual(existing_spu.title, "新标题")
        self.assertEqual(existing_spu.attr_snapshot_json["spuId"], existing_spu.id)
        self.assertGreaterEqual(len(session.deleted), 2)
        self.assertIn(old_sku, session.deleted)


if __name__ == "__main__":
    unittest.main()
