from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import typer
from sqlalchemy import func, select


from goofish_analyzer.adapters import (
    session_scope,
    AnalysisReport,
    BuyAlertEvent,
    BuyOpportunity,
    BuyPriceBaseline,
    DailyMetric,
    ModelScore,
)

from .contract import (
    ANALYZER_JOBS,
    DEFAULT_LOCK_DIR,
    DEFAULT_LOCK_PATHS,
    EXIT_CODE_ALREADY_RUNNING,
    HEALTH_STATUS_HEALTHY,
    HEALTH_STATUS_UNHEALTHY,
    HEALTH_STATUS_UNKNOWN,
    SOURCE_MODES,
    build_source_contract,
    resolve_lock_path,
)
from .jobs.analysis_reports import run_analysis_reports_job
from .jobs.buy_side import (
    DEFAULT_BUY_JOB_LOCK_DIR,
    DEFAULT_BUY_JOB_LOCK_PATHS,
    run_buy_alerts_job,
    run_buy_baselines_job,
    run_buy_opportunities_job,
)
from .jobs.daily_metrics import run_daily_metrics_job
from .jobs.model_scores import run_model_scores_job

app = typer.Typer(no_args_is_help=True)


def _resolve_date(value: str | None) -> date:
    return datetime.now(UTC).date() if value is None else datetime.fromisoformat(value).date()


def _normalize_source_mode(value: str) -> str:
    normalized = str(value or "").strip().lower() or "legacy_items"
    if normalized not in SOURCE_MODES:
        supported = ", ".join(sorted(SOURCE_MODES))
        raise typer.BadParameter(f"unsupported source_mode '{value}', supported: {supported}")
    return normalized


def _latest_output_date(
    *,
    job: str,
    business_domain: str | None,
    category_id: str | None,
) -> date | None:
    with session_scope() as session:
        if job == "daily_metrics":
            query = select(DailyMetric.metric_date).order_by(DailyMetric.metric_date.desc()).limit(1)
            if business_domain:
                query = query.where(DailyMetric.business_domain == business_domain)
            if category_id:
                query = query.where(DailyMetric.category_id == category_id)
            return session.execute(query).scalar_one_or_none()
        if job == "model_scores":
            query = select(ModelScore.score_date).order_by(ModelScore.score_date.desc()).limit(1)
            if business_domain:
                query = query.where(ModelScore.business_domain == business_domain)
            if category_id:
                query = query.where(ModelScore.category_id == category_id)
            return session.execute(query).scalar_one_or_none()
        if job == "analysis_reports":
            query = (
                select(AnalysisReport.report_date)
                .where(AnalysisReport.report_type == "market_daily_summary")
                .order_by(AnalysisReport.report_date.desc())
                .limit(1)
            )
            if business_domain:
                query = query.where(AnalysisReport.business_domain == business_domain)
            if category_id:
                query = query.where(AnalysisReport.category_id == category_id)
            return session.execute(query).scalar_one_or_none()
    return None


