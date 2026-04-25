from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import session_scope
from ...models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeOption,
    AttributeScopeType,
    AttributeStatus,
    Category,
    CategoryAttrTemplate,
    CategoryAttrTemplateItem,
    ProductAttrAuditLog,
    TemplateStatus,
)
from .spec_schema_snapshots import (
    SpecSchemaSnapshotError,
    template_item_schema_payload_from_input,
    upsert_active_schema_snapshot_with_session,
)


class CatalogTemplatePersistenceError(RuntimeError):
    pass


def persist_catalog_template_payload(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = persist_catalog_template_payload_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def persist_catalog_template_payload_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not operator_id.strip():
        raise CatalogTemplatePersistenceError("operator_id is required.")

    category_payload = dict(payload.get("category") or {})
    template_payload = dict(payload.get("template") or {})
    attribute_payloads = list(payload.get("attributes") or [])
    if not category_payload:
        raise CatalogTemplatePersistenceError("category is required.")
    if not template_payload:
        raise CatalogTemplatePersistenceError("template is required.")
    if not attribute_payloads:
        raise CatalogTemplatePersistenceError("attributes are required.")

    category = Category(
        code=str(category_payload["code"]),
        name=str(category_payload["name"]),
        path=str(category_payload["path"]),
        level=int(category_payload["level"]),
        status=str(category_payload.get("status", "ACTIVE")),
    )
    category_id = _validate_optional_uuid(category_payload.get("id"), "category.id")
    if category_id:
        if session.get(Category, category_id) is not None:
            raise CatalogTemplatePersistenceError(f"Category already exists: {category_id}")
        category.id = category_id
    session.add(category)
    session.flush()

    attribute_codes: set[str] = set()
    attribute_map: dict[str, AttributeDefinition] = {}
    option_count = 0
    for attribute_payload in attribute_payloads:
        code = str(attribute_payload["code"])
        if code in attribute_codes:
            raise CatalogTemplatePersistenceError(f"Duplicate attribute code in payload: {code}")
        attribute_codes.add(code)

        scope_type = _coerce_scope_type(attribute_payload.get("scopeType"))
        scope_id = str(attribute_payload.get("scopeId") or "platform")
        data_type = _coerce_data_type(attribute_payload.get("dataType"))
        value_scope = str(attribute_payload["valueScope"])
        is_multi = bool(attribute_payload.get("isMulti", False))
        unit = attribute_payload.get("unit")
        status = _coerce_attribute_status(attribute_payload.get("status"))
        requested_attribute_id = _validate_optional_uuid(attribute_payload.get("id"), f"attributes[{code}].id")

        existing_attribute = session.execute(
            select(AttributeDefinition).where(
                AttributeDefinition.scope_type == scope_type,
                AttributeDefinition.scope_id == scope_id,
                AttributeDefinition.code == code,
            )
        ).scalar_one_or_none()
        if existing_attribute is not None:
            if existing_attribute.data_type != data_type:
                raise CatalogTemplatePersistenceError(
                    f"Existing attribute {code} dataType mismatch: {existing_attribute.data_type} != {data_type}"
                )
            if str(existing_attribute.value_scope) != value_scope:
                raise CatalogTemplatePersistenceError(
                    f"Existing attribute {code} valueScope mismatch: {existing_attribute.value_scope} != {value_scope}"
                )
            if bool(existing_attribute.is_multi) != is_multi:
                raise CatalogTemplatePersistenceError(
                    f"Existing attribute {code} isMulti mismatch: {existing_attribute.is_multi} != {is_multi}"
                )
            existing_unit = existing_attribute.unit or None
            requested_unit = unit or None
            if existing_unit != requested_unit:
                raise CatalogTemplatePersistenceError(
                    f"Existing attribute {code} unit mismatch: {existing_unit} != {requested_unit}"
                )
            attribute_map[code] = existing_attribute
            continue

        attribute = AttributeDefinition(
            scope_type=scope_type,
            scope_id=scope_id,
            code=code,
            name=str(attribute_payload["name"]),
            data_type=data_type,
            value_scope=value_scope,
            is_multi=is_multi,
            unit=unit,
            validation_schema=attribute_payload.get("validationSchema"),
            status=status,
        )
        attribute_id = requested_attribute_id
        if attribute_id:
            if session.get(AttributeDefinition, attribute_id) is not None:
                raise CatalogTemplatePersistenceError(f"Attribute already exists: {attribute_id}")
            attribute.id = attribute_id
        session.add(attribute)
        attribute_map[code] = attribute

    session.flush()

    for attribute_payload in attribute_payloads:
        attribute = attribute_map[str(attribute_payload["code"])]
        seen_option_codes: set[str] = set()
        for option_payload in list(attribute_payload.get("options") or []):
            option_code = str(option_payload["optionCode"])
            if option_code in seen_option_codes:
                raise CatalogTemplatePersistenceError(
                    f"Duplicate option code for attribute {attribute.code}: {option_code}"
                )
            seen_option_codes.add(option_code)
            option = AttributeOption(
                attribute_id=attribute.id,
                option_code=option_code,
                option_name=str(option_payload["optionName"]),
                sort_no=int(option_payload.get("sortNo", 0)),
                status=_coerce_attribute_status(option_payload.get("status", "ACTIVE")),
            )
            option_id = _validate_optional_uuid(
                option_payload.get("id"),
                f"attributes[{attribute.code}].options[{option_code}].id",
            )
            if option_id:
                if session.get(AttributeOption, option_id) is not None:
                    raise CatalogTemplatePersistenceError(f"Attribute option already exists: {option_id}")
                option.id = option_id
            session.add(option)
            option_count += 1

    template = CategoryAttrTemplate(
        category_id=category.id,
        version=int(template_payload["version"]),
        status=_coerce_template_status(template_payload.get("status")),
        effective_at=_coerce_datetime(template_payload.get("effectiveAt")),
        published_by=template_payload.get("publishedBy"),
    )
    template_id = _validate_optional_uuid(template_payload.get("id"), "template.id")
    if template_id:
        if session.get(CategoryAttrTemplate, template_id) is not None:
            raise CatalogTemplatePersistenceError(f"Template already exists: {template_id}")
        template.id = template_id
    session.add(template)
    session.flush()

    template_item_count = 0
    seen_template_attributes: set[str] = set()
    created_template_items: list[CategoryAttrTemplateItem] = []
    for item_payload in list(template_payload.get("items") or []):
        attribute_code = str(item_payload["attributeCode"])
        attribute = attribute_map.get(attribute_code)
        if attribute is None:
            raise CatalogTemplatePersistenceError(
                f"Template references unknown attribute code: {attribute_code}"
            )
        if attribute_code in seen_template_attributes:
            raise CatalogTemplatePersistenceError(
                f"Duplicate template attribute code in payload: {attribute_code}"
            )
        seen_template_attributes.add(attribute_code)
        try:
            schema_payload = template_item_schema_payload_from_input(item_payload)
        except SpecSchemaSnapshotError as exc:
            raise CatalogTemplatePersistenceError(str(exc)) from exc
        item = CategoryAttrTemplateItem(
            template_id=template.id,
            attribute_id=attribute.id,
            is_required=bool(item_payload.get("isRequired", False)),
            is_sale=bool(item_payload.get("isSale", False)),
            is_filter=bool(item_payload.get("isFilter", False)),
            is_search=bool(item_payload.get("isSearch", False)),
            is_display=bool(item_payload.get("isDisplay", True)),
            role=schema_payload["role"],
            weight=schema_payload["weight"],
            normalization=schema_payload["normalization"],
            enum_values=schema_payload["enumValues"],
            sort_no=int(item_payload.get("sortNo", 0)),
        )
        item.attribute = attribute
        item.template = template
        session.add(item)
        created_template_items.append(item)
        template_item_count += 1
    template.items = created_template_items

    schema_snapshot = None
    if template.status == TemplateStatus.PUBLISHED:
        try:
            schema_snapshot = upsert_active_schema_snapshot_with_session(
                session,
                template=template,
                created_by=operator_id,
            )
        except SpecSchemaSnapshotError as exc:
            raise CatalogTemplatePersistenceError(str(exc)) from exc
        session.flush()

    audit_log = ProductAttrAuditLog(
        operator_id=operator_id,
        resource_type="category_attr_template",
        resource_id=template.id,
        action="CREATE_TEMPLATE_DRY_RUN" if dry_run else "CREATE_TEMPLATE",
        before_json=None,
        after_json={
            "requestId": payload.get("requestId"),
            "categoryId": category.id,
            "templateId": template.id,
            "attributeCodes": sorted(attribute_map.keys()),
            "templateVersion": template.version,
        },
    )
    session.add(audit_log)
    session.flush()

    return {
        "dryRun": dry_run,
        "requestId": payload.get("requestId"),
        "categoryId": category.id,
        "templateId": template.id,
        "attributeCount": len(attribute_map),
        "optionCount": option_count,
        "templateItemCount": template_item_count,
        "schemaId": getattr(schema_snapshot, "schema_id", None),
        "auditLogId": audit_log.id,
    }


def _coerce_scope_type(value: Any) -> AttributeScopeType:
    raw = str(value or AttributeScopeType.PLATFORM.value).upper()
    try:
        return AttributeScopeType(raw)
    except ValueError as exc:
        raise CatalogTemplatePersistenceError(f"Invalid scopeType: {value}") from exc


def _coerce_data_type(value: Any) -> AttributeDataType:
    raw = str(value or "").upper()
    try:
        return AttributeDataType(raw)
    except ValueError as exc:
        raise CatalogTemplatePersistenceError(f"Invalid dataType: {value}") from exc


def _coerce_attribute_status(value: Any) -> AttributeStatus:
    raw = str(value or AttributeStatus.DRAFT.value).upper()
    try:
        return AttributeStatus(raw)
    except ValueError as exc:
        raise CatalogTemplatePersistenceError(f"Invalid attribute status: {value}") from exc


def _coerce_template_status(value: Any) -> TemplateStatus:
    raw = str(value or TemplateStatus.DRAFT.value).upper()
    try:
        return TemplateStatus(raw)
    except ValueError as exc:
        raise CatalogTemplatePersistenceError(f"Invalid template status: {value}") from exc


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise CatalogTemplatePersistenceError(f"Invalid effectiveAt: {value}") from exc


def _validate_optional_uuid(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        UUID(raw)
    except ValueError as exc:
        raise CatalogTemplatePersistenceError(f"{field_name} must be a UUID string.") from exc
    return raw
