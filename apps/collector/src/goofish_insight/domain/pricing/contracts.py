from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any


PRICING_RECORD_FIELDS = {
    "item_id_ref": {"type": "int", "required": True},
    "item_id": {"type": "str", "required": True},
    "source_platform": {"type": "str", "required": True},
    "category_code": {"type": "str", "required": True},
    "category_name": {"type": "str", "required": False},
    "category_id": {"type": "str", "required": False},
    "template_id": {"type": "str", "required": False},
    "model_catalog_id": {"type": "str", "required": False},
    "seller_key": {"type": "str", "required": True},
    "title": {"type": "str", "required": True},
    "region": {"type": "str", "required": False},
    "listing_url": {"type": "str", "required": False},
    "price": {"type": "float", "required": True},
    "last_seen_at": {"type": "datetime", "required": True},
    "publish_time": {"type": "datetime", "required": False},
    "first_seen_at": {"type": "datetime", "required": False},
    "brand": {"type": "str", "required": True},
    "product_line": {"type": "str", "required": False},
    "model_name": {"type": "str", "required": False},
    "product_label": {"type": "str", "required": True},
    "spec_label": {"type": "str", "required": False},
    "exact_spec_ready": {"type": "bool", "required": False},
    "display_type": {"type": "str", "required": False},
    "case_size_mm": {"type": "int", "required": False},
    "is_solar": {"type": "bool", "required": False},
    "screen_size_in": {"type": "float", "required": False},
    "chip_family": {"type": "str", "required": False},
    "cpu_cores": {"type": "int", "required": False},
    "gpu_cores": {"type": "int", "required": False},
    "memory_gb": {"type": "int", "required": False},
    "storage_gb": {"type": "int", "required": False},
    "spec_status": {"type": "str", "required": False},
    "spec_confidence": {"type": "float", "required": False},
    "spec_contract": {"type": "dict", "required": False},
    "spec_source": {"type": "dict", "required": False},
    "pricing_eligibility": {"type": "dict", "required": False},
}

BASELINE_EXPLANATION_FIELDS = {
    "readiness_summary": {"type": "str", "required": True},
    "availability_tier": {"type": "str", "required": False},
    "availability_reason": {"type": "str", "required": False},
    "availability_reason_label": {"type": "str", "required": False},
    "confidence_summary": {"type": "str", "required": True},
    "seller_sample_count": {"type": "int", "required": False},
    "unique_seller_count": {"type": "int", "required": False},
    "exact_spec_ratio": {"type": "float", "required": False},
    "reliability_score": {"type": "float", "required": False},
    "effective_sample_count": {"type": "float", "required": False},
    "recency_weighted_sample_count": {"type": "float", "required": False},
    "mad": {"type": "float", "required": False},
    "confidence_score": {"type": "float", "required": False},
    "confidence_reasons": {"type": "list", "required": False},
    "quality_tier": {"type": "str", "required": False},
    "p15_price": {"type": "float", "required": False},
    "p35_price": {"type": "float", "required": False},
    "p50_price": {"type": "float", "required": False},
    "freshness_days": {"type": "int", "required": False},
}

TEMPLATE_GUIDANCE_FIELDS = {
    "category_code": {"type": "str", "required": True},
    "template_key": {"type": "str", "required": False},
    "template_label": {"type": "str", "required": False},
    "resolved_field_values": {"type": "dict", "required": False},
    "required_pricing_fields": {"type": "list", "required": False},
    "pricing_key_fields": {"type": "list", "required": False},
    "missing_fields": {"type": "list", "required": False},
    "completeness_status": {"type": "str", "required": False},
    "unsupported_pricing_fields": {"type": "list", "required": False},
}

ALERT_EVENT_FIELDS = {
    "id": {"type": "str", "required": True},
    "opportunity_id": {"type": "str", "required": True},
    "watch_target_id": {"type": "str", "required": True},
    "alert_channel": {"type": "str", "required": True},
    "alert_reason": {"type": "str", "required": True},
    "status": {"type": "str", "required": True},
    "sent_at": {"type": "datetime", "required": False},
}

AVAILABILITY_TIERS = {"guidance_ready", "reference_only", "incomplete", "blocked"}
QUALITY_TIERS = {"A", "B", "C", "D"}
OPPORTUNITY_STATUSES = {"OPEN", "REFERENCE_ONLY", "STALE", "CLOSED"}
ALERT_STATUSES = {"PENDING", "SENT", "FAILED", "CANCELLED"}
COMPLETENESS_STATUSES = {"complete", "partial", "missing", "legacy"}

