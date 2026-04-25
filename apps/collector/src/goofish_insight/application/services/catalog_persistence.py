from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import session_scope
from ...models import (
    AttributeDefinition,
    AttributeOption,
    CategoryAttrTemplate,
    CategoryAttrTemplateItem,
    OutboxEvent,
    ProductAttrAuditLog,
    ProductSku,
    ProductSkuAttrValue,
    ProductSpu,
    ProductSpuAttrValue,
    ProductStatus,
)
from .catalog_category_quality import catalog_scope_mismatch_reason
from .catalog_write import prepare_catalog_persist_plan


class CatalogPersistenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class CatalogMetadata:
    template: CategoryAttrTemplate
    template_items: list[dict[str, Any]]
    attributes: list[dict[str, Any]]
    attribute_map: dict[str, AttributeDefinition]
    option_code_map: dict[tuple[str, str], AttributeOption]
    option_id_map: dict[tuple[str, str], AttributeOption]
    category_code: str | None = None


def persist_catalog_payload(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = persist_catalog_payload_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def replace_catalog_payload(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = replace_catalog_payload_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def persist_catalog_payload_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not operator_id.strip():
        raise CatalogPersistenceError("operator_id is required.")

    spu_payload = dict(payload.get("spu") or {})
    category_id = str(spu_payload.get("categoryId") or "").strip()
    template_id = str(spu_payload.get("templateId") or "").strip()
    if not category_id or not template_id:
        raise CatalogPersistenceError("spu.categoryId and spu.templateId are required.")

    metadata = _load_catalog_metadata(
        session,
        template_id=template_id,
        category_id=category_id,
    )
    normalized_payload = _normalize_persist_payload(payload, metadata)
    plan = prepare_catalog_persist_plan(normalized_payload)
    _raise_if_catalog_scope_mismatch(plan=plan, metadata=metadata)
    attribute_map = metadata.attribute_map

    provided_spu_id = _validate_optional_uuid(normalized_payload["spu"].get("id"), "spu.id")
    if provided_spu_id and session.get(ProductSpu, provided_spu_id) is not None:
        raise CatalogPersistenceError(f"SPU already exists: {provided_spu_id}")

    spu_row = plan["spuRow"]
    spu = ProductSpu(
        category_id=spu_row["categoryId"],
        template_id=spu_row["templateId"],
        merchant_id=spu_row.get("merchantId"),
        brand_id=spu_row.get("brandId"),
        title=spu_row["title"],
        status=_coerce_product_status(spu_row.get("status")),
        attr_snapshot_json=spu_row["attrSnapshotJson"],
    )
    if provided_spu_id:
        spu.id = provided_spu_id
    session.add(spu)
    session.flush()
    spu.attr_snapshot_json = _with_spu_id(spu.attr_snapshot_json, spu.id)

    spu_attribute_count = 0
    for row in plan["spuAttributeRows"]:
        session.add(
            ProductSpuAttrValue(
                spu_id=spu.id,
                attribute_id=_attribute_id_for_code(attribute_map, row["attributeCode"]),
                value_seq=row["valueSeq"],
                text_value=row.get("textValue"),
                number_value=_coerce_decimal(row.get("numberValue")),
                normalized_number_value=_coerce_decimal(row.get("normalizedNumberValue")),
                bool_value=row.get("boolValue"),
                option_id=row.get("optionId"),
                json_value=row.get("jsonValue"),
            )
        )
        spu_attribute_count += 1

    sku_objects: dict[str, ProductSku] = {}
    for row in plan["skuRows"]:
        sku_code = str(row["skuCode"])
        if sku_code in sku_objects:
            raise CatalogPersistenceError(f"Duplicate skuCode in payload: {sku_code}")
        sku = ProductSku(
            spu_id=spu.id,
            sku_code=sku_code,
            sales_signature_raw=row["salesSignatureRaw"],
            sales_signature_hash=row["salesSignatureHash"],
            price=_coerce_decimal(row["price"]) or Decimal("0"),
            stock=int(row["stock"]),
            barcode=row.get("barcode"),
            status=_coerce_product_status(row.get("status")),
            attr_snapshot_json=row["attrSnapshotJson"],
        )
        session.add(sku)
        sku_objects[sku_code] = sku
    session.flush()

    sku_attribute_count = 0
    for row in plan["skuAttributeRows"]:
        sku_code = str(row["skuCode"])
        sku = sku_objects.get(sku_code)
        if sku is None:
            raise CatalogPersistenceError(f"Unknown skuCode in attribute rows: {sku_code}")
        session.add(
            ProductSkuAttrValue(
                sku_id=sku.id,
                attribute_id=_attribute_id_for_code(attribute_map, row["attributeCode"]),
                value_seq=row["valueSeq"],
                text_value=row.get("textValue"),
                number_value=_coerce_decimal(row.get("numberValue")),
                normalized_number_value=_coerce_decimal(row.get("normalizedNumberValue")),
                bool_value=row.get("boolValue"),
                option_id=row.get("optionId"),
                json_value=row.get("jsonValue"),
            )
        )
        sku_attribute_count += 1

    outbox_event = OutboxEvent(
        event_type=plan["outboxEvent"]["eventType"],
        aggregate_type=plan["outboxEvent"]["aggregateType"],
        aggregate_id=spu.id,
        event_version=int(plan["outboxEvent"].get("eventVersion", 1)),
        payload={
            **dict(plan["outboxEvent"]["payload"]),
            "spuId": spu.id,
            "skuIds": [sku.id for sku in sku_objects.values()],
        },
    )
    session.add(outbox_event)

    audit_log = ProductAttrAuditLog(
        operator_id=operator_id,
        resource_type="product_spu",
        resource_id=spu.id,
        action="CREATE_DRY_RUN" if dry_run else "CREATE",
        before_json=None,
        after_json={
            "requestId": normalized_payload.get("requestId"),
            "spuId": spu.id,
            "skuCodes": list(sku_objects.keys()),
            "snapshot": spu.attr_snapshot_json,
        },
    )
    session.add(audit_log)
    session.flush()

    return {
        "dryRun": dry_run,
        "requestId": normalized_payload.get("requestId"),
        "spuId": spu.id,
        "skuIds": [sku.id for sku in sku_objects.values()],
        "spuAttributeCount": spu_attribute_count,
        "skuCount": len(sku_objects),
        "skuAttributeCount": sku_attribute_count,
        "outboxEventId": outbox_event.id,
        "auditLogId": audit_log.id,
    }


def replace_catalog_payload_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not operator_id.strip():
        raise CatalogPersistenceError("operator_id is required.")

    spu_payload = dict(payload.get("spu") or {})
    provided_spu_id = _validate_optional_uuid(spu_payload.get("id"), "spu.id")
    if not provided_spu_id:
        raise CatalogPersistenceError("spu.id is required for replace.")

    existing_spu = session.get(ProductSpu, provided_spu_id)
    if existing_spu is None:
        raise CatalogPersistenceError(f"SPU not found for replace: {provided_spu_id}")

    category_id = str(spu_payload.get("categoryId") or "").strip()
    template_id = str(spu_payload.get("templateId") or "").strip()
    if not category_id or not template_id:
        raise CatalogPersistenceError("spu.categoryId and spu.templateId are required.")

    metadata = _load_catalog_metadata(
        session,
        template_id=template_id,
        category_id=category_id,
    )
    normalized_payload = _normalize_persist_payload(payload, metadata)
    plan = prepare_catalog_persist_plan(normalized_payload)
    _raise_if_catalog_scope_mismatch(plan=plan, metadata=metadata)
    attribute_map = metadata.attribute_map
    before_snapshot = dict(existing_spu.attr_snapshot_json or {})

    _delete_existing_spu_graph(session, existing_spu)

    spu_row = plan["spuRow"]
    existing_spu.category_id = spu_row["categoryId"]
    existing_spu.template_id = spu_row["templateId"]
    existing_spu.merchant_id = spu_row.get("merchantId")
    existing_spu.brand_id = spu_row.get("brandId")
    existing_spu.title = spu_row["title"]
    existing_spu.status = _coerce_product_status(spu_row.get("status"))
    existing_spu.attr_snapshot_json = _with_spu_id(spu_row["attrSnapshotJson"], existing_spu.id)
    session.flush()

    spu_attribute_count = 0
    for row in plan["spuAttributeRows"]:
        session.add(
            ProductSpuAttrValue(
                spu_id=existing_spu.id,
                attribute_id=_attribute_id_for_code(attribute_map, row["attributeCode"]),
                value_seq=row["valueSeq"],
                text_value=row.get("textValue"),
                number_value=_coerce_decimal(row.get("numberValue")),
                normalized_number_value=_coerce_decimal(row.get("normalizedNumberValue")),
                bool_value=row.get("boolValue"),
                option_id=row.get("optionId"),
                json_value=row.get("jsonValue"),
            )
        )
        spu_attribute_count += 1

    sku_objects: dict[str, ProductSku] = {}
    for row in plan["skuRows"]:
        sku_code = str(row["skuCode"])
        if sku_code in sku_objects:
            raise CatalogPersistenceError(f"Duplicate skuCode in payload: {sku_code}")
        sku = ProductSku(
            spu_id=existing_spu.id,
            sku_code=sku_code,
            sales_signature_raw=row["salesSignatureRaw"],
            sales_signature_hash=row["salesSignatureHash"],
            price=_coerce_decimal(row["price"]) or Decimal("0"),
            stock=int(row["stock"]),
            barcode=row.get("barcode"),
            status=_coerce_product_status(row.get("status")),
            attr_snapshot_json=row["attrSnapshotJson"],
        )
        session.add(sku)
        sku_objects[sku_code] = sku
    session.flush()

    sku_attribute_count = 0
    for row in plan["skuAttributeRows"]:
        sku_code = str(row["skuCode"])
        sku = sku_objects.get(sku_code)
        if sku is None:
            raise CatalogPersistenceError(f"Unknown skuCode in attribute rows: {sku_code}")
        session.add(
            ProductSkuAttrValue(
                sku_id=sku.id,
                attribute_id=_attribute_id_for_code(attribute_map, row["attributeCode"]),
                value_seq=row["valueSeq"],
                text_value=row.get("textValue"),
                number_value=_coerce_decimal(row.get("numberValue")),
                normalized_number_value=_coerce_decimal(row.get("normalizedNumberValue")),
                bool_value=row.get("boolValue"),
                option_id=row.get("optionId"),
                json_value=row.get("jsonValue"),
            )
        )
        sku_attribute_count += 1

    outbox_event = OutboxEvent(
        event_type=plan["outboxEvent"]["eventType"],
        aggregate_type=plan["outboxEvent"]["aggregateType"],
        aggregate_id=existing_spu.id,
        event_version=int(plan["outboxEvent"].get("eventVersion", 1)),
        payload={
            **dict(plan["outboxEvent"]["payload"]),
            "spuId": existing_spu.id,
            "skuIds": [sku.id for sku in sku_objects.values()],
            "replace": True,
        },
    )
    session.add(outbox_event)

    audit_log = ProductAttrAuditLog(
        operator_id=operator_id,
        resource_type="product_spu",
        resource_id=existing_spu.id,
        action="REPLACE_DRY_RUN" if dry_run else "REPLACE",
        before_json={
            "snapshot": before_snapshot,
        },
        after_json={
            "requestId": normalized_payload.get("requestId"),
            "spuId": existing_spu.id,
            "skuCodes": list(sku_objects.keys()),
            "snapshot": existing_spu.attr_snapshot_json,
        },
    )
    session.add(audit_log)
    session.flush()

    return {
        "dryRun": dry_run,
        "requestId": normalized_payload.get("requestId"),
        "spuId": existing_spu.id,
        "skuIds": [sku.id for sku in sku_objects.values()],
        "spuAttributeCount": spu_attribute_count,
        "skuCount": len(sku_objects),
        "skuAttributeCount": sku_attribute_count,
        "outboxEventId": outbox_event.id,
        "auditLogId": audit_log.id,
    }


def _load_catalog_metadata(
    session: Session,
    *,
    template_id: str,
    category_id: str,
) -> CatalogMetadata:
    template = session.get(CategoryAttrTemplate, template_id)
    if template is None:
        raise CatalogPersistenceError(f"Template not found: {template_id}")
    if template.category_id != category_id:
        raise CatalogPersistenceError(
            f"Template {template_id} does not belong to category {category_id}."
        )

    rows = session.execute(
        select(CategoryAttrTemplateItem, AttributeDefinition)
        .join(AttributeDefinition, CategoryAttrTemplateItem.attribute_id == AttributeDefinition.id)
        .where(CategoryAttrTemplateItem.template_id == template_id)
        .order_by(CategoryAttrTemplateItem.sort_no.asc(), AttributeDefinition.code.asc())
    ).all()
    if not rows:
        raise CatalogPersistenceError(f"Template has no attribute items: {template_id}")

    template_items: list[dict[str, Any]] = []
    attributes: list[dict[str, Any]] = []
    attribute_map: dict[str, AttributeDefinition] = {}

    for item, attribute in rows:
        attribute_map[attribute.code] = attribute
        template_items.append(
            {
                "attributeCode": attribute.code,
                "attributeId": attribute.id,
                "isSale": item.is_sale,
                "sortNo": item.sort_no,
            }
        )
        attributes.append(
            {
                "code": attribute.code,
                "name": attribute.name,
                "dataType": attribute.data_type.value,
                "isMulti": attribute.is_multi,
            }
        )

    option_code_map: dict[tuple[str, str], AttributeOption] = {}
    option_id_map: dict[tuple[str, str], AttributeOption] = {}
    option_rows = session.execute(
        select(AttributeOption)
        .where(AttributeOption.attribute_id.in_([attribute.id for attribute in attribute_map.values()]))
    ).scalars()
    attribute_by_id = {attribute.id: attribute for attribute in attribute_map.values()}
    for option in option_rows:
        attribute = attribute_by_id.get(option.attribute_id)
        if attribute is None:
            continue
        option_code_map[(attribute.code, option.option_code)] = option
        option_id_map[(attribute.code, option.id)] = option

    return CatalogMetadata(
        template=template,
        template_items=template_items,
        attributes=attributes,
        attribute_map=attribute_map,
        option_code_map=option_code_map,
        option_id_map=option_id_map,
        category_code=str(getattr(getattr(template, "category", None), "code", "") or ""),
    )


def _normalize_persist_payload(
    payload: dict[str, Any],
    metadata: CatalogMetadata,
) -> dict[str, Any]:
    return {
        "requestId": payload.get("requestId"),
        "spu": dict(payload.get("spu") or {}),
        "templateItems": metadata.template_items,
        "attributes": metadata.attributes,
        "spuAttributes": [
            _normalize_attribute_value(value, metadata) for value in list(payload.get("spuAttributes") or [])
        ],
        "skus": [
            {
                **dict(sku),
                "saleAttributes": [
                    _normalize_attribute_value(value, metadata)
                    for value in list(sku.get("saleAttributes") or [])
                ],
                "attributes": [
                    _normalize_attribute_value(value, metadata)
                    for value in list(sku.get("attributes") or [])
                ],
            }
            for sku in list(payload.get("skus") or [])
        ],
    }


def _normalize_attribute_value(
    raw_value: dict[str, Any],
    metadata: CatalogMetadata,
) -> dict[str, Any]:
    value = dict(raw_value)
    attribute_code = str(value.get("attributeCode") or "").strip()
    if not attribute_code:
        raise CatalogPersistenceError("attributeCode is required.")
    attribute = metadata.attribute_map.get(attribute_code)
    if attribute is None:
        raise CatalogPersistenceError(f"Attribute is not part of template: {attribute_code}")

    if attribute.data_type.value != "ENUM":
        value["optionId"] = None
        value["optionCode"] = None
        value["optionName"] = None
        return value

    option_id = str(value.get("optionId") or "").strip()
    option_code = str(value.get("optionCode") or "").strip()
    option = None
    if option_id:
        option = metadata.option_id_map.get((attribute_code, option_id))
        if option is None:
            raise CatalogPersistenceError(
                f"Option id does not belong to attribute {attribute_code}: {option_id}"
            )
    elif option_code:
        option = metadata.option_code_map.get((attribute_code, option_code))
        if option is None:
            raise CatalogPersistenceError(
                f"Option code does not belong to attribute {attribute_code}: {option_code}"
            )
    else:
        raise CatalogPersistenceError(
            f"Enum attribute requires optionId or optionCode: {attribute_code}"
        )

    if option_code and option.option_code != option_code:
        raise CatalogPersistenceError(
            f"Option code mismatch for attribute {attribute_code}: {option_code}"
        )

    value["optionId"] = option.id
    value["optionCode"] = option.option_code
    value["optionName"] = option.option_name
    return value


def _attribute_id_for_code(
    attribute_map: dict[str, AttributeDefinition],
    attribute_code: str,
) -> str:
    attribute = attribute_map.get(attribute_code)
    if attribute is None:
        raise CatalogPersistenceError(f"Unknown attribute code: {attribute_code}")
    return attribute.id


def _coerce_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _coerce_product_status(value: Any) -> ProductStatus:
    raw = str(value or ProductStatus.DRAFT.value).upper()
    try:
        return ProductStatus(raw)
    except ValueError as exc:
        raise CatalogPersistenceError(f"Invalid product status: {value}") from exc


def _raise_if_catalog_scope_mismatch(
    *,
    plan: dict[str, Any],
    metadata: CatalogMetadata,
) -> None:
    category_code = str(metadata.category_code or "").strip()
    if not category_code:
        return
    spu_row = dict(plan.get("spuRow") or {})
    reason = catalog_scope_mismatch_reason(
        category_code,
        title=spu_row.get("title"),
        spu_snapshot=spu_row.get("attrSnapshotJson"),
        sku_snapshots=[dict(row).get("attrSnapshotJson") for row in list(plan.get("skuRows") or [])],
    )
    if reason is not None:
        raise CatalogPersistenceError(
            f"Catalog payload does not match category {category_code}: {reason}"
        )


def _validate_optional_uuid(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        UUID(raw)
    except ValueError as exc:
        raise CatalogPersistenceError(f"{field_name} must be a UUID string.") from exc
    return raw


def _with_spu_id(snapshot: dict[str, Any], spu_id: str) -> dict[str, Any]:
    return {
        **dict(snapshot),
        "spuId": spu_id,
    }


def _delete_existing_spu_graph(session: Session, spu: ProductSpu) -> None:
    for attribute in list(spu.attributes):
        session.delete(attribute)
    for sku in list(spu.skus):
        for attribute in list(sku.attributes):
            session.delete(attribute)
        session.delete(sku)
    spu.attributes = []
    spu.skus = []
    session.flush()
