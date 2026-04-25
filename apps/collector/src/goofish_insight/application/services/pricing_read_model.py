from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ...models import BuyPriceBaseline
from .pricing_explanations import build_buy_price_baseline_explanation
from .pricing_templates import build_pricing_contract, build_pricing_record_template_snapshot


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def get_pricing_record_read_model(
    session: Session,
    *,
    record: dict[str, Any],
    business_domain: str | None = None,
) -> dict[str, Any]:
    """Build a stable pricing read model for one listing record."""
    template_snapshot = build_pricing_record_template_snapshot(
        business_domain=business_domain or str(record.get("category_code") or ""),
        record=record,
        session=session,
    )
    return {
        **record,
        "template_key": template_snapshot.get("templateKey"),
        "template_label": template_snapshot.get("templateLabel"),
        "template_availability_tier": template_snapshot.get("completenessStatus"),
        "template_snapshot": template_snapshot,
    }


def get_baseline_explanation_read_model(
    session: Session,
    *,
    baseline: BuyPriceBaseline,
) -> dict[str, Any]:
    """Build a stable baseline explanation read model."""
    _ = session
    payload = dict(baseline.payload or {})
    pricing_contract = dict(payload.get("pricingContract") or {})
    resolved_fields = dict(payload.get("resolvedFields") or {})
    missing_fields = list(payload.get("missingFields") or [])
    explanation = build_buy_price_baseline_explanation(baseline)
    return {
        "baseline_id": str(baseline.id),
        "category_id": baseline.category_id,
        "model_catalog_id": baseline.model_catalog_id,
        "baseline_key": baseline.baseline_key,
        "baseline_date": baseline.baseline_date.isoformat() if baseline.baseline_date else None,
        "fair_price": _decimal_to_float(baseline.fair_price),
        "median_price": _decimal_to_float(baseline.median_price),
        "sample_size": baseline.sample_size,
        "window_days": payload.get("windowDays"),
        "missing_rate": _decimal_to_float(payload.get("missingRate")),
        "resolved_fields": resolved_fields,
        "missing_fields": missing_fields,
        "pricing_contract": pricing_contract,
        "computed_at": payload.get("computedAt"),
        "is_active": payload.get("isActive"),
        "version": payload.get("version"),
        "explanation": explanation,
    }


def get_template_guidance_read_model(
    session: Session,
    *,
    business_domain: str | None,
    selected_filters: dict[str, Any],
    filter_catalog: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    """Expose template guidance subset from the pricing contract."""
    contract = build_pricing_contract(
        business_domain=business_domain,
        selected_filters=selected_filters,
        filter_catalog=filter_catalog or {},
        session=session,
    )
    return {
        "category_code": contract.get("categoryCode"),
        "template_key": contract.get("templateKeyPreview"),
        "template_label": contract.get("templateLabelPreview"),
        "resolved_field_values": dict(contract.get("selectedPricingValues") or {}),
        "required_pricing_fields": list(contract.get("requiredPricingFields") or []),
        "pricing_key_fields": list(contract.get("pricingKeyFields") or []),
        "missing_fields": list(contract.get("missingPricingFields") or []),
        "completeness_status": (contract.get("templateCompleteness") or {}).get("status"),
        "unsupported_pricing_fields": list(contract.get("unsupportedPricingFields") or []),
    }


def get_pricing_contract_read_model(
    session: Session,
    *,
    business_domain: str | None,
    selected_filters: dict[str, Any],
    filter_catalog: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    """Expose pricing contract as a read model payload."""
    return build_pricing_contract(
        business_domain=business_domain,
        selected_filters=selected_filters,
        filter_catalog=filter_catalog or {},
        session=session,
    )


__all__ = [
    "get_pricing_record_read_model",
    "get_baseline_explanation_read_model",
    "get_template_guidance_read_model",
    "get_pricing_contract_read_model",
]