PRICING_BLOCK_REASONS = {
    "template_incomplete",
    "insufficient_seller_samples",
    "insufficient_unique_sellers",
    "insufficient_exact_spec_ratio",
    "insufficient_reliability_score",
    "stale_pricing_evidence",
    "insufficient_pricing_evidence",
}


def normalize_availability_tier(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    lowered = text.lower()
    return lowered if lowered in AVAILABILITY_TIERS else None


def normalize_quality_tier(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    upper = text.upper()
    return upper if upper in QUALITY_TIERS else None


def normalize_opportunity_status(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    upper = text.upper()
    return upper if upper in OPPORTUNITY_STATUSES else None


def normalize_alert_status(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    upper = text.upper()
    return upper if upper in ALERT_STATUSES else None


def normalize_completeness_status(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    lowered = text.lower()
    return lowered if lowered in COMPLETENESS_STATUSES else None


def normalize_pricing_block_reason(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    lowered = text.lower()
    return lowered if lowered in PRICING_BLOCK_REASONS else None


def serialize_pricing_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "itemIdRef": record.get("item_id_ref"),
        "itemId": record.get("item_id"),
        "sourcePlatform": record.get("source_platform"),
        "categoryCode": record.get("category_code"),
        "categoryName": record.get("category_name"),
        "categoryId": record.get("category_id"),
        "templateId": record.get("template_id"),
        "modelCatalogId": record.get("model_catalog_id"),
        "sellerKey": record.get("seller_key"),
        "title": record.get("title"),
        "region": record.get("region"),
        "listingUrl": record.get("listing_url"),
        "price": _decimal_to_float(record.get("price")),
        "lastSeenAt": _datetime_to_iso(record.get("last_seen_at")),
        "publishTime": _datetime_to_iso(record.get("publish_time")),
        "firstSeenAt": _datetime_to_iso(record.get("first_seen_at")),
        "brand": record.get("brand"),
        "productLine": record.get("product_line"),
        "modelName": record.get("model_name"),
        "productLabel": record.get("product_label"),
        "specLabel": record.get("spec_label"),
        "exactSpecReady": record.get("exact_spec_ready"),
        "displayType": record.get("display_type"),
        "caseSizeMm": record.get("case_size_mm"),
        "isSolar": record.get("is_solar"),
        "screenSizeIn": _decimal_to_float(record.get("screen_size_in")),
        "chipFamily": record.get("chip_family"),
        "cpuCores": record.get("cpu_cores"),
        "gpuCores": record.get("gpu_cores"),
        "memoryGb": record.get("memory_gb"),
        "storageGb": record.get("storage_gb"),
        "specStatus": record.get("spec_status"),
        "specConfidence": record.get("spec_confidence"),
        "specContract": dict(record.get("spec_contract") or {}),
        "specSource": dict(record.get("spec_source") or {}),
        "pricingEligibility": dict(record.get("pricing_eligibility") or {}),
    }


def serialize_baseline_explanation(explanation: dict[str, Any]) -> dict[str, Any]:
    return {
        "readinessSummary": explanation.get("readiness_summary"),
        "availabilityTier": explanation.get("availability_tier"),
        "availabilityReason": explanation.get("availability_reason"),
        "availabilityReasonLabel": explanation.get("availability_reason_label"),
        "confidenceSummary": explanation.get("confidence_summary"),
        "sellerSampleCount": explanation.get("seller_sample_count"),
        "uniqueSellerCount": explanation.get("unique_seller_count"),
        "exactSpecRatio": explanation.get("exact_spec_ratio"),
        "reliabilityScore": explanation.get("reliability_score"),
        "effectiveSampleCount": explanation.get("effective_sample_count"),
        "recencyWeightedSampleCount": explanation.get("recency_weighted_sample_count"),
        "mad": explanation.get("mad"),
        "confidenceScore": explanation.get("confidence_score"),
        "confidenceReasons": list(explanation.get("confidence_reasons") or []),
        "qualityTier": explanation.get("quality_tier"),
        "p15Price": explanation.get("p15_price"),
        "p35Price": explanation.get("p35_price"),
        "p50Price": explanation.get("p50_price"),
        "freshnessDays": explanation.get("freshness_days"),
    }


def serialize_template_guidance(guidance: dict[str, Any]) -> dict[str, Any]:
    return {
        "categoryCode": guidance.get("category_code"),
        "templateKey": guidance.get("template_key"),
        "templateLabel": guidance.get("template_label"),
        "resolvedFieldValues": dict(guidance.get("resolved_field_values") or {}),
        "requiredPricingFields": list(guidance.get("required_pricing_fields") or []),
        "pricingKeyFields": list(guidance.get("pricing_key_fields") or []),
        "missingFields": list(guidance.get("missing_fields") or []),
        "completenessStatus": guidance.get("completeness_status"),
        "unsupportedPricingFields": list(guidance.get("unsupported_pricing_fields") or []),
    }


def serialize_alert_event(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": alert.get("id"),
        "opportunityId": alert.get("opportunity_id"),
        "watchTargetId": alert.get("watch_target_id"),
        "alertChannel": alert.get("alert_channel"),
        "alertReason": alert.get("alert_reason"),
        "status": alert.get("status"),
        "sentAt": _datetime_to_iso(alert.get("sent_at")),
        "payload": dict(alert.get("payload") or {}),
    }


def validate_pricing_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field_name, schema in PRICING_RECORD_FIELDS.items():
        if not schema.get("required", False):
            continue
        if record.get(field_name) is None:
            errors.append(f"missing required field: {field_name}")
    return errors


def validate_baseline_explanation(explanation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field_name, schema in BASELINE_EXPLANATION_FIELDS.items():
        if not schema.get("required", False):
            continue
        if explanation.get(field_name) is None:
            errors.append(f"missing required field: {field_name}")
    tier = explanation.get("availability_tier")
    if tier is not None and normalize_availability_tier(tier) is None:
        errors.append(f"invalid availability_tier: {tier}")
    quality_tier = explanation.get("quality_tier")
    if quality_tier is not None and normalize_quality_tier(quality_tier) is None:
        errors.append(f"invalid quality_tier: {quality_tier}")
    return errors


def validate_template_guidance(guidance: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field_name, schema in TEMPLATE_GUIDANCE_FIELDS.items():
        if not schema.get("required", False):
            continue
        if guidance.get(field_name) is None:
            errors.append(f"missing required field: {field_name}")
    status = guidance.get("completeness_status")
    if status is not None and normalize_completeness_status(status) is None:
        errors.append(f"invalid completeness_status: {status}")
    return errors


def validate_alert_event(alert: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field_name, schema in ALERT_EVENT_FIELDS.items():
        if not schema.get("required", False):
            continue
        if alert.get(field_name) is None:
            errors.append(f"missing required field: {field_name}")
    status = alert.get("status")
    if status is not None and normalize_alert_status(status) is None:
        errors.append(f"invalid alert status: {status}")
    return errors


def build_contract_field_lines() -> list[str]:
    lines: list[str] = []
    lines.append("# Pricing Record Fields")
    for field_name, schema in sorted(PRICING_RECORD_FIELDS.items()):
        required_marker = "*" if schema.get("required") else " "
        lines.append(f"  {required_marker} {field_name}<{schema['type']}>")
    lines.append("")
    lines.append("# Baseline Explanation Fields")
    for field_name, schema in sorted(BASELINE_EXPLANATION_FIELDS.items()):
        required_marker = "*" if schema.get("required") else " "
        lines.append(f"  {required_marker} {field_name}<{schema['type']}>")
    lines.append("")
    lines.append("# Template Guidance Fields")
    for field_name, schema in sorted(TEMPLATE_GUIDANCE_FIELDS.items()):
        required_marker = "*" if schema.get("required") else " "
        lines.append(f"  {required_marker} {field_name}<{schema['type']}>")
    lines.append("")
    lines.append("# Alert Event Fields")
    for field_name, schema in sorted(ALERT_EVENT_FIELDS.items()):
        required_marker = "*" if schema.get("required") else " "
        lines.append(f"  {required_marker} {field_name}<{schema['type']}>")
    return lines


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _datetime_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return None


__all__ = [
    "ALERT_EVENT_FIELDS",
    "ALERT_STATUSES",
    "AVAILABILITY_TIERS",
    "BASELINE_EXPLANATION_FIELDS",
    "COMPLETENESS_STATUSES",
    "OPPORTUNITY_STATUSES",
    "PRICING_BLOCK_REASONS",
    "PRICING_RECORD_FIELDS",
    "TEMPLATE_GUIDANCE_FIELDS",
    "build_contract_field_lines",
    "normalize_alert_status",
    "normalize_availability_tier",
    "normalize_completeness_status",
    "normalize_opportunity_status",
    "normalize_pricing_block_reason",
    "normalize_quality_tier",
    "serialize_alert_event",
    "serialize_baseline_explanation",
    "serialize_pricing_record",
    "serialize_template_guidance",
    "validate_alert_event",
    "validate_baseline_explanation",
    "validate_pricing_record",
    "validate_template_guidance",
]
