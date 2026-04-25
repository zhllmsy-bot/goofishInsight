from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from ._locking import analyzer_job_lock
from ..contract import (
    DEFAULT_LOCK_PATHS,
    build_source_contract,
)
from ..services.score_builder import build_model_scores
from ..logging import run_analyzer_job

ANALYZER_MODEL_SCORES_EXIT_CODE_ALREADY_RUNNING = 19


def run_model_scores_job(
    *,
    score_date: date,
    business_domain: str | None = None,
    category_id: str | None = None,
    source_mode: str = "legacy_items",
    replace_existing: bool = True,
    dry_run: bool = False,
    lock_path: Path = DEFAULT_LOCK_PATHS["model_scores"],
) -> dict[str, Any]:
    source_contract = build_source_contract(source_mode)
    with analyzer_job_lock(lock_path, job_name="model-scores"):
        return run_analyzer_job(
            job_name="analyzer_model_scores",
            phase="model_scores",
            metric_date=score_date,
            task_key="analyzer_model_scores",
            start_metadata={
                "score_date": score_date.isoformat(),
                "business_domain": business_domain,
                "category_id": category_id,
                "source_mode": source_mode,
                "source_contract": source_contract,
                "replace_existing": replace_existing,
                "dry_run": dry_run,
            },
            execute=lambda: _execute_model_scores_job(
                score_date=score_date,
                business_domain=business_domain,
                category_id=category_id,
                source_mode=source_mode,
                replace_existing=replace_existing,
                dry_run=dry_run,
                source_contract=source_contract,
            ),
        )


def _execute_model_scores_job(
    *,
    score_date: date,
    business_domain: str | None,
    category_id: str | None,
    source_mode: str,
    replace_existing: bool,
    dry_run: bool,
    source_contract: dict[str, Any],
) -> dict[str, Any]:
    summary = build_model_scores(
        score_date=score_date,
        business_domain=business_domain,
        category_id=category_id,
        source_mode=source_mode,
        replace_existing=replace_existing,
        dry_run=dry_run,
    )
    summary.setdefault("source_contract", source_contract)
    return summary
