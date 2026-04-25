from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...category_compat import get_category_scope_profile
from ...category_runtime_defaults import get_category_runtime_default, recommended_prompt_profile_for_category
from ...db import session_scope
from ...models import Category, CategoryAttrTemplate, ProductAttrAuditLog
from .category_runtime_profile import (
    serialize_category_runtime_profile,
    upsert_category_runtime_profile_with_session,
)


class CategoryConfigError(RuntimeError):
    pass


def list_category_configs(*, status: str | None = None) -> dict[str, Any]:
    with session_scope() as session:
        return list_category_configs_with_session(session, status=status)


def list_category_configs_with_session(
    session: Session,
    *,
    status: str | None = None,
) -> dict[str, Any]:
    rows = list(session.execute(select(Category)).scalars().all())
    if status:
        normalized_status = str(status).strip().upper()
        rows = [row for row in rows if str(row.status or "").upper() == normalized_status]
    items = [
        serialize_category_config(row)
        for row in sorted(rows, key=lambda row: (int(getattr(row, "level", 0) or 0), str(row.code or "")))
    ]
    return {
        "total": len(items),
        "items": items,
    }


def get_category_config(
    *,
    category_id: str | None = None,
    category_code: str | None = None,
) -> dict[str, Any] | None:
    with session_scope() as session:
        row = _resolve_category(session, category_id=category_id, category_code=category_code)
        return serialize_category_config(row)


def upsert_category_config(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = upsert_category_config_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def upsert_category_config_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_operator_id = _normalize_optional_string(operator_id)
    if not normalized_operator_id:
        raise CategoryConfigError("operator_id is required.")

    category_id = _normalize_optional_string(payload.get("categoryId"))
    category_code = _normalize_optional_string(payload.get("code"))
    category_name = _normalize_optional_string(payload.get("name"))
    category_path = _normalize_optional_string(payload.get("path"))
    category_level = payload.get("level")
    if not category_code:
        raise CategoryConfigError("code is required.")
    if not category_name:
        raise CategoryConfigError("name is required.")
    if not category_path:
        raise CategoryConfigError("path is required.")
    if category_level in (None, ""):
        raise CategoryConfigError("level is required.")

    existing = _resolve_category(session, category_id=category_id, category_code=category_code)
    before_json = serialize_category_config(existing)

    conflicting = _resolve_category(session, category_code=category_code)
    if conflicting is not None and existing is not None and str(conflicting.id) != str(existing.id):
        raise CategoryConfigError(f"Category code already exists: {category_code}")
    if conflicting is not None and existing is None:
        raise CategoryConfigError(f"Category code already exists: {category_code}")

    if existing is None:
        row = Category(
            code=category_code,
            name=category_name,
            path=category_path,
            level=int(category_level),
            status=_normalize_optional_string(payload.get("status")) or "ACTIVE",
        )
        if category_id:
            if session.get(Category, category_id) is not None:
                raise CategoryConfigError(f"Category already exists: {category_id}")
            row.id = category_id
        session.add(row)
        session.flush()
        action = "CREATE_CATEGORY_CONFIG_DRY_RUN" if dry_run else "CREATE_CATEGORY_CONFIG"
    else:
        row = existing
        row.code = category_code
        row.name = category_name
        row.path = category_path
        row.level = int(category_level)
        row.status = _normalize_optional_string(payload.get("status")) or "ACTIVE"
        session.flush()
        action = "UPDATE_CATEGORY_CONFIG_DRY_RUN" if dry_run else "UPDATE_CATEGORY_CONFIG"

    runtime_payload = _build_runtime_payload(row.id, payload)
    runtime_result = None
    if runtime_payload is not None:
        runtime_result = upsert_category_runtime_profile_with_session(
            session,
            payload=runtime_payload,
            operator_id=normalized_operator_id,
            dry_run=dry_run,
        )
        session.flush()

    after_json = serialize_category_config(row)
    audit_log = ProductAttrAuditLog(
        operator_id=normalized_operator_id,
        resource_type="category",
        resource_id=row.id,
        action=action,
        before_json=before_json,
        after_json=after_json,
    )
    session.add(audit_log)
    session.flush()
    return {
        "dryRun": dry_run,
        "category": after_json,
        "runtimeProfile": runtime_result["profile"] if runtime_result is not None else after_json.get("runtimeProfile"),
        "auditLogId": audit_log.id,
    }


def serialize_category_config(row: Category | None) -> dict[str, Any] | None:
    if row is None:
        return None
    templates = sorted(
        list(getattr(row, "templates", []) or []),
        key=lambda item: (-int(getattr(item, "version", 0) or 0), str(getattr(item, "id", "") or "")),
    )
    latest_template = templates[0] if templates else None
    runtime_profile = serialize_category_runtime_profile(getattr(row, "runtime_profile", None))
    scope_profile = get_category_scope_profile(row.code)
    runtime_default = get_category_runtime_default(row.code)
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "path": row.path,
        "level": row.level,
        "status": row.status,
        "legacyBusinessDomains": list(scope_profile.legacy_business_domains) if scope_profile is not None else [],
        "recommendedPromptProfile": recommended_prompt_profile_for_category(row.code)
        or getattr(scope_profile, "prompt_profile", None),
        "templateCount": len(templates),
        "activeTemplateId": runtime_profile.get("activeTemplateId") if runtime_profile else None,
        "latestTemplate": _serialize_template_summary(latest_template),
        "templateOptions": [_serialize_template_summary(template) for template in templates],
        "runtimeProfile": runtime_profile,
        "taskCount": len(list(getattr(row, "crawl_tasks", []) or [])),
        "modelCount": len(list(getattr(row, "model_catalog_entries", []) or [])),
        "createdAt": _json_safe_value(getattr(row, "created_at", None)),
        "updatedAt": _json_safe_value(getattr(row, "updated_at", None)),
    }


