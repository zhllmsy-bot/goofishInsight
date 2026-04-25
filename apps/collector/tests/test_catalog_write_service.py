import unittest

from goofish_insight.application.services.catalog_write import prepare_catalog_persist_plan


class CatalogWriteServiceTests(unittest.TestCase):
    def test_prepare_catalog_persist_plan_builds_rows_and_outbox(self) -> None:
        plan = prepare_catalog_persist_plan(
            {
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
                    {"code": "color", "name": "颜色", "dataType": "ENUM", "isMulti": False},
                    {"code": "memory_size", "name": "内存", "dataType": "ENUM", "isMulti": False},
                    {"code": "screen_size", "name": "屏幕尺寸", "dataType": "NUMBER", "isMulti": False},
                ],
                "spuAttributes": [
                    {"attributeCode": "screen_size", "numberValue": 6.36, "unit": "inch"}
                ],
                "skus": [
                    {
                        "skuCode": "MI15-BLK-12G",
                        "price": 4599,
                        "stock": 100,
                        "barcode": "690000000001",
                        "status": "ACTIVE",
                        "saleAttributes": [
                            {"attributeCode": "memory_size", "optionCode": "12", "optionName": "12GB"},
                            {"attributeCode": "color", "optionCode": "black", "optionName": "黑色"},
                        ],
                    }
                ],
            }
        )

        self.assertEqual(plan["spuRow"]["categoryId"], "cat-phone")
        self.assertEqual(plan["spuAttributeRows"][0]["attributeCode"], "screen_size")
        self.assertEqual(plan["skuRows"][0]["salesSignatureRaw"], "attr-color:black|attr-memory:12")
        self.assertEqual(plan["skuAttributeRows"][0]["skuCode"], "MI15-BLK-12G")
        self.assertEqual(plan["outboxEvent"]["payload"]["skuCount"], 1)


if __name__ == "__main__":
    unittest.main()
