from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import session_scope
from ...models import (
    Category,
    CategoryAttrTemplate,
    ProductAttrAuditLog,
    XianyuCategoryMapping,
    XianyuCategoryMatchScope,
    XianyuCategoryOnboardingQueue,
)
from .xianyu_category_mapping import (
    build_xianyu_category_match_candidates,
    build_xianyu_category_match_key,
    serialize_xianyu_category_mapping,
)


class RawCatePolicyConfigError(RuntimeError):
    pass


POLICY_MODES = {"BLOCK", "FORCE_CATEGORY", "FORCE_TEMPLATE", "OBSERVE"}


def list_raw_cate_policy_configs(
    *,
    status: str | None = None,
    policy_mode: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return list_raw_cate_policy_configs_with_session(
            session,
            status=status,
            policy_mode=policy_mode,
        )


def list_raw_cate_policy_configs_with_session(
    session: Session,
    *,
    status: str | None = None,
    policy_mode: str | None = None,
) -> dict[str, Any]:
    rows = list(session.execute(select(XianyuCategoryMapping)).scalars().all())
    normalized_status = _normalize_optional_string(status)
    normalized_policy_mode = _coerce_policy_mode(policy_mode) if policy_mode else None
    if normalized_status:
        rows = [row for row in rows if normalized_status == _normalize_optional_string(row.status)]
    if normalized_policy_mode:
        rows = [
            row
            for row in rows
            if normalized_policy_mode
            == (_normalize_optional_string(getattr(row, "policy_mode", None)) or "FORCE_TEMPLATE")
        ]
    queue_rows = list(session.execute(select(XianyuCategoryOnboardingQueue)).scalars().all())
    queue_by_key = {str(row.match_key): row for row in queue_rows}
    items = [
        serialize_raw_cate_policy_config(row, queue_row=queue_by_key.get(str(row.match_key)))
        for row in sorted(
            rows,
            key=lambda row: (
                str(getattr(row, "policy_mode", "") or ""),
                str(getattr(row, "match_key", "") or ""),
            ),
        )
    ]
    return {
        "status": normalized_status,
        "policyMode": normalized_policy_mode,
        "total": len(items),
        "items": items,
    }


def upsert_raw_cate_policy_config(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = upsert_raw_cate_policy_config_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def upsert_raw_cate_policy_config_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_operator_id = _normalize_optional_string(operator_id)
    if not normalized_operator_id:
        raise RawCatePolicyConfigError("operator_id is required.")

    normalized = _normalize_policy_payload(session, payload)
    mapping_id = _normalize_optional_string(payload.get("mappingId"))
    existing = None
    if mapping_id:
        existing = session.get(XianyuCategoryMapping, mapping_id)
        if existing is None:
            raise RawCatePolicyConfigError(f"Mapping not found: {mapping_id}")
    if existing is None:
        existing = session.execute(
            select(XianyuCategoryMapping).where(XianyuCategoryMapping.match_key == normalized["match_key"])
        ).scalar_one_or_none()

    before_json = serialize_raw_cate_policy_config(existing)
    if existing is None:
        row = XianyuCategoryMapping(
            match_scope=normalized["match_scope"],
            match_key=normalized["match_key"],
            xianyu_cat_id=normalized["xianyu_cat_id"],
            xianyu_tb_cat_id=normalized["xianyu_tb_cat_id"],
            xianyu_c_cat_id=normalized["xianyu_c_cat_id"],
            raw_category_name=normalized["raw_category_name"],
            raw_category_path=normalized["raw_category_path"],
            category_id=normalized["category_id"],
            template_id=normalized["template_id"],
            policy_mode=normalized["policy_mode"],
            template_override_id=normalized["template_override_id"],
            resolution_source=normalized["resolution_source"],
            status=normalized["status"],
            confidence=normalized["confidence"],
            metadata_json=normalized["metadata_json"],
        )
        session.add(row)
        session.flush()
        action = "CREATE_XIANYU_RAW_CATE_POLICY_DRY_RUN" if dry_run else "CREATE_XIANYU_RAW_CATE_POLICY"
    else:
        row = existing
        row.match_scope = normalized["match_scope"]
        row.match_key = normalized["match_key"]
        row.xianyu_cat_id = normalized["xianyu_cat_id"]
        row.xianyu_tb_cat_id = normalized["xianyu_tb_cat_id"]
        row.xianyu_c_cat_id = normalized["xianyu_c_cat_id"]
        row.raw_category_name = normalized["raw_category_name"]
        row.raw_category_path = normalized["raw_category_path"]
        row.category_id = normalized["category_id"]
        row.template_id = normalized["template_id"]
        row.policy_mode = normalized["policy_mode"]
        row.template_override_id = normalized["template_override_id"]
        row.resolution_source = normalized["resolution_source"]
        row.status = normalized["status"]
        row.confidence = normalized["confidence"]
        row.metadata_json = normalized["metadata_json"]
        session.flush()
        action = "UPDATE_XIANYU_RAW_CATE_POLICY_DRY_RUN" if dry_run else "UPDATE_XIANYU_RAW_CATE_POLICY"

    queue_row = session.execute(
        select(XianyuCategoryOnboardingQueue).where(XianyuCategoryOnboardingQueue.match_key == row.match_key)
    ).scalar_one_or_none()
    after_json = serialize_raw_cate_policy_config(row, queue_row=queue_row)
    audit_log = ProductAttrAuditLog(
        operator_id=normalized_operator_id,
        resource_type="xianyu_category_mapping",
        resource_id=row.id,
        action=action,
        before_json=before_json,
        after_json=after_json,
    )
    session.add(audit_log)
    session.flush()
    return {
        "dryRun": dry_run,
        "policy": after_json,
        "auditLogId": audit_log.id,
    }


def serialize_raw_cate_policy_config(
    row: XianyuCategoryMapping | None,
    *,
    queue_row: XianyuCategoryOnboardingQueue | None = None,
) -> dict[str, Any] | None:
    payload = serialize_xianyu_category_mapping(row)
    if payload is None:
        return None
    queue_snapshot = None
    if queue_row is not None:
        queue_snapshot = {
            "queueId": queue_row.id,
            "queueStatus": queue_row.status,
            "itemCountSnapshot": queue_row.item_count_snapshot,
            "sampleTitles": list(queue_row.sample_titles or []),
            "sourceKeywords": list(queue_row.source_keywords or []),
        }
    payload["queueSnapshot"] = queue_snapshot
    return payload


def _normalize_policy_payload(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    xianyu_cat_id = _normalize_optional_string(payload.get("xianyuCatId") or payload.get("xianyu_cat_id"))
    xianyu_tb_cat_id = _normalize_optional_string(payload.get("xianyuTbCatId") or payload.get("xianyu_tb_cat_id"))
    xianyu_c_cat_id = _normalize_optional_string(payload.get("xianyuCCatId") or payload.get("xianyu_c_cat_id"))
    match_scope = _resolve_match_scope(
        payload.get("matchScope") or payload.get("match_scope"),
        xianyu_cat_id=xianyu_cat_id,
        xianyu_tb_cat_id=xianyu_tb_cat_id,
        xianyu_c_cat_id=xianyu_c_cat_id,
    )
    match_key = build_xianyu_category_match_key(
        match_scope=match_scope,
        xianyu_cat_id=xianyu_cat_id,
        xianyu_tb_cat_id=xianyu_tb_cat_id,
        xianyu_c_cat_id=xianyu_c_cat_id,
    )

    category = _resolve_category(session, payload)
    template = _resolve_template(
        session,
        template_id=_normalize_optional_string(payload.get("templateId") or payload.get("template_id")),
    )
    template_override = _resolve_template(
        session,
        template_id=_normalize_optional_string(
            payload.get("templateOverrideId") or payload.get("template_override_id")
        ),
    )
    policy_mode = _coerce_policy_mode(payload.get("policyMode") or payload.get("policy_mode"))

    if category is None and template is not None:
        category = getattr(template, "category", None) or session.get(Category, template.category_id)
    if category is None and template_override is not None:
        category = getattr(template_override, "category", None) or session.get(Category, template_override.category_id)

    if policy_mode == "FORCE_CATEGORY" and category is None:
        raise RawCatePolicyConfigError("FORCE_CATEGORY requires categoryId or categoryCode.")
    if policy_mode == "FORCE_TEMPLATE" and template is None and template_override is None:
        raise RawCatePolicyConfigError("FORCE_TEMPLATE requires templateId or templateOverrideId.")

    confidence = payload.get("confidence")
    return {
        "match_scope": match_scope,
        "match_key": match_key,
        "xianyu_cat_id": xianyu_cat_id,
        "xianyu_tb_cat_id": xianyu_tb_cat_id,
        "xianyu_c_cat_id": xianyu_c_cat_id,
        "raw_category_name": _normalize_optional_string(
            payload.get("rawCategoryName") or payload.get("raw_category_name")
        ),
        "raw_category_path": _normalize_optional_string(
            payload.get("rawCategoryPath") or payload.get("raw_category_path")
        ),
        "category_id": getattr(category, "id", None),
        "template_id": getattr(template, "id", None),
        "policy_mode": policy_mode,
        "template_override_id": getattr(template_override, "id", None),
        "resolution_source": _normalize_optional_string(
            payload.get("resolutionSource") or payload.get("resolution_source")
        )
        or "manual",
        "status": _normalize_optional_string(payload.get("status")) or "ACTIVE",
        "confidence": Decimal(str(confidence)) if confidence is not None else None,
        "metadata_json": dict(payload.get("metadata") or payload.get("metadata_json") or {}),
    }


def _resolve_match_scope(
    value: Any,
    *,
    xianyu_cat_id: str | None,
    xianyu_tb_cat_id: str | None,
    xianyu_c_cat_id: str | None,
) -> XianyuCategoryMatchScope:
    if value:
        raw = str(value).strip().upper()
        try:
            return XianyuCategoryMatchScope(raw)
        except ValueError as exc:
            raise RawCatePolicyConfigError(f"Invalid matchScope: {value}") from exc
    candidates = build_xianyu_category_match_candidates(
        xianyu_cat_id=xianyu_cat_id,
        xianyu_tb_cat_id=xianyu_tb_cat_id,
        xianyu_c_cat_id=xianyu_c_cat_id,
    )
    if len(candidates) != 1:
        raise RawCatePolicyConfigError("matchScope is required when multiple raw category ids are provided.")
    return XianyuCategoryMatchScope(str(candidates[0]["matchScope"]))


def _resolve_category(session: Session, payload: dict[str, Any]) -> Category | None:
    category_id = _normalize_optional_string(payload.get("categoryId") or payload.get("category_id"))
    category_code = _normalize_optional_string(payload.get("categoryCode") or payload.get("category_code"))
    if category_id:
        return session.get(Category, category_id)
    if category_code:
        rows = list(session.execute(select(Category).where(Category.code == category_code)).scalars().all())
        return rows[0] if rows else None
    return None


def _resolve_template(session: Session, *, template_id: str | None) -> CategoryAttrTemplate | None:
    if not template_id:
        return None
    row = session.get(CategoryAttrTemplate, template_id)
    if row is None:
        raise RawCatePolicyConfigError(f"Template not found: {template_id}")
    return row


def _coerce_policy_mode(value: Any) -> str:
    normalized = (_normalize_optional_string(value) or "FORCE_TEMPLATE").upper()
    if normalized not in POLICY_MODES:
        raise RawCatePolicyConfigError(f"Unsupported policyMode: {value}")
    return normalized


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None
