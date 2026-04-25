from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import typer

from goofish_insight.application.services.collector_batch_runtime import (
    BATCH_COLLECT_ALREADY_RUNNING_EXIT_CODE,
    run_collect_batch_orchestration,
    summarize_batch_risk_event_db,
    summarize_batch_risk_event_log,
)
from goofish_insight.application.services.browser_guard import (
    DEFAULT_BROWSER_GUARD_BASE_SECONDS,
    DEFAULT_BROWSER_GUARD_MAX_SECONDS,
    default_browser_guard_event_log_path,
    default_browser_guard_state_path,
    evaluate_browser_guard_preflight,
    format_browser_guard_preflight_message,
    record_browser_guard_observation,
    render_browser_guard_shell_exports,
)
from goofish_insight.application.services.browser_guard_analytics import (
    build_browser_guard_pattern_report,
    persist_browser_job_attempt,
)
from goofish_insight.application.services.collector_runtime import (
    get_latest_collector_job_run_state,
    upsert_collector_job_run_state,
)


def _normalize_cdp_url(value: str | None) -> str | None:
    resolved = str(value or "").strip()
    return resolved or None


def _is_browser_cdp_ready(cdp_url: str) -> bool:
    try:
        with urlopen(f"{cdp_url.rstrip('/')}/json/version", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, URLError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and bool(payload)


def _build_browser_unavailable_decision(
    *,
    profile_key: str,
    feature: str,
    scope_key: str | None,
    cdp_url: str | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "allowed": False,
        "decision": "browser_unavailable",
        "profile_key": profile_key,
        "feature": feature,
        "scope_key": scope_key,
        "auth_state": "browser_unavailable",
        "source": "browser_preflight",
        "reason": reason,
        "wait_seconds": 0,
        "recommended_sleep_seconds": 5,
        "next_retry_at": None,
        "cooldown_started_at": None,
        "error_message": None,
        "cdp_url": cdp_url,
    }


def _guard_preflight_or_echo(
    *,
    profile_key: str,
    feature: str,
    scope_key: str | None = None,
) -> dict[str, Any]:
    decision = evaluate_browser_guard_preflight(
        profile_key=profile_key,
        feature=feature,
        scope_key=scope_key,
    )
    if not decision["allowed"]:
        typer.echo(
            json.dumps(
                {
                    "status": "blocked_by_browser_guard",
                    "browser_guard": decision,
                    "message": format_browser_guard_preflight_message(decision),
                },
                ensure_ascii=False,
            )
        )
    return decision


def register_collect_commands(
    app: typer.Typer,
    *,
    build_crawl_task_runtime_config,
    search_plan_entry_cls,
    default_config_path,
    ensure_task,
    export_task_config_bundle,
    get_settings,
    get_task_or_raise,
    group_batch_plans_by_platform,
    load_profile_settings,
    load_task_config,
    run_live_search_batch,
    run_live_search_capture,
    write_model_discovery_report,
) -> None:
    @app.command("preflight-browser-job")
    def preflight_browser_job(
        profile_key: str = typer.Option("default", help="Browser profile key shared by the job."),
        feature: str = typer.Option(..., help="Logical browser job feature, for example collect_batch/home_feed."),
        scope_key: str | None = typer.Option(None, help="Optional narrower feature scope."),
        state_path: Path = typer.Option(default_browser_guard_state_path(), help="Shared browser guard state path."),
        cdp_url: str | None = typer.Option(None, help="Optional attached browser CDP URL to probe."),
        require_browser_ready: bool = typer.Option(
            False,
            help="Also require the attached browser CDP endpoint to be reachable.",
        ),
        output_format: str = typer.Option("json", help="Output format: json or shell."),
        fail_on_block: bool = typer.Option(False, help="Exit non-zero when guard blocks the job."),
    ) -> None:
        decision = evaluate_browser_guard_preflight(
            profile_key=profile_key,
            feature=feature,
            scope_key=scope_key,
            state_path=state_path,
        )
        resolved_cdp_url = _normalize_cdp_url(cdp_url)
        if decision.get("allowed") and require_browser_ready:
            if resolved_cdp_url is None:
                decision = _build_browser_unavailable_decision(
                    profile_key=profile_key,
                    feature=feature,
                    scope_key=scope_key,
                    cdp_url=None,
                    reason="cdp_url_missing",
                )
            elif not _is_browser_cdp_ready(resolved_cdp_url):
                decision = _build_browser_unavailable_decision(
                    profile_key=profile_key,
                    feature=feature,
                    scope_key=scope_key,
                    cdp_url=resolved_cdp_url,
                    reason="cdp_unreachable",
                )
        resolved_output_format = str(output_format or "").strip().lower()
        if resolved_output_format == "shell":
            typer.echo(render_browser_guard_shell_exports(decision))
        else:
            payload = dict(decision)
            payload["message"] = format_browser_guard_preflight_message(decision)
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        if fail_on_block and not bool(decision.get("allowed")):
            raise typer.Exit(code=19)

    @app.command("collect-search")
    def collect_search(
        query: str,
        task_key: str | None = None,
        pages: int = 1,
        channel: str = "msedge",
        headless: bool = False,
        profile_key: str = "default",
        login_wait_seconds: int = 180,
    ) -> None:
        settings = get_settings()
        resolved_task_key = task_key or settings.default_task_key
        profile_settings = load_profile_settings(profile_key)
        resolved_channel = profile_settings.get("channel", channel)
        resolved_headless = bool(profile_settings.get("headless", headless))
        resolved_cdp_url = profile_settings.get("cdp_url")
        profile_dir = settings.browser_profile_dir / profile_key
        profile_dir.mkdir(parents=True, exist_ok=True)

        task = get_task_or_raise(resolved_task_key)
        guard_decision = _guard_preflight_or_echo(
            profile_key=profile_key,
            feature="collect_search",
            scope_key=f"{resolved_task_key}|{query}",
        )
        if not guard_decision["allowed"]:
            persist_browser_job_attempt(
                profile_key=profile_key,
                feature="collect_search",
                stage="preflight",
                scope_key=f"{resolved_task_key}|{query}",
                task_key=resolved_task_key,
                query=query,
                business_domain=getattr(task, "business_domain", None),
                attempt_outcome="blocked_by_guard",
                auth_state=guard_decision.get("auth_state"),
                guard_blocked=True,
                error_message=guard_decision.get("error_message"),
                metadata={"browser_guard": guard_decision},
            )
            return

        if resolved_cdp_url:
            outcomes = run_live_search_batch(
                plans=[search_plan_entry_cls(task=task, query=query, pages=pages)],
                channel=resolved_channel,
                headless=resolved_headless,
                cdp_url=resolved_cdp_url,
                parallel_tabs=1,
                profile_key=profile_key,
                profile_dir=profile_dir,
                login_wait_seconds=login_wait_seconds,
            )
            outcome = outcomes[0] if outcomes else None
            if outcome is not None and getattr(outcome, "status", None) == "completed":
                record_browser_guard_observation(
                    profile_key=profile_key,
                    feature="collect_search",
                    scope_key=f"{resolved_task_key}|{query}",
                    auth_state="authenticated",
                )
                persist_browser_job_attempt(
                    profile_key=profile_key,
                    feature="collect_search",
                    scope_key=f"{resolved_task_key}|{query}",
                    task_key=resolved_task_key,
                    task_query_id=str(getattr(outcome, "task_query_id", "") or "") or None,
                    query=query,
                    business_domain=getattr(task, "business_domain", None),
                    attempt_outcome="completed",
                    auth_state="authenticated",
                    metadata={
                        "status": getattr(outcome, "status", None),
                        "pages_requested": pages,
                    },
                )
            elif outcome is not None:
                record_browser_guard_observation(
                    profile_key=profile_key,
                    feature="collect_search",
                    scope_key=f"{resolved_task_key}|{query}",
                    auth_state=getattr(outcome, "auth_state", None),
                    error_message=getattr(outcome, "error_message", None),
                )
                persist_browser_job_attempt(
                    profile_key=profile_key,
                    feature="collect_search",
                    scope_key=f"{resolved_task_key}|{query}",
                    task_key=resolved_task_key,
                    task_query_id=str(getattr(outcome, "task_query_id", "") or "") or None,
                    query=query,
                    business_domain=getattr(task, "business_domain", None),
                    attempt_outcome=str(getattr(outcome, "status", None) or "failed"),
                    auth_state=getattr(outcome, "auth_state", None),
                    error_message=getattr(outcome, "error_message", None),
                    metadata={
                        "status": getattr(outcome, "status", None),
                        "pages_requested": pages,
                    },
                )
                raise RuntimeError(getattr(outcome, "error_message", None) or "Attached collection failed.")
            typer.echo(f"Attached collection finished for query '{query}'.")
            return

        try:
            result = run_live_search_capture(
                task=task,
                query=query,
                pages=pages,
                channel=resolved_channel,
                headless=resolved_headless,
                profile_key=profile_key,
                profile_dir=profile_dir,
                login_wait_seconds=login_wait_seconds,
            )
        except Exception as exc:
            record_browser_guard_observation(
                profile_key=profile_key,
                feature="collect_search",
                scope_key=f"{resolved_task_key}|{query}",
                error_message=str(exc),
            )
            persist_browser_job_attempt(
                profile_key=profile_key,
                feature="collect_search",
                scope_key=f"{resolved_task_key}|{query}",
                task_key=resolved_task_key,
                query=query,
                business_domain=getattr(task, "business_domain", None),
                attempt_outcome="failed",
                error_message=str(exc),
                metadata={"pages_requested": pages},
            )
            raise
        record_browser_guard_observation(
            profile_key=profile_key,
            feature="collect_search",
            scope_key=f"{resolved_task_key}|{query}",
            auth_state="authenticated",
        )
        persist_browser_job_attempt(
            profile_key=profile_key,
            feature="collect_search",
            scope_key=f"{resolved_task_key}|{query}",
            task_key=resolved_task_key,
            query=query,
            business_domain=getattr(task, "business_domain", None),
            attempt_outcome="completed",
            auth_state="authenticated",
            metadata={
                "pages_requested": pages,
                "pages_succeeded": result.get("pages_succeeded"),
            },
        )
        typer.echo(f"Captured {result['pages_succeeded']} valid search payload(s) for query '{query}'.")

    @app.command("collect-batch")
    def collect_batch(
        config_path: Path = typer.Option(default_config_path()),
        profile_key: str = "default",
        login_wait_seconds: int = 180,
        only_task: str | None = None,
        checkpoint_mode: str = typer.Option(
            "eager",
            help="Checkpoint mode: eager advances cursor at selection time, commit advances only after a healthy run.",
        ),
        job_phase: str = typer.Option(
            "batch",
            help="Logical batch phase label written into collector_job_run (for example probe/batch).",
        ),
        parallel_tabs: int | None = typer.Option(None, min=1, max=10),
        max_plans_per_run: int = typer.Option(
            0,
            min=0,
            help="When > 0, run only this many query plans per collect-batch run.",
        ),
        cursor_state_path: Path | None = typer.Option(
            None,
            help="Optional JSON state file used to rotate query plans across runs.",
        ),
        risk_backoff_state_path: Path = typer.Option(
            Path("reports/runtime/batch_collect_risk_backoff.json"),
            help="JSON state file for per-query risk-control exponential backoff.",
        ),
        risk_event_log_path: Path = typer.Option(
            Path("reports/runtime/batch_collect_risk_events.jsonl"),
            help="JSONL event log that records risk-control hit timestamps.",
        ),
        browser_guard_state_path: Path = typer.Option(
            default_browser_guard_state_path(),
            help="Shared profile-level browser guard state path.",
        ),
        browser_guard_event_log_path: Path = typer.Option(
            default_browser_guard_event_log_path(),
            help="Shared browser guard event log path.",
        ),
        browser_guard_base_seconds: int = typer.Option(
            DEFAULT_BROWSER_GUARD_BASE_SECONDS,
            min=60,
            max=86400,
            help="Profile-level cooldown seconds after first browser guard hit.",
        ),
        browser_guard_max_seconds: int = typer.Option(
            DEFAULT_BROWSER_GUARD_MAX_SECONDS,
            min=600,
            max=604800,
            help="Maximum profile-level browser guard cooldown seconds.",
        ),
        risk_backoff_base_seconds: int = typer.Option(
            600,
            min=60,
            max=86400,
            help="Base wait seconds after first risk-control hit (default 10 minutes).",
        ),
        risk_backoff_max_seconds: int = typer.Option(
            21600,
            min=600,
            max=604800,
            help="Maximum wait seconds for exponential backoff after repeated risk hits.",
        ),
        max_pages_per_plan: int | None = typer.Option(
            None,
            min=1,
            help="Optional per-plan page cap for this run. Useful for startup probes.",
        ),
        exit_on_risk_event: bool = typer.Option(
            False,
            help="When enabled, exit with code 19 if this run recorded at least one risk-control event.",
        ),
    ) -> None:
        run_collect_batch_orchestration(
            config_path=config_path,
            profile_key=profile_key,
            login_wait_seconds=login_wait_seconds,
            only_task=only_task,
            checkpoint_mode=checkpoint_mode,
            job_phase=job_phase,
            parallel_tabs=parallel_tabs,
            max_plans_per_run=max_plans_per_run,
            cursor_state_path=cursor_state_path,
            risk_backoff_state_path=risk_backoff_state_path,
            risk_event_log_path=risk_event_log_path,
            browser_guard_state_path=browser_guard_state_path,
            browser_guard_event_log_path=browser_guard_event_log_path,
            browser_guard_base_seconds=browser_guard_base_seconds,
            browser_guard_max_seconds=browser_guard_max_seconds,
            risk_backoff_base_seconds=risk_backoff_base_seconds,
            risk_backoff_max_seconds=risk_backoff_max_seconds,
            max_pages_per_plan=max_pages_per_plan,
            exit_on_risk_event=exit_on_risk_event,
            build_crawl_task_runtime_config=build_crawl_task_runtime_config,
            ensure_task=ensure_task,
            export_task_config_bundle=export_task_config_bundle,
            get_settings=get_settings,
            get_task_or_raise=get_task_or_raise,
            group_batch_plans_by_platform=group_batch_plans_by_platform,
            load_task_config=load_task_config,
            run_live_search_batch=run_live_search_batch,
            search_plan_entry_cls=search_plan_entry_cls,
        )

    @app.command("set-collector-runtime-state")
    def set_collector_runtime_state(
        job_name: str = typer.Option("batch_collect"),
        phase: str = typer.Option(..., help="Runtime phase label, for example cooldown/resume."),
        status: str = typer.Option("running", help="Runtime status, for example running/degraded/failed."),
        cooldown_reason: str | None = typer.Option(None, help="Cooldown trigger reason."),
        cooldown_started_at: str | None = typer.Option(None, help="Cooldown start timestamp (ISO8601)."),
        recovery_eta: str | None = typer.Option(None, help="Expected recovery timestamp (ISO8601)."),
        next_retry_at: str | None = typer.Option(None, help="Next retry timestamp (ISO8601)."),
        recent_risk_event: str | None = typer.Option(None, help="Recent risk-control event summary."),
        recent_failure_reason: str | None = typer.Option(None, help="Recent failure reason summary."),
        cooldown_seconds: int | None = typer.Option(None, min=0, help="Cooldown window in seconds."),
        next_cooldown_seconds: int | None = typer.Option(
            None,
            min=0,
            help="Persisted resident recovery backoff that should be used after the current cooldown.",
        ),
    ) -> None:
        metadata = {
            "cooldown_reason": cooldown_reason,
            "cooldown_started_at": cooldown_started_at,
            "recovery_eta": recovery_eta,
            "next_retry_at": next_retry_at,
            "recent_risk_event": recent_risk_event,
            "recent_failure_reason": recent_failure_reason,
            "cooldown_seconds": cooldown_seconds,
            "next_cooldown_seconds": next_cooldown_seconds,
            "state_updated_at": datetime.now(UTC).isoformat(),
        }
        metadata = {key: value for key, value in metadata.items() if value is not None}
        job_run_id = upsert_collector_job_run_state(
            job_name=job_name,
            phase=phase,
            status=status,
            metadata=metadata,
        )
        typer.echo(
            json.dumps(
                {
                    "job_run_id": str(job_run_id),
                    "job_name": job_name,
                    "phase": phase,
                    "status": status,
                },
                ensure_ascii=False,
            )
        )

    @app.command("get-collector-runtime-state")
    def get_collector_runtime_state(
        job_name: str = typer.Option("batch_collect"),
    ) -> None:
        payload = get_latest_collector_job_run_state(job_name=job_name)
        typer.echo(json.dumps(payload or {}, ensure_ascii=False))

    @app.command("summarize-batch-risk-events")
    def summarize_batch_risk_events(
        source: str = typer.Option(
            "db",
            help="Summary source: db or log. Defaults to db.",
        ),
        risk_event_log_path: Path = typer.Option(
            Path("reports/runtime/batch_collect_risk_events.jsonl"),
            help="JSONL event log generated by collect-batch risk-control tracking.",
        ),
        lookback_hours: int = typer.Option(168, min=1, max=24 * 365),
        top_n: int = typer.Option(20, min=1, max=200),
    ) -> None:
        resolved_source = str(source or "").strip().lower() or "db"
        if resolved_source == "db":
            try:
                summary = summarize_batch_risk_event_db(
                    lookback_hours=lookback_hours,
                    top_n=top_n,
                    now=datetime.now(UTC),
                )
            except Exception as exc:
                summary = summarize_batch_risk_event_log(
                    risk_event_log_path=risk_event_log_path,
                    lookback_hours=lookback_hours,
                    top_n=top_n,
                    now=datetime.now(UTC),
                )
                summary["note"] = (
                    f"db_summary_failed:{type(exc).__name__}; "
                    "fell back to jsonl log summary"
                )
        else:
            summary = summarize_batch_risk_event_log(
                risk_event_log_path=risk_event_log_path,
                lookback_hours=lookback_hours,
                top_n=top_n,
                now=datetime.now(UTC),
            )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("report-browser-guard-patterns")
    def report_browser_guard_patterns(
        lookback_hours: int = typer.Option(168, min=1, max=24 * 365),
        top_n: int = typer.Option(20, min=1, max=200),
        profile_key: str | None = typer.Option(None, help="Optional profile filter."),
        include_tests: bool = typer.Option(False, help="Include smoke/task-* test traffic."),
    ) -> None:
        report = build_browser_guard_pattern_report(
            lookback_hours=lookback_hours,
            top_n=top_n,
            now=datetime.now(UTC),
            profile_key=profile_key,
            include_tests=include_tests,
        )
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))

    @app.command("run-discovery")
    def run_discovery(
        config_path: Path = typer.Option(default_config_path()),
        profile_key: str = "default",
        login_wait_seconds: int = 180,
        limit: int = 15,
        parallel_tabs: int | None = typer.Option(None, min=1, max=10),
        task_key: str | None = None,
    ) -> None:
        try:
            config = load_task_config(config_path)
        except FileNotFoundError:
            config = export_task_config_bundle(config_path=config_path, include_inactive=False)
        for task in config.get("tasks", []):
            ensure_task(task)

        collect_batch(
            config_path=config_path,
            profile_key=profile_key,
            login_wait_seconds=login_wait_seconds,
            only_task=task_key,
            parallel_tabs=parallel_tabs,
        )
        selected_business_domain = None
        if task_key:
            selected_business_domain = get_task_or_raise(task_key).business_domain
        output_path = write_model_discovery_report(
            business_domain=selected_business_domain,
            category_code=None,
            limit=limit,
            freshness_days=30,
            min_sample_points=4,
            output=None,
        )
        typer.echo(str(output_path))

    @app.command("import-task-config")
    def import_task_config(
        config_path: Path = typer.Option(default_config_path()),
    ) -> None:
        config = load_task_config(config_path)
        for task in config.get("tasks", []):
            ensure_task(task)
            typer.echo(f"Imported task: {task['task_key']}")

    @app.command("export-task-config")
    def export_task_config(
        output: Path = typer.Option(default_config_path()),
        include_inactive: bool = False,
    ) -> None:
        payload = export_task_config_bundle(config_path=output, include_inactive=include_inactive)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        typer.echo(str(output))
