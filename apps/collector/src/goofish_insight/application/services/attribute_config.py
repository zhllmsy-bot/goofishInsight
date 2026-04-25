from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...common_runtime_attributes import is_runtime_common_attribute, merge_runtime_common_flag
from ...db import session_scope
from ...models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeOption,
    AttributeScopeType,
    AttributeStatus,
    ProductAttrAuditLog,
)


class AttributeConfigError(RuntimeError):
    pass


def list_attribute_configs(
    *,
    status: str | None = None,
    scope_type: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return list_attribute_configs_with_session(
            session,
            status=status,
            scope_type=scope_type,
        )


def list_attribute_configs_with_session(
    session: Session,
    *,
    status: str | None = None,
    scope_type: str | None = None,
) -> dict[str, Any]:
    rows = list(session.execute(select(AttributeDefinition)).scalars().all())
    if status:
        normalized_status = str(status).strip().upper()
        rows = [row for row in rows if str(getattr(row.status, "value", row.status)).upper() == normalized_status]
    if scope_type:
        normalized_scope_type = str(scope_type).strip().upper()
        rows = [row for row in rows if str(getattr(row.scope_type, "value", row.scope_type)).upper() == normalized_scope_type]
    items = [
        serialize_attribute_config(row)
        for row in sorted(
            rows,
            key=lambda row: (
                str(getattr(row.scope_type, "value", row.scope_type) or ""),
                str(row.scope_id or ""),
                str(row.code or ""),
            ),
        )
    ]
    return {
        "total": len(items),
        "items": items,
    }


def upsert_attribute_config(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = upsert_attribute_config_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def upsert_attribute_config_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_operator_id = _normalize_optional_string(operator_id)
    if not normalized_operator_id:
        raise AttributeConfigError("operator_id is required.")

    attribute_id = _normalize_optional_string(payload.get("attributeId"))
    scope_type = _coerce_scope_type(payload.get("scopeType"))
    scope_id = _normalize_optional_string(payload.get("scopeId")) or "platform"
    code = _normalize_optional_string(payload.get("code"))
    name = _normalize_optional_string(payload.get("name"))
    value_scope = _normalize_optional_string(payload.get("valueScope"))
    if not code:
        raise AttributeConfigError("code is required.")
    if not name:
        raise AttributeConfigError("name is required.")
    if not value_scope:
        raise AttributeConfigError("valueScope is required.")

    existing = _resolve_attribute(
        session,
        attribute_id=attribute_id,
        scope_type=scope_type,
        scope_id=scope_id,
        code=code,
    )
    before_json = serialize_attribute_config(existing)

    conflicting = _resolve_attribute(
        session,
        scope_type=scope_type,
        scope_id=scope_id,
        code=code,
    )
    if conflicting is not None and existing is not None and str(conflicting.id) != str(existing.id):
        raise AttributeConfigError(f"Attribute code already exists in scope: {code}")
    if conflicting is not None and existing is None:
        raise AttributeConfigError(f"Attribute code already exists in scope: {code}")

    input_validation_schema = dict(payload.get("validationSchema") or {})
    merged_validation_schema = merge_runtime_common_flag(
        code=code,
        validation_schema=input_validation_schema,
        is_common=payload.get("isCommon"),
    )

    if existing is None:
        row = AttributeDefinition(
            scope_type=scope_type,
            scope_id=scope_id,
            code=code,
            name=name,
            data_type=_coerce_data_type(payload.get("dataType")),
            value_scope=value_scope,
            is_multi=bool(payload.get("isMulti", False)),
            unit=_normalize_optional_string(payload.get("unit")),
            validation_schema=merged_validation_schema,
            status=_coerce_attribute_status(payload.get("status")),
        )
        if attribute_id:
            if session.get(AttributeDefinition, attribute_id) is not None:
                raise AttributeConfigError(f"Attribute already exists: {attribute_id}")
            row.id = attribute_id
        session.add(row)
        session.flush()
        action = "CREATE_ATTRIBUTE_CONFIG_DRY_RUN" if dry_run else "CREATE_ATTRIBUTE_CONFIG"
    else:
        row = existing
        row.scope_type = scope_type
        row.scope_id = scope_id
        row.code = code
        row.name = name
        row.data_type = _coerce_data_type(payload.get("dataType"))
        row.value_scope = value_scope
        row.is_multi = bool(payload.get("isMulti", False))
        row.unit = _normalize_optional_string(payload.get("unit"))
        row.validation_schema = merged_validation_schema
        row.status = _coerce_attribute_status(payload.get("status"))
        session.flush()
        action = "UPDATE_ATTRIBUTE_CONFIG_DRY_RUN" if dry_run else "UPDATE_ATTRIBUTE_CONFIG"

    if "options" in payload:
        _sync_attribute_options(row=row, option_payloads=list(payload.get("options") or []), session=session)
        session.flush()

    after_json = serialize_attribute_config(row)
    audit_log = ProductAttrAuditLog(
        operator_id=normalized_operator_id,
        resource_type="attribute_definition",
        resource_id=row.id,
        action=action,
        before_json=before_json,
        after_json=after_json,
    )
    session.add(audit_log)
    session.flush()
    return {
        "dryRun": dry_run,
        "attribute": after_json,
        "auditLogId": audit_log.id,
    }


def serialize_attribute_config(row: AttributeDefinition | None) -> dict[str, Any] | None:
    if row is None:
        return None
    options = sorted(list(getattr(row, "options", []) or []), key=lambda item: (int(item.sort_no or 0), str(item.option_code or "")))
    template_items = list(getattr(row, "template_items", []) or [])
    return {
        "id": row.id,
        "scopeType": getattr(row.scope_type, "value", row.scope_type),
        "scopeId": row.scope_id,
        "code": row.code,
        "name": row.name,
        "dataType": getattr(row.data_type, "value", row.data_type),
        "valueScope": row.value_scope,
        "isMulti": row.is_multi,
        "unit": row.unit,
        "validationSchema": dict(row.validation_schema or {}) if row.validation_schema else None,
        "isCommon": is_runtime_common_attribute(code=row.code, validation_schema=dict(row.validation_schema or {})),
        "status": getattr(row.status, "value", row.status),
        "optionCount": len(options),
        "options": [
            {
                "id": option.id,
                "optionCode": option.option_code,
                "optionName": option.option_name,
                "sortNo": option.sort_no,
                "status": getattr(option.status, "value", option.status),
            }
            for option in options
        ],
        "templateReferenceCount": len(template_items),
        "templateReferences": [
            {
                "templateId": item.template_id,
                "templateVersion": getattr(getattr(item, "template", None), "version", None),
                "categoryCode": getattr(getattr(getattr(item, "template", None), "category", None), "code", None),
            }
            for item in sorted(template_items, key=lambda item: (str(item.template_id or ""), int(item.sort_no or 0)))
        ],
        "createdAt": _json_safe_value(getattr(row, "created_at", None)),
        "updatedAt": _json_safe_value(getattr(row, "updated_at", None)),
    }


def _sync_attribute_options(
    *,
    row: AttributeDefinition,
    option_payloads: list[dict[str, Any]],
    session: Session,
) -> None:
    existing_by_code = {str(option.option_code): option for option in list(getattr(row, "options", []) or [])}
    seen_codes: set[str] = set()
    for index, option_payload in enumerate(option_payloads):
        option_code = _normalize_optional_string(option_payload.get("optionCode"))
        option_name = _normalize_optional_string(option_payload.get("optionName"))
        if not option_code or not option_name:
            raise AttributeConfigError("Each option requires optionCode and optionName.")
        if option_code in seen_codes:
            raise AttributeConfigError(f"Duplicate optionCode in payload: {option_code}")
        seen_codes.add(option_code)
        existing = existing_by_code.get(option_code)
        if existing is None:
            option = AttributeOption(
                attribute_id=row.id,
                option_code=option_code,
                option_name=option_name,
                sort_no=int(option_payload.get("sortNo", (index + 1) * 10)),
                status=_coerce_attribute_status(option_payload.get("status", "ACTIVE")),
            )
            session.add(option)
        else:
            existing.option_name = option_name
            existing.sort_no = int(option_payload.get("sortNo", existing.sort_no or (index + 1) * 10))
            existing.status = _coerce_attribute_status(option_payload.get("status", getattr(existing.status, "value", existing.status)))

    for option_code, existing in existing_by_code.items():
        if option_code not in seen_codes:
            existing.status = AttributeStatus.DISABLED


def _resolve_attribute(
    session: Session,
    *,
    attribute_id: str | None = None,
    scope_type: AttributeScopeType | None = None,
    scope_id: str | None = None,
    code: str | None = None,
) -> AttributeDefinition | None:
    normalized_attribute_id = _normalize_optional_string(attribute_id)
    if normalized_attribute_id:
        return session.get(AttributeDefinition, normalized_attribute_id)
    if scope_type is None or not scope_id or not code:
        return None
    rows = list(
        session.execute(
            select(AttributeDefinition).where(
                AttributeDefinition.scope_type == scope_type,
                AttributeDefinition.scope_id == scope_id,
                AttributeDefinition.code == code,
            )
        ).scalars().all()
    )
    return rows[0] if rows else None


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _coerce_scope_type(value: Any) -> AttributeScopeType:
    raw = str(value or AttributeScopeType.PLATFORM.value).upper()
    try:
        return AttributeScopeType(raw)
    except ValueError as exc:
        raise AttributeConfigError(f"Invalid scopeType: {value}") from exc


def _coerce_data_type(value: Any) -> AttributeDataType:
    raw = str(value or "").upper()
    try:
        return AttributeDataType(raw)
    except ValueError as exc:
        raise AttributeConfigError(f"Invalid dataType: {value}") from exc


def _coerce_attribute_status(value: Any) -> AttributeStatus:
    raw = str(value or AttributeStatus.DRAFT.value).upper()
    try:
        return AttributeStatus(raw)
    except ValueError as exc:
        raise AttributeConfigError(f"Invalid attribute status: {value}") from exc


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe_value(entry) for key, entry in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(entry) for entry in value]
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value
