from __future__ import annotations

import ast
import json
from collections import deque
from datetime import datetime, timedelta
from ...compat import UTC
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, select

from ...category_compat import compatible_scope_keys, is_analytics_scope, non_analytics_scope_codes, resolve_category_code
from ...models import Item
from ...presentation.web import domain_label
from ...settings import get_settings

REPORTS_DIR = get_settings().base_dir / "reports"


def _scope_keys_for_filter(business_domain: str | None) -> tuple[str, ...]:
    normalized = str(business_domain or "").strip()
    if not normalized:
        return ()
    return compatible_scope_keys(normalized)


def _canonical_scope(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    return resolve_category_code(normalized) or normalized


def _scope_match(value: str | None, scope_keys: tuple[str, ...]) -> bool:
    if not scope_keys:
        return is_analytics_scope(value)
    return any(candidate in scope_keys for candidate in compatible_scope_keys(value))


def _apply_visible_scope_filter(stmt, *, column, business_domain: str | None):
    scope_keys = _scope_keys_for_filter(business_domain)
    if scope_keys:
        return stmt.where(column.in_(scope_keys))
    return stmt.where(~column.in_(non_analytics_scope_codes()))


def build_llm_review_progress(
    session,
    *,
    business_domain: str | None,
) -> list[dict[str, Any]]:
    scope_keys = _scope_keys_for_filter(business_domain)
    pending_filter = (
        Item.is_active.is_(True),
        Item.llm_reviewed.is_(False),
        Item.llm_review_status != "in_progress",
    )
    in_progress_filter = (
        Item.is_active.is_(True),
        Item.llm_reviewed.is_(False),
        Item.llm_review_status == "in_progress",
    )
    pending_audit_filter = (
        Item.llm_review_status == "pending_audit",
        Item.llm_review_needs_audit.is_(True),
    )
    stmt = (
        select(
            Item.business_domain,
            func.count(Item.id).label("total_items"),
            func.count(Item.id).filter(Item.is_active.is_(True)).label("active_items"),
            func.count(Item.id).filter(*pending_filter).label("pending_review_count"),
            func.count(Item.id).filter(*in_progress_filter).label("in_progress_count"),
            func.count(Item.id).filter(*pending_audit_filter).label("pending_audit_count"),
            func.count(Item.id).filter(Item.llm_review_status == "valid").label("reviewed_valid_count"),
            func.count(Item.id).filter(Item.llm_review_status == "invalid").label("reviewed_invalid_count"),
            func.count(Item.id).filter(
                Item.is_active.is_(False),
                Item.llm_review_status == "invalid",
            ).label("inactive_invalid_count"),
            func.max(Item.llm_reviewed_at).label("last_reviewed_at"),
        )
        .group_by(Item.business_domain)
        .order_by(Item.business_domain)
    )
    stmt = _apply_visible_scope_filter(
        stmt,
        column=Item.business_domain,
        business_domain=business_domain,
    )

    grouped: dict[str, dict[str, Any]] = {}
    for row in session.execute(stmt).all():
        scope = _canonical_scope(row.business_domain)
        if not scope:
            continue
        pending_review_count = int(row.pending_review_count or 0)
        in_progress_count = int(row.in_progress_count or 0)
        pending_audit_count = int(row.pending_audit_count or 0)
        reviewed_valid_count = int(row.reviewed_valid_count or 0)
        reviewed_invalid_count = int(row.reviewed_invalid_count or 0)
        reviewed_total = reviewed_valid_count + reviewed_invalid_count
        review_target_total = reviewed_total + pending_review_count + in_progress_count + pending_audit_count
        completion_percent = round((reviewed_total / review_target_total) * 100, 1) if review_target_total > 0 else 0.0
        entry = grouped.get(scope)
        if entry is None:
            grouped[scope] = {
                "business_domain": scope,
                "label": domain_label(scope),
                "total_items": int(row.total_items or 0),
                "active_items": int(row.active_items or 0),
                "pending_review_count": pending_review_count,
                "in_progress_count": in_progress_count,
                "pending_audit_count": pending_audit_count,
                "reviewed_valid_count": reviewed_valid_count,
                "reviewed_invalid_count": reviewed_invalid_count,
                "reviewed_total": reviewed_total,
                "inactive_invalid_count": int(row.inactive_invalid_count or 0),
                "review_target_total": review_target_total,
                "completion_percent": completion_percent,
                "last_reviewed_at": row.last_reviewed_at,
            }
            continue

        entry["total_items"] += int(row.total_items or 0)
        entry["active_items"] += int(row.active_items or 0)
        entry["pending_review_count"] += pending_review_count
        entry["in_progress_count"] += in_progress_count
        entry["pending_audit_count"] += pending_audit_count
        entry["reviewed_valid_count"] += reviewed_valid_count
        entry["reviewed_invalid_count"] += reviewed_invalid_count
        entry["reviewed_total"] += reviewed_total
        entry["inactive_invalid_count"] += int(row.inactive_invalid_count or 0)
        entry["review_target_total"] += review_target_total
        if row.last_reviewed_at and (
            entry["last_reviewed_at"] is None or row.last_reviewed_at > entry["last_reviewed_at"]
        ):
            entry["last_reviewed_at"] = row.last_reviewed_at
        target_total = int(entry["review_target_total"] or 0)
        reviewed_total_now = int(entry["reviewed_total"] or 0)
        entry["completion_percent"] = round((reviewed_total_now / target_total) * 100, 1) if target_total > 0 else 0.0

    return [grouped[key] for key in sorted(grouped)]


def build_llm_review_overview(progress_rows: list[dict[str, Any]]) -> dict[str, Any]:
    pending_review_count = sum(row["pending_review_count"] for row in progress_rows)
    in_progress_count = sum(row["in_progress_count"] for row in progress_rows)
    pending_audit_count = sum(row.get("pending_audit_count", 0) for row in progress_rows)
    reviewed_valid_count = sum(row["reviewed_valid_count"] for row in progress_rows)
    reviewed_invalid_count = sum(row["reviewed_invalid_count"] for row in progress_rows)
    review_target_total = sum(row["review_target_total"] for row in progress_rows)
    reviewed_total = reviewed_valid_count + reviewed_invalid_count
    completion_percent = round((reviewed_total / review_target_total) * 100, 1) if review_target_total > 0 else 0.0
    last_reviewed_at = max(
        (row["last_reviewed_at"] for row in progress_rows if row.get("last_reviewed_at") is not None),
        default=None,
    )
    return {
        "domain_count": len(progress_rows),
        "pending_review_count": pending_review_count,
        "in_progress_count": in_progress_count,
        "pending_audit_count": pending_audit_count,
        "reviewed_valid_count": reviewed_valid_count,
        "reviewed_invalid_count": reviewed_invalid_count,
        "reviewed_total": reviewed_total,
        "review_target_total": review_target_total,
        "completion_percent": completion_percent,
        "last_reviewed_at": last_reviewed_at,
    }


def build_invalid_reason_breakdown(
    session,
    *,
    business_domain: str | None,
) -> list[dict[str, Any]]:
    scope_keys = _scope_keys_for_filter(business_domain)
    stmt = (
        select(
            Item.business_domain,
            Item.llm_review_reason,
            func.count(Item.id).label("item_count"),
            func.max(Item.llm_reviewed_at).label("last_reviewed_at"),
        )
        .where(
            Item.llm_review_status == "invalid",
            Item.llm_review_reason.is_not(None),
        )
        .group_by(Item.business_domain, Item.llm_review_reason)
        .order_by(desc("item_count"), Item.business_domain, Item.llm_review_reason)
    )
    stmt = _apply_visible_scope_filter(
        stmt,
        column=Item.business_domain,
        business_domain=business_domain,
    )

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in session.execute(stmt).all():
        scope = _canonical_scope(row.business_domain)
        reason = str(row.llm_review_reason or "")
        if not scope or not reason:
            continue
        key = (scope, reason)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = {
                "business_domain": scope,
                "domain_label": domain_label(scope),
                "reason": reason,
                "item_count": int(row.item_count or 0),
                "last_reviewed_at": row.last_reviewed_at,
            }
            continue
        existing["item_count"] += int(row.item_count or 0)
        if row.last_reviewed_at and (
            existing["last_reviewed_at"] is None or row.last_reviewed_at > existing["last_reviewed_at"]
        ):
            existing["last_reviewed_at"] = row.last_reviewed_at

    rows = sorted(
        grouped.values(),
        key=lambda item: (-int(item.get("item_count") or 0), str(item.get("business_domain") or ""), str(item.get("reason") or "")),
    )
    return rows[:12]


def build_llm_review_audit_queue(
    session,
    *,
    business_domain: str | None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    scope_keys = _scope_keys_for_filter(business_domain)
    stmt = (
        select(Item)
        .where(
            Item.llm_review_status == "pending_audit",
            Item.llm_review_needs_audit.is_(True),
        )
        .order_by(desc(Item.llm_reviewed_at), desc(Item.last_seen_at), desc(Item.id))
        .limit(limit)
    )
    stmt = _apply_visible_scope_filter(
        stmt,
        column=Item.business_domain,
        business_domain=business_domain,
    )

    rows = []
    for item in session.execute(stmt).scalars():
        scope = _canonical_scope(item.business_domain)
        decision = dict(item.llm_review_decision or {})
        rows.append(
            {
                "item_id": item.item_id,
                "business_domain": scope,
                "domain_label": domain_label(scope),
                "title": item.title,
                "audit_reason": item.llm_review_audit_reason,
                "confidence": float(item.llm_review_confidence) if item.llm_review_confidence is not None else None,
                "decision_status": decision.get("review_status"),
                "invalid_reason": decision.get("invalid_reason"),
                "field_change_count": len(decision.get("not_match_field") or []),
                "reviewed_at": item.llm_reviewed_at,
            }
        )
    return rows


def load_recent_json_lines(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    tail: deque[str] = deque(maxlen=max(limit, 1))
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.strip():
                tail.append(line)
    entries: list[dict[str, Any]] = []
    for line in tail:
        value = _parse_structured_value(line)
        if isinstance(value, dict):
            entries.append(value)
    return entries


def load_first_json_line(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = _parse_structured_value(line)
            if isinstance(value, dict):
                return value
    return None


def load_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = _parse_structured_value(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    return value if isinstance(value, dict) else None


def _parse_structured_value(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            value = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None
        return value if isinstance(value, (dict, list)) else None


def load_review_result_entries(path: Path) -> list[dict[str, Any]]:
    entries = load_json_array(path)
    if entries:
        return entries
    single = load_json_object(path)
    return [single] if isinstance(single, dict) else []


def summarize_worker_event(entry: dict[str, Any]) -> dict[str, Any]:
    event = str(entry.get("event") or "unknown")
    status_class = "watch"
    title = event.replace("_", " ").title()
    summary = "-"
    if event == "batch_completed":
        usage = entry.get("usage") if isinstance(entry.get("usage"), dict) else {}
        total_usage = usage.get("total_usage") if isinstance(usage.get("total_usage"), dict) else {}
        high_confidence_kept = int(total_usage.get("high_confidence_kept_count") or 0)
        low_confidence_filtered = int(total_usage.get("low_confidence_filtered_count") or 0)
        second_pass_rescued = int(total_usage.get("second_pass_rescued_count") or 0)
        status_class = "completed"
        summary = (
            f'{entry.get("worker_name") or "-"} / batch {entry.get("batch_index") or "-"} / '
            f'keep {high_confidence_kept} / low {low_confidence_filtered} / '
            f'rescued {second_pass_rescued} / pending after {entry.get("pending_after") or "-"}'
        )
    elif event == "batch_failed":
        status_class = "failed"
        summary = (
            f'{entry.get("worker_name") or "-"} / batch {entry.get("batch_index") or "-"} / '
            f'{str(entry.get("error") or "-")[:160]}'
        )
    elif event == "item_retry_failed":
        status_class = "failed"
        summary = (
            f'{entry.get("worker_name") or "-"} / item {entry.get("item_id") or "-"} / '
            f'{str(entry.get("error") or "-")[:160]}'
        )
    elif event == "worker_started":
        status_class = "completed"
        summary = (
            f'pending {entry.get("pending_reviews") or "-"} / '
            f'workers {entry.get("worker_count") or "-"} / batch {entry.get("batch_size") or "-"}'
        )
    elif event == "worker_finished":
        status_class = "completed"
        summary = f'pending {entry.get("pending_reviews") or "-"}'
    return {
        "event": event,
        "title": title,
        "summary": summary,
        "status_class": status_class,
    }


def summarize_result_run_event(*, title: str, summary: str, status_class: str = "completed") -> dict[str, Any]:
    return {
        "event": "result_ready",
        "title": title,
        "summary": summary,
        "status_class": status_class,
    }


def summarize_v3_watch_event(entry: dict[str, Any]) -> dict[str, Any]:
    event = str(entry.get("event") or "unknown")
    title = event.replace("_", " ").title()
    status_class = "watch"
    summary = "-"

    if event == "starting_full_backfill":
        status_class = "completed"
        summary = (
            f'样本 {entry.get("limit") or "-"} / '
            f'workers {entry.get("workers") or "-"} / '
            f'batch {entry.get("first_pass_batch_size") or "-"}'
        )
    elif event == "cohort_created":
        status_class = "completed"
        summary = f'cohort {entry.get("count") or "-"} / {entry.get("path") or "-"}'
    elif event == "first_pass_batches_created":
        status_class = "completed"
        summary = f'batches {entry.get("batch_count") or "-"} / batch {entry.get("batch_size") or "-"}'
    elif event == "first_pass_batch_completed":
        status_class = "completed"
        completed_item_count = entry.get("completed_item_count")
        failed_item_count = entry.get("failed_item_count")
        summary = (
            f'{domain_label(_canonical_scope(entry.get("business_domain")) or entry.get("business_domain"))} / '
            f'done {completed_item_count if completed_item_count is not None else "-"} / '
            f'failed {failed_item_count if failed_item_count is not None else "-"}'
        )
    elif event == "pending_second_pass_built":
        status_class = "watch"
        summary = f'待二次清洗 {entry.get("count") or "-"} / {entry.get("path") or "-"}'
    elif event == "completed":
        status_class = "completed"
        summary = f'summary {entry.get("summary_path") or "-"}'
    elif "failed" in event:
        status_class = "failed"
        summary = str(entry.get("error") or entry.get("summary_path") or entry.get("path") or "-")[:180]

    return {
        "event": event,
        "title": title,
        "summary": summary,
        "status_class": status_class,
    }


def _v3_watch_pipeline_label(path: Path) -> str:
    name = path.name
    if "full-active-watch" in name:
        return "V3 Full Backfill"
    if "second-pass-watch" in name:
        return "V3 Second Pass"
    return "V3 Watch"


def _summary_business_domain(payload: dict[str, Any]) -> str | None:
    raw_business_domain = _canonical_scope(str(payload.get("business_domain") or "").strip())
    if raw_business_domain:
        return raw_business_domain
    domain_counts = payload.get("domainResolutionStatusCounts")
    if not isinstance(domain_counts, dict):
        return None
    domains = sorted(
        {
            scope
            for scope in (_canonical_scope(key) for key in domain_counts)
            if scope and is_analytics_scope(scope)
        }
    )
    if len(domains) == 1:
        return domains[0]
    if len(domains) > 1:
        return "mixed"
    return None


def _v3_result_domains(entries: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            scope
            for scope in (
                _canonical_scope(
                    str(entry.get("business_domain") or entry.get("review_input", {}).get("business_domain") or "").strip()
                )
                for entry in entries
            )
            if scope and is_analytics_scope(scope)
        }
    )


def _aggregate_v3_usage_rows(path: Path) -> dict[str, Any] | None:
    payload = _parse_structured_value(path.read_text(encoding="utf-8", errors="ignore"))
    if isinstance(payload, dict):
        summary_payload = payload if "resolutionStatusCounts" in payload else None
        if summary_payload is not None:
            business_domain = _summary_business_domain(summary_payload)
            if not business_domain:
                business_domain = _canonical_scope(str(summary_payload.get("business_domain") or "").strip()) or None
            first_pass_done = int(summary_payload.get("firstPassDoneCount") or 0)
            second_pass_done = int(summary_payload.get("secondPassDoneCount") or 0)
            first_pass_batch_size = max(int(summary_payload.get("firstPassBatchSize") or 1), 1)
            first_pass_request_count = (first_pass_done + first_pass_batch_size - 1) // first_pass_batch_size
            resolution_counts = (
                summary_payload.get("resolutionStatusCounts")
                if isinstance(summary_payload.get("resolutionStatusCounts"), dict)
                else {}
            )
            return {
                "file_name": path.name,
                "pipeline": "V3 Summary",
                "business_domain": business_domain,
                "domain_label": "混合业务域" if business_domain == "mixed" else domain_label(business_domain),
                "generated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
                "request_count": first_pass_request_count + second_pass_done,
                "batch_count": first_pass_request_count,
                "requested_item_count": int(summary_payload.get("cohortCount") or 0),
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cached_tokens": 0,
                "garbage_hit_count": 0,
                "low_confidence_filtered_count": 0,
                "high_confidence_kept_count": int(resolution_counts.get("VALID_READY_FOR_PRICING") or 0),
                "second_pass_requested_count": int(summary_payload.get("pendingSecondPassCount") or 0),
                "second_pass_rescued_count": 0,
                "second_pass_unresolved_count": int(summary_payload.get("secondPassDoneCount") or 0),
            }
        usage = payload.get("llm_usage") if isinstance(payload.get("llm_usage"), dict) else {}
        request_count = int(payload.get("llm_request_count") or 0)
        if request_count <= 0 and not any(int(usage.get(key) or 0) for key in ("input_tokens", "output_tokens", "total_tokens")):
            return None
        business_domain = _summary_business_domain(payload)
        if not business_domain:
            business_domain = _canonical_scope(str(payload.get("business_domain") or "").strip()) or None
        return {
            "file_name": path.name,
            "pipeline": "V3",
            "business_domain": business_domain,
            "domain_label": "混合业务域" if business_domain == "mixed" else domain_label(business_domain),
            "generated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
            "request_count": request_count,
            "batch_count": int(payload.get("batch_count") or 1),
            "requested_item_count": int(payload.get("cohortCount") or payload.get("requested_item_count") or 1),
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "cached_tokens": int(usage.get("cached_tokens") or 0),
            "garbage_hit_count": 0,
            "low_confidence_filtered_count": 0,
            "high_confidence_kept_count": int(payload.get("resolution_status") == "VALID_READY_FOR_PRICING"),
            "second_pass_requested_count": int(payload.get("stage_status") == "second_pass_complete"),
            "second_pass_rescued_count": int(
                payload.get("stage_status") == "second_pass_complete"
                and payload.get("resolution_status") == "VALID_READY_FOR_PRICING"
            ),
            "second_pass_unresolved_count": int(
                payload.get("stage_status") == "second_pass_complete"
                and payload.get("resolution_status") != "VALID_READY_FOR_PRICING"
            ),
        }
    if not isinstance(payload, list):
        return None
    entries = [entry for entry in payload if isinstance(entry, dict)]
    if not entries:
        return None
    request_count = sum(int(entry.get("llm_request_count") or 0) for entry in entries)
    input_tokens = sum(
        int((entry.get("llm_usage") or {}).get("input_tokens") or 0)
        for entry in entries
        if isinstance(entry.get("llm_usage"), dict)
    )
    output_tokens = sum(
        int((entry.get("llm_usage") or {}).get("output_tokens") or 0)
        for entry in entries
        if isinstance(entry.get("llm_usage"), dict)
    )
    total_tokens = sum(
        int((entry.get("llm_usage") or {}).get("total_tokens") or 0)
        for entry in entries
        if isinstance(entry.get("llm_usage"), dict)
    )
    cached_tokens = sum(
        int((entry.get("llm_usage") or {}).get("cached_tokens") or 0)
        for entry in entries
        if isinstance(entry.get("llm_usage"), dict)
    )
    if request_count <= 0 and total_tokens <= 0:
        return None
    domains = _v3_result_domains(entries)
    business_domain = domains[0] if len(domains) == 1 else ("mixed" if domains else None)
    return {
        "file_name": path.name,
        "pipeline": "V3",
        "business_domain": business_domain,
        "domain_label": "混合业务域" if business_domain == "mixed" else domain_label(business_domain),
        "generated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
        "request_count": request_count,
        "batch_count": 1,
        "requested_item_count": len(entries),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "garbage_hit_count": 0,
        "low_confidence_filtered_count": 0,
        "high_confidence_kept_count": sum(
            int(entry.get("resolution_status") == "VALID_READY_FOR_PRICING") for entry in entries
        ),
        "second_pass_requested_count": sum(
            int(entry.get("stage_status") == "second_pass_complete") for entry in entries
        ),
        "second_pass_rescued_count": sum(
            int(
                entry.get("stage_status") == "second_pass_complete"
                and entry.get("resolution_status") == "VALID_READY_FOR_PRICING"
            )
            for entry in entries
        ),
        "second_pass_unresolved_count": sum(
            int(
                entry.get("stage_status") == "second_pass_complete"
                and entry.get("resolution_status") != "VALID_READY_FOR_PRICING"
            )
            for entry in entries
        ),
    }


def _aggregate_v3_watch_usage_row(path: Path) -> dict[str, Any] | None:
    start_entry = load_first_json_line(path)
    if not start_entry:
        return None
    entries = load_recent_json_lines(path, limit=512)
    combined_entries = [start_entry] + entries
    latest_completion = next(
        (entry for entry in reversed(combined_entries) if entry.get("event") == "first_pass_batch_completed"),
        None,
    )
    pending_second_pass_entry = next(
        (entry for entry in reversed(combined_entries) if entry.get("event") == "pending_second_pass_built"),
        None,
    )
    completed_count = int((latest_completion or {}).get("completed_item_count") or 0)
    failed_count = int((latest_completion or {}).get("failed_item_count") or 0)
    batch_size = max(
        int(
            start_entry.get("first_pass_batch_size")
            or next(
                (
                    entry.get("batch_size")
                    for entry in combined_entries
                    if entry.get("event") in {"first_pass_batches_created", "first_pass_batch_completed"}
                ),
                1,
            )
            or 1
        ),
        1,
    )
    cohort_count = int(
        next((entry.get("count") for entry in combined_entries if entry.get("event") == "cohort_created"), 0) or 0
    )
    if cohort_count <= 0 and completed_count <= 0 and failed_count <= 0:
        return None

    business_domain = None
    if "full-active-watch" in path.name:
        business_domain = "mixed"
    else:
        run_domains = sorted(
            {
                scope
                for scope in (
                    _canonical_scope(entry.get("business_domain")) for entry in combined_entries
                )
                if scope and is_analytics_scope(scope)
            }
        )
        business_domain = run_domains[0] if len(run_domains) == 1 else ("mixed" if run_domains else None)

    second_pass_requested = int((pending_second_pass_entry or {}).get("count") or 0)
    request_count = (completed_count + failed_count + batch_size - 1) // batch_size
    return {
        "file_name": path.name,
        "pipeline": "V3 Live",
        "business_domain": business_domain,
        "domain_label": "混合业务域" if business_domain == "mixed" else domain_label(business_domain),
        "generated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
        "request_count": request_count,
        "batch_count": request_count,
        "requested_item_count": cohort_count or (completed_count + failed_count),
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "garbage_hit_count": 0,
        "low_confidence_filtered_count": 0,
        "high_confidence_kept_count": 0,
        "second_pass_requested_count": second_pass_requested,
        "second_pass_rescued_count": 0,
        "second_pass_unresolved_count": 0,
    }


def _build_worker_log_cards(*, business_domain: str | None) -> list[dict[str, Any]]:
    scope_keys = _scope_keys_for_filter(business_domain)
    cards: list[dict[str, Any]] = []
    candidate_paths: list[Path] = []
    for pattern in ("review-v3-*-watch-*.log",):
        candidate_paths.extend(
            [
                path
                for path in REPORTS_DIR.glob(pattern)
                if path.is_file() and not path.name.endswith(".err.log")
            ]
        )
    for path in sorted(
        candidate_paths,
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    ):
        start_entry = load_first_json_line(path)
        if not start_entry:
            continue
        recent_entries = load_recent_json_lines(path, limit=8)
        run_domains = sorted(
            {
                scope
                for scope in (
                    _canonical_scope(entry.get("business_domain")) for entry in ([start_entry] + recent_entries)
                )
                if scope and is_analytics_scope(scope)
            }
        )
        run_business_domain = run_domains[0] if len(run_domains) == 1 else ("mixed" if run_domains else None)
        if run_business_domain not in {None, "mixed"} and not _scope_match(run_business_domain, scope_keys):
            continue
        latest_entry = recent_entries[-1] if recent_entries else start_entry
        updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        freshness = datetime.now(UTC) - updated_at
        worker_count = int(start_entry.get("workers") or start_entry.get("worker_count") or start_entry.get("llm_concurrency") or 0)
        batch_size = int(
            start_entry.get("first_pass_batch_size")
            or next(
                (
                    int(entry.get("batch_size") or 0)
                    for entry in recent_entries
                    if entry.get("event") in {"first_pass_batches_created", "first_pass_batch_completed"}
                ),
                0,
            )
            or 0
        )
        requested_item_count = max(
            int(start_entry.get("limit") or 0),
            int(
                next(
                    (entry.get("count") for entry in recent_entries if entry.get("event") == "cohort_created"),
                    0,
                )
                or 0
            ),
        )
        pending_reviews = int(
            next(
                (
                    entry.get("count")
                    for entry in recent_entries
                    if entry.get("event") == "pending_second_pass_built"
                ),
                0,
            )
            or 0
        )
        cards.append(
            {
                "run_type": "worker_log",
                "pipeline": _v3_watch_pipeline_label(path),
                "business_domain": run_business_domain,
                "domain_label": "混合业务域" if run_business_domain == "mixed" else domain_label(run_business_domain),
                "log_name": path.name,
                "updated_at": updated_at,
                "is_recent": freshness <= timedelta(minutes=5),
                "worker_label": start_entry.get("worker_label"),
                "ai_provider": "direct",
                "ai_model": get_settings().ai_model or "-",
                "worker_count": worker_count,
                "batch_size": batch_size,
                "pending_reviews": pending_reviews,
                "requested_item_count": requested_item_count,
                "recent_events": [summarize_v3_watch_event(entry) for entry in reversed(recent_entries or [latest_entry])],
            }
        )
        if len(cards) >= 4:
            break
    return cards


def _build_result_file_cards(*, business_domain: str | None) -> list[dict[str, Any]]:
    scope_keys = _scope_keys_for_filter(business_domain)
    seen_paths: set[Path] = set()
    candidate_paths: list[Path] = []
    for pattern in ("review-v3-*.final-summary.json", "review-v3-*.second-pass-summary.json", "review-v3-*.json"):
        for path in REPORTS_DIR.glob(pattern):
            if path.is_file() and path not in seen_paths:
                seen_paths.add(path)
                candidate_paths.append(path)

    cards: list[dict[str, Any]] = []
    for path in sorted(candidate_paths, key=lambda candidate: candidate.stat().st_mtime, reverse=True):
        payload = _parse_structured_value(path.read_text(encoding="utf-8", errors="ignore"))
        entries: list[dict[str, Any]] = []
        summary_payload: dict[str, Any] | None = payload if isinstance(payload, dict) and "resolutionStatusCounts" in payload else None
        if isinstance(payload, list):
            entries = [entry for entry in payload if isinstance(entry, dict)]
        elif isinstance(payload, dict) and "resolution_status" in payload:
            entries = [payload]
        elif isinstance(payload, dict) and "resolutionStatusCounts" not in payload:
            maybe_entries = load_review_result_entries(path)
            entries = [entry for entry in maybe_entries if isinstance(entry, dict) and "resolution_status" in entry]

        if summary_payload:
            run_business_domain = _summary_business_domain(summary_payload)
        else:
            domains = _v3_result_domains(entries)
            run_business_domain = domains[0] if len(domains) == 1 else ("mixed" if domains else None)

        if not run_business_domain:
            continue
        if run_business_domain != "mixed" and not _scope_match(run_business_domain, scope_keys):
            continue

        updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        freshness = datetime.now(UTC) - updated_at
        if summary_payload:
            resolution_counts = summary_payload.get("resolutionStatusCounts") if isinstance(summary_payload.get("resolutionStatusCounts"), dict) else {}
            valid_count = int(resolution_counts.get("VALID_READY_FOR_PRICING") or 0)
            invalid_count = sum(
                int(count or 0)
                for status, count in resolution_counts.items()
                if str(status).startswith("REJECTED_") or status == "INVALID_OR_NOT_SUPPORTED"
            )
            pending_audit_count = sum(
                int(count or 0)
                for status, count in resolution_counts.items()
                if status in {"MANUAL_AUDIT_REQUIRED", "PENDING_REVIEW"}
            )
            provider = "direct"
            model = get_settings().ai_model or "-"
            events = [
                summarize_result_run_event(
                    title="结果汇总",
                    summary=(
                        f"cohort {summary_payload.get('cohortCount') or '-'} / "
                        f"valid {valid_count} / invalid {invalid_count} / manual {pending_audit_count}"
                    ),
                )
            ]
            if int(summary_payload.get("secondPassDoneCount") or 0) > 0:
                events.append(
                    summarize_result_run_event(
                        title="Second Pass",
                        summary=(
                            f"done {summary_payload.get('secondPassDoneCount') or 0} / "
                            f"failed {summary_payload.get('secondPassFailedCount') or 0}"
                        ),
                        status_class="watch" if int(summary_payload.get("secondPassFailedCount") or 0) > 0 else "completed",
                    )
                )
            if int(summary_payload.get("firstPassDoneCount") or 0) > 0:
                events.append(
                    summarize_result_run_event(
                        title="First Pass",
                        summary=(
                            f"done {summary_payload.get('firstPassDoneCount') or 0} / "
                            f"failed {summary_payload.get('firstPassFailedCount') or 0}"
                        ),
                        status_class="watch" if int(summary_payload.get("firstPassFailedCount") or 0) > 0 else "completed",
                    )
                )
        else:
            if not entries:
                continue
            valid_count = sum(1 for entry in entries if entry.get("resolution_status") == "VALID_READY_FOR_PRICING")
            invalid_count = sum(
                1
                for entry in entries
                if str(entry.get("resolution_status") or "").startswith("REJECTED_")
                or entry.get("resolution_status") == "INVALID_OR_NOT_SUPPORTED"
            )
            pending_audit_count = sum(
                1
                for entry in entries
                if entry.get("resolution_status") in {"MANUAL_AUDIT_REQUIRED", "PENDING_REVIEW"}
            )
            confidences = [
                float(value)
                for value in (entry.get("first_pass_confidence") for entry in entries)
                if value is not None
            ]
            average_confidence = (sum(confidences) / len(confidences)) if confidences else None
            minimum_confidence = min(confidences) if confidences else None
            invalid_reason_counts: dict[str, int] = {}
            for entry in entries:
                resolution_status = str(entry.get("resolution_status") or "").strip()
                invalid_reason = str(entry.get("invalid_reason") or "").strip()
                if invalid_reason:
                    reason = invalid_reason
                elif resolution_status.startswith("REJECTED_") or resolution_status == "INVALID_OR_NOT_SUPPORTED":
                    reason = resolution_status
                else:
                    reason = ""
                if reason:
                    invalid_reason_counts[reason] = invalid_reason_counts.get(reason, 0) + 1
            top_invalid_reason = None
            if invalid_reason_counts:
                top_invalid_reason = max(invalid_reason_counts.items(), key=lambda item: item[1])

            provider = "direct"
            model = get_settings().ai_model or "direct-model"
            events = [
                summarize_result_run_event(
                    title="结果已生成",
                    summary=(
                        f"输出 {len(entries)} 条 / valid {valid_count} / "
                        f"invalid {invalid_count} / pending_audit {pending_audit_count}"
                    ),
                )
            ]
            if average_confidence is not None and minimum_confidence is not None:
                events.append(
                    summarize_result_run_event(
                        title="置信度",
                        summary=f"均值 {average_confidence:.1%} / 最低 {minimum_confidence:.1%}",
                        status_class="watch" if minimum_confidence < 0.9 else "completed",
                    )
                )
            if top_invalid_reason:
                events.append(
                    summarize_result_run_event(
                        title="主要剔除原因",
                        summary=f"{top_invalid_reason[0]} / {top_invalid_reason[1]} 条",
                        status_class="watch",
                    )
                )

        cards.append(
            {
                "run_type": "result_file",
                "pipeline": "V3 Summary" if summary_payload else "V3 Result",
                "business_domain": run_business_domain,
                "domain_label": "混合业务域" if run_business_domain == "mixed" else domain_label(run_business_domain),
                "log_name": path.name,
                "updated_at": updated_at,
                "is_recent": freshness <= timedelta(minutes=30),
                "worker_label": "result_file",
                "ai_provider": provider,
                "ai_model": model,
                "worker_count": 0,
                "batch_size": int(summary_payload.get("cohortCount") or 0) if summary_payload else len(entries),
                "pending_reviews": 0,
                "recent_events": events,
            }
        )
        if len(cards) >= 4:
            break
    return cards


def build_worker_run_cards(*, business_domain: str | None) -> list[dict[str, Any]]:
    if not REPORTS_DIR.exists():
        return []
    cards = _build_worker_log_cards(business_domain=business_domain) + _build_result_file_cards(
        business_domain=business_domain
    )
    cards.sort(key=lambda card: card["updated_at"], reverse=True)
    return cards[:4]


def build_usage_summary(*, business_domain: str | None) -> dict[str, Any]:
    scope_keys = _scope_keys_for_filter(business_domain)
    if not REPORTS_DIR.exists():
        return {
            "file_count": 0,
            "request_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
            "garbage_hit_count": 0,
            "low_confidence_filtered_count": 0,
            "high_confidence_kept_count": 0,
            "second_pass_requested_count": 0,
            "second_pass_rescued_count": 0,
            "second_pass_unresolved_count": 0,
            "last_generated_at": None,
            "recent_usage_runs": [],
        }

    recent_usage_runs: list[dict[str, Any]] = []
    totals = {
        "file_count": 0,
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "garbage_hit_count": 0,
        "low_confidence_filtered_count": 0,
        "high_confidence_kept_count": 0,
        "second_pass_requested_count": 0,
        "second_pass_rescued_count": 0,
        "second_pass_unresolved_count": 0,
        "last_generated_at": None,
    }

    for path in sorted(REPORTS_DIR.glob("review-v3-*-watch-*.log"), key=lambda candidate: candidate.stat().st_mtime, reverse=True):
        row = _aggregate_v3_watch_usage_row(path)
        if not row:
            continue
        run_business_domain = row.get("business_domain")
        if run_business_domain not in {None, "mixed"} and not _scope_match(run_business_domain, scope_keys):
            continue
        recent_usage_runs.append(row)
        if len(recent_usage_runs) >= 6:
            break

    for path in sorted(REPORTS_DIR.glob("review-v3-*.json"), key=lambda candidate: candidate.stat().st_mtime, reverse=True):
        row = _aggregate_v3_usage_rows(path)
        if not row:
            continue
        run_business_domain = row.get("business_domain")
        if run_business_domain not in {None, "mixed"} and not _scope_match(run_business_domain, scope_keys):
            continue
        totals["file_count"] += 1
        totals["request_count"] += int(row.get("request_count") or 0)
        totals["input_tokens"] += int(row.get("input_tokens") or 0)
        totals["output_tokens"] += int(row.get("output_tokens") or 0)
        totals["total_tokens"] += int(row.get("total_tokens") or 0)
        totals["cached_tokens"] += int(row.get("cached_tokens") or 0)
        totals["garbage_hit_count"] += int(row.get("garbage_hit_count") or 0)
        totals["low_confidence_filtered_count"] += int(row.get("low_confidence_filtered_count") or 0)
        totals["high_confidence_kept_count"] += int(row.get("high_confidence_kept_count") or 0)
        totals["second_pass_requested_count"] += int(row.get("second_pass_requested_count") or 0)
        totals["second_pass_rescued_count"] += int(row.get("second_pass_rescued_count") or 0)
        totals["second_pass_unresolved_count"] += int(row.get("second_pass_unresolved_count") or 0)
        generated_at = row.get("generated_at")
        if generated_at and (totals["last_generated_at"] is None or generated_at > totals["last_generated_at"]):
            totals["last_generated_at"] = generated_at
        recent_usage_runs.append(row)
        if len(recent_usage_runs) >= 6:
            break

    recent_usage_runs.sort(
        key=lambda row: row.get("generated_at") or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return {
        **totals,
        "recent_usage_runs": recent_usage_runs[:6],
    }


def build_review_progress_page_data(
    session,
    *,
    business_domain: str | None,
    current_ai_provider: str,
    current_ai_model: str,
) -> dict[str, Any]:
    selected_scope = _canonical_scope(business_domain) or business_domain
    raw_domains = list(
        session.execute(select(Item.business_domain).distinct().order_by(Item.business_domain)).scalars()
    )
    available_domains: list[str] = []
    seen_domains: set[str] = set()
    for raw_domain in raw_domains:
        if not is_analytics_scope(raw_domain):
            continue
        scope = _canonical_scope(raw_domain)
        if not scope or scope in seen_domains:
            continue
        seen_domains.add(scope)
        available_domains.append(scope)
    progress_rows = build_llm_review_progress(
        session,
        business_domain=selected_scope,
    )
    return {
        "selected_domain": selected_scope,
        "available_domains": available_domains,
        "review_overview": build_llm_review_overview(progress_rows),
        "usage_summary": build_usage_summary(business_domain=selected_scope),
        "review_progress_rows": progress_rows,
        "audit_queue_rows": build_llm_review_audit_queue(
            session,
            business_domain=selected_scope,
        ),
        "worker_runs": build_worker_run_cards(business_domain=selected_scope),
        "invalid_reason_rows": build_invalid_reason_breakdown(
            session,
            business_domain=selected_scope,
        ),
        "current_ai_provider": current_ai_provider,
        "current_ai_model": current_ai_model,
    }
