from __future__ import annotations

import asyncio
import json
import os
import sys
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
    fetch_pending_audit_item_ids,
    load_items_for_llm_review,
)
from goofish_insight.application.services.review_second_pass import run_second_pass_item_review_batches
from goofish_insight.entrypoints.cli.review import (
    apply_second_pass_local_ai_defaults,
    persist_second_pass_outputs,
    summarize_second_pass_usage,
)
from goofish_insight.settings import get_settings
from goofish_insight.specs import llm_is_configured

app = typer.Typer(no_args_is_help=True)


def build_default_output_path(*, enable_thinking: bool) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    mode = "thinking" if enable_thinking else "plain"
    return REPO_ROOT / "reports" / f"review-second-pass-low-confidence-rerun-{mode}-{timestamp}.json"


def apply_local_ai_defaults_with_backfill() -> None:
    apply_second_pass_local_ai_defaults()
    os.environ.setdefault("AI_PROVIDER", "openai_compatible")
    os.environ.setdefault("AI_API_KEY", "local-dev")
    os.environ.setdefault("AI_MODEL", os.environ.get("QWEN3_MODEL_PATH", "Qwen3-30B-A3B-MLX-4bit"))
    os.environ.setdefault("AI_BASE_URL", "http://127.0.0.1:8000/v1")


def summarize_apply_summaries(chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not chunks:
        return None
    totals = {
        "chunk_count": len(chunks),
        "review_entry_count": 0,
        "matched_item_count": 0,
        "missing_item_count": 0,
        "reviewed_valid_count": 0,
        "reviewed_invalid_count": 0,
        "pending_audit_count": 0,
        "changed_item_row_count": 0,
        "changed_spec_row_count": 0,
        "created_spec_row_count": 0,
        "deactivated_item_count": 0,
        "changed_field_count": 0,
    }
    for chunk in chunks:
        for key in tuple(totals.keys())[1:]:
            totals[key] += int(chunk.get(key) or 0)
    return totals


@app.command()
def main(
    business_domain: str | None = None,
    audit_reason: str | None = typer.Option("low_confidence_v2"),
    limit: int = typer.Option(0, min=0, help="0 means rerun all matching pending_audit rows"),
    concurrency: int = typer.Option(1, min=1, max=8),
    ai_timeout_sec: int = typer.Option(45, min=5),
    ai_max_tokens: int = typer.Option(1800, min=128, max=8192),
    ai_provider: str | None = None,
    ai_base_url: str | None = None,
    ai_api_key: str | None = None,
    ai_model: str | None = None,
    enable_thinking: bool = typer.Option(True, "--enable-thinking/--disable-thinking"),
    apply: bool = typer.Option(True, "--apply/--no-apply"),
    output: Path | None = None,
) -> None:
    for key, value in (
        ("AI_PROVIDER", ai_provider),
        ("AI_BASE_URL", ai_base_url),
        ("AI_API_KEY", ai_api_key),
        ("AI_MODEL", ai_model),
    ):
        if value is not None:
            os.environ[key] = value

    apply_local_ai_defaults_with_backfill()
    os.environ["AI_TIMEOUT_SEC"] = str(ai_timeout_sec)
    os.environ["AI_MAX_TOKENS"] = str(ai_max_tokens)
    os.environ["AI_ENABLE_THINKING"] = "true" if enable_thinking else "false"
    get_settings.cache_clear()

    if not llm_is_configured():
        raise typer.BadParameter("LLM review is not configured.")

    item_ids = fetch_pending_audit_item_ids(
        business_domain=business_domain,
        audit_reason=audit_reason,
        limit=limit,
    )
    if not item_ids:
        typer.echo("[]")
        return

    entries: list[dict[str, Any]] = []
    unresolved_details: list[dict[str, Any]] = []
    all_results: list[Any] = []
    apply_chunks: list[dict[str, Any]] = []
    processed_item_count = 0

    resolved_output = output or build_default_output_path(enable_thinking=enable_thinking)
    chunk_size = max(concurrency * 10, 1)
    total_chunks = (len(item_ids) + chunk_size - 1) // chunk_size

    for chunk_index, start in enumerate(range(0, len(item_ids), chunk_size), start=1):
        chunk_item_ids = item_ids[start : start + chunk_size]
        items = load_items_for_llm_review(
            business_domain=business_domain,
            item_id=None,
            item_ids=chunk_item_ids,
            limit=0,
            force=True,
        )
        if not items:
            continue
        processed_item_count += len(items)

        results = asyncio.run(
            run_second_pass_item_review_batches(
                items=items,
                concurrency=concurrency,
            )
        )
        all_results.extend(results)

        chunk_entries: list[dict[str, Any]] = []
        chunk_unresolved: list[dict[str, Any]] = []
        for result in results:
            chunk_entries.extend(result.entries)
            chunk_unresolved.extend(result.unresolved_details)

        entries.extend(chunk_entries)
        unresolved_details.extend(chunk_unresolved)

        usage_summary = summarize_second_pass_usage(
            results=all_results,
            requested_item_count=len(item_ids),
            concurrency=concurrency,
        )
        persist_second_pass_outputs(
            output=resolved_output,
            entries=entries,
            usage_summary=usage_summary,
            unresolved_details=unresolved_details,
        )

        chunk_apply_summary: dict[str, Any] | None = None
        if apply and chunk_entries:
            chunk_apply_summary = apply_review_entries(
                review_entries=chunk_entries,
                dry_run=False,
                source_label=f"{resolved_output}#chunk{chunk_index}",
                source_name=resolved_output.name,
            )
            apply_chunks.append(chunk_apply_summary)

        typer.echo(
            json.dumps(
                {
                    "event": "low_confidence_rerun_chunk_completed",
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                    "chunk_item_count": len(items),
                    "entries_kept_total": len(entries),
                    "unresolved_total": len(unresolved_details),
                    "thinking_enabled": enable_thinking,
                    "usage_total": usage_summary["total_usage"],
                    "chunk_apply_summary": chunk_apply_summary,
                },
                ensure_ascii=False,
            ),
            err=True,
        )

    usage_summary = summarize_second_pass_usage(
        results=all_results,
        requested_item_count=len(item_ids),
        concurrency=concurrency,
    )

    apply_summary = summarize_apply_summaries(apply_chunks)
    if apply_summary is not None:
        apply_output = resolved_output.with_name(f"{resolved_output.stem}.apply.json")
        apply_output.write_text(json.dumps(apply_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    typer.echo(
        json.dumps(
            {
                "event": "low_confidence_rerun_completed",
                "business_domain": business_domain,
                "audit_reason": audit_reason,
                "selected_item_count": len(item_ids),
                "loaded_item_count": processed_item_count,
                "entries_kept_count": len(entries),
                "unresolved_count": len(unresolved_details),
                "thinking_enabled": enable_thinking,
                "applied": apply and bool(entries),
                "output_path": str(resolved_output),
                "apply_output_path": (
                    str(resolved_output.with_name(f"{resolved_output.stem}.apply.json"))
                    if apply_summary is not None
                    else None
                ),
                "usage_summary": usage_summary,
                "apply_summary": apply_summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
