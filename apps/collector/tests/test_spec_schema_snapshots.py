from __future__ import annotations

import unittest

from goofish_insight.application.services.spec_schema_snapshots import (
    derive_spec_schema_from_template,
    evaluate_pricing_record_schema,
    template_item_schema_payload_from_input,
)
from goofish_insight.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeScopeType,
    AttributeStatus,
    Category,
    CategoryAttrTemplate,
    CategoryAttrTemplateItem,
    TemplateStatus,
)


class SpecSchemaSnapshotServiceTests(unittest.TestCase):
    def test_derive_schema_groups_template_items_by_role(self) -> None:
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        template = CategoryAttrTemplate(
            id="tpl-apple-v3",
            category_id="cat-apple",
            version=3,
            status=TemplateStatus.PUBLISHED,
        )
        template.category = category
        attrs = {
            "chip_family": _attribute("attr-chip", "chip_family", "芯片系列"),
            "memory_gb": _attribute("attr-memory", "memory_gb", "内存"),
            "color": _attribute("attr-color", "color", "颜色"),
            "condition_grade": _attribute("attr-condition", "condition_grade", "成色"),
        }
        template.items = [
            _template_item(template, attrs["chip_family"], role="locking", required=True, weight=0.25, sort_no=10),
            _template_item(template, attrs["memory_gb"], role="locking", required=True, weight=0.15, sort_no=20),
            _template_item(template, attrs["color"], role="variant", required=False, weight=0, sort_no=30),
            _template_item(template, attrs["condition_grade"], role="condition", required=False, weight=0, sort_no=40),
        ]

        schema = derive_spec_schema_from_template(
            template,
            persisted=False,
            created_by="ops-bot",
            valid_from=None,
        )

        self.assertEqual(schema["categoryCode"], "apple_computer")
        self.assertEqual(schema["templateVersion"], 3)
        self.assertEqual(schema["lockingAttrs"], ["chip_family", "memory_gb"])
        self.assertEqual(schema["requiredAttrs"], ["chip_family", "memory_gb"])
        self.assertEqual(schema["variantAttrs"], ["color"])
        self.assertEqual(schema["conditionAttrs"], ["condition_grade"])
        self.assertEqual(schema["weights"], {"chip_family": 0.25, "memory_gb": 0.15})
        self.assertEqual(schema["summary"]["lockingAttrCount"], 2)

    def test_evaluate_pricing_record_schema_marks_missing_required_attrs(self) -> None:
        schema = {
            "schemaId": 42,
            "templateVersion": 3,
            "lockingAttrs": ["model_name", "chip_family", "memory_gb", "storage_gb"],
            "requiredAttrs": ["model_name", "chip_family", "memory_gb", "storage_gb"],
        }

        result = evaluate_pricing_record_schema(
            record={
                "product_label": "MacBook Pro / M4",
                "chip_family": "M4",
                "memory_gb": 36,
            },
            schema=schema,
        )

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["schemaId"], 42)
        self.assertEqual(result["missingRequiredAttrs"], ["storage_gb"])

    def test_template_item_schema_payload_rejects_invalid_role(self) -> None:
        with self.assertRaises(Exception):
            template_item_schema_payload_from_input({"attributeCode": "memory_gb", "role": "core"})


def _attribute(attr_id: str, code: str, name: str) -> AttributeDefinition:
    return AttributeDefinition(
        id=attr_id,
        scope_type=AttributeScopeType.PLATFORM,
        scope_id="platform",
        code=code,
        name=name,
        data_type=AttributeDataType.TEXT,
        value_scope="SKU",
        status=AttributeStatus.ACTIVE,
    )


def _template_item(
    template: CategoryAttrTemplate,
    attribute: AttributeDefinition,
    *,
    role: str,
    required: bool,
    weight: float,
    sort_no: int,
) -> CategoryAttrTemplateItem:
    item = CategoryAttrTemplateItem(
        id=f"item-{attribute.code}",
        template_id=template.id,
        attribute_id=attribute.id,
        is_required=required,
        is_sale=False,
        role=role,
        weight=weight,
        sort_no=sort_no,
    )
    item.template = template
    item.attribute = attribute
    return item


if __name__ == "__main__":
    unittest.main()
