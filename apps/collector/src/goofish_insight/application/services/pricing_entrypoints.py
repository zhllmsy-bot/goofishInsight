from __future__ import annotations

from datetime import date

import typer


def parse_baseline_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("baseline-date must use YYYY-MM-DD") from exc
