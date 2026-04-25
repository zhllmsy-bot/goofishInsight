from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from goofish_analyzer.adapters import (
    resolve_category_code,
    UTC,
    BuyOpportunity,
    BuyPriceBaseline,
    Category,
    is_price_template_alert_strict_mode_enabled,
    is_price_template_contract_enabled,
    is_price_template_dashboard_enabled,
    is_price_template_opportunity_enabled,
    is_price_template_trend_enabled,
    session_scope,
)


class PricingMonitoringError(RuntimeError):
    pass


def summarize_template_availability_monitoring(
    *,
    category_code: str | None = None,
    window_days: int = 30,
) -> dict[str, Any]:
    with session_scope() as session:
        return summarize_template_availability_monitoring_with_session(
            session,
            category_code=category_code,
            window_days=window_days,
        )


def summarize_template_availability_monitoring_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    window_days: int = 30,
) -> dict[str, Any]:
    category = _resolve_optional_category(session, category_code=category_code)
    cutoff = datetime.now(UTC) - timedelta(days=max(int(window_days), 1))

    baseline_stmt = select(BuyPriceBaseline).where(BuyPriceBaseline.baseline_date >= cutoff.date())
    opportunity_stmt = select(BuyOpportunity).where(BuyOpportunity.last_detected_at >= cutoff)
    if category is not None:
        category_id = str(category.id)
        baseline_stmt = baseline_stmt.where(BuyPriceBaseline.category_id == category_id)
        opportunity_stmt = opportunity_stmt.where(BuyOpportunity.category_id == category_id)

    baselines = list(session.execute(baseline_stmt).scalars().all())
    opportunities = list(session.execute(opportunity_stmt).scalars().all())

    baseline_tier_counts: dict[str, int] = {}
    latest_baseline_date = None
    for row in baselines:
        if latest_baseline_date is None or row.baseline_date > latest_baseline_date:
            latest_baseline_date = row.baseline_date
        tier = _normalize_optional_string(
            dict(dict(row.payload or {}).get("pricingTemplate") or {})
            .get("availability", {})
            .get("availabilityTier")
        ) or "unknown"
        baseline_tier_counts[tier] = baseline_tier_counts.get(tier, 0) + 1

    opportunity_tier_counts: dict[str, int] = {}
    opportunity_status_counts: dict[str, int] = {}
    for row in opportunities:
        tier = _normalize_optional_string(dict(row.payload or {}).get("templateAvailabilityTier")) or "unknown"
        status = _normalize_optional_string(row.status) or "unknown"
        opportunity_tier_counts[tier] = opportunity_tier_counts.get(tier, 0) + 1
        opportunity_status_counts[status.upper()] = opportunity_status_counts.get(status.upper(), 0) + 1

    return {
        "categoryCode": category.code if category is not None else None,
        "windowDays": max(int(window_days), 1),
        "asOf": datetime.now(UTC).isoformat(),
        "featureFlags": _price_template_feature_flags(),
        "baseline": {
            "count": len(baselines),
            "latestBaselineDate": latest_baseline_date.isoformat() if latest_baseline_date is not None else None,
            "tierCounts": dict(sorted(baseline_tier_counts.items(), key=lambda item: (-item[1], item[0]))),
        },
        "opportunity": {
            "count": len(opportunities),
            "tierCounts": dict(sorted(opportunity_tier_counts.items(), key=lambda item: (-item[1], item[0]))),
            "statusCounts": dict(sorted(opportunity_status_counts.items(), key=lambda item: (-item[1], item[0]))),
        },
    }


def _price_template_feature_flags() -> dict[str, bool]:
    return {
        "priceTemplateContractEnabled": bool(is_price_template_contract_enabled()),
        "priceTemplateDashboardEnabled": bool(is_price_template_dashboard_enabled()),
        "priceTemplateOpportunityEnabled": bool(is_price_template_opportunity_enabled()),
        "priceTemplateTrendEnabled": bool(is_price_template_trend_enabled()),
        "priceTemplateAlertStrictMode": bool(is_price_template_alert_strict_mode_enabled()),
    }


def _resolve_optional_category(session: Session, *, category_code: str | None) -> Category | None:
    normalized = _normalize_optional_string(category_code)
    if not normalized:
        return None
    resolved = resolve_category_code(normalized)
    row = session.execute(select(Category).where(Category.code == resolved)).scalar_one_or_none()
    if row is None:
        raise PricingMonitoringError(f"Category not found: {resolved}")
    return row


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "PricingMonitoringError",
    "summarize_template_availability_monitoring",
    "summarize_template_availability_monitoring_with_session",
]
