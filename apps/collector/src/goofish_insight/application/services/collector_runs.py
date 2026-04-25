from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from ...compat import UTC
from ...db import session_scope
from ...models import CrawlRun


def finalize_run(
    *,
    run_id: UUID,
    status: str,
    pages_attempted: int,
    pages_succeeded: int,
    error_message: str | None = None,
) -> None:
    with session_scope() as session:
        run = session.get(CrawlRun, run_id)
        if run is None:
            return
        run.status = status
        run.pages_attempted = pages_attempted
        run.pages_succeeded = pages_succeeded
        run.finished_at = datetime.now(UTC)
        run.error_message = error_message


def capture_run_progress(
    *,
    captures: dict[int, Any],
    attempted_pages: int,
) -> tuple[int, int]:
    return (
        max(len(captures), attempted_pages),
        sum(1 for capture in captures.values() if _search_results_count(capture.payload) > 0),
    )


def latest_run_for_task(*, task_id: int) -> CrawlRun | None:
    with session_scope() as session:
        return session.execute(
            select(CrawlRun)
            .where(CrawlRun.task_id == task_id)
            .order_by(CrawlRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()


def _search_results_count(payload: dict[str, Any]) -> int:
    return len(payload.get("data", {}).get("resultList") or [])
