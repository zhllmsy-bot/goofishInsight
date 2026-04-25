from __future__ import annotations

from datetime import datetime, timedelta
from ...compat import UTC
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, or_, select, update

from ...category_compat import compatible_scope_keys, resolve_category_code
from ...db import session_scope
from ...domain.review.contracts import (
    REVIEW_STATUS_IN_PROGRESS,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_PENDING_AUDIT,
    normalize_chip_text,
    normalize_display_type,
    normalize_text,
)
from ...models import Item, ItemSpecEnrichment, RawResponse
from ...specs import extract_item_specs

DESCRIPTION_LENGTH_LIMIT = 400
DESCRIPTION_CANDIDATE_KEYS = (
    "description",
    "desc",
    "content",
    "detail",
    "itemdesc",
    "item_desc",
    "desc_text",
    "description_text",
)


def _scope_keys_for_filter(business_domain: str | None) -> tuple[str, ...]:
    normalized = str(business_domain or "").strip()
    if not normalized:
        return ()
    return compatible_scope_keys(normalized)


def load_items_for_llm_review(
    *,
    business_domain: str | None,
    item_id: str | None,
    item_ids: list[str] | None = None,
    limit: int,
    force: bool,
) -> list[dict[str, Any]]:
    claimable_filter = build_claimable_review_filter(lease_seconds=1800)
    stmt = (
        select(Item, ItemSpecEnrichment, RawResponse.response_body)
        .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
        .outerjoin(RawResponse, RawResponse.id == Item.current_raw_response_id)
        .where(Item.is_active.is_(True))
        .order_by(desc(Item.last_seen_at), desc(Item.id))
    )
    scope_keys = _scope_keys_for_filter(business_domain)
    if scope_keys:
        stmt = stmt.where(Item.business_domain.in_(scope_keys))
    if item_id:
        stmt = stmt.where(Item.item_id == item_id)
    if item_ids:
        stmt = stmt.where(Item.item_id.in_(item_ids))
    if not force:
        stmt = stmt.where(
            Item.llm_reviewed.is_(False),
            claimable_filter,
        )
    if limit > 0 and not item_ids:
        stmt = stmt.limit(limit)

    with session_scope() as session:
        rows = session.execute(stmt).all()

    return [
        serialize_review_row(item=item, spec=spec, raw_response_body=raw_response_body)
        for item, spec, raw_response_body in rows
    ]


def is_review_state_claimable(
    *,
    review_status: str | None,
    updated_at: datetime | None,
    now: datetime | None = None,
    lease_seconds: int = 1800,
) -> bool:
    if review_status == REVIEW_STATUS_PENDING:
        return True
    if review_status != REVIEW_STATUS_IN_PROGRESS or updated_at is None:
        return False
    current_time = now or datetime.now(UTC)
    lease_cutoff = current_time - timedelta(seconds=max(lease_seconds, 1))
    return updated_at < lease_cutoff


def build_claimable_review_filter(*, lease_seconds: int):
    lease_cutoff = datetime.now(UTC) - timedelta(seconds=max(lease_seconds, 1))
    return or_(
        Item.llm_review_status == REVIEW_STATUS_PENDING,
        (Item.llm_review_status == REVIEW_STATUS_IN_PROGRESS) & (Item.updated_at < lease_cutoff),
    )


def count_pending_reviews(*, business_domain: str | None, lease_seconds: int = 1800) -> int:
    stmt = select(func.count(Item.id)).where(
        Item.is_active.is_(True),
        Item.llm_reviewed.is_(False),
        build_claimable_review_filter(lease_seconds=lease_seconds),
    )
    scope_keys = _scope_keys_for_filter(business_domain)
    if scope_keys:
        stmt = stmt.where(Item.business_domain.in_(scope_keys))
    with session_scope() as session:
        return int(session.execute(stmt).scalar_one())


def fetch_pending_item_ids(
    *,
    business_domain: str | None,
    limit: int,
    exclude_item_ids: set[str] | None = None,
) -> list[str]:
    claimable_filter = build_claimable_review_filter(lease_seconds=1800)
    stmt = (
        select(Item.item_id)
        .where(
            Item.is_active.is_(True),
            Item.llm_reviewed.is_(False),
            claimable_filter,
        )
        .order_by(desc(Item.last_seen_at), desc(Item.id))
    )
    scope_keys = _scope_keys_for_filter(business_domain)
    if scope_keys:
        stmt = stmt.where(Item.business_domain.in_(scope_keys))
    if exclude_item_ids:
        stmt = stmt.where(Item.item_id.not_in(sorted(exclude_item_ids)))
    if limit > 0:
        stmt = stmt.limit(limit)
    with session_scope() as session:
        return list(session.execute(stmt).scalars())


