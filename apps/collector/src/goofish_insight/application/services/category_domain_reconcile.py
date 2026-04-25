from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ...category_compat import resolve_category_code
from ...models import Category, CategoryRuntimeProfile, Item, ItemIngestRejection
from ...pricing import resolve_domain_redirect_scope, title_domain_mismatch_reason, title_matches_domain
from .collector_ingest import CATEGORY_INGEST_GATE_PROFILES, classify_category_ingest_block_reason

CAMERA_SCOPE_SIBLINGS: dict[str, str] = {
    "camera_body": "camera_interchangeable_lens",
    "camera_interchangeable_lens": "camera_body",
}

LEGACY_REDIRECT_REASON_ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    ("camera_body", "camera_interchangeable_lens"): ("title_scope_override:camera_body_to_lens",),
    ("camera_interchangeable_lens", "camera_body"): ("title_scope_override:lens_to_camera_body",),
}
SOFT_RECONCILE_GATE_REASONS: tuple[str, ...] = (
    "non_comparable_title",
    "price_floor",
    "signature_mismatch",
)


def reconcile_item_category_domain_state(
    session: Session,
    *,
    category_code: str,
    limit: int | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    resolved_category_code = resolve_category_code(category_code)
    if not resolved_category_code:
        raise ValueError("category_code is required")

    category_id_by_code = _load_category_id_by_code(session)
    active_template_id_by_code = _load_active_template_id_by_code(session)
    canonical_category_id = category_id_by_code.get(resolved_category_code)
    canonical_template_id = active_template_id_by_code.get(resolved_category_code)

    stmt = _build_reconcile_item_query(category_code=resolved_category_code)
    if limit is not None and limit > 0:
        stmt = stmt.limit(int(limit))

    items = list(session.execute(stmt).scalars().all())
    updates: list[dict[str, object]] = []
    cleared_rejection_item_ids: set[str] = set()
    restored_count = 0
    redirected_count = 0
    blocked_count = 0
    unchanged_count = 0

    for item in items:
        title = str(getattr(item, "title", "") or "")
        current_domain = resolve_category_code(getattr(item, "business_domain", None))
        source_keyword = str(getattr(item, "source_keyword", "") or "")
        current_price = getattr(item, "current_price", None)
        gate_reason = _classify_reconcile_gate_reason(
            category_code=resolved_category_code,
            title=title,
            price=current_price,
            source_keyword=source_keyword,
        )
        redirect_scope = (
            gate_reason.split(":", 1)[1]
            if gate_reason and gate_reason.startswith("domain_redirect:")
            else resolve_domain_redirect_scope(resolved_category_code, title)
        )
        matches_canonical = title_matches_domain(resolved_category_code, title)
        if gate_reason in SOFT_RECONCILE_GATE_REASONS and (matches_canonical or redirect_scope):
            gate_reason = None

        if gate_reason and not gate_reason.startswith("domain_redirect:"):
            block_reason = gate_reason
            if gate_reason == "domain_mismatch":
                block_reason = title_domain_mismatch_reason(resolved_category_code, title) or gate_reason
            if gate_reason.startswith("domain_mismatch:"):
                block_reason = gate_reason.split(":", 1)[1] or "domain_mismatch"
            expected_reason = f"title_scope_blocked:{block_reason}"
            already_blocked = (
                current_domain == resolved_category_code
                and not bool(getattr(item, "is_active", True))
                and str(getattr(item, "category_validation_status", "") or "") == "BLOCKED"
                and str(getattr(item, "category_validation_reason", "") or "") == expected_reason
            )
            if already_blocked:
                unchanged_count += 1
                continue

            updates.append(
                {
                    "item_id": item.item_id,
                    "action": "block",
                    "from_domain": current_domain or getattr(item, "business_domain", None),
                    "to_domain": resolved_category_code,
                    "reason": block_reason,
                    "title": title,
                }
            )
            blocked_count += 1
            if dry_run:
                continue

            item.business_domain = resolved_category_code
            item.is_active = False
            item.resolved_category_id = None
            item.resolved_template_id = None
            item.category_validation_status = "BLOCKED"
            item.category_validation_reason = expected_reason
            item.category_validation_confidence = Decimal("0.9500")
            continue

        if matches_canonical:
            already_restored = (
                current_domain == resolved_category_code
                and bool(getattr(item, "is_active", True))
                and str(getattr(item, "category_validation_status", "") or "") == "MATCH_TASK_CATEGORY"
                and str(getattr(item, "resolved_category_id", "") or "") == str(canonical_category_id or "")
                and str(getattr(item, "resolved_template_id", "") or "") == str(canonical_template_id or "")
            )
            if already_restored:
                unchanged_count += 1
                continue

            updates.append(
                {
                    "item_id": item.item_id,
                    "action": "restore",
                    "from_domain": current_domain or getattr(item, "business_domain", None),
                    "to_domain": resolved_category_code,
                    "title": title,
                }
            )
            restored_count += 1
            cleared_rejection_item_ids.add(str(item.item_id))
            if dry_run:
                continue

            item.business_domain = resolved_category_code
            item.is_active = True
            if canonical_category_id is not None:
                item.resolved_category_id = canonical_category_id
                if item.target_category_id is None:
                    item.target_category_id = canonical_category_id
            item.resolved_template_id = canonical_template_id
            item.category_validation_status = "MATCH_TASK_CATEGORY"
            item.category_validation_reason = "title_scope_reconciled:match_task_category"
            item.category_validation_confidence = Decimal("0.9800")
            continue

        if redirect_scope:
            redirected_category_id = category_id_by_code.get(redirect_scope)
            redirected_template_id = active_template_id_by_code.get(redirect_scope)
            expected_reason = f"title_scope_override:{resolved_category_code}_to_{redirect_scope}"
            already_redirected = (
                current_domain == redirect_scope
                and bool(getattr(item, "is_active", True))
                and str(getattr(item, "category_validation_status", "") or "") == "OVERRIDE_CATEGORY"
                and str(getattr(item, "resolved_category_id", "") or "") == str(redirected_category_id or "")
                and str(getattr(item, "resolved_template_id", "") or "") == str(redirected_template_id or "")
                and str(getattr(item, "category_validation_reason", "") or "") == expected_reason
            )
            if already_redirected:
                unchanged_count += 1
                continue

            updates.append(
                {
                    "item_id": item.item_id,
                    "action": "redirect",
                    "from_domain": current_domain or getattr(item, "business_domain", None),
                    "to_domain": redirect_scope,
                    "title": title,
                }
            )
            redirected_count += 1
            cleared_rejection_item_ids.add(str(item.item_id))
            if dry_run:
                continue

            item.business_domain = redirect_scope
            item.is_active = True
            item.resolved_category_id = redirected_category_id
            item.resolved_template_id = redirected_template_id
            item.category_validation_status = "OVERRIDE_CATEGORY"
            item.category_validation_reason = expected_reason
            item.category_validation_confidence = Decimal("0.9300")
            continue

        mismatch_reason = title_domain_mismatch_reason(resolved_category_code, title) or "domain_mismatch"
        expected_reason = f"title_scope_blocked:{mismatch_reason}"
        already_blocked = (
            current_domain == resolved_category_code
            and not bool(getattr(item, "is_active", True))
            and str(getattr(item, "category_validation_status", "") or "") == "BLOCKED"
            and str(getattr(item, "category_validation_reason", "") or "") == expected_reason
        )
        if already_blocked:
            unchanged_count += 1
            continue

        updates.append(
            {
                "item_id": item.item_id,
                "action": "block",
                "from_domain": current_domain or getattr(item, "business_domain", None),
                "to_domain": resolved_category_code,
                "reason": mismatch_reason,
                "title": title,
            }
        )
        blocked_count += 1
        if dry_run:
            continue

        item.business_domain = resolved_category_code
        item.is_active = False
        item.resolved_category_id = None
        item.resolved_template_id = None
        item.category_validation_status = "BLOCKED"
        item.category_validation_reason = expected_reason
        item.category_validation_confidence = Decimal("0.9500")

    cleared_rejection_count = 0
    if not dry_run and cleared_rejection_item_ids:
        result = session.execute(
            delete(ItemIngestRejection).where(
                ItemIngestRejection.source_platform == "xianyu",
                ItemIngestRejection.item_id.in_(tuple(sorted(cleared_rejection_item_ids))),
                or_(
                    ItemIngestRejection.rejection_stage.like("%category_gate%"),
                    ItemIngestRejection.rejection_reason.like("domain_%"),
                    ItemIngestRejection.rejection_reason == "non_comparable_title",
                ),
            )
        )
        cleared_rejection_count = int(result.rowcount or 0)

    return {
        "category_code": resolved_category_code,
        "dry_run": bool(dry_run),
        "scanned": len(items),
        "restored_count": restored_count,
        "redirected_count": redirected_count,
        "blocked_count": blocked_count,
        "unchanged_count": unchanged_count,
        "cleared_rejection_count": cleared_rejection_count,
        "sample": updates[:100],
    }


def _build_reconcile_item_query(*, category_code: str):
    predicates = [
        (
            (Item.business_domain == category_code)
            & (
                Item.is_active.is_(False)
                | Item.category_validation_status.in_(("BLOCKED", "OVERRIDE_CATEGORY"))
                | Item.category_validation_reason.like("title_scope_%")
            )
        )
    ]
    sibling_scope = CAMERA_SCOPE_SIBLINGS.get(category_code)
    if sibling_scope:
        predicates.append(Item.category_validation_reason.like(f"title_scope_override:{category_code}_to_%"))
        for legacy_reason in LEGACY_REDIRECT_REASON_ALIASES.get((category_code, sibling_scope), ()):
            predicates.append(Item.category_validation_reason == legacy_reason)
    return select(Item).where(or_(*predicates)).order_by(Item.id.asc())


def _load_category_id_by_code(session: Session) -> dict[str, str]:
    rows = session.execute(select(Category.id, Category.code)).all()
    return {str(code): str(category_id) for category_id, code in rows if code}


def _load_active_template_id_by_code(session: Session) -> dict[str, str]:
    rows = session.execute(
        select(Category.code, CategoryRuntimeProfile.active_template_id)
        .join(CategoryRuntimeProfile, CategoryRuntimeProfile.category_id == Category.id)
        .where(CategoryRuntimeProfile.status == "ACTIVE")
    ).all()
    return {str(code): str(template_id) for code, template_id in rows if code and template_id}


def _classify_reconcile_gate_reason(
    *,
    category_code: str,
    title: str,
    price,
    source_keyword: str,
) -> str | None:
    profile = CATEGORY_INGEST_GATE_PROFILES.get(category_code)
    if profile is None:
        return None
    return classify_category_ingest_block_reason(
        category_code=category_code,
        title=title,
        price=price,
        source_keyword=source_keyword,
        profile=profile,
    )
