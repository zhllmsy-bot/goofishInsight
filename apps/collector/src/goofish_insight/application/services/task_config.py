from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...category_compat import compatible_scope_keys, resolve_category_code
from ...db import session_scope
from ...models import Category, CrawlTask, CrawlTaskLexicon, CrawlTaskQuery, ProductAttrAuditLog
from .task_runtime_materialization import materialize_task_runtime_fields


class TaskConfigError(RuntimeError):
    pass


def list_task_configs(
    *,
    status: str | None = None,
    category_code: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return list_task_configs_with_session(
            session,
            status=status,
            category_code=category_code,
        )


def list_task_configs_with_session(
    session: Session,
    *,
    status: str | None = None,
    category_code: str | None = None,
) -> dict[str, Any]:
    rows = list(session.execute(select(CrawlTask)).scalars().all())
    if status:
        normalized_status = str(status).strip().lower()
        rows = [row for row in rows if str(row.status or "").lower() == normalized_status]
    if category_code:
        normalized_category_code = str(category_code).strip()
        rows = [
            row
            for row in rows
            if normalized_category_code == str(getattr(getattr(row, "category", None), "code", "") or "")
        ]
    items = [
        serialize_task_config(row)
        for row in sorted(rows, key=lambda row: (str(row.task_key or ""), str(row.display_name or "")))
    ]
    return {
        "total": len(items),
        "items": items,
    }


def upsert_task_config(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = upsert_task_config_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def upsert_task_config_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_operator_id = _normalize_optional_string(operator_id)
    if not normalized_operator_id:
        raise TaskConfigError("operator_id is required.")

    task_key = _normalize_optional_string(payload.get("taskKey"))
    display_name = _normalize_optional_string(payload.get("displayName"))
    if not task_key:
        raise TaskConfigError("taskKey is required.")
    if not display_name:
        raise TaskConfigError("displayName is required.")

    existing = _resolve_task(session, task_key=task_key)
    before_json = serialize_task_config(existing)

    category_id = _normalize_optional_string(payload.get("categoryId"))
    category_code = _normalize_optional_string(payload.get("categoryCode"))
    category = _resolve_category(session, category_id=category_id, category_code=category_code)
    if category_id and category is None:
        raise TaskConfigError(f"Category not found: {category_id}")
    if category_code and category is None:
        raise TaskConfigError(f"Category not found: {category_code}")

    business_domain = _resolve_task_business_domain(
        category=category,
        requested_business_domain=_normalize_optional_string(payload.get("businessDomain")),
    )
    if not business_domain:
        raise TaskConfigError("businessDomain is required when category is not bound.")

    queries_payload = list(payload.get("queries") or [])
    lexicons_payload = dict(payload.get("lexicons") or {})
    query_texts = [str(entry.get("query") or "").strip() for entry in queries_payload if str(entry.get("query") or "").strip()]
    brand_terms = _collect_lexicon_terms(lexicons_payload.get("BRAND"))
    model_terms = _collect_lexicon_terms(lexicons_payload.get("MODEL"))
    config_terms = _collect_lexicon_terms(lexicons_payload.get("CONFIG"))

    if existing is None:
        row = CrawlTask(
            task_key=task_key,
            source_platform=_normalize_optional_string(payload.get("sourcePlatform")) or "xianyu",
            category_id=str(category.id) if category is not None else None,
            business_domain=business_domain,
            task_type=_normalize_optional_string(payload.get("taskType")) or "PRODUCTION",
            display_name=display_name,
            keywords=query_texts,
            brand_lexicon=brand_terms,
            model_lexicon=model_terms,
            config_lexicon=config_terms,
            paging_limit=int(payload.get("pagingLimit", 1)),
            profile_key=_normalize_optional_string(payload.get("profileKey")) or "default",
            parallel_tabs=int(payload.get("parallelTabs", 1)),
            status=_normalize_optional_string(payload.get("status")) or "active",
            metadata_json=dict(payload.get("metadata") or {}),
        )
        session.add(row)
        session.flush()
        action = "CREATE_TASK_CONFIG_DRY_RUN" if dry_run else "CREATE_TASK_CONFIG"
    else:
        row = existing
        row.source_platform = _normalize_optional_string(payload.get("sourcePlatform")) or row.source_platform or "xianyu"
        row.category_id = str(category.id) if category is not None else None
        row.business_domain = business_domain
        row.task_type = _normalize_optional_string(payload.get("taskType")) or "PRODUCTION"
        row.display_name = display_name
        row.keywords = query_texts
        row.brand_lexicon = brand_terms
        row.model_lexicon = model_terms
        row.config_lexicon = config_terms
        row.paging_limit = int(payload.get("pagingLimit", row.paging_limit or 1))
        row.profile_key = _normalize_optional_string(payload.get("profileKey")) or "default"
        row.parallel_tabs = int(payload.get("parallelTabs", row.parallel_tabs or 1))
        row.status = _normalize_optional_string(payload.get("status")) or "active"
        row.metadata_json = dict(payload.get("metadata") or {})
        session.flush()
        action = "UPDATE_TASK_CONFIG_DRY_RUN" if dry_run else "UPDATE_TASK_CONFIG"

    _sync_task_queries(session=session, task=row, query_payloads=queries_payload)
    _sync_task_lexicons(session=session, task=row, lexicons_payload=lexicons_payload)
    materialize_task_runtime_fields(row)
    session.flush()

    after_json = serialize_task_config(row)
    audit_log = ProductAttrAuditLog(
        operator_id=normalized_operator_id,
        resource_type="crawl_task",
        resource_id=str(row.id),
        action=action,
        before_json=before_json,
        after_json=after_json,
    )
    session.add(audit_log)
    session.flush()
    return {
        "dryRun": dry_run,
        "task": after_json,
        "auditLogId": audit_log.id,
    }


def serialize_task_config(row: CrawlTask | None) -> dict[str, Any] | None:
    if row is None:
        return None
    queries = sorted(list(getattr(row, "queries", []) or []), key=lambda item: (int(item.priority or 100), str(item.query_text or "")))
    lexicons = sorted(
        list(getattr(row, "lexicons", []) or []),
        key=lambda item: (str(item.lexicon_type or ""), int(item.priority or 100), str(item.term or "")),
    )
    grouped_lexicons: dict[str, list[dict[str, Any]]] = {}
    for entry in lexicons:
        grouped_lexicons.setdefault(str(entry.lexicon_type or "").upper(), []).append(
            {
                "id": entry.id,
                "term": entry.term,
                "priority": entry.priority,
                "status": entry.status,
                "metadata": dict(entry.metadata_json or {}),
            }
        )
    return {
        "id": row.id,
        "taskKey": row.task_key,
        "sourcePlatform": row.source_platform,
        "businessDomain": row.business_domain,
        "categoryId": row.category_id,
        "categoryCode": getattr(getattr(row, "category", None), "code", None),
        "categoryName": getattr(getattr(row, "category", None), "name", None),
        "taskType": row.task_type,
        "displayName": row.display_name,
        "pagingLimit": row.paging_limit,
        "profileKey": row.profile_key,
        "parallelTabs": row.parallel_tabs,
        "status": row.status,
        "metadata": dict(row.metadata_json or {}),
        "queries": [
            {
                "id": entry.id,
                "query": entry.query_text,
                "pages": entry.pages,
                "priority": entry.priority,
                "status": entry.status,
                "metadata": dict(entry.metadata_json or {}),
            }
            for entry in queries
        ],
        "lexicons": grouped_lexicons,
        "createdAt": _json_safe_value(getattr(row, "created_at", None)),
        "updatedAt": _json_safe_value(getattr(row, "updated_at", None)),
    }


def _sync_task_queries(*, session: Session, task: CrawlTask, query_payloads: list[dict[str, Any]]) -> None:
    existing_by_query = {str(entry.query_text): entry for entry in list(getattr(task, "queries", []) or [])}
    seen_queries: set[str] = set()
    for index, payload in enumerate(query_payloads):
        query_text = str(payload.get("query") or "").strip()
        if not query_text:
            continue
        if query_text in seen_queries:
            raise TaskConfigError(f"Duplicate query in payload: {query_text}")
        seen_queries.add(query_text)
        row = existing_by_query.get(query_text)
        if row is None:
            created = CrawlTaskQuery(
                task_id=task.id,
                query_text=query_text,
                pages=int(payload.get("pages", task.paging_limit or 1)),
                priority=int(payload.get("priority", (index + 1) * 10)),
                status=_normalize_optional_string(payload.get("status")) or "ACTIVE",
                metadata_json=dict(payload.get("metadata") or {}),
            )
            created.task = task
            session.add(created)
        else:
            row.pages = int(payload.get("pages", row.pages or task.paging_limit or 1))
            row.priority = int(payload.get("priority", row.priority or (index + 1) * 10))
            row.status = _normalize_optional_string(payload.get("status")) or "ACTIVE"
            row.metadata_json = dict(payload.get("metadata") or {})
    for query_text, row in existing_by_query.items():
        if query_text not in seen_queries:
            row.status = "DISABLED"


def _sync_task_lexicons(*, session: Session, task: CrawlTask, lexicons_payload: dict[str, Any]) -> None:
    existing_by_key = {
        (str(entry.lexicon_type or "").upper(), str(entry.term or "")): entry
        for entry in list(getattr(task, "lexicons", []) or [])
    }
    seen_keys: set[tuple[str, str]] = set()
    for lexicon_type, entries in dict(lexicons_payload or {}).items():
        normalized_type = str(lexicon_type or "").upper()
        for index, payload in enumerate(list(entries or [])):
            term = str(payload.get("term") or "").strip()
            if not normalized_type or not term:
                continue
            key = (normalized_type, term)
            if key in seen_keys:
                raise TaskConfigError(f"Duplicate lexicon term in payload: {normalized_type}/{term}")
            seen_keys.add(key)
            row = existing_by_key.get(key)
            if row is None:
                created = CrawlTaskLexicon(
                    task_id=task.id,
                    lexicon_type=normalized_type,
                    term=term,
                    priority=int(payload.get("priority", (index + 1) * 10)),
                    status=_normalize_optional_string(payload.get("status")) or "ACTIVE",
                    metadata_json=dict(payload.get("metadata") or {}),
                )
                created.task = task
                session.add(created)
            else:
                row.priority = int(payload.get("priority", row.priority or (index + 1) * 10))
                row.status = _normalize_optional_string(payload.get("status")) or "ACTIVE"
                row.metadata_json = dict(payload.get("metadata") or {})
    for key, row in existing_by_key.items():
        if key not in seen_keys:
            row.status = "DISABLED"


def _resolve_task(session: Session, *, task_key: str) -> CrawlTask | None:
    rows = list(session.execute(select(CrawlTask).where(CrawlTask.task_key == task_key)).scalars().all())
    return rows[0] if rows else None


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


def _resolve_task_business_domain(
    *,
    category: Category | None,
    requested_business_domain: str | None,
) -> str | None:
    normalized_requested = _normalize_optional_string(requested_business_domain)
    if category is None:
        return normalized_requested
    canonical_domain = _normalize_optional_string(getattr(category, "code", None))
    if canonical_domain is None:
        return normalized_requested
    if normalized_requested and resolve_category_code(normalized_requested) != canonical_domain:
        compatible_values = ", ".join(compatible_scope_keys(canonical_domain))
        raise TaskConfigError(
            f"businessDomain does not match bound category {canonical_domain}. Allowed values: {compatible_values}"
        )
    return canonical_domain


def _collect_lexicon_terms(entries: Any) -> list[str]:
    values: list[str] = []
    for payload in list(entries or []):
        term = str(payload.get("term") or "").strip()
        if term:
            values.append(term)
    return values


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
