from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "apps" / "collector" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from goofish_insight.application.services.review_apply import apply_review_entries
from goofish_insight.application.services.review_batches import review_item_batch
from goofish_insight.application.services.review_queries import (
    claim_pending_item_ids,
    count_pending_reviews,
    load_items_for_llm_review,
    release_item_claims,
)
from goofish_insight.pricing import build_pricing_views
from goofish_insight.settings import get_settings

app = typer.Typer(no_args_is_help=True)
LOG_LOCK = threading.Lock()


def emit_log(*, log_path: Path, payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=False)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with LOG_LOCK:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    print(line, flush=True)


def slugify_label(value: str | None) -> str | None:
    if not value:
        return None
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or None


def write_dashboard_snapshot(
    *,
    business_domain: str,
    output_path: Path,
) -> None:
    pricing_views = build_pricing_views(
        business_domain=business_domain,
        freshness_days=30,
        min_sample_points=4,
    )
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "business_domain": business_domain,
        "pending_reviews": count_pending_reviews(business_domain=business_domain),
        "product": pricing_views["product"][:20],
        "spec": pricing_views["spec"][:20],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def empty_stats(*, business_domain: str) -> dict[str, Any]:
    return {
        "business_domain": business_domain,
        "started_at": datetime.now(UTC).isoformat(),
        "reviewed_valid_count": 0,
        "reviewed_invalid_count": 0,
        "changed_item_row_count": 0,
        "changed_spec_row_count": 0,
        "created_spec_row_count": 0,
        "deactivated_item_count": 0,
        "unresolved_item_count": 0,
        "batch_count": 0,
    }


def merge_summary_into_stats(*, stats: dict[str, Any], summary: dict[str, Any] | None) -> None:
    if summary is None:
        return
    stats["reviewed_valid_count"] += summary["reviewed_valid_count"]
    stats["reviewed_invalid_count"] += summary["reviewed_invalid_count"]
    stats["changed_item_row_count"] += summary["changed_item_row_count"]
    stats["changed_spec_row_count"] += summary["changed_spec_row_count"]
    stats["created_spec_row_count"] += summary["created_spec_row_count"]
    stats["deactivated_item_count"] += summary["deactivated_item_count"]


def merge_worker_stats(*, target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "reviewed_valid_count",
        "reviewed_invalid_count",
        "changed_item_row_count",
        "changed_spec_row_count",
        "created_spec_row_count",
        "deactivated_item_count",
        "unresolved_item_count",
        "batch_count",
    ):
        target[key] += source.get(key, 0)


def review_and_apply_batch(
    *,
    business_domain: str,
    item_ids: list[str],
    source_name: str,
) -> tuple[dict[str, Any] | None, set[str]]:
    batch = load_items_for_llm_review(
        business_domain=business_domain,
        item_id=None,
        item_ids=item_ids,
        limit=0,
        force=True,
    )
    if not batch:
        return None, set(item_ids)

    result = review_item_batch(batch=batch)
    returned_ids = {entry["item_id"] for entry in result.entries}
    summary = None
    if result.entries:
        summary = apply_review_entries(
            review_entries=result.entries,
            dry_run=False,
            source_label=source_name,
            source_name=source_name,
        )
    unresolved_ids = set(item_ids) - returned_ids
    return summary, unresolved_ids


