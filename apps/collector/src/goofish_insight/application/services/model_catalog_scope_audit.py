from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...category_compat import resolve_category_code
from ...models import CategoryModelAlias, CategoryModelCatalog, ProductAttrAuditLog
from .catalog_category_quality import catalog_scope_mismatch_reason
from .task_model_catalog_sync import sync_category_model_catalog_to_tasks_with_session


def build_model_catalog_scope_audit(
    session: Session,
    *,
    category_code: str | None = None,
    active_only: bool = True,
) -> dict[str, Any]:
    findings = find_model_catalog_scope_mismatches(
        session,
        category_code=category_code,
        active_only=active_only,
    )
    return _audit_summary(
        findings=findings,
        category_code=resolve_category_code(category_code) or None,
        active_only=active_only,
    )


def find_model_catalog_scope_mismatches(
    session: Session,
    *,
    category_code: str | None = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    resolved_category_code = resolve_category_code(category_code)
    stmt = (
        select(CategoryModelCatalog)
        .options(
            selectinload(CategoryModelCatalog.category),
            selectinload(CategoryModelCatalog.aliases),
        )
        .order_by(
            CategoryModelCatalog.category_id.asc(),
            CategoryModelCatalog.brand_name.asc(),
            CategoryModelCatalog.model_name.asc(),
            CategoryModelCatalog.model_code.asc(),
        )
    )
    if active_only:
        stmt = stmt.where(CategoryModelCatalog.status == "ACTIVE")
    rows = list(session.execute(stmt).scalars().all())

    findings: list[dict[str, Any]] = []
    for model in rows:
        category = getattr(model, "category", None)
        if category is None:
            continue
        canonical_category_code = resolve_category_code(getattr(category, "code", None))
        if resolved_category_code and canonical_category_code != resolved_category_code:
            continue
        model_reason = catalog_scope_mismatch_reason(
            canonical_category_code,
            title=_model_scope_text(model),
        )
        if model_reason is not None:
            findings.append(
                {
                    "categoryCode": canonical_category_code,
                    "categoryName": getattr(category, "name", None),
                    "resourceType": "model",
                    "resourceId": str(getattr(model, "id", "") or ""),
                    "status": str(getattr(model, "status", "") or ""),
                    "reason": model_reason,
                    "brandName": getattr(model, "brand_name", None),
                    "seriesName": getattr(model, "series_name", None),
                    "modelCode": getattr(model, "model_code", None),
                    "modelName": getattr(model, "model_name", None),
                    "title": _model_scope_text(model),
                    "activeAliasCount": _active_alias_count(model),
                }
            )
            continue
        for alias in sorted(
            list(getattr(model, "aliases", []) or []),
            key=lambda row: (
                str(getattr(row, "alias_text", "") or ""),
                str(getattr(row, "id", "") or ""),
            ),
        ):
            if active_only and str(getattr(alias, "status", "") or "").upper() != "ACTIVE":
                continue
            alias_reason = catalog_scope_mismatch_reason(
                canonical_category_code,
                title=getattr(alias, "alias_text", None),
            )
            if alias_reason is None:
                continue
            findings.append(
                {
                    "categoryCode": canonical_category_code,
                    "categoryName": getattr(category, "name", None),
                    "resourceType": "alias",
                    "resourceId": str(getattr(alias, "id", "") or ""),
                    "status": str(getattr(alias, "status", "") or ""),
                    "reason": alias_reason,
                    "aliasText": getattr(alias, "alias_text", None),
                    "aliasType": getattr(alias, "alias_type", None),
                    "modelId": str(getattr(model, "id", "") or ""),
                    "modelCode": getattr(model, "model_code", None),
                    "modelName": getattr(model, "model_name", None),
                }
            )
    return findings


def cleanup_model_catalog_scope_mismatches(
    session: Session,
    *,
    category_code: str | None = None,
    operator_id: str = "model-catalog-scope-cleanup",
    dry_run: bool = True,
) -> dict[str, Any]:
    findings = find_model_catalog_scope_mismatches(
        session,
        category_code=category_code,
        active_only=True,
    )
    resolved_category_code = resolve_category_code(category_code) or None
    if dry_run or not findings:
        return _cleanup_summary(
            findings=findings,
            category_code=resolved_category_code,
            dry_run=dry_run,
            cleaned_model_count=0,
            cleaned_alias_count=0,
            sync_summaries=[],
        )

    model_ids = [row["resourceId"] for row in findings if row.get("resourceType") == "model"]
    alias_ids = [row["resourceId"] for row in findings if row.get("resourceType") == "alias"]

    models_by_id = {
        str(row.id): row
        for row in session.execute(
            select(CategoryModelCatalog)
            .where(CategoryModelCatalog.id.in_(tuple(model_ids or ("",))))
            .options(
                selectinload(CategoryModelCatalog.category),
                selectinload(CategoryModelCatalog.aliases),
            )
        ).scalars().all()
    }
    aliases_by_id = {
        str(row.id): row
        for row in session.execute(
            select(CategoryModelAlias)
            .where(CategoryModelAlias.id.in_(tuple(alias_ids or ("",))))
            .options(
                selectinload(CategoryModelAlias.model).selectinload(CategoryModelCatalog.category),
            )
        ).scalars().all()
    }

    cleaned_model_count = 0
    cleaned_alias_count = 0
    touched_categories: dict[str, Any] = {}

    for finding in findings:
        if finding.get("resourceType") == "model":
            model = models_by_id.get(str(finding.get("resourceId") or ""))
            if model is None:
                continue
            before = {
                "status": str(getattr(model, "status", "") or ""),
                "aliasStatuses": {
                    str(getattr(alias, "id", "") or ""): str(getattr(alias, "status", "") or "")
                    for alias in list(getattr(model, "aliases", []) or [])
                },
            }
            changed_alias_ids: list[str] = []
            if str(getattr(model, "status", "") or "").upper() != "INACTIVE":
                model.status = "INACTIVE"
                cleaned_model_count += 1
            for alias in list(getattr(model, "aliases", []) or []):
                if str(getattr(alias, "status", "") or "").upper() == "INACTIVE":
                    continue
                alias.status = "INACTIVE"
                changed_alias_ids.append(str(getattr(alias, "id", "") or ""))
                cleaned_alias_count += 1
            touched_categories[str(getattr(model, "category_id", "") or "")] = getattr(model, "category", None)
            session.add(
                ProductAttrAuditLog(
                    operator_id=operator_id,
                    resource_type="category_model_catalog",
                    resource_id=str(getattr(model, "id", "") or ""),
                    action="CATEGORY_SCOPE_CLEANUP",
                    before_json=before,
                    after_json={
                        "status": "INACTIVE",
                        "reason": finding.get("reason"),
                        "categoryCode": finding.get("categoryCode"),
                        "deactivatedAliasIds": changed_alias_ids,
                    },
                )
            )
            continue

        alias = aliases_by_id.get(str(finding.get("resourceId") or ""))
        if alias is None:
            continue
        if str(getattr(alias, "status", "") or "").upper() != "INACTIVE":
            before = {
                "status": str(getattr(alias, "status", "") or ""),
                "aliasText": getattr(alias, "alias_text", None),
            }
            alias.status = "INACTIVE"
            cleaned_alias_count += 1
            model = getattr(alias, "model", None)
            touched_categories[str(getattr(model, "category_id", "") or "")] = getattr(model, "category", None)
            session.add(
                ProductAttrAuditLog(
                    operator_id=operator_id,
                    resource_type="category_model_alias",
                    resource_id=str(getattr(alias, "id", "") or ""),
                    action="CATEGORY_SCOPE_CLEANUP",
                    before_json=before,
                    after_json={
                        "status": "INACTIVE",
                        "reason": finding.get("reason"),
                        "categoryCode": finding.get("categoryCode"),
                        "modelId": str(getattr(model, "id", "") or ""),
                    },
                )
            )

    session.flush()

    sync_summaries: list[dict[str, Any]] = []
    for category in sorted(
        (row for row in touched_categories.values() if row is not None),
        key=lambda row: str(getattr(row, "code", "") or ""),
    ):
        sync_summaries.append(
            sync_category_model_catalog_to_tasks_with_session(
                session,
                category=category,
            )
        )
    session.flush()

    return _cleanup_summary(
        findings=findings,
        category_code=resolved_category_code,
        dry_run=False,
        cleaned_model_count=cleaned_model_count,
        cleaned_alias_count=cleaned_alias_count,
        sync_summaries=sync_summaries,
    )


def _audit_summary(
    *,
    findings: list[dict[str, Any]],
    category_code: str | None,
    active_only: bool,
) -> dict[str, Any]:
    category_counts = Counter(str(row["categoryCode"]) for row in findings)
    reason_counts = Counter(str(row["reason"]) for row in findings)
    resource_counts = Counter(str(row["resourceType"]) for row in findings)
    return {
        "categoryCode": category_code,
        "activeOnly": active_only,
        "findingCount": len(findings),
        "resourceCounts": dict(sorted(resource_counts.items())),
        "categoryCounts": dict(sorted(category_counts.items())),
        "reasonCounts": dict(sorted(reason_counts.items())),
        "items": findings,
    }


def _cleanup_summary(
    *,
    findings: list[dict[str, Any]],
    category_code: str | None,
    dry_run: bool,
    cleaned_model_count: int,
    cleaned_alias_count: int,
    sync_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    category_counts = Counter(str(row["categoryCode"]) for row in findings)
    reason_counts = Counter(str(row["reason"]) for row in findings)
    resource_counts = Counter(str(row["resourceType"]) for row in findings)
    return {
        "categoryCode": category_code,
        "dryRun": dry_run,
        "findingCount": len(findings),
        "matchedModelCount": int(resource_counts.get("model", 0)),
        "matchedAliasCount": int(resource_counts.get("alias", 0)),
        "cleanedModelCount": 0 if dry_run else cleaned_model_count,
        "cleanedAliasCount": 0 if dry_run else cleaned_alias_count,
        "syncedCategoryCount": 0 if dry_run else len(sync_summaries),
        "syncedCategories": [] if dry_run else sync_summaries,
        "resourceCounts": dict(sorted(resource_counts.items())),
        "categoryCounts": dict(sorted(category_counts.items())),
        "reasonCounts": dict(sorted(reason_counts.items())),
        "items": findings,
    }


def _model_scope_text(model: CategoryModelCatalog) -> str:
    parts = (
        getattr(model, "brand_name", None),
        getattr(model, "series_name", None),
        getattr(model, "model_name", None),
        getattr(model, "model_code", None),
    )
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def _active_alias_count(model: CategoryModelCatalog) -> int:
    return sum(
        1
        for alias in list(getattr(model, "aliases", []) or [])
        if str(getattr(alias, "status", "") or "").upper() == "ACTIVE"
    )
