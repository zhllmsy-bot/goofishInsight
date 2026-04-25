from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


REFERENCE_ONLY_THRESHOLDS = {
    "seller_sample_count": 3,
    "unique_seller_count": 2,
    "exact_spec_ratio": 0.65,
    "reliability_score": 60.0,
    "freshness_days": 14,
}

GUIDANCE_READY_THRESHOLDS = {
    "seller_sample_count": 5,
    "unique_seller_count": 3,
    "exact_spec_ratio": 0.80,
    "reliability_score": 70.0,
    "freshness_days": 14,
}

PRICING_BLOCK_REASON_LABELS = {
    "template_incomplete": "模板未完整覆盖定价字段",
    "insufficient_seller_samples": "卖家样本数不足",
    "insufficient_unique_sellers": "不同卖家数不足",
    "insufficient_exact_spec_ratio": "精确规格覆盖不足",
    "insufficient_reliability_score": "可靠度不足",
    "stale_pricing_evidence": "价格证据已过期",
    "insufficient_pricing_evidence": "价格证据不足",
}


def evaluate_pricing_availability(
    *,
    template_complete: bool,
    seller_sample_count: int | None,
    unique_seller_count: int | None,
    exact_spec_ratio: float | None,
    reliability_score: float | None,
    latest_seen_at: str | datetime | None,
    as_of: datetime | None = None,
    reference_only_thresholds: dict[str, float | int] | None = None,
    guidance_ready_thresholds: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    effective_reference_thresholds = _normalized_thresholds(
        reference_only_thresholds,
        fallback=REFERENCE_ONLY_THRESHOLDS,
    )
    effective_guidance_thresholds = _normalized_thresholds(
        guidance_ready_thresholds,
        fallback=GUIDANCE_READY_THRESHOLDS,
    )
    evidence = {
        "sellerSampleCount": int(seller_sample_count or 0),
        "uniqueSellerCount": int(unique_seller_count or 0),
        "exactSpecRatio": float(exact_spec_ratio or 0.0),
        "reliabilityScore": float(reliability_score or 0.0),
        "latestSeenAt": _isoformat(latest_seen_at),
        "freshnessDays": _freshness_days(latest_seen_at, as_of=as_of),
        "templateComplete": bool(template_complete),
    }
    if not template_complete:
        return _availability_payload(
            tier="incomplete",
            available=False,
            reason="template_incomplete",
            evidence=evidence,
        )
    if not _meets_thresholds(evidence, effective_reference_thresholds):
        return _availability_payload(
            tier="blocked",
            available=False,
            reason=_first_failing_reason(evidence, effective_reference_thresholds),
            evidence=evidence,
        )
    if _meets_thresholds(evidence, effective_guidance_thresholds):
        return _availability_payload(
            tier="guidance_ready",
            available=True,
            reason=None,
            evidence=evidence,
        )
    return _availability_payload(
        tier="reference_only",
        available=True,
        reason=None,
        evidence=evidence,
    )


def _normalized_thresholds(
    value: dict[str, float | int] | None,
    *,
    fallback: dict[str, float | int],
) -> dict[str, float | int]:
    raw = dict(value or {})
    return {
        "seller_sample_count": int(raw.get("seller_sample_count", fallback["seller_sample_count"])),
        "unique_seller_count": int(raw.get("unique_seller_count", fallback["unique_seller_count"])),
        "exact_spec_ratio": float(raw.get("exact_spec_ratio", fallback["exact_spec_ratio"])),
        "reliability_score": float(raw.get("reliability_score", fallback["reliability_score"])),
        "freshness_days": int(raw.get("freshness_days", fallback["freshness_days"])),
    }


def _meets_thresholds(evidence: dict[str, Any], thresholds: dict[str, float | int]) -> bool:
    freshness_days = evidence.get("freshnessDays")
    if freshness_days is None:
        return False
    return (
        evidence["sellerSampleCount"] >= int(thresholds["seller_sample_count"])
        and evidence["uniqueSellerCount"] >= int(thresholds["unique_seller_count"])
        and evidence["exactSpecRatio"] >= float(thresholds["exact_spec_ratio"])
        and evidence["reliabilityScore"] >= float(thresholds["reliability_score"])
        and freshness_days <= int(thresholds["freshness_days"])
    )


def _first_failing_reason(evidence: dict[str, Any], thresholds: dict[str, float | int]) -> str:
    if evidence["sellerSampleCount"] < int(thresholds["seller_sample_count"]):
        return "insufficient_seller_samples"
    if evidence["uniqueSellerCount"] < int(thresholds["unique_seller_count"]):
        return "insufficient_unique_sellers"
    if evidence["exactSpecRatio"] < float(thresholds["exact_spec_ratio"]):
        return "insufficient_exact_spec_ratio"
    if evidence["reliabilityScore"] < float(thresholds["reliability_score"]):
        return "insufficient_reliability_score"
    freshness_days = evidence.get("freshnessDays")
    if freshness_days is None or freshness_days > int(thresholds["freshness_days"]):
        return "stale_pricing_evidence"
    return "insufficient_pricing_evidence"


def _freshness_days(latest_seen_at: str | datetime | None, *, as_of: datetime | None) -> int | None:
    parsed = _parse_datetime(latest_seen_at)
    if parsed is None:
        return None
    now = as_of.astimezone(UTC) if as_of is not None else datetime.now(UTC)
    delta = now - parsed.astimezone(UTC)
    if delta < timedelta(0):
        return 0
    return int(delta.total_seconds() // 86400)


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    return datetime.fromisoformat(text)


def _isoformat(value: str | datetime | None) -> str | None:
    parsed = _parse_datetime(value)
    return parsed.isoformat() if parsed is not None else None


def _availability_payload(
    *,
    tier: str,
    available: bool,
    reason: str | None,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    summary = build_pricing_availability_summary(
        availability_tier=tier,
        pricing_block_reason=reason,
        evidence=evidence,
    )
    return {
        "availabilityTier": tier,
        "pricingAvailable": available,
        "pricingBlockReason": reason,
        "pricingBlockReasonLabel": PRICING_BLOCK_REASON_LABELS.get(reason) if reason else None,
        "pricingEvidence": evidence,
        "pricingSummary": summary,
    }


def build_pricing_availability_summary(
    *,
    availability_tier: str | None,
    pricing_block_reason: str | None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_tier = str(availability_tier or "").strip().lower() or None
    normalized_reason = str(pricing_block_reason or "").strip().lower() or None
    evidence_payload = dict(evidence or {})
    if normalized_tier == "guidance_ready":
        readiness_summary = "可直接按价格指导口径使用"
    elif normalized_tier == "reference_only":
        readiness_summary = "仅参考：样本达基础线但未到指导线"
    elif normalized_reason:
        readiness_summary = f"暂不建议引用：{PRICING_BLOCK_REASON_LABELS.get(normalized_reason, normalized_reason)}"
    elif normalized_tier == "incomplete":
        readiness_summary = "暂不建议引用：模板未完整覆盖定价字段"
    else:
        readiness_summary = "暂不建议引用：价格证据不足"
    return {
        "readinessSummary": readiness_summary,
        "reasonLabel": PRICING_BLOCK_REASON_LABELS.get(normalized_reason) if normalized_reason else None,
        "sellerSampleCount": evidence_payload.get("sellerSampleCount"),
        "uniqueSellerCount": evidence_payload.get("uniqueSellerCount"),
        "exactSpecRatio": evidence_payload.get("exactSpecRatio"),
        "reliabilityScore": evidence_payload.get("reliabilityScore"),
        "freshnessDays": evidence_payload.get("freshnessDays"),
    }


def evaluate_pricing_row_availability(
    row: dict[str, Any],
    *,
    template_complete: bool,
    reference_only_thresholds: dict[str, float | int] | None = None,
    guidance_ready_thresholds: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    return evaluate_pricing_availability(
        template_complete=template_complete,
        seller_sample_count=row.get("seller_sample_count"),
        unique_seller_count=row.get("unique_seller_count"),
        exact_spec_ratio=row.get("exact_spec_ratio"),
        reliability_score=row.get("reliability_score"),
        latest_seen_at=row.get("latest_seen_at"),
        reference_only_thresholds=reference_only_thresholds,
        guidance_ready_thresholds=guidance_ready_thresholds,
    )


__all__ = [
    "evaluate_pricing_availability",
    "evaluate_pricing_row_availability",
    "build_pricing_availability_summary",
    "PRICING_BLOCK_REASON_LABELS",
    "REFERENCE_ONLY_THRESHOLDS",
    "GUIDANCE_READY_THRESHOLDS",
]
