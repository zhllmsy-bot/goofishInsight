from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "apps" / "collector" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from goofish_insight.application.services.review_apply import apply_review_entries
from goofish_insight.application.services.review_queries import (
    claim_pending_item_ids,
    count_pending_reviews,
    load_items_for_llm_review,
    quarantine_item_claims,
    release_item_claims,
)
from goofish_insight.application.services.review_second_pass import run_second_pass_item_review_batches
from goofish_insight.settings import get_settings

app = typer.Typer(no_args_is_help=True)
LOG_LOCK = threading.Lock()


def emit_jsonl(*, path: Path, payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with LOG_LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    print(line, flush=True)


def slugify_label(value: str | None) -> str | None:
    if not value:
        return None
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or None


def summarize_result_usage(results: list[Any]) -> dict[str, Any]:
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
    llm_request_count = 0
    for result in results:
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
    return {
        "llm_request_count": llm_request_count,
        "total_usage": totals,
    }


def run_claimed_batch(
    *,
    business_domain: str | None,
    item_ids: list[str],
    source_name: str,
    llm_concurrency: int,
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]], dict[str, Any]]:
    batch = load_items_for_llm_review(
        business_domain=business_domain,
        item_id=None,
        item_ids=item_ids,
        limit=0,
        force=True,
    )
    if not batch:
        return None, item_ids, [], {"llm_request_count": 0, "total_usage": {}}

    results = asyncio.run(
        run_second_pass_item_review_batches(
            items=batch,
            concurrency=max(llm_concurrency, 1),
        )
    )

    entries: list[dict[str, Any]] = []
    unresolved_details: list[dict[str, Any]] = []
    unresolved_item_ids: list[str] = []
    for result in results:
        entries.extend(result.entries)
        unresolved_details.extend(result.unresolved_details)
        if result.review_count <= 0:
            unresolved_item_ids.append(result.item_id)

    summary = None
    if entries:
        summary = apply_review_entries(
            review_entries=entries,
            dry_run=False,
            source_label=source_name,
            source_name=source_name,
        )

    usage_summary = summarize_result_usage(results)
    return summary, unresolved_item_ids, unresolved_details, usage_summary


def settle_unresolved_item_ids(
    *,
    unresolved_item_ids: list[str],
    worker_name: str,
) -> list[str]:
    if not unresolved_item_ids:
        return []
    return quarantine_item_claims(
        item_ids=unresolved_item_ids,
        worker_name=worker_name,
        audit_reason="low_confidence_v2",
    )


