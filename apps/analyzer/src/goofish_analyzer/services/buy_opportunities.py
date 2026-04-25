from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from goofish_insight.application.services.buy_side_calibration import (
    DEFAULT_BUY_SIDE_SCORING_CONFIG,
    load_buy_side_calibration_config_with_session,
    resolve_buy_side_scoring_config,
)

from goofish_analyzer.adapters import (
    build_pricing_record_template_snapshot,
    is_price_template_opportunity_enabled,
    resolve_category_code,
    UTC,
    session_scope,
    BuyOpportunity,
    BuyAlertEvent,
    BuyDecisionFeedback,
    BuyOpportunityRisk,
    BuyPriceBaseline,
    BuyWatchTarget,
    Category,
    Item,
    ItemIngestRejection,
    load_pricing_records,
)


class BuyOpportunityError(RuntimeError):
    pass


def refresh_buy_opportunities(
    *,
    category_code: str | None = None,
    business_domain: str | None = None,
    freshness_days: int = 30,
    baseline_date: date | None = None,
    min_discount_rate: float = 0.02,
    min_opportunity_score: float = 35.0,
    limit: int | None = None,
    ensure_default_target: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = refresh_buy_opportunities_with_session(
            session,
            category_code=category_code,
            business_domain=business_domain,
            freshness_days=freshness_days,
            baseline_date=baseline_date,
            min_discount_rate=min_discount_rate,
            min_opportunity_score=min_opportunity_score,
            limit=limit,
            ensure_default_target=ensure_default_target,
        )
        if dry_run:
            session.rollback()
            result["dryRun"] = True
        return result


def refresh_buy_opportunities_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    business_domain: str | None = None,
    freshness_days: int = 30,
    baseline_date: date | None = None,
    min_discount_rate: float = 0.02,
    min_opportunity_score: float = 35.0,
    limit: int | None = None,
    ensure_default_target: bool = True,
) -> dict[str, Any]:
    normalized_category_code = _resolve_requested_category_code(
        category_code=category_code,
        business_domain=business_domain,
    )
    category = _resolve_category(session, category_code=normalized_category_code)
    if category is None:
        raise BuyOpportunityError(f"Category not found: {normalized_category_code}")
    calibration_state = load_buy_side_calibration_config_with_session(
        session,
        category=category,
    )
    scoring_config = resolve_buy_side_scoring_config(calibration_state.get("effectiveConfig"))

    watch_targets = _load_watch_targets(session, category_id=str(category.id))
    if not watch_targets and ensure_default_target:
        watch_targets = [ensure_default_watch_target_with_session(session, category=category)]
        _flush(session)
    if not watch_targets:
        return {
            "dryRun": False,
            "categoryCode": normalized_category_code,
            "candidateRecordCount": 0,
            "opportunityCount": 0,
            "skipped": {"no_watch_target": 1},
            "items": [],
        }

    baselines = _load_baselines_by_key(
        session,
        category_id=str(category.id),
        baseline_date=baseline_date,
    )
    if not baselines:
        return {
            "dryRun": False,
            "categoryCode": normalized_category_code,
            "candidateRecordCount": 0,
            "opportunityCount": 0,
            "skipped": {"no_baseline": 1},
            "items": [],
        }

    records = load_pricing_records(
        business_domain=business_domain or normalized_category_code,
        category_code=normalized_category_code,
        freshness_days=freshness_days,
        session=session,
    )
    purged_tombstoned_opportunity_count = purge_tombstoned_buy_opportunities_with_session(
        session,
        category_id=str(category.id),
    )
    skipped = {
        "no_item_ref": 0,
        "no_watch_target_match": 0,
        "no_baseline_match": 0,
        "not_price_opportunity": 0,
        "low_opportunity_score": 0,
    }
    changed_rows: list[BuyOpportunity] = []
    live_keys: set[tuple[int, str]] = set()
    for record in records:
        if record.get("item_id_ref") is None:
            skipped["no_item_ref"] += 1
            continue
        watch_target = select_watch_target_for_pricing_record(
            record=record,
            watch_targets=watch_targets,
        )
        if watch_target is None:
            skipped["no_watch_target_match"] += 1
            continue
        baseline_match = select_best_baseline_for_pricing_record(
            record=record,
            baselines_by_key=baselines,
        )
        if baseline_match is None:
            skipped["no_baseline_match"] += 1
            continue
        baseline, match_level, match_key = baseline_match
        metrics = compute_opportunity_metrics(
            current_price=record.get("price"),
            fair_price=baseline.fair_price or baseline.median_price,
            buy_ceiling=_effective_buy_ceiling(
                baseline=baseline,
                watch_target=watch_target,
                scoring_config=scoring_config,
            ),
            confidence=baseline.confidence,
            sample_size=baseline.sample_size,
            scoring_config=scoring_config,
        )
        if not metrics["isPriceOpportunity"] and (metrics["discountRate"] or 0) < min_discount_rate:
            skipped["not_price_opportunity"] += 1
            continue
        if (metrics["opportunityScore"] or 0) < min_opportunity_score:
            skipped["low_opportunity_score"] += 1
            continue

        live_keys.add((int(record["item_id_ref"]), str(watch_target.id)))
        opportunity = upsert_buy_opportunity_from_record(
            session,
            record=record,
            watch_target=watch_target,
            baseline=baseline,
            match_level=match_level,
            match_key=match_key,
            metrics=metrics,
        )
        changed_rows.append(opportunity)
        if limit is not None and len(changed_rows) >= max(int(limit), 0):
            break

    stale_closed_count = close_stale_buy_opportunities_with_session(
        session,
        category_id=str(category.id),
        watch_target_ids={str(target.id) for target in watch_targets},
        live_keys=live_keys,
    )
    _flush(session)
    return {
        "dryRun": False,
        "categoryCode": normalized_category_code,
        "candidateRecordCount": len(records),
        "opportunityCount": len(changed_rows),
        "purgedTombstonedOpportunityCount": purged_tombstoned_opportunity_count,
        "staleClosedCount": stale_closed_count,
        "skipped": skipped,
        "items": [serialize_buy_opportunity(row) for row in changed_rows],
    }


