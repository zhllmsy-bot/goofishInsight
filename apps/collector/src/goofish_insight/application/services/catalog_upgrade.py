from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...db import session_scope
from ...models import CategoryAttrTemplate, OutboxEvent, ProductAttrAuditLog, ProductSpu
from .catalog_outbox import CATALOG_OUTBOX_AGGREGATE_TYPE, CATALOG_OUTBOX_EVENT_TYPE
from .catalog_persistence import replace_catalog_payload_with_session
from .catalog_queries import build_catalog_spu_detail, build_catalog_template_detail


class CatalogTemplateUpgradePreviewError(RuntimeError):
    pass


class CatalogTemplateUpgradeApplyError(RuntimeError):
    pass


class CatalogTemplateReplacePlanError(RuntimeError):
    pass


class CatalogTemplateReplaceApplyError(RuntimeError):
    pass


def preview_catalog_template_upgrade(
    *,
    spu_id: str,
    target_template_id: str,
) -> dict[str, Any]:
    with session_scope() as session:
        return preview_catalog_template_upgrade_with_session(
            session,
            spu_id=spu_id,
            target_template_id=target_template_id,
        )


def preview_catalog_template_upgrade_with_session(
    session: Session,
    *,
    spu_id: str,
    target_template_id: str,
) -> dict[str, Any]:
    spu_detail = build_catalog_spu_detail(session, spu_id)
    if spu_detail is None:
        raise CatalogTemplateUpgradePreviewError(f"SPU not found: {spu_id}")

    current_template_id = str(spu_detail["spu"]["templateId"])
    current_template = build_catalog_template_detail(session, current_template_id)
    if current_template is None:
        raise CatalogTemplateUpgradePreviewError(
            f"Current template not found for SPU {spu_id}: {current_template_id}"
        )

    target_template = build_catalog_template_detail(session, target_template_id)
    if target_template is None:
        raise CatalogTemplateUpgradePreviewError(f"Target template not found: {target_template_id}")
    if str(target_template["category"]["id"]) != str(spu_detail["spu"]["categoryId"]):
        raise CatalogTemplateUpgradePreviewError(
            f"Target template {target_template_id} does not belong to SPU category {spu_detail['spu']['categoryId']}"
        )

    current_template_items = list(current_template["items"])
    target_template_items = list(target_template["items"])

    current_sale_codes = sorted(
        item["attributeCode"] for item in current_template_items if item["isSale"]
    )
    target_sale_codes = sorted(
        item["attributeCode"] for item in target_template_items if item["isSale"]
    )

    current_item_map = {item["attributeCode"]: item for item in current_template_items}
    target_item_map = {item["attributeCode"]: item for item in target_template_items}

    current_template_codes = sorted(current_item_map)
    target_template_codes = sorted(target_item_map)

    spu_attribute_codes = {
        row["attributeCode"] for row in list(spu_detail["spuAttributes"])
    }
    sku_rows = list(spu_detail["skus"])
    sku_attribute_codes = {
        sku["skuCode"]: {row["attributeCode"] for row in list(sku["attributes"])}
        for sku in sku_rows
    }

    missing_required_spu_codes: list[str] = []
    missing_required_sku_codes: dict[str, list[str]] = {}

    for item in target_template_items:
        attribute_code = item["attributeCode"]
        if not item["isRequired"]:
            continue
        if item["valueScope"] == "SPU":
            if attribute_code not in spu_attribute_codes:
                missing_required_spu_codes.append(attribute_code)
            continue

        missing_for_skus = [
            sku["skuCode"]
            for sku in sku_rows
            if attribute_code not in sku_attribute_codes.get(sku["skuCode"], set())
        ]
        if missing_for_skus:
            missing_required_sku_codes[attribute_code] = missing_for_skus

    added_sale_codes = sorted(set(target_sale_codes) - set(current_sale_codes))
    removed_sale_codes = sorted(set(current_sale_codes) - set(target_sale_codes))
    added_template_codes = sorted(set(target_template_codes) - set(current_template_codes))
    removed_template_codes = sorted(set(current_template_codes) - set(target_template_codes))

    sale_scope_changes = {
        code: {
            "fromIsSale": current_item_map[code]["isSale"],
            "toIsSale": target_item_map[code]["isSale"],
        }
        for code in sorted(set(current_item_map) & set(target_item_map))
        if current_item_map[code]["isSale"] != target_item_map[code]["isSale"]
    }

    requires_sku_payload_rewrite = bool(added_sale_codes or removed_sale_codes)
    can_auto_upgrade = (
        not missing_required_spu_codes
        and not missing_required_sku_codes
        and not requires_sku_payload_rewrite
    )

    return {
        "spuId": spu_id,
        "currentCategoryId": spu_detail["spu"]["categoryId"],
        "targetCategoryId": target_template["category"]["id"],
        "currentTemplateId": current_template_id,
        "currentTemplateVersion": current_template["template"]["version"],
        "targetTemplateId": target_template_id,
        "targetTemplateVersion": target_template["template"]["version"],
        "currentSaleAttributeCodes": current_sale_codes,
        "targetSaleAttributeCodes": target_sale_codes,
        "addedSaleAttributeCodes": added_sale_codes,
        "removedSaleAttributeCodes": removed_sale_codes,
        "addedTemplateAttributeCodes": added_template_codes,
        "removedTemplateAttributeCodes": removed_template_codes,
        "saleScopeChanges": sale_scope_changes,
        "missingRequiredSpuAttributeCodes": sorted(missing_required_spu_codes),
        "missingRequiredSkuAttributeCodes": missing_required_sku_codes,
        "skuCount": len(sku_rows),
        "requiresSkuPayloadRewrite": requires_sku_payload_rewrite,
        "canAutoUpgrade": can_auto_upgrade,
    }


