from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ...category_compat import resolve_category_code
from ...db import session_scope
from ...models import Category, CrawlTask


def backfill_task_category_bindings(
    *,
    task_key: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        stmt = select(CrawlTask).order_by(CrawlTask.id.asc())
        if task_key:
            stmt = stmt.where(CrawlTask.task_key == str(task_key).strip())
        if not force:
            stmt = stmt.where(CrawlTask.category_id.is_(None))

        tasks = list(session.execute(stmt).scalars())
        summary = {
            "processed": 0,
            "updated": 0,
            "task_key": task_key,
            "force": force,
            "tasks": [],
        }
        for task in tasks:
            summary["processed"] += 1
            category_code = resolve_category_code(task.business_domain)
            category = session.execute(select(Category).where(Category.code == category_code)).scalar_one_or_none()
            if category is not None:
                task.category_id = category.id
                summary["updated"] += 1
            summary["tasks"].append(
                {
                    "taskKey": task.task_key,
                    "businessDomain": task.business_domain,
                    "categoryCode": category_code,
                    "categoryId": task.category_id,
                }
            )
        return summary
