from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...category_runtime_defaults import recommended_prompt_profile_for_category
from ...compat import UTC
from ...models import Category, CategoryRuntimeProfile
from .category_runtime_profile import upsert_category_runtime_profile_with_session
from .pricing_thresholds import GUIDANCE_READY_THRESHOLDS, REFERENCE_ONLY_THRESHOLDS

BUY_SIDE_CALIBRATION_METADATA_KEY = "buySideCalibration"

DEFAULT_BUY_SIDE_SCORING_CONFIG = {
    "buyCeilingTightenPct": 0.0,
    "discountRateWeight": 0.52,
    "ceilingGapWeight": 0.34,
    "confidenceWeight": 0.14,
    "riskPenaltyWeight": 0.20,
    "discountRateSaturation": 0.15,
    "ceilingGapSaturation": 0.12,
    "defaultConfidence": 0.45,
}

DEFAULT_BUY_SIDE_CALIBRATION_CONFIG = {
    "pricingThresholds": {
        "referenceOnly": dict(REFERENCE_ONLY_THRESHOLDS),
        "guidanceReady": dict(GUIDANCE_READY_THRESHOLDS),
    },
    "opportunityScoring": dict(DEFAULT_BUY_SIDE_SCORING_CONFIG),
}


class BuySideCalibrationError(RuntimeError):
    pass


def default_buy_side_calibration_config() -> dict[str, Any]:
    return deepcopy(DEFAULT_BUY_SIDE_CALIBRATION_CONFIG)


def extract_buy_side_calibration_config(metadata: dict[str, Any] | None) -> dict[str, Any]:
    raw_section = dict((metadata or {}).get(BUY_SIDE_CALIBRATION_METADATA_KEY) or {})
    return _deep_merge_dicts(default_buy_side_calibration_config(), raw_section)


def resolve_buy_side_pricing_thresholds(config: dict[str, Any] | None) -> dict[str, dict[str, float | int]]:
    effective = extract_buy_side_calibration_config(
        {BUY_SIDE_CALIBRATION_METADATA_KEY: config} if _looks_like_calibration_section(config) else None
    )
    if config and not _looks_like_calibration_section(config):
        effective = _deep_merge_dicts(default_buy_side_calibration_config(), dict(config))
    thresholds = dict(effective.get("pricingThresholds") or {})
    return {
        "referenceOnly": _normalize_threshold_block(
            thresholds.get("referenceOnly"),
            fallback=REFERENCE_ONLY_THRESHOLDS,
        ),
        "guidanceReady": _normalize_threshold_block(
            thresholds.get("guidanceReady"),
            fallback=GUIDANCE_READY_THRESHOLDS,
        ),
    }


def resolve_buy_side_scoring_config(config: dict[str, Any] | None) -> dict[str, float]:
    effective = extract_buy_side_calibration_config(
        {BUY_SIDE_CALIBRATION_METADATA_KEY: config} if _looks_like_calibration_section(config) else None
    )
    if config and not _looks_like_calibration_section(config):
        effective = _deep_merge_dicts(default_buy_side_calibration_config(), dict(config))
    scoring = dict(effective.get("opportunityScoring") or {})
    return {
        key: float(scoring.get(key, value))
        for key, value in DEFAULT_BUY_SIDE_SCORING_CONFIG.items()
    }


def load_buy_side_calibration_config_with_session(
    session: Session,
    *,
    category: Category | None = None,
    category_code: str | None = None,
    category_id: str | None = None,
) -> dict[str, Any]:
    resolved_category = category or _resolve_category(
        session,
        category_code=category_code,
        category_id=category_id,
    )
    runtime_profile = _resolve_runtime_profile(
        session,
        category_id=str(resolved_category.id) if resolved_category is not None else category_id,
    )
    metadata = dict(getattr(runtime_profile, "metadata_json", {}) or {})
    effective_config = extract_buy_side_calibration_config(metadata)
    return {
        "category": resolved_category,
        "runtimeProfile": runtime_profile,
        "metadata": metadata,
        "effectiveConfig": effective_config,
    }


