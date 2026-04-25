import unittest

from goofish_insight.domain.catalog.contracts import (
    build_product_snapshot,
    build_sales_signature,
    ensure_single_value_column,
    validate_sale_selections,
)


TEMPLATE_ITEMS = [
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
]

ATTRIBUTES = [
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
]


class CatalogContractTests(unittest.TestCase):
    def test_build_sales_signature_uses_template_order(self) -> None:
        first = build_sales_signature(
            template_items=TEMPLATE_ITEMS,
            attributes=ATTRIBUTES,
            selections=[
                {"attributeCode": "memory_size", "optionId": "opt-12"},
                {"attributeCode": "color", "optionId": "opt-black"},
            ],
        )
        second = build_sales_signature(
            template_items=TEMPLATE_ITEMS,
            attributes=ATTRIBUTES,
            selections=[
                {"attributeCode": "color", "optionId": "opt-black"},
                {"attributeCode": "memory_size", "optionId": "opt-12"},
            ],
        )
        self.assertEqual(first["raw"], "attr-color:opt-black|attr-memory:opt-12")
        self.assertEqual(first["raw"], second["raw"])
        self.assertEqual(first["hash"], second["hash"])

    def test_validate_sale_selections_rejects_missing_attribute(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError, "Missing required sale attribute: memory_size"
        ):
            validate_sale_selections(
                template_items=TEMPLATE_ITEMS,
                attributes=ATTRIBUTES,
                selections=[{"attributeCode": "color", "optionId": "opt-black"}],
            )

    def test_validate_sale_selections_rejects_duplicates(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Duplicate sale attribute: color"):
            validate_sale_selections(
                template_items=TEMPLATE_ITEMS,
                attributes=ATTRIBUTES,
                selections=[
                    {"attributeCode": "color", "optionId": "opt-black"},
                    {"attributeCode": "color", "optionId": "opt-white"},
                    {"attributeCode": "memory_size", "optionId": "opt-12"},
                ],
            )

    def test_ensure_single_value_column_rejects_multiple_values(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError, "must provide exactly one value column"
        ):
            ensure_single_value_column(
                {
                    "attributeCode": "screen_size",
                    "numberValue": 6.36,
                    "textValue": "6.36 英寸",
                }
            )

    def test_build_product_snapshot_returns_normalized_payload(self) -> None:
        snapshot = build_product_snapshot(
            spu={
                "id": "spu-1",
                "categoryId": "cat-phone",
                "templateId": "tpl-phone-v1",
                "title": "小米 15",
                "status": "ACTIVE",
            },
            template_items=TEMPLATE_ITEMS,
            attributes=ATTRIBUTES,
            spu_attributes=[
                {
                    "attributeCode": "screen_size",
                    "numberValue": 6.36,
                    "unit": "inch",
                }
            ],
            skus=[
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
        )

        self.assertEqual(snapshot["spuId"], "spu-1")
        self.assertEqual(snapshot["saleAttributeCodes"], ["color", "memory_size"])
        self.assertEqual(snapshot["attributes"][0]["attributeCode"], "screen_size")
        self.assertEqual(
            snapshot["skus"][0]["salesSignatureRaw"], "attr-color:black|attr-memory:12"
        )
        self.assertEqual(snapshot["skus"][0]["saleAttributes"][0]["attributeName"], "内存")


if __name__ == "__main__":
    unittest.main()
