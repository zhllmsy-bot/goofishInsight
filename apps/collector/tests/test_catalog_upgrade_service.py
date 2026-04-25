from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight.application.services.catalog_upgrade import (
    CatalogTemplateReplaceApplyError,
    CatalogTemplateReplacePlanError,
    CatalogTemplateUpgradeApplyError,
    CatalogTemplateUpgradePreviewError,
    apply_catalog_template_replace_plan_with_session,
    apply_catalog_template_upgrade_with_session,
    preview_catalog_template_replace_plan_with_session,
    preview_catalog_template_upgrade_with_session,
)
from goofish_insight.models import CategoryAttrTemplate, OutboxEvent, ProductAttrAuditLog, ProductSpu


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self._id_counter = 800
        self.spu_by_id: dict[str, ProductSpu] = {}
        self.template_by_id: dict[str, CategoryAttrTemplate] = {}

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
            return self.spu_by_id.get(key)
        if model is CategoryAttrTemplate:
            return self.template_by_id.get(key)
        return None


class CatalogUpgradeServiceTests(unittest.TestCase):
    def test_preview_catalog_template_upgrade_reports_sale_scope_changes(self) -> None:
        session = object()
        current_spu_detail = {
            "spu": {
                "id": "spu-1",
                "categoryId": "cat-1",
                "templateId": "tpl-1",
            },
            "spuAttributes": [
                {"attributeCode": "screen_size"},
            ],
            "skus": [
                {"skuCode": "sku-1", "attributes": [{"attributeCode": "color"}, {"attributeCode": "memory_size"}]},
                {"skuCode": "sku-2", "attributes": [{"attributeCode": "color"}, {"attributeCode": "memory_size"}]},
            ],
        }
        current_template = {
            "category": {"id": "cat-1"},
            "template": {"id": "tpl-1", "version": 1},
            "items": [
                {"attributeCode": "color", "valueScope": "SKU", "isRequired": True, "isSale": True},
                {"attributeCode": "memory_size", "valueScope": "SKU", "isRequired": True, "isSale": True},
                {"attributeCode": "screen_size", "valueScope": "SPU", "isRequired": False, "isSale": False},
            ],
        }
        target_template = {
            "category": {"id": "cat-1"},
            "template": {"id": "tpl-2", "version": 2},
            "items": [
                {"attributeCode": "color", "valueScope": "SKU", "isRequired": True, "isSale": True},
                {"attributeCode": "memory_size", "valueScope": "SKU", "isRequired": True, "isSale": False},
                {"attributeCode": "screen_size", "valueScope": "SPU", "isRequired": True, "isSale": False},
            ],
        }

        with (
            patch(
                "goofish_insight.application.services.catalog_upgrade.build_catalog_spu_detail",
                return_value=current_spu_detail,
            ),
            patch(
                "goofish_insight.application.services.catalog_upgrade.build_catalog_template_detail",
                side_effect=[current_template, target_template],
            ),
        ):
            result = preview_catalog_template_upgrade_with_session(
                session,
                spu_id="spu-1",
                target_template_id="tpl-2",
            )

        self.assertEqual(result["currentCategoryId"], "cat-1")
        self.assertEqual(result["targetCategoryId"], "cat-1")
        self.assertEqual(result["currentTemplateId"], "tpl-1")
        self.assertEqual(result["targetTemplateId"], "tpl-2")
        self.assertEqual(result["removedSaleAttributeCodes"], ["memory_size"])
        self.assertTrue(result["requiresSkuPayloadRewrite"])
        self.assertFalse(result["canAutoUpgrade"])
        self.assertEqual(result["missingRequiredSpuAttributeCodes"], [])

    def test_preview_catalog_template_upgrade_requires_missing_spu_attr(self) -> None:
        session = object()
        with (
            patch(
                "goofish_insight.application.services.catalog_upgrade.build_catalog_spu_detail",
                return_value={
                    "spu": {"id": "spu-1", "categoryId": "cat-1", "templateId": "tpl-1"},
                    "spuAttributes": [],
                    "skus": [],
                },
            ),
            patch(
                "goofish_insight.application.services.catalog_upgrade.build_catalog_template_detail",
                side_effect=[
                    {"category": {"id": "cat-1"}, "template": {"id": "tpl-1", "version": 1}, "items": []},
                    {
                        "category": {"id": "cat-1"},
                        "template": {"id": "tpl-2", "version": 2},
                        "items": [
                            {"attributeCode": "battery_capacity", "valueScope": "SPU", "isRequired": True, "isSale": False}
                        ],
                    },
                ],
            ),
        ):
            result = preview_catalog_template_upgrade_with_session(
                session,
                spu_id="spu-1",
                target_template_id="tpl-2",
            )

        self.assertEqual(result["missingRequiredSpuAttributeCodes"], ["battery_capacity"])
        self.assertFalse(result["canAutoUpgrade"])

    def test_preview_catalog_template_upgrade_requires_same_category(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.catalog_upgrade.build_catalog_spu_detail",
                return_value={
                    "spu": {"id": "spu-1", "categoryId": "cat-1", "templateId": "tpl-1"},
                    "spuAttributes": [],
                    "skus": [],
                },
            ),
            patch(
                "goofish_insight.application.services.catalog_upgrade.build_catalog_template_detail",
                side_effect=[
                    {"category": {"id": "cat-1"}, "template": {"id": "tpl-1", "version": 1}, "items": []},
                    {"category": {"id": "cat-2"}, "template": {"id": "tpl-2", "version": 2}, "items": []},
                ],
            ),
        ):
            with self.assertRaises(CatalogTemplateUpgradePreviewError):
                preview_catalog_template_upgrade_with_session(
                    object(),
                    spu_id="spu-1",
                    target_template_id="tpl-2",
                )

    def test_preview_catalog_template_upgrade_errors_when_spu_missing(self) -> None:
        with patch(
            "goofish_insight.application.services.catalog_upgrade.build_catalog_spu_detail",
            return_value=None,
        ):
            with self.assertRaises(CatalogTemplateUpgradePreviewError):
                preview_catalog_template_upgrade_with_session(
                    object(),
                    spu_id="missing",
                    target_template_id="tpl-2",
                )

    def test_apply_catalog_template_upgrade_updates_template_and_emits_outbox(self) -> None:
        session = _FakeSession()
        spu = ProductSpu(
            id="spu-1",
            category_id="cat-1",
            template_id="tpl-1",
            title="小米 15 Pro",
            status="ACTIVE",
            attr_snapshot_json={
                "spuId": "spu-1",
                "templateId": "tpl-1",
                "saleAttributeCodes": ["color", "memory_size"],
                "skus": [{"skuCode": "sku-1"}],
            },
        )
        target_template = CategoryAttrTemplate(
            id="tpl-3",
            category_id="cat-1",
            version=3,
            status="PUBLISHED",
        )
        session.spu_by_id[spu.id] = spu
        session.template_by_id[target_template.id] = target_template

        with patch(
            "goofish_insight.application.services.catalog_upgrade.preview_catalog_template_upgrade_with_session",
            return_value={
                "spuId": "spu-1",
                "currentTemplateId": "tpl-1",
                "targetTemplateId": "tpl-3",
                "targetSaleAttributeCodes": ["color", "memory_size"],
                "canAutoUpgrade": True,
            },
        ):
            result = apply_catalog_template_upgrade_with_session(
                session,
                spu_id="spu-1",
                target_template_id="tpl-3",
                operator_id="ops-bot",
                request_id="req-upgrade",
            )

        self.assertEqual(result["fromTemplateId"], "tpl-1")
        self.assertEqual(result["toTemplateId"], "tpl-3")
        self.assertEqual(spu.template_id, "tpl-3")
        self.assertEqual(spu.attr_snapshot_json["templateId"], "tpl-3")
        added_types = [type(obj) for obj in session.added]
        self.assertIn(OutboxEvent, added_types)
        self.assertIn(ProductAttrAuditLog, added_types)

    def test_apply_catalog_template_upgrade_requires_auto_upgrade(self) -> None:
        with patch(
            "goofish_insight.application.services.catalog_upgrade.preview_catalog_template_upgrade_with_session",
            return_value={
                "spuId": "spu-1",
                "targetTemplateId": "tpl-2",
                "targetSaleAttributeCodes": ["color"],
                "canAutoUpgrade": False,
            },
        ):
            with self.assertRaises(CatalogTemplateUpgradeApplyError):
                apply_catalog_template_upgrade_with_session(
                    _FakeSession(),
                    spu_id="spu-1",
                    target_template_id="tpl-2",
                    operator_id="ops-bot",
                )

    def test_preview_catalog_template_replace_plan_moves_sale_attribute_to_attribute_bucket(self) -> None:
        current_spu_detail = {
            "spu": {
                "id": "spu-1",
                "categoryId": "cat-1",
                "templateId": "tpl-1",
                "merchantId": "merchant-1",
                "brandId": "brand-1",
                "title": "小米 15 Pro",
                "status": "ACTIVE",
            },
            "spuAttributes": [
                {"attributeCode": "screen_size", "numberValue": 6.73, "normalizedNumberValue": 6.73},
            ],
            "skus": [
                {
                    "skuCode": "sku-1",
                    "price": 4999,
                    "stock": 50,
                    "barcode": "6901",
                    "status": "ACTIVE",
                    "attributes": [
                        {
                            "attributeCode": "color",
                            "optionId": "opt-black",
                            "optionCode": "black",
                            "optionName": "黑色",
                        },
                        {
                            "attributeCode": "memory_size",
                            "optionId": "opt-12",
                            "optionCode": "12",
                            "optionName": "12GB",
                        },
                    ],
                }
            ],
        }
        current_template = {
            "category": {"id": "cat-1"},
            "template": {"id": "tpl-1", "version": 1},
            "items": [
                {"attributeCode": "color", "valueScope": "SKU", "isRequired": True, "isSale": True},
                {"attributeCode": "memory_size", "valueScope": "SKU", "isRequired": True, "isSale": True},
                {"attributeCode": "screen_size", "valueScope": "SPU", "isRequired": False, "isSale": False},
            ],
        }
        target_template = {
            "category": {"id": "cat-1"},
            "template": {"id": "tpl-2", "version": 2},
            "items": [
                {"attributeCode": "color", "valueScope": "SKU", "isRequired": True, "isSale": True},
                {"attributeCode": "memory_size", "valueScope": "SKU", "isRequired": True, "isSale": False},
                {"attributeCode": "screen_size", "valueScope": "SPU", "isRequired": True, "isSale": False},
            ],
        }

        with (
            patch(
                "goofish_insight.application.services.catalog_upgrade.build_catalog_spu_detail",
                return_value=current_spu_detail,
            ),
            patch(
                "goofish_insight.application.services.catalog_upgrade.build_catalog_template_detail",
                side_effect=[current_template, target_template, current_template, target_template],
            ),
        ):
            result = preview_catalog_template_replace_plan_with_session(
                object(),
                spu_id="spu-1",
                target_template_id="tpl-2",
            )

        self.assertTrue(result["readyForReplace"])
        sku_payload = result["replacePayload"]["skus"][0]
        self.assertEqual([row["attributeCode"] for row in sku_payload["saleAttributes"]], ["color"])
        self.assertEqual([row["attributeCode"] for row in sku_payload["attributes"]], ["memory_size"])

    def test_preview_catalog_template_replace_plan_detects_ambiguous_scope_change(self) -> None:
        current_spu_detail = {
            "spu": {
                "id": "spu-1",
                "categoryId": "cat-1",
                "templateId": "tpl-1",
                "merchantId": "merchant-1",
                "brandId": "brand-1",
                "title": "小米 15 Pro",
                "status": "ACTIVE",
            },
            "spuAttributes": [],
            "skus": [
                {
                    "skuCode": "sku-1",
                    "price": 4999,
                    "stock": 50,
                    "status": "ACTIVE",
                    "attributes": [{"attributeCode": "memory_size", "optionCode": "12", "optionId": "opt-12"}],
                },
                {
                    "skuCode": "sku-2",
                    "price": 5499,
                    "stock": 30,
                    "status": "ACTIVE",
                    "attributes": [{"attributeCode": "memory_size", "optionCode": "16", "optionId": "opt-16"}],
                },
            ],
        }
        current_template = {
            "category": {"id": "cat-1"},
            "template": {"id": "tpl-1", "version": 1},
            "items": [
                {"attributeCode": "memory_size", "valueScope": "SKU", "isRequired": True, "isSale": False},
            ],
        }
        target_template = {
            "category": {"id": "cat-1"},
            "template": {"id": "tpl-2", "version": 2},
            "items": [
                {"attributeCode": "memory_size", "valueScope": "SPU", "isRequired": True, "isSale": False},
            ],
        }

        with (
            patch(
                "goofish_insight.application.services.catalog_upgrade.build_catalog_spu_detail",
                return_value=current_spu_detail,
            ),
            patch(
                "goofish_insight.application.services.catalog_upgrade.build_catalog_template_detail",
                side_effect=[current_template, target_template, current_template, target_template],
            ),
        ):
            result = preview_catalog_template_replace_plan_with_session(
                object(),
                spu_id="spu-1",
                target_template_id="tpl-2",
            )

        self.assertFalse(result["readyForReplace"])
        self.assertEqual(result["ambiguousScopeChangeAttributeCodes"]["memory_size"], ["sku-1", "sku-2"])

    def test_apply_catalog_template_replace_plan_invokes_replace_persistence(self) -> None:
        with (
            patch(
                "goofish_insight.application.services.catalog_upgrade.preview_catalog_template_replace_plan_with_session",
                return_value={
                    "preview": {"canAutoUpgrade": False},
                    "replacePayload": {
                        "requestId": None,
                        "spu": {"id": "spu-1", "templateId": "tpl-2"},
                        "spuAttributes": [],
                        "skus": [],
                    },
                    "autofilledSpuAttributeCodes": [],
                    "autofilledSkuAttributeCodes": [],
                    "ambiguousScopeChangeAttributeCodes": {},
                    "readyForReplace": True,
                },
            ),
            patch(
                "goofish_insight.application.services.catalog_upgrade.replace_catalog_payload_with_session",
                return_value={"spuId": "spu-1", "skuCount": 1},
            ) as replace_mock,
        ):
            result = apply_catalog_template_replace_plan_with_session(
                object(),
                spu_id="spu-1",
                target_template_id="tpl-2",
                operator_id="ops-bot",
                request_id="req-replace-plan",
            )

        self.assertEqual(result["replaceResult"]["spuId"], "spu-1")
        replace_mock.assert_called_once()
        self.assertEqual(replace_mock.call_args.kwargs["payload"]["requestId"], "req-replace-plan")

    def test_apply_catalog_template_replace_plan_requires_ready_plan(self) -> None:
        with patch(
            "goofish_insight.application.services.catalog_upgrade.preview_catalog_template_replace_plan_with_session",
            return_value={
                "replacePayload": {},
                "preview": {},
                "autofilledSpuAttributeCodes": [],
                "autofilledSkuAttributeCodes": [],
                "ambiguousScopeChangeAttributeCodes": {"memory_size": ["sku-1"]},
                "readyForReplace": False,
            },
        ):
            with self.assertRaises(CatalogTemplateReplaceApplyError):
                apply_catalog_template_replace_plan_with_session(
                    object(),
                    spu_id="spu-1",
                    target_template_id="tpl-2",
                    operator_id="ops-bot",
                )


if __name__ == "__main__":
    unittest.main()
