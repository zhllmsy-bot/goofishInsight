from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, or_, select
from sqlalchemy.dialects.postgresql import insert

from ...compat import UTC
from ...db import session_scope
from ...models import Category, CategoryRuntimeProfile, Item, ItemReviewV3
from .review_batches import build_review_input_signature
from .review_ingest import contains_suspicious_listing_keyword
from .review_queries import load_items_for_llm_review
from .review_v3_executor import execute_review_v3_prompt, review_v3_executor_is_configured
from .review_v3_mapping import (
    V3_STATUS_INVALID_OR_NOT_SUPPORTED,
    V3_STATUS_MANUAL_AUDIT_REQUIRED,
    V3_STATUS_PENDING_REVIEW,
    V3_STATUS_REJECTED_ACCESSORY,
    V3_STATUS_REJECTED_STATIC_GUARD,
    V3_STATUS_VALID_READY_FOR_PRICING,
    apply_second_pass_resolution,
    map_flat_features,
)
from .review_v3_profiles import (
    build_first_pass_batch_system_prompt,
    build_first_pass_batch_user_payload,
    build_first_pass_user_payload,
    build_second_pass_user_payload,
    get_review_v3_profile,
)

STATIC_BUYBACK_TOKENS = (
    "求购",
    "回收",
    "收购",
    "收机",
    "高价收",
)

STATIC_EXCHANGE_PATTERNS = (
    "以旧换新",
    "换购",
    "支持回收置换",
    "回收置换",
    "上门回收置换",
    "可回收置换",
)
FIRST_PASS_BATCH_ATTEMPTS = 3


def apply_review_v3_business_domain_override(
    *,
    rows_by_id: dict[str, dict[str, Any]],
    item_ids: list[str],
    business_domain: str | None,
) -> list[dict[str, Any]]:
    resolved_rows: list[dict[str, Any]] = []
    for current_item_id in item_ids:
        row = rows_by_id.get(current_item_id)
        if row is None:
            continue
        current_row = dict(row)
        if business_domain:
            current_row["source_business_domain"] = row.get("business_domain")
            current_row["business_domain"] = business_domain
        resolved_rows.append(current_row)
    return resolved_rows


def load_items_for_review_v3(
    *,
    business_domain: str | None,
    item_id: str | None,
    item_ids: list[str] | None = None,
    limit: int,
    force: bool,
) -> list[dict[str, Any]]:
    requested_item_ids = list(item_ids or [])
    with session_scope() as session:
        stmt = (
            select(Item.item_id)
            .outerjoin(ItemReviewV3, ItemReviewV3.item_id_ref == Item.id)
            .where(Item.is_active.is_(True))
            .order_by(desc(Item.last_seen_at), desc(Item.id))
        )
        if business_domain and not item_id:
            stmt = stmt.where(Item.business_domain == business_domain)
        if item_ids:
            stmt = stmt.where(Item.item_id.in_(item_ids))
        if item_id:
            stmt = stmt.where(Item.item_id == item_id)
        if not force:
            stmt = stmt.where(
                or_(
                    ItemReviewV3.id.is_(None),
                    ItemReviewV3.resolution_status.in_((V3_STATUS_PENDING_REVIEW,)),
                )
            )
        if limit > 0:
            stmt = stmt.limit(limit)
        selected_item_ids = list(session.execute(stmt).scalars())
    if not selected_item_ids:
        return []
    rows = load_items_for_llm_review(
        business_domain=None if selected_item_ids else business_domain,
        item_id=None,
        item_ids=selected_item_ids,
        limit=0,
        force=True,
    )
    rows_by_id = {row["item_id"]: row for row in rows}
    ordered_item_ids = requested_item_ids or selected_item_ids
    return apply_review_v3_business_domain_override(
        rows_by_id=rows_by_id,
        item_ids=ordered_item_ids,
        business_domain=business_domain,
    )


