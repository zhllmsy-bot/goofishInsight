from __future__ import annotations

from datetime import datetime, timedelta
from decimal import InvalidOperation
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from goofish_analyzer.services.buy_price_baselines import (
    build_buy_price_baselines_with_session,
)
from goofish_insight.application.services.buy_side_calibration import (
    load_buy_side_calibration_config_with_session,
    resolve_buy_side_pricing_thresholds,
    resolve_buy_side_scoring_config,
    upsert_buy_side_calibration_config_with_session,
)

from goofish_analyzer.adapters import (
    resolve_category_code,
    UTC,
    session_scope,
    BuyDecisionFeedback,
    DecisionFeedbackLog,
    BuyOpportunity,
    Category,
)
from goofish_analyzer.services.buy_alerts import (
    link_buy_feedback_to_alert_candidate_with_session,
)
from goofish_analyzer.services.buy_opportunities import (
    refresh_buy_opportunities_with_session,
)
from goofish_analyzer.services.pricing_thresholds import (
    GUIDANCE_READY_THRESHOLDS,
    REFERENCE_ONLY_THRESHOLDS,
)


class BuyFeedbackError(RuntimeError):
    pass


POSITIVE_FEEDBACK_LABELS = {
    "purchased",
    "bought",
    "成交",
    "已买",
    "contacted",
    "messaged",
    "已联系",
}

REJECT_FEEDBACK_LABELS = {
    "dismissed",
    "ignored",
    "not_worth",
    "not_worth_it",
    "不值得",
    "忽略",
    "false_positive",
    "wrong_model",
    "bad_risk",
    "template_mismatch",
    "price_too_high",
    "sample_unstable",
    "trend_unreliable",
}

ENGAGEMENT_FEEDBACK_LABELS = {
    "detail_opened",
    "listing_opened",
}

REJECT_REASON_ALIASES: dict[str, set[str]] = {
    "template_mismatch": {
        "wrong_model",
        "template_mismatch",
        "模板错",
        "型号错",
    },
    "price_too_high": {
        "price_too_high",
        "not_worth",
        "not_worth_it",
        "不值得",
        "价格偏高",
    },
    "sample_unstable": {
        "sample_unstable",
        "样本不稳",
        "样本不足",
    },
    "trend_unreliable": {
        "trend_unreliable",
        "趋势不可信",
    },
    "risk_too_high": {
        "bad_risk",
        "风险太高",
    },
}

AUTO_APPLYABLE_CALIBRATION_RECOMMENDATION_IDS = {
    "threshold_buy_ceiling_margin",
    "threshold_guidance_sample_count",
    "threshold_guidance_reliability_score",
    "threshold_reference_to_guidance_canary",
    "ranking_risk_penalty_weight",
}