def purge_tombstoned_buy_opportunities_with_session(
    session: Session,
    *,
    category_id: str,
) -> int:
    doomed_ids = list(
        session.execute(
            select(BuyOpportunity.id)
            .join(Item, Item.id == BuyOpportunity.item_id_ref)
            .join(
                ItemIngestRejection,
                (ItemIngestRejection.source_platform == Item.source_platform)
                & (ItemIngestRejection.item_id == Item.item_id),
            )
            .where(BuyOpportunity.category_id == category_id)
        )
        .scalars()
        .all()
    )
    if not doomed_ids:
        return 0

    session.execute(delete(BuyDecisionFeedback).where(BuyDecisionFeedback.opportunity_id.in_(doomed_ids)))
    session.execute(delete(BuyAlertEvent).where(BuyAlertEvent.opportunity_id.in_(doomed_ids)))
    session.execute(delete(BuyOpportunityRisk).where(BuyOpportunityRisk.opportunity_id.in_(doomed_ids)))
    result = session.execute(delete(BuyOpportunity).where(BuyOpportunity.id.in_(doomed_ids)))
    return int(result.rowcount or 0)


def stale_open_opportunity_ids(
    *,
    rows: list[tuple[str, int, str]],
    live_keys: set[tuple[int, str]],
) -> list[str]:
    return [
        opportunity_id
        for opportunity_id, item_id_ref, watch_target_id in rows
        if (int(item_id_ref), str(watch_target_id)) not in live_keys
    ]


def close_stale_buy_opportunities_with_session(
    session: Session,
    *,
    category_id: str,
    watch_target_ids: set[str],
    live_keys: set[tuple[int, str]],
) -> int:
    if not watch_target_ids:
        return 0

    rows = session.execute(
        select(BuyOpportunity.id, BuyOpportunity.item_id_ref, BuyOpportunity.watch_target_id)
        .where(BuyOpportunity.category_id == category_id)
        .where(BuyOpportunity.watch_target_id.in_(tuple(watch_target_ids)))
        .where(BuyOpportunity.status.in_(("OPEN", "REFERENCE_ONLY")))
    ).all()
    stale_ids = stale_open_opportunity_ids(rows=list(rows), live_keys=live_keys)
    if not stale_ids:
        return 0

    now = datetime.now(UTC)
    stale_rows = session.execute(
        select(BuyOpportunity).where(BuyOpportunity.id.in_(tuple(stale_ids)))
    ).scalars().all()
    for row in stale_rows:
        row.status = "STALE"
        row.payload = {
            **dict(row.payload or {}),
            "staleClosedAt": now.isoformat(),
        }
    return len(stale_rows)


