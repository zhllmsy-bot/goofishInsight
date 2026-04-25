from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import session_scope
from ...models import Category, CategoryModelAlias, CategoryModelCatalog, ProductAttrAuditLog
from .task_model_catalog_sync import sync_category_model_catalog_to_tasks_with_session


class ModelConfigError(RuntimeError):
    pass


def list_model_configs(
    *,
    status: str | None = None,
    category_code: str | None = None,
    brand_name: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return list_model_configs_with_session(
            session,
            status=status,
            category_code=category_code,
            brand_name=brand_name,
        )


def list_model_configs_with_session(
    session: Session,
    *,
    status: str | None = None,
    category_code: str | None = None,
    brand_name: str | None = None,
) -> dict[str, Any]:
    rows = list(session.execute(select(CategoryModelCatalog)).scalars().all())
    normalized_status = _normalize_optional_string(status)
    normalized_category_code = _normalize_optional_string(category_code)
    normalized_brand_name = _normalize_optional_string(brand_name)
    if normalized_status:
        rows = [row for row in rows if _normalize_optional_string(row.status) == normalized_status]
    if normalized_category_code:
        rows = [
            row
            for row in rows
            if normalized_category_code
            == _normalize_optional_string(getattr(getattr(row, "category", None), "code", None))
        ]
    if normalized_brand_name:
        rows = [
            row
            for row in rows
            if normalized_brand_name == _normalize_optional_string(row.brand_name)
        ]
    items = [
        serialize_model_config(row)
        for row in sorted(
            rows,
            key=lambda row: (
                str(getattr(getattr(row, "category", None), "code", "") or ""),
                str(row.brand_name or ""),
                str(row.model_code or ""),
            ),
        )
    ]
    return {
        "status": normalized_status,
        "categoryCode": normalized_category_code,
        "brandName": normalized_brand_name,
        "total": len(items),
        "items": items,
    }


def export_model_configs(
    *,
    status: str | None = None,
    category_code: str | None = None,
    brand_name: str | None = None,
) -> dict[str, Any]:
    payload = list_model_configs(
        status=status,
        category_code=category_code,
        brand_name=brand_name,
    )
    return {
        "total": payload["total"],
        "items": payload["items"],
    }


def import_model_configs(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    items = list(payload.get("items") or [])
    with session_scope() as session:
        results = []
        touched_category_ids: set[str] = set()
        for entry in items:
            result = upsert_model_config_with_session(
                session,
                payload=dict(entry),
                operator_id=operator_id,
                dry_run=dry_run,
                sync_tasks=False,
            )
            results.append(result)
            category_id = _normalize_optional_string(result.get("model", {}).get("categoryId"))
            if category_id:
                touched_category_ids.add(category_id)

        sync_summary = _empty_sync_summary()
        for category_id in sorted(touched_category_ids):
            category = session.get(Category, category_id)
            if category is None:
                continue
            sync = sync_category_model_catalog_to_tasks_with_session(session, category=category)
            sync_summary["taskCount"] += int(sync.get("taskCount") or 0)
            sync_summary["autoCreatedTaskCount"] += int(sync.get("autoCreatedTaskCount") or 0)
            sync_summary["queryCount"] += int(sync.get("queryCount") or 0)
            sync_summary["brandLexiconCount"] += int(sync.get("brandLexiconCount") or 0)
            sync_summary["modelLexiconCount"] += int(sync.get("modelLexiconCount") or 0)
            sync_summary["configLexiconCount"] += int(sync.get("configLexiconCount") or 0)
        if dry_run:
            session.rollback()
        return {
            "dryRun": dry_run,
            "importedCount": len(results),
            "items": results,
            "sync": sync_summary,
        }


def upsert_model_config(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
    sync_tasks: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = upsert_model_config_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
            sync_tasks=sync_tasks,
        )
        if dry_run:
            session.rollback()
        return result


def upsert_model_config_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
    sync_tasks: bool = True,
) -> dict[str, Any]:
    normalized_operator_id = _normalize_optional_string(operator_id)
    if not normalized_operator_id:
        raise ModelConfigError("operator_id is required.")

    model_id = _normalize_optional_string(payload.get("modelId"))
    category = _resolve_category_from_payload(session, payload)
    if category is None:
        raise ModelConfigError("Category not found.")

    model_code = _normalize_optional_string(payload.get("modelCode"))
    model_name = _normalize_optional_string(payload.get("modelName"))
    if not model_code:
        raise ModelConfigError("modelCode is required.")
    if not model_name:
        raise ModelConfigError("modelName is required.")

    existing = _resolve_model(
        session,
        model_id=model_id,
        category_id=category.id,
        model_code=model_code,
    )
    before_json = serialize_model_config(existing)

    conflicting = _resolve_model(session, category_id=category.id, model_code=model_code)
    if conflicting is not None and existing is not None and str(conflicting.id) != str(existing.id):
        raise ModelConfigError(f"modelCode already exists in category: {model_code}")
    if conflicting is not None and existing is None:
        raise ModelConfigError(f"modelCode already exists in category: {model_code}")

    if existing is None:
        row = CategoryModelCatalog(
            category_id=category.id,
            brand_name=_normalize_optional_string(payload.get("brandName")),
            series_name=_normalize_optional_string(payload.get("seriesName")),
            model_code=model_code,
            model_name=model_name,
            status=_normalize_optional_string(payload.get("status")) or "ACTIVE",
            metadata_json=dict(payload.get("metadata") or {}),
        )
        row.category = category
        if model_id:
            row.id = model_id
        session.add(row)
        session.flush()
        action = "CREATE_MODEL_CONFIG_DRY_RUN" if dry_run else "CREATE_MODEL_CONFIG"
    else:
        row = existing
        row.category_id = category.id
        row.category = category
        row.brand_name = _normalize_optional_string(payload.get("brandName"))
        row.series_name = _normalize_optional_string(payload.get("seriesName"))
        row.model_code = model_code
        row.model_name = model_name
        row.status = _normalize_optional_string(payload.get("status")) or "ACTIVE"
        row.metadata_json = dict(payload.get("metadata") or {})
        session.flush()
        action = "UPDATE_MODEL_CONFIG_DRY_RUN" if dry_run else "UPDATE_MODEL_CONFIG"

    if "aliases" in payload:
        _sync_aliases(session=session, model=row, alias_payloads=list(payload.get("aliases") or []))
        session.flush()
    sync_summary = (
        sync_category_model_catalog_to_tasks_with_session(session, category=category)
        if sync_tasks
        else None
    )

    after_json = serialize_model_config(row)
    audit_log = ProductAttrAuditLog(
        operator_id=normalized_operator_id,
        resource_type="category_model_catalog",
        resource_id=row.id,
        action=action,
        before_json=before_json,
        after_json=after_json,
    )
    session.add(audit_log)
    session.flush()
    return {
        "dryRun": dry_run,
        "model": after_json,
        "auditLogId": audit_log.id,
        "sync": sync_summary,
    }


def _empty_sync_summary() -> dict[str, int]:
    return {
        "taskCount": 0,
        "autoCreatedTaskCount": 0,
        "queryCount": 0,
        "brandLexiconCount": 0,
        "modelLexiconCount": 0,
        "configLexiconCount": 0,
    }


def serialize_model_config(row: CategoryModelCatalog | None) -> dict[str, Any] | None:
    if row is None:
        return None
    aliases = sorted(
        list(getattr(row, "aliases", []) or []),
        key=lambda alias: (str(alias.alias_type or ""), str(alias.alias_text or "")),
    )
    return {
        "id": row.id,
        "categoryId": row.category_id,
        "categoryCode": getattr(getattr(row, "category", None), "code", None),
        "categoryName": getattr(getattr(row, "category", None), "name", None),
        "brandName": row.brand_name,
        "seriesName": row.series_name,
        "modelCode": row.model_code,
        "modelName": row.model_name,
        "status": row.status,
        "metadata": _json_safe_value(dict(row.metadata_json or {})),
        "aliasCount": len(aliases),
        "aliases": [
            {
                "id": alias.id,
                "aliasText": alias.alias_text,
                "aliasNormalized": alias.alias_normalized,
                "aliasType": alias.alias_type,
                "status": alias.status,
                "metadata": _json_safe_value(dict(alias.metadata_json or {})),
            }
            for alias in aliases
        ],
        "createdAt": _json_safe_value(getattr(row, "created_at", None)),
        "updatedAt": _json_safe_value(getattr(row, "updated_at", None)),
    }


def normalize_model_alias(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)
    return normalized


def _sync_aliases(
    *,
    session: Session,
    model: CategoryModelCatalog,
    alias_payloads: list[dict[str, Any]],
) -> None:
    existing_by_normalized = {
        str(alias.alias_normalized): alias for alias in list(getattr(model, "aliases", []) or [])
    }
    seen_normalized: set[str] = set()
    resolved_aliases: list[CategoryModelAlias] = []
    for payload in alias_payloads:
        alias_text = _normalize_optional_string(payload.get("aliasText"))
        if not alias_text:
            raise ModelConfigError("Each alias requires aliasText.")
        alias_normalized = normalize_model_alias(alias_text)
        if not alias_normalized:
            raise ModelConfigError(f"Alias cannot be normalized: {alias_text}")
        if alias_normalized in seen_normalized:
            raise ModelConfigError(f"Duplicate alias in payload: {alias_text}")
        seen_normalized.add(alias_normalized)
        existing = existing_by_normalized.get(alias_normalized)
        if existing is None:
            created = CategoryModelAlias(
                model_id=model.id,
                alias_text=alias_text,
                alias_normalized=alias_normalized,
                alias_type=_normalize_optional_string(payload.get("aliasType")) or "MANUAL",
                status=_normalize_optional_string(payload.get("status")) or "ACTIVE",
                metadata_json=dict(payload.get("metadata") or {}),
            )
            created.model = model
            session.add(created)
            resolved_aliases.append(created)
            continue
        existing.alias_text = alias_text
        existing.alias_normalized = alias_normalized
        existing.alias_type = _normalize_optional_string(payload.get("aliasType")) or "MANUAL"
        existing.status = _normalize_optional_string(payload.get("status")) or "ACTIVE"
        existing.metadata_json = dict(payload.get("metadata") or {})
        resolved_aliases.append(existing)
    for alias_normalized, existing in existing_by_normalized.items():
        if alias_normalized in seen_normalized:
            continue
        session.delete(existing)
    if hasattr(model, "aliases"):
        model.aliases = sorted(
            resolved_aliases,
            key=lambda alias: (str(alias.alias_type or ""), str(alias.alias_text or "")),
        )


def _resolve_category_from_payload(session: Session, payload: dict[str, Any]) -> Category | None:
    category_id = _normalize_optional_string(payload.get("categoryId"))
    category_code = _normalize_optional_string(payload.get("categoryCode"))
    if category_id:
        return session.get(Category, category_id)
    if category_code:
        rows = list(session.execute(select(Category).where(Category.code == category_code)).scalars().all())
        return rows[0] if rows else None
    return None


def _resolve_model(
    session: Session,
    *,
    model_id: str | None = None,
    category_id: str | None = None,
    model_code: str | None = None,
) -> CategoryModelCatalog | None:
    normalized_model_id = _normalize_optional_string(model_id)
    if normalized_model_id:
        return session.get(CategoryModelCatalog, normalized_model_id)
    if not category_id or not model_code:
        return None
    rows = list(
        session.execute(
            select(CategoryModelCatalog).where(
                CategoryModelCatalog.category_id == category_id,
                CategoryModelCatalog.model_code == model_code,
            )
        ).scalars().all()
    )
    return rows[0] if rows else None


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
    return value
