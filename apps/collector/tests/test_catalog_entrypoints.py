from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class _DummySession:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class CatalogEntrypointTests(unittest.TestCase):
    def test_catalog_signature_preview_route_returns_canonical_signature(self) -> None:
        client = TestClient(create_app())

        response = client.post(
            "/api/catalog/tools/signature/preview",
            json={
                "templateItems": [
                    {
                        "attributeCode": "color",
                        "attributeId": "attr-color",
                        "isSale": True,
                        "sortNo": 10,
                    },
                    {
                        "attributeCode": "memory_size",
                        "attributeId": "attr-memory",
                        "isSale": True,
                        "sortNo": 20,
                    },
                ],
                "attributes": [
                    {
                        "code": "color",
                        "name": "颜色",
                        "dataType": "ENUM",
                        "isMulti": False,
                    },
                    {
                        "code": "memory_size",
                        "name": "内存",
                        "dataType": "ENUM",
                        "isMulti": False,
                    },
                ],
                "selections": [
                    {"attributeCode": "memory_size", "optionCode": "12"},
                    {"attributeCode": "color", "optionCode": "black"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["raw"],
            "attr-color:black|attr-memory:12",
        )

    def test_catalog_snapshot_preview_route_returns_snapshot(self) -> None:
        client = TestClient(create_app())

        response = client.post(
            "/api/catalog/tools/snapshot/preview",
            json={
                "spu": {
                    "id": "spu-1",
                    "categoryId": "cat-phone",
                    "templateId": "tpl-phone-v1",
                    "title": "小米 15",
                    "status": "ACTIVE",
                },
                "templateItems": [
                    {
                        "attributeCode": "color",
                        "attributeId": "attr-color",
                        "isSale": True,
                        "sortNo": 10,
                    },
                    {
                        "attributeCode": "memory_size",
                        "attributeId": "attr-memory",
                        "isSale": True,
                        "sortNo": 20,
                    },
                    {
                        "attributeCode": "screen_size",
                        "attributeId": "attr-screen",
                        "isSale": False,
                        "sortNo": 30,
                    },
                ],
                "attributes": [
                    {
                        "code": "color",
                        "name": "颜色",
                        "dataType": "ENUM",
                        "isMulti": False,
                    },
                    {
                        "code": "memory_size",
                        "name": "内存",
                        "dataType": "ENUM",
                        "isMulti": False,
                    },
                    {
                        "code": "screen_size",
                        "name": "屏幕尺寸",
                        "dataType": "NUMBER",
                        "isMulti": False,
                    },
                ],
                "spuAttributes": [
                    {
                        "attributeCode": "screen_size",
                        "numberValue": 6.36,
                        "unit": "inch",
                    }
                ],
                "skus": [
                    {
                        "skuCode": "MI15-BLK-12G",
                        "price": 4599,
                        "stock": 100,
                        "status": "ACTIVE",
                        "saleAttributes": [
                            {
                                "attributeCode": "memory_size",
                                "optionCode": "12",
                                "optionName": "12GB",
                            },
                            {
                                "attributeCode": "color",
                                "optionCode": "black",
                                "optionName": "黑色",
                            },
                        ],
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["spuId"], "spu-1")
        self.assertEqual(payload["saleAttributeCodes"], ["color", "memory_size"])
        self.assertEqual(
            payload["skus"][0]["salesSignatureRaw"],
            "attr-color:black|attr-memory:12",
        )

    def test_catalog_persist_plan_preview_route_returns_rows(self) -> None:
        client = TestClient(create_app())

        response = client.post(
            "/api/catalog/tools/persist-plan/preview",
            json={
                "requestId": "req-1",
                "spu": {
                    "id": "spu-1",
                    "categoryId": "cat-phone",
                    "templateId": "tpl-phone-v1",
                    "merchantId": "merchant-1",
                    "brandId": "brand-1",
                    "title": "小米 15",
                    "status": "ACTIVE",
                },
                "templateItems": [
                    {"attributeCode": "color", "attributeId": "attr-color", "isSale": True, "sortNo": 10},
                    {"attributeCode": "memory_size", "attributeId": "attr-memory", "isSale": True, "sortNo": 20},
                ],
                "attributes": [
                    {"code": "color", "name": "颜色", "dataType": "ENUM", "isMulti": False},
                    {"code": "memory_size", "name": "内存", "dataType": "ENUM", "isMulti": False},
                ],
                "spuAttributes": [],
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
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["requestId"], "req-1")
        self.assertEqual(payload["skuRows"][0]["salesSignatureRaw"], "attr-color:black|attr-memory:12")
        self.assertEqual(payload["outboxEvent"]["payload"]["skuCount"], 1)

    def test_catalog_persist_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.catalog_preview.persist_catalog_payload",
            return_value={
                "dryRun": False,
                "requestId": "req-persist",
                "spuId": "00000000-0000-0000-0000-000000000099",
                "skuIds": [],
                "spuAttributeCount": 0,
                "skuCount": 0,
                "skuAttributeCount": 0,
                "outboxEventId": "00000000-0000-0000-0000-000000000199",
                "auditLogId": "00000000-0000-0000-0000-000000000299",
            },
        ) as persist_mock:
            response = client.post(
                "/api/catalog/tools/persist",
                json={
                    "requestId": "req-persist",
                    "operatorId": "ops-bot",
                    "dryRun": False,
                    "spu": {
                        "categoryId": "00000000-0000-0000-0000-000000000001",
                        "templateId": "00000000-0000-0000-0000-000000000011",
                        "title": "小米 15",
                    },
                    "spuAttributes": [],
                    "skus": [],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["requestId"], "req-persist")
        persist_mock.assert_called_once()
        self.assertEqual(persist_mock.call_args.kwargs["operator_id"], "ops-bot")
        self.assertFalse(persist_mock.call_args.kwargs["dry_run"])

    def test_catalog_replace_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.catalog_preview.replace_catalog_payload",
            return_value={
                "dryRun": False,
                "requestId": "req-replace",
                "spuId": "00000000-0000-0000-0000-000000000099",
                "skuIds": [],
                "spuAttributeCount": 0,
                "skuCount": 0,
                "skuAttributeCount": 0,
                "outboxEventId": "00000000-0000-0000-0000-000000000199",
                "auditLogId": "00000000-0000-0000-0000-000000000299",
            },
        ) as replace_mock:
            response = client.post(
                "/api/catalog/tools/replace",
                json={
                    "requestId": "req-replace",
                    "operatorId": "ops-bot",
                    "dryRun": False,
                    "spu": {
                        "id": "00000000-0000-0000-0000-000000000099",
                        "categoryId": "00000000-0000-0000-0000-000000000001",
                        "templateId": "00000000-0000-0000-0000-000000000011",
                        "title": "小米 15",
                    },
                    "spuAttributes": [],
                    "skus": [],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["requestId"], "req-replace")
        replace_mock.assert_called_once()
        self.assertEqual(replace_mock.call_args.kwargs["operator_id"], "ops-bot")
        self.assertFalse(replace_mock.call_args.kwargs["dry_run"])

    def test_catalog_template_persist_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.catalog_preview.persist_catalog_template_payload",
            return_value={
                "dryRun": False,
                "requestId": "req-template",
                "categoryId": "00000000-0000-0000-0000-000000000401",
                "templateId": "00000000-0000-0000-0000-000000000402",
                "attributeCount": 1,
                "optionCount": 1,
                "templateItemCount": 1,
                "auditLogId": "00000000-0000-0000-0000-000000000499",
            },
        ) as persist_mock:
            response = client.post(
                "/api/catalog/tools/template/persist",
                json={
                    "requestId": "req-template",
                    "operatorId": "ops-bot",
                    "dryRun": False,
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
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["requestId"], "req-template")
        persist_mock.assert_called_once()
        self.assertEqual(persist_mock.call_args.kwargs["operator_id"], "ops-bot")
        self.assertFalse(persist_mock.call_args.kwargs["dry_run"])

    def test_catalog_template_version_persist_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.catalog_preview.persist_catalog_template_version_payload",
            return_value={
                "dryRun": False,
                "requestId": "req-template-v2",
                "categoryId": "cat-1",
                "templateId": "tpl-2",
                "templateVersion": 2,
                "templateItemCount": 2,
                "auditLogId": "audit-1",
            },
        ) as persist_mock:
            response = client.post(
                "/api/catalog/tools/template-version/persist",
                json={
                    "requestId": "req-template-v2",
                    "operatorId": "ops-bot",
                    "dryRun": False,
                    "categoryId": "cat-1",
                    "template": {
                        "version": 2,
                        "items": [{"attributeCode": "color", "isSale": True}],
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["templateVersion"], 2)
        persist_mock.assert_called_once()

    def test_catalog_spu_page_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with (
            patch(
                "goofish_insight.entrypoints.web.routers.catalog_preview.SessionLocal",
                return_value=_DummySession(),
            ),
            patch(
                "goofish_insight.entrypoints.web.routers.catalog_preview.build_catalog_spu_page",
                return_value={
                    "page": 1,
                    "pageSize": 20,
                    "total": 1,
                    "items": [{"id": "spu-1", "title": "小米 15 Pro"}],
                },
            ) as page_mock,
        ):
            response = client.get(
                "/api/catalog/spus",
                params={
                    "categoryId": "cat-1",
                    "status": "ACTIVE",
                    "page": 1,
                    "pageSize": 20,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        page_mock.assert_called_once()
        self.assertEqual(page_mock.call_args.kwargs["category_id"], "cat-1")
        self.assertEqual(page_mock.call_args.kwargs["status"], "ACTIVE")

    def test_catalog_sku_page_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with (
            patch(
                "goofish_insight.entrypoints.web.routers.catalog_preview.SessionLocal",
                return_value=_DummySession(),
            ),
            patch(
                "goofish_insight.entrypoints.web.routers.catalog_preview.build_catalog_sku_page",
                return_value={
                    "page": 1,
                    "pageSize": 20,
                    "total": 2,
                    "items": [{"id": "sku-1", "skuCode": "MI15P-BLK-12G"}],
                },
            ) as page_mock,
        ):
            response = client.get(
                "/api/catalog/skus",
                params={
                    "spuId": "spu-1",
                    "status": "ACTIVE",
                    "page": 1,
                    "pageSize": 20,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 2)
        page_mock.assert_called_once()
        self.assertEqual(page_mock.call_args.kwargs["spu_id"], "spu-1")
        self.assertEqual(page_mock.call_args.kwargs["status"], "ACTIVE")

    def test_catalog_spu_detail_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with (
            patch(
                "goofish_insight.entrypoints.web.routers.catalog_preview.SessionLocal",
                return_value=_DummySession(),
            ),
            patch(
                "goofish_insight.entrypoints.web.routers.catalog_preview.build_catalog_spu_detail",
                return_value={
                    "spu": {"id": "spu-1", "title": "小米 15", "status": "ACTIVE"},
                    "spuAttributes": [],
                    "skus": [],
                },
            ) as detail_mock,
        ):
            response = client.get("/api/catalog/spus/spu-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["spu"]["id"], "spu-1")
        detail_mock.assert_called_once()

    def test_catalog_template_detail_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with (
            patch(
                "goofish_insight.entrypoints.web.routers.catalog_preview.SessionLocal",
                return_value=_DummySession(),
            ),
            patch(
                "goofish_insight.entrypoints.web.routers.catalog_preview.build_catalog_template_detail",
                return_value={
                    "category": {"id": "cat-1", "code": "phone"},
                    "template": {"id": "tpl-1", "version": 1},
                    "items": [],
                },
            ) as detail_mock,
        ):
            response = client.get("/api/catalog/templates/tpl-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["template"]["id"], "tpl-1")
        detail_mock.assert_called_once()

    def test_catalog_category_templates_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with (
            patch(
                "goofish_insight.entrypoints.web.routers.catalog_preview.SessionLocal",
                return_value=_DummySession(),
            ),
            patch(
                "goofish_insight.entrypoints.web.routers.catalog_preview.build_catalog_category_templates",
                return_value={
                    "category": {"id": "cat-1", "code": "phone"},
                    "templateCount": 2,
                    "latestTemplateId": "tpl-2",
                    "templates": [
                        {"id": "tpl-2", "version": 2},
                        {"id": "tpl-1", "version": 1},
                    ],
                },
            ) as detail_mock,
        ):
            response = client.get("/api/catalog/categories/cat-1/templates")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["latestTemplateId"], "tpl-2")
        detail_mock.assert_called_once()

    def test_catalog_template_upgrade_preview_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.catalog_preview.preview_catalog_template_upgrade",
            return_value={
                "spuId": "spu-1",
                "targetTemplateId": "tpl-2",
                "requiresSkuPayloadRewrite": True,
            },
        ) as preview_mock:
            response = client.post(
                "/api/catalog/spus/spu-1/template-upgrades/preview",
                json={"targetTemplateId": "tpl-2"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["targetTemplateId"], "tpl-2")
        preview_mock.assert_called_once_with(spu_id="spu-1", target_template_id="tpl-2")

    def test_catalog_template_replace_plan_preview_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.catalog_preview.preview_catalog_template_replace_plan",
            return_value={
                "spuId": "spu-1",
                "targetTemplateId": "tpl-2",
                "readyForReplace": True,
            },
        ) as preview_mock:
            response = client.post(
                "/api/catalog/spus/spu-1/template-upgrades/replace-plan/preview",
                json={"targetTemplateId": "tpl-2"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["readyForReplace"])
        preview_mock.assert_called_once_with(spu_id="spu-1", target_template_id="tpl-2")

    def test_catalog_template_upgrade_apply_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.catalog_preview.apply_catalog_template_upgrade",
            return_value={
                "dryRun": False,
                "requestId": "req-upgrade",
                "spuId": "spu-1",
                "fromTemplateId": "tpl-1",
                "toTemplateId": "tpl-3",
                "outboxEventId": "evt-1",
                "auditLogId": "audit-1",
                "preview": {"canAutoUpgrade": True},
            },
        ) as apply_mock:
            response = client.post(
                "/api/catalog/spus/spu-1/template-upgrades/apply",
                json={
                    "requestId": "req-upgrade",
                    "operatorId": "ops-bot",
                    "dryRun": False,
                    "targetTemplateId": "tpl-3",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["toTemplateId"], "tpl-3")
        apply_mock.assert_called_once_with(
            spu_id="spu-1",
            target_template_id="tpl-3",
            operator_id="ops-bot",
            request_id="req-upgrade",
            dry_run=False,
        )

    def test_catalog_template_replace_plan_apply_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.catalog_preview.apply_catalog_template_replace_plan",
            return_value={
                "dryRun": False,
                "requestId": "req-replace-plan",
                "spuId": "spu-1",
                "targetTemplateId": "tpl-2",
                "replacePlan": {"readyForReplace": True},
                "replaceResult": {"spuId": "spu-1"},
            },
        ) as apply_mock:
            response = client.post(
                "/api/catalog/spus/spu-1/template-upgrades/replace-plan/apply",
                json={
                    "requestId": "req-replace-plan",
                    "operatorId": "ops-bot",
                    "dryRun": False,
                    "targetTemplateId": "tpl-2",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["targetTemplateId"], "tpl-2")
        apply_mock.assert_called_once_with(
            spu_id="spu-1",
            target_template_id="tpl-2",
            operator_id="ops-bot",
            request_id="req-replace-plan",
            dry_run=False,
        )


if __name__ == "__main__":
    unittest.main()
