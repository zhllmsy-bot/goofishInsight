from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "apps" / "collector" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from goofish_insight.application.services.spec_candidate_queue import (
    count_pending_enrichments,
    load_pending_db_item_ids,
)
from goofish_insight.application.services.spec_worker_state import (
    FREEZE_REASON_REPEAT_RESULT,
    frozen_db_ids_from_state,
    load_worker_state,
    save_worker_state,
    update_worker_state_from_batch,
)
from goofish_insight.cli import enrich_single_item
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


def chunked(values: list[int], size: int) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def process_enrichment_batch(
    *,
    db_item_ids: list[int],
    allow_llm: bool,
) -> dict[str, Any]:
    summary = {
        "requested": len(db_item_ids),
        "processed": 0,
        "complete": 0,
        "partial": 0,
        "unresolved": 0,
        "failed": 0,
        "llm_used": 0,
        "items": [],
    }
    for db_item_id in db_item_ids:
        try:
            result = enrich_single_item(db_item_id=db_item_id, allow_llm=allow_llm)
            status = result["status"] if result["status"] in summary else "failed"
            summary["processed"] += 1
            summary[status] += 1
            if result["extractor_type"] in {"llm", "hybrid"}:
                summary["llm_used"] += 1
            summary["items"].append(
                {
                    "db_item_id": db_item_id,
                    "item_id": result["item_id"],
                    "status": result["status"],
                    "confidence": result["confidence"],
                    "model_name": result["model_name"],
                    "extractor_type": result["extractor_type"],
                }
            )
        except Exception as exc:
            summary["failed"] += 1
            summary["items"].append(
                {
                    "db_item_id": db_item_id,
                    "status": "failed",
                    "error": str(exc),
                }
            )
    return summary