def ensure_default_watch_target_with_session(session: Session, *, category: Category) -> BuyWatchTarget:
    target_name = f"{category.code}:default"
    existing = session.execute(
        select(BuyWatchTarget)
        .where(BuyWatchTarget.category_id == str(category.id))
        .where(BuyWatchTarget.model_catalog_id.is_(None))
        .where(BuyWatchTarget.target_name == target_name)
        .where(BuyWatchTarget.profile_key == "default")
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    row = BuyWatchTarget(
        category_id=str(category.id),
        model_catalog_id=None,
        target_name=target_name,
        profile_key="default",
        status="ACTIVE",
        risk_tolerance="medium",
        notify_cooldown_minutes=60,
        metadata_json={"source": "auto_default"},
    )
    session.add(row)
    return row


def baseline_keys_for_pricing_record(record: dict[str, Any]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    template_snapshot = build_pricing_record_template_snapshot(
        business_domain=record.get("category_code") or record.get("business_domain"),
        record=record,
    )
    template_key = _normalize_optional_string(template_snapshot.get("templateKey"))
    if template_key:
        keys.append(("template", f"template:{template_key}"))
    spec_label = _normalize_optional_string(record.get("spec_label") or record.get("label"))
    product_label = _normalize_optional_string(record.get("product_label"))
    brand = _normalize_optional_string(record.get("brand"))
    if spec_label:
        keys.append(("spec", f"spec:{spec_label}"))
    if product_label:
        keys.append(("product", f"product:{product_label}"))
    if brand:
        keys.append(("brand", f"brand:{brand}"))
    return keys


def select_best_baseline_for_pricing_record(
    *,
    record: dict[str, Any],
    baselines_by_key: dict[tuple[str | None, str], BuyPriceBaseline],
) -> tuple[BuyPriceBaseline, str, str] | None:
    model_catalog_id = _normalize_optional_string(record.get("model_catalog_id"))
    for match_level, baseline_key in baseline_keys_for_pricing_record(record):
        for lookup_model_id in (model_catalog_id, None):
            candidate = baselines_by_key.get((lookup_model_id, baseline_key))
            if candidate is not None:
                return candidate, _normalized_baseline_match_level(match_level), baseline_key
    return None


def select_watch_target_for_pricing_record(
    *,
    record: dict[str, Any],
    watch_targets: list[BuyWatchTarget],
) -> BuyWatchTarget | None:
    for target in sorted(watch_targets, key=_watch_target_sort_key):
        if watch_target_matches_pricing_record(watch_target=target, record=record):
            return target
    return None


def watch_target_matches_pricing_record(
    *,
    watch_target: BuyWatchTarget,
    record: dict[str, Any],
) -> bool:
    pricing_selector = dict(getattr(watch_target, "metadata_json", {}) or {}).get("pricingSelector")
    if isinstance(pricing_selector, dict) and pricing_selector:
        template_snapshot = build_pricing_record_template_snapshot(
            business_domain=record.get("category_code") or record.get("business_domain"),
            record=record,
        )
        resolved_field_values = dict(template_snapshot.get("resolvedFieldValues") or {})
        for field, expected in pricing_selector.items():
            if resolved_field_values.get(field) != expected:
                return False
    model_catalog_id = _normalize_optional_string(record.get("model_catalog_id"))
    if watch_target.model_catalog_id and watch_target.model_catalog_id != model_catalog_id:
        return False
    if watch_target.desired_memory_gb is not None and watch_target.desired_memory_gb != _optional_int(record.get("memory_gb")):
        return False
    if watch_target.desired_storage_gb is not None and watch_target.desired_storage_gb != _optional_int(record.get("storage_gb")):
        return False
    if watch_target.desired_region:
        region = str(record.get("region") or "")
        if watch_target.desired_region not in region:
            return False
    if watch_target.budget_ceiling is not None:
        price = _optional_decimal(record.get("price"))
        if price is not None and price > watch_target.budget_ceiling:
            return False
    return True


def compute_opportunity_metrics(
    *,
    current_price: Any,
    fair_price: Decimal | None,
    buy_ceiling: Decimal | None,
    confidence: Decimal | None,
    sample_size: int | None,
    scoring_config: dict[str, float] | None = None,
) -> dict[str, Any]:
    effective_scoring = {
        key: float((scoring_config or {}).get(key, value))
        for key, value in DEFAULT_BUY_SIDE_SCORING_CONFIG.items()
    }
    price = _optional_decimal(current_price)
    if price is None or price <= 0:
        return {
            "discountRate": None,
            "opportunityScore": 0.0,
            "riskScore": 100.0,
            "isPriceOpportunity": False,
        }

    discount_rate = None
    if fair_price is not None and fair_price > 0:
        discount_rate = max((fair_price - price) / fair_price, Decimal("0"))

    ceiling_gap_score = Decimal("0")
    if buy_ceiling is not None and buy_ceiling > 0 and price <= buy_ceiling:
        ceiling_gap_score = min(
            (buy_ceiling - price)
            / max(buy_ceiling, Decimal("1"))
            / Decimal(str(effective_scoring["ceilingGapSaturation"])),
            Decimal("1"),
        )

    discount_score = Decimal("0")
    if discount_rate is not None:
        discount_score = min(discount_rate / Decimal(str(effective_scoring["discountRateSaturation"])), Decimal("1"))

    confidence_score = confidence if confidence is not None else Decimal(str(effective_scoring["defaultConfidence"]))
    risk_score = compute_risk_score(
        price=price,
        fair_price=fair_price,
        confidence=confidence,
        sample_size=sample_size,
    )
    opportunity_score = (
        Decimal("100")
        * (
            (Decimal(str(effective_scoring["discountRateWeight"])) * discount_score)
            + (Decimal(str(effective_scoring["ceilingGapWeight"])) * ceiling_gap_score)
            + (Decimal(str(effective_scoring["confidenceWeight"])) * min(confidence_score, Decimal("1")))
        )
    ) - (Decimal(str(risk_score)) * Decimal(str(effective_scoring["riskPenaltyWeight"])))
    opportunity_score = max(min(opportunity_score, Decimal("100")), Decimal("0"))

    return {
        "discountRate": discount_rate,
        "opportunityScore": float(round(opportunity_score, 2)),
        "riskScore": float(round(Decimal(str(risk_score)), 2)),
        "isPriceOpportunity": bool(
            (buy_ceiling is not None and price <= buy_ceiling)
            or (discount_rate is not None and discount_rate >= Decimal("0.02"))
        ),
    }


def compute_risk_score(
    *,
    price: Decimal,
    fair_price: Decimal | None,
    confidence: Decimal | None,
    sample_size: int | None,
) -> float:
    score = Decimal("0")
    if sample_size is None or sample_size < 3:
        score += Decimal("25")
    elif sample_size < 5:
        score += Decimal("12")
    if confidence is None:
        score += Decimal("18")
    elif confidence < Decimal("0.5"):
        score += Decimal("20")
    elif confidence < Decimal("0.65"):
        score += Decimal("10")
    if fair_price is not None and fair_price > 0 and price < fair_price * Decimal("0.55"):
        score += Decimal("18")
    return float(min(score, Decimal("100")))


def upsert_buy_opportunity_from_record(
    session: Session,
    *,
    record: dict[str, Any],
    watch_target: BuyWatchTarget,
    baseline: BuyPriceBaseline,
    match_level: str,
    match_key: str,
    metrics: dict[str, Any],
) -> BuyOpportunity:
    template_snapshot = build_pricing_record_template_snapshot(
        business_domain=record.get("category_code") or record.get("business_domain"),
        record=record,
    )
    baseline_payload = dict(baseline.payload or {})
    baseline_pricing_template = dict(baseline_payload.get("pricingTemplate") or {})
    matched_template_key = (
        template_snapshot.get("templateKey")
        or baseline_pricing_template.get("templateKey")
    )
    template_availability_tier = _effective_template_availability_tier(
        match_level=match_level,
        matched_template_key=matched_template_key,
        baseline_pricing_template=baseline_pricing_template,
    )
    existing = session.execute(
        select(BuyOpportunity)
        .where(BuyOpportunity.item_id_ref == int(record["item_id_ref"]))
        .where(BuyOpportunity.watch_target_id == str(watch_target.id))
    ).scalar_one_or_none()
    if existing is None:
        existing = BuyOpportunity(
            item_id_ref=int(record["item_id_ref"]),
            watch_target_id=str(watch_target.id),
            status="OPEN",
            first_detected_at=datetime.now(UTC),
        )
        session.add(existing)

    existing.category_id = baseline.category_id
    existing.model_catalog_id = baseline.model_catalog_id or _normalize_optional_string(record.get("model_catalog_id"))
    existing.baseline_id = str(baseline.id)
    existing.current_price = _optional_decimal(record.get("price"))
    existing.fair_price = baseline.fair_price or baseline.median_price
    existing.buy_ceiling = _effective_buy_ceiling(baseline=baseline, watch_target=watch_target)
    existing.discount_rate = metrics["discountRate"]
    existing.opportunity_score = _optional_decimal(metrics["opportunityScore"])
    existing.risk_score = _optional_decimal(metrics["riskScore"])
    existing.last_detected_at = datetime.now(UTC)
    existing.status = classify_buy_opportunity_status(
        match_level=match_level,
        matched_template_key=matched_template_key,
        template_availability_tier=template_availability_tier,
    )
    existing.payload = {
        "baseline_match_level": match_level,
        "baseline_match_key": match_key,
        "templateMatchLevel": match_level,
        "templateMatchErrorType": template_match_error_type_for_context(
            match_level=match_level,
            matched_template_key=matched_template_key,
            template_availability_tier=template_availability_tier,
        ),
        "matchedTemplateKey": matched_template_key,
        "matchedTemplateLabel": template_snapshot.get("templateLabel") or baseline_pricing_template.get("templateLabel"),
        "matchedFieldValues": dict(template_snapshot.get("resolvedFieldValues") or {}),
        "templateAvailabilityTier": template_availability_tier,
        "templateGuidanceReady": existing.status == "OPEN",
        "pricingEligibility": _json_safe_value(dict(record.get("pricing_eligibility") or {})),
        "specContract": _json_safe_value(dict(record.get("spec_contract") or {})),
        "specSource": _json_safe_value(dict(record.get("spec_source") or {})),
        "pricing_record": _json_safe_value(dict(record)),
        "metrics": _json_safe_metrics(metrics),
    }
    _flush(session)
    _upsert_risk_findings(session=session, opportunity=existing, baseline=baseline, metrics=metrics)
    return existing


def serialize_buy_opportunity(row: BuyOpportunity) -> dict[str, Any]:
    payload = dict(row.payload or {})
    feedback_summary = dict(payload.get("feedbackSummary") or {})
    return {
        "id": row.id,
        "itemIdRef": row.item_id_ref,
        "categoryId": row.category_id,
        "modelCatalogId": row.model_catalog_id,
        "watchTargetId": row.watch_target_id,
        "baselineId": row.baseline_id,
        "currentPrice": _decimal_to_float(row.current_price),
        "fairPrice": _decimal_to_float(row.fair_price),
        "buyCeiling": _decimal_to_float(row.buy_ceiling),
        "discountRate": _decimal_to_float(row.discount_rate),
        "opportunityScore": _decimal_to_float(row.opportunity_score),
        "riskScore": _decimal_to_float(row.risk_score),
        "status": row.status,
        "pricingEligibility": dict((row.payload or {}).get("pricingEligibility") or {}),
        "specContract": dict((row.payload or {}).get("specContract") or {}),
        "specSource": dict((row.payload or {}).get("specSource") or {}),
        "feedbackSummary": {
            "feedbackAction": _normalize_optional_string(feedback_summary.get("feedbackAction")),
            "feedbackCategory": _normalize_optional_string(feedback_summary.get("feedbackCategory")),
            "feedbackLabel": _normalize_optional_string(feedback_summary.get("feedbackLabel")),
            "operatorId": _normalize_optional_string(feedback_summary.get("operatorId")),
            "feedbackNote": _normalize_optional_string(feedback_summary.get("feedbackNote")),
            "recordedAt": _normalize_optional_string(feedback_summary.get("recordedAt")),
            "alertCandidateLinkage": dict(feedback_summary.get("alertCandidateLinkage") or {}),
        },
        "payload": dict(row.payload or {}),
    }


def _upsert_risk_findings(
    *,
    session: Session,
    opportunity: BuyOpportunity,
    baseline: BuyPriceBaseline,
    metrics: dict[str, Any],
) -> None:
    findings = risk_findings_for_opportunity(baseline=baseline, metrics=metrics)
    for finding in findings:
        existing = session.execute(
            select(BuyOpportunityRisk)
            .where(BuyOpportunityRisk.opportunity_id == str(opportunity.id))
            .where(BuyOpportunityRisk.risk_code == finding["risk_code"])
        ).scalar_one_or_none()
        if existing is None:
            existing = BuyOpportunityRisk(
                opportunity_id=str(opportunity.id),
                risk_code=finding["risk_code"],
            )
            session.add(existing)
        existing.risk_level = finding["risk_level"]
        existing.detail = finding["detail"]
        existing.evidence_json = dict(finding.get("evidence_json") or {})


def risk_findings_for_opportunity(
    *,
    baseline: BuyPriceBaseline,
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if baseline.sample_size < 3:
        findings.append(
            {
                "risk_code": "LOW_SAMPLE_SIZE",
                "risk_level": "high",
                "detail": "价格基线样本少于 3 个卖家样本，合理价不稳定。",
                "evidence_json": {"sample_size": baseline.sample_size},
            }
        )
    elif baseline.sample_size < 5:
        findings.append(
            {
                "risk_code": "MEDIUM_SAMPLE_SIZE",
                "risk_level": "medium",
                "detail": "价格基线样本少于 5 个卖家样本，需要人工复核。",
                "evidence_json": {"sample_size": baseline.sample_size},
            }
        )
    if baseline.confidence is None or baseline.confidence < Decimal("0.55"):
        findings.append(
            {
                "risk_code": "LOW_BASELINE_CONFIDENCE",
                "risk_level": "medium",
                "detail": "价格基线置信度偏低。",
                "evidence_json": {"confidence": _decimal_to_float(baseline.confidence)},
            }
        )
    if (metrics.get("riskScore") or 0) >= 40:
        findings.append(
            {
                "risk_code": "HIGH_COMPUTED_RISK",
                "risk_level": "high",
                "detail": "机会综合风险分偏高。",
                "evidence_json": {"risk_score": metrics.get("riskScore")},
            }
        )
    return findings


def _load_watch_targets(session: Session, *, category_id: str) -> list[BuyWatchTarget]:
    return list(
        session.execute(
            select(BuyWatchTarget)
            .where(BuyWatchTarget.category_id == category_id)
            .where(BuyWatchTarget.status == "ACTIVE")
        )
        .scalars()
        .all()
    )


def _load_baselines_by_key(
    session: Session,
    *,
    category_id: str,
    baseline_date: date | None,
) -> dict[tuple[str | None, str], BuyPriceBaseline]:
    target_date = baseline_date
    if target_date is None:
        target_date = session.execute(
            select(func.max(BuyPriceBaseline.baseline_date)).where(BuyPriceBaseline.category_id == category_id)
        ).scalar_one_or_none()
    if target_date is None:
        return {}
    rows = list(
        session.execute(
            select(BuyPriceBaseline)
            .where(BuyPriceBaseline.category_id == category_id)
            .where(BuyPriceBaseline.baseline_date == target_date)
        )
        .scalars()
        .all()
    )
    indexed: dict[tuple[str | None, str], BuyPriceBaseline] = {}
    for row in rows:
        model_catalog_id = _normalize_optional_string(row.model_catalog_id)
        indexed[(model_catalog_id, row.baseline_key)] = row
        pricing_template = dict((row.payload or {}).get("pricingTemplate") or {})
        template_key = _normalize_optional_string(pricing_template.get("templateKey"))
        if template_key:
            indexed[(model_catalog_id, f"template:{template_key}")] = row
    return indexed


def classify_buy_opportunity_status(
    *,
    match_level: str,
    matched_template_key: str | None,
    template_availability_tier: str | None,
) -> str:
    if not is_price_template_opportunity_enabled():
        return "OPEN"
    if match_level in {"degraded_product", "degraded_brand"}:
        return "REFERENCE_ONLY"
    if not _normalize_optional_string(matched_template_key):
        return "REFERENCE_ONLY"
    if template_availability_tier != "guidance_ready":
        return "REFERENCE_ONLY"
    return "OPEN"


def template_match_error_type_for_context(
    *,
    match_level: str,
    matched_template_key: str | None,
    template_availability_tier: str | None,
) -> str | None:
    if not is_price_template_opportunity_enabled():
        return None
    if match_level == "degraded_product":
        return "degraded_product_match"
    if match_level == "degraded_brand":
        return "degraded_brand_match"
    if not _normalize_optional_string(matched_template_key):
        return "missing_template_key"
    normalized_tier = _normalize_optional_string(template_availability_tier)
    if normalized_tier != "guidance_ready":
        return f"availability_{normalized_tier or 'unknown'}"
    return None


def _effective_template_availability_tier(
    *,
    match_level: str,
    matched_template_key: str | None,
    baseline_pricing_template: dict[str, Any],
) -> str:
    raw_tier = _normalize_optional_string(
        dict(baseline_pricing_template.get("availability") or {}).get("availabilityTier")
    )
    if not is_price_template_opportunity_enabled():
        return raw_tier or "guidance_ready"
    if match_level in {"degraded_product", "degraded_brand"}:
        return "reference_only"
    if not _normalize_optional_string(matched_template_key):
        return "reference_only"
    return raw_tier or "reference_only"


def _normalized_baseline_match_level(match_level: str) -> str:
    if match_level == "product":
        return "degraded_product"
    if match_level == "brand":
        return "degraded_brand"
    return match_level


def _resolve_requested_category_code(*, category_code: str | None, business_domain: str | None) -> str:
    requested = _normalize_optional_string(category_code) or _normalize_optional_string(business_domain)
    if not requested:
        raise BuyOpportunityError("category_code or business_domain is required.")
    return resolve_category_code(requested)


def _resolve_category(session: Session, *, category_code: str) -> Category | None:
    return session.execute(select(Category).where(Category.code == category_code)).scalar_one_or_none()


def _effective_buy_ceiling(
    *,
    baseline: BuyPriceBaseline,
    watch_target: BuyWatchTarget,
    scoring_config: dict[str, float] | None = None,
) -> Decimal | None:
    effective_scoring = {
        key: float((scoring_config or {}).get(key, value))
        for key, value in DEFAULT_BUY_SIDE_SCORING_CONFIG.items()
    }
    tightened_baseline_ceiling = baseline.buy_ceiling
    tighten_pct = max(float(effective_scoring["buyCeilingTightenPct"]), 0.0)
    if tightened_baseline_ceiling is not None and tighten_pct > 0:
        tightened_baseline_ceiling = max(
            tightened_baseline_ceiling * (Decimal("1") - (Decimal(str(tighten_pct)) / Decimal("100"))),
            Decimal("0"),
        )
    values = [value for value in (tightened_baseline_ceiling, watch_target.budget_ceiling) if value is not None]
    if not values:
        return None
    return min(values)


def _watch_target_sort_key(target: BuyWatchTarget) -> tuple[int, str]:
    specificity = 0
    if target.model_catalog_id:
        specificity += 10
    if target.desired_memory_gb is not None:
        specificity += 2
    if target.desired_storage_gb is not None:
        specificity += 2
    if target.desired_region:
        specificity += 1
    return (-specificity, str(target.target_name or ""))


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _json_safe_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _json_safe_value(value)
        for key, value in metrics.items()
    }


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_to_float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    return value


def _flush(session: Session) -> None:
    flush = getattr(session, "flush", None)
    if callable(flush):
        flush()


__all__ = [
    "BuyOpportunityError",
    "baseline_keys_for_pricing_record",
    "classify_buy_opportunity_status",
    "close_stale_buy_opportunities_with_session",
    "compute_opportunity_metrics",
    "compute_risk_score",
    "ensure_default_watch_target_with_session",
    "is_price_template_opportunity_enabled",
    "purge_tombstoned_buy_opportunities_with_session",
    "refresh_buy_opportunities",
    "refresh_buy_opportunities_with_session",
    "risk_findings_for_opportunity",
    "select_best_baseline_for_pricing_record",
    "select_watch_target_for_pricing_record",
    "serialize_buy_opportunity",
    "stale_open_opportunity_ids",
    "template_match_error_type_for_context",
    "upsert_buy_opportunity_from_record",
    "watch_target_matches_pricing_record",
    "_json_safe_value",
]
