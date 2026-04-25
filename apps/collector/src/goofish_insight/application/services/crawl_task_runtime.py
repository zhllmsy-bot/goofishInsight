from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import session_scope
from ...logging import get_logger
from ...models import CrawlTask, CrawlTaskLexicon, CrawlTaskQuery

logger = get_logger(__name__)


class CrawlTaskRuntimeError(RuntimeError):
    pass


def build_crawl_task_runtime_config(*, task_key: str) -> dict[str, Any]:
    with session_scope() as session:
        return build_crawl_task_runtime_config_with_session(session, task_key=task_key)


def build_crawl_task_runtime_config_with_session(
    session: Session,
    *,
    task_key: str,
) -> dict[str, Any]:
    normalized_task_key = str(task_key or "").strip()
    if not normalized_task_key:
        logger.warning("crawl task runtime config requested without task_key")
        raise CrawlTaskRuntimeError("task_key is required.")

    rows = list(session.execute(select(CrawlTask).where(CrawlTask.task_key == normalized_task_key)).scalars().all())
    task = rows[0] if rows else None
    if task is None:
        logger.warning("crawl task runtime config missing task", extra={"task_key": normalized_task_key})
        raise CrawlTaskRuntimeError(f"Crawl task not found: {normalized_task_key}")

    query_rows = list(
        session.execute(select(CrawlTaskQuery).where(CrawlTaskQuery.task_id == task.id)).scalars().all()
    )
    lexicon_rows = list(
        session.execute(select(CrawlTaskLexicon).where(CrawlTaskLexicon.task_id == task.id)).scalars().all()
    )

    queries = (
        [
            {
                "id": row.id,
                "query": row.query_text,
                "pages": int(row.pages or 1),
                "priority": int(row.priority or 100),
                "status": row.status,
                "lastRunAt": _json_safe_value(row.last_run_at),
                "metadata": dict(row.metadata_json or {}),
            }
            for row in sorted(query_rows, key=lambda row: (int(row.priority or 100), str(row.id or "")))
            if str(row.status or "").upper() == "ACTIVE"
        ]
        if query_rows
        else [
            {
                "id": None,
                "query": str(query),
                "pages": int(task.paging_limit or 1),
                "priority": (index + 1) * 10,
                "status": "LEGACY",
                "lastRunAt": None,
                "metadata": {"source": "legacy_keywords"},
            }
            for index, query in enumerate(list(task.keywords or []))
            if str(query).strip()
        ]
    )

    lexicons = _serialize_lexicons(task=task, rows=lexicon_rows)
    return {
        "task": {
            "id": task.id,
            "taskKey": task.task_key,
            "sourcePlatform": task.source_platform,
            "categoryId": task.category_id,
            "businessDomain": task.business_domain,
            "taskType": task.task_type,
            "displayName": task.display_name,
            "pagingLimit": task.paging_limit,
            "profileKey": task.profile_key,
            "parallelTabs": task.parallel_tabs,
            "status": task.status,
            "metadata": dict(task.metadata_json or {}),
        },
        "queries": queries,
        "lexicons": lexicons,
    }


def _serialize_lexicons(
    *,
    task: CrawlTask,
    rows: list[CrawlTaskLexicon],
) -> dict[str, list[dict[str, Any]]]:
    if rows:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in sorted(rows, key=lambda row: (str(row.lexicon_type or ""), int(row.priority or 100), str(row.id or ""))):
            if str(row.status or "").upper() != "ACTIVE":
                continue
            bucket = grouped.setdefault(str(row.lexicon_type or "").upper(), [])
            bucket.append(
                {
                    "id": row.id,
                    "term": row.term,
                    "priority": int(row.priority or 100),
                    "status": row.status,
                    "metadata": dict(row.metadata_json or {}),
                }
            )
        return grouped

    return {
        "BRAND": [
            {"id": None, "term": str(term), "priority": (index + 1) * 10, "status": "LEGACY", "metadata": {"source": "legacy_brand_lexicon"}}
            for index, term in enumerate(list(task.brand_lexicon or []))
            if str(term).strip()
        ],
        "MODEL": [
            {"id": None, "term": str(term), "priority": (index + 1) * 10, "status": "LEGACY", "metadata": {"source": "legacy_model_lexicon"}}
            for index, term in enumerate(list(task.model_lexicon or []))
            if str(term).strip()
        ],
        "CONFIG": [
            {"id": None, "term": str(term), "priority": (index + 1) * 10, "status": "LEGACY", "metadata": {"source": "legacy_config_lexicon"}}
            for index, term in enumerate(list(task.config_lexicon or []))
            if str(term).strip()
        ],
    }


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except Exception:
            logger.debug("failed to serialize runtime value with isoformat", exc_info=True)
            return str(value)
    return value
