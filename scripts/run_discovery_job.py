from __future__ import annotations

import json
from pathlib import Path

import typer

from goofish_insight.cli import (
    cleanup_historical_data,
    collect_batch,
    default_config_path,
    discover_models,
    latest_report_path,
    seed_tasks_from_config,
)
from goofish_insight.settings import get_settings

app = typer.Typer(no_args_is_help=True)


@app.command()
def main(
    config_path: Path = typer.Option(default_config_path()),
    profile_key: str = "chrome-attached",
    login_wait_seconds: int = 180,
    limit: int = 15,
    business_domain: str | None = None,
    only_task: str | None = None,
    output: Path | None = None,
    cleanup_after_run: bool = True,
) -> None:
    seed_tasks_from_config(config_path)
    collect_batch(
        config_path=config_path,
        profile_key=profile_key,
        login_wait_seconds=login_wait_seconds,
        only_task=only_task,
    )
    if cleanup_after_run:
        cleanup_historical_data(
            dry_run=False,
            prune_raw=get_settings().prune_raw_after_ingest,
            prune_snapshots=True,
            max_passes=1,
        )
    report_path = output or latest_report_path()
    discover_models(
        business_domain=business_domain,
        limit=limit,
        output=report_path,
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
