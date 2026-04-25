from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from ...compat import UTC
from pathlib import Path
from typing import Any

import typer

from ...application.services.review_apply import apply_review_file
from ...application.services.review_batches import run_llm_item_review_batches
from ...application.services.review_calibration import (
    build_review_calibration_set,
    evaluate_review_calibration_set,
    load_review_calibration_entries,
    persist_review_calibration_export,
    validate_review_calibration_entries,
)
from ...application.services.review_output_artifacts import (
    build_review_calibration_eval_output_path,
    build_review_calibration_output_path,
    iter_review_items_in_chunks,
    persist_review_outputs,
    summarize_llm_usage,
)
from ...application.services.review_v3_cozeloop import sync_review_v3_cozeloop_prompts
from ...application.services.review_v3_pipeline import (
    revalidate_review_v3_second_pass,
    run_review_v3_first_pass,
    run_review_v3_first_pass_batch,
    run_review_v3_second_pass,
    sync_review_v3_compat_fields,
)
from ...application.services.review_second_pass import apply_second_pass_local_ai_defaults
from ...application.services.review_v3_profiles import get_review_v3_profile, list_review_v3_profiles
from ...settings import get_settings
from ...specs import llm_is_configured


def register_review_commands(app: typer.Typer) -> None:
    @app.command("review-items-llm")
    def review_items_llm(
        business_domain: str | None = None,
        item_id: str | None = None,
        limit: int = typer.Option(50, min=0, help="0 means no limit"),
        force: bool = False,
        batch_size: int = typer.Option(5, min=1, max=100),
        concurrency: int = typer.Option(1, min=1, max=16),
        ai_timeout_sec: int | None = typer.Option(30, min=5),
        output: Path | None = None,
    ) -> None:
        if ai_timeout_sec is not None:
            os.environ["AI_TIMEOUT_SEC"] = str(ai_timeout_sec)
            get_settings.cache_clear()

        if not llm_is_configured():
            raise typer.BadParameter("LLM review is not configured.")

        chunk_size = max(batch_size * concurrency, 1)
        requested_item_count, total_chunks, item_chunks = iter_review_items_in_chunks(
            business_domain=business_domain,
            item_id=item_id,
            limit=limit,
            force=force,
            chunk_size=chunk_size,
        )
        if requested_item_count == 0:
            typer.echo("[]")
            return

        entries: list[dict[str, Any]] = []
        all_results: list[Any] = []
        for chunk_index, chunk_items in enumerate(item_chunks, start=1):
            started_at = datetime.now(UTC)
            chunk_results = asyncio.run(
                run_llm_item_review_batches(
                    items=chunk_items,
                    batch_size=batch_size,
                    concurrency=concurrency,
                )
            )
            all_results.extend(chunk_results)
            for result in chunk_results:
                entries.extend(result.entries)

            usage_summary = summarize_llm_usage(
                results=all_results,
                requested_item_count=requested_item_count,
                batch_size=batch_size,
                concurrency=concurrency,
            )
            persist_review_outputs(
                output=output,
                entries=entries,
                usage_summary=usage_summary,
            )
            elapsed_seconds = (datetime.now(UTC) - started_at).total_seconds()
            chunk_garbage_hit_count = sum(int(result.garbage_hit_count or 0) for result in chunk_results)
            chunk_low_confidence_filtered_count = sum(
                int(result.low_confidence_filtered_count or 0) for result in chunk_results
            )
            chunk_high_confidence_kept_count = sum(
                int(result.high_confidence_kept_count or 0) for result in chunk_results
            )
            typer.echo(
                json.dumps(
                    {
                        "event": "review_chunk_completed",
                        "chunk_index": chunk_index,
                        "total_chunks": total_chunks,
                        "chunk_item_count": len(chunk_items),
                        "entries_kept_total": len(entries),
                        "chunk_garbage_hit_count": chunk_garbage_hit_count,
                        "chunk_low_confidence_filtered_count": chunk_low_confidence_filtered_count,
                        "chunk_high_confidence_kept_count": chunk_high_confidence_kept_count,
                        "garbage_hit_count_total": usage_summary["total_usage"]["garbage_hit_count"],
                        "low_confidence_filtered_count_total": usage_summary["total_usage"][
                            "low_confidence_filtered_count"
                        ],
                        "high_confidence_kept_count_total": usage_summary["total_usage"][
                            "high_confidence_kept_count"
                        ],
                        "llm_request_count_total": usage_summary["llm_request_count"],
                        "usage_total": usage_summary["total_usage"],
                        "elapsed_seconds": round(elapsed_seconds, 3),
                    },
                    ensure_ascii=False,
                ),
                err=True,
            )

        typer.echo(json.dumps(entries, ensure_ascii=False, indent=2))

    @app.command("review-items-llm-v2")
    @app.command("review-items-llm-second-pass")
    def review_items_llm_second_pass(
        business_domain: str | None = None,
        item_id: str | None = None,
        limit: int = typer.Option(50, min=0, help="0 means no limit"),
        force: bool = False,
        concurrency: int = typer.Option(1, min=1, max=16),
        ai_timeout_sec: int | None = typer.Option(30, min=5),
        output: Path | None = None,
    ) -> None:
        typer.echo(
            json.dumps(
                {
                    "event": "deprecated_review_v2_command_forwarded",
                    "message": "review-items-llm-second-pass now forwards to review-v3-second-pass",
                    "ignored_concurrency": concurrency,
                },
                ensure_ascii=False,
            ),
            err=True,
        )
        settings_changed = False
        if ai_timeout_sec is not None:
            os.environ["AI_TIMEOUT_SEC"] = str(ai_timeout_sec)
            settings_changed = True

        os.environ["REVIEW_V3_EXECUTOR"] = os.environ.get("REVIEW_V3_EXECUTOR") or "direct"
        settings_changed = True

        settings_changed = apply_second_pass_local_ai_defaults() or settings_changed

        if settings_changed:
            get_settings.cache_clear()

        if not llm_is_configured():
            raise typer.BadParameter("LLM review is not configured.")
        results = run_review_v3_second_pass(
            business_domain=business_domain,
            item_id=item_id,
            limit=limit,
            force=force,
        )
        serialized = json.dumps(results, ensure_ascii=False, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized)

    @app.command("apply-item-llm-review")
    def apply_item_llm_review(
        input_path: Path,
        dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run"),
        output: Path | None = None,
    ) -> None:
        summary = apply_review_file(
            input_path=input_path,
            dry_run=dry_run,
        )
        serialized = json.dumps(summary, ensure_ascii=False, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized)

    @app.command("review-v3-first-pass")
    def review_v3_first_pass(
        business_domain: str | None = None,
        item_id: str | None = None,
        limit: int = typer.Option(50, min=0, help="0 means no limit"),
        force: bool = False,
        ai_timeout_sec: int | None = typer.Option(30, min=5),
        executor: str | None = typer.Option(None, help="direct or cozeloop"),
        output: Path | None = None,
    ) -> None:
        settings_changed = False
        if ai_timeout_sec is not None:
            os.environ["AI_TIMEOUT_SEC"] = str(ai_timeout_sec)
            settings_changed = True
        if executor:
            os.environ["REVIEW_V3_EXECUTOR"] = executor
            settings_changed = True
        if settings_changed:
            get_settings.cache_clear()

        results = run_review_v3_first_pass(
            business_domain=business_domain,
            item_id=item_id,
            limit=limit,
            force=force,
        )
        serialized = json.dumps(results, ensure_ascii=False, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized)

    @app.command("review-v3-first-pass-batch")
    def review_v3_first_pass_batch_command(
        business_domain: str,
        item_ids: str = typer.Option(..., help="Comma-separated item_ids for one same-domain batch."),
        force: bool = False,
        ai_timeout_sec: int | None = typer.Option(30, min=5),
        executor: str | None = typer.Option(None, help="direct or cozeloop"),
        output: Path | None = None,
    ) -> None:
        settings_changed = False
        if ai_timeout_sec is not None:
            os.environ["AI_TIMEOUT_SEC"] = str(ai_timeout_sec)
            settings_changed = True
        if executor:
            os.environ["REVIEW_V3_EXECUTOR"] = executor
            settings_changed = True
        if settings_changed:
            get_settings.cache_clear()

        parsed_item_ids = [current_item_id.strip() for current_item_id in item_ids.split(",") if current_item_id.strip()]
        if not parsed_item_ids:
            raise typer.BadParameter("At least one item_id is required.")
        results = run_review_v3_first_pass_batch(
            business_domain=business_domain,
            item_ids=parsed_item_ids,
            force=force,
        )
        serialized = json.dumps(results, ensure_ascii=False, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized)

    @app.command("review-v3-second-pass")
    def review_v3_second_pass(
        business_domain: str | None = None,
        item_id: str | None = None,
        limit: int = typer.Option(50, min=0, help="0 means no limit"),
        force: bool = False,
        ai_timeout_sec: int | None = typer.Option(30, min=5),
        executor: str | None = typer.Option(None, help="direct or cozeloop"),
        output: Path | None = None,
    ) -> None:
        settings_changed = False
        if ai_timeout_sec is not None:
            os.environ["AI_TIMEOUT_SEC"] = str(ai_timeout_sec)
            settings_changed = True
        if executor:
            os.environ["REVIEW_V3_EXECUTOR"] = executor
            settings_changed = True
        if settings_changed:
            get_settings.cache_clear()

        results = run_review_v3_second_pass(
            business_domain=business_domain,
            item_id=item_id,
            limit=limit,
            force=force,
        )
        serialized = json.dumps(results, ensure_ascii=False, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized)

    @app.command("review-v3-revalidate-second-pass")
    def review_v3_revalidate_second_pass(
        business_domain: str | None = None,
        item_id: str | None = None,
        limit: int = typer.Option(50, min=0, help="0 means no limit"),
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
        output: Path | None = None,
    ) -> None:
        results = revalidate_review_v3_second_pass(
            business_domain=business_domain,
            item_id=item_id,
            limit=limit,
            dry_run=dry_run,
        )
        serialized = json.dumps(results, ensure_ascii=False, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized)

    @app.command("sync-review-v3-compat")
    def sync_review_v3_compat(
        business_domain: str | None = None,
        item_id: str | None = None,
        limit: int = typer.Option(0, min=0, help="0 means no limit"),
        dry_run: bool = typer.Option(False, "--dry-run/--apply"),
        output: Path | None = None,
    ) -> None:
        results = sync_review_v3_compat_fields(
            business_domain=business_domain,
            item_id=item_id,
            limit=limit,
            dry_run=dry_run,
        )
        serialized = json.dumps(results, ensure_ascii=False, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized)

    @app.command("sync-review-v3-cozeloop-prompts")
    def sync_review_v3_cozeloop_prompts_command(
        business_domain: str | None = None,
        first_pass_only: bool = False,
        second_pass_only: bool = False,
        output: Path | None = None,
    ) -> None:
        if first_pass_only and second_pass_only:
            raise typer.BadParameter("Choose only one of --first-pass-only or --second-pass-only.")
        phases: tuple[str, ...]
        if first_pass_only:
            phases = ("first_pass",)
        elif second_pass_only:
            phases = ("second_pass",)
        else:
            phases = ("first_pass", "second_pass")

        if business_domain:
            profile = get_review_v3_profile(business_domain)
            if profile is None:
                raise typer.BadParameter(f"Unsupported business domain: {business_domain}")
            profiles = (profile,)
        else:
            profiles = tuple(list_review_v3_profiles())
        results = sync_review_v3_cozeloop_prompts(profiles=profiles, phases=phases)
        serialized = json.dumps(results, ensure_ascii=False, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized)

    @app.command("build-review-calibration-set")
    def build_review_calibration_set_command(
        business_domain: str | None = None,
        freshness_days: int = typer.Option(30, min=1, max=180),
        pricing_freshness_days: int = typer.Option(30, min=1, max=180),
        min_sample_points: int = typer.Option(4, min=1, max=50),
        valid_limit: int = typer.Option(30, min=0, max=500),
        invalid_limit: int = typer.Option(30, min=0, max=500),
        pending_audit_limit: int = typer.Option(30, min=0, max=500),
        high_profit_high_risk_limit: int = typer.Option(30, min=0, max=500),
        seed: int = typer.Option(42),
        output: Path | None = None,
    ) -> None:
        payload = build_review_calibration_set(
            business_domain=business_domain,
            freshness_days=freshness_days,
            pricing_freshness_days=pricing_freshness_days,
            min_sample_points=min_sample_points,
            valid_limit=valid_limit,
            invalid_limit=invalid_limit,
            pending_audit_limit=pending_audit_limit,
            high_profit_high_risk_limit=high_profit_high_risk_limit,
            seed=seed,
        )
        resolved_output = build_review_calibration_output_path(output)
        written_paths = persist_review_calibration_export(
            output=resolved_output,
            payload=payload,
        )
        typer.echo(
            json.dumps(
                {
                    "status": "ok",
                    "sample_count": len(payload.get("samples") or []),
                    "selection_summary": payload.get("selection_summary"),
                    "json_path": written_paths["json_path"],
                    "csv_path": written_paths["csv_path"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("evaluate-review-calibration-set")
    def evaluate_review_calibration_set_command(
        input_path: Path,
        output: Path | None = None,
    ) -> None:
        entries = load_review_calibration_entries(input_path)
        evaluation = evaluate_review_calibration_set(entries=entries)
        serialized = json.dumps(evaluation, ensure_ascii=False, indent=2)
        resolved_output = build_review_calibration_eval_output_path(
            input_path=input_path,
            output=output,
        )
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized)

    @app.command("validate-review-calibration-set")
    def validate_review_calibration_set_command(
        input_path: Path,
        output: Path | None = None,
    ) -> None:
        entries = load_review_calibration_entries(input_path)
        summary = validate_review_calibration_entries(entries)
        serialized = json.dumps(summary, ensure_ascii=False, indent=2)
        resolved_output = build_review_calibration_eval_output_path(
            input_path=input_path,
            output=output,
        )
        resolved_output.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized)