def preview_catalog_template_replace_plan(
    *,
    spu_id: str,
    target_template_id: str,
) -> dict[str, Any]:
    with session_scope() as session:
        return preview_catalog_template_replace_plan_with_session(
            session,
            spu_id=spu_id,
            target_template_id=target_template_id,
        )


def preview_catalog_template_replace_plan_with_session(
    session: Session,
    *,
    spu_id: str,
    target_template_id: str,
) -> dict[str, Any]:
    preview = preview_catalog_template_upgrade_with_session(
        session,
        spu_id=spu_id,
        target_template_id=target_template_id,
    )
    spu_detail = build_catalog_spu_detail(session, spu_id)
    if spu_detail is None:
        raise CatalogTemplateReplacePlanError(f"SPU not found: {spu_id}")

    current_template = build_catalog_template_detail(session, preview["currentTemplateId"])
    if current_template is None:
        raise CatalogTemplateReplacePlanError(f"Current template not found: {preview['currentTemplateId']}")
    target_template = build_catalog_template_detail(session, target_template_id)
    if target_template is None:
        raise CatalogTemplateReplacePlanError(f"Target template not found: {target_template_id}")

    current_item_map = {item["attributeCode"]: item for item in current_template["items"]}
    target_items = list(target_template["items"])
    spu_value_map = {row["attributeCode"]: row for row in list(spu_detail["spuAttributes"])}
    sku_value_maps = {
        sku["skuCode"]: {row["attributeCode"]: row for row in list(sku["attributes"])}
        for sku in list(spu_detail["skus"])
    }

    autofilled_spu_attribute_codes: list[str] = []
    autofilled_sku_attribute_codes: list[str] = []
    ambiguous_scope_change_attribute_codes: dict[str, list[str]] = {}

    replace_payload = {
        "requestId": None,
        "spu": {
            "id": spu_detail["spu"]["id"],
            "categoryId": spu_detail["spu"]["categoryId"],
            "templateId": target_template_id,
            "merchantId": spu_detail["spu"]["merchantId"],
            "brandId": spu_detail["spu"]["brandId"],
            "title": spu_detail["spu"]["title"],
            "status": spu_detail["spu"]["status"],
        },
        "spuAttributes": [],
        "skus": [],
    }

    missing_required_spu_codes: list[str] = []
    missing_required_sku_codes: dict[str, list[str]] = {}

    for item in target_items:
        attribute_code = item["attributeCode"]
        current_item = current_item_map.get(attribute_code)
        if item["valueScope"] == "SPU":
            value = spu_value_map.get(attribute_code)
            if value is None and current_item and current_item["valueScope"] == "SKU":
                resolved = _resolve_uniform_sku_value(
                    sku_value_maps=sku_value_maps,
                    attribute_code=attribute_code,
                )
                if resolved["status"] == "resolved":
                    value = resolved["value"]
                    autofilled_spu_attribute_codes.append(attribute_code)
                elif resolved["status"] == "ambiguous":
                    ambiguous_scope_change_attribute_codes[attribute_code] = resolved["skuCodes"]
            if value is not None:
                replace_payload["spuAttributes"].append(_detail_value_to_payload(value))
            elif item["isRequired"]:
                missing_required_spu_codes.append(attribute_code)
            continue

        if item["valueScope"] != "SKU":
            raise CatalogTemplateReplacePlanError(
                f"Unsupported target valueScope for attribute {attribute_code}: {item['valueScope']}"
            )

        for sku in list(spu_detail["skus"]):
            sku_code = sku["skuCode"]
            value = sku_value_maps.get(sku_code, {}).get(attribute_code)
            if value is None and current_item and current_item["valueScope"] == "SPU":
                current_spu_value = spu_value_map.get(attribute_code)
                if current_spu_value is not None:
                    value = current_spu_value
                    autofilled_sku_attribute_codes.append(attribute_code)

            if value is None:
                if item["isRequired"]:
                    missing_required_sku_codes.setdefault(attribute_code, []).append(sku_code)
                continue

            payload_value = _detail_value_to_payload(value)
            target_key = "saleAttributes" if item["isSale"] else "attributes"
            sku_payload = _ensure_replace_plan_sku(replace_payload["skus"], sku)
            sku_payload[target_key].append(payload_value)

    replace_payload["spuAttributes"].sort(key=lambda row: row["attributeCode"])
    for sku_payload in replace_payload["skus"]:
        sku_payload["saleAttributes"].sort(key=lambda row: row["attributeCode"])
        sku_payload["attributes"].sort(key=lambda row: row["attributeCode"])

    ready_for_replace = (
        not missing_required_spu_codes
        and not missing_required_sku_codes
        and not ambiguous_scope_change_attribute_codes
    )

    return {
        "spuId": spu_id,
        "targetTemplateId": target_template_id,
        "preview": preview,
        "replacePayload": replace_payload,
        "autofilledSpuAttributeCodes": sorted(set(autofilled_spu_attribute_codes)),
        "autofilledSkuAttributeCodes": sorted(set(autofilled_sku_attribute_codes)),
        "ambiguousScopeChangeAttributeCodes": ambiguous_scope_change_attribute_codes,
        "missingRequiredSpuAttributeCodes": sorted(missing_required_spu_codes),
        "missingRequiredSkuAttributeCodes": missing_required_sku_codes,
        "readyForReplace": ready_for_replace,
    }


