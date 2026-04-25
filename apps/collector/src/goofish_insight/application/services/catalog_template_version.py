from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import session_scope
from ...models import (
    Category,
    CategoryAttrTemplate,
    CategoryAttrTemplateItem,
    ProductAttrAuditLog,
    TemplateStatus,
)
from .attribute_binding_resolution import resolve_attribute_bindings
from .spec_schema_snapshots import (
    SpecSchemaSnapshotError,
    template_item_schema_payload_from_input,
    upsert_active_schema_snapshot_with_session,
)


class CatalogTemplateVersionError(RuntimeError):
    pass


def persist_catalog_template_version_payload(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = persist_catalog_template_version_payload_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def persist_catalog_template_version_payload_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not operator_id.strip():
        raise CatalogTemplateVersionError("operator_id is required.")

    category_id = _require_uuid(payload.get("categoryId"), "categoryId")
    template_payload = dict(payload.get("template") or {})
    if not template_payload:
        raise CatalogTemplateVersionError("template is required.")

    category = session.get(Category, category_id)
    if category is None:
        raise CatalogTemplateVersionError(f"Category not found: {category_id}")

    template_items = list(template_payload.get("items") or [])
    if not template_items:
        raise CatalogTemplateVersionError("template.items are required.")

    attribute_codes = [str(item["attributeCode"]) for item in template_items]
    if len(attribute_codes) != len(set(attribute_codes)):
        raise CatalogTemplateVersionError("template.items contains duplicate attributeCode.")

    attribute_map = resolve_attribute_bindings(
        session,
        items=template_items,
        error_factory=CatalogTemplateVersionError,
    )

    version = int(template_payload["version"])
    existing_template = session.execute(
        select(CategoryAttrTemplate).where(
            CategoryAttrTemplate.category_id == category_id,
            CategoryAttrTemplate.version == version,
        )
    ).scalar_one_or_none()
    if existing_template is not None:
        raise CatalogTemplateVersionError(
            f"Template version already exists for category {category_id}: {version}"
        )

    template = CategoryAttrTemplate(
        category_id=category_id,
        version=version,
        status=_coerce_template_status(template_payload.get("status")),
        effective_at=_coerce_datetime(template_payload.get("effectiveAt")),
        published_by=template_payload.get("publishedBy"),
    )
    template_id = _validate_optional_uuid(template_payload.get("id"), "template.id")
    if template_id:
        if session.get(CategoryAttrTemplate, template_id) is not None:
            raise CatalogTemplateVersionError(f"Template already exists: {template_id}")
        template.id = template_id
    session.add(template)
    session.flush()

    created_items: list[CategoryAttrTemplateItem] = []
    for item_payload in template_items:
        attribute = attribute_map[str(item_payload["attributeCode"])]
        try:
            schema_payload = template_item_schema_payload_from_input(item_payload)
        except SpecSchemaSnapshotError as exc:
            raise CatalogTemplateVersionError(str(exc)) from exc
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
        created_items.append(item)
    template.items = created_items

    schema_snapshot = None
    if template.status == TemplateStatus.PUBLISHED:
        try:
            schema_snapshot = upsert_active_schema_snapshot_with_session(
                session,
                template=template,
                created_by=operator_id,
            )
        except SpecSchemaSnapshotError as exc:
            raise CatalogTemplateVersionError(str(exc)) from exc
        session.flush()

    audit_log = ProductAttrAuditLog(
        operator_id=operator_id,
        resource_type="category_attr_template",
        resource_id=template.id,
        action="CREATE_TEMPLATE_VERSION_DRY_RUN" if dry_run else "CREATE_TEMPLATE_VERSION",
        before_json=None,
        after_json={
            "requestId": payload.get("requestId"),
            "categoryId": category.id,
            "templateId": template.id,
            "templateVersion": template.version,
            "attributeCodes": attribute_codes,
        },
    )
    session.add(audit_log)
    session.flush()

    return {
        "dryRun": dry_run,
        "requestId": payload.get("requestId"),
        "categoryId": category.id,
        "templateId": template.id,
        "templateVersion": template.version,
        "templateItemCount": len(template_items),
        "schemaId": getattr(schema_snapshot, "schema_id", None),
        "auditLogId": audit_log.id,
    }


def _coerce_template_status(value: Any) -> TemplateStatus:
    raw = str(value or TemplateStatus.DRAFT.value).upper()
    try:
        return TemplateStatus(raw)
    except ValueError as exc:
        raise CatalogTemplateVersionError(f"Invalid template status: {value}") from exc


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise CatalogTemplateVersionError(f"Invalid effectiveAt: {value}") from exc


def _validate_optional_uuid(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        UUID(raw)
    except ValueError as exc:
        raise CatalogTemplateVersionError(f"{field_name} must be a UUID string.") from exc
    return raw


def _require_uuid(value: Any, field_name: str) -> str:
    raw = _validate_optional_uuid(value, field_name)
    if raw is None:
        raise CatalogTemplateVersionError(f"{field_name} is required.")
    return raw