def record_buy_decision_feedback(
    *,
    opportunity_id: str,
    feedback_type: str,
    feedback_label: str,
    operator_id: str | None = None,
    feedback_note: str | None = None,
    purchase_price: Any = None,
    expected_resale_price: Any = None,
    link_to_alert_candidate: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = record_buy_decision_feedback_with_session(
            session,
            opportunity_id=opportunity_id,
            feedback_type=feedback_type,
            feedback_label=feedback_label,
            operator_id=operator_id,
            feedback_note=feedback_note,
            purchase_price=purchase_price,
            expected_resale_price=expected_resale_price,
            link_to_alert_candidate=link_to_alert_candidate,
        )
        if dry_run:
            session.rollback()
            result["dryRun"] = True
        return result


def record_buy_decision_feedback_with_session(
    session: Session,
    *,
    opportunity_id: str,
    feedback_type: str,
    feedback_label: str,
    operator_id: str | None = None,
    feedback_note: str | None = None,
    purchase_price: Any = None,
    expected_resale_price: Any = None,
    link_to_alert_candidate: bool = False,
) -> dict[str, Any]:
    normalized_opportunity_id = _normalize_required_string(opportunity_id, "opportunity_id")
    normalized_feedback_type = _normalize_required_string(feedback_type, "feedback_type")
    normalized_feedback_label = _normalize_required_string(feedback_label, "feedback_label")

    opportunity = session.get(BuyOpportunity, normalized_opportunity_id)
    if opportunity is None:
        raise BuyFeedbackError(f"Opportunity not found: {normalized_opportunity_id}")
    status_at_feedback = str(opportunity.status or "").strip().upper() or None
    is_engagement = is_engagement_feedback(normalized_feedback_type, normalized_feedback_label)
    feedback_action = "engage" if is_engagement else feedback_action_for_label(normalized_feedback_label)
    feedback_category = feedback_category_for_label(normalized_feedback_label)
    recorded_at = datetime.now(UTC)

    feedback = BuyDecisionFeedback(
        id=str(uuid4()),
        opportunity_id=normalized_opportunity_id,
        feedback_type=normalized_feedback_type,
        feedback_label=normalized_feedback_label,
        operator_id=_normalize_optional_string(operator_id),
        feedback_note=_normalize_optional_string(feedback_note),
        purchase_price=_optional_decimal(purchase_price),
        expected_resale_price=_optional_decimal(expected_resale_price),
        payload={
            "source": "buy_feedback.record_buy_decision_feedback",
            "feedbackAction": feedback_action,
            "feedbackCategory": feedback_category,
            "opportunityStatusAtFeedback": status_at_feedback,
            "templateMatchErrorType": _normalize_optional_string(
                dict(opportunity.payload or {}).get("templateMatchErrorType")
            ),
            "templateAvailabilityTier": _normalize_optional_string(
                dict(opportunity.payload or {}).get("templateAvailabilityTier")
            ),
            "baselineMatchLevel": _normalize_optional_string(
                dict(opportunity.payload or {}).get("baseline_match_level")
            ),
            "matchedTemplateKey": _normalize_optional_string(
                dict(opportunity.payload or {}).get("matchedTemplateKey")
            ),
        },
    )
    session.add(feedback)

    if not is_engagement:
        opportunity.decision = normalized_feedback_label
        opportunity.status = opportunity_status_for_feedback_label(normalized_feedback_label)
        opportunity.decision_note = _normalize_optional_string(feedback_note)
    _flush(session)
    linkage_result = _default_alert_candidate_linkage_result(enabled=link_to_alert_candidate)
    if (not is_engagement) and link_to_alert_candidate and feedback_action == "accept":
        linkage_result = link_buy_feedback_to_alert_candidate_with_session(
            session,
            opportunity=opportunity,
            status_at_feedback=status_at_feedback,
            linkage_source=f"buy_feedback:{feedback_action}",
        )

    feedback.payload = {
        **dict(feedback.payload or {}),
        "alertCandidateLinkage": dict(linkage_result),
    }
    summary_key = "engagementSummary" if is_engagement else "feedbackSummary"
    opportunity.payload = {
        **dict(opportunity.payload or {}),
        summary_key: {
            "feedbackAction": feedback_action,
            "feedbackCategory": feedback_category,
            "feedbackType": normalized_feedback_type,
            "feedbackLabel": normalized_feedback_label,
            "operatorId": _normalize_optional_string(operator_id),
            "feedbackNote": _normalize_optional_string(feedback_note),
            "recordedAt": recorded_at.isoformat(),
            "alertCandidateLinkage": dict(linkage_result),
        },
    }
    _flush(session)
    _record_feedback_log_with_session(
        session,
        feedback=feedback,
        opportunity=opportunity,
        feedback_action=feedback_action,
        feedback_category=feedback_category,
        opportunity_status=opportunity.status,
        operator_id=operator_id,
        recorded_at=recorded_at,
    )

    return {
        "dryRun": False,
        "feedback": serialize_buy_decision_feedback(feedback),
        "opportunity": {
            "id": opportunity.id,
            "status": opportunity.status,
            "decision": opportunity.decision,
        },
        "alertCandidateLinkage": linkage_result,
    }


def _record_feedback_log_with_session(
    session: Session,
    *,
    feedback: BuyDecisionFeedback,
    opportunity: BuyOpportunity,
    feedback_action: str,
    feedback_category: str,
    opportunity_status: str | None,
    operator_id: str | None,
    recorded_at: datetime,
) -> None:
    pricing_record = dict(dict(opportunity.payload or {}).get("pricing_record") or {})
    sample_snapshot = dict(pricing_record.get("sample_snapshot") or {})
    log_row = DecisionFeedbackLog(
        id=str(uuid4()),
        feedback_id=str(feedback.id),
        opportunity_id=str(opportunity.id),
        item_id_ref=getattr(opportunity, "item_id_ref", None),
        category_id=_normalize_optional_string(getattr(opportunity, "category_id", None)),
        scope_key=_normalize_optional_string(pricing_record.get("category_code") or pricing_record.get("business_domain")),
        model_catalog_id=_normalize_optional_string(
            getattr(opportunity, "model_catalog_id", None) or pricing_record.get("model_catalog_id")
        ),
        schema_id=_optional_int(pricing_record.get("schema_id") or sample_snapshot.get("schemaId")),
        fingerprint_hash=_normalize_optional_string(sample_snapshot.get("fingerprintHash")),
        baseline_match_level=_normalize_optional_string(dict(opportunity.payload or {}).get("baseline_match_level")),
        baseline_match_key=_normalize_optional_string(dict(opportunity.payload or {}).get("baseline_match_key")),
        feedback_type=str(feedback.feedback_type),
        feedback_label=str(feedback.feedback_label),
        feedback_action=str(feedback_action),
        feedback_category=str(feedback_category),
        opportunity_status=_normalize_optional_string(opportunity_status),
        operator_id=_normalize_optional_string(operator_id),
        recorded_at=recorded_at,
        payload={
            "pricingRecord": {
                "itemId": _normalize_optional_string(pricing_record.get("item_id")),
                "title": _normalize_optional_string(pricing_record.get("title")),
                "price": pricing_record.get("price"),
                "schemaId": pricing_record.get("schema_id") or sample_snapshot.get("schemaId"),
            },
            "sampleSnapshot": sample_snapshot,
            "feedbackPayload": dict(feedback.payload or {}),
        },
    )
    session.add(log_row)
    _flush(session)


def opportunity_status_for_feedback_label(feedback_label: str) -> str:
    normalized = normalize_feedback_label(feedback_label)
    if normalized in {"purchased", "bought", "成交", "已买"}:
        return "PURCHASED"
    if normalized in {"contacted", "messaged", "已联系"}:
        return "CONTACTED"
    if normalized in {"dismissed", "ignored", "not_worth", "not_worth_it", "不值得", "忽略"}:
        return "DISMISSED"
    if normalized in {"false_positive", "wrong_model", "bad_risk"}:
        return "REJECTED"
    return "REVIEWED"


def feedback_action_for_label(feedback_label: str) -> str:
    normalized = normalize_feedback_label(feedback_label)
    if normalized in ENGAGEMENT_FEEDBACK_LABELS:
        return "engage"
    if normalized in POSITIVE_FEEDBACK_LABELS:
        return "accept"
    if normalized in REJECT_FEEDBACK_LABELS:
        return "reject"
    return "neutral"


def feedback_category_for_label(feedback_label: str) -> str:
    normalized = normalize_feedback_label(feedback_label)
    action = feedback_action_for_label(feedback_label)
    if action == "engage":
        return f"engaged_{normalized}" if normalized else "engaged"
    if action == "accept":
        if normalized in {"purchased", "bought", "成交", "已买"}:
            return "accepted_purchased"
        if normalized in {"contacted", "messaged", "已联系"}:
            return "accepted_contacted"
        return "accepted_other"
    if action == "reject":
        for category, aliases in REJECT_REASON_ALIASES.items():
            if normalized in aliases:
                return category
        return "rejected_other"
    return "reviewed"


def normalize_feedback_label(value: Any) -> str:
    normalized = _normalize_optional_string(value)
    if not normalized:
        return ""
    return normalized.lower().replace("-", "_").replace(" ", "_")


def is_engagement_feedback(feedback_type: Any, feedback_label: Any) -> bool:
    normalized_type = normalize_feedback_label(feedback_type)
    normalized_label = normalize_feedback_label(feedback_label)
    return normalized_type == "engagement" or normalized_label in ENGAGEMENT_FEEDBACK_LABELS


def summarize_buy_feedback_quality(
    *,
    category_code: str | None = None,
    window_days: int = 30,
) -> dict[str, Any]:
    with session_scope() as session:
        return summarize_buy_feedback_quality_with_session(
            session,
            category_code=category_code,
            window_days=window_days,
        )


def summarize_buy_feedback_calibration(
    *,
    category_code: str | None = None,
    window_days: int = 30,
) -> dict[str, Any]:
    with session_scope() as session:
        return summarize_buy_feedback_calibration_with_session(
            session,
            category_code=category_code,
            window_days=window_days,
        )


def summarize_buy_feedback_calibration_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    window_days: int = 30,
) -> dict[str, Any]:
    category = _resolve_optional_category(session, category_code=category_code)
    quality = summarize_buy_feedback_quality_with_session(
        session,
        category_code=category.code if category is not None else category_code,
        window_days=window_days,
    )
    calibration_state = load_buy_side_calibration_config_with_session(
        session,
        category=category,
    )
    recommendations = build_feedback_calibration_recommendations(
        quality,
        pricing_thresholds=resolve_buy_side_pricing_thresholds(calibration_state.get("effectiveConfig")),
        scoring_config=resolve_buy_side_scoring_config(calibration_state.get("effectiveConfig")),
    )
    return {
        "categoryCode": quality.get("categoryCode"),
        "windowDays": quality.get("windowDays"),
        "asOf": quality.get("asOf"),
        "qualitySnapshot": {
            "opportunityCount": quality.get("opportunityCount", 0),
            "feedbackCount": quality.get("feedbackCount", 0),
            "acceptCount": quality.get("acceptCount", 0),
            "rejectCount": quality.get("rejectCount", 0),
        },
        "effectiveCalibrationConfig": calibration_state.get("effectiveConfig"),
        "recommendations": recommendations,
    }


