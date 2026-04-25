from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "apps" / "collector" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from goofish_insight.cli import review_items_llm

app = typer.Typer(no_args_is_help=True)


@app.command()
def main(
    business_domain: str | None = None,
    item_id: str | None = None,
    limit: int = typer.Option(50, min=0, help="0 means no limit"),
    force: bool = False,
    batch_size: int = typer.Option(5, min=1, max=100),
    concurrency: int = typer.Option(1, min=1, max=16),
    ai_timeout_sec: int = typer.Option(180, min=5),
    output: Path | None = None,
) -> None:
    resolved_output = output or (
        REPO_ROOT
        / "reports"
        / f"item-llm-review-preview-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    review_items_llm(
        business_domain=business_domain,
        item_id=item_id,
        limit=limit,
        force=force,
        batch_size=batch_size,
        concurrency=concurrency,
        ai_timeout_sec=ai_timeout_sec,
        output=resolved_output,
    )


if __name__ == "__main__":
    app()
