from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class CapturedSearchPayload:
    page_number: int
    request_url: str
    request_body: dict[str, Any]
    request_headers: dict[str, Any]
    response_status: int
    payload: dict[str, Any]
    captured_at: datetime


@dataclass(slots=True)
class SearchPlanEntry:
    task: Any
    query: str
    pages: int
    task_query_id: int | None = None


@dataclass(slots=True)
class SearchPlanOutcome:
    plan: SearchPlanEntry
    status: str
    pages_succeeded: int = 0
    pages_attempted: int = 0
    auth_state: str | None = None
    run_id: UUID | None = None
    error_message: str | None = None


class ManualVerificationRequired(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        auth_state: str,
        run_id: UUID | None = None,
        keep_page_open: bool = False,
    ) -> None:
        super().__init__(message)
        self.auth_state = auth_state
        self.run_id = run_id
        self.keep_page_open = keep_page_open


def group_batch_plans_by_platform(plans: list[SearchPlanEntry]) -> dict[str, list[SearchPlanEntry]]:
    grouped: dict[str, list[SearchPlanEntry]] = defaultdict(list)
    for plan in plans:
        grouped[plan.task.source_platform or "xianyu"].append(plan)
    return dict(grouped)