def worker_loop(
    *,
    business_domain: str,
    worker_index: int,
    batch_size: int,
    pause_seconds: float,
    claim_ttl_sec: int,
    max_batches: int,
    batch_state: dict[str, int],
    batch_state_lock: threading.Lock,
    log_path: Path,
) -> dict[str, Any]:
    worker_name = f"pid{os.getpid()}-t{worker_index:02d}"
    stats = empty_stats(business_domain=business_domain)
    stats["worker_name"] = worker_name

    while True:
        pending_before = count_pending_reviews(business_domain=business_domain)
        if pending_before <= 0:
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

        with batch_state_lock:
            if max_batches and batch_state["value"] >= max_batches:
                release_item_claims(item_ids=claimed_item_ids, worker_name=worker_name)
                break
            batch_state["value"] += 1
            batch_index = batch_state["value"]

        stats["batch_count"] += 1
        batch_name = f"{worker_name}-batch-{batch_index:05d}.json"

        try:
            batch_summary, unresolved_ids = review_and_apply_batch(
                business_domain=business_domain,
                item_ids=claimed_item_ids,
                source_name=batch_name,
            )
            merge_summary_into_stats(stats=stats, summary=batch_summary)

            deferred_item_ids: list[str] = []
            for unresolved_id in sorted(unresolved_ids):
                single_name = f"{worker_name}-item-{unresolved_id}.json"
                try:
                    single_summary, single_unresolved = review_and_apply_batch(
                        business_domain=business_domain,
                        item_ids=[unresolved_id],
                        source_name=single_name,
                    )
                except Exception as exc:
                    emit_log(
                        log_path=log_path,
                        payload={
                            "event": "item_retry_failed",
                            "worker_name": worker_name,
                            "batch_index": batch_index,
                            "item_id": unresolved_id,
                            "error": str(exc),
                        },
                    )
                    single_summary = None
                    single_unresolved = {unresolved_id}
                merge_summary_into_stats(stats=stats, summary=single_summary)
                if not single_summary or single_summary["review_entry_count"] <= 0:
                    if single_unresolved:
                        deferred_item_ids.append(unresolved_id)
                        stats["unresolved_item_count"] += 1

            emit_log(
                log_path=log_path,
                payload={
                    "event": "batch_completed",
                    "worker_name": worker_name,
                    "batch_index": batch_index,
                    "candidate_count": len(claimed_item_ids),
                    "pending_before": pending_before,
                    "pending_after": count_pending_reviews(business_domain=business_domain),
                    "batch_summary": batch_summary,
                    "deferred_item_ids": deferred_item_ids,
                    "claim_ttl_sec": claim_ttl_sec,
                    "worker_stats": stats,
                },
            )
        except Exception as exc:
            released_item_ids = release_item_claims(item_ids=claimed_item_ids, worker_name=worker_name)
            emit_log(
                log_path=log_path,
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

    return stats


@app.command()
def main(
    business_domain: str = "apple_m_series",
    batch_size: int = typer.Option(5, min=1, max=20),
    worker_count: int = typer.Option(10, min=1, max=100),
    worker_label: str | None = typer.Option(None, help="Human-readable label for this worker/model"),
    ai_provider: str | None = typer.Option(None, help="Per-process AI provider override"),
    ai_base_url: str | None = typer.Option(None, help="Per-process AI base URL override"),
    ai_api_key: str | None = typer.Option(None, help="Per-process AI API key override"),
    ai_model: str | None = typer.Option(None, help="Per-process AI model override"),
    ai_timeout_sec: int = typer.Option(300, min=30),
    pause_seconds: float = typer.Option(0.5, min=0.0, max=30.0),
    claim_ttl_sec: int = typer.Option(1800, min=60, max=86400),
    max_batches: int = typer.Option(0, min=0, help="0 means run until no pending items remain"),
    log_path: Path | None = None,
    dashboard_output: Path | None = None,
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
    resolved_worker_label = worker_label or settings.ai_model or "worker"
    label_slug = slugify_label(resolved_worker_label)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    resolved_log = log_path or (
        REPO_ROOT / "reports" / f"llm-review-worker-{business_domain}-{label_slug or 'worker'}-{timestamp}.log"
    )
    resolved_dashboard = dashboard_output or (
        REPO_ROOT / "reports" / f"dashboard-refresh-{business_domain}-{label_slug or 'worker'}-{timestamp}.json"
    )

    stats = empty_stats(business_domain=business_domain)
    batch_state = {"value": 0}
    batch_state_lock = threading.Lock()

    emit_log(
        log_path=resolved_log,
        payload={
            "event": "worker_started",
            "business_domain": business_domain,
            "worker_label": resolved_worker_label,
            "ai_provider": settings.ai_provider,
            "ai_model": settings.ai_model,
            "pending_reviews": count_pending_reviews(business_domain=business_domain),
            "batch_size": batch_size,
            "worker_count": worker_count,
            "ai_timeout_sec": ai_timeout_sec,
            "claim_ttl_sec": claim_ttl_sec,
        },
    )

    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="llm-review") as executor:
        futures = [
            executor.submit(
                worker_loop,
                business_domain=business_domain,
                worker_index=index + 1,
                batch_size=batch_size,
                pause_seconds=pause_seconds,
                claim_ttl_sec=claim_ttl_sec,
                max_batches=max_batches,
                batch_state=batch_state,
                batch_state_lock=batch_state_lock,
                log_path=resolved_log,
            )
            for index in range(worker_count)
        ]
        for future in as_completed(futures):
            worker_stats = future.result()
            merge_worker_stats(target=stats, source=worker_stats)

    write_dashboard_snapshot(
        business_domain=business_domain,
        output_path=resolved_dashboard,
    )
    emit_log(
        log_path=resolved_log,
        payload={
            "event": "worker_finished",
            "business_domain": business_domain,
            "worker_label": resolved_worker_label,
            "ai_provider": settings.ai_provider,
            "ai_model": settings.ai_model,
            "finished_at": datetime.now(UTC).isoformat(),
            "pending_reviews": count_pending_reviews(business_domain=business_domain),
            "dashboard_output": str(resolved_dashboard),
            "stats": stats,
        },
    )


if __name__ == "__main__":
    app()
