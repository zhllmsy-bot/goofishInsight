from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...category_runtime_defaults import recommended_prompt_profile_for_category
from ...db import session_scope
from ...models import (
    AttributeDefinition,
    Category,
    CategoryAttrTemplate,
    CategoryAttrTemplateItem,
    ProductAttrAuditLog,
    TemplateStatus,
)
from .attribute_binding_resolution import resolve_attribute_bindings
from .category_runtime_profile import upsert_category_runtime_profile_with_session


class TemplateConfigError(RuntimeError):
    pass


def list_template_configs(
    *,
    status: str | None = None,
    category_code: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return list_template_configs_with_session(
            session,
            status=status,
            category_code=category_code,
        )


def list_template_configs_with_session(
    session: Session,
    *,
    status: str | None = None,
    category_code: str | None = None,
) -> dict[str, Any]:
    rows = list(session.execute(select(CategoryAttrTemplate)).scalars().all())
    normalized_status = _normalize_optional_string(status)
    normalized_category_code = _normalize_optional_string(category_code)
    if normalized_status:
        rows = [
            row
            for row in rows
            if _normalize_optional_string(getattr(getattr(row, "status", None), "value", getattr(row, "status", None)))
            == normalized_status
        ]
    if normalized_category_code:
        rows = [
            row
            for row in rows
            if normalized_category_code
            == _normalize_optional_string(getattr(getattr(row, "category", None), "code", None))
        ]
    items = [
        serialize_template_config(row, include_items=False, include_diff=False)
        for row in sorted(
            rows,
            key=lambda row: (
                str(getattr(getattr(row, "category", None), "code", "") or ""),
                -int(getattr(row, "version", 0) or 0),
                str(getattr(row, "id", "") or ""),
            ),
        )
    ]
    return {
        "status": normalized_status,
        "categoryCode": normalized_category_code,
        "total": len(items),
        "items": items,
    }


def get_template_config(
    *,
    template_id: str,
    compare_to_template_id: str | None = None,
) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(CategoryAttrTemplate, template_id)
        if row is None:
            return None
        return serialize_template_config(
            row,
            include_items=True,
            include_diff=True,
            compare_to_template_id=compare_to_template_id,
            session=session,
        )


def preview_template_config_diff(
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    with session_scope() as session:
        return preview_template_config_diff_with_session(session, payload=payload)


def preview_template_config_diff_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    category = _resolve_category_from_payload(session, payload)
    if category is None:
        raise TemplateConfigError("Category not found for template diff preview.")
    target_items = _normalize_template_items(payload.get("items"))
    baseline = _resolve_baseline_template(session, category=category, payload=payload)
    return _build_template_diff_preview(
        category=category,
        target_items=target_items,
        baseline=baseline,
    )


def upsert_template_config(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = upsert_template_config_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def upsert_template_config_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_operator_id = _normalize_optional_string(operator_id)
    if not normalized_operator_id:
        raise TemplateConfigError("operator_id is required.")

    category = _resolve_category_from_payload(session, payload)
    if category is None:
        raise TemplateConfigError("Category not found.")

    template_id = _normalize_optional_string(payload.get("templateId"))
    target_items = _normalize_template_items(payload.get("items"))
    if not target_items:
        raise TemplateConfigError("items are required.")

    attribute_by_code = resolve_attribute_bindings(
        session,
        items=target_items,
        error_factory=TemplateConfigError,
    )

    existing = session.get(CategoryAttrTemplate, template_id) if template_id else None
    if template_id and existing is None:
        raise TemplateConfigError(f"Template not found: {template_id}")
    if existing is not None and str(existing.category_id) != str(category.id):
        raise TemplateConfigError("Selected template does not belong to the selected category.")

    before_json = serialize_template_config(existing, include_items=True, include_diff=False)
    template_version = payload.get("version")
    resolved_version = _resolve_template_version(
        category=category,
        existing=existing,
        requested_version=template_version,
    )
    _ensure_category_version_available(
        category=category,
        existing=existing,
        version=resolved_version,
    )

    if existing is None:
        row = CategoryAttrTemplate(
            category_id=str(category.id),
            version=resolved_version,
            status=_coerce_template_status(payload.get("status")),
            effective_at=_coerce_datetime(payload.get("effectiveAt")),
            published_by=_resolve_published_by(
                operator_id=normalized_operator_id,
                status=_coerce_template_status(payload.get("status")),
                published_by=payload.get("publishedBy"),
            ),
        )
        row.category = category
        if template_id:
            row.id = template_id
        session.add(row)
        session.flush()
        action = "CREATE_TEMPLATE_CONFIG_DRY_RUN" if dry_run else "CREATE_TEMPLATE_CONFIG"
    else:
        row = existing
        row.version = resolved_version
        row.status = _coerce_template_status(payload.get("status"))
        row.effective_at = _coerce_datetime(payload.get("effectiveAt"))
        row.published_by = _resolve_published_by(
            operator_id=normalized_operator_id,
            status=row.status,
            published_by=payload.get("publishedBy"),
        )
        session.flush()
        action = "UPDATE_TEMPLATE_CONFIG_DRY_RUN" if dry_run else "UPDATE_TEMPLATE_CONFIG"

    _sync_template_items(
        session=session,
        template=row,
        target_items=target_items,
        attribute_by_code=attribute_by_code,
    )
    session.flush()

    runtime_result = None
    if bool(payload.get("activateOnPublish")) or bool(payload.get("bindAsActiveTemplate")):
        prompt_profile = _normalize_optional_string(payload.get("promptProfile"))
        if not prompt_profile:
            prompt_profile = _normalize_optional_string(
                getattr(getattr(category, "runtime_profile", None), "prompt_profile", None)
            ) or recommended_prompt_profile_for_category(category.code)
        if not prompt_profile:
            raise TemplateConfigError("promptProfile is required when binding template to runtime profile.")
        runtime_result = upsert_category_runtime_profile_with_session(
            session,
            payload={
                "categoryId": category.id,
                "activeTemplateId": row.id,
                "promptProfile": prompt_profile,
                "extractorProfile": _normalize_optional_string(payload.get("extractorProfile"))
                or _normalize_optional_string(getattr(getattr(category, "runtime_profile", None), "extractor_profile", None)),
                "validatorProfile": _normalize_optional_string(payload.get("validatorProfile"))
                or _normalize_optional_string(getattr(getattr(category, "runtime_profile", None), "validator_profile", None)),
                "llmProviderOverride": _normalize_optional_string(payload.get("llmProviderOverride"))
                or _normalize_optional_string(getattr(getattr(category, "runtime_profile", None), "llm_provider_override", None)),
                "llmModelOverride": _normalize_optional_string(payload.get("llmModelOverride"))
                or _normalize_optional_string(getattr(getattr(category, "runtime_profile", None), "llm_model_override", None)),
                "status": _normalize_optional_string(payload.get("runtimeStatus"))
                or _normalize_optional_string(getattr(getattr(category, "runtime_profile", None), "status", None))
                or "ACTIVE",
                "metadata": dict(payload.get("runtimeMetadata") or getattr(getattr(category, "runtime_profile", None), "metadata_json", None) or {}),
            },
            operator_id=normalized_operator_id,
            dry_run=dry_run,
        )
        session.flush()

    after_json = serialize_template_config(
        row,
        include_items=True,
        include_diff=True,
        session=session,
    )
    audit_log = ProductAttrAuditLog(
        operator_id=normalized_operator_id,
        resource_type="category_attr_template",
        resource_id=row.id,
        action=action,
        before_json=before_json,
        after_json=after_json,
    )
    session.add(audit_log)
    session.flush()
    return {
        "dryRun": dry_run,
        "template": after_json,
        "runtimeProfile": runtime_result["profile"] if runtime_result is not None else None,
        "diffPreview": after_json.get("diffPreview"),
        "auditLogId": audit_log.id,
    }


def serialize_template_config(
    row: CategoryAttrTemplate | None,
    *,
    include_items: bool = True,
    include_diff: bool = True,
    compare_to_template_id: str | None = None,
    session: Session | None = None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    status = getattr(row.status, "value", row.status)
    category = getattr(row, "category", None)
    runtime_profile = getattr(category, "runtime_profile", None)
    detail = {
        "id": row.id,
        "categoryId": row.category_id,
        "categoryCode": getattr(category, "code", None),
        "categoryName": getattr(category, "name", None),
        "version": row.version,
        "status": status,
        "effectiveAt": _json_safe_value(row.effective_at),
        "publishedBy": row.published_by,
        "itemCount": len(list(getattr(row, "items", []) or [])),
        "isActiveTemplate": str(getattr(runtime_profile, "active_template_id", "") or "") == str(row.id),
        "activePromptProfile": getattr(runtime_profile, "prompt_profile", None),
        "createdAt": _json_safe_value(getattr(row, "created_at", None)),
        "updatedAt": _json_safe_value(getattr(row, "updated_at", None)),
    }
    if include_items:
        detail["items"] = _serialize_template_items(list(getattr(row, "items", []) or []))
    else:
        detail["items"] = []
    if include_diff:
        compare_to = None
        if session is not None:
            compare_to = _resolve_compare_template_for_serialization(
                session=session,
                row=row,
                compare_to_template_id=compare_to_template_id,
            )
        detail["diffPreview"] = _build_template_diff_preview(
            category=category,
            target_items=detail["items"],
            baseline=compare_to,
        )
    return detail


def _resolve_category_from_payload(session: Session, payload: dict[str, Any]) -> Category | None:
    category_id = _normalize_optional_string(payload.get("categoryId"))
    category_code = _normalize_optional_string(payload.get("categoryCode"))
    if category_id:
        return session.get(Category, category_id)
    if category_code:
        rows = list(session.execute(select(Category).where(Category.code == category_code)).scalars().all())
        return rows[0] if rows else None
    return None


def _resolve_template_version(
    *,
    category: Category,
    existing: CategoryAttrTemplate | None,
    requested_version: Any,
) -> int:
    if existing is not None:
        if requested_version in (None, ""):
            return int(existing.version)
        return int(requested_version)
    if requested_version not in (None, ""):
        return int(requested_version)
    current_max = max((int(template.version or 0) for template in list(getattr(category, "templates", []) or [])), default=0)
    return current_max + 1


def _ensure_category_version_available(
    *,
    category: Category,
    existing: CategoryAttrTemplate | None,
    version: int,
) -> None:
    for template in list(getattr(category, "templates", []) or []):
        if existing is not None and str(template.id) == str(existing.id):
            continue
        if int(getattr(template, "version", 0) or 0) == int(version):
            raise TemplateConfigError(f"Template version already exists in category: {version}")


def _normalize_template_items(value: Any) -> list[dict[str, Any]]:
    items = []
    seen_codes: set[str] = set()
    for index, item in enumerate(list(value or [])):
        attribute_code = _normalize_optional_string(item.get("attributeCode"))
        if not attribute_code:
            raise TemplateConfigError("Each template item requires attributeCode.")
        if attribute_code in seen_codes:
            raise TemplateConfigError(f"Duplicate attributeCode in template items: {attribute_code}")
        seen_codes.add(attribute_code)
        items.append(
            {
                "attributeCode": attribute_code,
                "attributeId": _normalize_optional_string(item.get("attributeId")),
                "isRequired": bool(item.get("isRequired", False)),
                "isSale": bool(item.get("isSale", False)),
                "isFilter": bool(item.get("isFilter", False)),
                "isSearch": bool(item.get("isSearch", False)),
                "isDisplay": bool(item.get("isDisplay", True)),
                "sortNo": int(item.get("sortNo", (index + 1) * 10)),
            }
        )
    return items


def _serialize_template_items(items: list[CategoryAttrTemplateItem]) -> list[dict[str, Any]]:
    return [
        {
            "attributeCode": item.attribute.code,
            "attributeId": item.attribute.id,
            "attributeName": item.attribute.name,
            "attributeScopeType": getattr(item.attribute.scope_type, "value", item.attribute.scope_type),
            "attributeScopeId": item.attribute.scope_id,
            "dataType": getattr(item.attribute.data_type, "value", item.attribute.data_type),
            "valueScope": item.attribute.value_scope,
            "isMulti": bool(item.attribute.is_multi),
            "isRequired": bool(item.is_required),
            "isSale": bool(item.is_sale),
            "isFilter": bool(item.is_filter),
            "isSearch": bool(item.is_search),
            "isDisplay": bool(item.is_display),
            "sortNo": int(item.sort_no or 0),
            "options": [
                {
                    "optionCode": option.option_code,
                    "optionName": option.option_name,
                    "sortNo": option.sort_no,
                    "status": getattr(option.status, "value", option.status),
                }
                for option in sorted(
                    list(getattr(item.attribute, "options", []) or []),
                    key=lambda option: (int(option.sort_no or 0), str(option.option_code or "")),
                )
            ],
        }
        for item in sorted(
            items,
            key=lambda entry: (int(entry.sort_no or 0), str(getattr(getattr(entry, "attribute", None), "code", "") or "")),
        )
    ]


def _sync_template_items(
    *,
    session: Session,
    template: CategoryAttrTemplate,
    target_items: list[dict[str, Any]],
    attribute_by_code: dict[str, AttributeDefinition],
) -> None:
    existing_by_code = {
        str(item.attribute.code): item
        for item in list(getattr(template, "items", []) or [])
        if getattr(item, "attribute", None) is not None
    }
    seen_codes: set[str] = set()
    resolved_items: list[CategoryAttrTemplateItem] = []
    for item in target_items:
        code = item["attributeCode"]
        seen_codes.add(code)
        existing = existing_by_code.get(code)
        if existing is None:
            created = CategoryAttrTemplateItem(
                template_id=template.id,
                attribute_id=attribute_by_code[code].id,
                is_required=bool(item["isRequired"]),
                is_sale=bool(item["isSale"]),
                is_filter=bool(item["isFilter"]),
                is_search=bool(item["isSearch"]),
                is_display=bool(item["isDisplay"]),
                sort_no=int(item["sortNo"]),
            )
            created.attribute = attribute_by_code[code]
            created.template = template
            session.add(created)
            resolved_items.append(created)
            continue
        existing.attribute_id = attribute_by_code[code].id
        existing.attribute = attribute_by_code[code]
        existing.is_required = bool(item["isRequired"])
        existing.is_sale = bool(item["isSale"])
        existing.is_filter = bool(item["isFilter"])
        existing.is_search = bool(item["isSearch"])
        existing.is_display = bool(item["isDisplay"])
        existing.sort_no = int(item["sortNo"])
        resolved_items.append(existing)

    for code, existing in existing_by_code.items():
        if code in seen_codes:
            continue
        session.delete(existing)

    if hasattr(template, "items"):
        template.items = sorted(
            resolved_items,
            key=lambda entry: (
                int(getattr(entry, "sort_no", 0) or 0),
                str(getattr(getattr(entry, "attribute", None), "code", "") or ""),
            ),
        )


def _resolve_compare_template_for_serialization(
    *,
    session: Session,
    row: CategoryAttrTemplate,
    compare_to_template_id: str | None = None,
) -> dict[str, Any] | None:
    if compare_to_template_id:
        compare_to = session.get(CategoryAttrTemplate, compare_to_template_id)
        if compare_to is not None:
            return {
                "id": compare_to.id,
                "version": compare_to.version,
                "status": getattr(compare_to.status, "value", compare_to.status),
                "items": _serialize_template_items(list(getattr(compare_to, "items", []) or [])),
            }

    runtime_profile = getattr(getattr(row, "category", None), "runtime_profile", None)
    active_template_id = _normalize_optional_string(getattr(runtime_profile, "active_template_id", None))
    if active_template_id and active_template_id != str(row.id):
        active_template = session.get(CategoryAttrTemplate, active_template_id)
        if active_template is not None:
            return {
                "id": active_template.id,
                "version": active_template.version,
                "status": getattr(active_template.status, "value", active_template.status),
                "items": _serialize_template_items(list(getattr(active_template, "items", []) or [])),
            }

    candidate_templates = [
        template
        for template in list(getattr(getattr(row, "category", None), "templates", []) or [])
        if str(template.id) != str(row.id)
    ]
    if not candidate_templates:
        return None
    compare_to = sorted(
        candidate_templates,
        key=lambda template: (-int(getattr(template, "version", 0) or 0), str(getattr(template, "id", "") or "")),
    )[0]
    return {
        "id": compare_to.id,
        "version": compare_to.version,
        "status": getattr(compare_to.status, "value", compare_to.status),
        "items": _serialize_template_items(list(getattr(compare_to, "items", []) or [])),
    }


def _resolve_baseline_template(
    session: Session,
    *,
    category: Category,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    compare_to_template_id = _normalize_optional_string(payload.get("compareToTemplateId"))
    if compare_to_template_id:
        compare_to = session.get(CategoryAttrTemplate, compare_to_template_id)
        if compare_to is None:
            raise TemplateConfigError(f"compareToTemplateId not found: {compare_to_template_id}")
        return {
            "id": compare_to.id,
            "version": compare_to.version,
            "status": getattr(compare_to.status, "value", compare_to.status),
            "items": _serialize_template_items(list(getattr(compare_to, "items", []) or [])),
        }

    runtime_profile = getattr(category, "runtime_profile", None)
    active_template_id = _normalize_optional_string(getattr(runtime_profile, "active_template_id", None))
    if active_template_id:
        active_template = session.get(CategoryAttrTemplate, active_template_id)
        if active_template is not None:
            return {
                "id": active_template.id,
                "version": active_template.version,
                "status": getattr(active_template.status, "value", active_template.status),
                "items": _serialize_template_items(list(getattr(active_template, "items", []) or [])),
            }
    return None


def _build_template_diff_preview(
    *,
    category: Category | None,
    target_items: list[dict[str, Any]],
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    baseline_items = list((baseline or {}).get("items") or [])
    baseline_by_code = {str(item["attributeCode"]): item for item in baseline_items if _normalize_optional_string(item.get("attributeCode"))}
    target_by_code = {str(item["attributeCode"]): item for item in list(target_items or []) if _normalize_optional_string(item.get("attributeCode"))}
    added_codes = sorted(set(target_by_code) - set(baseline_by_code))
    removed_codes = sorted(set(baseline_by_code) - set(target_by_code))
    changed_items: list[dict[str, Any]] = []
    for code in sorted(set(target_by_code) & set(baseline_by_code)):
        current = target_by_code[code]
        previous = baseline_by_code[code]
        field_changes = {}
        for field in ("isRequired", "isSale", "isFilter", "isSearch", "isDisplay", "sortNo"):
            if current.get(field) != previous.get(field):
                field_changes[field] = {
                    "from": previous.get(field),
                    "to": current.get(field),
                }
        if field_changes:
            changed_items.append(
                {
                    "attributeCode": code,
                    "changes": field_changes,
                }
            )
    unchanged_count = max(len(target_by_code) - len(added_codes) - len(changed_items), 0)
    return {
        "categoryId": getattr(category, "id", None),
        "categoryCode": getattr(category, "code", None),
        "compareToTemplateId": (baseline or {}).get("id"),
        "compareToTemplateVersion": (baseline or {}).get("version"),
        "compareToTemplateStatus": (baseline or {}).get("status"),
        "targetItemCount": len(target_items),
        "compareItemCount": len(baseline_items),
        "addedAttributeCodes": added_codes,
        "removedAttributeCodes": removed_codes,
        "changedItems": changed_items,
        "unchangedItemCount": unchanged_count,
    }


def _coerce_template_status(value: Any) -> TemplateStatus:
    raw = str(value or TemplateStatus.DRAFT.value).upper()
    try:
        return TemplateStatus(raw)
    except ValueError as exc:
        raise TemplateConfigError(f"Invalid template status: {value}") from exc


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise TemplateConfigError(f"Invalid effectiveAt: {value}") from exc


def _resolve_published_by(
    *,
    operator_id: str,
    status: TemplateStatus,
    published_by: Any,
) -> str | None:
    normalized = _normalize_optional_string(published_by)
    if normalized:
        return normalized
    if status == TemplateStatus.PUBLISHED:
        return operator_id
    return None


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
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
