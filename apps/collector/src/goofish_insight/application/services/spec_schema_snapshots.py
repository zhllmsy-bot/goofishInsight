from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...category_compat import resolve_category_code
from ...db import session_scope
from ...models import (
    Category,
    CategoryAttrTemplate,
    CategoryAttrTemplateItem,
    CategoryRuntimeProfile,
    SkuSpecSchemaSnapshot,
)


VALID_TEMPLATE_ITEM_ROLES = {"locking", "variant", "condition", "descriptive"}


class SpecSchemaSnapshotError(RuntimeError):
    pass


def get_category_spec_schema(*, category_code: str) -> dict[str, Any] | None:
    with session_scope() as session:
        return get_category_spec_schema_with_session(session, category_code=category_code)


def get_category_spec_schema_with_session(
    session: Session,
    *,
    category_code: str,
) -> dict[str, Any] | None:
    canonical_code = resolve_category_code(category_code)
    if not canonical_code:
        return None
    snapshot = _load_active_snapshot(session, category_code=canonical_code)
    if snapshot is not None:
        return serialize_spec_schema_snapshot(snapshot)

    template = _load_active_or_latest_template(session, category_code=canonical_code)
    if template is None:
        return None
    return derive_spec_schema_from_template(
        template,
        persisted=False,
        created_by=None,
        valid_from=getattr(template, "effective_at", None),
    )


def load_active_spec_schema_for_pricing_with_session(
    session: Session,
    *,
    category_code: str,
) -> dict[str, Any] | None:
    schema = get_category_spec_schema_with_session(session, category_code=category_code)
    if schema is None:
        return None
    return {
        "schemaId": schema.get("schemaId"),
        "categoryCode": schema.get("categoryCode"),
        "templateVersion": schema.get("templateVersion"),
        "lockingAttrs": list(schema.get("lockingAttrs") or []),
        "requiredAttrs": list(schema.get("requiredAttrs") or []),
        "variantAttrs": list(schema.get("variantAttrs") or []),
        "conditionAttrs": list(schema.get("conditionAttrs") or []),
        "weights": dict(schema.get("weights") or {}),
        "validFrom": schema.get("validFrom"),
        "validTo": schema.get("validTo"),
        "summary": dict(schema.get("summary") or {}),
    }


