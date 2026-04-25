from __future__ import annotations

from collections import defaultdict
from typing import Any

from .catalog_preview import preview_catalog_snapshot


def _attribute_rows(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counters: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []

    for value in values:
        attribute_code = str(value["attributeCode"])
        value_seq = counters[attribute_code]
        counters[attribute_code] += 1
        rows.append(
            {
                "attributeCode": attribute_code,
                "valueSeq": value_seq,
                "textValue": value.get("textValue"),
                "numberValue": value.get("numberValue"),
                "normalizedNumberValue": value.get("normalizedNumberValue"),
                "boolValue": value.get("boolValue"),
                "optionId": value.get("optionId"),
                "optionCode": value.get("optionCode"),
                "optionName": value.get("optionName"),
                "jsonValue": value.get("jsonValue"),
                "unit": value.get("unit"),
            }
        )
    return rows


def prepare_catalog_persist_plan(payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = preview_catalog_snapshot(payload)
    spu = dict(payload.get("spu") or {})
    skus = list(payload.get("skus") or [])
    spu_attributes = list(payload.get("spuAttributes") or [])

    sku_rows: list[dict[str, Any]] = []
    sku_attribute_rows: list[dict[str, Any]] = []

    snapshot_sku_map = {row["skuCode"]: row for row in snapshot["skus"]}

    for sku in skus:
        snapshot_row = snapshot_sku_map[sku["skuCode"]]
        sku_rows.append(
            {
                "skuCode": sku["skuCode"],
                "price": sku["price"],
                "stock": sku["stock"],
                "status": sku.get("status", "DRAFT"),
                "barcode": sku.get("barcode"),
                "salesSignatureRaw": snapshot_row["salesSignatureRaw"],
                "salesSignatureHash": snapshot_row["salesSignatureHash"],
                "attrSnapshotJson": snapshot_row,
            }
        )
        for row in _attribute_rows(
            list(sku.get("saleAttributes") or []) + list(sku.get("attributes") or [])
        ):
            sku_attribute_rows.append(
                {
                    "skuCode": sku["skuCode"],
                    **row,
                }
            )

    return {
        "requestId": payload.get("requestId"),
        "spuRow": {
            "categoryId": spu["categoryId"],
            "templateId": spu["templateId"],
            "merchantId": spu.get("merchantId"),
            "brandId": spu.get("brandId"),
            "title": spu["title"],
            "status": spu.get("status", "DRAFT"),
            "attrSnapshotJson": snapshot,
        },
        "spuAttributeRows": _attribute_rows(spu_attributes),
        "skuRows": sku_rows,
        "skuAttributeRows": sku_attribute_rows,
        "outboxEvent": {
            "eventType": "catalog.product_spu_changed",
            "aggregateType": "product_spu",
            "aggregateKey": spu.get("id") or spu["title"],
            "eventVersion": 1,
            "payload": {
                "requestId": payload.get("requestId"),
                "categoryId": spu["categoryId"],
                "templateId": spu["templateId"],
                "skuCount": len(sku_rows),
                "salesSignatures": [row["salesSignatureHash"] for row in sku_rows],
            },
        },
    }
