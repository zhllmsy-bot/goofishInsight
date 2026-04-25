from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from ...compat import UTC
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ...category_compat import compatible_scope_keys, resolve_category_code
from ...db import session_scope
from ...models import Item, ItemSnapshot
from ...normalizers import normalize_market_price
from ...settings import get_settings

MAX_EXAMPLES = 25


def _scope_keys_for_filter(business_domain: str | None) -> tuple[str, ...]:
    normalized = str(business_domain or "").strip()
    if not normalized:
        return ()
    return compatible_scope_keys(normalized)


def _canonical_scope(value: str | None) -> str:
    resolved = resolve_category_code(value)
    return resolved or str(value or "").strip()


def backfill_normalized_prices(
    *,
    dry_run: bool = False,
    business_domain: str | None = None,
    item_limit: int | None = None,
    snapshot_limit: int | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    summary: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "dry_run": dry_run,
        "business_domain": business_domain,
        "items_scanned": 0,
        "items_changed": 0,
        "snapshots_scanned": 0,
        "snapshots_changed": 0,
        "item_examples": [],
        "snapshot_examples": [],
        "by_domain": {},
        "report_path": None,
    }
    per_domain: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "items_scanned": 0,
            "items_changed": 0,
            "snapshots_scanned": 0,
            "snapshots_changed": 0,
        }
    )

    with session_scope() as session:
        scope_keys = _scope_keys_for_filter(business_domain)
        item_stmt = (
            select(Item)
            .where(
                Item.current_price.is_not(None),
                Item.current_price > 0,
            )
            .order_by(Item.id)
        )
        if scope_keys:
            item_stmt = item_stmt.where(Item.business_domain.in_(scope_keys))
        if item_limit is not None:
            item_stmt = item_stmt.limit(item_limit)

        items = session.execute(item_stmt).scalars().all()
        for item in items:
            scope = _canonical_scope(item.business_domain)
            domain_summary = per_domain[scope]
            domain_summary["items_scanned"] += 1
            summary["items_scanned"] += 1

            normalized_price = normalize_market_price(
                item.current_price,
                business_domain=item.business_domain,
                model_family=item.normalized_model_family,
            )
            if normalized_price is None or normalized_price == item.current_price:
                continue

            if len(summary["item_examples"]) < MAX_EXAMPLES:
                summary["item_examples"].append(
                    {
                        "item_id": item.item_id,
                        "business_domain": scope,
                        "model_family": item.normalized_model_family,
                        "title": item.title[:160],
                        "old_price": _decimal_to_float(item.current_price),
                        "new_price": _decimal_to_float(normalized_price),
                    }
                )

            summary["items_changed"] += 1
            domain_summary["items_changed"] += 1
            if not dry_run:
                item.current_price = normalized_price

        snapshot_stmt = (
            select(ItemSnapshot, Item.business_domain, Item.normalized_model_family, Item.item_id)
            .join(Item, ItemSnapshot.item_id_ref == Item.id)
            .where(
                ItemSnapshot.price.is_not(None),
                ItemSnapshot.price > 0,
            )
            .order_by(ItemSnapshot.id)
        )
        if scope_keys:
            snapshot_stmt = snapshot_stmt.where(Item.business_domain.in_(scope_keys))
        if snapshot_limit is not None:
            snapshot_stmt = snapshot_stmt.limit(snapshot_limit)

        snapshot_rows = session.execute(snapshot_stmt).all()
        for snapshot, snapshot_domain, model_family, item_id in snapshot_rows:
            scope = _canonical_scope(snapshot_domain)
            domain_summary = per_domain[scope]
            domain_summary["snapshots_scanned"] += 1
            summary["snapshots_scanned"] += 1

            normalized_price = normalize_market_price(
                snapshot.price,
                business_domain=snapshot_domain,
                model_family=model_family,
            )
            if normalized_price is None or normalized_price == snapshot.price:
                continue

            if len(summary["snapshot_examples"]) < MAX_EXAMPLES:
                summary["snapshot_examples"].append(
                    {
                        "item_id": item_id,
                        "snapshot_id": snapshot.id,
                        "business_domain": scope,
                        "model_family": model_family,
                        "old_price": _decimal_to_float(snapshot.price),
                        "new_price": _decimal_to_float(normalized_price),
                        "snapshot_at": snapshot.snapshot_at.isoformat() if snapshot.snapshot_at else None,
                    }
                )

            summary["snapshots_changed"] += 1
            domain_summary["snapshots_changed"] += 1
            if not dry_run:
                snapshot.price = normalized_price

    summary["by_domain"] = dict(sorted(per_domain.items()))
    summary["finished_at"] = datetime.now(UTC).isoformat()
    report_path = write_price_backfill_report(summary)
    summary["report_path"] = str(report_path)
    return summary


def write_price_backfill_report(summary: dict[str, Any]) -> Path:
    settings = get_settings()
    report_dir = settings.base_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report_path = report_dir / f"price-backfill-{timestamp}.json"
    report_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report_path


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
