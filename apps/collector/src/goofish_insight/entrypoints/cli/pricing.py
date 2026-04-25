from __future__ import annotations

import json
from pathlib import Path

import typer

from ...analyzer_runtime import ensure_analyzer_src_on_path
from ...application.services.buy_price_baselines import build_buy_price_baselines
from ...application.services.buy_alerts import emit_buy_alert_events, summarize_buy_alert_hit_rate
from ...application.services.alert_dispatcher import dispatch_notification_deliveries
from ...application.services.outreach_outcomes import record_outreach_outcome, summarize_outreach_outcomes
from ...application.services.pricing_monitoring import summarize_template_availability_monitoring
from ...application.services.pricing_reporting import (
    _annotate_rows_with_availability,
    run_template_mode_smoke,
    write_model_discovery_report,
    write_template_smoke_report,
)
from ...application.services.pricing_entrypoints import parse_baseline_date
from ...pricing import build_pricing_views, build_spec_summary

ensure_analyzer_src_on_path()

from goofish_analyzer.services.buy_decision_hub import (  # noqa: E402
    apply_buy_feedback_calibration,
    record_buy_decision_feedback,
    refresh_buy_opportunities,
)
from goofish_analyzer.services.buy_feedback import (  # noqa: E402
    summarize_buy_feedback_calibration,
    summarize_buy_feedback_quality,
)