def apply_buy_feedback_calibration(
    *,
    category_code: str,
    window_days: int = 30,
    operator_id: str | None = None,
    recommendation_ids: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = apply_buy_feedback_calibration_with_session(
            session,
            category_code=category_code,
            window_days=window_days,
            operator_id=operator_id,
            recommendation_ids=recommendation_ids,
        )
        if dry_run:
            session.rollback()
            result["dryRun"] = True
        return result


def apply_buy_feedback_calibration_with_session(
    session: Session,
    *,
    category_code: str,
    window_days: int = 30,
    operator_id: str | None = None,
    recommendation_ids: list[str] | None = None,
) -> dict[str, Any]:
    category = _resolve_optional_category(session, category_code=category_code)
    if category is None:
        raise BuyFeedbackError("category_code is required.")

    calibration = summarize_buy_feedback_calibration_with_session(
        session,
        category_code=category.code,
        window_days=window_days,
    )
    recommendations_payload = dict(calibration.get("recommendations") or {})
    available_recommendations = _flatten_calibration_recommendations(recommendations_payload)
    requested_ids = _normalize_recommendation_ids(recommendation_ids)
    selected_recommendations = [
        recommendation
        for recommendation in available_recommendations
        if not requested_ids or str(recommendation.get("id") or "") in requested_ids
    ]

    skipped_recommendations: list[dict[str, Any]] = []
    if requested_ids:
        known_ids = {str(recommendation.get("id") or "") for recommendation in available_recommendations}
        for missing_id in sorted(requested_ids - known_ids):
            skipped_recommendations.append(
                {
                    "id": missing_id,
                    "title": missing_id,
                    "reason": "recommendation_not_found",
                }
            )

    config_patch: dict[str, Any] = {}
    applied_recommendations: list[dict[str, Any]] = []
    for recommendation in selected_recommendations:
        recommendation_id = str(recommendation.get("id") or "")
        if recommendation_id not in AUTO_APPLYABLE_CALIBRATION_RECOMMENDATION_IDS:
            skipped_recommendations.append(
                {
                    "id": recommendation_id,
                    "title": recommendation.get("title"),
                    "reason": "manual_only",
                }
            )
            continue
        recommendation_patch = _build_calibration_patch_for_recommendation(recommendation)
        if not recommendation_patch:
            skipped_recommendations.append(
                {
                    "id": recommendation_id,
                    "title": recommendation.get("title"),
                    "reason": "no_effective_patch",
                }
            )
            continue
        config_patch = _merge_dicts(config_patch, recommendation_patch)
        applied_recommendations.append(
            {
                "id": recommendation_id,
                "title": recommendation.get("title"),
                "summary": recommendation.get("summary"),
                "recommendedAction": recommendation.get("recommendedAction"),
                "evidence": dict(recommendation.get("evidence") or {}),
            }
        )

    effective_config = dict(calibration.get("effectiveCalibrationConfig") or {})
    if not applied_recommendations:
        return {
            "dryRun": False,
            "categoryCode": category.code,
            "windowDays": max(int(window_days), 1),
            "effectiveCalibrationConfig": effective_config,
            "appliedRecommendationCount": 0,
            "skippedRecommendationCount": len(skipped_recommendations),
            "appliedRecommendations": applied_recommendations,
            "skippedRecommendations": skipped_recommendations,
            "baselineRebuild": None,
            "opportunityRefresh": None,
        }

    upsert_result = upsert_buy_side_calibration_config_with_session(
        session,
        category=category,
        config_patch=config_patch,
        operator_id=_normalize_optional_string(operator_id) or "buy-feedback-calibration",
        source="buy_feedback_calibration_apply",
        applied_recommendation_ids=[str(item.get("id") or "") for item in applied_recommendations],
        recommendation_snapshot={
            "windowDays": max(int(window_days), 1),
            "appliedRecommendationIds": [str(item.get("id") or "") for item in applied_recommendations],
            "skippedRecommendationIds": [str(item.get("id") or "") for item in skipped_recommendations],
        },
        window_days=window_days,
        dry_run=False,
    )
    baseline_rebuild = build_buy_price_baselines_with_session(
        session,
        category_code=category.code,
        view="all",
    )
    opportunity_refresh = refresh_buy_opportunities_with_session(
        session,
        category_code=category.code,
    )
    return {
        "dryRun": False,
        "categoryCode": category.code,
        "windowDays": max(int(window_days), 1),
        "effectiveCalibrationConfig": upsert_result.get("effectiveConfig"),
        "appliedRecommendationCount": len(applied_recommendations),
        "skippedRecommendationCount": len(skipped_recommendations),
        "appliedRecommendations": applied_recommendations,
        "skippedRecommendations": skipped_recommendations,
        "calibrationProfile": upsert_result.get("profile"),
        "baselineRebuild": baseline_rebuild,
        "opportunityRefresh": opportunity_refresh,
    }


def build_feedback_calibration_recommendations(
    quality: dict[str, Any],
    *,
    pricing_thresholds: dict[str, dict[str, float | int]] | None = None,
    scoring_config: dict[str, float] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    template_field_recommendations = _build_template_field_recommendations(quality)
    threshold_recommendations = _build_threshold_recommendations(
        quality,
        pricing_thresholds=pricing_thresholds,
        scoring_config=scoring_config,
    )
    ranking_recommendations = _build_ranking_recommendations(
        quality,
        scoring_config=scoring_config,
    )
    return {
        "templateFieldRecommendations": template_field_recommendations,
        "thresholdRecommendations": threshold_recommendations,
        "rankingRecommendations": ranking_recommendations,
        "totalRecommendationCount": (
            len(template_field_recommendations) + len(threshold_recommendations) + len(ranking_recommendations)
        ),
        "autoApplicableRecommendationCount": len(
            [
                recommendation
                for recommendation in (
                    threshold_recommendations + ranking_recommendations
                )
                if str(recommendation.get("id") or "") in AUTO_APPLYABLE_CALIBRATION_RECOMMENDATION_IDS
            ]
        ),
    }


def summarize_buy_feedback_quality_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    window_days: int = 30,
) -> dict[str, Any]:
    category = _resolve_optional_category(session, category_code=category_code)
    cutoff = datetime.now(UTC) - timedelta(days=max(int(window_days), 1))
    opportunity_stmt = select(BuyOpportunity).where(BuyOpportunity.last_detected_at >= cutoff)
    if category is not None:
        opportunity_stmt = opportunity_stmt.where(BuyOpportunity.category_id == str(category.id))
    opportunities = list(session.execute(opportunity_stmt).scalars().all())
    opportunity_ids = [str(row.id) for row in opportunities]
    opportunities_by_id = {
        str(row.id): {
            "status": str(row.status or "").strip().upper(),
            "tier": _normalize_optional_string(dict(row.payload or {}).get("templateAvailabilityTier")) or "unknown",
            "baselineMatchLevel": _normalize_optional_string(dict(row.payload or {}).get("baseline_match_level")),
            "matchedTemplateKey": _normalize_optional_string(dict(row.payload or {}).get("matchedTemplateKey")),
            "templateMatchErrorType": _normalize_optional_string(
                dict(row.payload or {}).get("templateMatchErrorType")
            ),
            "missingRequiredFields": _normalize_string_list(
                dict(
                    dict(row.payload or {}).get("specContract")
                    or dict(dict(row.payload or {}).get("pricing_record") or {}).get("spec_contract")
                    or {}
                ).get("missingRequiredFields")
                or []
            ),
            "riskScore": _optional_float(row.risk_score),
            "opportunityScore": _optional_float(row.opportunity_score),
            "discountRate": _optional_float(row.discount_rate),
            "currentPrice": _optional_float(row.current_price),
            "buyCeiling": _optional_float(row.buy_ceiling),
        }
        for row in opportunities
    }

    tier_stats: dict[str, dict[str, Any]] = {}
    template_match_error_counts: dict[str, int] = {}
    decision_score_sums = {
        "accept": {
            "count": 0,
            "riskScoreSum": 0.0,
            "riskScoreCount": 0,
            "opportunityScoreSum": 0.0,
            "opportunityScoreCount": 0,
            "discountRateSum": 0.0,
            "discountRateCount": 0,
            "buyCeilingGapSum": 0.0,
            "buyCeilingGapCount": 0,
        },
        "reject": {
            "count": 0,
            "riskScoreSum": 0.0,
            "riskScoreCount": 0,
            "opportunityScoreSum": 0.0,
            "opportunityScoreCount": 0,
            "discountRateSum": 0.0,
            "discountRateCount": 0,
            "buyCeilingGapSum": 0.0,
            "buyCeilingGapCount": 0,
        },
    }
    for context in opportunities_by_id.values():
        tier = context["tier"]
        stats = tier_stats.setdefault(
            tier,
            {
                "opportunityCount": 0,
                "feedbackCount": 0,
                "acceptCount": 0,
                "rejectCount": 0,
                "neutralCount": 0,
            },
        )
        stats["opportunityCount"] += 1
        error_type = context.get("templateMatchErrorType")
        if error_type:
            template_match_error_counts[error_type] = template_match_error_counts.get(error_type, 0) + 1

    feedback_rows: list[BuyDecisionFeedback] = []
    if opportunity_ids:
        feedback_rows = list(
            session.execute(
                select(BuyDecisionFeedback)
                .where(BuyDecisionFeedback.opportunity_id.in_(opportunity_ids))
                .where(BuyDecisionFeedback.created_at >= cutoff)
            )
            .scalars()
            .all()
        )

    reject_reason_counts: dict[str, int] = {}
    reject_reason_by_tier_counts: dict[str, dict[str, int]] = {}
    accepted_baseline_match_counts: dict[str, int] = {}
    template_mismatch_missing_field_counts: dict[str, int] = {}
    accepted_with_template_key_count = 0
    accepted_without_template_key_count = 0
    for row in feedback_rows:
        context = opportunities_by_id.get(str(row.opportunity_id))
        if context is None:
            continue
        payload = dict(row.payload or {})
        action = _normalize_optional_string(payload.get("feedbackAction")) or feedback_action_for_label(row.feedback_label)
        if action == "engage" or is_engagement_feedback(row.feedback_type, row.feedback_label):
            continue
        category_label = _normalize_optional_string(payload.get("feedbackCategory")) or feedback_category_for_label(
            row.feedback_label
        )
        tier = context["tier"]
        stats = tier_stats.setdefault(
            tier,
            {
                "opportunityCount": 0,
                "feedbackCount": 0,
                "acceptCount": 0,
                "rejectCount": 0,
                "neutralCount": 0,
            },
        )
        stats["feedbackCount"] += 1
        if action == "accept":
            stats["acceptCount"] += 1
            _apply_decision_score_sums(decision_score_sums["accept"], context=context)
            if context.get("matchedTemplateKey"):
                accepted_with_template_key_count += 1
            else:
                accepted_without_template_key_count += 1
            baseline_match_level = context.get("baselineMatchLevel") or "unknown"
            accepted_baseline_match_counts[baseline_match_level] = (
                accepted_baseline_match_counts.get(baseline_match_level, 0) + 1
            )
        elif action == "reject":
            stats["rejectCount"] += 1
            _apply_decision_score_sums(decision_score_sums["reject"], context=context)
            reject_reason_counts[category_label] = reject_reason_counts.get(category_label, 0) + 1
            per_tier_reasons = reject_reason_by_tier_counts.setdefault(tier, {})
            per_tier_reasons[category_label] = per_tier_reasons.get(category_label, 0) + 1
            if category_label == "template_mismatch":
                for field in context.get("missingRequiredFields") or []:
                    template_mismatch_missing_field_counts[field] = (
                        template_mismatch_missing_field_counts.get(field, 0) + 1
                    )
        else:
            stats["neutralCount"] += 1

    for stats in tier_stats.values():
        decided = int(stats.get("acceptCount") or 0) + int(stats.get("rejectCount") or 0)
        stats["decisionCount"] = decided
        stats["acceptanceRate"] = round((stats["acceptCount"] / decided), 4) if decided else 0.0
        stats["feedbackCoverageRate"] = (
            round((stats["feedbackCount"] / stats["opportunityCount"]), 4)
            if stats["opportunityCount"]
            else 0.0
        )

    feedback_count = sum(int(stats.get("feedbackCount") or 0) for stats in tier_stats.values())
    accepted_count = sum(int(stats.get("acceptCount") or 0) for stats in tier_stats.values())
    rejected_count = sum(int(stats.get("rejectCount") or 0) for stats in tier_stats.values())
    decision_score_stats = {
        action: _finalize_decision_score_stats(sums)
        for action, sums in decision_score_sums.items()
    }

    return {
        "categoryCode": category.code if category is not None else None,
        "windowDays": max(int(window_days), 1),
        "asOf": datetime.now(UTC).isoformat(),
        "opportunityCount": len(opportunities_by_id),
        "feedbackCount": feedback_count,
        "acceptCount": accepted_count,
        "rejectCount": rejected_count,
        "tierStats": tier_stats,
        "templateMatchErrorCounts": dict(
            sorted(template_match_error_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "rejectReasonCounts": dict(
            sorted(reject_reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "rejectReasonByTierCounts": {
            tier: dict(sorted(reason_counts.items(), key=lambda item: (-item[1], item[0])))
            for tier, reason_counts in sorted(reject_reason_by_tier_counts.items(), key=lambda item: item[0])
        },
        "templateMismatchMissingFieldCounts": dict(
            sorted(template_mismatch_missing_field_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "decisionScoreStats": decision_score_stats,
        "acceptedTemplateHit": {
            "acceptedCount": accepted_count,
            "acceptedWithTemplateKeyCount": accepted_with_template_key_count,
            "acceptedWithoutTemplateKeyCount": accepted_without_template_key_count,
            "acceptedWithTemplateKeyRate": (
                round((accepted_with_template_key_count / accepted_count), 4)
                if accepted_count
                else 0.0
            ),
            "acceptedBaselineMatchCounts": dict(
                sorted(accepted_baseline_match_counts.items(), key=lambda item: (-item[1], item[0]))
            ),
        },
    }


def serialize_buy_decision_feedback(row: BuyDecisionFeedback) -> dict[str, Any]:
    return {
        "id": row.id,
        "opportunityId": row.opportunity_id,
        "feedbackType": row.feedback_type,
        "feedbackLabel": row.feedback_label,
        "operatorId": row.operator_id,
        "feedbackNote": row.feedback_note,
        "purchasePrice": _decimal_to_float(row.purchase_price),
        "expectedResalePrice": _decimal_to_float(row.expected_resale_price),
        "payload": dict(row.payload or {}),
    }


def _normalize_required_string(value: Any, field_name: str) -> str:
    normalized = _normalize_optional_string(value)
    if not normalized:
        raise BuyFeedbackError(f"{field_name} is required.")
    return normalized


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BuyFeedbackError(f"Invalid decimal value: {value}") from exc


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _normalize_string_list(values: Any) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        text = _normalize_optional_string(value)
        if text:
            normalized.append(text)
    # Keep order stable while removing duplicates.
    return list(dict.fromkeys(normalized))


def _apply_decision_score_sums(sums: dict[str, Any], *, context: dict[str, Any]) -> None:
    sums["count"] += 1
    risk_score = _optional_float(context.get("riskScore"))
    if risk_score is not None:
        sums["riskScoreSum"] += risk_score
        sums["riskScoreCount"] += 1
    opportunity_score = _optional_float(context.get("opportunityScore"))
    if opportunity_score is not None:
        sums["opportunityScoreSum"] += opportunity_score
        sums["opportunityScoreCount"] += 1
    discount_rate = _optional_float(context.get("discountRate"))
    if discount_rate is not None:
        sums["discountRateSum"] += discount_rate
        sums["discountRateCount"] += 1
    current_price = _optional_float(context.get("currentPrice"))
    buy_ceiling = _optional_float(context.get("buyCeiling"))
    if current_price is not None and buy_ceiling is not None and buy_ceiling > 0:
        sums["buyCeilingGapSum"] += (current_price - buy_ceiling) / buy_ceiling
        sums["buyCeilingGapCount"] += 1


def _finalize_decision_score_stats(sums: dict[str, Any]) -> dict[str, Any]:
    risk_score_count = int(sums.get("riskScoreCount") or 0)
    opportunity_score_count = int(sums.get("opportunityScoreCount") or 0)
    discount_rate_count = int(sums.get("discountRateCount") or 0)
    buy_ceiling_gap_count = int(sums.get("buyCeilingGapCount") or 0)
    return {
        "count": int(sums.get("count") or 0),
        "avgRiskScore": round(float(sums["riskScoreSum"] / risk_score_count), 4) if risk_score_count else None,
        "avgOpportunityScore": (
            round(float(sums["opportunityScoreSum"] / opportunity_score_count), 4)
            if opportunity_score_count
            else None
        ),
        "avgDiscountRate": (
            round(float(sums["discountRateSum"] / discount_rate_count), 6) if discount_rate_count else None
        ),
        "avgBuyCeilingGapRate": (
            round(float(sums["buyCeilingGapSum"] / buy_ceiling_gap_count), 6) if buy_ceiling_gap_count else None
        ),
    }


def _build_template_field_recommendations(quality: dict[str, Any]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    opportunity_count = int(quality.get("opportunityCount") or 0)
    template_error_counts = dict(quality.get("templateMatchErrorCounts") or {})

    missing_template_key_count = int(template_error_counts.get("missing_template_key") or 0)
    if opportunity_count and missing_template_key_count:
        miss_rate = missing_template_key_count / opportunity_count
        if missing_template_key_count >= 10 or miss_rate >= 0.08:
            recommendations.append(
                {
                    "id": "template_key_coverage",
                    "priority": "high" if miss_rate >= 0.15 else "medium",
                    "title": "补齐模板键覆盖",
                    "summary": f"缺失模板键 {missing_template_key_count} 条，占机会池 {miss_rate * 100:.1f}%。",
                    "recommendedAction": "优先补齐规格抽取链路与模板键拼接映射，减少 missing_template_key。",
                    "evidence": {
                        "missingTemplateKeyCount": missing_template_key_count,
                        "opportunityCount": opportunity_count,
                        "missingTemplateKeyRate": round(miss_rate, 4),
                    },
                }
            )

    degraded_count = int(template_error_counts.get("degraded_product_match") or 0) + int(
        template_error_counts.get("degraded_brand_match") or 0
    )
    if opportunity_count and degraded_count:
        degraded_rate = degraded_count / opportunity_count
        if degraded_count >= 8 or degraded_rate >= 0.06:
            recommendations.append(
                {
                    "id": "degraded_match_rate",
                    "priority": "medium" if degraded_rate < 0.15 else "high",
                    "title": "减少降级匹配",
                    "summary": f"模板降级匹配 {degraded_count} 条，占机会池 {degraded_rate * 100:.1f}%。",
                    "recommendedAction": "检查模型别名和 selector 映射，优先命中 template 级 baseline。",
                    "evidence": {
                        "degradedCount": degraded_count,
                        "opportunityCount": opportunity_count,
                        "degradedRate": round(degraded_rate, 4),
                    },
                }
            )

    field_counts = dict(quality.get("templateMismatchMissingFieldCounts") or {})
    template_mismatch_reject_count = int(dict(quality.get("rejectReasonCounts") or {}).get("template_mismatch") or 0)
    if template_mismatch_reject_count:
        for field, count in list(field_counts.items())[:5]:
            count_int = int(count or 0)
            if count_int < 2:
                continue
            share = count_int / template_mismatch_reject_count
            if share < 0.2:
                continue
            recommendations.append(
                {
                    "id": f"template_field_{field}",
                    "priority": "high" if share >= 0.45 else "medium",
                    "title": f"评估字段 `{field}` 的模板地位",
                    "summary": (
                        f"在模板错拒绝中，`{field}` 缺失出现 {count_int}/{template_mismatch_reject_count} "
                        f"（{share * 100:.1f}%）。"
                    ),
                    "recommendedAction": "评估是否升为 requiredPricingFields，或增加针对该字段的抽取规则。",
                    "evidence": {
                        "field": field,
                        "missingCount": count_int,
                        "templateMismatchRejectCount": template_mismatch_reject_count,
                        "share": round(share, 4),
                    },
                }
            )

    return recommendations


def _build_threshold_recommendations(
    quality: dict[str, Any],
    *,
    pricing_thresholds: dict[str, dict[str, float | int]] | None = None,
    scoring_config: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    effective_thresholds = pricing_thresholds or {
        "referenceOnly": dict(REFERENCE_ONLY_THRESHOLDS),
        "guidanceReady": dict(GUIDANCE_READY_THRESHOLDS),
    }
    reference_thresholds = dict(effective_thresholds.get("referenceOnly") or REFERENCE_ONLY_THRESHOLDS)
    guidance_thresholds = dict(effective_thresholds.get("guidanceReady") or GUIDANCE_READY_THRESHOLDS)
    effective_scoring = dict(scoring_config or {})
    current_tighten_pct = float(effective_scoring.get("buyCeilingTightenPct") or 0.0)
    tier_stats = dict(quality.get("tierStats") or {})
    reject_reason_by_tier = dict(quality.get("rejectReasonByTierCounts") or {})
    guidance_stats = dict(tier_stats.get("guidance_ready") or {})
    guidance_decisions = int(guidance_stats.get("decisionCount") or 0)
    guidance_reject_reasons = dict(reject_reason_by_tier.get("guidance_ready") or {})

    if guidance_decisions >= 6:
        price_reject_count = int(guidance_reject_reasons.get("price_too_high") or 0)
        if price_reject_count:
            price_reject_rate = price_reject_count / guidance_decisions
            if price_reject_rate >= 0.3:
                additional_tighten_pct = round(min(8.0, max(2.0, price_reject_rate * 10.0)), 1)
                suggested_tighten_pct = round(min(15.0, current_tighten_pct + additional_tighten_pct), 1)
                if suggested_tighten_pct > current_tighten_pct:
                    recommendations.append(
                        {
                            "id": "threshold_buy_ceiling_margin",
                            "priority": "high" if price_reject_rate >= 0.45 else "medium",
                            "title": "收紧指导价买入线",
                            "summary": (
                                f"`guidance_ready` 决策中，价格偏高拒绝 {price_reject_count}/{guidance_decisions} "
                                f"（{price_reject_rate * 100:.1f}%）。"
                            ),
                            "recommendedAction": (
                                "建议将 buy ceiling 安全边际由 "
                                f"{current_tighten_pct:.1f}% 提高到 {suggested_tighten_pct:.1f}% 做灰度验证。"
                            ),
                            "evidence": {
                                "priceTooHighRejectCount": price_reject_count,
                                "guidanceDecisionCount": guidance_decisions,
                                "priceTooHighRejectRate": round(price_reject_rate, 4),
                                "currentTightenPct": round(current_tighten_pct, 1),
                                "suggestedTightenPct": suggested_tighten_pct,
                            },
                        }
                    )

        sample_unstable_count = int(guidance_reject_reasons.get("sample_unstable") or 0)
        sample_unstable_rate = sample_unstable_count / guidance_decisions if guidance_decisions else 0.0
        if sample_unstable_rate >= 0.2:
            current_sample_threshold = int(guidance_thresholds["seller_sample_count"])
            suggested_sample_threshold = current_sample_threshold + 1
            recommendations.append(
                {
                    "id": "threshold_guidance_sample_count",
                    "priority": "medium",
                    "title": "提高 guidance 样本门槛",
                    "summary": (
                        f"`guidance_ready` 决策中，样本不稳拒绝 {sample_unstable_count}/{guidance_decisions} "
                        f"（{sample_unstable_rate * 100:.1f}%）。"
                    ),
                    "recommendedAction": (
                        "建议将 guidance 卖家样本阈值由 "
                        f"{current_sample_threshold} 提高到 "
                        f"{suggested_sample_threshold}。"
                    ),
                    "evidence": {
                        "sampleUnstableRejectCount": sample_unstable_count,
                        "guidanceDecisionCount": guidance_decisions,
                        "sampleUnstableRejectRate": round(sample_unstable_rate, 4),
                        "currentThreshold": current_sample_threshold,
                        "suggestedThreshold": suggested_sample_threshold,
                    },
                }
            )

        trend_unreliable_count = int(guidance_reject_reasons.get("trend_unreliable") or 0)
        trend_unreliable_rate = trend_unreliable_count / guidance_decisions if guidance_decisions else 0.0
        if trend_unreliable_rate >= 0.15:
            current_reliability_threshold = float(guidance_thresholds["reliability_score"])
            suggested_reliability_threshold = current_reliability_threshold + 5.0
            recommendations.append(
                {
                    "id": "threshold_guidance_reliability_score",
                    "priority": "medium",
                    "title": "提高趋势可靠度门槛",
                    "summary": (
                        f"`guidance_ready` 决策中，趋势不可信拒绝 {trend_unreliable_count}/{guidance_decisions} "
                        f"（{trend_unreliable_rate * 100:.1f}%）。"
                    ),
                    "recommendedAction": (
                        "建议将 guidance 可靠度阈值由 "
                        f"{current_reliability_threshold:.0f} 提高到 "
                        f"{suggested_reliability_threshold:.0f}。"
                    ),
                    "evidence": {
                        "trendUnreliableRejectCount": trend_unreliable_count,
                        "guidanceDecisionCount": guidance_decisions,
                        "trendUnreliableRejectRate": round(trend_unreliable_rate, 4),
                        "currentThreshold": current_reliability_threshold,
                        "suggestedThreshold": suggested_reliability_threshold,
                    },
                }
            )

    reference_stats = dict(tier_stats.get("reference_only") or {})
    reference_decisions = int(reference_stats.get("decisionCount") or 0)
    reference_accept_rate = float(reference_stats.get("acceptanceRate") or 0.0)
    reference_reject_reasons = dict(reject_reason_by_tier.get("reference_only") or {})
    reference_unstable_count = int(reference_reject_reasons.get("sample_unstable") or 0) + int(
        reference_reject_reasons.get("trend_unreliable") or 0
    )
    reference_unstable_rate = reference_unstable_count / reference_decisions if reference_decisions else 0.0
    if reference_decisions >= 8 and reference_accept_rate >= 0.65 and reference_unstable_rate < 0.15:
        current_exact_ratio_threshold = float(guidance_thresholds["exact_spec_ratio"])
        suggested_exact_ratio_threshold = float(
            max(
                float(reference_thresholds["exact_spec_ratio"]),
                current_exact_ratio_threshold - 0.05,
            )
        )
        if suggested_exact_ratio_threshold < current_exact_ratio_threshold:
            recommendations.append(
                {
                    "id": "threshold_reference_to_guidance_canary",
                    "priority": "low",
                    "title": "评估放宽 guidance 过渡阈值",
                    "summary": (
                        f"`reference_only` 采纳率 {reference_accept_rate * 100:.1f}%（决策 {reference_decisions} 条），"
                        "说明有部分可提前升级到指导价灰度池。"
                    ),
                    "recommendedAction": (
                        "建议小流量试验：将 guidance exact_spec_ratio 从 "
                        f"{current_exact_ratio_threshold:.2f} 下调至 "
                        f"{suggested_exact_ratio_threshold:.2f}，"
                        "并保持 alert 严格门控。"
                    ),
                    "evidence": {
                        "referenceDecisionCount": reference_decisions,
                        "referenceAcceptanceRate": round(reference_accept_rate, 4),
                        "referenceUnstableRejectRate": round(reference_unstable_rate, 4),
                        "currentThreshold": current_exact_ratio_threshold,
                        "suggestedThreshold": suggested_exact_ratio_threshold,
                    },
                }
            )

    return recommendations


def _build_ranking_recommendations(
    quality: dict[str, Any],
    *,
    scoring_config: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    current_penalty_weight = float(dict(scoring_config or {}).get("riskPenaltyWeight") or 0.20)
    decision_stats = dict(quality.get("decisionScoreStats") or {})
    accept_stats = dict(decision_stats.get("accept") or {})
    reject_stats = dict(decision_stats.get("reject") or {})
    accept_count = int(accept_stats.get("count") or 0)
    reject_count = int(reject_stats.get("count") or 0)
    accept_risk = _optional_float(accept_stats.get("avgRiskScore"))
    reject_risk = _optional_float(reject_stats.get("avgRiskScore"))
    reject_reason_counts = dict(quality.get("rejectReasonCounts") or {})
    risk_reject_count = int(reject_reason_counts.get("risk_too_high") or 0)

    if accept_count >= 5 and reject_count >= 5 and accept_risk is not None and reject_risk is not None:
        risk_gap = reject_risk - accept_risk
        if risk_reject_count >= 3 or risk_gap >= 6:
            suggested_weight = max(current_penalty_weight, 0.30 if risk_gap >= 10 else 0.25)
            if suggested_weight > current_penalty_weight:
                recommendations.append(
                    {
                        "id": "ranking_risk_penalty_weight",
                        "priority": "medium",
                        "title": "提高机会排序中的风险惩罚权重",
                        "summary": (
                            f"拒绝机会平均风险分 {reject_risk:.2f}，采纳机会 {accept_risk:.2f}，差值 {risk_gap:.2f}。"
                        ),
                        "recommendedAction": (
                            "建议把机会分中 risk penalty 系数从 "
                            f"{current_penalty_weight:.2f} 提高到 {suggested_weight:.2f}，让高风险机会更靠后。"
                        ),
                        "evidence": {
                            "acceptCount": accept_count,
                            "rejectCount": reject_count,
                            "acceptAvgRiskScore": round(accept_risk, 4),
                            "rejectAvgRiskScore": round(reject_risk, 4),
                            "riskGap": round(risk_gap, 4),
                            "riskTooHighRejectCount": risk_reject_count,
                            "currentPenaltyWeight": current_penalty_weight,
                            "suggestedPenaltyWeight": suggested_weight,
                        },
                    }
                )

    return recommendations


def _flatten_calibration_recommendations(recommendations: dict[str, Any]) -> list[dict[str, Any]]:
    ordered_sections = (
        recommendations.get("templateFieldRecommendations") or [],
        recommendations.get("thresholdRecommendations") or [],
        recommendations.get("rankingRecommendations") or [],
    )
    return [dict(entry or {}) for section in ordered_sections for entry in section]


def _normalize_recommendation_ids(values: list[str] | None) -> set[str]:
    normalized: set[str] = set()
    for value in values or []:
        text = _normalize_optional_string(value)
        if text:
            normalized.add(text)
    return normalized


def _build_calibration_patch_for_recommendation(recommendation: dict[str, Any]) -> dict[str, Any]:
    recommendation_id = str(recommendation.get("id") or "")
    evidence = dict(recommendation.get("evidence") or {})
    if recommendation_id == "threshold_buy_ceiling_margin":
        return {
            "opportunityScoring": {
                "buyCeilingTightenPct": float(evidence.get("suggestedTightenPct") or 0.0),
            }
        }
    if recommendation_id == "threshold_guidance_sample_count":
        return {
            "pricingThresholds": {
                "guidanceReady": {
                    "seller_sample_count": int(evidence.get("suggestedThreshold") or 0),
                }
            }
        }
    if recommendation_id == "threshold_guidance_reliability_score":
        return {
            "pricingThresholds": {
                "guidanceReady": {
                    "reliability_score": float(evidence.get("suggestedThreshold") or 0.0),
                }
            }
        }
    if recommendation_id == "threshold_reference_to_guidance_canary":
        return {
            "pricingThresholds": {
                "guidanceReady": {
                    "exact_spec_ratio": float(evidence.get("suggestedThreshold") or 0.0),
                }
            }
        }
    if recommendation_id == "ranking_risk_penalty_weight":
        return {
            "opportunityScoring": {
                "riskPenaltyWeight": float(evidence.get("suggestedPenaltyWeight") or 0.0),
            }
        }
    return {}


def _merge_dicts(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in dict(patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(dict(merged[key]), value)
            continue
        merged[key] = value
    return merged


def _flush(session: Session) -> None:
    flush = getattr(session, "flush", None)
    if callable(flush):
        flush()


def _default_alert_candidate_linkage_result(*, enabled: bool) -> dict[str, Any]:
    if enabled:
        return {
            "status": "skipped",
            "reason": "feedback_not_positive",
            "channel": "dashboard",
            "alertEventId": None,
        }
    return {
        "status": "disabled",
        "reason": "linkage_not_requested",
        "channel": "dashboard",
        "alertEventId": None,
    }


def _resolve_optional_category(session: Session, *, category_code: str | None) -> Category | None:
    normalized = _normalize_optional_string(category_code)
    if not normalized:
        return None
    resolved = resolve_category_code(normalized)
    row = session.execute(select(Category).where(Category.code == resolved)).scalar_one_or_none()
    if row is None:
        raise BuyFeedbackError(f"Category not found: {resolved}")
    return row
