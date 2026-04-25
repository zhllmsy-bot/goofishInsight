from __future__ import annotations

from decimal import Decimal
from typing import Any

from goofish_analyzer.adapters import (
    AVAILABILITY_TIERS,
    normalize_availability_tier,
    normalize_opportunity_status,
    normalize_pricing_block_reason,
    serialize_baseline_explanation,
    BuyPriceBaseline,
)
from goofish_analyzer.services.pricing_thresholds import build_pricing_availability_summary


def build_buy_opportunity_explanation(
    *,
    opportunity_status: str | None,
    pricing_eligibility: dict[str, Any],
    spec_contract: dict[str, Any],
    template_guidance_ready: bool,
) -> dict[str, Any]:
    review_gate = dict(pricing_eligibility.get("reviewGate") or {})
    spec_gate = dict(pricing_eligibility.get("specGate") or {})
    pricing_ready = bool(pricing_eligibility.get("pricingReady"))
    missing_fields = [str(field) for field in (spec_contract.get("missingRequiredFields") or []) if str(field).strip()]
    review_summary = review_gate.get("reasonLabel") or ("review ready" if review_gate.get("passed") else "review pending")
    spec_summary = spec_gate.get("reasonLabel") or ("spec ready" if spec_gate.get("passed") else "spec pending")

    normalized_status = normalize_opportunity_status(opportunity_status)
    if pricing_ready and template_guidance_ready and normalized_status == "OPEN":
        readiness_summary = "可直接按价格池口径判断"
    elif missing_fields:
        readiness_summary = f"仅参考：缺 {', '.join(missing_fields)}"
    elif not template_guidance_ready:
        readiness_summary = "仅参考：模板指导未就绪"
    elif not pricing_ready:
        readiness_summary = f"未进入价格池：{spec_summary if spec_gate.get('passed') is not True else review_summary}"
    else:
        readiness_summary = "仅参考：仍需人工复核"

    spec_contract_summary = (
        f"{spec_contract.get('status') or 'unknown'}"
        if not missing_fields
        else f"{spec_contract.get('status') or 'partial'} · 缺 {', '.join(missing_fields)}"
    )
    return {
        "readinessSummary": readiness_summary,
        "reviewGateSummary": review_summary,
        "specGateSummary": spec_summary,
        "specContractSummary": spec_contract_summary,
        "missingRequiredFields": missing_fields,
    }


def build_buy_price_baseline_explanation(row: BuyPriceBaseline) -> dict[str, Any]:
    payload = dict(row.payload or {})
    pricing_template = dict(payload.get("pricingTemplate") or {})
    availability = dict(pricing_template.get("availability") or {})
    evidence = dict(availability.get("pricingEvidence") or {})
    availability_tier = normalize_availability_tier(availability.get("availabilityTier"))
    block_reason = normalize_pricing_block_reason(availability.get("pricingBlockReason"))
    confidence = _decimal_to_float(row.confidence)

    availability_summary = build_pricing_availability_summary(
        availability_tier=availability_tier,
        pricing_block_reason=block_reason,
        evidence=evidence,
    )

    if confidence is None:
        confidence_summary = "置信度缺失"
    elif confidence >= 0.8:
        confidence_summary = "高置信"
    elif confidence >= 0.6:
        confidence_summary = "中置信"
    else:
        confidence_summary = "低置信"

    internal_explanation = {
        "readiness_summary": (
            "可直接作为买入线参考"
            if availability_tier == "guidance_ready"
            else availability_summary["readinessSummary"]
        ),
        "availability_tier": availability_tier,
        "availability_reason": block_reason,
        "availability_reason_label": availability_summary.get("reasonLabel"),
        "confidence_summary": confidence_summary,
        "seller_sample_count": availability_summary.get("sellerSampleCount", row.sample_size),
        "unique_seller_count": availability_summary.get("uniqueSellerCount"),
        "exact_spec_ratio": availability_summary.get("exactSpecRatio"),
        "reliability_score": availability_summary.get("reliabilityScore"),
        "freshness_days": availability_summary.get("freshnessDays"),
    }
    return serialize_baseline_explanation(internal_explanation)


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


__all__ = [
    "build_buy_opportunity_explanation",
    "build_buy_price_baseline_explanation",
]