def fetch_pending_audit_item_ids(
    *,
    business_domain: str | None,
    audit_reason: str | None,
    limit: int,
) -> list[str]:
    stmt = (
        select(Item.item_id)
        .where(
            Item.is_active.is_(True),
            Item.llm_review_status == REVIEW_STATUS_PENDING_AUDIT,
        )
        .order_by(desc(Item.llm_reviewed_at), desc(Item.last_seen_at), desc(Item.id))
    )
    scope_keys = _scope_keys_for_filter(business_domain)
    if scope_keys:
        stmt = stmt.where(Item.business_domain.in_(scope_keys))
    if audit_reason is not None:
        stmt = stmt.where(Item.llm_review_audit_reason == audit_reason)
    if limit > 0:
        stmt = stmt.limit(limit)
    with session_scope() as session:
        return list(session.execute(stmt).scalars())


def claim_pending_item_ids(
    *,
    business_domain: str | None,
    limit: int,
    worker_name: str,
    lease_seconds: int,
) -> list[str]:
    if limit <= 0:
        return []

    claim_reason = f"claimed:{worker_name}"
    claimable_filter = build_claimable_review_filter(lease_seconds=lease_seconds)
    stmt = (
        select(Item.id)
        .where(
            Item.is_active.is_(True),
            Item.llm_reviewed.is_(False),
            claimable_filter,
        )
        .order_by(desc(Item.last_seen_at), desc(Item.id))
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    scope_keys = _scope_keys_for_filter(business_domain)
    if scope_keys:
        stmt = stmt.where(Item.business_domain.in_(scope_keys))

    with session_scope() as session:
        claimed_ids = list(session.execute(stmt).scalars())
        if not claimed_ids:
            return []
        return list(
            session.execute(
                update(Item)
                .where(Item.id.in_(claimed_ids))
                .values(
                    llm_review_status=REVIEW_STATUS_IN_PROGRESS,
                    llm_review_reason=claim_reason,
                    updated_at=func.now(),
                )
                .returning(Item.item_id)
            ).scalars()
        )


def release_item_claims(
    *,
    item_ids: list[str],
    worker_name: str,
) -> list[str]:
    if not item_ids:
        return []

    claim_reason = f"claimed:{worker_name}"
    with session_scope() as session:
        return list(
            session.execute(
                update(Item)
                .where(
                    Item.item_id.in_(item_ids),
                    Item.llm_reviewed.is_(False),
                    Item.llm_review_status == REVIEW_STATUS_IN_PROGRESS,
                    Item.llm_review_reason == claim_reason,
                )
                .values(
                    llm_review_status=REVIEW_STATUS_PENDING,
                    llm_review_reason=None,
                    updated_at=func.now(),
                )
                .returning(Item.item_id)
            ).scalars()
        )


def quarantine_item_claims(
    *,
    item_ids: list[str],
    worker_name: str,
    audit_reason: str = "low_confidence_v2",
) -> list[str]:
    if not item_ids:
        return []

    claim_reason = f"claimed:{worker_name}"
    with session_scope() as session:
        return list(
            session.execute(
                update(Item)
                .where(
                    Item.item_id.in_(item_ids),
                    Item.llm_review_status == REVIEW_STATUS_IN_PROGRESS,
                    Item.llm_review_reason == claim_reason,
                )
                .values(
                    llm_reviewed=True,
                    llm_review_status=REVIEW_STATUS_PENDING_AUDIT,
                    llm_review_reason=None,
                    llm_reviewed_at=func.now(),
                    llm_review_confidence=None,
                    llm_review_needs_audit=True,
                    llm_review_audit_reason=audit_reason,
                    llm_review_decision={
                        "review_status": REVIEW_STATUS_PENDING_AUDIT,
                        "audit_reason": audit_reason,
                        "review_origin": "v2_second_pass",
                    },
                    updated_at=func.now(),
                )
                .returning(Item.item_id)
            ).scalars()
        )


def serialize_review_row(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    raw_response_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    listing_description = extract_listing_description(
        raw_response_body=raw_response_body,
        review_input=item.llm_review_input,
    )
    rule_candidate = extract_item_specs(item, allow_llm=False)
    item_fields = {
        "normalized_brand": normalize_text(item.normalized_brand),
        "normalized_model_family": normalize_text(item.normalized_model_family),
        "normalized_model": normalize_text(item.normalized_model),
        "normalized_chip": normalize_chip_text(item.normalized_chip),
        "normalized_memory_gb": item.normalized_memory_gb,
        "normalized_storage_gb": item.normalized_storage_gb,
    }
    spec_fields = {
        "brand": normalize_text(spec.brand) if spec else None,
        "product_line": normalize_text(spec.product_line) if spec else None,
        "model_family": normalize_text(spec.model_family) if spec else None,
        "model_name": normalize_text(spec.model_name) if spec else None,
        "generation": normalize_text(spec.generation) if spec else None,
        "case_size_mm": spec.case_size_mm if spec else None,
        "is_solar": spec.is_solar if spec else None,
        "display_type": normalize_display_type(spec.display_type) if spec else None,
        "screen_size_in": decimal_to_json(spec.screen_size_in) if spec else None,
        "chip_family": normalize_chip_text(spec.chip_family) if spec else None,
        "cpu_model": normalize_chip_text(spec.cpu_model) if spec else None,
        "cpu_cores": spec.cpu_cores if spec else None,
        "gpu_cores": spec.gpu_cores if spec else None,
        "memory_gb": spec.memory_gb if spec else None,
        "storage_gb": spec.storage_gb if spec else None,
    }
    current_values = {
        "item.normalized_brand": item_fields["normalized_brand"],
        "item.normalized_model_family": item_fields["normalized_model_family"],
        "item.normalized_model": item_fields["normalized_model"],
        "item.normalized_chip": item_fields["normalized_chip"],
        "item.normalized_memory_gb": item_fields["normalized_memory_gb"],
        "item.normalized_storage_gb": item_fields["normalized_storage_gb"],
        "spec.brand": spec_fields["brand"],
        "spec.product_line": spec_fields["product_line"],
        "spec.model_family": spec_fields["model_family"],
        "spec.model_name": spec_fields["model_name"],
        "spec.generation": spec_fields["generation"],
        "spec.case_size_mm": spec_fields["case_size_mm"],
        "spec.is_solar": spec_fields["is_solar"],
        "spec.display_type": spec_fields["display_type"],
        "spec.screen_size_in": spec_fields["screen_size_in"],
        "spec.chip_family": spec_fields["chip_family"],
        "spec.cpu_model": spec_fields["cpu_model"],
        "spec.cpu_cores": spec_fields["cpu_cores"],
        "spec.gpu_cores": spec_fields["gpu_cores"],
        "spec.memory_gb": spec_fields["memory_gb"],
        "spec.storage_gb": spec_fields["storage_gb"],
    }
    resolved_domain = resolve_category_code(item.business_domain) or item.business_domain
    return {
        "item_id": item.item_id,
        "business_domain": resolved_domain,
        "category_code": resolved_domain,
        "source_platform": item.source_platform,
        "source_keyword": item.source_keyword,
        "title": item.title,
        "current_price": decimal_to_json(item.current_price),
        "condition_tags": item.condition_tags or [],
        "region": normalize_text(item.region),
        "listing_description": listing_description,
        "listing_description_length": len(listing_description) if listing_description else 0,
        "llm_review": {
            "reviewed": item.llm_reviewed,
            "status": item.llm_review_status,
            "reason": item.llm_review_reason,
            "confidence": decimal_to_json(item.llm_review_confidence),
            "needs_audit": item.llm_review_needs_audit,
            "audit_reason": item.llm_review_audit_reason,
            "input_signature": item.llm_review_input_signature,
            "reviewed_at": item.llm_reviewed_at.isoformat() if item.llm_reviewed_at else None,
        },
        "item_fields": item_fields,
        "spec_fields": spec_fields,
        "current_values": current_values,
        "rule_candidate": {
            "status": rule_candidate.status,
            "confidence": decimal_to_json(rule_candidate.confidence),
            "brand": normalize_text(rule_candidate.brand),
            "product_line": normalize_text(rule_candidate.product_line),
            "model_family": normalize_text(rule_candidate.model_family),
            "model_name": normalize_text(rule_candidate.model_name),
            "generation": normalize_text(rule_candidate.generation),
            "case_size_mm": rule_candidate.case_size_mm,
            "is_solar": rule_candidate.is_solar,
            "display_type": normalize_display_type(rule_candidate.display_type),
            "screen_size_in": decimal_to_json(rule_candidate.screen_size_in),
            "chip_family": normalize_chip_text(rule_candidate.chip_family),
            "cpu_model": normalize_chip_text(rule_candidate.cpu_model),
            "cpu_cores": rule_candidate.cpu_cores,
            "gpu_cores": rule_candidate.gpu_cores,
            "memory_gb": rule_candidate.memory_gb,
            "storage_gb": rule_candidate.storage_gb,
        },
    }


def extract_listing_description(
    *,
    raw_response_body: dict[str, Any] | None,
    review_input: dict[str, Any] | None,
) -> str | None:
    existing_review_description = normalize_text((review_input or {}).get("listing_description"))
    if existing_review_description:
        return existing_review_description
    candidates = collect_description_candidates(raw_response_body)
    if not candidates:
        return None
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def collect_description_candidates(value: Any) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def visit(node: Any, *, key_hint: str | None = None) -> None:
        if isinstance(node, dict):
            for key, nested in node.items():
                normalized_key = str(key).strip().lower()
                visit(nested, key_hint=normalized_key)
            return
        if isinstance(node, list):
            for nested in node:
                visit(nested, key_hint=key_hint)
            return
        if not isinstance(node, str):
            return

        text = normalize_text(node)
        if not text:
            return
        compact = "".join(text.split())
        if len(compact) < 40:
            return
        if key_hint and not any(token in key_hint for token in DESCRIPTION_CANDIDATE_KEYS):
            return
        if text in seen:
            return
        seen.add(text)
        candidates.append(text)

    visit(value)
    return candidates


def decimal_to_json(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
