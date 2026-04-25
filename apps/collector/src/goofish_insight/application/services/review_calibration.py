from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from ...compat import UTC
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select

from ...category_compat import compatible_scope_keys, is_apple_computer_scope, is_garmin_watch_scope
from ...db import session_scope
from ...domain.review.contracts import (
    REVIEW_STATUS_INVALID,
    REVIEW_STATUS_PENDING_AUDIT,
    REVIEW_STATUS_VALID,
)
from ...domain.review.policy import (
    LLM_REVIEW_INVALID_MAX_CONFIDENCE,
    LLM_REVIEW_VALID_CONFIDENCE,
    PRICING_VALID_CONFIDENCE,
)
from ...models import Item, ItemSpecEnrichment, RawResponse
from ...pricing import (
    APPLE_ANALYSIS_PRODUCT_LINES,
    GARMIN_ANALYSIS_PRODUCT_LINES,
    MIN_ACTIONABLE_PROFIT_MARGIN_PCT,
    aggregate_pricing_view,
    compute_profit_margin_pct,
    decimal_to_float,
    first_non_null,
    first_text,
    is_item_eligible_for_pricing,
    load_pricing_records,
    max_optional_float,
    minimum_actionable_profit_amount,
    normalize_product_line,
    pricing_gate_exclusion_reason,
    pricing_group_key,
    round_money,
    title_is_non_comparable_listing,
    title_matches_domain,
)
from ...specs import extract_item_specs
from .review_queries import serialize_review_row

CALIBRATION_BUCKET_VALID = "valid"
CALIBRATION_BUCKET_INVALID = "invalid"
CALIBRATION_BUCKET_PENDING_AUDIT = "pending_audit"
CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK = "high_profit_high_risk"
CALIBRATION_BUCKET_PRIORITY = (
    CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK,
    CALIBRATION_BUCKET_PENDING_AUDIT,
    CALIBRATION_BUCKET_VALID,
    CALIBRATION_BUCKET_INVALID,
)
CALIBRATION_REVIEW_STATUS_VALUES = (
    REVIEW_STATUS_VALID,
    REVIEW_STATUS_INVALID,
    REVIEW_STATUS_PENDING_AUDIT,
)
CALIBRATION_RISK_LEVEL_VALUES = ("low", "medium", "high")
CALIBRATION_BUCKET_VALUES = (
    CALIBRATION_BUCKET_VALID,
    CALIBRATION_BUCKET_INVALID,
    CALIBRATION_BUCKET_PENDING_AUDIT,
    CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK,
)


def build_review_calibration_set(
    *,
    business_domain: str | None,
    freshness_days: int,
    pricing_freshness_days: int,
    min_sample_points: int,
    valid_limit: int,
    invalid_limit: int,
    pending_audit_limit: int,
    high_profit_high_risk_limit: int,
    seed: int,
) -> dict[str, Any]:
    with session_scope() as session:
        rows = _load_calibration_source_rows(
            session=session,
            business_domain=business_domain,
            freshness_days=freshness_days,
        )
        pricing_records = load_pricing_records(
            business_domain=business_domain,
            freshness_days=pricing_freshness_days,
            session=session,
        )

    spec_lookup = {
        pricing_group_key(record=row, view="spec"): row
        for row in aggregate_pricing_view(records=pricing_records, view="spec", min_sample_points=min_sample_points)
        if pricing_group_key(record=row, view="spec") is not None
    }
    product_lookup = {
        pricing_group_key(record=row, view="product"): row
        for row in aggregate_pricing_view(records=pricing_records, view="product", min_sample_points=min_sample_points)
        if pricing_group_key(record=row, view="product") is not None
    }

    candidates = [
        build_calibration_candidate(
            item=item,
            spec=spec,
            raw_response_body=raw_response_body,
            spec_lookup=spec_lookup,
            product_lookup=product_lookup,
        )
        for item, spec, raw_response_body in rows
    ]

    bucket_limits = {
        CALIBRATION_BUCKET_VALID: max(valid_limit, 0),
        CALIBRATION_BUCKET_INVALID: max(invalid_limit, 0),
        CALIBRATION_BUCKET_PENDING_AUDIT: max(pending_audit_limit, 0),
        CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK: max(high_profit_high_risk_limit, 0),
    }
    selected_samples, selection_summary = select_calibration_samples(
        candidates=candidates,
        bucket_limits=bucket_limits,
        seed=seed,
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "business_domain": business_domain,
        "freshness_days": freshness_days,
        "pricing_freshness_days": pricing_freshness_days,
        "min_sample_points": min_sample_points,
        "seed": seed,
        "bucket_limits": bucket_limits,
        "selection_summary": selection_summary,
        "samples": selected_samples,
    }