def load_pending_review_v3_items(
    *,
    business_domain: str | None,
    item_id: str | None,
    limit: int,
    force: bool,
) -> list[dict[str, Any]]:
    with session_scope() as session:
        stmt = (
            select(Item.item_id)
            .join(ItemReviewV3, ItemReviewV3.item_id_ref == Item.id)
            .where(Item.is_active.is_(True))
            .where(ItemReviewV3.resolution_status == V3_STATUS_PENDING_REVIEW)
            .where(ItemReviewV3.candidate_payload.is_not(None))
            .order_by(desc(Item.last_seen_at), desc(Item.id))
        )
        if business_domain and not item_id:
            stmt = stmt.where(Item.business_domain == business_domain)
        if item_id:
            stmt = stmt.where(Item.item_id == item_id)
        if not force:
            stmt = stmt.where(
                or_(
                    ItemReviewV3.second_pass_payload == {},
                    ItemReviewV3.second_pass_payload.is_(None),
                )
            )
        if limit > 0:
            stmt = stmt.limit(limit)
        item_ids = list(session.execute(stmt).scalars())
    if not item_ids:
        return []
    rows = load_items_for_llm_review(
        business_domain=None if item_ids else business_domain,
        item_id=None,
        item_ids=item_ids,
        limit=0,
        force=True,
    )
    rows_by_id = {row["item_id"]: row for row in rows}
    return apply_review_v3_business_domain_override(
        rows_by_id=rows_by_id,
        item_ids=item_ids,
        business_domain=business_domain,
    )


def evaluate_static_guard(item: dict[str, Any]) -> dict[str, Any] | None:
    title = str(item.get("title") or "").strip()
    if len(title) > 500:
        return {"status": V3_STATUS_REJECTED_STATIC_GUARD, "reason": "title_length_gt_500"}
    compact_title = "".join(title.split())
    if any(token in compact_title for token in STATIC_BUYBACK_TOKENS):
        return {"status": V3_STATUS_REJECTED_STATIC_GUARD, "reason": "buyback_or_exchange_post"}
    if any(pattern in compact_title for pattern in STATIC_EXCHANGE_PATTERNS):
        return {"status": V3_STATUS_REJECTED_STATIC_GUARD, "reason": "buyback_or_exchange_post"}
    if contains_suspicious_listing_keyword(title=title):
        return {"status": V3_STATUS_REJECTED_STATIC_GUARD, "reason": "suspicious_listing_keyword"}
    return None


def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = _strip_markdown_fence(text)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM output must be a JSON object")
    return payload


def extract_json_items(text: str) -> list[dict[str, Any]]:
    payload = extract_json_object(text)
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("LLM batch output must contain an items array")
    normalized_items: list[dict[str, Any]] = []
    for entry in items:
        if not isinstance(entry, dict):
            raise ValueError("Each batch result entry must be a JSON object")
        normalized_items.append(dict(entry))
    return normalized_items


def coerce_first_pass_features(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["is_main_product"] = bool(normalized.get("is_main_product"))
    for key in ("is_flawless", "is_solar", "has_anc"):
        value = normalized.get(key)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"null", "none", "unknown", ""}:
                normalized[key] = None
            else:
                normalized[key] = lowered in {"1", "true", "yes"}
        elif value is None:
            normalized[key] = None if key != "is_flawless" else False
        else:
            normalized[key] = bool(value)
    confidence = normalized.get("confidence_score")
    try:
        normalized["confidence_score"] = max(0.0, min(float(confidence), 1.0))
    except (TypeError, ValueError):
        normalized["confidence_score"] = 0.0
    for key in ("memory_gb", "storage_gb", "case_size_mm"):
        if normalized.get(key) is None:
            continue
        try:
            normalized[key] = int(normalized[key])
        except (TypeError, ValueError):
            normalized[key] = None
    return normalized


