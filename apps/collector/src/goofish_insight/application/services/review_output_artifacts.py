from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from ...compat import UTC
from ...settings import get_settings
from .review_queries import fetch_pending_item_ids, load_items_for_llm_review


def build_usage_sidecar_path(output: Path) -> Path:
    suffix = output.suffix or ".json"
    return output.with_name(f"{output.stem}.usage{suffix}")


def build_low_confidence_sidecar_path(output: Path) -> Path:
    suffix = output.suffix or ".json"
    return output.with_name(f"{output.stem}.low-confidence{suffix}")


def build_review_calibration_output_path(output: Path | None) -> Path:
    if output is not None:
        return output
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return get_settings().base_dir / "reports" / f"review-calibration-set-{timestamp}.json"


def build_review_calibration_eval_output_path(*, input_path: Path, output: Path | None) -> Path:
    if output is not None:
        return output
    suffix = input_path.suffix or ".json"
    return input_path.with_name(f"{input_path.stem}.evaluation{suffix}")


def summarize_llm_usage(
    *,
    results: list[Any],
    requested_item_count: int,
    batch_size: int,
    concurrency: int,
) -> dict[str, Any]:
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "garbage_hit_count": 0,
        "low_confidence_filtered_count": 0,
        "high_confidence_kept_count": 0,
    }
    batches: list[dict[str, Any]] = []
    llm_request_count = 0
    for index, result in enumerate(results, start=1):
        usage = dict(result.llm_usage or {})
        for key in ("input_tokens", "output_tokens", "total_tokens", "cached_tokens"):
            totals[key] += int(usage.get(key) or 0)
        totals["garbage_hit_count"] += int(result.garbage_hit_count or 0)
        totals["low_confidence_filtered_count"] += int(result.low_confidence_filtered_count or 0)
        totals["high_confidence_kept_count"] += int(result.high_confidence_kept_count or 0)
        llm_request_count += int(result.llm_request_count or 0)
        batches.append(
            {
                "batch_index": index,
                "batch_size": int(result.batch_size),
                "review_count": int(result.review_count),
                "llm_request_count": int(result.llm_request_count or 0),
                "llm_usage": usage or None,
                "garbage_hit_count": int(result.garbage_hit_count or 0),
                "low_confidence_filtered_count": int(result.low_confidence_filtered_count or 0),
                "high_confidence_kept_count": int(result.high_confidence_kept_count or 0),
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "requested_item_count": requested_item_count,
        "batch_size": batch_size,
        "concurrency": concurrency,
        "batch_count": len(results),
        "llm_request_count": llm_request_count,
        "total_usage": totals,
        "batches": batches,
    }


def summarize_second_pass_usage(
    *,
    results: list[Any],
    requested_item_count: int,
    concurrency: int,
) -> dict[str, Any]:
    totals = {
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
    }
    batches: list[dict[str, Any]] = []
    llm_request_count = 0
    for index, result in enumerate(results, start=1):
        usage = dict(result.llm_usage or {})
        for key in ("input_tokens", "output_tokens", "total_tokens", "cached_tokens"):
            totals[key] += int(usage.get(key) or 0)
        totals["garbage_hit_count"] += int(result.garbage_hit_count or 0)
        totals["low_confidence_filtered_count"] += int(result.low_confidence_filtered_count or 0)
        totals["high_confidence_kept_count"] += int(result.high_confidence_kept_count or 0)
        totals["second_pass_requested_count"] += int(result.second_pass_requested_count or 0)
        totals["second_pass_rescued_count"] += int(result.second_pass_rescued_count or 0)
        totals["second_pass_unresolved_count"] += int(result.second_pass_unresolved_count or 0)
        llm_request_count += int(result.llm_request_count or 0)
        batches.append(
            {
                "batch_index": index,
                "item_id": result.item_id,
                "batch_size": int(result.batch_size),
                "review_count": int(result.review_count),
                "llm_request_count": int(result.llm_request_count or 0),
                "llm_usage": usage or None,
                "garbage_hit_count": int(result.garbage_hit_count or 0),
                "low_confidence_filtered_count": int(result.low_confidence_filtered_count or 0),
                "high_confidence_kept_count": int(result.high_confidence_kept_count or 0),
                "second_pass_requested_count": int(result.second_pass_requested_count or 0),
                "second_pass_rescued_count": int(result.second_pass_rescued_count or 0),
                "second_pass_unresolved_count": int(result.second_pass_unresolved_count or 0),
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "requested_item_count": requested_item_count,
        "batch_size": 1,
        "concurrency": concurrency,
        "batch_count": len(results),
        "llm_request_count": llm_request_count,
        "total_usage": totals,
        "batches": batches,
    }


def persist_review_outputs(
    *,
    output: Path | None,
    entries: list[dict[str, Any]],
    usage_summary: dict[str, Any],
) -> None:
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    usage_output = build_usage_sidecar_path(output)
    usage_output.write_text(json.dumps(usage_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def persist_second_pass_outputs(
    *,
    output: Path | None,
    entries: list[dict[str, Any]],
    usage_summary: dict[str, Any],
    unresolved_details: list[dict[str, Any]],
) -> None:
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    usage_output = build_usage_sidecar_path(output)
    usage_output.write_text(json.dumps(usage_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    low_confidence_output = build_low_confidence_sidecar_path(output)
    low_confidence_output.write_text(
        json.dumps(unresolved_details, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def iter_review_items_in_chunks(
    *,
    business_domain: str | None,
    item_id: str | None,
    limit: int,
    force: bool,
    chunk_size: int,
) -> tuple[int, int, Iterator[list[dict[str, Any]]]]:
    resolved_chunk_size = max(chunk_size, 1)

    def build_chunk_iterator(items: list[dict[str, Any]]) -> Iterator[list[dict[str, Any]]]:
        for index in range(0, len(items), resolved_chunk_size):
            yield items[index : index + resolved_chunk_size]

    if force or item_id:
        items = load_items_for_llm_review(
            business_domain=business_domain,
            item_id=item_id,
            limit=limit,
            force=force,
        )
        if not items:
            return 0, 0, iter(())
        total_chunks = (len(items) + resolved_chunk_size - 1) // resolved_chunk_size
        return len(items), total_chunks, build_chunk_iterator(items)

    if limit > 0 and limit <= resolved_chunk_size:
        items = load_items_for_llm_review(
            business_domain=business_domain,
            item_id=item_id,
            limit=limit,
            force=force,
        )
        if not items:
            return 0, 0, iter(())
        return len(items), 1, iter((items,))

    pending_item_ids = fetch_pending_item_ids(
        business_domain=business_domain,
        limit=limit,
        exclude_item_ids=None,
    )
    if not pending_item_ids:
        return 0, 0, iter(())

    def generate_pending_chunks() -> Iterator[list[dict[str, Any]]]:
        for start in range(0, len(pending_item_ids), resolved_chunk_size):
            chunk_item_ids = pending_item_ids[start : start + resolved_chunk_size]
            chunk_rows = load_items_for_llm_review(
                business_domain=business_domain,
                item_id=None,
                item_ids=chunk_item_ids,
                limit=0,
                force=force,
            )
            rows_by_item_id = {entry["item_id"]: entry for entry in chunk_rows}
            ordered_chunk = [rows_by_item_id[item_id] for item_id in chunk_item_ids if item_id in rows_by_item_id]
            if ordered_chunk:
                yield ordered_chunk

    total_requested = len(pending_item_ids)
    total_chunks = (total_requested + resolved_chunk_size - 1) // resolved_chunk_size
    return total_requested, total_chunks, generate_pending_chunks()
