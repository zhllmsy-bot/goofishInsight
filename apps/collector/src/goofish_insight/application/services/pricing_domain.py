from __future__ import annotations

from typing import Any

from ...compat import UTC

MIN_ACTIONABLE_PROFIT_MARGIN_PCT = 10.0
MIN_ACTIONABLE_PROFIT_AMOUNT = 100.0
MIN_ACTIONABLE_PROFIT_FLOOR_RATIO = 0.04

GARMIN_ANALYSIS_PRODUCT_LINES = {
    "Fenix",
    "Epix",
    "Instinct",
    "Forerunner",
    "Venu",
    "MARQ",
    "Approach",
    "Enduro",
    "Tactix",
    "Descent",
}

APPLE_ANALYSIS_PRODUCT_LINES = {
    "MacBook Air",
    "MacBook Pro",
    "Mac mini",
    "Mac Studio",
    "iMac",
}


def minimum_actionable_profit_amount(fair_price: float | None) -> float:
    if fair_price is None or fair_price <= 0:
        return MIN_ACTIONABLE_PROFIT_AMOUNT
    return max(MIN_ACTIONABLE_PROFIT_AMOUNT, fair_price * MIN_ACTIONABLE_PROFIT_FLOOR_RATIO)


def compute_profit_margin_pct(*, buy_price: float | None, fair_price: float | None) -> float | None:
    if buy_price is None or fair_price is None or buy_price <= 0:
        return None
    return max(((fair_price - buy_price) / buy_price) * 100, 0)


def compute_opportunity_score(
    *,
    estimated_profit_floor: float | None,
    normal_margin_pct: float | None,
    required_profit_amount: float,
) -> float:
    amount_score = min((estimated_profit_floor or 0) / max(required_profit_amount, 1), 1.0)
    margin_score = min((normal_margin_pct or 0) / MIN_ACTIONABLE_PROFIT_MARGIN_PCT, 1.0)
    return 100 * ((0.58 * amount_score) + (0.42 * margin_score))


def classify_opportunity_tier(
    *,
    sample_confident: bool,
    meets_profit_gate: bool,
    estimated_profit_floor: float | None,
    estimated_profit_ceiling: float | None,
    normal_margin_pct: float | None,
    required_profit_amount: float,
) -> str:
    if not sample_confident:
        return "watch"
    if meets_profit_gate:
        return "good"
    if (
        estimated_profit_ceiling is not None
        and estimated_profit_ceiling >= required_profit_amount * 0.5
        and (normal_margin_pct or 0) >= MIN_ACTIONABLE_PROFIT_MARGIN_PCT * 0.6
    ):
        return "thin"
    if (estimated_profit_floor or 0) > 0 or (estimated_profit_ceiling or 0) > 0:
        return "low"
    return "none"


def spec_dimension_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_type": record.get("display_type"),
        "case_size_mm": record.get("case_size_mm"),
        "is_solar": record.get("is_solar"),
        "screen_size_in": record.get("screen_size_in"),
        "chip_family": record.get("chip_family"),
        "cpu_cores": record.get("cpu_cores"),
        "gpu_cores": record.get("gpu_cores"),
        "memory_gb": record.get("memory_gb"),
        "storage_gb": record.get("storage_gb"),
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    bounded = min(max(fraction, 0.0), 1.0)
    position = (len(values) - 1) * bounded
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    weight = position - lower_index
    lower_value = values[lower_index]
    upper_value = values[upper_index]
    return lower_value + ((upper_value - lower_value) * weight)


def round_money(value: float | None, *, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def reliability_tier(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 65:
        return "medium"
    if score >= 50:
        return "watch"
    return "weak"


def sort_last_seen(record: dict[str, Any]) -> float:
    last_seen_at = record.get("last_seen_at")
    if last_seen_at is None:
        return 0.0
    return last_seen_at.astimezone(UTC).timestamp()