def coerce_second_pass_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["is_resolved"] = bool(normalized.get("is_resolved"))
    normalized["needs_human"] = bool(normalized.get("needs_human"))
    if normalized.get("resolved_model_code") is not None:
        normalized["resolved_model_code"] = str(normalized.get("resolved_model_code") or "").strip() or None
    if normalized.get("resolved_model_code") and not normalized.get("needs_human"):
        normalized["is_resolved"] = True
    confidence = normalized.get("confidence_score")
    try:
        normalized["confidence_score"] = max(0.0, min(float(confidence), 1.0))
    except (TypeError, ValueError):
        normalized["confidence_score"] = None
    return normalized


def persist_review_v3_row(*, item_row: Item, payload: dict[str, Any]) -> None:
    payload_data = dict(payload)
    effective_business_domain = payload_data.pop("business_domain", None) or item_row.business_domain
    with session_scope() as session:
        persisted_item = session.get(Item, item_row.id)
        if persisted_item is None:
            return
        stmt = (
            insert(ItemReviewV3)
            .values(item_id_ref=item_row.id, business_domain=effective_business_domain, **payload_data)
            .on_conflict_do_update(
                index_elements=[ItemReviewV3.item_id_ref],
                set_={**payload_data, "business_domain": effective_business_domain, "updated_at": datetime.now(UTC)},
            )
        )
        session.execute(stmt)
        apply_review_v3_compat_to_item(
            item_row=persisted_item,
            business_domain=effective_business_domain,
            payload=payload_data,
        )


def _load_review_v3_item_context(
    *,
    item: dict[str, Any],
    business_domain: str | None,
) -> tuple[Item, str | None, str | None]:
    with session_scope() as session:
        item_row = session.execute(select(Item).where(Item.item_id == item["item_id"])).scalar_one()
        target_category_id, target_template_id = resolve_review_v3_target_context(
            session,
            item_row=item_row,
            business_domain=business_domain,
        )
    return item_row, target_category_id, target_template_id


def _persist_review_v3_static_guard_result(
    *,
    item: dict[str, Any],
    item_row: Item,
    business_domain: str,
    target_category_id: str | None,
    target_template_id: str | None,
    static_guard: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "business_domain": business_domain,
        "category_id": target_category_id,
        "template_id": target_template_id,
        "pipeline_version": "v3",
        "stage_status": "first_pass_static_reject",
        "resolution_status": static_guard["status"],
        "reject_reason": static_guard["reason"],
        "first_pass_confidence": Decimal("0.00"),
        "extracted_features": {},
        "mapping_payload": {"reason": static_guard["reason"]},
        "candidate_payload": [],
        "second_pass_payload": {},
        "final_payload": {"static_guard": static_guard},
    }
    persist_review_v3_row(item_row=item_row, payload=payload)
    return {
        "item_id": item["item_id"],
        "business_domain": business_domain,
        "resolution_status": static_guard["status"],
        "reject_reason": static_guard["reason"],
        "llm_request_count": 0,
        "llm_usage": None,
    }


def _persist_review_v3_first_pass_features(
    *,
    item: dict[str, Any],
    item_row: Item,
    profile,
    target_category_id: str | None,
    target_template_id: str | None,
    features: dict[str, Any],
    llm_request_count: int,
    llm_usage: dict[str, Any] | None,
    llm_provider: str | None,
    llm_model: str | None,
) -> dict[str, Any]:
    with session_scope() as session:
        live_item_row = session.get(Item, item_row.id)
        if live_item_row is None:
            raise RuntimeError(f"Item disappeared before first-pass persist: {item['item_id']}")
        mapping = map_flat_features(session, item=live_item_row, profile=profile, features=features)
    first_pass_confidence = Decimal(str(features.get("confidence_score") or 0.0)).quantize(Decimal("0.0001"))
    persist_review_v3_row(
        item_row=item_row,
        payload={
            "business_domain": profile.business_domain,
            "category_id": target_category_id,
            "template_id": target_template_id,
            "model_catalog_id": mapping.model_catalog_id,
            "pipeline_version": "v3",
            "stage_status": "first_pass_complete",
            "resolution_status": mapping.resolution_status,
            "reject_reason": None if mapping.resolution_status != V3_STATUS_REJECTED_ACCESSORY else "not_main_product",
            "needs_human": False,
            "first_pass_confidence": first_pass_confidence,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "extracted_features": features,
            "mapping_payload": mapping.mapping_payload,
            "candidate_payload": mapping.candidate_payload,
            "second_pass_payload": {},
            "final_payload": {
                "first_pass": features,
                "mapping": mapping.mapping_payload,
            },
        },
    )
    return {
        "item_id": item["item_id"],
        "business_domain": item.get("business_domain"),
        "resolution_status": mapping.resolution_status,
        "model_catalog_id": mapping.model_catalog_id,
        "candidate_count": len(mapping.candidate_payload),
        "first_pass_confidence": float(first_pass_confidence),
        "llm_request_count": llm_request_count,
        "llm_usage": llm_usage,
    }


