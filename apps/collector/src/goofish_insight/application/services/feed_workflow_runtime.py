from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql import func

from ...models import HomeFeedItemDecision, Item
from .category_resolution import ResolvedItemCategoryContext
from .feed_category_resolution import FeedCategorySelection


def build_home_feed_decision_payload(
    *,
    category_selection: FeedCategorySelection | None,
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if category_selection is not None:
        payload["categorySelection"] = dict(category_selection.decision_payload or {})
    if extra_payload:
        payload.update(extra_payload)
    return payload


def persist_home_feed_item_decision(
    *,
    session,
    item_id: str,
    decision_stage: str,
    decision_status: str,
    source_platform: str = "xianyu",
    item_id_ref: int | None = None,
    current_outreach_status: str | None = None,
    category_selection: FeedCategorySelection | None = None,
    category_context: ResolvedItemCategoryContext | None = None,
    confidence: Decimal | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> None:
    resolved_context = category_context or (
        category_selection.category_context if category_selection is not None else None
    )
    decision_payload = build_home_feed_decision_payload(
        category_selection=category_selection,
        extra_payload=extra_payload,
    )
    match_key = None
    match_scope = None
    if category_selection is not None:
        target_pool_gate = dict(category_selection.decision_payload or {}).get("targetPoolGate") or {}
        if isinstance(target_pool_gate, dict):
            match_key = _normalize_text(target_pool_gate.get("matchKey"))
            match_scope = _normalize_text(target_pool_gate.get("matchScope"))

    stmt = insert(HomeFeedItemDecision).values(
        item_id=item_id,
        item_id_ref=item_id_ref,
        source_platform=source_platform,
        decision_stage=decision_stage,
        decision_status=decision_status,
        decision_source=(
            category_selection.decision_source if category_selection is not None else None
        ),
        decision_reason=(
            category_selection.decision_reason if category_selection is not None else None
        ),
        current_outreach_status=current_outreach_status,
        resolved_business_domain=(
            resolved_context.resolved_business_domain if resolved_context is not None else None
        ),
        resolved_category_id=(
            str(resolved_context.resolved_category_id)
            if resolved_context is not None and resolved_context.resolved_category_id
            else None
        ),
        resolved_template_id=(
            str(resolved_context.resolved_template_id)
            if resolved_context is not None and resolved_context.resolved_template_id
            else None
        ),
        confidence=confidence or _confidence_from_context(resolved_context),
        match_key=match_key,
        match_scope=match_scope,
        candidate_business_domains=(
            list(category_selection.candidate_business_domains)
            if category_selection is not None
            else []
        ),
        active_candidate_business_domains=(
            list(category_selection.active_candidate_business_domains)
            if category_selection is not None
            else []
        ),
        payload=decision_payload,
        created_at=func.now(),
        updated_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            HomeFeedItemDecision.source_platform,
            HomeFeedItemDecision.item_id,
            HomeFeedItemDecision.decision_stage,
        ],
        set_={
            "item_id_ref": item_id_ref,
            "decision_status": decision_status,
            "decision_source": (
                category_selection.decision_source if category_selection is not None else None
            ),
            "decision_reason": (
                category_selection.decision_reason if category_selection is not None else None
            ),
            "current_outreach_status": current_outreach_status,
            "resolved_business_domain": (
                resolved_context.resolved_business_domain if resolved_context is not None else None
            ),
            "resolved_category_id": (
                str(resolved_context.resolved_category_id)
                if resolved_context is not None and resolved_context.resolved_category_id
                else None
            ),
            "resolved_template_id": (
                str(resolved_context.resolved_template_id)
                if resolved_context is not None and resolved_context.resolved_template_id
                else None
            ),
            "confidence": confidence or _confidence_from_context(resolved_context),
            "match_key": match_key,
            "match_scope": match_scope,
            "candidate_business_domains": (
                list(category_selection.candidate_business_domains)
                if category_selection is not None
                else []
            ),
            "active_candidate_business_domains": (
                list(category_selection.active_candidate_business_domains)
                if category_selection is not None
                else []
            ),
            "payload": decision_payload,
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)


def persist_home_feed_item_decision_for_item(
    *,
    session,
    item: Item | None,
    decision_stage: str,
    decision_status: str,
    current_outreach_status: str | None = None,
    category_selection: FeedCategorySelection | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> None:
    if item is None:
        return
    context = build_category_context_from_item(item)
    persist_home_feed_item_decision(
        session=session,
        item_id=item.item_id,
        item_id_ref=int(item.id) if item.id is not None else None,
        source_platform=item.source_platform or "xianyu",
        decision_stage=decision_stage,
        decision_status=decision_status,
        current_outreach_status=current_outreach_status,
        category_selection=category_selection,
        category_context=context,
        extra_payload=extra_payload,
    )


def _confidence_from_context(context: ResolvedItemCategoryContext | None) -> Decimal | None:
    if context is None:
        return None
    return context.category_validation_confidence


def build_category_context_from_item(item: Item | None) -> ResolvedItemCategoryContext | None:
    if item is None:
        return None
    return ResolvedItemCategoryContext(
        target_category_id=item.target_category_id,
        resolved_category_id=item.resolved_category_id,
        resolved_template_id=item.resolved_template_id,
        category_validation_status=item.category_validation_status,
        category_validation_reason=item.category_validation_reason,
        category_validation_confidence=item.category_validation_confidence,
        resolved_business_domain=item.business_domain,
    )


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


__all__ = [
    "build_category_context_from_item",
    "build_home_feed_decision_payload",
    "persist_home_feed_item_decision",
    "persist_home_feed_item_decision_for_item",
]