def _build_runtime_payload(category_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    runtime_keys = {
        "activeTemplateId",
        "promptProfile",
        "extractorProfile",
        "validatorProfile",
        "llmProviderOverride",
        "llmModelOverride",
        "runtimeStatus",
        "runtimeMetadata",
    }
    if not any(key in payload for key in runtime_keys):
        return None
    prompt_profile = _normalize_optional_string(payload.get("promptProfile"))
    if not prompt_profile:
        runtime_default = get_category_runtime_default(payload.get("code"))
        if runtime_default is not None:
            prompt_profile = runtime_default.prompt_profile
        else:
            scope_profile = get_category_scope_profile(payload.get("code"))
            prompt_profile = getattr(scope_profile, "prompt_profile", None)
    if not prompt_profile:
        raise CategoryConfigError("promptProfile is required when runtime profile is being updated.")
    runtime_default = get_category_runtime_default(payload.get("code"))
    return {
        "categoryId": category_id,
        "activeTemplateId": _normalize_optional_string(payload.get("activeTemplateId")),
        "promptProfile": prompt_profile,
        "extractorProfile": _normalize_optional_string(payload.get("extractorProfile"))
        or getattr(runtime_default, "extractor_profile", None),
        "validatorProfile": _normalize_optional_string(payload.get("validatorProfile"))
        or getattr(runtime_default, "validator_profile", None),
        "llmProviderOverride": _normalize_optional_string(payload.get("llmProviderOverride")),
        "llmModelOverride": _normalize_optional_string(payload.get("llmModelOverride")),
        "status": _normalize_optional_string(payload.get("runtimeStatus")) or "ACTIVE",
        "metadata": dict(payload.get("runtimeMetadata") or {}),
    }


def _resolve_category(
    session: Session,
    *,
    category_id: str | None = None,
    category_code: str | None = None,
) -> Category | None:
    normalized_category_id = _normalize_optional_string(category_id)
    normalized_category_code = _normalize_optional_string(category_code)
    if normalized_category_id:
        return session.get(Category, normalized_category_id)
    if normalized_category_code:
        rows = list(session.execute(select(Category).where(Category.code == normalized_category_code)).scalars().all())
        return rows[0] if rows else None
    return None


def _serialize_template_summary(template: CategoryAttrTemplate | None) -> dict[str, Any] | None:
    if template is None:
        return None
    status = getattr(template, "status", None)
    return {
        "id": template.id,
        "version": template.version,
        "status": getattr(status, "value", status),
        "itemCount": len(list(getattr(template, "items", []) or [])),
        "createdAt": _json_safe_value(getattr(template, "created_at", None)),
        "updatedAt": _json_safe_value(getattr(template, "updated_at", None)),
    }


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
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(entry) for entry in value]
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value
