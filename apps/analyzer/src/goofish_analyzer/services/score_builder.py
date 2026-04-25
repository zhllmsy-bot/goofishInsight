from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select

from goofish_analyzer.adapters import session_scope, Item, ItemSpecEnrichment, ModelScore


@dataclass(slots=True)
class ModelScoreAggregate:
    business_domain: str
    category_id: str | None
    model_catalog_id: str | None
    normalized_model: str
    normalized_model_family: str | None
    listing_count: int
    unique_seller_count: int
    priced_listing_count: int
    median_price: Decimal | None
    p25_price: Decimal | None
    p75_price: Decimal | None
    liquidity_score: Decimal | None
    profit_potential_score: Decimal | None
    selection_score: Decimal | None


def _score_window(score_date: date) -> tuple[datetime, datetime]:
    start_at = datetime.combine(score_date, time.min, tzinfo=UTC)
    return start_at, start_at + timedelta(days=1)


def _normalize_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _category_id_from_row(row: Any) -> str | None:
    return _normalize_optional_text(
        getattr(row, "spec_category_id", None)
        or getattr(row, "resolved_category_id", None)
        or getattr(row, "target_category_id", None)
    )


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
    return (lower_value + (upper_value - lower_value) * fraction).quantize(Decimal("0.01"))


def _quantize_score(value: Decimal | float | int | None) -> Decimal | None:
    if value is None:
        return None
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    return max(Decimal("0"), min(Decimal("100"), decimal_value)).quantize(Decimal("0.01"))


def _calculate_liquidity_score(listing_count: int, unique_seller_count: int) -> Decimal:
    # MVP scoring favors repeat supply while keeping the formula easy to inspect.
    return _quantize_score(Decimal(listing_count) * Decimal("4") + Decimal(unique_seller_count) * Decimal("8")) or Decimal("0.00")


def _calculate_profit_potential_score(
    *,
    median_price: Decimal | None,
    p25_price: Decimal | None,
    p75_price: Decimal | None,
) -> Decimal | None:
    if median_price is None or p25_price is None or p75_price is None or median_price <= 0:
        return None
    spread_ratio = (p75_price - p25_price) / median_price
    return _quantize_score(spread_ratio * Decimal("160"))


def _calculate_selection_score(
    *,
    liquidity_score: Decimal | None,
    profit_potential_score: Decimal | None,
) -> Decimal | None:
    if liquidity_score is None and profit_potential_score is None:
        return None
    if profit_potential_score is None:
        return liquidity_score
    if liquidity_score is None:
        return profit_potential_score
    return _quantize_score(liquidity_score * Decimal("0.65") + profit_potential_score * Decimal("0.35"))


def _model_identity_from_row(row: Any) -> tuple[str, str | None]:
    model = _normalize_optional_text(
        getattr(row, "spec_model_name", None)
        or getattr(row, "item_normalized_model", None)
        or getattr(row, "item_normalized_model_family", None)
        or getattr(row, "source_keyword", None)
    )
    family = _normalize_optional_text(
        getattr(row, "spec_model_family", None)
        or getattr(row, "spec_product_line", None)
        or getattr(row, "item_normalized_model_family", None)
    )
    return model or "Unclassified", family


def _build_model_score_aggregates(rows: list[Any]) -> list[ModelScoreAggregate]:
    grouped: dict[tuple[str, str | None, str | None, str], dict[str, Any]] = defaultdict(
        lambda: {
            "normalized_model": None,
            "family": None,
            "listing_count": 0,
            "seller_ids": set(),
            "prices": [],
        }
    )

    for row in rows:
        business_domain = _normalize_optional_text(getattr(row, "business_domain", None)) or "unknown"
        category_id = _category_id_from_row(row)
        model_catalog_id = _normalize_optional_text(getattr(row, "model_catalog_id", None))
        normalized_model, normalized_model_family = _model_identity_from_row(row)
        model_bucket_key = model_catalog_id or normalized_model
        bucket = grouped[(business_domain, category_id, model_catalog_id, model_bucket_key)]
        bucket["listing_count"] += 1
        bucket["normalized_model"] = bucket["normalized_model"] or normalized_model
        bucket["family"] = bucket["family"] or normalized_model_family
        seller_profile_id = getattr(row, "seller_profile_id", None)
        if seller_profile_id is not None:
            bucket["seller_ids"].add(int(seller_profile_id))
        price = _as_decimal(getattr(row, "current_price", None))
        if price is not None:
            bucket["prices"].append(price)

    aggregates: list[ModelScoreAggregate] = []
    for (business_domain, category_id, model_catalog_id, _model_bucket_key), bucket in sorted(
        grouped.items(),
        key=lambda item: tuple(str(value or "") for value in item[0]),
    ):
        prices = list(bucket["prices"])
        listing_count = int(bucket["listing_count"])
        unique_seller_count = len(bucket["seller_ids"])
        median_price = _percentile_decimal(prices, 0.5)
        p25_price = _percentile_decimal(prices, 0.25)
        p75_price = _percentile_decimal(prices, 0.75)
        liquidity_score = _calculate_liquidity_score(listing_count, unique_seller_count)
        profit_potential_score = _calculate_profit_potential_score(
            median_price=median_price,
            p25_price=p25_price,
            p75_price=p75_price,
        )
        selection_score = _calculate_selection_score(
            liquidity_score=liquidity_score,
            profit_potential_score=profit_potential_score,
        )
        aggregates.append(
            ModelScoreAggregate(
                business_domain=business_domain,
                category_id=category_id,
                model_catalog_id=model_catalog_id,
                normalized_model=bucket["normalized_model"] or "Unclassified",
                normalized_model_family=bucket["family"],
                listing_count=listing_count,
                unique_seller_count=unique_seller_count,
                priced_listing_count=len(prices),
                median_price=median_price,
                p25_price=p25_price,
                p75_price=p75_price,
                liquidity_score=liquidity_score,
                profit_potential_score=profit_potential_score,
                selection_score=selection_score,
            )
        )
    return aggregates


