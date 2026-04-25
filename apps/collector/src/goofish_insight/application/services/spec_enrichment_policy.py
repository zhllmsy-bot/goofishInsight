from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...category_compat import is_apple_computer_scope, is_garmin_watch_scope
from .pricing_eligibility import MIN_SPEC_CONFIDENCE_FOR_PRICING

SPEC_RETRY_CONFIDENCE_THRESHOLD = Decimal(str(MIN_SPEC_CONFIDENCE_FOR_PRICING))
APPLE_SCREEN_SIZE_REQUIRED_LINES = {"MacBook Air", "MacBook Pro", "iMac"}
GARMIN_SOLAR_TOKENS = ("solar", "太阳能", "双动力")
GARMIN_DISPLAY_TOKENS = ("amoled", "mip", "反射屏")
APPLE_WATCH_TOKENS = ("apple watch", "watch se", "watch series", "watch ultra")
SPEC_NON_RETRY_REASONS = {"non_target_apple_watch", "invalid_screen_size_in"}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True



def _coerce_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None



def _listing_text(item: Any, candidate: Any) -> str:
    title = str(getattr(item, "title", "") or "")
    condition_tags = list(getattr(item, "condition_tags", None) or [])
    edition_tags = list(getattr(candidate, "edition_tags", None) or [])
    return " ".join([title, *[str(tag) for tag in condition_tags], *[str(tag) for tag in edition_tags]]).lower()


def _invalidate_candidate_as_garbage(*, candidate: Any, reason: str) -> Any:
    """Mark candidate as unresolved and clear fields that are known to pollute downstream analytics."""
    for field in (
        "brand",
        "product_line",
        "model_family",
        "model_name",
        "generation",
        "case_size_mm",
        "is_solar",
        "display_type",
        "screen_size_in",
        "chip_family",
        "cpu_model",
        "cpu_cores",
        "gpu_cores",
        "memory_gb",
        "storage_gb",
    ):
        try:
            setattr(candidate, field, None)
        except Exception:
            continue
    try:
        candidate.edition_tags = []
    except Exception:
        pass
    candidate.status = "unresolved"
    candidate.needs_review = True
    evidence = dict(getattr(candidate, "evidence", {}) or {})
    evidence["reason"] = reason
    candidate.evidence = evidence
    payload = dict(getattr(candidate, "extraction_payload", {}) or {})
    payload["rejected_by_policy"] = {"reason": reason}
    candidate.extraction_payload = payload
    return candidate


def reject_obvious_garbage_candidate(*, item: Any, candidate: Any) -> Any:
    """Hard guardrails for obviously invalid candidates.

    These are conservative checks meant to prevent unit mixups or cross-category pollution from landing in DB.
    """
    domain = str(getattr(item, "business_domain", "") or "")
    model_name = str(getattr(candidate, "model_name", "") or "")
    text = _listing_text(item, candidate)

    if is_apple_computer_scope(domain):
        if any(token in text for token in APPLE_WATCH_TOKENS) or "watch" in model_name.lower():
            return _invalidate_candidate_as_garbage(candidate=candidate, reason="non_target_apple_watch")
        screen_size = getattr(candidate, "screen_size_in", None)
        if screen_size is not None:
            try:
                if Decimal(str(screen_size)) > Decimal("30"):
                    return _invalidate_candidate_as_garbage(candidate=candidate, reason="invalid_screen_size_in")
            except Exception:
                return _invalidate_candidate_as_garbage(candidate=candidate, reason="invalid_screen_size_in")

    return candidate



def required_fields_for_candidate(*, item: Any, candidate: Any) -> tuple[str, ...]:
    if is_apple_computer_scope(getattr(item, "business_domain", None)):
        required = ["product_line", "chip_family", "memory_gb", "storage_gb"]
        if str(getattr(candidate, "product_line", "") or "") in APPLE_SCREEN_SIZE_REQUIRED_LINES:
            required.append("screen_size_in")
        return tuple(required)
    if is_garmin_watch_scope(getattr(item, "business_domain", None)):
        required = ["model_name", "case_size_mm"]
        text = _listing_text(item, candidate)
        if any(token in text for token in GARMIN_DISPLAY_TOKENS) or _has_value(getattr(candidate, "display_type", None)):
            required.append("display_type")
        if any(token in text for token in GARMIN_SOLAR_TOKENS) or _has_value(getattr(candidate, "is_solar", None)):
            required.append("is_solar")
        return tuple(required)
    return ()



