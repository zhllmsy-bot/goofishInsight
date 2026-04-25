from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...models import Item, ItemSpecEnrichment

PRICING_GATE_REASON_LABELS = {
    "pending_audit": "待审核",
    "invalid": "已判无效",
    "low_confidence": "有效但低于利润池门槛",
    "review_not_ready": "审查未完成",
}
SPEC_GATE_REASON_LABELS = {
    "missing_spec": "缺少可用规格",
    "shadow_spec": "仅有影子规格行",
    "unresolved_spec": "规格提取未收敛",
    "missing_spec_confidence": "规格缺少置信度",
    "low_spec_confidence": "规格置信度低于价格池门槛",
}
REVIEW_STATUS_VALID = "valid"
REVIEW_STATUS_INVALID = "invalid"
REVIEW_STATUS_PENDING_AUDIT = "pending_audit"
PRICING_VALID_CONFIDENCE = 0.95
MIN_SPEC_CONFIDENCE_FOR_PRICING = 0.75
NON_PRICING_SPEC_EXTRACTOR_TYPES = {"llm_review"}


def decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def float_to_decimal(value: float | int | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return None


def pricing_review_passes_gate(
    *,
    review_status: Any,
    confidence: float | None,
    needs_audit: bool,
) -> bool:
    if needs_audit:
        return False
    if str(review_status or "").strip().lower() != REVIEW_STATUS_VALID:
        return False
    if confidence is None:
        return False
    return float(confidence) >= PRICING_VALID_CONFIDENCE


def is_item_eligible_for_pricing(item: Item) -> bool:
    confidence = decimal_to_float(item.llm_review_confidence) if item.llm_review_confidence is not None else None
    return pricing_review_passes_gate(
        review_status=item.llm_review_status,
        confidence=confidence,
        needs_audit=bool(item.llm_review_needs_audit),
    ) and bool(item.llm_reviewed)



def pricing_gate_exclusion_reason(item: Item) -> str | None:
    status = item.llm_review_status
    confidence = decimal_to_float(item.llm_review_confidence) if item.llm_review_confidence is not None else None
    if item.llm_review_needs_audit or status == REVIEW_STATUS_PENDING_AUDIT:
        return "pending_audit"
    if status == REVIEW_STATUS_INVALID:
        return "invalid"
    if not item.llm_reviewed or status != REVIEW_STATUS_VALID or confidence is None:
        return "review_not_ready"
    if confidence < PRICING_VALID_CONFIDENCE:
        return "low_confidence"
    return None


def build_pricing_spec_source_snapshot(spec: ItemSpecEnrichment | None) -> dict[str, Any]:
    extractor_type = str(getattr(spec, "extractor_type", "") or "").strip().lower() or None
    is_shadow = bool(extractor_type in NON_PRICING_SPEC_EXTRACTOR_TYPES)
    return {
        "present": spec is not None,
        "extractorType": extractor_type,
        "isShadow": is_shadow,
        "pricingUsable": bool(spec is not None and not is_shadow),
    }



def usable_spec_for_pricing(spec: ItemSpecEnrichment | None) -> ItemSpecEnrichment | None:
    spec_source = build_pricing_spec_source_snapshot(spec)
    if not spec_source["pricingUsable"]:
        return None
    return spec



def spec_confidence_passes_pricing_gate(confidence: float | None) -> bool:
    return confidence is not None and confidence >= MIN_SPEC_CONFIDENCE_FOR_PRICING


def spec_pricing_exclusion_reason(
    *,
    raw_spec: ItemSpecEnrichment | None,
    spec_status: Any,
    spec_confidence: float | None,
) -> str | None:
    spec_source = build_pricing_spec_source_snapshot(raw_spec)
    normalized_status = str(spec_status or "").strip().lower()
    if spec_source["isShadow"]:
        return "shadow_spec"
    if normalized_status == "unresolved":
        return "unresolved_spec"
    if spec_confidence is None:
        if not spec_source["present"] and not normalized_status:
            return "missing_spec"
        return "missing_spec_confidence"
    if spec_confidence < MIN_SPEC_CONFIDENCE_FOR_PRICING:
        return "low_spec_confidence"
    return None


def build_pricing_eligibility_snapshot(
    *,
    item: Item,
    raw_spec: ItemSpecEnrichment | None,
    spec_status: Any,
    spec_confidence: float | None,
    exact_spec_ready: bool,
) -> dict[str, Any]:
    spec_source = build_pricing_spec_source_snapshot(raw_spec)
    review_reason = pricing_gate_exclusion_reason(item)
    spec_reason = spec_pricing_exclusion_reason(
        raw_spec=raw_spec,
        spec_status=spec_status,
        spec_confidence=spec_confidence,
    )
    review_confidence = (
        decimal_to_float(item.llm_review_confidence)
        if item.llm_review_confidence is not None
        else None
    )
    return {
        "pricingReady": review_reason is None and spec_reason is None,
        "specSource": spec_source,
        "reviewGate": {
            "passed": review_reason is None,
            "reason": review_reason,
            "reasonLabel": PRICING_GATE_REASON_LABELS.get(review_reason) if review_reason else None,
            "status": str(item.llm_review_status or "").strip().lower() or None,
            "confidence": review_confidence,
            "threshold": PRICING_VALID_CONFIDENCE,
            "needsAudit": bool(item.llm_review_needs_audit),
            "reviewed": bool(item.llm_reviewed),
        },
        "specGate": {
            "passed": spec_reason is None,
            "reason": spec_reason,
            "reasonLabel": SPEC_GATE_REASON_LABELS.get(spec_reason) if spec_reason else None,
            "status": str(spec_status or "").strip().lower() or None,
            "confidence": spec_confidence,
            "threshold": MIN_SPEC_CONFIDENCE_FOR_PRICING,
            "exactSpecReady": bool(exact_spec_ready),
            "extractorType": spec_source.get("extractorType"),
        },
    }