def upsert_active_schema_snapshot_with_session(
    session: Session,
    *,
    template: CategoryAttrTemplate,
    created_by: str | None = None,
) -> SkuSpecSchemaSnapshot:
    category = getattr(template, "category", None)
    if category is None and getattr(template, "category_id", None):
        category = session.get(Category, template.category_id)
    if category is None:
        raise SpecSchemaSnapshotError("Template category is required to build schema snapshot.")
    template.category = category

    derived = derive_spec_schema_from_template(
        template,
        persisted=True,
        created_by=created_by,
        valid_from=getattr(template, "effective_at", None),
    )
    existing = session.execute(
        select(SkuSpecSchemaSnapshot)
        .where(SkuSpecSchemaSnapshot.category_code == derived["categoryCode"])
        .where(SkuSpecSchemaSnapshot.template_version == int(derived["templateVersion"]))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if existing is None:
        existing = SkuSpecSchemaSnapshot(
            category_id=str(category.id),
            category_code=str(category.code),
            template_id=str(template.id),
            template_version=int(template.version),
            valid_from=getattr(template, "effective_at", None) or now,
            created_by=created_by,
        )
        session.add(existing)

    existing.category = category
    existing.template = template
    existing.category_id = str(category.id)
    existing.category_code = str(category.code)
    existing.template_id = str(template.id)
    existing.template_version = int(template.version)
    existing.locking_attrs = list(derived["lockingAttrs"])
    existing.required_attrs = list(derived["requiredAttrs"])
    existing.variant_attrs = list(derived["variantAttrs"])
    existing.condition_attrs = list(derived["conditionAttrs"])
    existing.weights = dict(derived["weights"])
    existing.normalization = dict(derived["normalization"] or {}) or None
    existing.enum_values = dict(derived["enumValues"] or {}) or None
    existing.valid_to = None
    if created_by:
        existing.created_by = created_by

    for active in session.execute(
        select(SkuSpecSchemaSnapshot)
        .where(SkuSpecSchemaSnapshot.category_code == str(category.code))
        .where(SkuSpecSchemaSnapshot.valid_to.is_(None))
    ).scalars().all():
        if active is existing:
            continue
        if getattr(active, "schema_id", None) == getattr(existing, "schema_id", None):
            continue
        active.valid_to = now

    return existing


def derive_spec_schema_from_template(
    template: CategoryAttrTemplate,
    *,
    persisted: bool,
    created_by: str | None,
    valid_from: datetime | None,
) -> dict[str, Any]:
    category = getattr(template, "category", None)
    item_payloads = _template_item_payloads(list(getattr(template, "items", []) or []))
    locking_attrs = [item["attributeCode"] for item in item_payloads if item["role"] == "locking"]
    required_attrs = [
        item["attributeCode"]
        for item in item_payloads
        if item["role"] == "locking" and bool(item["required"])
    ]
    variant_attrs = [item["attributeCode"] for item in item_payloads if item["role"] == "variant"]
    condition_attrs = [item["attributeCode"] for item in item_payloads if item["role"] == "condition"]
    weights = {
        item["attributeCode"]: item["weight"]
        for item in item_payloads
        if item["role"] == "locking" and item.get("weight") not in (None, 0, 0.0)
    }
    normalization = {
        item["attributeCode"]: item["normalization"]
        for item in item_payloads
        if item.get("normalization") is not None
    }
    enum_values = {
        item["attributeCode"]: item["enumValues"]
        for item in item_payloads
        if item.get("enumValues") is not None
    }
    schema_id = getattr(template, "schema_id", None)
    return {
        "schemaId": schema_id,
        "categoryId": getattr(category, "id", None) or getattr(template, "category_id", None),
        "categoryCode": getattr(category, "code", None),
        "categoryName": getattr(category, "name", None),
        "templateId": getattr(template, "id", None),
        "templateVersion": int(getattr(template, "version", 1) or 1),
        "lockingAttrs": locking_attrs,
        "requiredAttrs": required_attrs,
        "variantAttrs": variant_attrs,
        "conditionAttrs": condition_attrs,
        "weights": weights,
        "normalization": normalization,
        "enumValues": enum_values,
        "validFrom": _json_safe_value(valid_from),
        "validTo": None,
        "createdBy": created_by,
        "persisted": persisted,
        "isCurrent": True,
        "summary": _schema_summary(
            locking_attrs=locking_attrs,
            required_attrs=required_attrs,
            variant_attrs=variant_attrs,
            condition_attrs=condition_attrs,
            is_current=True,
        ),
        "items": item_payloads,
    }


def serialize_spec_schema_snapshot(row: SkuSpecSchemaSnapshot) -> dict[str, Any]:
    template = getattr(row, "template", None)
    items = _template_item_payloads(list(getattr(template, "items", []) or [])) if template is not None else []
    locking_attrs = list(getattr(row, "locking_attrs", []) or [])
    required_attrs = list(getattr(row, "required_attrs", []) or [])
    variant_attrs = list(getattr(row, "variant_attrs", []) or [])
    condition_attrs = list(getattr(row, "condition_attrs", []) or [])
    is_current = getattr(row, "valid_to", None) is None
    category = getattr(row, "category", None)
    return {
        "schemaId": getattr(row, "schema_id", None),
        "categoryId": getattr(row, "category_id", None),
        "categoryCode": getattr(row, "category_code", None),
        "categoryName": getattr(category, "name", None),
        "templateId": getattr(row, "template_id", None),
        "templateVersion": int(getattr(row, "template_version", 1) or 1),
        "lockingAttrs": locking_attrs,
        "requiredAttrs": required_attrs,
        "variantAttrs": variant_attrs,
        "conditionAttrs": condition_attrs,
        "weights": dict(getattr(row, "weights", None) or {}),
        "normalization": dict(getattr(row, "normalization", None) or {}),
        "enumValues": dict(getattr(row, "enum_values", None) or {}),
        "validFrom": _json_safe_value(getattr(row, "valid_from", None)),
        "validTo": _json_safe_value(getattr(row, "valid_to", None)),
        "createdBy": getattr(row, "created_by", None),
        "persisted": True,
        "isCurrent": is_current,
        "summary": _schema_summary(
            locking_attrs=locking_attrs,
            required_attrs=required_attrs,
            variant_attrs=variant_attrs,
            condition_attrs=condition_attrs,
            is_current=is_current,
        ),
        "items": items,
    }


def normalize_template_role(value: Any) -> str:
    role = str(value or "descriptive").strip().lower()
    if role not in VALID_TEMPLATE_ITEM_ROLES:
        raise SpecSchemaSnapshotError(
            f"Invalid template item role: {value}. Expected one of: {', '.join(sorted(VALID_TEMPLATE_ITEM_ROLES))}"
        )
    return role


def normalize_template_weight(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    weight = Decimal(str(value))
    if weight < 0 or weight > 1:
        raise SpecSchemaSnapshotError("Template item weight must be between 0 and 1.")
    return weight


def template_item_schema_payload_from_input(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": normalize_template_role(
            item.get("role")
            if item.get("role") is not None
            else item.get("templateRole")
            if item.get("templateRole") is not None
            else item.get("attributeRole")
        ),
        "weight": normalize_template_weight(item.get("weight")),
        "normalization": _coerce_optional_json(item.get("normalization")),
        "enumValues": _coerce_optional_json(
            item.get("enumValues") if "enumValues" in item else item.get("enum_values")
        ),
    }


def evaluate_pricing_record_schema(
    *,
    record: dict[str, Any],
    schema: dict[str, Any] | None,
) -> dict[str, Any]:
    if not schema:
        return {
            "schemaId": None,
            "status": "no_schema",
            "missingRequiredAttrs": [],
            "requiredAttrs": [],
        }
    required_attrs = list(schema.get("requiredAttrs") or [])
    missing_attrs = [
        attr_code
        for attr_code in required_attrs
        if not _has_value(_record_value(record, attr_code))
    ]
    return {
        "schemaId": schema.get("schemaId"),
        "templateVersion": schema.get("templateVersion"),
        "status": "incomplete" if missing_attrs else "complete",
        "missingRequiredAttrs": missing_attrs,
        "requiredAttrs": required_attrs,
        "lockingAttrs": list(schema.get("lockingAttrs") or []),
    }


def _load_active_snapshot(
    session: Session,
    *,
    category_code: str,
) -> SkuSpecSchemaSnapshot | None:
    return session.execute(
        select(SkuSpecSchemaSnapshot)
        .where(SkuSpecSchemaSnapshot.category_code == category_code)
        .where(SkuSpecSchemaSnapshot.valid_to.is_(None))
        .order_by(SkuSpecSchemaSnapshot.valid_from.desc(), SkuSpecSchemaSnapshot.schema_id.desc())
    ).scalar_one_or_none()


def _load_active_or_latest_template(
    session: Session,
    *,
    category_code: str,
) -> CategoryAttrTemplate | None:
    runtime_template = session.execute(
        select(CategoryAttrTemplate)
        .join(CategoryRuntimeProfile, CategoryRuntimeProfile.active_template_id == CategoryAttrTemplate.id)
        .join(Category, Category.id == CategoryRuntimeProfile.category_id)
        .where(Category.code == category_code)
        .where(CategoryRuntimeProfile.status == "ACTIVE")
    ).scalar_one_or_none()
    if runtime_template is not None:
        return runtime_template
    return session.execute(
        select(CategoryAttrTemplate)
        .join(Category, Category.id == CategoryAttrTemplate.category_id)
        .where(Category.code == category_code)
        .order_by(CategoryAttrTemplate.version.desc(), CategoryAttrTemplate.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _template_item_payloads(items: list[CategoryAttrTemplateItem]) -> list[dict[str, Any]]:
    payloads = []
    for item in sorted(
        items,
        key=lambda entry: (
            int(getattr(entry, "sort_no", 0) or 0),
            str(getattr(getattr(entry, "attribute", None), "code", "") or ""),
        ),
    ):
        attribute = getattr(item, "attribute", None)
        role = normalize_template_role(getattr(item, "role", "descriptive"))
        weight = normalize_template_weight(getattr(item, "weight", None))
        payloads.append(
            {
                "attributeCode": getattr(attribute, "code", None),
                "attributeId": getattr(attribute, "id", None),
                "attributeName": getattr(attribute, "name", None),
                "role": role,
                "required": bool(getattr(item, "is_required", False)),
                "weight": _decimal_to_float(weight),
                "normalization": _json_safe_value(getattr(item, "normalization", None)),
                "enumValues": _json_safe_value(getattr(item, "enum_values", None)),
                "sortNo": int(getattr(item, "sort_no", 0) or 0),
            }
        )
    return [payload for payload in payloads if payload.get("attributeCode")]


def _schema_summary(
    *,
    locking_attrs: list[str],
    required_attrs: list[str],
    variant_attrs: list[str],
    condition_attrs: list[str],
    is_current: bool,
) -> dict[str, Any]:
    return {
        "lockingAttrCount": len(locking_attrs),
        "requiredAttrCount": len(required_attrs),
        "variantAttrCount": len(variant_attrs),
        "conditionAttrCount": len(condition_attrs),
        "isCurrent": is_current,
    }


def _record_value(record: dict[str, Any], attr_code: str) -> Any:
    aliases = {
        "brand_name": ("brand_name", "brand"),
        "model_name": ("model_name", "product_label"),
        "ram_gb": ("ram_gb", "memory_gb"),
    }
    for key in aliases.get(attr_code, (attr_code,)):
        value = record.get(key)
        if _has_value(value):
            return value
    return None


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _coerce_optional_json(value: Any) -> Any:
    if value in (None, ""):
        return None
    return value


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return _decimal_to_float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_value(entry) for key, entry in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(entry) for entry in value]
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return enum_value
    return value