def apply_catalog_template_upgrade(
    *,
    spu_id: str,
    target_template_id: str,
    operator_id: str,
    request_id: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = apply_catalog_template_upgrade_with_session(
            session,
            spu_id=spu_id,
            target_template_id=target_template_id,
            operator_id=operator_id,
            request_id=request_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def apply_catalog_template_upgrade_with_session(
    session: Session,
    *,
    spu_id: str,
    target_template_id: str,
    operator_id: str,
    request_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not operator_id.strip():
        raise CatalogTemplateUpgradeApplyError("operator_id is required.")

    preview = preview_catalog_template_upgrade_with_session(
        session,
        spu_id=spu_id,
        target_template_id=target_template_id,
    )
    if not preview["canAutoUpgrade"]:
        raise CatalogTemplateUpgradeApplyError(
            "Template upgrade requires manual replace because preview.canAutoUpgrade is false."
        )

    spu = session.get(ProductSpu, spu_id)
    if spu is None:
        raise CatalogTemplateUpgradeApplyError(f"SPU not found: {spu_id}")
    if spu.template_id == target_template_id:
        raise CatalogTemplateUpgradeApplyError(f"SPU already uses template: {target_template_id}")

    target_template = session.get(CategoryAttrTemplate, target_template_id)
    if target_template is None:
        raise CatalogTemplateUpgradeApplyError(f"Target template not found: {target_template_id}")
    if spu.category_id != target_template.category_id:
        raise CatalogTemplateUpgradeApplyError(
            f"Target template {target_template_id} does not belong to SPU category {spu.category_id}"
        )

    before_snapshot = dict(spu.attr_snapshot_json or {})
    before_template_id = spu.template_id
    updated_snapshot = {
        **before_snapshot,
        "templateId": target_template_id,
        "saleAttributeCodes": list(preview["targetSaleAttributeCodes"]),
    }
    spu.template_id = target_template_id
    spu.attr_snapshot_json = updated_snapshot

    outbox_event = OutboxEvent(
        event_type=CATALOG_OUTBOX_EVENT_TYPE,
        aggregate_type=CATALOG_OUTBOX_AGGREGATE_TYPE,
        aggregate_id=spu.id,
        event_version=1,
        payload={
            "requestId": request_id,
            "spuId": spu.id,
            "templateUpgrade": True,
            "fromTemplateId": before_template_id,
            "toTemplateId": target_template_id,
            "skuCount": len(list(spu.skus or [])),
            "canAutoUpgrade": True,
        },
    )
    session.add(outbox_event)

    audit_log = ProductAttrAuditLog(
        operator_id=operator_id,
        resource_type="product_spu",
        resource_id=spu.id,
        action="UPGRADE_TEMPLATE_DRY_RUN" if dry_run else "UPGRADE_TEMPLATE",
        before_json={
            "requestId": request_id,
            "templateId": before_template_id,
            "snapshot": before_snapshot,
        },
        after_json={
            "requestId": request_id,
            "templateId": target_template_id,
            "snapshot": updated_snapshot,
            "preview": preview,
        },
    )
    session.add(audit_log)
    session.flush()

    return {
        "dryRun": dry_run,
        "requestId": request_id,
        "spuId": spu.id,
        "fromTemplateId": before_template_id,
        "toTemplateId": target_template_id,
        "outboxEventId": outbox_event.id,
        "auditLogId": audit_log.id,
        "preview": preview,
    }


def apply_catalog_template_replace_plan(
    *,
    spu_id: str,
    target_template_id: str,
    operator_id: str,
    request_id: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = apply_catalog_template_replace_plan_with_session(
            session,
            spu_id=spu_id,
            target_template_id=target_template_id,
            operator_id=operator_id,
            request_id=request_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def apply_catalog_template_replace_plan_with_session(
    session: Session,
    *,
    spu_id: str,
    target_template_id: str,
    operator_id: str,
    request_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not operator_id.strip():
        raise CatalogTemplateReplaceApplyError("operator_id is required.")

    plan = preview_catalog_template_replace_plan_with_session(
        session,
        spu_id=spu_id,
        target_template_id=target_template_id,
    )
    if not plan["readyForReplace"]:
        raise CatalogTemplateReplaceApplyError(
            "Template replace plan is not ready. Resolve missing or ambiguous attributes first."
        )

    payload = {
        **dict(plan["replacePayload"]),
        "requestId": request_id,
    }
    result = replace_catalog_payload_with_session(
        session,
        payload=payload,
        operator_id=operator_id,
        dry_run=dry_run,
    )
    return {
        "dryRun": dry_run,
        "requestId": request_id,
        "spuId": spu_id,
        "targetTemplateId": target_template_id,
        "preview": plan["preview"],
        "replacePlan": {
            "autofilledSpuAttributeCodes": plan["autofilledSpuAttributeCodes"],
            "autofilledSkuAttributeCodes": plan["autofilledSkuAttributeCodes"],
            "ambiguousScopeChangeAttributeCodes": plan["ambiguousScopeChangeAttributeCodes"],
            "readyForReplace": plan["readyForReplace"],
        },
        "replaceResult": result,
    }


def _detail_value_to_payload(value: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "attributeCode": value["attributeCode"],
    }
    if value.get("textValue") is not None:
        payload["textValue"] = value["textValue"]
    if value.get("numberValue") is not None:
        payload["numberValue"] = value["numberValue"]
    if value.get("normalizedNumberValue") is not None:
        payload["normalizedNumberValue"] = value["normalizedNumberValue"]
    if value.get("boolValue") is not None:
        payload["boolValue"] = value["boolValue"]
    if value.get("optionId") is not None:
        payload["optionId"] = value["optionId"]
    if value.get("optionCode") is not None:
        payload["optionCode"] = value["optionCode"]
    if value.get("optionName") is not None:
        payload["optionName"] = value["optionName"]
    if value.get("jsonValue") is not None:
        payload["jsonValue"] = value["jsonValue"]
    return payload


def _ensure_replace_plan_sku(replace_skus: list[dict[str, Any]], sku: dict[str, Any]) -> dict[str, Any]:
    for row in replace_skus:
        if row["skuCode"] == sku["skuCode"]:
            return row

    created = {
        "skuCode": sku["skuCode"],
        "price": sku["price"],
        "stock": sku["stock"],
        "barcode": sku.get("barcode"),
        "status": sku.get("status", "DRAFT"),
        "saleAttributes": [],
        "attributes": [],
    }
    replace_skus.append(created)
    return created


def _resolve_uniform_sku_value(
    *,
    sku_value_maps: dict[str, dict[str, dict[str, Any]]],
    attribute_code: str,
) -> dict[str, Any]:
    found: list[tuple[str, dict[str, Any]]] = []
    for sku_code, value_map in sku_value_maps.items():
        value = value_map.get(attribute_code)
        if value is not None:
            found.append((sku_code, value))

    if not found:
        return {"status": "missing"}

    normalized_pairs = [(_detail_value_signature(value), sku_code, value) for sku_code, value in found]
    first_signature = normalized_pairs[0][0]
    if all(signature == first_signature for signature, _, _ in normalized_pairs):
        return {"status": "resolved", "value": normalized_pairs[0][2]}
    return {"status": "ambiguous", "skuCodes": [sku_code for _, sku_code, _ in normalized_pairs]}


def _detail_value_signature(value: dict[str, Any]) -> tuple[Any, ...]:
    json_value = value.get("jsonValue")
    normalized_json = repr(json_value) if json_value is not None else None
    return (
        value.get("attributeCode"),
        value.get("textValue"),
        value.get("numberValue"),
        value.get("normalizedNumberValue"),
        value.get("boolValue"),
        value.get("optionId"),
        value.get("optionCode"),
        value.get("optionName"),
        normalized_json,
    )
