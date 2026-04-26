from __future__ import annotations

from typing import Any

from ...pricing import aggregate_pricing_view
from ...presentation.web import PRICING_VIEW_LABELS, format_currency, format_screen_label, format_storage_label, pricing_view_label
from .dashboard_filters import filter_pricing_records
from .pricing_thresholds import evaluate_pricing_row_availability


def pricing_dimensions(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    if row.get("display_type"):
        values.append(str(row["display_type"]))
    if row.get("case_size_mm") is not None:
        values.append(f'{row["case_size_mm"]}mm')
    if row.get("is_solar") is True:
        values.append("太阳能")
    elif row.get("is_solar") is False:
        values.append("非太阳能")
    if row.get("screen_size_in") is not None:
        values.append(format_screen_label(row["screen_size_in"]))
    if row.get("chip_family"):
        values.append(str(row["chip_family"]))
    if row.get("cpu_cores") is not None:
        values.append(f'{row["cpu_cores"]}核 CPU')
    if row.get("gpu_cores") is not None:
        values.append(f'{row["gpu_cores"]}核 GPU')
    if row.get("memory_gb") is not None:
        values.append(f'{row["memory_gb"]}G')
    if row.get("storage_gb") is not None:
        values.append(format_storage_label(int(row["storage_gb"])))
    return values


def compact_row_dimensions(row: dict[str, Any], limit: int = 3) -> list[str]:
    return pricing_dimensions(row)[:limit]


def format_profit_range_label(row: dict[str, Any]) -> str:
    floor = row.get("estimated_profit_floor")
    ceiling = row.get("estimated_profit_ceiling")
    if floor is None and ceiling is None:
        return "-"
    if floor == ceiling:
        return format_currency(floor)
    return f"{format_currency(floor)} ~ {format_currency(ceiling)}"


def format_focus_caption(row: dict[str, Any]) -> str:
    parts = [
        f"{int(row.get('seller_sample_count') or 0)} 个卖家样本",
        f"可靠度 {int(row.get('reliability_score') or 0)}",
    ]
    if row.get("quality_tier"):
        parts.append(f"质量 {row['quality_tier']}")
    if row.get("schema_id") is not None:
        parts.append(f"Schema v{row['schema_id']}")
    if row.get("effective_sample_count") is not None:
        parts.append(f"有效样本 {round(float(row['effective_sample_count'] or 0), 1)}")
    if row.get("recency_weighted_sample_count") is not None:
        parts.append(f"近样本 {round(float(row['recency_weighted_sample_count'] or 0), 1)}")
    if row.get("normal_margin_pct") is not None:
        parts.append(f"正常毛利 {float(row['normal_margin_pct']):.1f}%")
    if row.get("view"):
        parts.append(pricing_view_label(row["view"]))
    return " | ".join(parts)


def focus_state_payload(row: dict[str, Any]) -> dict[str, str]:
    if row.get("is_actionable"):
        return {"label": "机会成立", "class_name": "actionable"}
    if row.get("sample_confident"):
        return {"label": "仅看样本", "class_name": "watch"}
    return {"label": "观察中", "class_name": "watch"}


def opportunity_label(row: dict[str, Any]) -> str:
    mapping = {
        "good": "机会成立",
        "thin": "薄利观察",
        "low": "价差偏薄",
        "none": "暂无价差",
        "watch": "仅看样本",
    }
    tier = row.get("opportunity_tier") or "watch"
    return mapping.get(tier, "观察中")


def to_focus_card(*, title: str, tone: str, row: dict[str, Any] | None, empty_text: str) -> dict[str, Any]:
    if row is None:
        return {
            "title": title,
            "tone": tone,
            "empty": True,
            "empty_text": empty_text,
        }
    return {
        "title": title,
        "tone": tone,
        "empty": False,
        "label": row["label"],
        "product_label": row.get("product_label"),
        "spec_label": row.get("spec_label"),
        "safe_buy_price": row.get("safe_buy_price"),
        "normal_buy_price": row.get("normal_buy_price"),
        "market_mid_price": row.get("market_mid_price"),
        "estimated_profit_floor": row.get("estimated_profit_floor"),
        "estimated_profit_ceiling": row.get("estimated_profit_ceiling"),
        "estimated_profit_label": format_profit_range_label(row),
        "buy_floor_price": row.get("buy_floor_price"),
        "target_buy_ceiling": row.get("target_buy_ceiling"),
        "fair_price": row.get("fair_price"),
        "high_price_floor": row.get("high_price_floor"),
        "reliability_score": row.get("reliability_score"),
        "seller_sample_count": row.get("seller_sample_count"),
        "schema_id": row.get("schema_id"),
        "effective_sample_count": row.get("effective_sample_count"),
        "recency_weighted_sample_count": row.get("recency_weighted_sample_count"),
        "quality_tier": row.get("quality_tier"),
        "confidence_score": row.get("confidence_score"),
        "confidence_reasons": list(row.get("confidence_reasons") or []),
        "mad": row.get("mad"),
        "p15_price": row.get("p15_price"),
        "p35_price": row.get("p35_price"),
        "p50_price": row.get("p50_price"),
        "caption": format_focus_caption(row),
        "dimensions": compact_row_dimensions(row),
        "latest_seen_at": row.get("latest_seen_at"),
        "normal_margin_pct": row.get("normal_margin_pct"),
        "opportunity_label": opportunity_label(row),
        "required_profit_amount": row.get("required_profit_amount"),
        "is_actionable": row.get("is_actionable"),
        "focus_state_label": focus_state_payload(row)["label"],
        "focus_state_class": focus_state_payload(row)["class_name"],
        "pricingAvailability": dict(row.get("pricingAvailability") or {}),
        "pricingAvailabilitySummary": dict(row.get("pricingAvailabilitySummary") or {}),
    }


def build_market_focus(
    *,
    pricing_records: list[dict[str, Any]],
    filters: dict[str, Any],
    min_sample_points: int,
    pricing_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    filtered_records = filter_pricing_records(pricing_records, filters)
    spec_rows = aggregate_pricing_view(records=filtered_records, view="spec", min_sample_points=min_sample_points)
    product_rows = aggregate_pricing_view(records=filtered_records, view="product", min_sample_points=min_sample_points)

    actionable_spec = [row for row in spec_rows if row.get("is_actionable")]
    best_buy = None
    if actionable_spec:
        best_buy = max(
            actionable_spec,
            key=lambda row: (
                float(row.get("opportunity_score") or 0),
                float(row.get("reliability_score") or 0),
            ),
        )
    if best_buy is None:
        actionable_product = [row for row in product_rows if row.get("is_actionable")]
        if actionable_product:
            best_buy = max(
                actionable_product,
                key=lambda row: (
                    float(row.get("opportunity_score") or 0),
                    float(row.get("reliability_score") or 0),
                ),
            )

    most_liquid = None
    if product_rows:
        most_liquid = max(
            product_rows,
            key=lambda row: (
                int(row.get("seller_sample_count") or 0),
                int(row.get("unique_seller_count") or 0),
                float(row.get("reliability_score") or 0),
            ),
        )

    premium_focus = None
    if actionable_spec:
        premium_focus = max(
            actionable_spec,
            key=lambda row: (
                float(row.get("fair_price") or 0),
                float(row.get("opportunity_score") or 0),
                float(row.get("reliability_score") or 0),
            ),
        )
    else:
        premium_candidates = [row for row in product_rows if row.get("sample_confident")]
        if premium_candidates:
            premium_focus = max(
                premium_candidates,
                key=lambda row: (
                    float(row.get("fair_price") or 0),
                    float(row.get("reliability_score") or 0),
                    int(row.get("seller_sample_count") or 0),
                ),
            )

    if premium_focus is not None and not premium_focus.get("sample_confident"):
        premium_focus = None

    if premium_focus is None and product_rows:
        watch_candidates = [
            row
            for row in product_rows
            if int(row.get("seller_sample_count") or 0) >= max(min_sample_points, 3)
        ]
        if watch_candidates:
            premium_focus = max(
                watch_candidates,
                key=lambda row: (
                    float(row.get("fair_price") or 0),
                    float(row.get("reliability_score") or 0),
                    int(row.get("seller_sample_count") or 0),
                ),
            )

    template_complete = bool(((pricing_contract or {}).get("templateCompleteness") or {}).get("isComplete"))
    selected_rows = [best_buy, most_liquid, premium_focus]
    annotated_rows = [
        _annotate_focus_row_availability(row, template_complete=template_complete)
        for row in selected_rows
    ]
    return [
        to_focus_card(
            title="当前最有机会",
            tone="buy",
            row=annotated_rows[0],
            empty_text="当前没有利润和利润率都达标的分组。样本可以先看，但不建议因为薄利就下判断。",
        ),
        to_focus_card(
            title="流通最快",
            tone="liquid",
            row=annotated_rows[1],
            empty_text="暂时没有稳定的高流通分组。",
        ),
        to_focus_card(
            title="高客单重点",
            tone="premium",
            row=annotated_rows[2],
            empty_text="暂时没有明显突出的高客单分组。",
        ),
    ]


def _annotate_focus_row_availability(
    row: dict[str, Any] | None,
    *,
    template_complete: bool,
) -> dict[str, Any] | None:
    if row is None:
        return None
    availability = evaluate_pricing_row_availability(row, template_complete=template_complete)
    return {
        **row,
        "pricingAvailability": availability,
        "pricingAvailabilitySummary": dict(availability.get("pricingSummary") or {}),
    }


def reliability_class(row: dict[str, Any]) -> str:
    if row.get("is_actionable"):
        return "high"
    tier = row.get("reliability_tier") or "watch"
    return "watch" if tier == "watch" else tier


def build_pricing_band_panel(
    *,
    pricing_records: list[dict[str, Any]],
    filters: dict[str, Any],
    pricing_view: str,
    actionable_only: bool,
    min_sample_points: int,
    limit: int,
    freshness_days: int,
) -> dict[str, Any]:
    normalized_view = pricing_view if pricing_view in PRICING_VIEW_LABELS else "product"
    filtered_records = filter_pricing_records(pricing_records, filters)
    views = {
        "brand": aggregate_pricing_view(records=filtered_records, view="brand", min_sample_points=min_sample_points),
        "product": aggregate_pricing_view(records=filtered_records, view="product", min_sample_points=min_sample_points),
        "spec": aggregate_pricing_view(records=filtered_records, view="spec", min_sample_points=min_sample_points),
    }
    rows = views[normalized_view]
    total_count = len(rows)
    actionable_count = sum(1 for row in rows if row["is_actionable"])
    if actionable_only:
        rows = [row for row in rows if row["is_actionable"]]

    return {
        "view": normalized_view,
        "view_label": pricing_view_label(normalized_view),
        "actionable_only": actionable_only,
        "freshness_days": freshness_days,
        "min_sample_points": min_sample_points,
        "record_count": len(filtered_records),
        "total_count": total_count,
        "actionable_count": actionable_count,
        "rows": [
            {
                **row,
                "dimensions": pricing_dimensions(row),
                "reliability_class": reliability_class(row),
                "opportunity_label": opportunity_label(row),
            }
            for row in rows[:limit]
        ],
    }