def build_calibration_candidate(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    raw_response_body: dict[str, Any] | None,
    spec_lookup: dict[tuple[Any, ...], dict[str, Any]],
    product_lookup: dict[tuple[Any, ...], dict[str, Any]],
) -> dict[str, Any]:
    review_row = serialize_review_row(
        item=item,
        spec=spec,
        raw_response_body=raw_response_body,
    )
    pricing_context = build_calibration_pricing_context(
        item=item,
        spec=spec,
        spec_lookup=spec_lookup,
        product_lookup=product_lookup,
    )
    bucket_tags = classify_calibration_bucket_tags(
        review_prediction=review_row["llm_review"],
        pricing_context=pricing_context,
    )
    route_hint = infer_calibration_route_hint(
        review_prediction=review_row["llm_review"],
        pricing_context=pricing_context,
        bucket_tags=bucket_tags,
    )
    return {
        "sample_id": None,
        "bucket": None,
        "bucket_tags": bucket_tags,
        "route_hint": route_hint,
        "item_id": item.item_id,
        "db_item_id": item.id,
        "business_domain": item.business_domain,
        "source_keyword": item.source_keyword,
        "source_platform": item.source_platform,
        "title": item.title,
        "listing_url": item.listing_url,
        "current_price": decimal_to_float(item.current_price),
        "region": item.region,
        "condition_tags": item.condition_tags or [],
        "listing_description": review_row.get("listing_description"),
        "listing_description_length": review_row.get("listing_description_length"),
        "is_active": bool(item.is_active),
        "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
        "item_fields": review_row["item_fields"],
        "spec_fields": review_row["spec_fields"],
        "rule_candidate": review_row["rule_candidate"],
        "review_prediction": review_row["llm_review"],
        "pricing_context": pricing_context,
        "annotation": default_calibration_annotation(),
    }


def build_calibration_pricing_context(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    spec_lookup: dict[tuple[Any, ...], dict[str, Any]],
    product_lookup: dict[tuple[Any, ...], dict[str, Any]],
) -> dict[str, Any]:
    comparison_record = resolve_comparison_record(item=item, spec=spec)
    gate_reason = pricing_gate_exclusion_reason(item)
    eligible_for_pricing = is_item_eligible_for_pricing(item)
    if comparison_record is None:
        return {
            "eligible_for_pricing": eligible_for_pricing,
            "pricing_gate_exclusion_reason": gate_reason,
            "matched_view": None,
            "matched_label": None,
            "matched_product_label": None,
            "matched_spec_label": None,
            "matched_group_reliability_score": None,
            "matched_group_sample_count": None,
            "matched_group_required_profit_amount": None,
            "matched_group_fair_price": None,
            "matched_group_target_buy_ceiling": None,
            "apparent_profit_to_fair_price": None,
            "apparent_margin_pct_to_fair_price": None,
            "is_high_profit_high_risk_candidate": False,
        }

    matched_view = None
    matched_row = None
    spec_key = pricing_group_key(record=comparison_record, view="spec")
    if spec_key is not None:
        matched_row = spec_lookup.get(spec_key)
        if matched_row is not None:
            matched_view = "spec"
    if matched_row is None:
        product_key = pricing_group_key(record=comparison_record, view="product")
        if product_key is not None:
            matched_row = product_lookup.get(product_key)
            if matched_row is not None:
                matched_view = "product"

    current_price = decimal_to_float(item.current_price)
    fair_price = matched_row.get("fair_price") if matched_row is not None else None
    required_profit_amount = matched_row.get("required_profit_amount") if matched_row is not None else None
    apparent_profit = (
        max((fair_price or 0) - (current_price or 0), 0)
        if fair_price is not None and current_price is not None
        else None
    )
    apparent_margin_pct = compute_profit_margin_pct(
        buy_price=current_price,
        fair_price=fair_price,
    )
    is_high_profit_high_risk_candidate = bool(
        matched_row is not None
        and gate_reason is not None
        and apparent_profit is not None
        and required_profit_amount is not None
        and apparent_profit >= required_profit_amount
        and apparent_margin_pct is not None
        and apparent_margin_pct >= MIN_ACTIONABLE_PROFIT_MARGIN_PCT
    )
    return {
        "eligible_for_pricing": eligible_for_pricing,
        "pricing_gate_exclusion_reason": gate_reason,
        "matched_view": matched_view,
        "matched_label": matched_row.get("label") if matched_row is not None else None,
        "matched_product_label": matched_row.get("product_label") if matched_row is not None else None,
        "matched_spec_label": matched_row.get("spec_label") if matched_row is not None else None,
        "matched_group_reliability_score": matched_row.get("reliability_score") if matched_row is not None else None,
        "matched_group_sample_count": matched_row.get("seller_sample_count") if matched_row is not None else None,
        "matched_group_required_profit_amount": required_profit_amount,
        "matched_group_fair_price": fair_price,
        "matched_group_target_buy_ceiling": matched_row.get("target_buy_ceiling") if matched_row is not None else None,
        "apparent_profit_to_fair_price": round_money(apparent_profit),
        "apparent_margin_pct_to_fair_price": round_money(apparent_margin_pct, digits=2),
        "is_high_profit_high_risk_candidate": is_high_profit_high_risk_candidate,
    }