def register_pricing_commands(app: typer.Typer) -> None:
    @app.command("discover-models")
    def discover_models(
        business_domain: str | None = None,
        category_code: str | None = None,
        limit: int = 15,
        freshness_days: int = typer.Option(30, min=7, max=180),
        min_sample_points: int = typer.Option(4, min=2, max=20),
        output: Path | None = None,
    ) -> None:
        output_path = write_model_discovery_report(
            business_domain=business_domain,
            category_code=category_code,
            limit=limit,
            freshness_days=freshness_days,
            min_sample_points=min_sample_points,
            output=output,
        )
        typer.echo(str(output_path))

    @app.command("show-spec-summary")
    def show_spec_summary(
        business_domain: str | None = None,
        category_code: str | None = None,
        limit: int = 20,
    ) -> None:
        rows = build_spec_summary(business_domain=business_domain, category_code=category_code, limit=limit)
        rows = _annotate_rows_with_availability(
            category_scope=category_code or business_domain,
            rows=rows,
        )
        typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))

    @app.command("show-price-bands")
    def show_price_bands(
        business_domain: str | None = None,
        category_code: str | None = None,
        view: str = typer.Option("spec", help="brand, product, spec"),
        limit: int = 20,
        freshness_days: int = typer.Option(30, min=7, max=180),
        min_sample_points: int = typer.Option(4, min=2, max=20),
        actionable_only: bool = True,
    ) -> None:
        normalized_view = view.strip().lower()
        if normalized_view not in {"brand", "product", "spec"}:
            raise typer.BadParameter("view must be one of: brand, product, spec")

        rows = build_pricing_views(
            business_domain=business_domain,
            category_code=category_code,
            freshness_days=freshness_days,
            min_sample_points=min_sample_points,
        )[normalized_view]
        rows = _annotate_rows_with_availability(
            category_scope=category_code or business_domain,
            rows=rows,
        )
        if actionable_only:
            rows = [row for row in rows if row["is_actionable"]]
        typer.echo(json.dumps(rows[:limit], ensure_ascii=False, indent=2))

    @app.command("build-buy-baselines")
    def build_buy_baselines(
        category_code: str | None = None,
        business_domain: str | None = None,
        view: str = typer.Option("all", help="all, brand, product, spec"),
        freshness_days: int = typer.Option(30, min=7, max=180),
        min_sample_points: int = typer.Option(4, min=2, max=20),
        baseline_date: str | None = typer.Option(None, help="YYYY-MM-DD"),
        limit: int | None = typer.Option(None, min=1),
        dry_run: bool = False,
    ) -> None:
        result = build_buy_price_baselines(
            category_code=category_code,
            business_domain=business_domain,
            view=view,
            freshness_days=freshness_days,
            min_sample_points=min_sample_points,
            baseline_date=parse_baseline_date(baseline_date),
            limit=limit,
            dry_run=dry_run,
        )
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.command("refresh-buy-opportunities")
    def refresh_buy_opportunities_command(
        category_code: str | None = None,
        business_domain: str | None = None,
        freshness_days: int = typer.Option(30, min=7, max=180),
        baseline_date: str | None = typer.Option(None, help="YYYY-MM-DD"),
        min_discount_rate: float = typer.Option(0.02, min=0.0, max=1.0),
        min_opportunity_score: float = typer.Option(35.0, min=0.0, max=100.0),
        limit: int | None = typer.Option(None, min=1),
        ensure_default_target: bool = True,
        dry_run: bool = False,
    ) -> None:
        result = refresh_buy_opportunities(
            category_code=category_code,
            business_domain=business_domain,
            freshness_days=freshness_days,
            baseline_date=parse_baseline_date(baseline_date),
            min_discount_rate=min_discount_rate,
            min_opportunity_score=min_opportunity_score,
            limit=limit,
            ensure_default_target=ensure_default_target,
            dry_run=dry_run,
        )
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.command("emit-buy-alerts")
    def emit_buy_alerts_command(
        category_code: str | None = None,
        min_opportunity_score: float = typer.Option(55.0, min=0.0, max=100.0),
        channel: str = typer.Option("dashboard"),
        limit: int | None = typer.Option(None, min=1),
        dry_run: bool = False,
    ) -> None:
        result = emit_buy_alert_events(
            category_code=category_code,
            min_opportunity_score=min_opportunity_score,
            channel=channel,
            limit=limit,
            dry_run=dry_run,
        )
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.command("show-buy-feedback-summary")
    def show_buy_feedback_summary(
        category_code: str | None = None,
        window_days: int = typer.Option(30, min=1, max=180),
    ) -> None:
        quality = summarize_buy_feedback_quality(
            category_code=category_code,
            window_days=window_days,
        )
        calibration = summarize_buy_feedback_calibration(
            category_code=category_code,
            window_days=window_days,
        )
        payload = {
            "categoryCode": quality.get("categoryCode"),
            "windowDays": quality.get("windowDays", window_days),
            "asOf": quality.get("asOf"),
            "feedbackCount": quality.get("feedbackCount", 0),
            "acceptCount": quality.get("acceptCount", 0),
            "rejectCount": quality.get("rejectCount", 0),
            "rejectReasonCounts": quality.get("rejectReasonCounts", {}),
            "templateMatchErrorCounts": quality.get("templateMatchErrorCounts", {}),
            "templateMismatchMissingFieldCounts": quality.get(
                "templateMismatchMissingFieldCounts",
                {},
            ),
            "feedbackQuality": quality,
            "feedbackCalibration": calibration,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    @app.command("apply-buy-feedback-calibration")
    def apply_buy_feedback_calibration_command(
        category_code: str = typer.Option(..., help="Canonical category code, for example apple_computer"),
        window_days: int = typer.Option(30, min=1, max=180),
        operator_id: str | None = typer.Option(None),
        recommendation_id: list[str] | None = typer.Option(
            None,
            "--recommendation-id",
            help="Apply only selected recommendation IDs. Repeat the flag to pass multiple IDs.",
        ),
        dry_run: bool = False,
    ) -> None:
        result = apply_buy_feedback_calibration(
            category_code=category_code,
            window_days=window_days,
            operator_id=operator_id,
            recommendation_ids=recommendation_id,
            dry_run=dry_run,
        )
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.command("show-buy-alert-hit-rate")
    def show_buy_alert_hit_rate_command(
        category_code: str | None = None,
    ) -> None:
        result = summarize_buy_alert_hit_rate(category_code=category_code)
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.command("dispatch-notifications")
    def dispatch_notifications_command(
        limit: int = typer.Option(50, min=1, max=500),
        dry_run: bool = False,
    ) -> None:
        result = dispatch_notification_deliveries(limit=limit, dry_run=dry_run)
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.command("record-buy-feedback")
    def record_buy_feedback_command(
        opportunity_id: str,
        feedback_label: str,
        feedback_type: str = typer.Option("decision"),
        operator_id: str | None = None,
        feedback_note: str | None = None,
        purchase_price: str | None = None,
        expected_resale_price: str | None = None,
        link_to_alert_candidate: bool = typer.Option(
            False,
            "--link-to-alert-candidate/--no-link-to-alert-candidate",
            help="When enabled, accepted feedback may create or update a dashboard alert candidate linkage.",
        ),
        dry_run: bool = False,
    ) -> None:
        result = record_buy_decision_feedback(
            opportunity_id=opportunity_id,
            feedback_type=feedback_type,
            feedback_label=feedback_label,
            operator_id=operator_id,
            feedback_note=feedback_note,
            purchase_price=purchase_price,
            expected_resale_price=expected_resale_price,
            link_to_alert_candidate=link_to_alert_candidate,
            dry_run=dry_run,
        )
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.command("record-outreach-outcome")
    def record_outreach_outcome_command(
        outcome_status: str,
        outreach_id: int | None = typer.Option(None, min=1),
        item_id: str | None = typer.Option(None),
        deal_price: str | None = typer.Option(None),
        operator_note: str | None = typer.Option(None),
        closed_at: str | None = typer.Option(None, help="ISO datetime"),
        dry_run: bool = False,
    ) -> None:
        result = record_outreach_outcome(
            outreach_id=outreach_id,
            item_id=item_id,
            outcome_status=outcome_status,
            deal_price=deal_price,
            operator_note=operator_note,
            closed_at=closed_at,
            dry_run=dry_run,
        )
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.command("show-outreach-outcomes")
    def show_outreach_outcomes_command(
        window_days: int = typer.Option(30, min=1, max=365),
    ) -> None:
        result = summarize_outreach_outcomes(window_days=window_days)
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.command("show-template-monitoring")
    def show_template_monitoring_command(
        category_code: str | None = None,
        window_days: int = typer.Option(30, min=1, max=180),
    ) -> None:
        result = summarize_template_availability_monitoring(
            category_code=category_code,
            window_days=window_days,
        )
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.command("smoke-template-mode")
    def smoke_template_mode_command(
        base_url: str = typer.Option("http://127.0.0.1:8791"),
        category_code: str = typer.Option("apple_computer"),
        window_days: int = typer.Option(30, min=1, max=180),
        limit: int = typer.Option(20, min=1, max=200),
        pricing_view: str = typer.Option("spec"),
        pricing_scope: str = typer.Option("all"),
        pricing_limit: int = typer.Option(20, min=1, max=200),
        pricing_freshness_days: int = typer.Option(30, min=7, max=180),
        heartbeat_days: int = typer.Option(14, min=1, max=60),
        pricing_min_samples: int = typer.Option(4, min=2, max=20),
        output: Path | None = None,
        fail_on_warn: bool = False,
    ) -> None:
        report = run_template_mode_smoke(
            base_url=base_url,
            category_code=category_code,
            window_days=window_days,
            limit=limit,
            pricing_view=pricing_view,
            pricing_scope=pricing_scope,
            pricing_limit=pricing_limit,
            pricing_freshness_days=pricing_freshness_days,
            heartbeat_days=heartbeat_days,
            pricing_min_samples=pricing_min_samples,
        )
        report_path = write_template_smoke_report(report=report, output=output)
        report["reportPath"] = str(report_path)
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        if report["overallStatus"] == "fail":
            raise typer.Exit(code=1)
        if fail_on_warn and report["overallStatus"] == "warn":
            raise typer.Exit(code=1)
