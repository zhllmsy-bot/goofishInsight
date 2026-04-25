from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ...category_compat import compatible_scope_keys, resolve_category_code
from ...models import HomeFeedItemDecision


def build_home_feed_decision_report(
    session: Session,
    *,
    category_code: str | None = None,
    source_platform: str = "xianyu",
    lookback_days: int = 7,
    limit: int = 50,
) -> dict[str, Any]:
    resolved_category_code = resolve_category_code(category_code) or None
    scope_keys = compatible_scope_keys(resolved_category_code) if resolved_category_code else ()
    cutoff = datetime.now(UTC) - timedelta(days=max(int(lookback_days), 1))

    rows = list(
        session.execute(
            select(HomeFeedItemDecision)
            .where(HomeFeedItemDecision.source_platform == source_platform)
            .where(HomeFeedItemDecision.updated_at >= cutoff)
            .order_by(desc(HomeFeedItemDecision.updated_at), desc(HomeFeedItemDecision.id))
        ).scalars()
    )

    filtered_rows = [
        row
        for row in rows
        if _decision_matches_scope(
            row=row,
            canonical_scope=resolved_category_code,
            scope_keys=scope_keys,
        )
    ]

    stage_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    unresolved_candidate_counts: Counter[str] = Counter()

    for row in filtered_rows:
        stage_counts[str(getattr(row, "decision_stage", "") or "unknown")] += 1
        status_counts[str(getattr(row, "decision_status", "") or "unknown")] += 1
        source_counts[str(getattr(row, "decision_source", "") or "unknown")] += 1
        reason = str(getattr(row, "decision_reason", "") or "unknown")
        reason_counts[reason] += 1
        if str(getattr(row, "decision_status", "") or "") in {
            "skipped_category_unresolved",
            "raw_category_llm_unresolved",
        }:
            for candidate in list(getattr(row, "active_candidate_business_domains", []) or []):
                unresolved_candidate_counts[str(candidate)] += 1

    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "sourcePlatform": source_platform,
        "lookbackDays": int(lookback_days),
        "categoryCode": resolved_category_code,
        "scopeKeys": list(scope_keys),
        "decisionCount": len(filtered_rows),
        "byStage": _counter_rows(stage_counts, "decisionStage"),
        "byStatus": _counter_rows(status_counts, "decisionStatus"),
        "bySource": _counter_rows(source_counts, "decisionSource"),
        "topReasons": _counter_rows(reason_counts, "decisionReason", limit=15),
        "topUnresolvedCandidates": _counter_rows(
            unresolved_candidate_counts,
            "businessDomain",
            limit=10,
        ),
        "recentDecisions": [
            {
                "itemId": row.item_id,
                "itemIdRef": row.item_id_ref,
                "decisionStage": row.decision_stage,
                "decisionStatus": row.decision_status,
                "decisionSource": row.decision_source,
                "decisionReason": row.decision_reason,
                "resolvedBusinessDomain": row.resolved_business_domain,
                "resolvedCategoryId": row.resolved_category_id,
                "resolvedTemplateId": row.resolved_template_id,
                "confidence": float(row.confidence) if row.confidence is not None else None,
                "currentOutreachStatus": row.current_outreach_status,
                "matchKey": row.match_key,
                "matchScope": row.match_scope,
                "candidateBusinessDomains": list(row.candidate_business_domains or []),
                "activeCandidateBusinessDomains": list(row.active_candidate_business_domains or []),
                "updatedAt": row.updated_at,
                "payload": row.payload or {},
            }
            for row in filtered_rows[: max(int(limit), 0)]
        ],
    }


def _decision_matches_scope(
    *,
    row: HomeFeedItemDecision,
    canonical_scope: str | None,
    scope_keys: tuple[str, ...],
) -> bool:
    if canonical_scope is None:
        return True

    resolved_business_domain = str(getattr(row, "resolved_business_domain", "") or "").strip()
    if resolved_business_domain and (
        resolved_business_domain in scope_keys or resolve_category_code(resolved_business_domain) == canonical_scope
    ):
        return True

    for candidate in list(getattr(row, "candidate_business_domains", []) or []):
        normalized = str(candidate or "").strip()
        if normalized and (normalized in scope_keys or resolve_category_code(normalized) == canonical_scope):
            return True
    return False


def _counter_rows(counter: Counter[str], key_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    rows = [
        {
            key_name: key,
            "count": int(count),
        }
        for key, count in sorted(counter.items(), key=lambda entry: (-entry[1], entry[0]))
    ]
    if limit is not None:
        return rows[: max(int(limit), 0)]
    return rows


__all__ = ["build_home_feed_decision_report"]
