from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from ...compat import UTC
from decimal import Decimal
from pathlib import Path
from typing import Any

from ...category_compat import is_apple_computer_scope, is_garmin_watch_scope, resolve_category_code
from ...db import session_scope
from .dashboard_queries import build_top_models
from .mobile_market_history import (
    MobileMarketSnapshot,
    collect_mobile_market_history,
    persist_mobile_market_history,
    reports_dir,
    save_mobile_market_history_report,
)


TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_DONE = "done"
TASK_STATUS_BLOCKED_INPUT = "blocked_input"
TASK_STATUS_FAILED = "failed"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def mobile_bulk_dir() -> Path:
    path = reports_dir() / "mobile-market-bulk"
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(value: str) -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-") or "task"


def decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def model_query_candidates(*, business_domain: str, model_name: str) -> list[str]:
    resolved_scope = resolve_category_code(business_domain)
    normalized = model_name.strip().lower()
    compact = re.sub(r"\s+", "", normalized)
    candidates: list[str] = []

    def add(value: str) -> None:
        cleaned = re.sub(r"\s+", " ", value.strip())
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    add(normalized)
    add(compact)

    if is_apple_computer_scope(resolved_scope):
        base = normalized
        base = re.sub(r"\b(8g|16g|24g|32g|36g|48g|64g|96g|128g|192g)\b", "", base)
        base = re.sub(r"\b(256g|512g|1t|2t|4t|8t)\b", "", base)
        base = re.sub(r"\s+", " ", base).strip()
        add(base)
        add(base.replace(" ", ""))
    elif is_garmin_watch_scope(resolved_scope):
        compact_no_space = compact
        add(f"garmin {normalized}")
        add(f"佳明 {compact_no_space}")
        add(f"佳明手表{compact_no_space}")
        add(normalized.replace(" ", ""))

    return candidates


@dataclass(slots=True)
class BulkTaskEvent:
    timestamp: str
    step: str
    status: str
    detail: str


@dataclass(slots=True)
class BulkMarketTask:
    task_id: str
    business_domain: str
    model_name: str
    query_candidates: list[str]
    listing_count: int
    seller_count: int
    avg_price: float | None
    last_seen_at: str | None
    status: str = TASK_STATUS_PENDING
    attempt_count: int = 0
    success_count: int = 0
    last_attempted_query: str | None = None
    last_output_path: str | None = None
    last_report_id: int | None = None
    last_error: str | None = None
    last_snapshot_summary: dict[str, Any] | None = None
    updated_at: str = field(default_factory=now_iso)
    events: list[BulkTaskEvent] = field(default_factory=list)


@dataclass(slots=True)
class BulkMarketQueueState:
    generated_at: str
    source: dict[str, Any]
    tasks: list[BulkMarketTask]
    summary: dict[str, int] = field(default_factory=dict)


def summarize_snapshot(snapshot: MobileMarketSnapshot) -> dict[str, Any]:
    return {
        "query": snapshot.query,
        "state": snapshot.state,
        "recent_avg_price_7d": snapshot.recent_avg_price_7d,
        "sold_price_range_low": snapshot.sold_price_range_low,
        "sold_price_range_high": snapshot.sold_price_range_high,
        "visible_record_count": len(snapshot.visible_records),
        "warnings": list(snapshot.warnings),
    }


def recompute_summary(tasks: list[BulkMarketTask]) -> dict[str, int]:
    summary = {
        TASK_STATUS_PENDING: 0,
        TASK_STATUS_RUNNING: 0,
        TASK_STATUS_DONE: 0,
        TASK_STATUS_BLOCKED_INPUT: 0,
        TASK_STATUS_FAILED: 0,
    }
    for task in tasks:
        summary[task.status] = summary.get(task.status, 0) + 1
    return summary


