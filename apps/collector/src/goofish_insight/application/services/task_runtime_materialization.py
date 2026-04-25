from __future__ import annotations

from typing import Any

from ...models import CrawlTask, CrawlTaskLexicon, CrawlTaskQuery


def materialize_task_runtime_fields(task: CrawlTask) -> dict[str, Any]:
    query_rows = sorted(
        [
            row
            for row in list(getattr(task, "queries", []) or [])
            if str(getattr(row, "status", "") or "").upper() == "ACTIVE"
            and str(getattr(row, "query_text", "") or "").strip()
        ],
        key=lambda row: (int(getattr(row, "priority", 100) or 100), str(getattr(row, "query_text", "") or "")),
    )
    task.keywords = [str(row.query_text).strip() for row in query_rows]

    lexicon_rows = [
        row
        for row in list(getattr(task, "lexicons", []) or [])
        if str(getattr(row, "status", "") or "").upper() == "ACTIVE"
        and str(getattr(row, "term", "") or "").strip()
    ]
    task.brand_lexicon = _materialize_lexicon_terms(lexicon_rows, lexicon_type="BRAND")
    task.model_lexicon = _materialize_lexicon_terms(lexicon_rows, lexicon_type="MODEL")
    task.config_lexicon = _materialize_lexicon_terms(lexicon_rows, lexicon_type="CONFIG")
    return {
        "queryCount": len(task.keywords or []),
        "brandLexiconCount": len(task.brand_lexicon or []),
        "modelLexiconCount": len(task.model_lexicon or []),
        "configLexiconCount": len(task.config_lexicon or []),
    }


def _materialize_lexicon_terms(
    rows: list[CrawlTaskLexicon],
    *,
    lexicon_type: str,
) -> list[str]:
    normalized_type = str(lexicon_type or "").upper()
    filtered_rows = sorted(
        [
            row
            for row in rows
            if normalized_type == str(getattr(row, "lexicon_type", "") or "").upper()
        ],
        key=lambda row: (int(getattr(row, "priority", 100) or 100), str(getattr(row, "term", "") or "")),
    )
    return [str(row.term).strip() for row in filtered_rows]
