from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...category_compat import resolve_category_code
from ...db import session_scope
from ...models import Category, CategoryModelCatalog, CrawlTask, CrawlTaskLexicon, CrawlTaskQuery
from .catalog_category_quality import catalog_scope_mismatch_reason
from .task_runtime_materialization import materialize_task_runtime_fields

SYNC_SOURCE = "model_catalog_sync"
SYNC_MANAGER = "category_model_catalog"


class TaskModelCatalogSyncError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CategoryQueryProfile:
    templates: tuple[str, ...] = ("{base}",)
    prefer_alias_queries: bool = False
    include_brand_prefixed_query: bool = True
    query_style: str = "default"


DEFAULT_QUERY_PROFILE = CategoryQueryProfile()
CATEGORY_QUERY_PROFILES: dict[str, CategoryQueryProfile] = {
    "camera_body": CategoryQueryProfile(
        templates=("{base}",),
        prefer_alias_queries=True,
        query_style="camera_body_short_name",
    ),
    "apple_computer": CategoryQueryProfile(
        templates=("{base}",),
        query_style="apple_short_name",
    ),
    "camera_interchangeable_lens": CategoryQueryProfile(
        templates=("{base}",),
        prefer_alias_queries=True,
        include_brand_prefixed_query=False,
        query_style="lens_short_name",
    ),
}


