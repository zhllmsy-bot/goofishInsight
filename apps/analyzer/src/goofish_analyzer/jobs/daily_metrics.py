from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from ..contract import (
    DEFAULT_LOCK_PATHS,
    build_source_contract,
)
from ..services.metrics_builder import build_daily_metrics
from ..logging import run_analyzer_job
from ._locking import analyzer_job_lock

ANALYZER_DAILY_METRICS_EXIT_CODE_ALREADY_RUNNING = 18


def run_daily_metrics_job(
    *,
    metric_date: date,
    business_domain: str | None = None,
    category_id: str | None = None,
    source_mode: str = "legacy_items",
    replace_existing: bool = True,
    dry_run: bool = False,
    lock_path: Path = DEFAULT_LOCK_PATHS["daily_metrics"],
) -> dict[str, Any]:
    source_contract = build_source_contract(source_mode)
    with analyzer_job_lock(lock_path, job_name="daily-metrics"):
        return run_analyzer_job(
            job_name="analyzer_daily_metrics",
            phase="daily_metrics",
            metric_date=metric_date,
            task_key="analyzer_daily_metrics",
            start_metadata={
                "metric_date": metric_date.isoformat(),
                "business_domain": business_domain,
                "category_id": category_id,
                "source_mode": source_mode,
                "source_contract": source_contract,
                "replace_existing": replace_existing,
                "dry_run": dry_run,
            },
            execute=lambda: _execute_daily_metrics_job(
                metric_date=metric_date,
                business_domain=business_domain,
                category_id=category_id,
                source_mode=source_mode,
                replace_existing=replace_existing,
                dry_run=dry_run,
                source_contract=source_contract,
            ),
        )


def _execute_daily_metrics_job(
    *,
    metric_date: date,
    business_domain: str | None,
    category_id: str | None,
    source_mode: str,
    replace_existing: bool,
    dry_run: bool,
    source_contract: dict[str, Any],
) -> dict[str, Any]:
    summary = build_daily_metrics(
        metric_date=metric_date,
        business_domain=business_domain,
        category_id=category_id,
        source_mode=source_mode,
        replace_existing=replace_existing,
        dry_run=dry_run,
    )
    summary.setdefault("source_contract", source_contract)
    if not dry_run:
        from goofish_analyzer.adapters import QualityMetricsService

        summary["quality_metrics"] = QualityMetricsService.refresh_operational_quality_metrics(
            metric_date=metric_date,
            business_domain=business_domain,
            category_id=category_id,
        )
    return summary
