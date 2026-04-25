from __future__ import annotations

import json
from pathlib import Path

import typer

from ...application.services.mobile_market_history import (
    collect_mobile_market_history,
    persist_mobile_market_history,
    save_mobile_market_history_report,
)
from ...application.services.mobile_market_history_batch import (
    default_queue_state_path,
    initialize_mainstream_bulk_queue,
    run_bulk_market_history,
)


def register_mobile_commands(app: typer.Typer) -> None:
    @app.command("capture-mobile-market-history")
    def capture_mobile_market_history(
        query: str | None = typer.Option(
            None,
            help="Target query. Current implementation prefers the current query or a recent-search chip on device.",
        ),
        serial: str | None = typer.Option(None, help="ADB serial when multiple devices are connected."),
        max_scrolls: int = typer.Option(0, min=0, max=10, help="Additional record-section scrolls to collect."),
        output: Path | None = typer.Option(None, help="Optional output JSON path."),
        persist_report: bool = typer.Option(
            True,
            "--persist-report/--no-persist-report",
            help="Persist the captured mobile market snapshot into AnalysisReport.",
        ),
    ) -> None:
        snapshot = collect_mobile_market_history(query=query, serial=serial, max_scrolls=max_scrolls)
        output_path = persist_mobile_market_history(snapshot, output=output)
        report_id = save_mobile_market_history_report(snapshot) if persist_report else None
        typer.echo(
            json.dumps(
                {
                    "output_path": str(output_path),
                    "report_id": report_id,
                    "query": snapshot.query,
                    "state": snapshot.state,
                    "recent_avg_price_7d": snapshot.recent_avg_price_7d,
                    "sold_price_range_low": snapshot.sold_price_range_low,
                    "sold_price_range_high": snapshot.sold_price_range_high,
                    "visible_record_count": len(snapshot.visible_records),
                    "warnings": snapshot.warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("init-mobile-market-history-bulk")
    def init_mobile_market_history_bulk(
        output: Path | None = typer.Option(None, help="Queue state JSON path."),
        top_n: int = typer.Option(12, min=1, max=50, help="Number of mainstream models to seed into the queue."),
        window_days: int = typer.Option(30, min=1, max=90, help="Freshness window for mainstream model selection."),
        heartbeat_days: int = typer.Option(7, min=1, max=30, help="Heartbeat window for active model selection."),
    ) -> None:
        state_path = initialize_mainstream_bulk_queue(
            path=output or default_queue_state_path(),
            top_n=top_n,
            window_days=window_days,
            heartbeat_days=heartbeat_days,
        )
        typer.echo(json.dumps({"state_path": str(state_path), "top_n": top_n}, ensure_ascii=False, indent=2))

    @app.command("run-mobile-market-history-bulk")
    def run_mobile_market_history_bulk(
        state_path: Path | None = typer.Option(None, help="Queue state JSON path."),
        serial: str | None = typer.Option(None, help="ADB serial when multiple devices are connected."),
        max_tasks: int = typer.Option(1, min=1, max=100, help="Maximum number of queue tasks to execute in this run."),
        max_scrolls: int = typer.Option(0, min=0, max=10, help="Additional record-section scrolls to collect."),
        persist_report: bool = typer.Option(
            True,
            "--persist-report/--no-persist-report",
            help="Persist successful captures into AnalysisReport.",
        ),
    ) -> None:
        result = run_bulk_market_history(
            path=state_path or default_queue_state_path(),
            serial=serial,
            max_tasks=max_tasks,
            max_scrolls=max_scrolls,
            persist_report=persist_report,
        )
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