def save_queue_state(state: BulkMarketQueueState, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    payload["summary"] = recompute_summary(state.tasks)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    state.summary = payload["summary"]
    return path


def load_queue_state(path: Path) -> BulkMarketQueueState:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = [
        BulkMarketTask(
            **{
                **task,
                "events": [BulkTaskEvent(**event) for event in task.get("events", [])],
            }
        )
        for task in payload.get("tasks", [])
    ]
    return BulkMarketQueueState(
        generated_at=payload["generated_at"],
        source=payload.get("source", {}),
        tasks=tasks,
        summary=payload.get("summary", {}),
    )


def default_queue_state_path() -> Path:
    return mobile_bulk_dir() / "queue-state.json"


def build_mainstream_bulk_queue(
    *,
    top_n: int = 12,
    window_days: int = 30,
    heartbeat_days: int = 7,
) -> BulkMarketQueueState:
    with session_scope() as session:
        rows = build_top_models(
            session,
            business_domain=None,
            window_days=window_days,
            heartbeat_days=heartbeat_days,
            filtered_item_ids=None,
        )

    tasks: list[BulkMarketTask] = []
    for row in rows[:top_n]:
        raw_scope = str(row["business_domain"] or "").strip()
        scope_code = resolve_category_code(raw_scope) or raw_scope
        task = BulkMarketTask(
            task_id=f"{scope_code}:{slugify(row['model_name'])}",
            business_domain=scope_code,
            model_name=row["model_name"],
            query_candidates=model_query_candidates(
                business_domain=scope_code,
                model_name=row["model_name"],
            ),
            listing_count=int(row["listing_count"] or 0),
            seller_count=int(row["seller_count"] or 0),
            avg_price=decimal_to_float(row.get("avg_price")),
            last_seen_at=row["last_seen_at"].isoformat() if row.get("last_seen_at") else None,
        )
        task.events.append(
            BulkTaskEvent(
                timestamp=now_iso(),
                step="queue_init",
                status="ok",
                detail=f"Initialized mainstream task for {task.model_name} with {len(task.query_candidates)} query candidates.",
            )
        )
        tasks.append(task)

    state = BulkMarketQueueState(
        generated_at=now_iso(),
        source={
            "type": "top_models",
            "top_n": top_n,
            "window_days": window_days,
            "heartbeat_days": heartbeat_days,
        },
        tasks=tasks,
    )
    state.summary = recompute_summary(tasks)
    return state


def initialize_mainstream_bulk_queue(
    *,
    path: Path | None = None,
    top_n: int = 12,
    window_days: int = 30,
    heartbeat_days: int = 7,
) -> Path:
    output_path = path or default_queue_state_path()
    state = build_mainstream_bulk_queue(
        top_n=top_n,
        window_days=window_days,
        heartbeat_days=heartbeat_days,
    )
    return save_queue_state(state, output_path)


def pick_next_task(tasks: list[BulkMarketTask]) -> BulkMarketTask | None:
    for status in (TASK_STATUS_PENDING, TASK_STATUS_BLOCKED_INPUT):
        for task in tasks:
            if task.status == status:
                return task
    return None


def validate_snapshot(snapshot: MobileMarketSnapshot) -> tuple[bool, str]:
    if snapshot.state != "market":
        return False, f"unexpected_state:{snapshot.state}"
    if snapshot.recent_avg_price_7d is None and snapshot.sold_price_range_low is None and not snapshot.visible_records:
        return False, "missing_market_metrics"
    return True, "ok"


def make_task_report_output(task: BulkMarketTask) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return mobile_bulk_dir() / f"{task.task_id}-{timestamp}.json"


def append_task_event(task: BulkMarketTask, *, step: str, status: str, detail: str) -> None:
    task.events.append(BulkTaskEvent(timestamp=now_iso(), step=step, status=status, detail=detail))
    task.updated_at = now_iso()


def classify_task_failure(errors: list[str]) -> str:
    joined = "\n".join(errors)
    if "Unable to advance to the market page automatically" in joined or "unexpected_state" in joined:
        return TASK_STATUS_BLOCKED_INPUT
    return TASK_STATUS_FAILED


def run_bulk_market_history(
    *,
    path: Path | None = None,
    serial: str | None = None,
    max_tasks: int = 1,
    max_scrolls: int = 0,
    persist_report: bool = True,
) -> dict[str, Any]:
    state_path = path or default_queue_state_path()
    state = load_queue_state(state_path)

    processed = 0
    reports_created = 0
    tasks_completed = 0
    tasks_blocked = 0
    tasks_failed = 0

    while processed < max_tasks:
        task = pick_next_task(state.tasks)
        if task is None:
            break

        task.status = TASK_STATUS_RUNNING
        task.attempt_count += 1
        task.last_error = None
        append_task_event(task, step="task_start", status="ok", detail="Starting bulk mobile market capture.")
        save_queue_state(state, state_path)

        errors: list[str] = []
        success = False

        for query in task.query_candidates:
            task.last_attempted_query = query
            append_task_event(task, step="query_try", status="ok", detail=f"Trying query candidate: {query}")
            save_queue_state(state, state_path)
            try:
                snapshot = collect_mobile_market_history(
                    query=query,
                    serial=serial,
                    max_scrolls=max_scrolls,
                    reset_to_home=True,
                )
                valid, reason = validate_snapshot(snapshot)
                if not valid:
                    raise RuntimeError(reason)

                output_path = persist_mobile_market_history(snapshot, output=make_task_report_output(task))
                report_id = save_mobile_market_history_report(snapshot) if persist_report else None

                task.status = TASK_STATUS_DONE
                task.success_count += 1
                task.last_output_path = str(output_path)
                task.last_report_id = report_id
                task.last_snapshot_summary = summarize_snapshot(snapshot)
                append_task_event(
                    task,
                    step="query_success",
                    status="ok",
                    detail=f"Captured market history for query={query}.",
                )
                success = True
                reports_created += 1 if report_id is not None else 0
                tasks_completed += 1
                break
            except Exception as exc:  # noqa: BLE001
                error = f"{query}: {exc}"
                errors.append(error)
                append_task_event(task, step="query_failed", status="failed", detail=error)

        if not success:
            task.status = classify_task_failure(errors)
            task.last_error = "\n".join(errors[-3:])
            if task.status == TASK_STATUS_BLOCKED_INPUT:
                tasks_blocked += 1
            else:
                tasks_failed += 1

        save_queue_state(state, state_path)
        processed += 1

    state.summary = recompute_summary(state.tasks)
    save_queue_state(state, state_path)
    return {
        "state_path": str(state_path),
        "processed": processed,
        "reports_created": reports_created,
        "tasks_completed": tasks_completed,
        "tasks_blocked": tasks_blocked,
        "tasks_failed": tasks_failed,
        "summary": state.summary,
    }