def resolve_comparison_record(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
) -> dict[str, Any] | None:
    if item.current_price is None or item.current_price <= 0:
        return None
    if not title_matches_domain(item.business_domain, item.title):
        return None
    if title_is_non_comparable_listing(
        business_domain=item.business_domain,
        title=item.title,
        price=item.current_price,
    ):
        return None

    rule_candidate = extract_item_specs(item, allow_llm=False)
    brand = first_text(spec.brand if spec else None, rule_candidate.brand, item.normalized_brand)
    if is_garmin_watch_scope(item.business_domain):
        brand = brand or "Garmin"
        if brand != "Garmin":
            return None
    elif is_apple_computer_scope(item.business_domain):
        brand = brand or "Apple"
        if brand != "Apple":
            return None
    elif brand is None:
        return None

    product_line = first_text(
        spec.product_line if spec else None,
        rule_candidate.product_line,
        spec.model_family if spec else None,
        item.normalized_model_family,
    )
    model_name = first_text(
        spec.model_name if spec else None,
        rule_candidate.model_name,
        item.normalized_model,
        product_line,
    )
    display_type = first_text(spec.display_type if spec else None, rule_candidate.display_type)
    if display_type:
        display_type = display_type.upper()
    case_size_mm = first_non_null(spec.case_size_mm if spec else None, rule_candidate.case_size_mm)
    is_solar = first_non_null(spec.is_solar if spec else None, rule_candidate.is_solar)
    screen_size_in = first_non_null(spec.screen_size_in if spec else None, rule_candidate.screen_size_in)
    chip_family = first_text(spec.chip_family if spec else None, rule_candidate.chip_family, item.normalized_chip)
    cpu_cores = first_non_null(spec.cpu_cores if spec else None, rule_candidate.cpu_cores)
    gpu_cores = first_non_null(spec.gpu_cores if spec else None, rule_candidate.gpu_cores)
    memory_gb = first_non_null(
        spec.memory_gb if spec else None,
        rule_candidate.memory_gb,
        item.normalized_memory_gb,
    )
    storage_gb = first_non_null(
        spec.storage_gb if spec else None,
        rule_candidate.storage_gb,
        item.normalized_storage_gb,
    )
    spec_confidence = max_optional_float(
        decimal_to_float(spec.confidence) if spec and spec.confidence is not None else None,
        decimal_to_float(rule_candidate.confidence) if rule_candidate.confidence is not None else None,
    )
    spec_status = first_text(spec.status if spec else None, rule_candidate.status)

    if is_garmin_watch_scope(item.business_domain):
        product_line = normalize_product_line(
            product_line=product_line,
            model_name=model_name,
            allowed_values=GARMIN_ANALYSIS_PRODUCT_LINES,
        )
        if product_line not in GARMIN_ANALYSIS_PRODUCT_LINES:
            return None
    elif is_apple_computer_scope(item.business_domain):
        product_line = normalize_product_line(
            product_line=product_line,
            model_name=model_name,
            allowed_values=APPLE_ANALYSIS_PRODUCT_LINES,
        )
        if product_line not in APPLE_ANALYSIS_PRODUCT_LINES or not chip_family:
            return None

    spec_label = build_spec_label(
        business_domain=item.business_domain,
        product_line=product_line,
        model_name=model_name,
        display_type=display_type,
        case_size_mm=case_size_mm,
        is_solar=is_solar,
        screen_size_in=screen_size_in,
        chip_family=chip_family,
        cpu_cores=cpu_cores,
        gpu_cores=gpu_cores,
        memory_gb=memory_gb,
        storage_gb=storage_gb,
    )
    if not spec_label:
        return None
    return {
        "business_domain": item.business_domain,
        "brand": brand,
        "product_label": product_line,
        "spec_label": spec_label,
        "price": decimal_to_float(item.current_price),
        "spec_confidence": spec_confidence,
        "spec_status": spec_status,
    }


def build_spec_label(
    *,
    business_domain: str,
    product_line: str | None,
    model_name: str | None,
    display_type: str | None,
    case_size_mm: int | None,
    is_solar: bool | None,
    screen_size_in: float | None,
    chip_family: str | None,
    cpu_cores: int | None,
    gpu_cores: int | None,
    memory_gb: int | None,
    storage_gb: int | None,
) -> str | None:
    if is_garmin_watch_scope(business_domain):
        parts = [first_text(model_name, product_line)]
        if case_size_mm is not None:
            parts.append(f"{case_size_mm}mm")
        if display_type:
            parts.append(display_type)
        if is_solar is True:
            parts.append("Solar")
        return " / ".join(part for part in parts if part)

    if is_apple_computer_scope(business_domain):
        parts = [first_text(model_name, product_line)]
        if screen_size_in is not None:
            parts.append(f"{screen_size_in:.1f}in")
        if chip_family:
            parts.append(chip_family)
        if memory_gb is not None:
            parts.append(f"{memory_gb}GB")
        if storage_gb is not None:
            parts.append(f"{storage_gb}GB")
        if cpu_cores is not None and gpu_cores is not None:
            parts.append(f"{cpu_cores}C/{gpu_cores}G")
        return " / ".join(part for part in parts if part)

    return first_text(model_name, product_line)


def classify_calibration_bucket_tags(
    *,
    review_prediction: dict[str, Any],
    pricing_context: dict[str, Any],
) -> list[str]:
    tags: list[str] = []
    status = review_prediction.get("status")
    if status == REVIEW_STATUS_VALID and not review_prediction.get("needs_audit"):
        tags.append(CALIBRATION_BUCKET_VALID)
    if status == REVIEW_STATUS_INVALID:
        tags.append(CALIBRATION_BUCKET_INVALID)
    if status == REVIEW_STATUS_PENDING_AUDIT or review_prediction.get("needs_audit"):
        tags.append(CALIBRATION_BUCKET_PENDING_AUDIT)
    if pricing_context.get("is_high_profit_high_risk_candidate"):
        tags.append(CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK)
    return tags


def infer_calibration_route_hint(
    *,
    review_prediction: dict[str, Any],
    pricing_context: dict[str, Any],
    bucket_tags: list[str],
) -> str:
    if CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK in bucket_tags:
        return "dense_or_manual_profit_sensitive"
    if (
        CALIBRATION_BUCKET_PENDING_AUDIT in bucket_tags
        or pricing_context.get("pricing_gate_exclusion_reason") in {"pending_audit", "low_confidence"}
    ):
        return "dense_second_pass_candidate"
    status = review_prediction.get("status")
    if status in {REVIEW_STATUS_VALID, REVIEW_STATUS_INVALID}:
        return "qwen3_first_pass_benchmark"
    return "needs_triage"