def upsert_buy_side_calibration_config_with_session(
    session: Session,
    *,
    category: Category,
    config_patch: dict[str, Any],
    operator_id: str,
    source: str,
    applied_recommendation_ids: list[str] | None = None,
    recommendation_snapshot: dict[str, Any] | None = None,
    window_days: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_operator_id = str(operator_id or "").strip() or "buy-calibration-bot"
    runtime_profile = _resolve_runtime_profile(session, category_id=str(category.id))
    metadata = dict(getattr(runtime_profile, "metadata_json", {}) or {})
    calibration_section = dict(metadata.get(BUY_SIDE_CALIBRATION_METADATA_KEY) or {})
    merged_section = _deep_merge_dicts(calibration_section, config_patch)
    merged_section["lastAppliedAt"] = datetime.now(UTC).isoformat()
    merged_section["lastAppliedBy"] = normalized_operator_id
    merged_section["lastApplySource"] = str(source or "").strip() or "buy_feedback_calibration"
    if applied_recommendation_ids:
        merged_section["lastAppliedRecommendationIds"] = list(dict.fromkeys(applied_recommendation_ids))
    if recommendation_snapshot:
        merged_section["lastRecommendationSnapshot"] = dict(recommendation_snapshot)
    if window_days is not None:
        merged_section["lastCalibrationWindowDays"] = max(int(window_days), 1)
    metadata[BUY_SIDE_CALIBRATION_METADATA_KEY] = merged_section

    prompt_profile = str(getattr(runtime_profile, "prompt_profile", "") or "").strip()
    if not prompt_profile:
        prompt_profile = recommended_prompt_profile_for_category(category.code) or f"{category.code}_extract_v1"
    if not prompt_profile:
        raise BuySideCalibrationError(f"promptProfile is required for category {category.code}")

    result = upsert_category_runtime_profile_with_session(
        session,
        payload={
            "categoryId": str(category.id),
            "activeTemplateId": getattr(runtime_profile, "active_template_id", None),
            "promptProfile": prompt_profile,
            "extractorProfile": getattr(runtime_profile, "extractor_profile", None),
            "validatorProfile": getattr(runtime_profile, "validator_profile", None),
            "llmProviderOverride": getattr(runtime_profile, "llm_provider_override", None),
            "llmModelOverride": getattr(runtime_profile, "llm_model_override", None),
            "status": getattr(runtime_profile, "status", None) or "ACTIVE",
            "metadata": metadata,
        },
        operator_id=normalized_operator_id,
        dry_run=dry_run,
    )
    profile = dict(result.get("profile") or {})
    return {
        "categoryCode": category.code,
        "profile": profile,
        "auditLogId": result.get("auditLogId"),
        "effectiveConfig": extract_buy_side_calibration_config(dict(profile.get("metadata") or {})),
        "appliedPatch": _deep_merge_dicts({}, config_patch),
    }


def _resolve_category(
    session: Session,
    *,
    category_code: str | None = None,
    category_id: str | None = None,
) -> Category | None:
    normalized_category_id = str(category_id or "").strip()
    normalized_category_code = str(category_code or "").strip()
    if normalized_category_id:
        return session.get(Category, normalized_category_id)
    if normalized_category_code:
        return session.execute(select(Category).where(Category.code == normalized_category_code)).scalar_one_or_none()
    return None


def _resolve_runtime_profile(session: Session, *, category_id: str | None) -> CategoryRuntimeProfile | None:
    normalized_category_id = str(category_id or "").strip()
    if not normalized_category_id:
        return None
    return session.execute(
        select(CategoryRuntimeProfile).where(CategoryRuntimeProfile.category_id == normalized_category_id)
    ).scalar_one_or_none()


def _normalize_threshold_block(
    value: Any,
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


def _looks_like_calibration_section(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return False
    return "pricingThresholds" in config or "opportunityScoring" in config


def _deep_merge_dicts(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in dict(patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_dicts(dict(result[key]), value)
            continue
        result[key] = deepcopy(value)
    return result


__all__ = [
    "BUY_SIDE_CALIBRATION_METADATA_KEY",
    "BuySideCalibrationError",
    "DEFAULT_BUY_SIDE_CALIBRATION_CONFIG",
    "DEFAULT_BUY_SIDE_SCORING_CONFIG",
    "default_buy_side_calibration_config",
    "extract_buy_side_calibration_config",
    "load_buy_side_calibration_config_with_session",
    "resolve_buy_side_pricing_thresholds",
    "resolve_buy_side_scoring_config",
    "upsert_buy_side_calibration_config_with_session",
]