def _latest_buy_outputs() -> dict[str, Any]:
    with session_scope() as session:
        latest_baseline = session.execute(
            select(BuyPriceBaseline.baseline_date).order_by(BuyPriceBaseline.baseline_date.desc()).limit(1)
        ).scalar_one_or_none()
        latest_opportunity = session.execute(
            select(BuyOpportunity.last_detected_at)
            .order_by(BuyOpportunity.last_detected_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        latest_alert = session.execute(
            select(func.coalesce(BuyAlertEvent.sent_at, BuyAlertEvent.created_at))
            .order_by(func.coalesce(BuyAlertEvent.sent_at, BuyAlertEvent.created_at).desc())
            .limit(1)
        ).scalar_one_or_none()
    return {
        "buy_price_baselines": latest_baseline.isoformat() if latest_baseline else None,
        "buy_opportunities": latest_opportunity.isoformat() if latest_opportunity else None,
        "buy_alert_events": latest_alert.isoformat() if latest_alert else None,
    }


def _date_range(start_date: date, end_date: date) -> list[date]:
    if start_date > end_date:
        return []
    days = (end_date - start_date).days
    return [date.fromordinal(start_date.toordinal() + offset) for offset in range(days + 1)]


def _resolve_run_dates(
    *,
    jobs_to_run: list[str],
    target_date: date,
    catch_up: bool,
    catch_up_lookback_days: int,
    business_domain: str | None,
    category_id: str | None,
) -> list[date]:
    if not catch_up:
        return [target_date]

    lookback_days = max(catch_up_lookback_days, 1)
    earliest_allowed_date = target_date.fromordinal(target_date.toordinal() - lookback_days + 1)
    candidate_start_dates: list[date] = []
    for job in jobs_to_run:
        latest_date = _latest_output_date(
            job=job,
            business_domain=business_domain,
            category_id=category_id,
        )
        candidate_start_dates.append(
            earliest_allowed_date
            if latest_date is None
            else date.fromordinal(latest_date.toordinal() + 1)
        )

    start_date = max(min(candidate_start_dates), earliest_allowed_date)
    return _date_range(start_date, target_date) or [target_date]


def _run_one_job(
    *,
    job: str,
    source_mode: str,
    run_date: date,
    business_domain: str | None,
    category_id: str | None,
    replace_existing: bool,
    dry_run: bool,
    lock_path: Path | None,
) -> dict[str, Any]:
    if job == "daily_metrics":
        return run_daily_metrics_job(
            metric_date=run_date,
            business_domain=business_domain,
            category_id=category_id,
            source_mode=source_mode,
            replace_existing=replace_existing,
            dry_run=dry_run,
            lock_path=resolve_lock_path(job, lock_path),
        )
    if job == "model_scores":
        return run_model_scores_job(
            score_date=run_date,
            business_domain=business_domain,
            category_id=category_id,
            source_mode=source_mode,
            replace_existing=replace_existing,
            dry_run=dry_run,
            lock_path=resolve_lock_path(job, lock_path),
        )
    if job == "analysis_reports":
        return run_analysis_reports_job(
            report_date=run_date,
            business_domain=business_domain,
            category_id=category_id,
            source_mode=source_mode,
            replace_existing=replace_existing,
            dry_run=dry_run,
            lock_path=resolve_lock_path(job, lock_path),
        )
    raise ValueError(f"unsupported analyzer job: {job}")


def _execute_run(
    *,
    normalized_job: str,
    source_mode: str,
    run_date: date,
    business_domain: str | None,
    category_id: str | None,
    replace_existing: bool,
    dry_run: bool,
    lock_path: Path | None,
    catch_up: bool,
    catch_up_lookback_days: int,
) -> None:
    jobs_to_run = sorted(ANALYZER_JOBS - {"all"}) if normalized_job == "all" else [normalized_job]
    summaries: dict[str, Any] = {}
    run_dates = _resolve_run_dates(
        jobs_to_run=jobs_to_run,
        target_date=run_date,
        catch_up=catch_up,
        catch_up_lookback_days=catch_up_lookback_days,
        business_domain=business_domain,
        category_id=category_id,
    )

    for rd in run_dates:
        date_key = rd.isoformat()
        summaries[date_key] = {}
        for current_job in jobs_to_run:
            try:
                job_summary = _run_one_job(
                    job=current_job,
                    source_mode=source_mode,
                    run_date=rd,
                    business_domain=business_domain,
                    category_id=category_id,
                    replace_existing=replace_existing,
                    dry_run=dry_run,
                    lock_path=lock_path if normalized_job != "all" else None,
                )
                if isinstance(job_summary, dict):
                    job_summary.setdefault(
                        "source_contract",
                        build_source_contract(source_mode),
                    )
                summaries[date_key][current_job] = job_summary
            except RuntimeError as exc:
                typer.echo(str(exc))
                raise typer.Exit(code=EXIT_CODE_ALREADY_RUNNING[current_job]) from exc

    source_contract = build_source_contract(source_mode)
    if len(run_dates) == 1 and normalized_job != "all":
        single_summary = summaries[run_dates[0].isoformat()][jobs_to_run[0]]
        if isinstance(single_summary, dict):
            payload = dict(single_summary)
            payload.setdefault("source_contract", source_contract)
            typer.echo(json.dumps(payload, ensure_ascii=False, default=str))
        else:
            typer.echo(json.dumps({"result": single_summary, "source_contract": source_contract}, ensure_ascii=False, default=str))
    elif len(run_dates) == 1:
        payload = dict(summaries[run_dates[0].isoformat()])
        payload["source_contract"] = source_contract
        typer.echo(json.dumps(payload, ensure_ascii=False, default=str))
    else:
        typer.echo(
            json.dumps(
                {
                    "catch_up_dates": [rd.isoformat() for rd in run_dates],
                    "runs": summaries,
                    "source_contract": source_contract,
                },
                ensure_ascii=False,
                default=str,
            )
        )


@app.command("run-job")
def run_job(
    job: str = typer.Option(
        "daily_metrics",
        "--job",
        help="Analyzer job to run: daily_metrics, model_scores, analysis_reports, or all.",
    ),
    metric_date: str | None = typer.Option(
        None,
        help="Target date in YYYY-MM-DD. Defaults to today in UTC.",
    ),
    business_domain: str | None = typer.Option(None),
    category_id: str | None = typer.Option(None),
    replace_existing: bool = typer.Option(
        True,
        "--replace-existing/--no-replace-existing",
        help="Delete existing analyzer rows for the same scope before rebuild.",
    ),
    dry_run: bool = typer.Option(False),
    lock_path: Path | None = typer.Option(
        None,
        help="Filesystem lock path. Defaults to a per-job lock under reports/runtime/locks.",
    ),
    catch_up: bool = typer.Option(
        False,
        "--catch-up/--no-catch-up",
        help="Run missing dates since the latest analyzer output, capped by --catch-up-lookback-days.",
    ),
    catch_up_lookback_days: int = typer.Option(
        7,
        min=1,
        help="Maximum catch-up window, in days.",
    ),
    source_mode: str = typer.Option(
        "legacy_items",
        "--source-mode",
        help="Analyzer read mode: legacy_items, catalog_dual_read, or catalog_primary.",
    ),
) -> None:
    normalized_job = job.strip().lower().replace("-", "_")
    if normalized_job not in ANALYZER_JOBS:
        supported = ", ".join(sorted(ANALYZER_JOBS))
        raise typer.BadParameter(f"unsupported analyzer job '{job}', supported: {supported}")
    normalized_source_mode = _normalize_source_mode(source_mode)
    resolved_run_date = _resolve_date(metric_date)

    _execute_run(
        normalized_job=normalized_job,
        source_mode=normalized_source_mode,
        run_date=resolved_run_date,
        business_domain=business_domain,
        category_id=category_id,
        replace_existing=replace_existing,
        dry_run=dry_run,
        lock_path=lock_path,
        catch_up=catch_up,
        catch_up_lookback_days=catch_up_lookback_days,
    )


@app.command("run-daily-metrics")
def run_daily_metrics(
    metric_date: str | None = typer.Option(
        None,
        help="Metric date in YYYY-MM-DD. Defaults to today in UTC.",
    ),
    business_domain: str | None = typer.Option(None),
    category_id: str | None = typer.Option(None),
    replace_existing: bool = typer.Option(
        True,
        "--replace-existing/--no-replace-existing",
    ),
    dry_run: bool = typer.Option(False),
    lock_path: Path | None = typer.Option(None),
    catch_up: bool = typer.Option(False, "--catch-up/--no-catch-up"),
    catch_up_lookback_days: int = typer.Option(7, min=1),
    source_mode: str = typer.Option(
        "legacy_items",
        "--source-mode",
        help="Analyzer read mode: legacy_items, catalog_dual_read, or catalog_primary.",
    ),
) -> None:
    normalized_source_mode = _normalize_source_mode(source_mode)
    resolved_run_date = _resolve_date(metric_date)

    _execute_run(
        normalized_job="daily_metrics",
        source_mode=normalized_source_mode,
        run_date=resolved_run_date,
        business_domain=business_domain,
        category_id=category_id,
        replace_existing=replace_existing,
        dry_run=dry_run,
        lock_path=lock_path,
        catch_up=catch_up,
        catch_up_lookback_days=catch_up_lookback_days,
    )


@app.command("run-model-scores")
def run_model_scores(
    metric_date: str | None = typer.Option(
        None,
        help="Score date in YYYY-MM-DD. Defaults to today in UTC.",
    ),
    business_domain: str | None = typer.Option(None),
    category_id: str | None = typer.Option(None),
    replace_existing: bool = typer.Option(
        True,
        "--replace-existing/--no-replace-existing",
    ),
    dry_run: bool = typer.Option(False),
    lock_path: Path | None = typer.Option(None),
    catch_up: bool = typer.Option(False, "--catch-up/--no-catch-up"),
    catch_up_lookback_days: int = typer.Option(7, min=1),
    source_mode: str = typer.Option(
        "legacy_items",
        "--source-mode",
        help="Analyzer read mode: legacy_items, catalog_dual_read, or catalog_primary.",
    ),
) -> None:
    normalized_source_mode = _normalize_source_mode(source_mode)
    resolved_run_date = _resolve_date(metric_date)

    _execute_run(
        normalized_job="model_scores",
        source_mode=normalized_source_mode,
        run_date=resolved_run_date,
        business_domain=business_domain,
        category_id=category_id,
        replace_existing=replace_existing,
        dry_run=dry_run,
        lock_path=lock_path,
        catch_up=catch_up,
        catch_up_lookback_days=catch_up_lookback_days,
    )


@app.command("run-analysis-reports")
def run_analysis_reports(
    metric_date: str | None = typer.Option(
        None,
        help="Report date in YYYY-MM-DD. Defaults to today in UTC.",
    ),
    business_domain: str | None = typer.Option(None),
    category_id: str | None = typer.Option(None),
    replace_existing: bool = typer.Option(
        True,
        "--replace-existing/--no-replace-existing",
    ),
    dry_run: bool = typer.Option(False),
    lock_path: Path | None = typer.Option(None),
    catch_up: bool = typer.Option(False, "--catch-up/--no-catch-up"),
    catch_up_lookback_days: int = typer.Option(7, min=1),
    source_mode: str = typer.Option(
        "legacy_items",
        "--source-mode",
        help="Analyzer read mode: legacy_items, catalog_dual_read, or catalog_primary.",
    ),
) -> None:
    normalized_source_mode = _normalize_source_mode(source_mode)
    resolved_run_date = _resolve_date(metric_date)

    _execute_run(
        normalized_job="analysis_reports",
        source_mode=normalized_source_mode,
        run_date=resolved_run_date,
        business_domain=business_domain,
        category_id=category_id,
        replace_existing=replace_existing,
        dry_run=dry_run,
        lock_path=lock_path,
        catch_up=catch_up,
        catch_up_lookback_days=catch_up_lookback_days,
    )


@app.command("run-all")
def run_all(
    metric_date: str | None = typer.Option(
        None,
        help="Target date in YYYY-MM-DD. Defaults to today in UTC.",
    ),
    business_domain: str | None = typer.Option(None),
    category_id: str | None = typer.Option(None),
    replace_existing: bool = typer.Option(
        True,
        "--replace-existing/--no-replace-existing",
    ),
    dry_run: bool = typer.Option(False),
    lock_path: Path | None = typer.Option(None),
    catch_up: bool = typer.Option(False, "--catch-up/--no-catch-up"),
    catch_up_lookback_days: int = typer.Option(7, min=1),
    source_mode: str = typer.Option(
        "legacy_items",
        "--source-mode",
        help="Analyzer read mode: legacy_items, catalog_dual_read, or catalog_primary.",
    ),
) -> None:
    normalized_source_mode = _normalize_source_mode(source_mode)
    resolved_run_date = _resolve_date(metric_date)

    _execute_run(
        normalized_job="all",
        source_mode=normalized_source_mode,
        run_date=resolved_run_date,
        business_domain=business_domain,
        category_id=category_id,
        replace_existing=replace_existing,
        dry_run=dry_run,
        lock_path=lock_path,
        catch_up=catch_up,
        catch_up_lookback_days=catch_up_lookback_days,
    )


@app.command("run-buy-baselines")
def run_buy_baselines(
    category_code: str | None = typer.Option(None),
    business_domain: str | None = typer.Option(None),
    view: str = typer.Option("all", help="all, brand, product, spec"),
    freshness_days: int = typer.Option(30, min=7, max=180),
    min_sample_points: int = typer.Option(4, min=2, max=20),
    baseline_date: str | None = typer.Option(None, help="Baseline date in YYYY-MM-DD. Defaults to today in UTC."),
    limit: int | None = typer.Option(None, min=1),
    dry_run: bool = typer.Option(False),
    lock_path: Path | None = typer.Option(
        None,
        help="Filesystem lock path. Defaults to reports/runtime/locks/analyzer_buy_baselines.lock.",
    ),
) -> None:
    payload = run_buy_baselines_job(
        category_code=category_code,
        business_domain=business_domain,
        view=view,
        freshness_days=freshness_days,
        min_sample_points=min_sample_points,
        baseline_date=_resolve_date(baseline_date),
        limit=limit,
        dry_run=dry_run,
        lock_path=lock_path or DEFAULT_BUY_JOB_LOCK_PATHS["buy_baselines"],
    )
    typer.echo(json.dumps(payload, ensure_ascii=False, default=str))


@app.command("run-buy-opportunities")
def run_buy_opportunities(
    category_code: str | None = typer.Option(None),
    business_domain: str | None = typer.Option(None),
    freshness_days: int = typer.Option(30, min=7, max=180),
    baseline_date: str | None = typer.Option(None, help="Baseline date in YYYY-MM-DD. Defaults to today in UTC."),
    min_discount_rate: float = typer.Option(0.02, min=0.0, max=1.0),
    min_opportunity_score: float = typer.Option(35.0, min=0.0, max=100.0),
    limit: int | None = typer.Option(None, min=1),
    ensure_default_target: bool = typer.Option(True),
    dry_run: bool = typer.Option(False),
    lock_path: Path | None = typer.Option(
        None,
        help="Filesystem lock path. Defaults to reports/runtime/locks/analyzer_buy_opportunities.lock.",
    ),
) -> None:
    payload = run_buy_opportunities_job(
        category_code=category_code,
        business_domain=business_domain,
        freshness_days=freshness_days,
        baseline_date=_resolve_date(baseline_date),
        min_discount_rate=min_discount_rate,
        min_opportunity_score=min_opportunity_score,
        limit=limit,
        ensure_default_target=ensure_default_target,
        dry_run=dry_run,
        lock_path=lock_path or DEFAULT_BUY_JOB_LOCK_PATHS["buy_opportunities"],
    )
    typer.echo(json.dumps(payload, ensure_ascii=False, default=str))


@app.command("run-buy-alerts")
def run_buy_alerts(
    category_code: str | None = typer.Option(None),
    min_opportunity_score: float = typer.Option(55.0, min=0.0, max=100.0),
    channel: str = typer.Option("dashboard"),
    limit: int | None = typer.Option(None, min=1),
    dry_run: bool = typer.Option(False),
    lock_path: Path | None = typer.Option(
        None,
        help="Filesystem lock path. Defaults to reports/runtime/locks/analyzer_buy_alerts.lock.",
    ),
) -> None:
    payload = run_buy_alerts_job(
        category_code=category_code,
        min_opportunity_score=min_opportunity_score,
        channel=channel,
        limit=limit,
        dry_run=dry_run,
        lock_path=lock_path or DEFAULT_BUY_JOB_LOCK_PATHS["buy_alerts"],
    )
    typer.echo(json.dumps(payload, ensure_ascii=False, default=str))


@app.command("health")
def health() -> None:
    health_status = HEALTH_STATUS_HEALTHY
    latest_outputs: dict[str, Any] = {}
    latest_buy_outputs: dict[str, Any] = {}

    try:
        with session_scope() as session:
            latest_daily = session.execute(
                select(DailyMetric.metric_date).order_by(DailyMetric.metric_date.desc()).limit(1)
            ).scalar_one_or_none()
            latest_outputs["daily_metrics"] = latest_daily.isoformat() if latest_daily else None

            latest_score = session.execute(
                select(ModelScore.score_date).order_by(ModelScore.score_date.desc()).limit(1)
            ).scalar_one_or_none()
            latest_outputs["model_scores"] = latest_score.isoformat() if latest_score else None

            latest_report = session.execute(
                select(AnalysisReport.report_date)
                .where(AnalysisReport.report_type == "market_daily_summary")
                .order_by(AnalysisReport.report_date.desc())
                .limit(1)
            ).scalar_one_or_none()
            latest_outputs["analysis_reports"] = latest_report.isoformat() if latest_report else None

            if all(v is None for v in latest_outputs.values()):
                health_status = HEALTH_STATUS_UNKNOWN

        latest_buy_outputs = _latest_buy_outputs()

    except Exception:
        health_status = HEALTH_STATUS_UNHEALTHY

    typer.echo(
        json.dumps(
            {
                "health_status": health_status,
                "latest_outputs": latest_outputs,
                "latest_buy_outputs": latest_buy_outputs,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=False,
            default=str,
        )
    )


@app.command("status")
def status() -> None:
    health_status = HEALTH_STATUS_HEALTHY
    latest_outputs: dict[str, Any] = {}
    latest_buy_outputs: dict[str, Any] = {}

    try:
        with session_scope() as session:
            latest_daily = session.execute(
                select(DailyMetric.metric_date).order_by(DailyMetric.metric_date.desc()).limit(1)
            ).scalar_one_or_none()
            latest_outputs["daily_metrics"] = latest_daily.isoformat() if latest_daily else None

            latest_score = session.execute(
                select(ModelScore.score_date).order_by(ModelScore.score_date.desc()).limit(1)
            ).scalar_one_or_none()
            latest_outputs["model_scores"] = latest_score.isoformat() if latest_score else None

            latest_report = session.execute(
                select(AnalysisReport.report_date)
                .where(AnalysisReport.report_type == "market_daily_summary")
                .order_by(AnalysisReport.report_date.desc())
                .limit(1)
            ).scalar_one_or_none()
            latest_outputs["analysis_reports"] = latest_report.isoformat() if latest_report else None

            if all(v is None for v in latest_outputs.values()):
                health_status = HEALTH_STATUS_UNKNOWN

        latest_buy_outputs = _latest_buy_outputs()

    except Exception:
        health_status = HEALTH_STATUS_UNHEALTHY

    typer.echo(
        json.dumps(
            {
                "health": {
                    "health_status": health_status,
                    "latest_outputs": latest_outputs,
                    "latest_buy_outputs": latest_buy_outputs,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                "supported_jobs": sorted(ANALYZER_JOBS - {"all"}),
                "supported_buy_jobs": ["buy_baselines", "buy_opportunities", "buy_alerts"],
                "source_modes": sorted(SOURCE_MODES),
                "default_lock_dir": str(DEFAULT_LOCK_DIR),
                "default_lock_paths": {k: str(v) for k, v in DEFAULT_LOCK_PATHS.items()},
                "default_buy_job_lock_dir": str(DEFAULT_BUY_JOB_LOCK_DIR),
                "default_buy_job_lock_paths": {k: str(v) for k, v in DEFAULT_BUY_JOB_LOCK_PATHS.items()},
                "exit_codes_already_running": EXIT_CODE_ALREADY_RUNNING,
            },
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    app()