def default_calibration_annotation() -> dict[str, Any]:
    return {
        "review_status": None,
        "pricing_safe": None,
        "risk_level": None,
        "needs_dense_second_pass": None,
        "needs_manual_tail_review": None,
        "reviewer": None,
        "reviewed_at": None,
        "notes": None,
    }


def select_calibration_samples(
    *,
    candidates: list[dict[str, Any]],
    bucket_limits: dict[str, int],
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    available_counts = {
        bucket: sum(1 for candidate in candidates if bucket in candidate.get("bucket_tags", []))
        for bucket in CALIBRATION_BUCKET_PRIORITY
    }
    selected_samples: list[dict[str, Any]] = []
    selected_item_ids: set[str] = set()
    picked_counts: dict[str, int] = {}

    for bucket in CALIBRATION_BUCKET_PRIORITY:
        limit = max(int(bucket_limits.get(bucket, 0) or 0), 0)
        bucket_candidates = [
            candidate
            for candidate in candidates
            if bucket in candidate.get("bucket_tags", [])
            and candidate.get("item_id") not in selected_item_ids
        ]
        picked = balanced_sample_by_domain(
            candidates=bucket_candidates,
            limit=limit,
            rng=rng,
        )
        picked_counts[bucket] = len(picked)
        for candidate in picked:
            sample = dict(candidate)
            sample["bucket"] = bucket
            selected_samples.append(sample)
            selected_item_ids.add(sample["item_id"])

    selected_samples.sort(
        key=lambda sample: (
            CALIBRATION_BUCKET_PRIORITY.index(sample["bucket"]),
            sample.get("business_domain") or "",
            sample.get("item_id") or "",
        )
    )
    for index, sample in enumerate(selected_samples, start=1):
        sample["sample_id"] = f"cal-{index:04d}"
        sample["sampling_reason"] = sample["bucket"]

    selection_summary = {
        "available_counts": available_counts,
        "picked_counts": picked_counts,
        "selected_total": len(selected_samples),
        "selected_by_domain": dict(Counter(sample.get("business_domain") or "unknown" for sample in selected_samples)),
    }
    return selected_samples, selection_summary


def balanced_sample_by_domain(
    *,
    candidates: list[dict[str, Any]],
    limit: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    if limit <= 0 or not candidates:
        return []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        domain = str(candidate.get("business_domain") or "unknown")
        grouped[domain].append(candidate)
    domains = sorted(grouped)
    for domain in domains:
        rng.shuffle(grouped[domain])

    picked: list[dict[str, Any]] = []
    while len(picked) < limit:
        progressed = False
        for domain in domains:
            pool = grouped[domain]
            if not pool:
                continue
            picked.append(pool.pop())
            progressed = True
            if len(picked) >= limit:
                break
        if not progressed:
            break
    return picked


def persist_review_calibration_export(
    *,
    output: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = build_calibration_csv_sidecar_path(output)
    rows = build_calibration_csv_rows(payload.get("samples") or [])
    fieldnames = CALIBRATION_CSV_FIELDS
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return {
        "json_path": str(output),
        "csv_path": str(csv_path),
    }


def build_calibration_csv_sidecar_path(path: Path) -> Path:
    suffix = path.suffix or ".json"
    return path.with_name(f"{path.stem}.annotation{'.csv' if suffix else '.csv'}")


CALIBRATION_CSV_FIELDS = (
    "sample_id",
    "bucket",
    "bucket_tags",
    "route_hint",
    "item_id",
    "business_domain",
    "source_keyword",
    "title",
    "current_price",
    "region",
    "condition_tags",
    "listing_description",
    "review_status",
    "review_confidence",
    "review_needs_audit",
    "review_reason",
    "review_audit_reason",
    "pricing_gate_exclusion_reason",
    "pricing_eligible",
    "matched_view",
    "matched_label",
    "matched_group_fair_price",
    "matched_group_target_buy_ceiling",
    "matched_group_required_profit_amount",
    "apparent_profit_to_fair_price",
    "apparent_margin_pct_to_fair_price",
    "is_high_profit_high_risk_candidate",
    "annotation_review_status",
    "annotation_pricing_safe",
    "annotation_risk_level",
    "annotation_needs_dense_second_pass",
    "annotation_needs_manual_tail_review",
    "annotation_reviewer",
    "annotation_reviewed_at",
    "annotation_notes",
)


def build_calibration_csv_rows(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sample in samples:
        review_prediction = sample.get("review_prediction") or {}
        pricing_context = sample.get("pricing_context") or {}
        annotation = sample.get("annotation") or {}
        rows.append(
            {
                "sample_id": sample.get("sample_id"),
                "bucket": sample.get("bucket"),
                "bucket_tags": ",".join(sample.get("bucket_tags") or []),
                "route_hint": sample.get("route_hint"),
                "item_id": sample.get("item_id"),
                "business_domain": sample.get("business_domain"),
                "source_keyword": sample.get("source_keyword"),
                "title": sample.get("title"),
                "current_price": sample.get("current_price"),
                "region": sample.get("region"),
                "condition_tags": ",".join(sample.get("condition_tags") or []),
                "listing_description": sample.get("listing_description"),
                "review_status": review_prediction.get("status"),
                "review_confidence": review_prediction.get("confidence"),
                "review_needs_audit": review_prediction.get("needs_audit"),
                "review_reason": review_prediction.get("reason"),
                "review_audit_reason": review_prediction.get("audit_reason"),
                "pricing_gate_exclusion_reason": pricing_context.get("pricing_gate_exclusion_reason"),
                "pricing_eligible": pricing_context.get("eligible_for_pricing"),
                "matched_view": pricing_context.get("matched_view"),
                "matched_label": pricing_context.get("matched_label"),
                "matched_group_fair_price": pricing_context.get("matched_group_fair_price"),
                "matched_group_target_buy_ceiling": pricing_context.get("matched_group_target_buy_ceiling"),
                "matched_group_required_profit_amount": pricing_context.get("matched_group_required_profit_amount"),
                "apparent_profit_to_fair_price": pricing_context.get("apparent_profit_to_fair_price"),
                "apparent_margin_pct_to_fair_price": pricing_context.get("apparent_margin_pct_to_fair_price"),
                "is_high_profit_high_risk_candidate": pricing_context.get("is_high_profit_high_risk_candidate"),
                "annotation_review_status": annotation.get("review_status"),
                "annotation_pricing_safe": annotation.get("pricing_safe"),
                "annotation_risk_level": annotation.get("risk_level"),
                "annotation_needs_dense_second_pass": annotation.get("needs_dense_second_pass"),
                "annotation_needs_manual_tail_review": annotation.get("needs_manual_tail_review"),
                "annotation_reviewer": annotation.get("reviewer"),
                "annotation_reviewed_at": annotation.get("reviewed_at"),
                "annotation_notes": annotation.get("notes"),
            }
        )
    return rows


def load_review_calibration_entries(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [calibration_entry_from_csv_row(row) for row in reader]

    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        samples = raw.get("samples")
        if isinstance(samples, list):
            return [coerce_calibration_entry(sample) for sample in samples]
        raise RuntimeError("Calibration JSON object must contain a samples array.")
    if isinstance(raw, list):
        return [coerce_calibration_entry(sample) for sample in raw]
    raise RuntimeError("Calibration input must be a JSON object or JSON array.")


def calibration_entry_from_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": row.get("sample_id"),
        "bucket": row.get("bucket"),
        "bucket_tags": [part for part in str(row.get("bucket_tags") or "").split(",") if part],
        "route_hint": row.get("route_hint"),
        "item_id": row.get("item_id"),
        "business_domain": row.get("business_domain"),
        "source_keyword": row.get("source_keyword"),
        "title": row.get("title"),
        "current_price": parse_optional_float(row.get("current_price")),
        "region": row.get("region"),
        "condition_tags": [part for part in str(row.get("condition_tags") or "").split(",") if part],
        "listing_description": row.get("listing_description"),
        "review_prediction": {
            "status": row.get("review_status"),
            "confidence": parse_optional_float(row.get("review_confidence")),
            "needs_audit": parse_optional_bool(row.get("review_needs_audit")),
            "reason": row.get("review_reason"),
            "audit_reason": row.get("review_audit_reason"),
        },
        "pricing_context": {
            "pricing_gate_exclusion_reason": row.get("pricing_gate_exclusion_reason"),
            "eligible_for_pricing": parse_optional_bool(row.get("pricing_eligible")),
            "matched_view": row.get("matched_view"),
            "matched_label": row.get("matched_label"),
            "matched_group_fair_price": parse_optional_float(row.get("matched_group_fair_price")),
            "matched_group_target_buy_ceiling": parse_optional_float(row.get("matched_group_target_buy_ceiling")),
            "matched_group_required_profit_amount": parse_optional_float(row.get("matched_group_required_profit_amount")),
            "apparent_profit_to_fair_price": parse_optional_float(row.get("apparent_profit_to_fair_price")),
            "apparent_margin_pct_to_fair_price": parse_optional_float(row.get("apparent_margin_pct_to_fair_price")),
            "is_high_profit_high_risk_candidate": parse_optional_bool(row.get("is_high_profit_high_risk_candidate")),
        },
        "annotation": {
            "review_status": row.get("annotation_review_status") or None,
            "pricing_safe": parse_optional_bool(row.get("annotation_pricing_safe")),
            "risk_level": row.get("annotation_risk_level") or None,
            "needs_dense_second_pass": parse_optional_bool(row.get("annotation_needs_dense_second_pass")),
            "needs_manual_tail_review": parse_optional_bool(row.get("annotation_needs_manual_tail_review")),
            "reviewer": row.get("annotation_reviewer") or None,
            "reviewed_at": row.get("annotation_reviewed_at") or None,
            "notes": row.get("annotation_notes") or None,
        },
    }


def coerce_calibration_entry(entry: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(entry)
    review_prediction = dict(coerced.get("review_prediction") or {})
    pricing_context = dict(coerced.get("pricing_context") or {})
    annotation = dict(default_calibration_annotation())
    annotation.update(coerced.get("annotation") or {})
    review_prediction["confidence"] = parse_optional_float(review_prediction.get("confidence"))
    review_prediction["needs_audit"] = parse_optional_bool(review_prediction.get("needs_audit"))
    pricing_context["eligible_for_pricing"] = parse_optional_bool(pricing_context.get("eligible_for_pricing"))
    pricing_context["is_high_profit_high_risk_candidate"] = parse_optional_bool(
        pricing_context.get("is_high_profit_high_risk_candidate")
    )
    pricing_context["matched_group_fair_price"] = parse_optional_float(pricing_context.get("matched_group_fair_price"))
    pricing_context["matched_group_required_profit_amount"] = parse_optional_float(
        pricing_context.get("matched_group_required_profit_amount")
    )
    pricing_context["apparent_profit_to_fair_price"] = parse_optional_float(
        pricing_context.get("apparent_profit_to_fair_price")
    )
    pricing_context["apparent_margin_pct_to_fair_price"] = parse_optional_float(
        pricing_context.get("apparent_margin_pct_to_fair_price")
    )
    annotation["pricing_safe"] = parse_optional_bool(annotation.get("pricing_safe"))
    annotation["needs_dense_second_pass"] = parse_optional_bool(annotation.get("needs_dense_second_pass"))
    annotation["needs_manual_tail_review"] = parse_optional_bool(annotation.get("needs_manual_tail_review"))
    coerced["review_prediction"] = review_prediction
    coerced["pricing_context"] = pricing_context
    coerced["annotation"] = annotation
    return coerced


def parse_optional_bool(value: Any) -> bool | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def parse_optional_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_review_calibration_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    coerced_entries = [coerce_calibration_entry(entry) for entry in entries]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_sample_ids: set[str] = set()
    seen_item_ids: set[str] = set()

    for index, entry in enumerate(coerced_entries, start=1):
        sample_id = entry.get("sample_id")
        item_id = entry.get("item_id")
        bucket = entry.get("bucket")
        route_hint = entry.get("route_hint")
        annotation = entry.get("annotation") or {}
        review_prediction = entry.get("review_prediction") or {}

        location = {
            "index": index,
            "sample_id": sample_id,
            "item_id": item_id,
        }

        if not sample_id:
            errors.append({"code": "missing_sample_id", **location})
        elif sample_id in seen_sample_ids:
            errors.append({"code": "duplicate_sample_id", **location})
        else:
            seen_sample_ids.add(sample_id)

        if not item_id:
            errors.append({"code": "missing_item_id", **location})
        elif item_id in seen_item_ids:
            errors.append({"code": "duplicate_item_id", **location})
        else:
            seen_item_ids.add(item_id)

        if bucket not in CALIBRATION_BUCKET_VALUES:
            errors.append({"code": "invalid_bucket", "value": bucket, **location})

        if not route_hint:
            warnings.append({"code": "missing_route_hint", **location})

        review_status = annotation.get("review_status")
        if review_status is not None and review_status not in CALIBRATION_REVIEW_STATUS_VALUES:
            errors.append({"code": "invalid_annotation_review_status", "value": review_status, **location})

        risk_level = annotation.get("risk_level")
        if risk_level is not None and risk_level not in CALIBRATION_RISK_LEVEL_VALUES:
            errors.append({"code": "invalid_annotation_risk_level", "value": risk_level, **location})

        pricing_safe = annotation.get("pricing_safe")
        if pricing_safe is None and review_status == REVIEW_STATUS_VALID:
            warnings.append({"code": "missing_pricing_safe_for_human_valid", **location})

        if pricing_safe is True and review_status == REVIEW_STATUS_INVALID:
            warnings.append({"code": "pricing_safe_true_but_human_invalid", **location})

        if review_prediction.get("status") == REVIEW_STATUS_PENDING_AUDIT and review_status == REVIEW_STATUS_VALID:
            warnings.append({"code": "human_rescued_pending_audit", **location})

        if bucket == CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK and pricing_safe is False:
            warnings.append({"code": "high_profit_high_risk_marked_not_pricing_safe", **location})

    return {
        "entry_count": len(coerced_entries),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "valid": len(errors) == 0,
    }


def evaluate_review_calibration_set(
    *,
    entries: list[dict[str, Any]],
    valid_thresholds: list[float] | None = None,
    invalid_thresholds: list[float] | None = None,
    pricing_thresholds: list[float] | None = None,
) -> dict[str, Any]:
    coerced_entries = [coerce_calibration_entry(entry) for entry in entries]
    validation_summary = validate_review_calibration_entries(coerced_entries)
    review_labeled_entries = [
        entry
        for entry in coerced_entries
        if (entry.get("annotation") or {}).get("review_status") in CALIBRATION_REVIEW_STATUS_VALUES
    ]
    pricing_labeled_entries = [
        entry
        for entry in coerced_entries
        if (entry.get("annotation") or {}).get("pricing_safe") is not None
    ]

    valid_sweep_values = unique_sorted_thresholds(
        valid_thresholds or [0.85, 0.88, LLM_REVIEW_VALID_CONFIDENCE, 0.92, PRICING_VALID_CONFIDENCE, 0.97]
    )
    invalid_sweep_values = unique_sorted_thresholds(
        invalid_thresholds or [0.20, 0.25, LLM_REVIEW_INVALID_MAX_CONFIDENCE, 0.35, 0.40]
    )
    pricing_sweep_values = unique_sorted_thresholds(
        pricing_thresholds or [LLM_REVIEW_VALID_CONFIDENCE, 0.93, PRICING_VALID_CONFIDENCE, 0.97]
    )

    current_policy_metrics = {
        "auto_valid": summarize_auto_valid_precision(
            entries=coerced_entries,
            threshold=LLM_REVIEW_VALID_CONFIDENCE,
        ),
        "auto_invalid": summarize_auto_invalid_precision(
            entries=coerced_entries,
            threshold=LLM_REVIEW_INVALID_MAX_CONFIDENCE,
        ),
        "pricing_pool": summarize_pricing_pool_precision(
            entries=coerced_entries,
            threshold=PRICING_VALID_CONFIDENCE,
        ),
    }

    return {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "entry_count": len(coerced_entries),
        "validation": validation_summary,
        "review_labeled_count": len(review_labeled_entries),
        "pricing_labeled_count": len(pricing_labeled_entries),
        "label_completion": {
            "review_status": ratio(len(review_labeled_entries), len(coerced_entries)),
            "pricing_safe": ratio(len(pricing_labeled_entries), len(coerced_entries)),
            "needs_dense_second_pass": ratio(
                sum(
                    1
                    for entry in coerced_entries
                    if (entry.get("annotation") or {}).get("needs_dense_second_pass") is not None
                ),
                len(coerced_entries),
            ),
            "needs_manual_tail_review": ratio(
                sum(
                    1
                    for entry in coerced_entries
                    if (entry.get("annotation") or {}).get("needs_manual_tail_review") is not None
                ),
                len(coerced_entries),
            ),
        },
        "human_label_distribution": {
            "review_status": dict(
                Counter((entry.get("annotation") or {}).get("review_status") for entry in review_labeled_entries)
            ),
            "pricing_safe": {
                "true": sum(1 for entry in pricing_labeled_entries if (entry.get("annotation") or {}).get("pricing_safe") is True),
                "false": sum(1 for entry in pricing_labeled_entries if (entry.get("annotation") or {}).get("pricing_safe") is False),
            },
        },
        "current_policy_metrics": current_policy_metrics,
        "threshold_sweeps": {
            "auto_valid_precision": [
                summarize_auto_valid_precision(entries=coerced_entries, threshold=threshold)
                for threshold in valid_sweep_values
            ],
            "auto_invalid_precision": [
                summarize_auto_invalid_precision(entries=coerced_entries, threshold=threshold)
                for threshold in invalid_sweep_values
            ],
            "pricing_pool_precision": [
                summarize_pricing_pool_precision(entries=coerced_entries, threshold=threshold)
                for threshold in pricing_sweep_values
            ],
        },
        "bucket_breakdown": summarize_bucket_breakdown(coerced_entries),
        "model_lane_observations": summarize_model_lane_observations(coerced_entries),
    }


def summarize_auto_valid_precision(
    *,
    entries: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    selected = [
        entry
        for entry in entries
        if entry_auto_valid(entry, threshold=threshold)
    ]
    labeled = [entry for entry in selected if (entry.get("annotation") or {}).get("review_status") in CALIBRATION_REVIEW_STATUS_VALUES]
    valid_hits = sum(1 for entry in labeled if (entry.get("annotation") or {}).get("review_status") == REVIEW_STATUS_VALID)
    pending_hits = sum(1 for entry in labeled if (entry.get("annotation") or {}).get("review_status") == REVIEW_STATUS_PENDING_AUDIT)
    pricing_safe_hits = sum(
        1 for entry in selected if (entry.get("annotation") or {}).get("pricing_safe") is True
    )
    pricing_labeled_count = sum(
        1 for entry in selected if (entry.get("annotation") or {}).get("pricing_safe") is not None
    )
    return {
        "threshold": threshold,
        "selected_count": len(selected),
        "review_labeled_count": len(labeled),
        "precision_valid": ratio(valid_hits, len(labeled)),
        "pending_rate_within_selected": ratio(pending_hits, len(labeled)),
        "pricing_safe_labeled_count": pricing_labeled_count,
        "pricing_safe_precision": ratio(pricing_safe_hits, pricing_labeled_count),
    }


def summarize_auto_invalid_precision(
    *,
    entries: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    selected = [
        entry
        for entry in entries
        if entry_auto_invalid(entry, threshold=threshold)
    ]
    labeled = [entry for entry in selected if (entry.get("annotation") or {}).get("review_status") in CALIBRATION_REVIEW_STATUS_VALUES]
    invalid_hits = sum(1 for entry in labeled if (entry.get("annotation") or {}).get("review_status") == REVIEW_STATUS_INVALID)
    pending_hits = sum(1 for entry in labeled if (entry.get("annotation") or {}).get("review_status") == REVIEW_STATUS_PENDING_AUDIT)
    return {
        "threshold": threshold,
        "selected_count": len(selected),
        "review_labeled_count": len(labeled),
        "precision_invalid": ratio(invalid_hits, len(labeled)),
        "pending_rate_within_selected": ratio(pending_hits, len(labeled)),
    }


def summarize_pricing_pool_precision(
    *,
    entries: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    selected = [
        entry
        for entry in entries
        if entry_in_pricing_pool(entry, threshold=threshold)
    ]
    pricing_labeled = [entry for entry in selected if (entry.get("annotation") or {}).get("pricing_safe") is not None]
    pricing_safe_hits = sum(1 for entry in pricing_labeled if (entry.get("annotation") or {}).get("pricing_safe") is True)
    review_labeled = [entry for entry in selected if (entry.get("annotation") or {}).get("review_status") in CALIBRATION_REVIEW_STATUS_VALUES]
    review_valid_hits = sum(
        1 for entry in review_labeled if (entry.get("annotation") or {}).get("review_status") == REVIEW_STATUS_VALID
    )
    return {
        "threshold": threshold,
        "selected_count": len(selected),
        "pricing_labeled_count": len(pricing_labeled),
        "pricing_safe_precision": ratio(pricing_safe_hits, len(pricing_labeled)),
        "review_labeled_count": len(review_labeled),
        "review_valid_precision": ratio(review_valid_hits, len(review_labeled)),
    }


def entry_auto_valid(entry: dict[str, Any], *, threshold: float) -> bool:
    review_prediction = entry.get("review_prediction") or {}
    confidence = parse_optional_float(review_prediction.get("confidence"))
    needs_audit = parse_optional_bool(review_prediction.get("needs_audit"))
    return (
        review_prediction.get("status") == REVIEW_STATUS_VALID
        and not needs_audit
        and confidence is not None
        and confidence >= threshold
    )


def entry_auto_invalid(entry: dict[str, Any], *, threshold: float) -> bool:
    review_prediction = entry.get("review_prediction") or {}
    confidence = parse_optional_float(review_prediction.get("confidence"))
    return (
        review_prediction.get("status") == REVIEW_STATUS_INVALID
        and confidence is not None
        and confidence <= threshold
    )


def entry_in_pricing_pool(entry: dict[str, Any], *, threshold: float) -> bool:
    review_prediction = entry.get("review_prediction") or {}
    confidence = parse_optional_float(review_prediction.get("confidence"))
    needs_audit = parse_optional_bool(review_prediction.get("needs_audit"))
    return (
        review_prediction.get("status") == REVIEW_STATUS_VALID
        and not needs_audit
        and confidence is not None
        and confidence >= threshold
    )


def summarize_bucket_breakdown(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[str(entry.get("bucket") or "unbucketed")].append(entry)
    rows: list[dict[str, Any]] = []
    for bucket, bucket_entries in sorted(grouped.items()):
        review_labeled = [
            entry
            for entry in bucket_entries
            if (entry.get("annotation") or {}).get("review_status") in CALIBRATION_REVIEW_STATUS_VALUES
        ]
        pricing_labeled = [
            entry
            for entry in bucket_entries
            if (entry.get("annotation") or {}).get("pricing_safe") is not None
        ]
        rows.append(
            {
                "bucket": bucket,
                "count": len(bucket_entries),
                "review_labeled_count": len(review_labeled),
                "review_status_distribution": dict(
                    Counter((entry.get("annotation") or {}).get("review_status") for entry in review_labeled)
                ),
                "pricing_labeled_count": len(pricing_labeled),
                "pricing_safe_true_count": sum(
                    1 for entry in pricing_labeled if (entry.get("annotation") or {}).get("pricing_safe") is True
                ),
                "pricing_safe_false_count": sum(
                    1 for entry in pricing_labeled if (entry.get("annotation") or {}).get("pricing_safe") is False
                ),
            }
        )
    return rows


def summarize_model_lane_observations(entries: list[dict[str, Any]]) -> dict[str, Any]:
    review_labeled_entries = [
        entry
        for entry in entries
        if (entry.get("annotation") or {}).get("review_status") in CALIBRATION_REVIEW_STATUS_VALUES
    ]
    dense_candidates = [
        entry
        for entry in review_labeled_entries
        if (
            (entry.get("annotation") or {}).get("needs_dense_second_pass") is True
            or (
                (entry.get("annotation") or {}).get("review_status") == REVIEW_STATUS_VALID
                and (
                    entry.get("bucket") in {CALIBRATION_BUCKET_PENDING_AUDIT, CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK}
                    or not entry_auto_valid(entry, threshold=LLM_REVIEW_VALID_CONFIDENCE)
                )
            )
        )
    ]
    manual_tail_candidates = [
        entry
        for entry in review_labeled_entries
        if (
            (entry.get("annotation") or {}).get("needs_manual_tail_review") is True
            or (
                entry.get("bucket") == CALIBRATION_BUCKET_HIGH_PROFIT_HIGH_RISK
                and (
                    (entry.get("annotation") or {}).get("review_status") == REVIEW_STATUS_PENDING_AUDIT
                    or (entry.get("annotation") or {}).get("pricing_safe") is False
                )
            )
        )
    ]
    return {
        "review_labeled_count": len(review_labeled_entries),
        "dense_second_pass_candidate_count": len(dense_candidates),
        "dense_second_pass_candidate_ratio": ratio(len(dense_candidates), len(review_labeled_entries)),
        "manual_tail_candidate_count": len(manual_tail_candidates),
        "manual_tail_candidate_ratio": ratio(len(manual_tail_candidates), len(review_labeled_entries)),
        "dense_second_pass_candidate_buckets": dict(Counter(entry.get("bucket") for entry in dense_candidates)),
        "manual_tail_candidate_buckets": dict(Counter(entry.get("bucket") for entry in manual_tail_candidates)),
        "recommended_model_split": {
            "first_pass": "Qwen3 for broad throughput screening",
            "second_pass_dense": "Use a denser model for pending_audit and profit-sensitive candidates that humans still judge as valid",
            "manual_tail": "Reserve manual or third-pass review for high-profit high-risk samples that remain ambiguous or unsafe for pricing",
        },
    }


def unique_sorted_thresholds(values: list[float]) -> list[float]:
    normalized = sorted({round(float(value), 4) for value in values})
    return normalized


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _load_calibration_source_rows(
    *,
    session,
    business_domain: str | None,
    freshness_days: int,
) -> list[tuple[Item, ItemSpecEnrichment | None, dict[str, Any] | None]]:
    cutoff = datetime.now(UTC) - timedelta(days=max(freshness_days, 1))
    stmt = (
        select(Item, ItemSpecEnrichment, RawResponse.response_body)
        .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
        .outerjoin(RawResponse, RawResponse.id == Item.current_raw_response_id)
        .where(
            Item.current_price.is_not(None),
            Item.current_price > 0,
            Item.is_ad.is_(False),
            Item.is_auction.is_(False),
            Item.last_seen_at >= cutoff,
        )
        .order_by(desc(Item.last_seen_at), desc(Item.id))
    )
    scope_keys = compatible_scope_keys(business_domain)
    if scope_keys:
        stmt = stmt.where(Item.business_domain.in_(scope_keys))
    return list(session.execute(stmt).all())