def identity_fields_for_candidate(*, item: Any) -> tuple[str, ...]:
    if is_apple_computer_scope(getattr(item, "business_domain", None)):
        return ("product_line", "chip_family", "model_name")
    if is_garmin_watch_scope(getattr(item, "business_domain", None)):
        return ("product_line", "model_name")
    return ()



def missing_required_fields(*, item: Any, candidate: Any) -> tuple[str, ...]:
    return tuple(
        field
        for field in required_fields_for_candidate(item=item, candidate=candidate)
        if not _has_value(getattr(candidate, field, None))
    )



def apply_spec_enrichment_contract(*, item: Any, candidate: Any, source: str) -> Any:
    if getattr(candidate, "status", None) == "failed":
        return candidate

    candidate = reject_obvious_garbage_candidate(item=item, candidate=candidate)
    rejected_reason = str((getattr(candidate, "evidence", {}) or {}).get("reason") or "")

    identity_fields = identity_fields_for_candidate(item=item)
    required_fields = required_fields_for_candidate(item=item, candidate=candidate)
    missing_fields = missing_required_fields(item=item, candidate=candidate)
    identity_present = any(_has_value(getattr(candidate, field, None)) for field in identity_fields)
    confidence = _coerce_decimal(getattr(candidate, "confidence", None))
    non_target_reason = str((getattr(candidate, "evidence", {}) or {}).get("reason") or "")

    if non_target_reason == "non_target_camera_body":
        candidate.status = "unresolved"
        candidate.needs_review = False
    elif rejected_reason in SPEC_NON_RETRY_REASONS:
        # Hard-rejected candidates should not be overwritten by confidence gating logic below.
        candidate.status = "unresolved"
        candidate.needs_review = True
    elif identity_fields:
        if not identity_present:
            candidate.status = "unresolved"
            candidate.needs_review = confidence is None or confidence < SPEC_RETRY_CONFIDENCE_THRESHOLD
        elif not missing_fields:
            candidate.status = "complete"
            candidate.needs_review = confidence is None or confidence < SPEC_RETRY_CONFIDENCE_THRESHOLD
        else:
            candidate.status = "partial"
            candidate.needs_review = True
    elif confidence is not None and confidence >= Decimal("0.78") and getattr(candidate, "status", None) == "complete":
        candidate.needs_review = False

    extraction_payload = dict(getattr(candidate, "extraction_payload", {}) or {})
    extraction_payload["contract"] = {
        "source": source,
        "requiredFields": list(required_fields),
        "missingRequiredFields": list(missing_fields),
        "identityFields": list(identity_fields),
        "status": getattr(candidate, "status", None),
        "needsReview": bool(getattr(candidate, "needs_review", False)),
    }
    candidate.extraction_payload = extraction_payload
    return candidate



def should_auto_retry_existing_enrichment(*, item: Any, enrichment: Any | None) -> bool:
    if enrichment is None:
        return True
    status = str(getattr(enrichment, "status", "") or "")
    confidence = _coerce_decimal(getattr(enrichment, "confidence", None))
    needs_review = bool(getattr(enrichment, "needs_review", False))

    if status in {"unresolved", "failed"}:
        reason = str((getattr(enrichment, "evidence", {}) or {}).get("reason") or "")
        if reason in SPEC_NON_RETRY_REASONS:
            return False
        return True
    if status == "complete":
        return confidence is None or confidence < SPEC_RETRY_CONFIDENCE_THRESHOLD
    if status != "partial":
        return confidence is None
    if not needs_review:
        return False
    if confidence is not None and confidence >= SPEC_RETRY_CONFIDENCE_THRESHOLD:
        return False

    missing_fields = missing_required_fields(item=item, candidate=enrichment)
    identity_fields = identity_fields_for_candidate(item=item)
    if not identity_fields:
        return True
    return bool(missing_fields)