def _run_review_v3_first_pass_single_loaded_item(item: dict[str, Any]) -> dict[str, Any]:
    profile = get_review_v3_profile(item.get("business_domain"))
    if profile is None:
        return {
            "item_id": item.get("item_id"),
            "business_domain": item.get("business_domain"),
            "resolution_status": V3_STATUS_INVALID_OR_NOT_SUPPORTED,
            "reject_reason": "unsupported_business_domain",
        }
    item_row, target_category_id, target_template_id = _load_review_v3_item_context(
        item=item,
        business_domain=profile.business_domain,
    )
    static_guard = evaluate_static_guard(item)
    if static_guard is not None:
        return _persist_review_v3_static_guard_result(
            item=item,
            item_row=item_row,
            business_domain=profile.business_domain,
            target_category_id=target_category_id,
            target_template_id=target_template_id,
            static_guard=static_guard,
        )
    execution = execute_review_v3_prompt(
        profile=profile,
        phase="first_pass",
        user_payload=build_first_pass_user_payload(item=item),
    )
    features = coerce_first_pass_features(extract_json_object(execution.content))
    return _persist_review_v3_first_pass_features(
        item=item,
        item_row=item_row,
        profile=profile,
        target_category_id=target_category_id,
        target_template_id=target_template_id,
        features=features,
        llm_request_count=1,
        llm_usage=execution.usage,
        llm_provider=execution.provider,
        llm_model=execution.model,
    )


def _coerce_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.0001"))
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except Exception:
        return None