def sync_category_model_catalog_to_tasks(
    *,
    category_id: str | None = None,
    category_code: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        category = _resolve_category(session, category_id=category_id, category_code=category_code)
        if category is None:
            raise TaskModelCatalogSyncError("Category not found.")
        return sync_category_model_catalog_to_tasks_with_session(session, category=category)


def sync_category_model_catalog_to_tasks_with_session(
    session: Session,
    *,
    category: Category,
) -> dict[str, Any]:
    models = _load_active_models_for_category(session, category=category)
    desired_queries = _build_desired_queries(category=category, models=models)
    desired_lexicons = _build_desired_lexicons(category=category, models=models)
    tasks = _resolve_sync_target_tasks(session, category=category)
    auto_created_task_count = 0

    if not tasks and (desired_queries or any(desired_lexicons.values())):
        tasks = [_create_auto_managed_task(session, category=category)]
        auto_created_task_count = 1

    summary = {
        "categoryId": getattr(category, "id", None),
        "categoryCode": getattr(category, "code", None),
        "taskCount": len(tasks),
        "autoCreatedTaskCount": auto_created_task_count,
        "queryCount": 0,
        "brandLexiconCount": 0,
        "modelLexiconCount": 0,
        "configLexiconCount": 0,
    }
    for task in tasks:
        task_summary = _sync_single_task(
            session,
            task=task,
            category=category,
            desired_queries=desired_queries,
            desired_lexicons=desired_lexicons,
        )
        summary["queryCount"] += int(task_summary["queryCount"])
        summary["brandLexiconCount"] += int(task_summary["brandLexiconCount"])
        summary["modelLexiconCount"] += int(task_summary["modelLexiconCount"])
        summary["configLexiconCount"] += int(task_summary["configLexiconCount"])
    return summary


def _sync_single_task(
    session: Session,
    *,
    task: CrawlTask,
    category: Category,
    desired_queries: list[dict[str, Any]],
    desired_lexicons: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    _align_task_scope(task=task, category=category)
    existing_queries = {
        str(getattr(row, "query_text", "") or "").strip(): row
        for row in list(getattr(task, "queries", []) or [])
        if str(getattr(row, "query_text", "") or "").strip()
    }
    seen_queries: set[str] = set()
    for index, payload in enumerate(desired_queries):
        query_text = str(payload.get("query") or "").strip()
        if not query_text:
            continue
        seen_queries.add(query_text)
        existing = existing_queries.get(query_text)
        if existing is None:
            created = CrawlTaskQuery(
                task_id=task.id,
                query_text=query_text,
                pages=int(payload.get("pages", task.paging_limit or 1)),
                priority=int(payload.get("priority", (index + 1) * 10)),
                status="ACTIVE",
                metadata_json=_query_metadata(
                    category=category,
                    model_catalog_id=payload.get("modelCatalogId"),
                    query_kind=payload.get("queryKind"),
                ),
            )
            created.task = task
            session.add(created)
            continue
        if _is_auto_managed(existing):
            existing.pages = int(payload.get("pages", existing.pages or task.paging_limit or 1))
            existing.priority = int(payload.get("priority", existing.priority or (index + 1) * 10))
            existing.status = "ACTIVE"
            existing.metadata_json = _query_metadata(
                category=category,
                model_catalog_id=payload.get("modelCatalogId"),
                query_kind=payload.get("queryKind"),
            )
    for query_text, existing in existing_queries.items():
        if query_text in seen_queries or not _is_auto_managed(existing):
            continue
        existing.status = "DISABLED"

    for lexicon_type, payloads in desired_lexicons.items():
        normalized_type = str(lexicon_type or "").upper()
        existing_lexicons = {
            str(getattr(row, "term", "") or "").strip(): row
            for row in list(getattr(task, "lexicons", []) or [])
            if normalized_type == str(getattr(row, "lexicon_type", "") or "").upper()
            and str(getattr(row, "term", "") or "").strip()
        }
        seen_terms: set[str] = set()
        for index, payload in enumerate(payloads):
            term = str(payload.get("term") or "").strip()
            if not term:
                continue
            seen_terms.add(term)
            existing = existing_lexicons.get(term)
            if existing is None:
                created = CrawlTaskLexicon(
                    task_id=task.id,
                    lexicon_type=normalized_type,
                    term=term,
                    priority=int(payload.get("priority", (index + 1) * 10)),
                    status="ACTIVE",
                    metadata_json=_lexicon_metadata(
                        category=category,
                        lexicon_type=normalized_type,
                        model_catalog_id=payload.get("modelCatalogId"),
                    ),
                )
                created.task = task
                session.add(created)
                continue
            if _is_auto_managed(existing):
                existing.priority = int(payload.get("priority", existing.priority or (index + 1) * 10))
                existing.status = "ACTIVE"
                existing.metadata_json = _lexicon_metadata(
                    category=category,
                    lexicon_type=normalized_type,
                    model_catalog_id=payload.get("modelCatalogId"),
                )
        for term, existing in existing_lexicons.items():
            if term in seen_terms or not _is_auto_managed(existing):
                continue
            existing.status = "DISABLED"

    task_summary = materialize_task_runtime_fields(task)
    session.flush()
    return task_summary


def _load_active_models_for_category(
    session: Session,
    *,
    category: Category,
) -> list[CategoryModelCatalog]:
    rows = list(
        session.execute(
            select(CategoryModelCatalog).where(CategoryModelCatalog.category_id == category.id)
        ).scalars().all()
    )
    return [
        row
        for row in sorted(rows, key=lambda row: (str(row.brand_name or ""), str(row.model_name or ""), str(row.model_code or "")))
        if str(getattr(row, "status", "") or "").upper() == "ACTIVE"
        and _model_belongs_to_category(category=category, model=row)
    ]


def _resolve_sync_target_tasks(
    session: Session,
    *,
    category: Category,
) -> list[CrawlTask]:
    rows = list(
        session.execute(select(CrawlTask)).scalars().all()
    )
    candidates = [row for row in rows if _task_matches_category(row, category=category) and _task_is_sync_target(row)]
    return sorted(
        candidates,
        key=lambda row: (
            str(getattr(row, "source_platform", "") or ""),
            str(getattr(row, "task_key", "") or ""),
        ),
    )


def _task_is_sync_target(task: CrawlTask) -> bool:
    metadata = dict(getattr(task, "metadata_json", {}) or {})
    if metadata.get("syncModelCatalog") is False:
        return False
    if str(metadata.get("managedBy") or "") == SYNC_SOURCE:
        return True
    if metadata.get("syncModelCatalog") is True:
        return True
    task_key = str(getattr(task, "task_key", "") or "").strip().lower()
    return (
        str(getattr(task, "status", "") or "").strip().lower() == "active"
        and str(getattr(task, "task_type", "") or "").strip().upper() == "PRODUCTION"
        and str(getattr(task, "source_platform", "") or "").strip().lower() == "xianyu"
        and not task_key.startswith("smoke-")
        and not task_key.startswith("xianyu-onboarding")
    )


def _create_auto_managed_task(
    session: Session,
    *,
    category: Category,
) -> CrawlTask:
    existing_rows = list(session.execute(select(CrawlTask)).scalars().all())
    existing_keys = {str(getattr(row, "task_key", "") or "").strip() for row in existing_rows}
    base_key = f"{str(getattr(category, 'code', '') or '').replace('_', '-')}-catalog-auto"
    task_key = _allocate_task_key(base_key, existing_keys)
    status = "active" if str(getattr(category, "status", "") or "").upper() == "ACTIVE" else "paused"
    task = CrawlTask(
        task_key=task_key,
        source_platform="xianyu",
        category_id=category.id,
        business_domain=category.code,
        task_type="PRODUCTION",
        display_name=f"{category.name} 自动采集任务",
        keywords=[],
        brand_lexicon=[],
        model_lexicon=[],
        config_lexicon=[],
        paging_limit=5,
        profile_key="default",
        parallel_tabs=1,
        status=status,
        metadata_json={
            "syncModelCatalog": True,
            "managedBy": SYNC_SOURCE,
            "source": SYNC_MANAGER,
            "categoryId": category.id,
            "categoryCode": category.code,
        },
    )
    task.category = category
    session.add(task)
    session.flush()
    return task


def _allocate_task_key(base_key: str, existing_keys: set[str]) -> str:
    if base_key not in existing_keys:
        return base_key
    index = 2
    while f"{base_key}-{index}" in existing_keys:
        index += 1
    return f"{base_key}-{index}"


def _task_matches_category(task: CrawlTask, *, category: Category) -> bool:
    if getattr(task, "category_id", None):
        return str(task.category_id) == str(category.id)
    return resolve_category_code(getattr(task, "business_domain", None)) == str(getattr(category, "code", "") or "")


def _align_task_scope(*, task: CrawlTask, category: Category) -> None:
    if str(getattr(task, "category_id", "") or "") != str(getattr(category, "id", "") or ""):
        task.category_id = category.id
        task.category = category
    if resolve_category_code(getattr(task, "business_domain", None)) == str(getattr(category, "code", "") or ""):
        task.business_domain = category.code


def _build_desired_queries(
    *,
    category: Category,
    models: list[CategoryModelCatalog],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    profile = _query_profile_for_category(category)
    for model in models:
        brand_name = _normalize_text(getattr(model, "brand_name", None))
        model_name = _normalize_text(getattr(model, "model_name", None))
        active_aliases = [
            _normalize_query_base(
                _normalize_text(getattr(alias, "alias_text", None)),
                profile=profile,
                brand_name=brand_name,
            )
            for alias in list(getattr(model, "aliases", []) or [])
            if str(getattr(alias, "status", "") or "").upper() == "ACTIVE"
            and _alias_belongs_to_category(category=category, alias_text=getattr(alias, "alias_text", None))
        ]
        active_aliases = [alias_text for alias_text in active_aliases if alias_text]
        should_use_model_name_queries = not (profile.prefer_alias_queries and active_aliases)
        if model_name and should_use_model_name_queries:
            normalized_model_name = _normalize_query_base(
                model_name,
                profile=profile,
                brand_name=brand_name,
            )
            if (
                normalized_model_name
                and
                profile.include_brand_prefixed_query
                and brand_name
                and not _contains_token(normalized_model_name or model_name, brand_name)
            ):
                _append_query_entries(
                    entries,
                    seen_keys,
                    base_query=f"{brand_name} {normalized_model_name}",
                    model_catalog_id=getattr(model, "id", None),
                    query_kind="brand_model_name",
                    profile=profile,
                )
            _append_query_entries(
                entries,
                seen_keys,
                base_query=normalized_model_name,
                model_catalog_id=getattr(model, "id", None),
                query_kind="model_name",
                profile=profile,
            )
        for alias_text in active_aliases:
            _append_query_entries(
                entries,
                seen_keys,
                base_query=alias_text,
                model_catalog_id=getattr(model, "id", None),
                query_kind="alias",
                profile=profile,
            )
    return [
        {
            **entry,
            "pages": 5,
            "priority": (index + 1) * 10,
        }
        for index, entry in enumerate(entries)
    ]


def _build_desired_lexicons(
    *,
    category: Category,
    models: list[CategoryModelCatalog],
) -> dict[str, list[dict[str, Any]]]:
    brand_entries: list[dict[str, Any]] = []
    model_entries: list[dict[str, Any]] = []
    seen_brand_keys: set[str] = set()
    seen_model_keys: set[str] = set()
    for model in models:
        brand_name = _normalize_text(getattr(model, "brand_name", None))
        model_name = _normalize_text(getattr(model, "model_name", None))
        model_id = getattr(model, "id", None)
        brand_key = _normalize_dedupe_key(brand_name)
        if brand_key and brand_key not in seen_brand_keys:
            seen_brand_keys.add(brand_key)
            brand_entries.append({"term": brand_name, "modelCatalogId": model_id})
        model_key = _normalize_dedupe_key(model_name)
        if model_key and model_key not in seen_model_keys:
            seen_model_keys.add(model_key)
            model_entries.append({"term": model_name, "modelCatalogId": model_id})
        for alias in list(getattr(model, "aliases", []) or []):
            if str(getattr(alias, "status", "") or "").upper() != "ACTIVE":
                continue
            alias_text = _normalize_text(getattr(alias, "alias_text", None))
            if not _alias_belongs_to_category(category=category, alias_text=alias_text):
                continue
            alias_key = _normalize_dedupe_key(alias_text)
            if not alias_key or alias_key in seen_model_keys:
                continue
            seen_model_keys.add(alias_key)
            model_entries.append({"term": alias_text, "modelCatalogId": model_id})
    return {
        "BRAND": _with_priorities(brand_entries),
        "MODEL": _with_priorities(model_entries),
        "CONFIG": [],
    }


def _model_belongs_to_category(*, category: Category, model: CategoryModelCatalog) -> bool:
    text_parts = [
        getattr(model, "brand_name", None),
        getattr(model, "series_name", None),
        getattr(model, "model_name", None),
        getattr(model, "model_code", None),
    ]
    haystack = " ".join(str(part or "").strip() for part in text_parts if str(part or "").strip())
    return catalog_scope_mismatch_reason(getattr(category, "code", None), title=haystack) is None


def _alias_belongs_to_category(*, category: Category, alias_text: str | None) -> bool:
    text = str(alias_text or "").strip()
    if not text:
        return True
    return catalog_scope_mismatch_reason(getattr(category, "code", None), title=text) is None


def _append_query_entries(
    entries: list[dict[str, Any]],
    seen_keys: set[str],
    *,
    base_query: str | None,
    model_catalog_id: Any,
    query_kind: str,
    profile: CategoryQueryProfile,
) -> None:
    for query_text in _render_query_variants(base_query, profile=profile):
        key = _normalize_dedupe_key(query_text)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        entries.append(
            {
                "query": query_text,
                "modelCatalogId": model_catalog_id,
                "queryKind": query_kind,
            }
        )


def _render_query_variants(base_query: str | None, *, profile: CategoryQueryProfile) -> list[str]:
    normalized = _normalize_text(base_query)
    if normalized is None:
        return []
    variants: list[str] = []
    seen_keys: set[str] = set()
    for template in profile.templates or DEFAULT_QUERY_PROFILE.templates:
        candidate = _normalize_text(str(template).format(base=normalized))
        if candidate is None:
            continue
        key = _normalize_dedupe_key(candidate)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        variants.append(candidate)
    return variants


def _normalize_query_base(
    base_query: str | None,
    *,
    profile: CategoryQueryProfile,
    brand_name: str | None,
) -> str | None:
    normalized = _normalize_text(base_query)
    if normalized is None:
        return None
    if profile.query_style == "camera_body_short_name":
        return _normalize_camera_body_query(normalized)
    if profile.query_style == "apple_short_name":
        return _normalize_apple_short_query(normalized)
    if profile.query_style == "lens_short_name":
        return _normalize_lens_short_query(normalized, brand_name=brand_name)
    return normalized


def _normalize_camera_body_query(value: str) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    candidate = text
    candidate = _replace_case_insensitive(candidate, "机身", "")
    candidate = re.sub(r"\s+", " ", candidate).strip()
    return candidate or None


def _normalize_apple_short_query(value: str) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    candidate = text
    candidate = _replace_case_insensitive(candidate, "内存", "")
    candidate = _replace_case_insensitive(candidate, "统一内存", "")
    candidate = _replace_case_insensitive(candidate, "硬盘", "")
    candidate = _replace_case_insensitive(candidate, "存储", "")
    candidate = _replace_case_insensitive(candidate, "固态", "")
    candidate = re.sub(r"(?i)\b\d+\s*(gb|g|tb|t)\b", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    return candidate or None


def _normalize_lens_short_query(value: str, *, brand_name: str | None) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    candidate = text
    brand = _normalize_text(brand_name)
    if brand:
        candidate = _replace_case_insensitive(candidate, brand, _display_brand_name(brand))
    candidate = _replace_case_insensitive(candidate, "NIKKOR", "")
    candidate = _replace_case_insensitive(candidate, "镜头", "")
    candidate = _replace_case_insensitive(candidate, "卡口", "")
    candidate = _replace_case_insensitive(candidate, "微距", "")
    candidate = re.sub(r"(?i)\bmm\b", "", candidate)
    candidate = re.sub(r"(?i)f\s*/\s*", "", candidate)
    candidate = re.sub(r"(?i)\bf(?=\s*\d)", "", candidate)
    candidate = re.sub(r"(?i)\bz\s*([0-9])", r"Z \1", candidate)
    candidate = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", candidate)
    candidate = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", candidate)
    candidate = re.sub(r"(?i)(\d(?:\.\d+)?)\s*s\b", r"\1", candidate)
    candidate = re.sub(r"(?i)\b(vr|mc|s|plena)\b", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    return candidate or None


def _replace_case_insensitive(value: str, target: str, replacement: str) -> str:
    pattern = re.compile(re.escape(target), re.IGNORECASE)
    return pattern.sub(replacement, value)


def _display_brand_name(value: str) -> str:
    mapping = {
        "nikon": "尼康",
        "canon": "佳能",
        "sony": "索尼",
        "sigma": "适马",
        "tamron": "腾龙",
        "fujifilm": "富士",
    }
    normalized = str(value or "").strip().lower()
    return mapping.get(normalized, value)


def _with_priorities(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**entry, "priority": (index + 1) * 10} for index, entry in enumerate(entries)]


def _query_metadata(
    *,
    category: Category,
    model_catalog_id: Any,
    query_kind: Any,
) -> dict[str, Any]:
    return {
        "source": SYNC_SOURCE,
        "managedBy": SYNC_SOURCE,
        "syncSource": SYNC_MANAGER,
        "categoryId": getattr(category, "id", None),
        "categoryCode": getattr(category, "code", None),
        "modelCatalogId": model_catalog_id,
        "queryKind": query_kind,
    }


def _lexicon_metadata(
    *,
    category: Category,
    lexicon_type: str,
    model_catalog_id: Any,
) -> dict[str, Any]:
    return {
        "source": SYNC_SOURCE,
        "managedBy": SYNC_SOURCE,
        "syncSource": SYNC_MANAGER,
        "categoryId": getattr(category, "id", None),
        "categoryCode": getattr(category, "code", None),
        "modelCatalogId": model_catalog_id,
        "lexiconType": lexicon_type,
    }


def _is_auto_managed(row: CrawlTaskQuery | CrawlTaskLexicon) -> bool:
    metadata = dict(getattr(row, "metadata_json", {}) or {})
    return str(metadata.get("managedBy") or metadata.get("source") or "") == SYNC_SOURCE


def _contains_token(value: str, token: str) -> bool:
    return _normalize_dedupe_key(token) in _normalize_dedupe_key(value)


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _normalize_dedupe_key(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _query_profile_for_category(category: Category) -> CategoryQueryProfile:
    code = _normalize_text(getattr(category, "code", None))
    if code is None:
        return DEFAULT_QUERY_PROFILE
    return CATEGORY_QUERY_PROFILES.get(code, DEFAULT_QUERY_PROFILE)


def _resolve_category(
    session: Session,
    *,
    category_id: str | None = None,
    category_code: str | None = None,
) -> Category | None:
    normalized_category_id = _normalize_text(category_id)
    normalized_category_code = _normalize_text(category_code)
    if normalized_category_id:
        return session.get(Category, normalized_category_id)
    if normalized_category_code:
        rows = list(session.execute(select(Category).where(Category.code == normalized_category_code)).scalars().all())
        return rows[0] if rows else None
    return None
