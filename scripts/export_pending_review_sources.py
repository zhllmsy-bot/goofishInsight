from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "apps" / "collector" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from goofish_insight.application.services.review_export import export_review_source_groups

app = typer.Typer(no_args_is_help=True)


@app.command()
def main(
    business_domain: str | None = typer.Option(None, "--business-domain"),
    groups: int = typer.Option(20, "--groups", min=1),
    tail_percent: int = typer.Option(80, "--tail-percent", min=1, max=100),
    include_in_progress: bool = typer.Option(True, "--include-in-progress/--exclude-in-progress"),
    output_root: Path = typer.Option(REPO_ROOT / "database", "--output-root"),
) -> None:
    summary = export_review_source_groups(
        output_root=output_root,
        business_domain=business_domain,
        group_count=groups,
        tail_fraction=tail_percent / 100,
        include_in_progress=include_in_progress,
    )
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