def build_review_v3_compat_payload(
    *,
    item_row: Item,
    business_domain: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    resolution_status = str(payload.get("resolution_status") or "").strip().upper()
    reject_reason = str(payload.get("reject_reason") or "").strip() or None
    first_pass_confidence = _coerce_decimal(payload.get("first_pass_confidence"))
    second_pass_confidence = _coerce_decimal(payload.get("second_pass_confidence"))
    effective_confidence = second_pass_confidence or first_pass_confidence
    if resolution_status == V3_STATUS_VALID_READY_FOR_PRICING:
        compat_status = "valid"
        compat_reviewed = True
        compat_needs_audit = False
        compat_confidence = max(effective_confidence or Decimal("0.9500"), Decimal("0.9500"))
        compat_reason = None
        compat_audit_reason = None
    elif resolution_status in {
        V3_STATUS_REJECTED_ACCESSORY,
        V3_STATUS_REJECTED_STATIC_GUARD,
        V3_STATUS_INVALID_OR_NOT_SUPPORTED,
    }:
        compat_status = "invalid"
        compat_reviewed = True
        compat_needs_audit = False
        compat_confidence = effective_confidence or Decimal("0.1000")
        compat_reason = reject_reason or resolution_status.lower()
        compat_audit_reason = None
    elif resolution_status == V3_STATUS_MANUAL_AUDIT_REQUIRED:
        compat_status = "pending_audit"
        compat_reviewed = True
        compat_needs_audit = True
        compat_confidence = None
        compat_reason = "pending_audit"
        compat_audit_reason = reject_reason or resolution_status.lower()
    else:
        compat_status = "pending"
        compat_reviewed = False
        compat_needs_audit = False
        compat_confidence = None
        compat_reason = None
        compat_audit_reason = None

    review_input = {
        "item_id": item_row.item_id,
        "business_domain": business_domain,
        "source_business_domain": item_row.business_domain,
        "pipeline_version": str(payload.get("pipeline_version") or "v3"),
        "features": dict(payload.get("extracted_features") or {}),
    }
    review_input_signature = build_review_input_signature(review_input)
    review_decision = {
        "engine": "review_v3",
        "business_domain": business_domain,
        "resolution_status": resolution_status,
        "stage_status": payload.get("stage_status"),
        "model_catalog_id": str(payload.get("model_catalog_id") or "") or None,
        "reject_reason": reject_reason,
        "needs_human": bool(payload.get("needs_human")),
    }
    return {
        "llm_reviewed": compat_reviewed,
        "llm_review_status": compat_status,
        "llm_review_reason": compat_reason,
        "llm_reviewed_at": datetime.now(UTC) if compat_reviewed else None,
        "llm_review_confidence": compat_confidence,
        "llm_review_input": review_input,
        "llm_review_input_signature": review_input_signature,
        "llm_review_needs_audit": compat_needs_audit,
        "llm_review_audit_reason": compat_audit_reason,
        "llm_review_decision": review_decision,
    }


def apply_review_v3_compat_to_item(
    *,
    item_row: Item,
    business_domain: str,
    payload: dict[str, Any],
) -> None:
    compat_payload = build_review_v3_compat_payload(
        item_row=item_row,
        business_domain=business_domain,
        payload=payload,
    )
    for key, value in compat_payload.items():
        setattr(item_row, key, value)


def resolve_review_v3_target_context(
    session,
    *,
    item_row: Item,
    business_domain: str | None,
) -> tuple[str | None, str | None]:
    category = None
    if business_domain:
        category = session.execute(select(Category).where(Category.code == business_domain).limit(1)).scalar_one_or_none()
    if category is None and item_row.resolved_category_id:
        category = session.get(Category, item_row.resolved_category_id)
    if category is None and item_row.business_domain:
        category = session.execute(select(Category).where(Category.code == item_row.business_domain).limit(1)).scalar_one_or_none()
    category_id = str(category.id) if category is not None else item_row.resolved_category_id
    template_id = item_row.resolved_template_id
    if category_id:
        runtime_profile = session.execute(
            select(CategoryRuntimeProfile.active_template_id).where(
                CategoryRuntimeProfile.category_id == category_id,
                CategoryRuntimeProfile.status == "ACTIVE",
            )
        ).scalar_one_or_none()
        if runtime_profile:
            template_id = str(runtime_profile)
    return category_id, template_id


def run_review_v3_first_pass(
    *,
    business_domain: str | None,
    item_id: str | None,
    limit: int,
    force: bool,
) -> list[dict[str, Any]]:
    if not review_v3_executor_is_configured():
        raise RuntimeError("Review V3 executor is not configured.")

    items = load_items_for_review_v3(
        business_domain=business_domain,
        item_id=item_id,
        item_ids=None,
        limit=limit,
        force=force,
    )
    return [_run_review_v3_first_pass_single_loaded_item(item) for item in items]


def run_review_v3_first_pass_batch(
    *,
    business_domain: str,
    item_ids: list[str],
    force: bool,
) -> list[dict[str, Any]]:
    if not review_v3_executor_is_configured():
        raise RuntimeError("Review V3 executor is not configured.")

    profile = get_review_v3_profile(business_domain)
    if profile is None:
        raise RuntimeError(f"Unsupported business domain for first-pass batch: {business_domain}")

    items = load_items_for_review_v3(
        business_domain=business_domain,
        item_id=None,
        item_ids=item_ids,
        limit=0,
        force=force,
    )
    if not items:
        return []

    results: list[dict[str, Any]] = []
    llm_batch_items: list[dict[str, Any]] = []
    item_contexts: dict[str, tuple[Item, str | None, str | None]] = {}
    for item in items:
        item_row, target_category_id, target_template_id = _load_review_v3_item_context(
            item=item,
            business_domain=profile.business_domain,
        )
        item_contexts[item["item_id"]] = (item_row, target_category_id, target_template_id)
        static_guard = evaluate_static_guard(item)
        if static_guard is not None:
            results.append(
                _persist_review_v3_static_guard_result(
                    item=item,
                    item_row=item_row,
                    business_domain=profile.business_domain,
                    target_category_id=target_category_id,
                    target_template_id=target_template_id,
                    static_guard=static_guard,
                )
            )
            continue
        llm_batch_items.append(item)

    if not llm_batch_items:
        return results

    features_by_item_id: dict[str, dict[str, Any]] | None = None
    execution = None
    last_error: Exception | None = None
    for _ in range(FIRST_PASS_BATCH_ATTEMPTS):
        try:
            current_execution = execute_review_v3_prompt(
                profile=profile,
                phase="first_pass",
                user_payload=build_first_pass_batch_user_payload(
                    business_domain=profile.business_domain,
                    items=llm_batch_items,
                ),
                system_prompt_override=build_first_pass_batch_system_prompt(profile),
            )
            current_features_by_item_id: dict[str, dict[str, Any]] = {}
            for entry in extract_json_items(current_execution.content):
                current_item_id = str(entry.get("item_id") or "").strip()
                if not current_item_id:
                    continue
                current_features_by_item_id[current_item_id] = coerce_first_pass_features(entry)
            missing_item_ids = [
                item["item_id"] for item in llm_batch_items if item["item_id"] not in current_features_by_item_id
            ]
            if missing_item_ids:
                last_error = RuntimeError(
                    "first-pass batch response missing item_ids: " + ",".join(missing_item_ids)
                )
                continue
            execution = current_execution
            features_by_item_id = current_features_by_item_id
            break
        except Exception as exc:
            last_error = exc
            continue

    if features_by_item_id is None or execution is None:
        raise RuntimeError(
            f"first-pass batch failed for business_domain={business_domain}, item_ids={','.join(item_ids)}"
        ) from last_error

    llm_usage_consumed = False
    for item in llm_batch_items:
        features = features_by_item_id[item["item_id"]]
        item_row, target_category_id, target_template_id = item_contexts[item["item_id"]]
        results.append(
            _persist_review_v3_first_pass_features(
                item=item,
                item_row=item_row,
                profile=profile,
                target_category_id=target_category_id,
                target_template_id=target_template_id,
                features=features,
                llm_request_count=0 if llm_usage_consumed else 1,
                llm_usage=None if llm_usage_consumed or execution is None else execution.usage,
                llm_provider=None if execution is None else execution.provider,
                llm_model=None if execution is None else execution.model,
            )
        )
        llm_usage_consumed = True

    result_by_id = {result["item_id"]: result for result in results}
    return [result_by_id[item_id] for item_id in item_ids if item_id in result_by_id]


def run_review_v3_second_pass(
    *,
    business_domain: str | None,
    item_id: str | None,
    limit: int,
    force: bool,
) -> list[dict[str, Any]]:
    if not review_v3_executor_is_configured():
        raise RuntimeError("Review V3 executor is not configured.")

    items = load_pending_review_v3_items(
        business_domain=business_domain,
        item_id=item_id,
        limit=limit,
        force=force,
    )
    results: list[dict[str, Any]] = []
    for item in items:
        profile = get_review_v3_profile(item.get("business_domain"))
        if profile is None:
            continue
        with session_scope() as session:
            item_row = session.execute(select(Item).where(Item.item_id == item["item_id"])).scalar_one()
            review_row = session.execute(select(ItemReviewV3).where(ItemReviewV3.item_id_ref == item_row.id)).scalar_one()
            candidate_payload = list(review_row.candidate_payload or [])
            if not candidate_payload:
                persist_review_v3_row(
                    item_row=item_row,
                    payload={
                        "business_domain": review_row.business_domain,
                        "category_id": review_row.category_id,
                        "template_id": review_row.template_id,
                        "model_catalog_id": None,
                        "pipeline_version": review_row.pipeline_version,
                        "stage_status": "second_pass_skipped",
                        "resolution_status": V3_STATUS_INVALID_OR_NOT_SUPPORTED,
                        "reject_reason": "candidate_list_empty",
                        "needs_human": False,
                        "first_pass_confidence": review_row.first_pass_confidence,
                        "second_pass_confidence": None,
                        "llm_provider": review_row.llm_provider,
                        "llm_model": review_row.llm_model,
                        "extracted_features": review_row.extracted_features,
                        "mapping_payload": review_row.mapping_payload,
                        "candidate_payload": review_row.candidate_payload,
                        "second_pass_payload": {"reason": "candidate_list_empty"},
                        "final_payload": review_row.final_payload,
                    },
                )
                results.append(
                    {
                        "item_id": item["item_id"],
                        "business_domain": item.get("business_domain"),
                        "resolution_status": V3_STATUS_INVALID_OR_NOT_SUPPORTED,
                        "llm_request_count": 0,
                        "llm_usage": None,
                    }
                )
                continue

            execution = execute_review_v3_prompt(
                profile=profile,
                phase="second_pass",
                user_payload=build_second_pass_user_payload(
                    item=item,
                    first_pass_features=dict(review_row.extracted_features or {}),
                    catalog_candidates=candidate_payload,
                ),
            )
            review_payload = coerce_second_pass_payload(extract_json_object(execution.content))
            resolution_status, model_catalog_id, resolution_detail = apply_second_pass_resolution(
                candidate_payload=candidate_payload,
                review_payload=review_payload,
                features=dict(review_row.extracted_features or {}),
                profile=profile,
            )
            second_pass_confidence = review_payload.get("confidence_score")
            second_pass_decimal = None
            if second_pass_confidence is not None:
                second_pass_decimal = Decimal(str(second_pass_confidence)).quantize(Decimal("0.0001"))
            needs_human = bool(review_payload.get("needs_human")) or resolution_status == V3_STATUS_MANUAL_AUDIT_REQUIRED
            persist_review_v3_row(
                item_row=item_row,
                payload={
                    "business_domain": profile.business_domain,
                    "category_id": review_row.category_id,
                    "template_id": review_row.template_id,
                    "model_catalog_id": model_catalog_id,
                    "pipeline_version": review_row.pipeline_version,
                    "stage_status": "second_pass_complete",
                    "resolution_status": resolution_status,
                    "reject_reason": None if resolution_status == V3_STATUS_VALID_READY_FOR_PRICING else resolution_status.lower(),
                    "needs_human": needs_human,
                    "first_pass_confidence": review_row.first_pass_confidence,
                    "second_pass_confidence": second_pass_decimal,
                    "llm_provider": execution.provider,
                    "llm_model": execution.model,
                    "extracted_features": review_row.extracted_features,
                    "mapping_payload": review_row.mapping_payload,
                    "candidate_payload": review_row.candidate_payload,
                    "second_pass_payload": review_payload,
                    "final_payload": {
                        **dict(review_row.final_payload or {}),
                        "second_pass": review_payload,
                        "second_pass_resolution": resolution_detail,
                    },
                },
            )
            results.append(
                {
                    "item_id": item["item_id"],
                    "business_domain": item.get("business_domain"),
                    "resolution_status": resolution_status,
                    "model_catalog_id": model_catalog_id,
                    "llm_request_count": 1,
                    "llm_usage": execution.usage,
                }
            )
    return results


def sync_review_v3_compat_fields(
    *,
    business_domain: str | None,
    item_id: str | None,
    limit: int,
    dry_run: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with session_scope() as session:
        stmt = (
            select(ItemReviewV3, Item)
            .join(Item, Item.id == ItemReviewV3.item_id_ref)
            .order_by(desc(ItemReviewV3.updated_at), desc(Item.id))
        )
        if business_domain:
            stmt = stmt.where(ItemReviewV3.business_domain == business_domain)
        if item_id:
            stmt = stmt.where(Item.item_id == item_id)
        if limit > 0:
            stmt = stmt.limit(limit)

        rows = session.execute(stmt).all()
        for review_row, item_row in rows:
            payload = {
                "pipeline_version": review_row.pipeline_version,
                "stage_status": review_row.stage_status,
                "resolution_status": review_row.resolution_status,
                "model_catalog_id": review_row.model_catalog_id,
                "reject_reason": review_row.reject_reason,
                "needs_human": review_row.needs_human,
                "first_pass_confidence": review_row.first_pass_confidence,
                "second_pass_confidence": review_row.second_pass_confidence,
                "extracted_features": dict(review_row.extracted_features or {}),
            }
            compat_payload = build_review_v3_compat_payload(
                item_row=item_row,
                business_domain=review_row.business_domain,
                payload=payload,
            )
            results.append(
                {
                    "item_id": item_row.item_id,
                    "business_domain": review_row.business_domain,
                    "resolution_status": review_row.resolution_status,
                    "compat_status": compat_payload["llm_review_status"],
                    "compat_reviewed": bool(compat_payload["llm_reviewed"]),
                    "compat_needs_audit": bool(compat_payload["llm_review_needs_audit"]),
                }
            )
            if dry_run:
                continue
            for key, value in compat_payload.items():
                setattr(item_row, key, value)
        if dry_run:
            session.rollback()
    return results


def revalidate_review_v3_second_pass(
    *,
    business_domain: str | None,
    item_id: str | None,
    limit: int,
    dry_run: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with session_scope() as session:
        stmt = (
            select(Item, ItemReviewV3)
            .join(ItemReviewV3, ItemReviewV3.item_id_ref == Item.id)
            .where(ItemReviewV3.stage_status == "second_pass_complete")
            .order_by(desc(ItemReviewV3.updated_at), desc(Item.id))
        )
        if business_domain:
            stmt = stmt.where(Item.business_domain == business_domain)
        if item_id:
            stmt = stmt.where(Item.item_id == item_id)
        if limit > 0:
            stmt = stmt.limit(limit)

        rows = session.execute(stmt).all()
        for item_row, review_row in rows:
            profile = get_review_v3_profile(review_row.business_domain)
            if profile is None:
                continue
            resolution_status, model_catalog_id, resolution_detail = apply_second_pass_resolution(
                candidate_payload=list(review_row.candidate_payload or []),
                review_payload=dict(review_row.second_pass_payload or {}),
                features=dict(review_row.extracted_features or {}),
                profile=profile,
            )
            needs_human = resolution_status == V3_STATUS_MANUAL_AUDIT_REQUIRED
            changed = (
                resolution_status != review_row.resolution_status
                or model_catalog_id != review_row.model_catalog_id
                or needs_human != bool(review_row.needs_human)
            )
            results.append(
                {
                    "item_id": item_row.item_id,
                    "business_domain": review_row.business_domain,
                    "old_status": review_row.resolution_status,
                    "new_status": resolution_status,
                    "old_model_catalog_id": review_row.model_catalog_id,
                    "new_model_catalog_id": model_catalog_id,
                    "changed": changed,
                    "resolution": resolution_detail,
                }
            )
            if not changed:
                continue
            review_row.resolution_status = resolution_status
            review_row.model_catalog_id = model_catalog_id
            review_row.needs_human = needs_human
            review_row.reject_reason = None if resolution_status == V3_STATUS_VALID_READY_FOR_PRICING else resolution_status.lower()
            review_row.final_payload = {
                **dict(review_row.final_payload or {}),
                "second_pass_resolution": resolution_detail,
            }
            review_row.updated_at = datetime.now(UTC)

        if dry_run:
            session.rollback()
    return results