def build_model_scores(
    *,
    score_date: date,
    business_domain: str | None = None,
    category_id: str | None = None,
    source_mode: str = "legacy_items",
    replace_existing: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    start_at, end_at = _score_window(score_date)

    with session_scope() as session:
        query = (
            select(
                Item.business_domain.label("business_domain"),
                Item.resolved_category_id.label("resolved_category_id"),
                Item.target_category_id.label("target_category_id"),
                Item.seller_profile_id.label("seller_profile_id"),
                Item.current_price.label("current_price"),
                Item.normalized_model.label("item_normalized_model"),
                Item.normalized_model_family.label("item_normalized_model_family"),
                Item.source_keyword.label("source_keyword"),
                ItemSpecEnrichment.category_id.label("spec_category_id"),
                ItemSpecEnrichment.model_catalog_id.label("model_catalog_id"),
                ItemSpecEnrichment.product_line.label("spec_product_line"),
                ItemSpecEnrichment.model_family.label("spec_model_family"),
                ItemSpecEnrichment.model_name.label("spec_model_name"),
            )
            .select_from(Item)
            .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
            .where(Item.last_seen_at >= start_at)
            .where(Item.last_seen_at < end_at)
            .where(Item.is_active.is_(True))
        )
        if business_domain:
            query = query.where(Item.business_domain == business_domain)
        if category_id:
            query = query.where(
                (Item.resolved_category_id == category_id)
                | (Item.target_category_id == category_id)
                | (ItemSpecEnrichment.category_id == category_id)
            )

        rows = session.execute(query).all()
        aggregates = _build_model_score_aggregates(rows)

        deleted_count = 0
        if replace_existing and not dry_run:
            delete_stmt = delete(ModelScore).where(ModelScore.score_date == score_date)
            if business_domain:
                delete_stmt = delete_stmt.where(ModelScore.business_domain == business_domain)
            if category_id:
                delete_stmt = delete_stmt.where(ModelScore.category_id == category_id)
            deleted_count = int(session.execute(delete_stmt).rowcount or 0)

        if not dry_run:
            generated_at = datetime.now(UTC).isoformat()
            for aggregate in aggregates:
                session.add(
                    ModelScore(
                        business_domain=aggregate.business_domain,
                        category_id=aggregate.category_id,
                        model_catalog_id=aggregate.model_catalog_id,
                        normalized_model=aggregate.normalized_model,
                        normalized_model_family=aggregate.normalized_model_family,
                        score_date=score_date,
                        liquidity_score=aggregate.liquidity_score,
                        profit_potential_score=aggregate.profit_potential_score,
                        selection_score=aggregate.selection_score,
                        score_reason={
                            "listing_count": aggregate.listing_count,
                            "unique_seller_count": aggregate.unique_seller_count,
                            "priced_listing_count": aggregate.priced_listing_count,
                            "median_price": str(aggregate.median_price) if aggregate.median_price is not None else None,
                            "p25_price": str(aggregate.p25_price) if aggregate.p25_price is not None else None,
                            "p75_price": str(aggregate.p75_price) if aggregate.p75_price is not None else None,
                            "formula_version": "mvp-20260414",
                            "source_path": "items+item_spec_enrichments",
                            "generated_at": generated_at,
                        },
                    )
                )

    return {
        "score_date": score_date.isoformat(),
        "model_count": len(aggregates),
        "listing_count": sum(aggregate.listing_count for aggregate in aggregates),
        "priced_listing_count": sum(aggregate.priced_listing_count for aggregate in aggregates),
        "deleted_count": deleted_count,
        "business_domain": business_domain,
        "category_id": category_id,
        "dry_run": dry_run,
        "source_path": "items+item_spec_enrichments",
        "source_mode": source_mode,
    }