@app.command()
def main(
    business_domain: str | None = None,
    batch_size: int = typer.Option(10, min=1, max=100),
    llm_concurrency: int = typer.Option(1, min=1, max=8),
    worker_label: str | None = typer.Option(None),
    ai_provider: str | None = typer.Option(None),
    ai_base_url: str | None = typer.Option(None),
    ai_api_key: str | None = typer.Option(None),
    ai_model: str | None = typer.Option(None),
    ai_timeout_sec: int = typer.Option(30, min=5),
    pause_seconds: float = typer.Option(1.0, min=0.0, max=30.0),
    claim_ttl_sec: int = typer.Option(1800, min=60, max=86400),
    max_batches: int = typer.Option(0, min=0, help="0 means keep running"),
    log_path: Path | None = None,
    low_confidence_path: Path | None = None,
) -> None:
    if ai_provider is not None:
        os.environ["AI_PROVIDER"] = ai_provider
    if ai_base_url is not None:
        os.environ["AI_BASE_URL"] = ai_base_url
    if ai_api_key is not None:
        os.environ["AI_API_KEY"] = ai_api_key
    if ai_model is not None:
        os.environ["AI_MODEL"] = ai_model
    os.environ["AI_TIMEOUT_SEC"] = str(ai_timeout_sec)
    get_settings.cache_clear()
    settings = get_settings()

    resolved_label = worker_label or settings.ai_model or "v2-worker"
    label_slug = slugify_label(resolved_label) or "v2-worker"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    resolved_log = log_path or (REPO_ROOT / "reports" / f"llm-review-v2-worker-{label_slug}-{timestamp}.log")
    resolved_low_confidence = low_confidence_path or (
        REPO_ROOT / "reports" / f"llm-review-v2-worker-{label_slug}-{timestamp}.low-confidence.jsonl"
    )
    worker_name = f"{label_slug}-pid{os.getpid()}"

    stats = {
        "batch_count": 0,
        "reviewed_valid_count": 0,
        "reviewed_invalid_count": 0,
        "changed_item_row_count": 0,
        "changed_spec_row_count": 0,
        "created_spec_row_count": 0,
        "deactivated_item_count": 0,
        "released_low_confidence_count": 0,
        "quarantined_low_confidence_count": 0,
        "llm_request_count": 0,
        "usage": {
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
        },
    }

    emit_jsonl(
        path=resolved_log,
        payload={
            "event": "worker_started",
            "worker_name": worker_name,
            "worker_label": resolved_label,
            "business_domain": business_domain,
            "batch_size": batch_size,
            "llm_concurrency": llm_concurrency,
            "ai_provider": settings.ai_provider,
            "ai_base_url": settings.ai_base_url,
            "ai_model": settings.ai_model,
            "pending_reviews": count_pending_reviews(
                business_domain=business_domain,
                lease_seconds=claim_ttl_sec,
            ),
        },
    )

    batch_index = 0
    while True:
        pending_before = count_pending_reviews(
            business_domain=business_domain,
            lease_seconds=claim_ttl_sec,
        )
        if pending_before <= 0:
            break
        if max_batches and batch_index >= max_batches:
            break

        claimed_item_ids = claim_pending_item_ids(
            business_domain=business_domain,
            limit=batch_size,
            worker_name=worker_name,
            lease_seconds=claim_ttl_sec,
        )
        if not claimed_item_ids:
            if pause_seconds > 0:
                time.sleep(pause_seconds)
            continue

        batch_index += 1
        stats["batch_count"] += 1
        batch_name = f"{worker_name}-batch-{batch_index:05d}.json"
        started_at = time.time()

        try:
            summary, unresolved_item_ids, unresolved_details, usage_summary = run_claimed_batch(
                business_domain=business_domain,
                item_ids=claimed_item_ids,
                source_name=batch_name,
                llm_concurrency=llm_concurrency,
            )
            quarantined_item_ids = settle_unresolved_item_ids(
                unresolved_item_ids=unresolved_item_ids,
                worker_name=worker_name,
            )

            if unresolved_details:
                for detail in unresolved_details:
                    emit_jsonl(path=resolved_low_confidence, payload=detail)

            if summary:
                for key in (
                    "reviewed_valid_count",
                    "reviewed_invalid_count",
                    "changed_item_row_count",
                    "changed_spec_row_count",
                    "created_spec_row_count",
                    "deactivated_item_count",
                ):
                    stats[key] += int(summary.get(key) or 0)

            stats["quarantined_low_confidence_count"] += len(quarantined_item_ids)
            stats["llm_request_count"] += int(usage_summary["llm_request_count"] or 0)
            for key, value in usage_summary["total_usage"].items():
                stats["usage"][key] += int(value or 0)

            emit_jsonl(
                path=resolved_log,
                payload={
                    "event": "batch_completed",
                    "worker_name": worker_name,
                    "batch_index": batch_index,
                    "candidate_count": len(claimed_item_ids),
                    "pending_before": pending_before,
                    "pending_after": count_pending_reviews(business_domain=business_domain),
                    "summary": summary,
                    "released_low_confidence_item_ids": [],
                    "quarantined_low_confidence_item_ids": quarantined_item_ids,
                    "usage": usage_summary,
                    "elapsed_seconds": round(time.time() - started_at, 3),
                    "worker_stats": stats,
                },
            )
        except Exception as exc:
            released_item_ids = release_item_claims(item_ids=claimed_item_ids, worker_name=worker_name)
            emit_jsonl(
                path=resolved_log,
                payload={
                    "event": "batch_failed",
                    "worker_name": worker_name,
                    "batch_index": batch_index,
                    "candidate_count": len(claimed_item_ids),
                    "released_item_ids": released_item_ids,
                    "error": str(exc),
                },
            )

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    emit_jsonl(
        path=resolved_log,
        payload={
            "event": "worker_finished",
            "worker_name": worker_name,
            "business_domain": business_domain,
            "finished_at": datetime.now(UTC).isoformat(),
            "pending_reviews": count_pending_reviews(business_domain=business_domain),
            "low_confidence_path": str(resolved_low_confidence),
            "worker_stats": stats,
        },
    )


if __name__ == "__main__":
    app()
