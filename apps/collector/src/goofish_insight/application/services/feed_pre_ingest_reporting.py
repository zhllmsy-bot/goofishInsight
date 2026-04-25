from __future__ import annotations

from collections import Counter, deque
from pathlib import Path
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...category_compat import compatible_scope_keys, resolve_category_code
from ...models import ItemIngestRejection


def build_feed_pre_ingest_rejection_report(
    session: Session,
    *,
    category_code: str | None = None,
    source_platform: str = "xianyu",
    limit: int = 20,
    sample_limit: int = 20,
    log_scan_lines: int = 400,
    log_path: Path | None = None,
) -> dict[str, Any]:
    resolved_category_code = resolve_category_code(category_code) or None
    scope_keys = compatible_scope_keys(resolved_category_code) if resolved_category_code else ()
    resolved_log_path = log_path or _default_home_feed_log_path()
    rows = list(
        session.execute(
            select(ItemIngestRejection).where(
                ItemIngestRejection.source_platform == source_platform,
                ItemIngestRejection.rejection_stage == "feed_pre_ingest_template",
            )
        ).scalars().all()
    )
    filtered_rows = [
        row
        for row in rows
        if _rejection_matches_scope(
            business_domain=getattr(row, "business_domain", None),
            scope_keys=scope_keys,
            canonical_scope=resolved_category_code,
        )
    ]
    ordered_rows = sorted(
        filtered_rows,
        key=lambda row: str(getattr(row, "last_rejected_at", "") or ""),
        reverse=True,
    )

    domain_counts: Counter[str] = Counter()
    domain_hit_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    reason_hit_counts: Counter[str] = Counter()
    for row in filtered_rows:
        canonical_business_domain = resolve_category_code(getattr(row, "business_domain", None)) or (
            str(getattr(row, "business_domain", "") or "").strip() or "unknown"
        )
        reason = str(getattr(row, "rejection_reason", "") or "unknown")
        hits = int(getattr(row, "hit_count", 0) or 0)
        domain_counts[canonical_business_domain] += 1
        domain_hit_counts[canonical_business_domain] += hits
        reason_counts[reason] += 1
        reason_hit_counts[reason] += hits

    samples = _load_feed_pre_ingest_rejection_samples(
        log_path=resolved_log_path,
        sample_limit=sample_limit,
        scan_lines=log_scan_lines,
        scope_keys=scope_keys,
        canonical_scope=resolved_category_code,
    )

    return {
        "sourcePlatform": source_platform,
        "categoryCode": resolved_category_code,
        "scopeKeys": list(scope_keys),
        "dbSummary": {
            "rejectedItemCount": len(filtered_rows),
            "totalHitCount": sum(int(getattr(row, "hit_count", 0) or 0) for row in filtered_rows),
        },
        "byBusinessDomain": [
            {
                "businessDomain": key,
                "rejectedItemCount": int(domain_counts[key]),
                "totalHitCount": int(domain_hit_counts[key]),
            }
            for key in sorted(domain_counts.keys())
        ],
        "byReason": [
            {
                "reason": key,
                "rejectedItemCount": int(reason_counts[key]),
                "totalHitCount": int(reason_hit_counts[key]),
            }
            for key in sorted(reason_counts.keys())
        ],
        "recentRejections": [
            {
                "itemId": getattr(row, "item_id", None),
                "businessDomain": getattr(row, "business_domain", None),
                "canonicalBusinessDomain": resolve_category_code(getattr(row, "business_domain", None)) or None,
                "categoryId": getattr(row, "category_id", None),
                "reason": getattr(row, "rejection_reason", None),
                "hitCount": int(getattr(row, "hit_count", 0) or 0),
                "firstRejectedAt": getattr(row, "first_rejected_at", None),
                "lastRejectedAt": getattr(row, "last_rejected_at", None),
            }
            for row in ordered_rows[: max(limit, 0)]
        ],
        "logSummary": {
            "logPath": str(resolved_log_path) if resolved_log_path is not None else None,
            "sampleCount": len(samples),
            "sampleReasonCounts": _sample_reason_counts(samples),
            "samples": samples,
        },
    }


def _load_feed_pre_ingest_rejection_samples(
    *,
    log_path: Path | None,
    sample_limit: int,
    scan_lines: int,
    scope_keys: tuple[str, ...],
    canonical_scope: str | None,
) -> list[dict[str, Any]]:
    if log_path is None or sample_limit <= 0 or scan_lines <= 0 or not log_path.exists():
        return []
    recent_lines: deque[str] = deque(maxlen=scan_lines)
    with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                recent_lines.append(line)

    samples: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for raw_line in reversed(recent_lines):
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        generated_at = str(payload.get("generated_at") or "")
        for item in reversed(list(payload.get("items") or [])):
            if str(item.get("status") or "") != "skipped_pre_ingest_template_rejected":
                continue
            if not _sample_matches_scope(
                item=item,
                scope_keys=scope_keys,
                canonical_scope=canonical_scope,
            ):
                continue
            item_id = str(item.get("item_id") or "")
            dedupe_key = (item_id, generated_at)
            if not item_id or dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            samples.append(
                {
                    "generatedAt": generated_at or None,
                    "itemId": item.get("item_id"),
                    "title": item.get("title"),
                    "price": item.get("price"),
                    "businessDomain": item.get("business_domain"),
                    "mappedBusinessDomain": item.get("mapped_business_domain"),
                    "reason": item.get("reason"),
                    "preIngestTemplateId": item.get("pre_ingest_template_id"),
                    "preIngestCategoryId": item.get("pre_ingest_category_id"),
                }
            )
            if len(samples) >= sample_limit:
                return samples
    return samples


def _rejection_matches_scope(
    *,
    business_domain: str | None,
    scope_keys: tuple[str, ...],
    canonical_scope: str | None,
) -> bool:
    if not canonical_scope:
        return True
    normalized = str(business_domain or "").strip()
    if normalized in scope_keys:
        return True
    return resolve_category_code(normalized) == canonical_scope


def _sample_matches_scope(
    *,
    item: dict[str, Any],
    scope_keys: tuple[str, ...],
    canonical_scope: str | None,
) -> bool:
    if not canonical_scope:
        return True
    for candidate in (
        item.get("mapped_business_domain"),
        item.get("business_domain"),
    ):
        normalized = str(candidate or "").strip()
        if not normalized:
            continue
        if normalized in scope_keys or resolve_category_code(normalized) == canonical_scope:
            return True
    return False


def _sample_reason_counts(samples: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(sample.get("reason") or "unknown") for sample in samples)
    return {key: int(counts[key]) for key in sorted(counts.keys())}


def _default_home_feed_log_path() -> Path | None:
    from .runtime_controls import HOME_FEED_LOG

    return HOME_FEED_LOG
