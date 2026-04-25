from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ..logging import run_analyzer_job
from ..services.buy_alerts import emit_buy_alert_events
from ..services.buy_opportunities import refresh_buy_opportunities
from ..services.buy_price_baselines import build_buy_price_baselines
from ._locking import analyzer_job_lock

DEFAULT_BUY_JOB_LOCK_DIR = Path("reports/runtime/locks")
DEFAULT_BUY_JOB_LOCK_PATHS = {
    "buy_baselines": DEFAULT_BUY_JOB_LOCK_DIR / "analyzer_buy_baselines.lock",
    "buy_opportunities": DEFAULT_BUY_JOB_LOCK_DIR / "analyzer_buy_opportunities.lock",
    "buy_alerts": DEFAULT_BUY_JOB_LOCK_DIR / "analyzer_buy_alerts.lock",
}


def run_buy_baselines_job(
    *,
    category_code: str | None = None,
    business_domain: str | None = None,
    view: str = "all",
    freshness_days: int = 30,
    min_sample_points: int = 4,
    baseline_date: date | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    lock_path: Path = DEFAULT_BUY_JOB_LOCK_PATHS["buy_baselines"],
) -> dict[str, Any]:
    target_date = baseline_date or datetime.now(UTC).date()
    with analyzer_job_lock(lock_path, job_name="buy-baselines"):
        return run_analyzer_job(
            job_name="analyzer_buy_baselines",
            phase="buy_baselines",
            metric_date=target_date,
            task_key="analyzer_buy_baselines",
            start_metadata={
                "category_code": category_code,
                "business_domain": business_domain,
                "view": view,
                "freshness_days": freshness_days,
                "min_sample_points": min_sample_points,
                "baseline_date": target_date.isoformat(),
                "limit": limit,
                "dry_run": dry_run,
            },
            execute=lambda: build_buy_price_baselines(
                category_code=category_code,
                business_domain=business_domain,
                view=view,
                freshness_days=freshness_days,
                min_sample_points=min_sample_points,
                baseline_date=target_date,
                limit=limit,
                dry_run=dry_run,
            ),
        )


def run_buy_opportunities_job(
    *,
    category_code: str | None = None,
    business_domain: str | None = None,
    freshness_days: int = 30,
    baseline_date: date | None = None,
    min_discount_rate: float = 0.02,
    min_opportunity_score: float = 35.0,
    limit: int | None = None,
    ensure_default_target: bool = True,
    dry_run: bool = False,
    lock_path: Path = DEFAULT_BUY_JOB_LOCK_PATHS["buy_opportunities"],
) -> dict[str, Any]:
    target_date = baseline_date or datetime.now(UTC).date()
    with analyzer_job_lock(lock_path, job_name="buy-opportunities"):
        return run_analyzer_job(
            job_name="analyzer_buy_opportunities",
            phase="buy_opportunities",
            metric_date=target_date,
            task_key="analyzer_buy_opportunities",
            start_metadata={
                "category_code": category_code,
                "business_domain": business_domain,
                "freshness_days": freshness_days,
                "baseline_date": target_date.isoformat(),
                "min_discount_rate": min_discount_rate,
                "min_opportunity_score": min_opportunity_score,
                "limit": limit,
                "ensure_default_target": ensure_default_target,
                "dry_run": dry_run,
            },
            execute=lambda: refresh_buy_opportunities(
                category_code=category_code,
                business_domain=business_domain,
                freshness_days=freshness_days,
                baseline_date=target_date,
                min_discount_rate=min_discount_rate,
                min_opportunity_score=min_opportunity_score,
                limit=limit,
                ensure_default_target=ensure_default_target,
                dry_run=dry_run,
            ),
        )


def run_buy_alerts_job(
    *,
    category_code: str | None = None,
    min_opportunity_score: float = 55.0,
    channel: str = "dashboard",
    limit: int | None = None,
    dry_run: bool = False,
    lock_path: Path = DEFAULT_BUY_JOB_LOCK_PATHS["buy_alerts"],
) -> dict[str, Any]:
    target_date = datetime.now(UTC).date()
    with analyzer_job_lock(lock_path, job_name="buy-alerts"):
        return run_analyzer_job(
            job_name="analyzer_buy_alerts",
            phase="buy_alerts",
            metric_date=target_date,
            task_key="analyzer_buy_alerts",
            start_metadata={
                "category_code": category_code,
                "min_opportunity_score": min_opportunity_score,
                "channel": channel,
                "limit": limit,
                "dry_run": dry_run,
            },
            execute=lambda: emit_buy_alert_events(
                category_code=category_code,
                min_opportunity_score=min_opportunity_score,
                channel=channel,
                limit=limit,
                dry_run=dry_run,
            ),
        )