@app.command()
def main(
    business_domain: str | None = None,
    batch_size: int = typer.Option(6, min=1, max=20),
    worker_concurrency: int = typer.Option(15, min=1, max=32),
    worker_label: str | None = typer.Option(None),
    ai_provider: str | None = typer.Option(None),
    ai_base_url: str | None = typer.Option(None),
    ai_api_key: str | None = typer.Option(None),
    ai_model: str | None = typer.Option(None),
    ai_timeout_sec: int = typer.Option(120, min=10),
    pause_seconds: float = typer.Option(0.0, min=0.0, max=60.0),
    max_cycles: int = typer.Option(0, min=0, help="0 means keep draining until no pending items remain."),
    stagnant_cycle_threshold: int = typer.Option(3, min=1, max=20),
    stagnant_backoff_seconds: float = typer.Option(900.0, min=1.0, max=86400.0),
    repeat_freeze_threshold: int = typer.Option(2, min=2, max=20),
    log_path: Path | None = None,
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

    resolved_label = worker_label or business_domain or "spec-enrichment-worker"
    label_slug = slugify_label(resolved_label) or "spec-enrichment-worker"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    resolved_log = log_path or (
        REPO_ROOT / "reports" / f"spec-enrichment-worker-{label_slug}-{timestamp}.log"
    )
    state_path = resolved_log.with_suffix(".state.json")
    worker_state = load_worker_state(path=state_path)
    frozen_db_ids = frozen_db_ids_from_state(worker_state)

    stats = {
        "cycle_count": 0,
        "requested": 0,
        "processed": 0,
        "complete": 0,
        "partial": 0,
        "unresolved": 0,
        "failed": 0,
        "llm_used": 0,
    }

    emit_jsonl(
        path=resolved_log,
        payload={
            "event": "worker_started",
            "worker_label": resolved_label,
            "business_domain": business_domain,
            "batch_size": batch_size,
            "worker_concurrency": worker_concurrency,
            "ai_provider": settings.ai_provider,
            "ai_base_url": settings.ai_base_url,
            "ai_model": settings.ai_model,
            "pending_enrichments": count_pending_enrichments(
                business_domain=business_domain,
                frozen_db_ids=frozen_db_ids,
            ),
            "frozen_item_count": len(frozen_db_ids),
            "state_path": str(state_path),
        },
    )

    cycle_index = 0
    stagnant_cycles = 0
    while True:
        frozen_db_ids = frozen_db_ids_from_state(worker_state)
        pending_before = count_pending_enrichments(
            business_domain=business_domain,
            frozen_db_ids=frozen_db_ids,
        )
        if pending_before <= 0:
            break
        if max_cycles and cycle_index >= max_cycles:
            break

        item_limit = max(batch_size * worker_concurrency, 1)
        db_item_ids = load_pending_db_item_ids(
            business_domain=business_domain,
            limit=item_limit,
            frozen_db_ids=frozen_db_ids,
        )
        if not db_item_ids:
            emit_jsonl(
                path=resolved_log,
                payload={
                    "event": "worker_idle_backoff",
                    "cycle_index": cycle_index,
                    "pending_before": pending_before,
                    "frozen_item_count": len(frozen_db_ids),
                    "backoff_seconds": stagnant_backoff_seconds,
                    "reason": "no_eligible_items_after_freeze_filter",
                },
            )
            time.sleep(stagnant_backoff_seconds)
            continue

        cycle_index += 1
        stats["cycle_count"] += 1
        batches = chunked(db_item_ids, batch_size)
        cycle_started_at = time.time()
        emit_jsonl(
            path=resolved_log,
            payload={
                "event": "cycle_started",
                "cycle_index": cycle_index,
                "pending_before": pending_before,
                "requested_db_item_count": len(db_item_ids),
                "batch_count": len(batches),
                "batch_size": batch_size,
                "worker_concurrency": worker_concurrency,
            },
        )

        with ThreadPoolExecutor(max_workers=worker_concurrency) as executor:
            future_map = {
                executor.submit(
                    process_enrichment_batch,
                    db_item_ids=batch,
                    allow_llm=True,
                ): batch
                for batch in batches
            }
            for batch_index, future in enumerate(as_completed(future_map), start=1):
                batch_result = future.result()
                for key in ("requested", "processed", "complete", "partial", "unresolved", "failed", "llm_used"):
                    stats[key] += int(batch_result.get(key) or 0)
                frozen_events = update_worker_state_from_batch(
                    state=worker_state,
                    batch_items=batch_result["items"],
                    repeat_threshold=repeat_freeze_threshold,
                )
                if frozen_events:
                    save_worker_state(path=state_path, state=worker_state)
                emit_jsonl(
                    path=resolved_log,
                    payload={
                        "event": "batch_completed",
                        "cycle_index": cycle_index,
                        "batch_index": batch_index,
                        "requested": batch_result["requested"],
                        "processed": batch_result["processed"],
                        "complete": batch_result["complete"],
                        "partial": batch_result["partial"],
                        "unresolved": batch_result["unresolved"],
                        "failed": batch_result["failed"],
                        "llm_used": batch_result["llm_used"],
                        "items": batch_result["items"],
                        "frozen_items": frozen_events,
                    },
                )

        frozen_db_ids = frozen_db_ids_from_state(worker_state)
        pending_after = count_pending_enrichments(
            business_domain=business_domain,
            frozen_db_ids=frozen_db_ids,
        )
        if pending_after < pending_before:
            stagnant_cycles = 0
        else:
            stagnant_cycles += 1
        emit_jsonl(
            path=resolved_log,
            payload={
                "event": "cycle_completed",
                "cycle_index": cycle_index,
                "elapsed_seconds": round(time.time() - cycle_started_at, 3),
                "pending_after": pending_after,
                "stagnant_cycles": stagnant_cycles,
                "frozen_item_count": len(frozen_db_ids),
                "stats": dict(stats),
            },
        )
        if stagnant_cycles >= stagnant_cycle_threshold:
            emit_jsonl(
                path=resolved_log,
                payload={
                    "event": "worker_idle_backoff",
                    "cycle_index": cycle_index,
                    "pending_before": pending_before,
                    "pending_after": pending_after,
                    "stagnant_cycles": stagnant_cycles,
                    "frozen_item_count": len(frozen_db_ids),
                    "backoff_seconds": stagnant_backoff_seconds,
                    "reason": "pending_not_decreasing",
                },
            )
            stagnant_cycles = 0
            save_worker_state(path=state_path, state=worker_state)
            time.sleep(stagnant_backoff_seconds)
            continue
        if pause_seconds > 0:
            time.sleep(pause_seconds)

    emit_jsonl(
        path=resolved_log,
        payload={
            "event": "worker_completed",
            "stats": stats,
            "pending_remaining": count_pending_enrichments(
                business_domain=business_domain,
                frozen_db_ids=frozen_db_ids_from_state(worker_state),
            ),
            "frozen_item_count": len(worker_state.get("frozen_items", {})),
            "state_path": str(state_path),
        },
    )


if __name__ == "__main__":
    app()
