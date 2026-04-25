from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ...db import session_scope
from ...category_compat import resolve_category_code
from ...models import Category, CategoryAttrTemplate, CategoryRuntimeProfile, CrawlTask, Item
from ...pricing import resolve_domain_redirect_scope, title_domain_mismatch_reason, title_matches_domain
from .xianyu_category_mapping import resolve_xianyu_category_mapping_with_session


@dataclass(slots=True)
class ResolvedItemCategoryContext:
    target_category_id: str | None
    resolved_category_id: str | None
    resolved_template_id: str | None
    category_validation_status: str
    category_validation_reason: str | None
    category_validation_confidence: Decimal | None
    resolved_business_domain: str | None = None
    raw_policy_mode: str | None = None
    raw_mapping_id: str | None = None


def backfill_item_category_resolution(
    *,
    task_key: str | None = None,
    canonical_category_code: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        return backfill_item_category_resolution_with_session(
            session,
            task_key=task_key,
            canonical_category_code=canonical_category_code,
            limit=limit,
            dry_run=dry_run,
        )


def backfill_item_category_resolution_with_session(
    session: Session,
    *,
    task_key: str | None = None,
    canonical_category_code: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    resolved_category_code = resolve_category_code(canonical_category_code)
    camera_lens_category_id = (
        _resolve_category_id_by_code(session, "camera_interchangeable_lens")
        if resolved_category_code == "camera_body"
        else None
    )
    camera_body_category_id = (
        _resolve_category_id_by_code(session, "camera_body")
        if resolved_category_code == "camera_interchangeable_lens"
        else None
    )
    stmt = (
        select(Item, CrawlTask)
        .join(CrawlTask, CrawlTask.id == Item.task_id)
        .where(
            or_(
                Item.target_category_id.is_(None),
                Item.resolved_category_id.is_(None),
                Item.resolved_template_id.is_(None),
                Item.category_validation_status == "PENDING",
            )
        )
        .order_by(Item.id.asc())
    )
    if resolved_category_code:
        stmt = (
            select(Item, CrawlTask)
            .join(CrawlTask, CrawlTask.id == Item.task_id)
            .where(Item.business_domain.in_((resolved_category_code,)))
            .where(
                or_(
                    and_(
                        Item.category_validation_status == "MATCH_TASK_CATEGORY",
                        Item.title.is_not(None),
                    ),
                    and_(
                        camera_lens_category_id is not None,
                        Item.resolved_category_id == camera_lens_category_id,
                    ),
                    and_(
                        camera_body_category_id is not None,
                        Item.resolved_category_id == camera_body_category_id,
                    ),
                )
            )
            .order_by(Item.id.asc())
        )
    if task_key:
        stmt = stmt.where(CrawlTask.task_key == str(task_key).strip())
    if resolved_category_code:
        stmt = stmt.where(Item.business_domain.in_((resolved_category_code,)))
    if limit is not None and limit > 0:
        stmt = stmt.limit(limit)

    rows = list(session.execute(stmt).all())
    summary = {
        "processed": 0,
        "updated": 0,
        "dry_run": dry_run,
        "task_key": task_key,
        "canonical_category_code": resolved_category_code or None,
        "items": [],
    }
    for item, task in rows:
        context = resolve_item_category_context_with_session(
            session,
            task=task,
            xianyu_cat_id=item.xianyu_cat_id,
            xianyu_tb_cat_id=item.xianyu_tb_cat_id,
            xianyu_c_cat_id=item.xianyu_c_cat_id,
            title=item.title,
        )
        summary["processed"] += 1
        summary["items"].append(
            {
                "item_id": item.item_id,
                "target_category_id": context.target_category_id,
                "resolved_category_id": context.resolved_category_id,
                "resolved_template_id": context.resolved_template_id,
                "category_validation_status": context.category_validation_status,
            }
        )
        if dry_run:
            continue
        item.target_category_id = context.target_category_id
        item.resolved_category_id = context.resolved_category_id
        item.resolved_template_id = context.resolved_template_id
        item.category_validation_status = context.category_validation_status
        item.category_validation_reason = context.category_validation_reason
        item.category_validation_confidence = context.category_validation_confidence
        if context.resolved_business_domain:
            item.business_domain = context.resolved_business_domain
        summary["updated"] += 1
    return summary


def resolve_item_category_context_with_session(
    session: Session,
    *,
    task: CrawlTask,
    xianyu_cat_id: str | None = None,
    xianyu_tb_cat_id: str | None = None,
    xianyu_c_cat_id: str | None = None,
    title: str | None = None,
) -> ResolvedItemCategoryContext:
    target_category_id = _resolve_task_category_id(session, task=task)
    canonical_scope = resolve_category_code(getattr(task, "business_domain", None))
    title_matches_task_domain = title_matches_domain(canonical_scope, title) if title is not None else True
    title_override_context = _resolve_title_override_context(
        session,
        task=task,
        title=title,
        title_matches_task_domain=title_matches_task_domain,
    )
    if title_override_context is not None:
        return title_override_context
    default_template_id = _load_active_template_id(session, category_id=target_category_id)

    mapping = resolve_xianyu_category_mapping_with_session(
        session,
        xianyu_cat_id=xianyu_cat_id,
        xianyu_tb_cat_id=xianyu_tb_cat_id,
        xianyu_c_cat_id=xianyu_c_cat_id,
        active_only=True,
    )
    if mapping is None:
        return ResolvedItemCategoryContext(
            target_category_id=target_category_id,
            resolved_category_id=target_category_id,
            resolved_template_id=default_template_id,
            category_validation_status="MATCH_TASK_CATEGORY" if target_category_id else "PENDING",
            category_validation_reason="task_bound_category" if target_category_id else "missing_task_category",
            category_validation_confidence=Decimal("1.0000") if target_category_id else None,
            resolved_business_domain=canonical_scope or getattr(task, "business_domain", None),
        )

    policy_mode = (getattr(mapping, "policy_mode", None) or "FORCE_TEMPLATE").upper()
    mapping_template_id = getattr(mapping, "template_override_id", None) or getattr(mapping, "template_id", None)
    mapping_category_id = getattr(mapping, "category_id", None)

    if policy_mode == "BLOCK":
        return ResolvedItemCategoryContext(
            target_category_id=target_category_id,
            resolved_category_id=None,
            resolved_template_id=None,
            category_validation_status="BLOCKED",
            category_validation_reason=f"raw_cate_blocked:{mapping.match_key}",
            category_validation_confidence=Decimal("1.0000"),
            resolved_business_domain=canonical_scope or getattr(task, "business_domain", None),
            raw_policy_mode=policy_mode,
            raw_mapping_id=mapping.id,
        )

    if policy_mode == "FORCE_CATEGORY":
        resolved_category_id = mapping_category_id or target_category_id
        return ResolvedItemCategoryContext(
            target_category_id=target_category_id,
            resolved_category_id=resolved_category_id,
            resolved_template_id=_load_active_template_id(session, category_id=resolved_category_id),
            category_validation_status="OVERRIDE_CATEGORY",
            category_validation_reason=f"raw_cate_force_category:{mapping.match_key}",
            category_validation_confidence=Decimal("0.9500"),
            resolved_business_domain=_resolve_category_code_by_id(session, resolved_category_id)
            or canonical_scope
            or getattr(task, "business_domain", None),
            raw_policy_mode=policy_mode,
            raw_mapping_id=mapping.id,
        )

    if policy_mode == "OBSERVE":
        return ResolvedItemCategoryContext(
            target_category_id=target_category_id,
            resolved_category_id=target_category_id,
            resolved_template_id=default_template_id,
            category_validation_status="OBSERVE",
            category_validation_reason=f"raw_cate_observe:{mapping.match_key}",
            category_validation_confidence=Decimal("0.7000"),
            resolved_business_domain=canonical_scope or getattr(task, "business_domain", None),
            raw_policy_mode=policy_mode,
            raw_mapping_id=mapping.id,
        )

    resolved_template_id = mapping_template_id or default_template_id
    resolved_category_id = mapping_category_id or _load_template_category_id(session, resolved_template_id) or target_category_id
    return ResolvedItemCategoryContext(
        target_category_id=target_category_id,
        resolved_category_id=resolved_category_id,
        resolved_template_id=resolved_template_id,
        category_validation_status="OVERRIDE_TEMPLATE",
        category_validation_reason=f"raw_cate_force_template:{mapping.match_key}",
        category_validation_confidence=Decimal("0.9800"),
        resolved_business_domain=_resolve_category_code_by_id(session, resolved_category_id)
        or canonical_scope
        or getattr(task, "business_domain", None),
        raw_policy_mode=policy_mode,
        raw_mapping_id=mapping.id,
    )


def _resolve_task_category_id(session: Session, *, task: CrawlTask) -> str | None:
    if getattr(task, "category_id", None):
        return str(task.category_id)
    category_code = resolve_category_code(getattr(task, "business_domain", None))
    if not category_code:
        return None
    row = session.execute(select(Category).where(Category.code == category_code)).scalar_one_or_none()
    return str(row.id) if row is not None else None


def _load_active_template_id(session: Session, *, category_id: str | None) -> str | None:
    if not category_id:
        return None
    runtime_profile = session.execute(
        select(CategoryRuntimeProfile).where(
            CategoryRuntimeProfile.category_id == category_id,
            CategoryRuntimeProfile.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    return str(runtime_profile.active_template_id) if runtime_profile and runtime_profile.active_template_id else None


def _load_template_category_id(session: Session, template_id: str | None) -> str | None:
    if not template_id:
        return None
    row = session.get(CategoryAttrTemplate, template_id)
    return str(row.category_id) if row is not None else None


def _resolve_title_override_context(
    session: Session,
    *,
    task: CrawlTask,
    title: str | None,
    title_matches_task_domain: bool,
) -> ResolvedItemCategoryContext | None:
    canonical_scope = resolve_category_code(getattr(task, "business_domain", None))
    if title is None or title_matches_task_domain:
        return None

    if canonical_scope == "apple_computer":
        mismatch_reason = title_domain_mismatch_reason("apple_computer", title) or "apple_computer_mismatch"
        if mismatch_reason in {"apple_watch_like", "apple_audio_like"}:
            return ResolvedItemCategoryContext(
                target_category_id=_resolve_task_category_id(session, task=task),
                resolved_category_id=None,
                resolved_template_id=None,
                category_validation_status="BLOCKED",
                category_validation_reason=f"title_scope_blocked:{mismatch_reason}",
                category_validation_confidence=Decimal("0.9900"),
                resolved_business_domain=canonical_scope,
            )
        return ResolvedItemCategoryContext(
            target_category_id=_resolve_task_category_id(session, task=task),
            resolved_category_id=None,
            resolved_template_id=None,
            category_validation_status="BLOCKED",
            category_validation_reason="title_scope_blocked:apple_computer_mismatch",
            category_validation_confidence=Decimal("0.9500"),
            resolved_business_domain=canonical_scope,
        )

    if canonical_scope == "camera_body":
        redirected_scope = resolve_domain_redirect_scope(canonical_scope, title)
        if redirected_scope is None:
            mismatch_reason = title_domain_mismatch_reason(canonical_scope, title) or "camera_body_mismatch"
            return ResolvedItemCategoryContext(
                target_category_id=_resolve_task_category_id(session, task=task),
                resolved_category_id=None,
                resolved_template_id=None,
                category_validation_status="BLOCKED",
                category_validation_reason=f"title_scope_blocked:{mismatch_reason}",
                category_validation_confidence=Decimal("0.9500"),
                resolved_business_domain=canonical_scope,
            )
        target_category_id = _resolve_category_id_by_code(session, redirected_scope)
        return ResolvedItemCategoryContext(
            target_category_id=_resolve_task_category_id(session, task=task),
            resolved_category_id=target_category_id,
            resolved_template_id=_load_active_template_id(session, category_id=target_category_id),
            category_validation_status="OVERRIDE_CATEGORY",
            category_validation_reason=f"title_scope_override:{canonical_scope}_to_{redirected_scope}",
            category_validation_confidence=Decimal("0.9300"),
            resolved_business_domain=redirected_scope,
        )

    if canonical_scope == "camera_interchangeable_lens":
        redirected_scope = resolve_domain_redirect_scope(canonical_scope, title)
        if redirected_scope is None:
            mismatch_reason = title_domain_mismatch_reason(canonical_scope, title) or "camera_interchangeable_lens_mismatch"
            return ResolvedItemCategoryContext(
                target_category_id=_resolve_task_category_id(session, task=task),
                resolved_category_id=None,
                resolved_template_id=None,
                category_validation_status="BLOCKED",
                category_validation_reason=f"title_scope_blocked:{mismatch_reason}",
                category_validation_confidence=Decimal("0.9500"),
                resolved_business_domain=canonical_scope,
            )
        target_category_id = _resolve_category_id_by_code(session, redirected_scope)
        return ResolvedItemCategoryContext(
            target_category_id=_resolve_task_category_id(session, task=task),
            resolved_category_id=target_category_id,
            resolved_template_id=_load_active_template_id(session, category_id=target_category_id),
            category_validation_status="OVERRIDE_CATEGORY",
            category_validation_reason=f"title_scope_override:{canonical_scope}_to_{redirected_scope}",
            category_validation_confidence=Decimal("0.9300"),
            resolved_business_domain=redirected_scope,
        )

    return None


def _looks_like_watch_or_audio_title(title: str | None) -> bool:
    normalized = str(title or "").strip().lower()
    return any(
        token in normalized
        for token in ("apple watch", "watch ultra", "watch series", "watch se", "iwatch", "airpods")
    )


def _resolve_category_id_by_code(session: Session, category_code: str) -> str | None:
    row = session.execute(select(Category).where(Category.code == category_code)).scalar_one_or_none()
    if row is None:
        return None
    category_id = getattr(row, "id", None)
    if category_id is not None:
        return str(category_id)
    if isinstance(row, str):
        return row
    return None


def _resolve_category_code_by_id(session: Session, category_id: str | None) -> str | None:
    if not category_id:
        return None
    row = session.get(Category, category_id)
    if row is None:
        return None
    category_code = getattr(row, "code", None)
    return resolve_category_code(category_code)
