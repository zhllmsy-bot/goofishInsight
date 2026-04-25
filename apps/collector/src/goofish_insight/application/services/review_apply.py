from __future__ import annotations

import json
from datetime import datetime
from ...compat import UTC
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ...db import session_scope
from ...domain.review.contracts import (
    INVALID_FIELD_VALUE,
    REVIEW_STATUS_INVALID,
    REVIEW_STATUS_PENDING_AUDIT,
    normalize_current_value,
    split_field_key,
    to_storage_value,
    validate_field_value,
)
from ...models import Item, ItemSpecEnrichment
from ...settings import get_settings
from .review_batches import normalize_review_entries, normalize_review_input

LLM_REVIEW_EXTRACTOR_TYPE = "llm_review"
LLM_REVIEW_EXTRACTOR_VERSION = "preview_v1"


def coerce_review_spec_confidence(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        numeric = Decimal(str(value))
    except Exception:
        return None
    if numeric > 1:
        numeric /= Decimal("100")
    numeric = max(Decimal("0"), min(numeric, Decimal("1")))
    return numeric.quantize(Decimal("0.01"))


def sync_review_spec_confidence(*, spec: ItemSpecEnrichment, item: Item) -> None:
    if (spec.extractor_type or "").strip().lower() != LLM_REVIEW_EXTRACTOR_TYPE:
        return
    confidence = coerce_review_spec_confidence(item.llm_review_confidence)
    if confidence is not None:
        spec.confidence = confidence


def load_review_entries(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RuntimeError("Review input must be a JSON array.")
    return normalize_review_entries(raw)


def apply_review_file(
    *,
    input_path: Path,
    dry_run: bool,
) -> dict[str, Any]:
    review_entries = load_review_entries(input_path)
    return apply_review_entries(
        review_entries=review_entries,
        dry_run=dry_run,
        source_label=str(input_path),
        source_name=input_path.name,
    )


def apply_review_entries(
    *,
    review_entries: list[dict[str, Any]],
    dry_run: bool,
    source_label: str,
    source_name: str,
) -> dict[str, Any]:
    requested_item_ids = [entry["item_id"] for entry in review_entries]
    summary = {
        "input_path": source_label,
        "dry_run": dry_run,
        "review_entry_count": len(review_entries),
        "matched_item_count": 0,
        "missing_item_count": 0,
        "reviewed_valid_count": 0,
        "reviewed_invalid_count": 0,
        "pending_audit_count": 0,
        "changed_item_row_count": 0,
        "changed_spec_row_count": 0,
        "created_spec_row_count": 0,
        "deactivated_item_count": 0,
        "changed_field_count": 0,
        "items": [],
    }
    if not requested_item_ids:
        return summary

    settings = get_settings()
    with session_scope() as session:
        rows = session.execute(
            select(Item, ItemSpecEnrichment)
            .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
            .where(Item.item_id.in_(requested_item_ids))
        ).all()
        item_map = {
            item.item_id: (item, spec)
            for item, spec in rows
        }

        for entry in review_entries:
            item_id = entry["item_id"]
            match = item_map.get(item_id)
            if match is None:
                summary["missing_item_count"] += 1
                summary["items"].append(
                    {
                        "item_id": item_id,
                        "status": "missing_item",
                    }
                )
                continue

            item, spec = match
            summary["matched_item_count"] += 1
            review_status = entry["review_status"]
            invalid_reason = entry.get("invalid_reason")
            if review_status == REVIEW_STATUS_INVALID:
                summary["reviewed_invalid_count"] += 1
            else:
                summary["reviewed_valid_count"] += 1

            needs_audit, audit_reason = classify_review_audit_requirement(
                review_status=review_status,
                entry=entry,
            )
            effective_review_status = REVIEW_STATUS_PENDING_AUDIT if needs_audit else review_status
            effective_invalid_reason = invalid_reason if not needs_audit else None
            review_meta_changes = build_review_meta_changes(
                item=item,
                review_status=effective_review_status,
                invalid_reason=effective_invalid_reason,
                confidence=entry.get("confidence"),
                review_input=entry.get("review_input"),
                review_input_signature=entry.get("review_input_signature"),
                needs_audit=needs_audit,
                audit_reason=audit_reason,
                decision=build_review_decision_payload(entry),
                deactivate_invalid=not needs_audit,
            )
            item_changes, spec_changes = build_apply_changes(
                item=item,
                spec=spec,
                entry=entry,
            )
            if review_status == REVIEW_STATUS_INVALID:
                spec_changes = []
            blocked_item_changes = item_changes
            blocked_spec_changes = spec_changes
            if needs_audit:
                summary["pending_audit_count"] += 1
                item_changes = []
                spec_changes = []
            if not review_meta_changes and not item_changes and not spec_changes:
                summary["items"].append(
                    {
                        "item_id": item_id,
                        "title": item.title,
                        "review_status": effective_review_status,
                        "status": "no_change",
                    }
                )
                continue

            create_spec_row = bool(spec is None and spec_changes)
            summary["changed_field_count"] += len(review_meta_changes) + len(item_changes) + len(spec_changes)
            if review_meta_changes or item_changes:
                summary["changed_item_row_count"] += 1
            if spec_changes:
                summary["changed_spec_row_count"] += 1
            if create_spec_row:
                summary["created_spec_row_count"] += 1
            if any(change["field_key"] == "item.is_active" and change["to"] is False for change in review_meta_changes):
                summary["deactivated_item_count"] += 1

            if not dry_run:
                if create_spec_row:
                    spec = create_review_spec_row(
                        item=item,
                        settings=settings,
                    )
                    session.add(spec)
                apply_item_review_meta_changes(item=item, changes=review_meta_changes)
                apply_changes_to_target(target=item, changes=item_changes)
                if spec is not None:
                    sync_review_spec_confidence(spec=spec, item=item)
                    apply_changes_to_target(target=spec, changes=spec_changes)
                    stamp_review_patch(
                        spec=spec,
                        input_name=source_name,
                        field_keys=[change["field_key"] for change in spec_changes],
                    )

            summary["items"].append(
                {
                    "item_id": item_id,
                    "title": item.title,
                    "review_status": effective_review_status,
                    "invalid_reason": invalid_reason,
                    "status": (
                        "queued_for_audit"
                        if needs_audit
                        else ("would_update" if dry_run else "updated")
                    ),
                    "create_spec_row": create_spec_row,
                    "needs_audit": needs_audit,
                    "audit_reason": audit_reason,
                    "review_meta_changes": review_meta_changes,
                    "item_changes": blocked_item_changes if needs_audit else item_changes,
                    "spec_changes": blocked_spec_changes if needs_audit else spec_changes,
                }
            )

        if dry_run:
            session.rollback()

    return summary


def build_review_meta_changes(
    *,
    item: Item,
    review_status: str,
    invalid_reason: str | None,
    confidence: float | None,
    review_input: dict[str, Any] | None,
    review_input_signature: str | None,
    needs_audit: bool,
    audit_reason: str | None,
    decision: dict[str, Any],
    deactivate_invalid: bool,
) -> list[dict[str, Any]]:
    reviewed_at = datetime.now(UTC)
    normalized_review_input = normalize_review_input(review_input) or {}
    desired_values = {
        "item.llm_reviewed": True,
        "item.llm_review_status": review_status,
        "item.llm_review_reason": invalid_reason if review_status == REVIEW_STATUS_INVALID else None,
        "item.llm_reviewed_at": reviewed_at.isoformat(),
        "item.llm_review_confidence": confidence,
        "item.llm_review_input": normalized_review_input,
        "item.llm_review_input_signature": review_input_signature,
        "item.llm_review_needs_audit": needs_audit,
        "item.llm_review_audit_reason": audit_reason,
        "item.llm_review_decision": decision,
        "item.is_active": False if review_status == REVIEW_STATUS_INVALID and deactivate_invalid else item.is_active,
    }
    current_values = {
        "item.llm_reviewed": item.llm_reviewed,
        "item.llm_review_status": item.llm_review_status,
        "item.llm_review_reason": item.llm_review_reason,
        "item.llm_reviewed_at": item.llm_reviewed_at.isoformat() if item.llm_reviewed_at else None,
        "item.llm_review_confidence": float(item.llm_review_confidence) if item.llm_review_confidence is not None else None,
        "item.llm_review_input": item.llm_review_input or {},
        "item.llm_review_input_signature": item.llm_review_input_signature,
        "item.llm_review_needs_audit": item.llm_review_needs_audit,
        "item.llm_review_audit_reason": item.llm_review_audit_reason,
        "item.llm_review_decision": item.llm_review_decision or {},
        "item.is_active": item.is_active,
    }

    changes: list[dict[str, Any]] = []
    for field_key, desired_value in desired_values.items():
        if field_key == "item.llm_reviewed_at":
            if item.llm_reviewed is True and item.llm_review_status == review_status and item.llm_review_reason == desired_values["item.llm_review_reason"]:
                continue
        elif desired_value == current_values.get(field_key):
            continue
        changes.append(
            {
                "field_key": field_key,
                "from": current_values.get(field_key),
                "to": desired_value,
            }
        )
    return changes


def apply_item_review_meta_changes(*, item: Item, changes: list[dict[str, Any]]) -> None:
    for change in changes:
        _, attr_name = split_field_key(change["field_key"])
        value = change["to"]
        if attr_name == "llm_reviewed_at" and isinstance(value, str):
            value = datetime.fromisoformat(value)
        if attr_name == "llm_review_confidence" and isinstance(value, float):
            value = Decimal(str(value))
        setattr(item, attr_name, value)


def build_apply_changes(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    entry: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    item_changes: list[dict[str, Any]] = []
    spec_changes: list[dict[str, Any]] = []
    for field in entry.get("not_match_field") or []:
        field_key = field["field_key"]
        new_value = validate_field_value(field_key=field_key, value=field.get("true_value"))
        if new_value is INVALID_FIELD_VALUE:
            continue
        target_name, attr_name = split_field_key(field_key)
        current_target = item if target_name == "item" else spec
        current_raw = getattr(current_target, attr_name) if current_target is not None else None
        current_value = normalize_current_value(field_key=field_key, value=current_raw)
        if new_value == current_value:
            continue
        change = {
            "field_key": field_key,
            "from": current_value,
            "to": new_value,
        }
        if target_name == "item":
            item_changes.append(change)
        else:
            spec_changes.append(change)
    return item_changes, spec_changes


def apply_changes_to_target(*, target: Any, changes: list[dict[str, Any]]) -> None:
    for change in changes:
        _, attr_name = split_field_key(change["field_key"])
        setattr(target, attr_name, to_storage_value(field_key=change["field_key"], value=change["to"]))


def create_review_spec_row(*, item: Item, settings: Any) -> ItemSpecEnrichment:
    return ItemSpecEnrichment(
        item_id_ref=item.id,
        business_domain=item.business_domain,
        extractor_type=LLM_REVIEW_EXTRACTOR_TYPE,
        extractor_version=LLM_REVIEW_EXTRACTOR_VERSION,
        llm_provider=settings.ai_provider or None,
        llm_model=settings.ai_model or None,
        status="partial",
        confidence=None,
        needs_review=False,
        evidence={},
        extraction_payload={},
    )


def classify_review_audit_requirement(
    *,
    review_status: str,
    entry: dict[str, Any],
) -> tuple[bool, str | None]:
    review_origin = entry.get("review_origin")
    if review_status == REVIEW_STATUS_INVALID and review_origin == "rule_precheck":
        return False, None
    if review_status == REVIEW_STATUS_INVALID:
        return True, "invalidated_by_llm"
    if entry.get("not_match_field"):
        return True, "field_corrections"
    return False, None


def build_review_decision_payload(entry: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "review_status": entry["review_status"],
        "confidence": entry.get("confidence"),
        "invalid_reason": entry.get("invalid_reason"),
        "not_match_field": entry.get("not_match_field") or [],
    }
    if entry.get("review_origin"):
        payload["review_origin"] = entry.get("review_origin")
    if entry.get("review_input_signature"):
        payload["review_input_signature"] = entry["review_input_signature"]
    return payload


def stamp_review_patch(
    *,
    spec: ItemSpecEnrichment,
    input_name: str,
    field_keys: list[str],
) -> None:
    stamp = {
        "source": "apply-item-llm-review",
        "input_file": input_name,
        "applied_at": datetime.now(UTC).isoformat(),
        "field_keys": field_keys,
    }
    evidence = dict(spec.evidence or {})
    evidence["llm_review_patch"] = stamp
    spec.evidence = evidence
    payload = dict(spec.extraction_payload or {})
    payload["llm_review_patch"] = stamp
    spec.extraction_payload = payload
    spec.needs_review = False
