from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select

from goofish_analyzer.adapters import session_scope, DailyMetric, Item


@dataclass(slots=True)
class DailyMetricAggregate:
    business_domain: str
    category_id: str | None
    listing_count: int
    unique_seller_count: int
    priced_listing_count: int
    median_price: Decimal | None
    p25_price: Decimal | None
    p75_price: Decimal | None


def _metric_window(metric_date: date) -> tuple[datetime, datetime]:
    start_at = datetime.combine(metric_date, time.min, tzinfo=UTC)
    return start_at, start_at + timedelta(days=1)


def _category_id_from_row(row: Any) -> str | None:
    resolved_category_id = getattr(row, "resolved_category_id", None)
    target_category_id = getattr(row, "target_category_id", None)
    return str(resolved_category_id or target_category_id or "").strip() or None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _percentile_decimal(values: list[Decimal], percentile: float) -> Decimal | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0].quantize(Decimal("0.01"))
    ordered = sorted(values)
    rank = Decimal(str(percentile)) * Decimal(str(len(ordered) - 1))
    lower_index = int(rank.to_integral_value(rounding="ROUND_FLOOR"))
    upper_index = int(rank.to_integral_value(rounding="ROUND_CEILING"))
    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    if lower_index == upper_index:
        return lower_value.quantize(Decimal("0.01"))
    fraction = rank - Decimal(lower_index)
    interpolated = lower_value + (upper_value - lower_value) * fraction
    return interpolated.quantize(Decimal("0.01"))


def _build_daily_metric_aggregates(rows: list[Any]) -> list[DailyMetricAggregate]:
    grouped: dict[tuple[str, str | None], dict[str, Any]] = defaultdict(
        lambda: {
            "listing_count": 0,
            "seller_ids": set(),
            "prices": [],
        }
    )

    for row in rows:
        business_domain = str(getattr(row, "business_domain", "") or "").strip() or "unknown"
        category_id = _category_id_from_row(row)
        bucket = grouped[(business_domain, category_id)]
        bucket["listing_count"] += 1
        seller_profile_id = getattr(row, "seller_profile_id", None)
        if seller_profile_id is not None:
            bucket["seller_ids"].add(int(seller_profile_id))
        price = _as_decimal(getattr(row, "current_price", None))
        if price is not None:
            bucket["prices"].append(price)

    aggregates: list[DailyMetricAggregate] = []
    for (business_domain, category_id), bucket in sorted(
        grouped.items(),
        key=lambda item: (str(item[0][0] or ""), str(item[0][1] or "")),
    ):
        prices = list(bucket["prices"])
        aggregates.append(
            DailyMetricAggregate(
                business_domain=business_domain,
                category_id=category_id,
                listing_count=int(bucket["listing_count"]),
                unique_seller_count=len(bucket["seller_ids"]),
                priced_listing_count=len(prices),
                median_price=_percentile_decimal(prices, 0.5),
                p25_price=_percentile_decimal(prices, 0.25),
                p75_price=_percentile_decimal(prices, 0.75),
            )
        )
    return aggregates


def build_daily_metrics(
    *,
    metric_date: date,
    business_domain: str | None = None,
    category_id: str | None = None,
    source_mode: str = "legacy_items",
    replace_existing: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    start_at, end_at = _metric_window(metric_date)

    with session_scope() as session:
        query = (
            select(
                Item.business_domain,
                Item.resolved_category_id,
                Item.target_category_id,
                Item.seller_profile_id,
                Item.current_price,
            )
            .where(Item.last_seen_at >= start_at)
            .where(Item.last_seen_at < end_at)
            .where(Item.is_active.is_(True))
        )
        if business_domain:
            query = query.where(Item.business_domain == business_domain)
        if category_id:
            query = query.where(
                (Item.resolved_category_id == category_id) | (Item.target_category_id == category_id)
            )

        rows = session.execute(query).all()
        aggregates = _build_daily_metric_aggregates(rows)

        deleted_count = 0
        if replace_existing and not dry_run:
            delete_stmt = delete(DailyMetric).where(DailyMetric.metric_date == metric_date)
            if business_domain:
                delete_stmt = delete_stmt.where(DailyMetric.business_domain == business_domain)
            if category_id:
                delete_stmt = delete_stmt.where(DailyMetric.category_id == category_id)
            deleted_count = int(session.execute(delete_stmt).rowcount or 0)

        if not dry_run:
            for aggregate in aggregates:
                session.add(
                    DailyMetric(
                        metric_date=metric_date,
                        business_domain=aggregate.business_domain,
                        category_id=aggregate.category_id,
                        model_catalog_id=None,
                        normalized_model=None,
                        listing_count=aggregate.listing_count,
                        unique_seller_count=aggregate.unique_seller_count,
                        median_price=aggregate.median_price,
                        p25_price=aggregate.p25_price,
                        p75_price=aggregate.p75_price,
                        metric_payload={
                            "priced_listing_count": aggregate.priced_listing_count,
                            "generated_at": datetime.now(UTC).isoformat(),
                            "metric_scope": "category_daily",
                        },
                    )
                )

    return {
        "metric_date": metric_date.isoformat(),
        "group_count": len(aggregates),
        "listing_count": sum(aggregate.listing_count for aggregate in aggregates),
        "priced_listing_count": sum(aggregate.priced_listing_count for aggregate in aggregates),
        "deleted_count": deleted_count,
        "business_domain": business_domain,
        "category_id": category_id,
        "dry_run": dry_run,
        "source_path": "items",
        "source_mode": source_mode,
    }
