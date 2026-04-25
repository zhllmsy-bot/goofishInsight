from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "apps" / "collector" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from goofish_insight.cli import apply_item_llm_review

app = typer.Typer(no_args_is_help=True)


@app.command()
def main(
    input_path: Path,
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run"),
    output: Path | None = None,
) -> None:
    resolved_output = output or (
        REPO_ROOT
        / "reports"
        / f"item-llm-review-apply-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    apply_item_llm_review(
        input_path=input_path,
        dry_run=dry_run,
        output=resolved_output,
    )


if __name__ == "__main__":
    app()
