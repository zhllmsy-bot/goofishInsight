from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from ._locking import analyzer_job_lock
from ..contract import (
    DEFAULT_LOCK_PATHS,
    build_source_contract,
)
from ..services.report_builder import build_analysis_reports
from ..logging import run_analyzer_job

ANALYZER_ANALYSIS_REPORTS_EXIT_CODE_ALREADY_RUNNING = 20


def run_analysis_reports_job(
    *,
    report_date: date,
    business_domain: str | None = None,
    category_id: str | None = None,
    source_mode: str = "legacy_items",
    replace_existing: bool = True,
    dry_run: bool = False,
    lock_path: Path = DEFAULT_LOCK_PATHS["analysis_reports"],
) -> dict[str, Any]:
    source_contract = build_source_contract(source_mode)
    with analyzer_job_lock(lock_path, job_name="analysis-reports"):
        return run_analyzer_job(
            job_name="analyzer_analysis_reports",
            phase="analysis_reports",
            metric_date=report_date,
            task_key="analyzer_analysis_reports",
            start_metadata={
                "report_date": report_date.isoformat(),
                "business_domain": business_domain,
                "category_id": category_id,
                "source_mode": source_mode,
                "source_contract": source_contract,
                "replace_existing": replace_existing,
                "dry_run": dry_run,
            },
            execute=lambda: _execute_analysis_reports_job(
                report_date=report_date,
                business_domain=business_domain,
                category_id=category_id,
                source_mode=source_mode,
                replace_existing=replace_existing,
                dry_run=dry_run,
                source_contract=source_contract,
            ),
        )


def _execute_analysis_reports_job(
    *,
    report_date: date,
    business_domain: str | None,
    category_id: str | None,
    source_mode: str,
    replace_existing: bool,
    dry_run: bool,
    source_contract: dict[str, Any],
) -> dict[str, Any]:
    summary = build_analysis_reports(
        report_date=report_date,
        business_domain=business_domain,
        category_id=category_id,
        source_mode=source_mode,
        replace_existing=replace_existing,
        dry_run=dry_run,
    )
    summary.setdefault("source_contract", source_contract)
    return summary
