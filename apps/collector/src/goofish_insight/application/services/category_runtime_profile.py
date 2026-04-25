from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import session_scope
from ...models import Category, CategoryAttrTemplate, CategoryRuntimeProfile, ProductAttrAuditLog


class CategoryRuntimeProfileError(RuntimeError):
    pass


def list_category_runtime_profiles(
    *,
    status: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return list_category_runtime_profiles_with_session(
            session,
            status=status,
        )


def list_category_runtime_profiles_with_session(
    session: Session,
    *,
    status: str | None = None,
) -> dict[str, Any]:
    rows = list(session.execute(select(CategoryRuntimeProfile)).scalars().all())
    if status:
        normalized_status = status.strip().upper()
        rows = [row for row in rows if str(row.status or "").upper() == normalized_status]
    items = [
        serialize_category_runtime_profile(row)
        for row in sorted(
            rows,
            key=lambda row: (
                str(getattr(getattr(row, "category", None), "code", "") or ""),
                str(row.id or ""),
            ),
        )
    ]
    return {
        "total": len(items),
        "items": items,
    }


def get_category_runtime_profile(
    *,
    category_id: str | None = None,
    category_code: str | None = None,
) -> dict[str, Any] | None:
    with session_scope() as session:
        row = _resolve_category_runtime_profile(
            session,
            category_id=category_id,
            category_code=category_code,
        )
        return serialize_category_runtime_profile(row)


def upsert_category_runtime_profile(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = upsert_category_runtime_profile_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def upsert_category_runtime_profile_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_operator_id = (operator_id or "").strip()
    if not normalized_operator_id:
        raise CategoryRuntimeProfileError("operator_id is required.")

    category_id = _normalize_optional_string(payload.get("categoryId"))
    category_code = _normalize_optional_string(payload.get("categoryCode"))
    prompt_profile = _normalize_optional_string(payload.get("promptProfile"))
    if not prompt_profile:
        raise CategoryRuntimeProfileError("promptProfile is required.")

    category = _resolve_category(session, category_id=category_id, category_code=category_code)
    if category is None:
        raise CategoryRuntimeProfileError("Target category was not found.")

    active_template_id = _normalize_optional_string(payload.get("activeTemplateId"))
    active_template = None
    if active_template_id:
        active_template = session.get(CategoryAttrTemplate, active_template_id)
        if active_template is None:
            raise CategoryRuntimeProfileError(f"Template not found: {active_template_id}")
        if str(active_template.category_id) != str(category.id):
            raise CategoryRuntimeProfileError("activeTemplateId does not belong to the selected category.")

    existing = _resolve_category_runtime_profile(session, category_id=str(category.id))
    before_json = serialize_category_runtime_profile(existing)
    if existing is None:
        row = CategoryRuntimeProfile(
            category_id=str(category.id),
            active_template_id=str(active_template.id) if active_template is not None else None,
            prompt_profile=prompt_profile,
            extractor_profile=_normalize_optional_string(payload.get("extractorProfile")),
            validator_profile=_normalize_optional_string(payload.get("validatorProfile")),
            llm_provider_override=_normalize_optional_string(payload.get("llmProviderOverride")),
            llm_model_override=_normalize_optional_string(payload.get("llmModelOverride")),
            status=_normalize_optional_string(payload.get("status")) or "ACTIVE",
            metadata_json=dict(payload.get("metadata") or {}),
        )
        session.add(row)
        session.flush()
        action = "CREATE_CATEGORY_RUNTIME_PROFILE_DRY_RUN" if dry_run else "CREATE_CATEGORY_RUNTIME_PROFILE"
    else:
        row = existing
        row.active_template_id = str(active_template.id) if active_template is not None else None
        row.prompt_profile = prompt_profile
        row.extractor_profile = _normalize_optional_string(payload.get("extractorProfile"))
        row.validator_profile = _normalize_optional_string(payload.get("validatorProfile"))
        row.llm_provider_override = _normalize_optional_string(payload.get("llmProviderOverride"))
        row.llm_model_override = _normalize_optional_string(payload.get("llmModelOverride"))
        row.status = _normalize_optional_string(payload.get("status")) or "ACTIVE"
        row.metadata_json = dict(payload.get("metadata") or {})
        session.flush()
        action = "UPDATE_CATEGORY_RUNTIME_PROFILE_DRY_RUN" if dry_run else "UPDATE_CATEGORY_RUNTIME_PROFILE"

    after_json = serialize_category_runtime_profile(row)
    audit_log = ProductAttrAuditLog(
        operator_id=normalized_operator_id,
        resource_type="category_runtime_profile",
        resource_id=row.id,
        action=action,
        before_json=before_json,
        after_json=after_json,
    )
    session.add(audit_log)
    session.flush()
    return {
        "dryRun": dry_run,
        "profile": after_json,
        "auditLogId": audit_log.id,
    }


def serialize_category_runtime_profile(
    row: CategoryRuntimeProfile | None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    category = getattr(row, "category", None)
    template = getattr(row, "active_template", None)
    return {
        "id": row.id,
        "categoryId": row.category_id,
        "categoryCode": getattr(category, "code", None),
        "categoryName": getattr(category, "name", None),
        "activeTemplateId": row.active_template_id,
        "activeTemplateVersion": getattr(template, "version", None),
        "promptProfile": row.prompt_profile,
        "extractorProfile": row.extractor_profile,
        "validatorProfile": row.validator_profile,
        "llmProviderOverride": row.llm_provider_override,
        "llmModelOverride": row.llm_model_override,
        "status": row.status,
        "metadata": _json_safe_value(dict(row.metadata_json or {})),
        "createdAt": _json_safe_value(getattr(row, "created_at", None)),
        "updatedAt": _json_safe_value(getattr(row, "updated_at", None)),
    }


def _resolve_category_runtime_profile(
    session: Session,
    *,
    category_id: str | None = None,
    category_code: str | None = None,
) -> CategoryRuntimeProfile | None:
    normalized_category_id = _normalize_optional_string(category_id)
    normalized_category_code = _normalize_optional_string(category_code)
    if normalized_category_id:
        rows = list(
            session.execute(
                select(CategoryRuntimeProfile).where(CategoryRuntimeProfile.category_id == normalized_category_id)
            ).scalars().all()
        )
        return rows[0] if rows else None
    if normalized_category_code:
        category = _resolve_category(session, category_code=normalized_category_code)
        if category is None:
            return None
        rows = list(
            session.execute(
                select(CategoryRuntimeProfile).where(CategoryRuntimeProfile.category_id == str(category.id))
            ).scalars().all()
        )
        return rows[0] if rows else None
    return None


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
