from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from goofish_insight.application.services.buy_side_calibration import (
    load_buy_side_calibration_config_with_session,
    resolve_buy_side_pricing_thresholds,
)
from goofish_insight.application.services.pricing_support import (
    refresh_sku_neighbors_with_session,
)

from goofish_analyzer.adapters import (
    aggregate_pricing_view,
    build_pricing_record_template_snapshot,
    load_pricing_records,
    resolve_category_code,
    session_scope,
    BuyPriceBaseline,
    Category,
)
from goofish_analyzer.services.pricing_explanations import build_buy_price_baseline_explanation
from goofish_analyzer.services.pricing_thresholds import evaluate_pricing_availability


class BuyPriceBaselineError(RuntimeError):
    pass


def _view_prefixes(view_names: list[str]) -> tuple[str, ...]:
    return tuple(f"{view_name}:" for view_name in view_names)


def build_buy_price_baselines(
    *,
    category_code: str | None = None,
    business_domain: str | None = None,
    view: str = "all",
    freshness_days: int = 30,
    min_sample_points: int = 4,
    baseline_date: date | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = build_buy_price_baselines_with_session(
            session,
            category_code=category_code,
            business_domain=business_domain,
            view=view,
            freshness_days=freshness_days,
            min_sample_points=min_sample_points,
            baseline_date=baseline_date,
            limit=limit,
        )
        if dry_run:
            session.rollback()
            result["dryRun"] = True
        return result


def build_buy_price_baselines_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    business_domain: str | None = None,
    view: str = "all",
    freshness_days: int = 30,
    min_sample_points: int = 4,
    baseline_date: date | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    normalized_view = _normalize_view(view)
    normalized_category_code = _resolve_requested_category_code(
        category_code=category_code,
        business_domain=business_domain,
    )
    category = _resolve_category(session, category_code=normalized_category_code)
    if category is None:
        raise BuyPriceBaselineError(f"Category not found: {normalized_category_code}")

    records = load_pricing_records(
        business_domain=business_domain or normalized_category_code,
        category_code=normalized_category_code,
        freshness_days=freshness_days,
        session=session,
        persist_item_samples=True,
    )
    calibration_state = load_buy_side_calibration_config_with_session(
        session,
        category=category,
    )
    pricing_thresholds = resolve_buy_side_pricing_thresholds(calibration_state.get("effectiveConfig"))
    target_date = baseline_date or date.today()
    changed_rows: list[BuyPriceBaseline] = []
    expected_keys: set[tuple[str | None, str]] = set()
    row_counts_by_view: dict[str, int] = {}
    expanded_views = _expand_views(normalized_view)
    support_refresh: list[dict[str, Any]] = []
    for view_name in expanded_views:
        rows = aggregate_pricing_view(
            records=records,
            view=view_name,
            min_sample_points=min_sample_points,
        )
        if limit is not None:
            rows = rows[: max(int(limit), 0)]
        row_counts_by_view[view_name] = len(rows)
        for row in rows:
            baseline = upsert_buy_price_baseline_from_pricing_row(
                session,
                category=category,
                pricing_row=row,
                view=view_name,
                baseline_date=target_date,
                build_config={
                    "freshness_days": freshness_days,
                    "min_sample_points": min_sample_points,
                    "requested_view": normalized_view,
                },
                pricing_thresholds=pricing_thresholds,
            )
            changed_rows.append(baseline)
            expected_keys.add((baseline.model_catalog_id, baseline.baseline_key))
    _prune_stale_buy_price_baselines(
        session,
        category_id=str(category.id),
        baseline_date=target_date,
        baseline_key_prefixes=_view_prefixes(list(expanded_views)),
        expected_keys=expected_keys,
    )
    schema_ids = sorted(
        {
            int(record["schema_id"])
            for record in records
            if record.get("schema_id") is not None
        }
    )
    for schema_id in schema_ids:
        support_refresh.append(
            refresh_sku_neighbors_with_session(
                session,
                schema_id=schema_id,
            )
        )
    session.flush()

    return {
        "dryRun": False,
        "categoryCode": normalized_category_code,
        "view": normalized_view,
        "baselineDate": target_date.isoformat(),
        "candidateRecordCount": len(records),
        "baselineCountByView": row_counts_by_view,
        "baselineCount": len(changed_rows),
        "supportRefresh": support_refresh,
        "items": [serialize_buy_price_baseline(row) for row in changed_rows],
    }


def upsert_buy_price_baseline_from_pricing_row(
    session: Session,
    *,
    category: Category,
    pricing_row: dict[str, Any],
    view: str,
    baseline_date: date,
    build_config: dict[str, Any] | None = None,
    pricing_thresholds: dict[str, dict[str, float | int]] | None = None,
) -> BuyPriceBaseline:
    baseline_key = build_baseline_key(pricing_row=pricing_row, view=view)
    model_catalog_id = _normalize_optional_string(pricing_row.get("model_catalog_id"))
    pricing_template = build_pricing_record_template_snapshot(
        business_domain=category.code,
        record=pricing_row,
        session=session,
    )
    schema_id = _optional_int(pricing_template.get("schemaId") or pricing_row.get("schema_id"))
    existing_stmt = (
        select(BuyPriceBaseline)
        .where(BuyPriceBaseline.category_id == str(category.id))
        .where(BuyPriceBaseline.baseline_key == baseline_key)
        .where(BuyPriceBaseline.baseline_date == baseline_date)
    )
    if model_catalog_id:
        existing_stmt = existing_stmt.where(BuyPriceBaseline.model_catalog_id == model_catalog_id)
    else:
        existing_stmt = existing_stmt.where(BuyPriceBaseline.model_catalog_id.is_(None))
    if schema_id is not None:
        existing_stmt = existing_stmt.where(BuyPriceBaseline.schema_id == schema_id)
    else:
        existing_stmt = existing_stmt.where(BuyPriceBaseline.schema_id.is_(None))

    row = session.execute(existing_stmt).scalar_one_or_none()
    if row is None:
        row = BuyPriceBaseline(
            category_id=str(category.id),
            model_catalog_id=model_catalog_id,
            schema_id=schema_id,
            baseline_key=baseline_key,
            baseline_date=baseline_date,
        )
        session.add(row)

    template_availability = evaluate_pricing_availability(
        template_complete=pricing_template.get("completenessStatus") == "complete",
        seller_sample_count=pricing_row.get("seller_sample_count"),
        unique_seller_count=pricing_row.get("unique_seller_count"),
        exact_spec_ratio=pricing_row.get("exact_spec_ratio"),
        reliability_score=pricing_row.get("reliability_score"),
        effective_sample_count=pricing_row.get("effective_sample_count"),
        recency_weighted_sample_count=pricing_row.get("recency_weighted_sample_count"),
        mad=pricing_row.get("mad"),
        confidence_score=pricing_row.get("confidence_score"),
        confidence_reasons=pricing_row.get("confidence_reasons"),
        quality_tier=pricing_row.get("quality_tier"),
        p15_price=pricing_row.get("p15_price"),
        p35_price=pricing_row.get("p35_price"),
        p50_price=pricing_row.get("p50_price") or pricing_row.get("median_price"),
        latest_seen_at=pricing_row.get("latest_seen_at"),
        reference_only_thresholds=dict((pricing_thresholds or {}).get("referenceOnly") or {}),
        guidance_ready_thresholds=dict((pricing_thresholds or {}).get("guidanceReady") or {}),
    )

    row.schema_id = schema_id
    row.memory_gb = _optional_int(pricing_row.get("memory_gb")) if view == "spec" else None
    row.storage_gb = _optional_int(pricing_row.get("storage_gb")) if view == "spec" else None
    row.region = _normalize_optional_string(pricing_row.get("region"))
    row.sample_size = int(pricing_row.get("seller_sample_count") or pricing_row.get("listing_count") or 0)
    row.median_price = _optional_decimal(pricing_row.get("median_price") or pricing_row.get("fair_price"))
    row.p25_price = _optional_decimal(pricing_row.get("good_value_price"))
    row.p75_price = _optional_decimal(pricing_row.get("high_price_floor"))
    row.fair_price = _optional_decimal(pricing_row.get("fair_price") or pricing_row.get("median_price"))
    row.buy_ceiling = _optional_decimal(pricing_row.get("target_buy_ceiling"))
    row.confidence = _confidence_decimal(pricing_row.get("reliability_score"))
    row.payload = {
        "view": view,
        "source": "pricing.aggregate_pricing_view",
        "build_config": dict(build_config or {}),
        "pricing_row": dict(pricing_row),
        "pricingTemplate": {
            **pricing_template,
            "baselineLookupKey": (
                f"template:{pricing_template['templateKey']}"
                if pricing_template.get("templateKey")
                else None
            ),
            "availability": template_availability,
        },
        "schema": {
            "schemaId": schema_id,
            "schemaSummary": dict(pricing_template.get("schemaSummary") or {}),
        },
        "sampleFingerprint": {
            "dominantFingerprintHash": _normalize_optional_string(pricing_row.get("dominant_fingerprint_hash")),
            "fingerprintCount": _optional_int(pricing_row.get("sample_fingerprint_count")) or 0,
            "sampleStateCounts": dict(pricing_row.get("sample_state_counts") or {}),
        },
    }
    return row


def _prune_stale_buy_price_baselines(
    session: Session,
    *,
    category_id: str,
    baseline_date: date,
    baseline_key_prefixes: tuple[str, ...],
    expected_keys: set[tuple[str | None, str]],
) -> int:
    stmt = (
        select(BuyPriceBaseline)
        .where(BuyPriceBaseline.category_id == category_id)
        .where(BuyPriceBaseline.baseline_date == baseline_date)
    )
    if baseline_key_prefixes:
        stmt = stmt.where(
            or_(*(BuyPriceBaseline.baseline_key.like(f"{prefix}%") for prefix in baseline_key_prefixes))
        )
    existing_rows = session.execute(stmt).scalars().all()
    deleted = 0
    for row in existing_rows:
        row_key = (row.model_catalog_id, row.baseline_key)
        if row_key in expected_keys:
            continue
        session.delete(row)
        deleted += 1
    return deleted


def build_baseline_key(*, pricing_row: dict[str, Any], view: str) -> str:
    label = _normalize_optional_string(pricing_row.get("label"))
    if not label:
        label = _normalize_optional_string(pricing_row.get("spec_label"))
    if not label:
        label = _normalize_optional_string(pricing_row.get("product_label"))
    if not label:
        raise BuyPriceBaselineError("pricing row must include a label, spec_label, or product_label")
    return f"{view}:{label}"


def serialize_buy_price_baseline(row: BuyPriceBaseline) -> dict[str, Any]:
    payload = dict(row.payload or {})
    pricing_row = dict(payload.get("pricing_row") or {})
    return {
        "id": row.id,
        "categoryId": row.category_id,
        "modelCatalogId": row.model_catalog_id,
        "schemaId": row.schema_id,
        "baselineKey": row.baseline_key,
        "memoryGb": row.memory_gb,
        "storageGb": row.storage_gb,
        "region": row.region,
        "sampleSize": row.sample_size,
        "medianPrice": _decimal_to_float(row.median_price),
        "p25Price": _decimal_to_float(row.p25_price),
        "p75Price": _decimal_to_float(row.p75_price),
        "p15Price": _decimal_to_float(pricing_row.get("p15_price")),
        "p35Price": _decimal_to_float(pricing_row.get("p35_price")),
        "p50Price": _decimal_to_float(pricing_row.get("p50_price") or pricing_row.get("median_price")),
        "fairPrice": _decimal_to_float(row.fair_price),
        "buyCeiling": _decimal_to_float(row.buy_ceiling),
        "confidence": _decimal_to_float(row.confidence),
        "mad": _decimal_to_float(pricing_row.get("mad")),
        "effectiveSampleCount": _decimal_to_float(pricing_row.get("effective_sample_count")),
        "recencyWeightedSampleCount": _decimal_to_float(pricing_row.get("recency_weighted_sample_count")),
        "qualityTier": pricing_row.get("quality_tier"),
        "confidenceScore": _decimal_to_float(pricing_row.get("confidence_score")),
        "confidenceReasons": list(pricing_row.get("confidence_reasons") or []),
        "baselineDate": row.baseline_date.isoformat() if row.baseline_date else None,
        "schemaSummary": dict((row.payload or {}).get("schema", {}).get("schemaSummary") or {}),
        "sampleFingerprint": dict((row.payload or {}).get("sampleFingerprint") or {}),
        "explanation": build_buy_price_baseline_explanation(row),
        "payload": payload,
    }


def _resolve_requested_category_code(*, category_code: str | None, business_domain: str | None) -> str:
    requested = _normalize_optional_string(category_code) or _normalize_optional_string(business_domain)
    if not requested:
        raise BuyPriceBaselineError("category_code or business_domain is required.")
    return resolve_category_code(requested)


def _resolve_category(session: Session, *, category_code: str) -> Category | None:
    return session.execute(select(Category).where(Category.code == category_code)).scalar_one_or_none()


def _normalize_view(view: str) -> str:
    normalized = str(view or "").strip().lower()
    if normalized not in {"all", "brand", "product", "spec"}:
        raise BuyPriceBaselineError("view must be one of: all, brand, product, spec")
    return normalized


def _expand_views(view: str) -> tuple[str, ...]:
    if view == "all":
        return ("brand", "product", "spec")
    return (view,)


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _confidence_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    normalized = max(min(float(value) / 100, 1.0), 0.0)
    return Decimal(str(round(normalized, 4)))


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
