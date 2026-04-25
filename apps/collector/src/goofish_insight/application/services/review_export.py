from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from ...compat import UTC
from math import ceil
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select

from ...category_compat import compatible_scope_keys
from ...db import session_scope
from ...domain.review.contracts import REVIEW_STATUS_IN_PROGRESS
from ...models import Item, ItemSpecEnrichment
from .review_queries import serialize_review_row


def take_trailing_share(items: list[Any], *, tail_fraction: float) -> tuple[list[Any], int]:
    if tail_fraction <= 0 or tail_fraction > 1:
        raise ValueError("tail_fraction must be within (0, 1].")
    total = len(items)
    if total == 0:
        return [], 0
    trailing_count = ceil(total * tail_fraction)
    skipped_count = max(total - trailing_count, 0)
    return items[skipped_count:], skipped_count


def split_evenly(items: list[Any], *, group_count: int) -> list[list[Any]]:
    if group_count <= 0:
        raise ValueError("group_count must be greater than 0.")
    base_size = len(items) // group_count
    remainder = len(items) % group_count
    groups: list[list[Any]] = []
    offset = 0
    for group_index in range(group_count):
        current_size = base_size + (1 if group_index < remainder else 0)
        groups.append(items[offset : offset + current_size])
        offset += current_size
    return groups


def load_unreviewed_items(
    *,
    business_domain: str | None,
    include_in_progress: bool,
) -> list[dict[str, Any]]:
    scope_keys = compatible_scope_keys(business_domain) if str(business_domain or "").strip() else ()
    stmt = (
        select(Item, ItemSpecEnrichment)
        .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
        .where(
            Item.is_active.is_(True),
            Item.llm_reviewed.is_(False),
        )
        .order_by(desc(Item.last_seen_at), desc(Item.id))
    )
    if scope_keys:
        stmt = stmt.where(Item.business_domain.in_(scope_keys))
    if not include_in_progress:
        stmt = stmt.where(Item.llm_review_status != REVIEW_STATUS_IN_PROGRESS)

    with session_scope() as session:
        rows = session.execute(stmt).all()

    return [serialize_review_row(item=item, spec=spec) for item, spec in rows]


def export_review_source_groups(
    *,
    output_root: Path,
    business_domain: str | None,
    group_count: int,
    tail_fraction: float,
    include_in_progress: bool,
) -> dict[str, Any]:
    pending_items = load_unreviewed_items(
        business_domain=business_domain,
        include_in_progress=include_in_progress,
    )
    selected_items, skipped_count = take_trailing_share(
        pending_items,
        tail_fraction=tail_fraction,
    )
    groups = split_evenly(selected_items, group_count=group_count)

    source_dir = output_root / "source"
    review_dir = output_root / "review"
    source_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)

    for stale_file in source_dir.glob("group-*.json"):
        stale_file.unlink()
    manifest_path = source_dir / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()

    generated_at = datetime.now(UTC).isoformat()
    manifest_groups: list[dict[str, Any]] = []

    for index, group_items in enumerate(groups, start=1):
        file_name = f"group-{index:02d}.json"
        output_path = source_dir / file_name
        output_path.write_text(
            json.dumps(group_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        domain_counts = Counter(item["business_domain"] for item in group_items)
        status_counts = Counter((item.get("llm_review") or {}).get("status") for item in group_items)
        manifest_groups.append(
            {
                "group_index": index,
                "file_name": file_name,
                "item_count": len(group_items),
                "business_domains": dict(sorted(domain_counts.items())),
                "llm_statuses": dict(sorted((key or "unknown", value) for key, value in status_counts.items())),
                "first_item_id": group_items[0]["item_id"] if group_items else None,
                "last_item_id": group_items[-1]["item_id"] if group_items else None,
            }
        )

    overall_domain_counts = Counter(item["business_domain"] for item in selected_items)
    overall_status_counts = Counter((item.get("llm_review") or {}).get("status") for item in selected_items)
    summary = {
        "generated_at": generated_at,
        "business_domain": business_domain,
        "group_count": group_count,
        "tail_fraction": tail_fraction,
        "include_in_progress": include_in_progress,
        "selection_rule": "Ordered by last_seen_at DESC, id DESC. Skipped the front 20% of unreviewed active items and exported the trailing 80%.",
        "total_unreviewed_active_count": len(pending_items),
        "skipped_front_count": skipped_count,
        "exported_count": len(selected_items),
        "business_domains": dict(sorted(overall_domain_counts.items())),
        "llm_statuses": dict(sorted((key or "unknown", value) for key, value in overall_status_counts.items())),
        "source_pattern": "database/source/group-XX.json",
        "review_pattern": "database/review/group-XX.review.json",
        "groups": manifest_groups,
    }
    manifest_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
