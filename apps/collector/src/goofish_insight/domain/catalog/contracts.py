from __future__ import annotations

from hashlib import sha256
from typing import Any


def _by_template_order(item: dict[str, Any]) -> tuple[int, str]:
    return (int(item.get("sortNo") or 0), str(item["attributeCode"]))


def _attribute_map(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["code"]): item for item in items}


def ensure_single_value_column(value: dict[str, Any]) -> None:
    populated = sum(
        int(value.get(key) is not None)
        for key in ("textValue", "numberValue", "boolValue", "jsonValue")
    )
    if value.get("optionCode") is not None or value.get("optionId") is not None:
        populated += 1
    if populated != 1:
        raise RuntimeError(
            f"Attribute {value['attributeCode']} must provide exactly one value column"
        )


def validate_sale_selections(
    *,
    template_items: list[dict[str, Any]],
    attributes: list[dict[str, Any]],
    selections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    attribute_map = _attribute_map(attributes)
    sale_template_items = sorted(
        (item for item in template_items if item.get("isSale")),
        key=_by_template_order,
    )
    seen: dict[str, dict[str, Any]] = {}

    for selection in selections:
        attribute_code = str(selection["attributeCode"])
        if attribute_code in seen:
            raise RuntimeError(f"Duplicate sale attribute: {attribute_code}")
        seen[attribute_code] = selection

    for template_item in sale_template_items:
        attribute_code = str(template_item["attributeCode"])
        selection = seen.get(attribute_code)
        if selection is None:
            raise RuntimeError(f"Missing required sale attribute: {attribute_code}")

        attribute = attribute_map.get(attribute_code)
        if attribute is None:
            raise RuntimeError(f"Missing attribute definition: {attribute_code}")
        if str(attribute.get("dataType")) != "ENUM":
            raise RuntimeError(f"Sale attribute must be ENUM: {attribute_code}")
        if bool(attribute.get("isMulti")):
            raise RuntimeError(f"Sale attribute cannot be multi-value: {attribute_code}")
        if not selection.get("optionCode") and not selection.get("optionId"):
            raise RuntimeError(f"Sale attribute requires option token: {attribute_code}")

    sale_attribute_codes = {str(item["attributeCode"]) for item in sale_template_items}
    for selection in selections:
        attribute_code = str(selection["attributeCode"])
        if attribute_code not in sale_attribute_codes:
            raise RuntimeError(f"Unexpected sale attribute: {attribute_code}")

    return sale_template_items


def build_sales_signature(
    *,
    template_items: list[dict[str, Any]],
    attributes: list[dict[str, Any]],
    selections: list[dict[str, Any]],
) -> dict[str, str]:
    sale_template_items = validate_sale_selections(
        template_items=template_items,
        attributes=attributes,
        selections=selections,
    )
    selection_map = {str(item["attributeCode"]): item for item in selections}

    parts: list[str] = []
    for item in sale_template_items:
        selection = selection_map[str(item["attributeCode"])]
        attribute_token = (
            selection.get("attributeId") or item.get("attributeId") or item["attributeCode"]
        )
        option_token = selection.get("optionId") or selection.get("optionCode")
        parts.append(f"{attribute_token}:{option_token}")

    raw = "|".join(parts)
    hashed = sha256(raw.encode("utf-8")).hexdigest()
    return {"raw": raw, "hash": hashed}


def normalize_attribute_value(value: dict[str, Any]) -> dict[str, Any]:
    ensure_single_value_column(value)

    if value.get("optionId") is not None or value.get("optionCode") is not None:
        return {
            "attributeCode": value["attributeCode"],
            "valueType": "ENUM",
            "optionId": value.get("optionId"),
            "optionCode": value.get("optionCode"),
            "optionName": value.get("optionName"),
        }

    if value.get("textValue") is not None:
        return {
            "attributeCode": value["attributeCode"],
            "valueType": "TEXT",
            "value": value["textValue"],
        }

    if value.get("numberValue") is not None:
        return {
            "attributeCode": value["attributeCode"],
            "valueType": "NUMBER",
            "value": value["numberValue"],
            "normalizedValue": value.get("normalizedNumberValue", value["numberValue"]),
            "unit": value.get("unit"),
        }

    if value.get("boolValue") is not None:
        return {
            "attributeCode": value["attributeCode"],
            "valueType": "BOOLEAN",
            "value": value["boolValue"],
        }

    return {
        "attributeCode": value["attributeCode"],
        "valueType": "JSON",
        "value": value["jsonValue"],
    }


def build_product_snapshot(
    *,
    spu: dict[str, Any],
    template_items: list[dict[str, Any]],
    attributes: list[dict[str, Any]],
    spu_attributes: list[dict[str, Any]],
    skus: list[dict[str, Any]],
) -> dict[str, Any]:
    attribute_map = _attribute_map(attributes)
    sale_attribute_codes = sorted(
        {str(item["attributeCode"]) for item in template_items if item.get("isSale")},
        key=lambda code: next(
            _by_template_order(item)
            for item in template_items
            if item["attributeCode"] == code
        ),
    )

    normalized_skus: list[dict[str, Any]] = []
    for sku in skus:
        signature = build_sales_signature(
            template_items=template_items,
            attributes=attributes,
            selections=list(sku.get("saleAttributes") or []),
        )
        normalized_skus.append(
            {
                "skuCode": sku["skuCode"],
                "price": sku["price"],
                "stock": sku["stock"],
                "status": sku.get("status", "DRAFT"),
                "salesSignatureRaw": signature["raw"],
                "salesSignatureHash": signature["hash"],
                "saleAttributes": [
                    {
                        "attributeCode": value["attributeCode"],
                        "attributeName": attribute_map.get(str(value["attributeCode"]), {}).get(
                            "name",
                            value["attributeCode"],
                        ),
                        "optionCode": value.get("optionCode"),
                        "optionId": value.get("optionId"),
                        "optionName": value.get("optionName"),
                    }
                    for value in list(sku.get("saleAttributes") or [])
                ],
                "attributes": [
                    normalize_attribute_value(value)
                    for value in list(sku.get("attributes") or [])
                ],
            }
        )

    return {
        "spuId": spu.get("id"),
        "categoryId": spu["categoryId"],
        "templateId": spu["templateId"],
        "title": spu["title"],
        "status": spu.get("status", "DRAFT"),
        "saleAttributeCodes": sale_attribute_codes,
        "attributes": [normalize_attribute_value(value) for value in spu_attributes],
        "skus": normalized_skus,
    }
