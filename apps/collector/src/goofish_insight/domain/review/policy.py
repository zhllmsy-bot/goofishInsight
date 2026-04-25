from __future__ import annotations

from typing import Any

from .contracts import REVIEW_STATUS_INVALID, REVIEW_STATUS_VALID, normalize_invalid_reason, normalize_review_status

LLM_REVIEW_VALID_CONFIDENCE = 0.90
LLM_REVIEW_INVALID_MAX_CONFIDENCE = 0.30
PRICING_VALID_CONFIDENCE = 0.95


def resolve_review_status(*, review_status: Any, invalid_reason: Any = None) -> str:
    normalized_status = normalize_review_status(review_status)
    normalized_reason = normalize_invalid_reason(invalid_reason)
    if normalized_status is not None:
        return normalized_status
    if normalized_reason:
        return REVIEW_STATUS_INVALID
    return REVIEW_STATUS_VALID


def review_confidence_passes_acceptance_gate(*, review_status: Any, confidence: float | None) -> bool:
    if confidence is None:
        return False
    status = resolve_review_status(review_status=review_status)
    if status == REVIEW_STATUS_INVALID:
        return float(confidence) <= LLM_REVIEW_INVALID_MAX_CONFIDENCE
    return float(confidence) >= LLM_REVIEW_VALID_CONFIDENCE


def review_decision_strength(*, review_status: Any, confidence: float | None) -> float:
    if confidence is None:
        return -1.0
    status = resolve_review_status(review_status=review_status)
    numeric_confidence = max(0.0, min(float(confidence), 1.0))
    if status == REVIEW_STATUS_INVALID:
        return 1.0 - numeric_confidence
    return numeric_confidence


def pricing_review_passes_gate(
    *,
    review_status: Any,
    confidence: float | None,
    needs_audit: bool,
) -> bool:
    if needs_audit:
        return False
    if resolve_review_status(review_status=review_status) != REVIEW_STATUS_VALID:
        return False
    if confidence is None:
        return False
    return float(confidence) >= PRICING_VALID_CONFIDENCE
