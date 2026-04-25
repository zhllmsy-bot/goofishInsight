from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CatalogBackfillBlueprint:
    business_domain: str
    category_id: str
    category_code: str
    category_name: str
    category_path: str
    category_level: int
    template_id: str
    template_version: int
    attributes: list[dict[str, Any]]
    template_items: list[dict[str, Any]]


BACKFILL_BLUEPRINTS: dict[str, CatalogBackfillBlueprint] = {
    "garmin": CatalogBackfillBlueprint(
        business_domain="garmin",
        category_id="22222222-2222-2222-2222-222222222101",
        category_code="garmin_watch",
        category_name="Garmin手表",
        category_path="wearables/garmin-watch",
        category_level=2,
        template_id="22222222-2222-2222-2222-222222222401",
        template_version=1,
        attributes=[
            {
                "code": "product_line",
                "name": "产品线",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "isMulti": False,
            },
            {
                "code": "model_name",
                "name": "型号",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "isMulti": False,
            },
            {
                "code": "generation",
                "name": "代际",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "isMulti": False,
            },
            {
                "code": "display_type",
                "name": "屏幕类型",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "isMulti": False,
            },
            {
                "code": "case_size_mm",
                "name": "表盘尺寸",
                "dataType": "NUMBER",
                "valueScope": "SPU",
                "isMulti": False,
                "unit": "mm",
            },
            {
                "code": "is_solar",
                "name": "是否太阳能",
                "dataType": "BOOLEAN",
                "valueScope": "SPU",
                "isMulti": False,
            },
            {
                "code": "edition_tags",
                "name": "版本标签",
                "dataType": "JSON",
                "valueScope": "SPU",
                "isMulti": True,
            },
        ],
        template_items=[
            {"attributeCode": "product_line", "sortNo": 10},
            {"attributeCode": "model_name", "sortNo": 20},
            {"attributeCode": "generation", "sortNo": 30},
            {"attributeCode": "display_type", "sortNo": 40},
            {"attributeCode": "case_size_mm", "sortNo": 50},
            {"attributeCode": "is_solar", "sortNo": 60},
            {"attributeCode": "edition_tags", "sortNo": 70},
        ],
    ),
    "apple_m_series": CatalogBackfillBlueprint(
        business_domain="apple_m_series",
        category_id="33333333-3333-3333-3333-333333333101",
        category_code="apple_computer",
        category_name="Apple电脑",
        category_path="computers/apple-computer",
        category_level=2,
        template_id="33333333-3333-3333-3333-333333333401",
        template_version=1,
        attributes=[
            {
                "code": "product_line",
                "name": "产品线",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "isMulti": False,
            },
            {
                "code": "model_name",
                "name": "型号",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "isMulti": False,
            },
            {
                "code": "chip_family",
                "name": "芯片系列",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "isMulti": False,
            },
            {
                "code": "screen_size_in",
                "name": "屏幕尺寸",
                "dataType": "NUMBER",
                "valueScope": "SPU",
                "isMulti": False,
                "unit": "inch",
            },
            {
                "code": "cpu_cores",
                "name": "CPU 核心数",
                "dataType": "NUMBER",
                "valueScope": "SPU",
                "isMulti": False,
            },
            {
                "code": "gpu_cores",
                "name": "GPU 核心数",
                "dataType": "NUMBER",
                "valueScope": "SPU",
                "isMulti": False,
            },
            {
                "code": "memory_gb",
                "name": "内存",
                "dataType": "NUMBER",
                "valueScope": "SKU",
                "isMulti": False,
                "unit": "GB",
            },
            {
                "code": "storage_gb",
                "name": "存储",
                "dataType": "NUMBER",
                "valueScope": "SKU",
                "isMulti": False,
                "unit": "GB",
            },
        ],
        template_items=[
            {"attributeCode": "product_line", "sortNo": 10},
            {"attributeCode": "model_name", "sortNo": 20},
            {"attributeCode": "chip_family", "sortNo": 30},
            {"attributeCode": "screen_size_in", "sortNo": 40},
            {"attributeCode": "cpu_cores", "sortNo": 50},
            {"attributeCode": "gpu_cores", "sortNo": 60},
            {"attributeCode": "memory_gb", "sortNo": 70},
            {"attributeCode": "storage_gb", "sortNo": 80},
        ],
    ),
}


def get_catalog_backfill_blueprint(business_domain: str) -> CatalogBackfillBlueprint | None:
    return BACKFILL_BLUEPRINTS.get(str(business_domain).strip())


def build_blueprint_template_detail(blueprint: CatalogBackfillBlueprint) -> dict[str, Any]:
    attribute_map = {str(attribute["code"]): dict(attribute) for attribute in blueprint.attributes}
    items: list[dict[str, Any]] = []
    for template_item in blueprint.template_items:
        attribute_code = str(template_item["attributeCode"])
        attribute = attribute_map[attribute_code]
        options = [
            {
                "optionId": option.get("id"),
                "optionCode": option["optionCode"],
                "optionName": option["optionName"],
                "sortNo": int(option.get("sortNo", 0)),
                "status": str(option.get("status", "ACTIVE")),
            }
            for option in list(attribute.get("options") or [])
        ]
        items.append(
            {
                "attributeCode": attribute_code,
                "attributeId": attribute.get("id"),
                "attributeName": attribute["name"],
                "dataType": attribute["dataType"],
                "valueScope": attribute["valueScope"],
                "isMulti": bool(attribute.get("isMulti", False)),
                "isRequired": bool(template_item.get("isRequired", False)),
                "isSale": bool(template_item.get("isSale", False)),
                "isFilter": bool(template_item.get("isFilter", True)),
                "isSearch": bool(template_item.get("isSearch", True)),
                "isDisplay": bool(template_item.get("isDisplay", True)),
                "sortNo": int(template_item.get("sortNo", 0)),
                "unit": attribute.get("unit"),
                "options": options,
            }
        )
    items.sort(key=lambda row: (int(row["sortNo"]), str(row["attributeCode"])))
    return {
        "category": {
            "id": blueprint.category_id,
            "code": blueprint.category_code,
            "name": blueprint.category_name,
            "path": blueprint.category_path,
            "level": blueprint.category_level,
            "status": "ACTIVE",
        },
        "template": {
            "id": blueprint.template_id,
            "categoryId": blueprint.category_id,
            "version": blueprint.template_version,
            "status": "PUBLISHED",
            "effectiveAt": None,
            "publishedBy": "catalog-backfill",
            "createdAt": None,
            "updatedAt": None,
        },
        "items": items,
    }
