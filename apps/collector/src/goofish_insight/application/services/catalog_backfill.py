from __future__ import annotations

import re
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...category_compat import (
    compatible_scope_keys,
    is_apple_computer_scope,
    is_garmin_watch_scope,
    resolve_category_code,
)
from ...db import session_scope
from ...models import (
    Category,
    CategoryAttrTemplate,
    Item,
    ItemSpecEnrichment,
    OutboxEvent,
    OutboxStatus,
    ProductSpu,
    ProductStatus,
)
from ...domain.catalog.blueprints import (
    BACKFILL_BLUEPRINTS,
    CatalogBackfillBlueprint,
)
from ...pricing import build_product_label, build_spec_label, normalize_product_line
from .pricing_domain import APPLE_ANALYSIS_PRODUCT_LINES
from ...specs import extract_rule_specs, normalize_storage_gb
from .catalog_queries import build_catalog_template_detail
from .catalog_outbox import process_catalog_outbox_events
from .catalog_preview import preview_catalog_snapshot
from .catalog_category_quality import catalog_scope_mismatch_reason
from .catalog_persistence import persist_catalog_payload
from .catalog_template import persist_catalog_template_payload
from .catalog_write import prepare_catalog_persist_plan
from .xianyu_category_mapping import resolve_xianyu_category_mapping_with_session


class CatalogBackfillPreviewError(RuntimeError):
    pass


_GARMIN_FORERUNNER_MIP_MODEL_TOKENS = ("255", "955", "945")
_GARMIN_FORERUNNER_AMOLED_MODEL_TOKENS = ("165", "265", "965")


def preview_catalog_backfill_item(
    *,
    item_id: str,
    category_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return preview_catalog_backfill_item_with_session(
            session,
            item_id=item_id,
            category_id=category_id,
            template_id=template_id,
        )


def build_catalog_backfill_template_payload(*, business_domain: str) -> dict[str, Any]:
    blueprint = _require_blueprint(business_domain)
    normalized_domain = resolve_category_code(business_domain.strip()) or blueprint.business_domain
    return {
        "requestId": f"catalog-backfill-template-{normalized_domain}-v{blueprint.template_version}",
        "category": {
            "id": blueprint.category_id,
            "code": blueprint.category_code,
            "name": blueprint.category_name,
            "path": blueprint.category_path,
            "level": blueprint.category_level,
            "status": "ACTIVE",
        },
        "attributes": [
            {
                "id": str(uuid5(NAMESPACE_URL, f"goofish:catalog-attribute:{normalized_domain}:{attribute['code']}")),
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "code": attribute["code"],
                "name": attribute["name"],
                "dataType": attribute["dataType"],
                "valueScope": attribute["valueScope"],
                "isMulti": attribute.get("isMulti", False),
                "unit": attribute.get("unit"),
                "status": "ACTIVE",
                "options": [],
            }
            for attribute in blueprint.attributes
        ],
        "template": {
            "id": blueprint.template_id,
            "version": blueprint.template_version,
            "status": "PUBLISHED",
            "publishedBy": "catalog-backfill",
            "items": [
                {
                    "attributeCode": item["attributeCode"],
                    "isRequired": False,
                    "isSale": bool(item.get("isSale", False)),
                    "isFilter": True,
                    "isSearch": True,
                    "isDisplay": True,
                    "sortNo": item.get("sortNo", 0),
                }
                for item in blueprint.template_items
            ],
        },
    }


def persist_catalog_backfill_template(
    *,
    business_domain: str,
    operator_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    payload = build_catalog_backfill_template_payload(business_domain=business_domain)
    return persist_catalog_template_payload(
        payload=payload,
        operator_id=operator_id,
        dry_run=dry_run,
    )


def ensure_catalog_backfill_template(
    *,
    business_domain: str,
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    blueprint = _require_blueprint(business_domain)
    with session_scope() as session:
        category = session.get(Category, blueprint.category_id)
        template = session.get(CategoryAttrTemplate, blueprint.template_id)
        if category is not None and template is not None:
            return {
                "dryRun": dry_run,
                "businessDomain": blueprint.business_domain,
                "status": "existing",
                "categoryId": blueprint.category_id,
                "templateId": blueprint.template_id,
            }

    result = persist_catalog_backfill_template(
        business_domain=business_domain,
        operator_id=operator_id,
        dry_run=dry_run,
    )
    return {
        **result,
        "businessDomain": blueprint.business_domain,
        "status": "created" if not dry_run else "would_create",
    }


def persist_catalog_backfill_item(
    *,
    item_id: str,
    operator_id: str,
    dry_run: bool = True,
    allow_warnings: bool = False,
    category_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    preview = preview_catalog_backfill_item(
        item_id=item_id,
        category_id=category_id,
        template_id=template_id,
    )
    if preview["warnings"] and not allow_warnings:
        raise CatalogBackfillPreviewError(
            f"Backfill preview has warnings for item {item_id}: {', '.join(preview['warnings'])}"
        )
    return persist_catalog_payload(
        payload=preview["payload"],
        operator_id=operator_id,
        dry_run=dry_run,
    )


def persist_catalog_backfill_batch(
    *,
    business_domain: str,
    operator_id: str,
    limit: int = 20,
    offset: int = 0,
    dry_run: bool = True,
    enriched_only: bool = True,
    allow_warnings: bool = False,
    skip_existing: bool = True,
    category_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    preview = preview_catalog_backfill_batch(
        business_domain=business_domain,
        limit=limit,
        offset=offset,
        enriched_only=enriched_only,
        category_id=category_id,
        template_id=template_id,
    )
    results: list[dict[str, Any]] = []
    processed_count = 0
    failed_count = 0
    skipped_count = 0
    skip_reason_counts: dict[str, int] = {}

    for item in preview["items"]:
        item_id = str(item["itemId"])
        try:
            detail = persist_catalog_backfill_item(
                item_id=item_id,
                operator_id=operator_id,
                dry_run=dry_run,
                allow_warnings=allow_warnings,
                category_id=category_id,
                template_id=template_id,
            )
            processed_count += 1
            results.append(
                {
                    "itemId": item_id,
                    "status": "processed",
                    "applyState": "would_apply" if dry_run else "applied",
                    "spuId": detail["spuId"],
                    "skuCount": detail["skuCount"],
                    "outboxEventId": detail["outboxEventId"],
                }
            )
        except Exception as exc:
            if skip_existing and "SPU already exists" in str(exc):
                skipped_count += 1
                skip_reason_counts["existing_spu"] = skip_reason_counts.get("existing_spu", 0) + 1
                results.append(
                    {
                        "itemId": item_id,
                        "status": "skipped_existing",
                        "skipReason": "existing_spu",
                        "error": str(exc),
                    }
                )
                continue
            failed_count += 1
            results.append(
                {
                    "itemId": item_id,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    return {
        "businessDomain": preview["businessDomain"],
        "dryRun": dry_run,
        "limit": preview["limit"],
        "offset": preview["offset"],
        "enrichedOnly": preview["enrichedOnly"],
        "applyMode": "dry_run" if dry_run else "apply",
        "wouldApplyCount": processed_count if dry_run else 0,
        "appliedCount": processed_count if not dry_run else 0,
        "candidateCount": len(preview["items"]),
        "processedCount": processed_count,
        "skippedCount": skipped_count,
        "failedCount": failed_count,
        "warningCounts": preview["warningCounts"],
        "skipReasonCounts": skip_reason_counts,
        "items": results,
    }


def run_catalog_backfill_migration(
    *,
    business_domain: str,
    operator_id: str,
    batch_size: int = 100,
    dry_run: bool = False,
    enriched_only: bool = True,
    allow_warnings: bool = False,
    skip_existing: bool = True,
    process_outbox_after_batch: bool = True,
    max_batches: int | None = None,
) -> dict[str, Any]:
    blueprint = _require_blueprint(business_domain)
    template_result = ensure_catalog_backfill_template(
        business_domain=business_domain,
        operator_id=operator_id,
        dry_run=dry_run,
    )
    preview = preview_catalog_backfill_batch(
        business_domain=business_domain,
        limit=1,
        offset=0,
        enriched_only=enriched_only,
        category_id=blueprint.category_id,
        template_id=blueprint.template_id,
    )
    total = int(preview["total"])
    resolved_batch_size = min(max(int(batch_size), 1), 500)
    batches: list[dict[str, Any]] = []
    processed_count = 0
    skipped_count = 0
    failed_count = 0
    outbox_processed_count = 0
    outbox_failed_count = 0
    skip_reason_counts: dict[str, int] = {}
    offset = 0
    batch_index = 0

    while offset < total:
        if max_batches is not None and batch_index >= max_batches:
            break
        batch = persist_catalog_backfill_batch(
            business_domain=business_domain,
            operator_id=operator_id,
            limit=resolved_batch_size,
            offset=offset,
            dry_run=dry_run,
            enriched_only=enriched_only,
            allow_warnings=allow_warnings,
            skip_existing=skip_existing,
            category_id=blueprint.category_id,
            template_id=blueprint.template_id,
        )
        processed_count += int(batch["processedCount"])
        skipped_count += int(batch["skippedCount"])
        failed_count += int(batch["failedCount"])
        batch_skip_reason_counts = dict(batch.get("skipReasonCounts") or {})
        for reason, count in batch_skip_reason_counts.items():
            skip_reason_counts[str(reason)] = skip_reason_counts.get(str(reason), 0) + int(count)

        batch_summary = {
            "batchIndex": batch_index + 1,
            "offset": offset,
            "candidateCount": batch["candidateCount"],
            "processedCount": batch["processedCount"],
            "skippedCount": batch["skippedCount"],
            "failedCount": batch["failedCount"],
            "skipReasonCounts": batch_skip_reason_counts,
        }
        if batch["failedCount"]:
            batch_summary["failures"] = [
                item for item in batch["items"] if item["status"] == "failed"
            ][:10]

        if not dry_run and process_outbox_after_batch:
            outbox_result = _drain_catalog_outbox(limit=max(resolved_batch_size * 2, 50))
            outbox_processed_count += int(outbox_result["processedCount"])
            outbox_failed_count += int(outbox_result["failedCount"])
            batch_summary["outbox"] = outbox_result

        batches.append(batch_summary)
        offset += int(batch["limit"])
        batch_index += 1

    report = build_catalog_backfill_reconciliation_report(business_domain=business_domain)
    outbox_total = outbox_processed_count + outbox_failed_count
    return {
        "businessDomain": blueprint.business_domain,
        "dryRun": dry_run,
        "applyMode": "dry_run" if dry_run else "apply",
        "wouldApplyCount": processed_count if dry_run else 0,
        "appliedCount": processed_count if not dry_run else 0,
        "template": template_result,
        "batchSize": resolved_batch_size,
        "totalCandidates": total,
        "batchesRun": batch_index,
        "processedCount": processed_count,
        "skippedCount": skipped_count,
        "failedCount": failed_count,
        "skipReasonCounts": skip_reason_counts,
        "outboxProcessedCount": outbox_processed_count,
        "outboxFailedCount": outbox_failed_count,
        "outboxSuccessRate": round(outbox_processed_count / outbox_total, 4) if outbox_total > 0 else None,
        "report": report,
        "batches": batches,
    }


def build_catalog_backfill_reconciliation_report(*, business_domain: str) -> dict[str, Any]:
    with session_scope() as session:
        return build_catalog_backfill_reconciliation_report_with_session(
            session,
            business_domain=business_domain,
        )


def build_catalog_backfill_reconciliation_report_with_session(
    session: Session,
    *,
    business_domain: str,
) -> dict[str, Any]:
    blueprint = _require_blueprint(business_domain)
    scope_keys = compatible_scope_keys(blueprint.business_domain)
    total_items = int(
        session.execute(
            select(func.count(Item.id)).where(Item.business_domain.in_(scope_keys))
        ).scalar_one()
        or 0
    )
    enriched_items = int(
        session.execute(
            select(func.count(Item.id)).where(
                Item.business_domain.in_(scope_keys),
                Item.spec_enrichment.has(),
            )
        ).scalar_one()
        or 0
    )
    migrated_spus = int(
        session.execute(
            select(func.count(ProductSpu.id)).where(
                ProductSpu.category_id == blueprint.category_id,
                ProductSpu.template_id == blueprint.template_id,
            )
        ).scalar_one()
        or 0
    )
    pending_outbox = int(
        session.execute(
            select(func.count(OutboxEvent.id))
            .join(ProductSpu, ProductSpu.id == OutboxEvent.aggregate_id)
            .where(
                ProductSpu.category_id == blueprint.category_id,
                OutboxEvent.status != OutboxStatus.DONE,
            )
        ).scalar_one()
        or 0
    )
    category = session.get(Category, blueprint.category_id)
    template = session.get(CategoryAttrTemplate, blueprint.template_id)
    recent_spus = session.execute(
        select(ProductSpu)
        .where(
            ProductSpu.category_id == blueprint.category_id,
            ProductSpu.template_id == blueprint.template_id,
        )
        .order_by(ProductSpu.updated_at.desc(), ProductSpu.created_at.desc())
        .limit(10)
    ).scalars()
    coverage_ratio = None
    if enriched_items > 0:
        coverage_ratio = round(migrated_spus / enriched_items, 4)
    return {
        "businessDomain": blueprint.business_domain,
        "target": {
            "categoryId": blueprint.category_id,
            "templateId": blueprint.template_id,
            "categoryExists": category is not None,
            "templateExists": template is not None,
        },
        "counts": {
            "legacyItemTotal": total_items,
            "legacyEnrichedItemTotal": enriched_items,
            "migratedSpuTotal": migrated_spus,
            "pendingOutboxTotal": pending_outbox,
        },
        "coverageRatio": coverage_ratio,
        "recentSpus": [
            {
                "id": spu.id,
                "title": spu.title,
                "status": spu.status.value,
                "merchantId": spu.merchant_id,
                "skuCount": len(spu.skus),
                "updatedAt": spu.updated_at,
            }
            for spu in recent_spus
        ],
    }


def preview_catalog_backfill_batch(
    *,
    business_domain: str,
    limit: int = 20,
    offset: int = 0,
    enriched_only: bool = False,
    category_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return preview_catalog_backfill_batch_with_session(
            session,
            business_domain=business_domain,
            limit=limit,
            offset=offset,
            enriched_only=enriched_only,
            category_id=category_id,
            template_id=template_id,
        )


def preview_catalog_backfill_item_with_session(
    session: Session,
    *,
    item_id: str,
    category_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    normalized_item_id = item_id.strip()
    if not normalized_item_id:
        raise CatalogBackfillPreviewError("item_id is required.")

    stmt = (
        select(Item)
        .where(Item.item_id == normalized_item_id)
        .options(
            selectinload(Item.spec_enrichment),
            selectinload(Item.seller),
        )
    )
    item = session.execute(stmt).scalar_one_or_none()
    if item is None:
        raise CatalogBackfillPreviewError(f"Item not found: {normalized_item_id}")

    blueprint, resolved_category_id, resolved_template_id = _resolve_backfill_target(
        session=session,
        item=item,
        category_id=category_id,
        template_id=template_id,
    )

    return _build_backfill_preview_result(
        item=item,
        blueprint=blueprint,
        category_id=resolved_category_id,
        template_id=resolved_template_id,
    )


def preview_catalog_backfill_batch_with_session(
    session: Session,
    *,
    business_domain: str,
    limit: int = 20,
    offset: int = 0,
    enriched_only: bool = False,
    category_id: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    normalized_domain = business_domain.strip()
    scope_keys = compatible_scope_keys(normalized_domain) if normalized_domain else ()

    resolved_limit = min(max(limit, 1), 500)
    resolved_offset = max(offset, 0)
    total_stmt = select(func.count(Item.id))
    if scope_keys:
        total_stmt = total_stmt.where(Item.business_domain.in_(scope_keys))
    if enriched_only:
        total_stmt = total_stmt.where(Item.spec_enrichment.has())
    total = int(session.execute(total_stmt).scalar_one())

    rows_stmt = select(Item).options(
        selectinload(Item.spec_enrichment),
        selectinload(Item.seller),
    )
    if scope_keys:
        rows_stmt = rows_stmt.where(Item.business_domain.in_(scope_keys))
    rows_stmt = rows_stmt.order_by(Item.updated_at.desc()).offset(resolved_offset).limit(resolved_limit)
    if enriched_only:
        rows_stmt = rows_stmt.where(Item.spec_enrichment.has())
    items = session.execute(rows_stmt).scalars().all()
    previews = [
        _build_backfill_preview_result(
            item=item,
            blueprint=resolved_blueprint,
            category_id=resolved_category_id,
            template_id=resolved_template_id,
        )
        for item in items
        for resolved_blueprint, resolved_category_id, resolved_template_id in [
            _resolve_backfill_target(
                session=session,
                item=item,
                category_id=category_id,
                template_id=template_id,
            )
        ]
    ]

    warning_counts: dict[str, int] = {}
    for preview in previews:
        for warning in preview["warnings"]:
            warning_counts[warning] = warning_counts.get(warning, 0) + 1

    return {
        "businessDomain": normalized_domain,
        "limit": resolved_limit,
        "offset": resolved_offset,
        "enrichedOnly": enriched_only,
        "total": total,
        "warningCounts": warning_counts,
        "items": [_summarize_backfill_preview(preview) for preview in previews],
    }


def _build_backfill_preview_result(
    *,
    item: Item,
    blueprint: CatalogBackfillBlueprint,
    category_id: str,
    template_id: str,
) -> dict[str, Any]:
    warnings: list[str] = []
    spec = _spec_for_backfill(item=item, warnings=warnings)

    payload = _build_payload(
        item=item,
        spec=spec,
        blueprint=blueprint,
        category_id=category_id,
        template_id=template_id,
        warnings=warnings,
    )
    mismatch_reason = catalog_scope_mismatch_reason(
        blueprint.category_code,
        title=str(payload.get("spu", {}).get("title") or ""),
        spu_snapshot=payload,
        sku_snapshots=list(payload.get("skus") or []),
    )
    if mismatch_reason is not None:
        warnings.append(f"category_scope_mismatch:{mismatch_reason}")
    snapshot = preview_catalog_snapshot(payload)
    persist_plan = prepare_catalog_persist_plan(payload)

    return {
        "itemId": item.item_id,
        "businessDomain": item.business_domain,
        "warnings": warnings,
        "target": {
            "categoryId": payload["spu"]["categoryId"],
            "categoryCode": blueprint.category_code,
            "categoryName": blueprint.category_name,
            "templateId": payload["spu"]["templateId"],
            "templateVersion": blueprint.template_version,
            "usesDraftTargetIds": (
                category_id == blueprint.category_id and template_id == blueprint.template_id
            ),
        },
        "legacySummary": _build_legacy_summary(item, spec),
        "payload": payload,
        "snapshot": snapshot,
        "persistPlan": persist_plan,
    }


def _resolve_backfill_target(
    *,
    session: Session,
    item: Item,
    category_id: str | None,
    template_id: str | None,
) -> tuple[CatalogBackfillBlueprint, str, str]:
    resolved_template_id = template_id or getattr(item, "resolved_template_id", None)
    resolved_category_id = category_id or getattr(item, "resolved_category_id", None)

    if resolved_template_id:
        detail = build_catalog_template_detail(session, resolved_template_id)
        if detail is None:
            raise CatalogBackfillPreviewError(f"Template not found for catalog backfill preview: {resolved_template_id}")
        blueprint = _blueprint_from_template_detail(item=item, template_detail=detail)
        return blueprint, str(detail["category"]["id"]), str(detail["template"]["id"])

    if template_id:
        detail = build_catalog_template_detail(session, template_id)
        if detail is None:
            raise CatalogBackfillPreviewError(f"Template not found for catalog backfill preview: {template_id}")
        blueprint = _blueprint_from_template_detail(item=item, template_detail=detail)
        return blueprint, str(detail["category"]["id"]), str(detail["template"]["id"])

    mapping = resolve_xianyu_category_mapping_with_session(
        session,
        xianyu_cat_id=item.xianyu_cat_id,
        xianyu_tb_cat_id=item.xianyu_tb_cat_id,
        xianyu_c_cat_id=item.xianyu_c_cat_id,
    )
    if mapping is not None:
        mapping_template_id = getattr(mapping, "template_override_id", None) or getattr(mapping, "template_id", None)
        detail = build_catalog_template_detail(session, mapping_template_id) if mapping_template_id else None
        if detail is not None:
            blueprint = _blueprint_from_template_detail(item=item, template_detail=detail)
            mapped_category_id = getattr(mapping, "category_id", None) or detail["category"]["id"]
            return blueprint, str(mapped_category_id), str(detail["template"]["id"])

    runtime_target = _resolve_runtime_profile_target(
        session=session,
        item=item,
        resolved_category_id=resolved_category_id,
    )
    if runtime_target is not None:
        return runtime_target

    try:
        blueprint = _require_blueprint(item.business_domain)
    except CatalogBackfillPreviewError as exc:
        raise CatalogBackfillPreviewError(
            f"Unsupported business_domain for catalog backfill preview: {item.business_domain}"
        ) from exc
    return blueprint, resolved_category_id or blueprint.category_id, blueprint.template_id


def _blueprint_from_template_detail(
    *,
    item: Item,
    template_detail: dict[str, Any],
) -> CatalogBackfillBlueprint:
    category = dict(template_detail.get("category") or {})
    template = dict(template_detail.get("template") or {})
    items = list(template_detail.get("items") or [])
    return CatalogBackfillBlueprint(
        business_domain=item.business_domain,
        category_id=str(category["id"]),
        category_code=str(category["code"]),
        category_name=str(category["name"]),
        category_path=str(category["path"]),
        category_level=int(category["level"]),
        template_id=str(template["id"]),
        template_version=int(template["version"]),
        attributes=[
            {
                "code": item_detail["attributeCode"],
                "name": item_detail["attributeName"],
                "dataType": item_detail["dataType"],
                "valueScope": item_detail["valueScope"],
                "isMulti": bool(item_detail.get("isMulti", False)),
                "unit": item_detail.get("unit"),
            }
            for item_detail in items
        ],
        template_items=[
            {
                "attributeCode": item_detail["attributeCode"],
                "isSale": bool(item_detail.get("isSale", False)),
                "sortNo": int(item_detail.get("sortNo", 0)),
            }
            for item_detail in items
        ],
    )


def _resolve_runtime_profile_target(
    *,
    session: Session,
    item: Item,
    resolved_category_id: str | None,
) -> tuple[CatalogBackfillBlueprint, str, str] | None:
    if not hasattr(session, "get"):
        return None

    candidate_category_ids: list[str] = []
    for candidate in (
        resolved_category_id,
        getattr(item, "resolved_category_id", None),
        getattr(item, "target_category_id", None),
    ):
        normalized = str(candidate or "").strip()
        if normalized and normalized not in candidate_category_ids:
            candidate_category_ids.append(normalized)

    scope_code = resolve_category_code(item.business_domain)
    if scope_code:
        category_by_code = session.execute(select(Category).where(Category.code == scope_code)).scalar_one_or_none()
        category_id = str(getattr(category_by_code, "id", "") or "")
        if category_id and category_id not in candidate_category_ids:
            candidate_category_ids.append(category_id)

    for category_id in candidate_category_ids:
        category = session.get(Category, category_id)
        if category is None:
            continue
        runtime_profile = getattr(category, "runtime_profile", None)
        active_template_id = str(getattr(runtime_profile, "active_template_id", "") or "").strip()
        if not active_template_id:
            continue
        detail = build_catalog_template_detail(session, active_template_id)
        if detail is None:
            continue
        blueprint = _blueprint_from_template_detail(item=item, template_detail=detail)
        return blueprint, str(category.id), str(detail["template"]["id"])

    return None


def _summarize_backfill_preview(preview: dict[str, Any]) -> dict[str, Any]:
    sku = preview["payload"]["skus"][0]
    return {
        "itemId": preview["itemId"],
        "businessDomain": preview["businessDomain"],
        "sourceTitle": preview["legacySummary"]["title"],
        "spuTitle": preview["payload"]["spu"]["title"],
        "skuCode": sku["skuCode"],
        "price": sku["price"],
        "warnings": preview["warnings"],
        "spuAttributeCount": len(preview["payload"]["spuAttributes"]),
        "skuAttributeCount": len(sku["attributes"]),
        "target": preview["target"],
    }


def _spec_for_backfill(
    *,
    item: Item,
    warnings: list[str],
) -> Any:
    stored_spec = item.spec_enrichment
    if stored_spec is not None:
        return stored_spec

    warnings.append("missing_spec_enrichment")
    rule_spec = extract_rule_specs(item)
    if rule_spec.status != "unresolved":
        warnings.append("used_rule_spec_fallback")
        return rule_spec
    return None


def _build_payload(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    blueprint: CatalogBackfillBlueprint,
    category_id: str,
    template_id: str,
    warnings: list[str],
) -> dict[str, Any]:
    generic_payload = _build_generic_payload(
        item=item,
        spec=spec,
        blueprint=blueprint,
        category_id=category_id,
        template_id=template_id,
        warnings=warnings,
    )
    if generic_payload is not None:
        return generic_payload

    if is_apple_computer_scope(blueprint.business_domain):
        return _build_apple_payload(
            item=item,
            spec=spec,
            blueprint=blueprint,
            category_id=category_id,
            template_id=template_id,
            warnings=warnings,
        )
    if is_garmin_watch_scope(blueprint.business_domain):
        return _build_garmin_payload(
            item=item,
            spec=spec,
            blueprint=blueprint,
            category_id=category_id,
            template_id=template_id,
            warnings=warnings,
        )
    raise CatalogBackfillPreviewError(
        f"Unsupported business_domain for payload build: {blueprint.business_domain}"
    )


def _build_generic_payload(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    blueprint: CatalogBackfillBlueprint,
    category_id: str,
    template_id: str,
    warnings: list[str],
) -> dict[str, Any] | None:
    groups = _catalog_attribute_groups_for_backfill(
        item=item,
        spec=spec,
        blueprint=blueprint,
    )
    if not any(groups[group] for group in ("spuAttributes", "skuAttributes", "saleAttributes")):
        return None

    product_line = _first_text_attribute(groups["spuAttributes"], "product_line")
    model_name = _first_text_attribute(groups["spuAttributes"], "model_name")
    source_is_rule_fallback = item.spec_enrichment is None and spec is not None
    source_is_default_inference = item.spec_enrichment is None and spec is None
    if product_line is None and model_name is None:
        warnings.append("missing_product_identity")

    if is_apple_computer_scope(blueprint.business_domain):
        memory_gb = _first_number_attribute(groups["skuAttributes"], "memory_gb")
        storage_gb = _first_number_attribute(groups["skuAttributes"], "storage_gb")
        if source_is_rule_fallback and (memory_gb is not None or storage_gb is not None):
            warnings.append("used_rule_memory_storage_fallback")
        if source_is_default_inference and (memory_gb is not None or storage_gb is not None):
            warnings.append("used_rule_memory_storage_fallback")
        if memory_gb is None:
            warnings.append("missing_memory_gb")
        if storage_gb is None:
            warnings.append("missing_storage_gb")
    if is_garmin_watch_scope(blueprint.business_domain):
        display_type = _first_text_attribute(groups["spuAttributes"], "display_type")
        case_size_mm = _first_number_attribute(groups["spuAttributes"], "case_size_mm")
        if source_is_rule_fallback and display_type is not None:
            warnings.append("used_model_default_display_type")
        if source_is_rule_fallback and case_size_mm is not None:
            warnings.append("used_model_default_case_size_mm")
        if source_is_default_inference and display_type is not None:
            warnings.append("used_model_default_display_type")
        if source_is_default_inference and case_size_mm is not None:
            warnings.append("used_model_default_case_size_mm")
        if display_type is None:
            warnings.append("missing_display_type")
        if case_size_mm is None:
            warnings.append("missing_case_size_mm")

    return _build_single_sku_payload(
        item=item,
        blueprint=blueprint,
        category_id=category_id,
        template_id=template_id,
        spu_title=_build_generic_spu_title(item=item, groups=groups),
        spu_attributes=groups["spuAttributes"],
        sku_attributes=groups["skuAttributes"],
        sale_attributes=groups["saleAttributes"],
    )


def _catalog_attribute_groups_for_backfill(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    blueprint: CatalogBackfillBlueprint,
) -> dict[str, list[dict[str, Any]]]:
    payload = dict(spec.extraction_payload or {}) if spec is not None else {}
    source = payload.get("catalogAttributes")
    if not isinstance(source, dict):
        source = payload

    groups = {
        "spuAttributes": [dict(row) for row in list(source.get("spuAttributes") or []) if isinstance(row, dict)],
        "skuAttributes": [dict(row) for row in list(source.get("skuAttributes") or []) if isinstance(row, dict)],
        "saleAttributes": [dict(row) for row in list(source.get("saleAttributes") or []) if isinstance(row, dict)],
    }
    if any(groups[group] for group in groups):
        return groups

    return _fallback_catalog_attribute_groups(
        item=item,
        spec=spec,
        blueprint=blueprint,
    )


def _fallback_catalog_attribute_groups(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    blueprint: CatalogBackfillBlueprint,
) -> dict[str, list[dict[str, Any]]]:
    groups = {
        "spuAttributes": [],
        "skuAttributes": [],
        "saleAttributes": [],
    }
    attribute_map = {str(attribute["code"]): dict(attribute) for attribute in blueprint.attributes}
    template_map = {
        str(template_item["attributeCode"]): dict(template_item)
        for template_item in blueprint.template_items
    }

    for attribute_code, attribute in attribute_map.items():
        template_item = template_map.get(attribute_code, {})
        target_group = "saleAttributes" if template_item.get("isSale") else (
            "skuAttributes" if str(attribute.get("valueScope") or "").upper() == "SKU" else "spuAttributes"
        )
        value = _legacy_attribute_value(item=item, spec=spec, attribute_code=attribute_code)
        if value is None:
            continue
        groups[target_group].extend(
            _rows_from_legacy_attribute_value(
                attribute_code=attribute_code,
                attribute=attribute,
                value=value,
            )
        )

    return groups


def _legacy_attribute_value(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    attribute_code: str,
) -> Any:
    if attribute_code == "product_line":
        return _first_text(spec.product_line if spec else None, item.normalized_model_family)
    if attribute_code == "model_name":
        return _first_text(spec.model_name if spec else None, item.normalized_model)
    if attribute_code == "generation":
        return _first_text(spec.generation if spec else None)
    if attribute_code == "display_type":
        inferred_display_type, _ = _infer_garmin_display_case_defaults(item=item)
        return _first_text(spec.display_type if spec else None, inferred_display_type)
    if attribute_code == "case_size_mm":
        _, inferred_case_size_mm = _infer_garmin_display_case_defaults(item=item)
        return _first_int(spec.case_size_mm if spec else None, inferred_case_size_mm)
    if attribute_code == "is_solar":
        return spec.is_solar if spec else None
    if attribute_code == "edition_tags":
        return list(spec.edition_tags or []) if spec and spec.edition_tags else None
    if attribute_code == "chip_family":
        return _first_text(spec.chip_family if spec else None, item.normalized_chip)
    if attribute_code == "screen_size_in":
        return spec.screen_size_in if spec else None
    if attribute_code == "cpu_cores":
        return spec.cpu_cores if spec else None
    if attribute_code == "gpu_cores":
        return spec.gpu_cores if spec else None
    if attribute_code == "memory_gb":
        if spec and spec.memory_gb is not None:
            return spec.memory_gb
        if item.normalized_memory_gb is not None:
            return item.normalized_memory_gb
        rule_spec = extract_rule_specs(item)
        if str(getattr(rule_spec, "status", "") or "").lower() != "unresolved":
            return getattr(rule_spec, "memory_gb", None)
        return None
    if attribute_code == "storage_gb":
        if spec and spec.storage_gb is not None:
            return spec.storage_gb
        normalized_storage = normalize_storage_gb(item.normalized_storage_gb)
        if normalized_storage is not None:
            return normalized_storage
        rule_spec = extract_rule_specs(item)
        if str(getattr(rule_spec, "status", "") or "").lower() != "unresolved":
            return getattr(rule_spec, "storage_gb", None)
        return None
    return None


def _rows_from_legacy_attribute_value(
    *,
    attribute_code: str,
    attribute: dict[str, Any],
    value: Any,
) -> list[dict[str, Any]]:
    data_type = str(attribute.get("dataType") or "").upper()
    unit = attribute.get("unit")
    is_multi = bool(attribute.get("isMulti", False))
    if value is None or value == "":
        return []

    if data_type == "TEXT":
        values = value if isinstance(value, list) and is_multi else [value]
        return [
            {"attributeCode": attribute_code, "textValue": str(entry).strip()}
            for entry in values
            if str(entry).strip()
        ]

    if data_type == "NUMBER":
        values = value if isinstance(value, list) and is_multi else [value]
        rows: list[dict[str, Any]] = []
        for entry in values:
            number_value = _decimal_to_number(entry)
            if number_value is None:
                continue
            rows.append(
                {
                    "attributeCode": attribute_code,
                    "numberValue": number_value,
                    "normalizedNumberValue": number_value,
                    "unit": unit,
                }
            )
        return rows

    if data_type == "BOOLEAN":
        values = value if isinstance(value, list) and is_multi else [value]
        return [
            {"attributeCode": attribute_code, "boolValue": bool(entry)}
            for entry in values
            if entry is not None
        ]

    if data_type == "ENUM":
        values = value if isinstance(value, list) and is_multi else [value]
        return [
            {"attributeCode": attribute_code, "optionCode": str(entry).strip()}
            for entry in values
            if str(entry).strip()
        ]

    return [{"attributeCode": attribute_code, "jsonValue": list(value) if isinstance(value, list) else value}]


def _build_generic_spu_title(
    *,
    item: Item,
    groups: dict[str, list[dict[str, Any]]],
) -> str:
    identity = _first_text(
        _first_text_attribute(groups["spuAttributes"], "model_name"),
        _first_text_attribute(groups["spuAttributes"], "product_line"),
        item.normalized_model,
        item.normalized_model_family,
        item.title,
    )
    segments: list[str] = [identity] if identity else []
    for segment in (
        _format_title_number(_first_number_attribute(groups["spuAttributes"], "screen_size_in"), suffix="in"),
        _first_text_attribute(groups["spuAttributes"], "chip_family"),
        _format_title_number(_first_number_attribute(groups["spuAttributes"], "cpu_cores"), suffix="C CPU"),
        _format_title_number(_first_number_attribute(groups["spuAttributes"], "gpu_cores"), suffix="C GPU"),
        _format_title_number(_first_number_attribute(groups["skuAttributes"], "memory_gb"), suffix="G"),
        _format_title_number(_first_number_attribute(groups["skuAttributes"], "storage_gb"), suffix="G"),
        _first_text_attribute(groups["spuAttributes"], "generation"),
        _first_text_attribute(groups["spuAttributes"], "display_type"),
        _format_title_number(_first_number_attribute(groups["spuAttributes"], "case_size_mm"), suffix="mm"),
        "Solar" if _first_bool_attribute(groups["spuAttributes"], "is_solar") else None,
    ):
        _append_title_segment(segments, segment)
    return " / ".join(segment for segment in segments if segment) or item.title


def _append_title_segment(segments: list[str], segment: str | None) -> None:
    if not segment:
        return
    normalized_segment = str(segment).strip()
    if not normalized_segment:
        return
    lowered_segment = normalized_segment.lower()
    for existing in segments:
        lowered_existing = str(existing).lower()
        if lowered_segment == lowered_existing or lowered_segment in lowered_existing.split():
            return
    segments.append(normalized_segment)


def _first_text_attribute(rows: list[dict[str, Any]], attribute_code: str) -> str | None:
    for row in rows:
        if str(row.get("attributeCode")) != attribute_code:
            continue
        value = row.get("textValue")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _first_number_attribute(rows: list[dict[str, Any]], attribute_code: str) -> int | float | None:
    for row in rows:
        if str(row.get("attributeCode")) == attribute_code and row.get("numberValue") is not None:
            return row["numberValue"]
    return None


def _first_bool_attribute(rows: list[dict[str, Any]], attribute_code: str) -> bool | None:
    for row in rows:
        if str(row.get("attributeCode")) == attribute_code and row.get("boolValue") is not None:
            return bool(row["boolValue"])
    return None


def _format_title_number(value: int | float | Decimal | None, *, suffix: str) -> str | None:
    number = _decimal_to_number(value)
    if number is None:
        return None
    return f"{number}{suffix}"


def _build_apple_payload(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    blueprint: CatalogBackfillBlueprint,
    category_id: str,
    template_id: str,
    warnings: list[str],
) -> dict[str, Any]:
    product_line = _first_text(spec.product_line if spec else None, item.normalized_model_family)
    model_name = _first_text(spec.model_name if spec else None, item.normalized_model)
    chip_family = _first_text(spec.chip_family if spec else None, item.normalized_chip)
    screen_size_in = spec.screen_size_in if spec else None
    cpu_cores = spec.cpu_cores if spec else None
    gpu_cores = spec.gpu_cores if spec else None
    resolved_memory_storage = _resolve_apple_memory_storage(
        item=item,
        spec=spec,
    )
    memory_gb = resolved_memory_storage["memoryGb"]
    storage_gb = resolved_memory_storage["storageGb"]
    if resolved_memory_storage["usedRuleFallback"]:
        warnings.append("used_rule_memory_storage_fallback")
    product_line = normalize_product_line(
        product_line=product_line,
        model_name=model_name,
        allowed_values=APPLE_ANALYSIS_PRODUCT_LINES,
    )
    if product_line not in APPLE_ANALYSIS_PRODUCT_LINES:
        warnings.append("invalid_product_line")
        product_line = None

    if product_line is None and model_name is None:
        warnings.append("missing_product_identity")
    if memory_gb is None:
        warnings.append("missing_memory_gb")
    if storage_gb is None:
        warnings.append("missing_storage_gb")

    product_label = build_product_label(
        business_domain=item.business_domain,
        product_line=product_line,
        model_name=model_name,
        screen_size_in=screen_size_in,
        chip_family=chip_family,
    )
    spec_label, _ = build_spec_label(
        business_domain=item.business_domain,
        product_label=product_label,
        display_type=None,
        case_size_mm=None,
        is_solar=None,
        screen_size_in=screen_size_in,
        chip_family=chip_family,
        cpu_cores=cpu_cores,
        gpu_cores=gpu_cores,
        memory_gb=memory_gb,
        storage_gb=storage_gb,
    )
    spu_title = spec_label or product_label or item.title

    spu_attributes: list[dict[str, Any]] = []
    sku_attributes: list[dict[str, Any]] = []

    _append_text_value(spu_attributes, "product_line", product_line)
    _append_text_value(spu_attributes, "model_name", model_name)
    _append_text_value(spu_attributes, "chip_family", chip_family)
    _append_number_value(spu_attributes, "screen_size_in", screen_size_in, unit="inch")
    _append_number_value(spu_attributes, "cpu_cores", cpu_cores)
    _append_number_value(spu_attributes, "gpu_cores", gpu_cores)
    _append_number_value(sku_attributes, "memory_gb", memory_gb, unit="GB")
    _append_number_value(sku_attributes, "storage_gb", storage_gb, unit="GB")

    return _build_single_sku_payload(
        item=item,
        blueprint=blueprint,
        category_id=category_id,
        template_id=template_id,
        spu_title=spu_title,
        spu_attributes=spu_attributes,
        sku_attributes=sku_attributes,
        sale_attributes=[],
    )


def _build_garmin_payload(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
    blueprint: CatalogBackfillBlueprint,
    category_id: str,
    template_id: str,
    warnings: list[str],
) -> dict[str, Any]:
    product_line = _first_text(spec.product_line if spec else None, item.normalized_model_family)
    model_name = _first_text(spec.model_name if spec else None, item.normalized_model)
    generation = _first_text(spec.generation if spec else None)
    inferred_display_type, inferred_case_size_mm = _infer_garmin_display_case_defaults(item=item)
    display_type = _first_text(spec.display_type if spec else None, inferred_display_type)
    case_size_mm = _first_int(spec.case_size_mm if spec else None, inferred_case_size_mm)
    is_solar = spec.is_solar if spec else None
    edition_tags = list(spec.edition_tags or []) if spec else []

    if product_line is None and model_name is None:
        warnings.append("missing_product_identity")
    if display_type is None:
        warnings.append("missing_display_type")
    if case_size_mm is None:
        warnings.append("missing_case_size_mm")

    product_label = build_product_label(
        business_domain=item.business_domain,
        product_line=product_line,
        model_name=model_name,
        screen_size_in=None,
        chip_family=None,
    )
    spec_label, _ = build_spec_label(
        business_domain=item.business_domain,
        product_label=product_label,
        display_type=display_type,
        case_size_mm=case_size_mm,
        is_solar=is_solar,
        screen_size_in=None,
        chip_family=None,
        cpu_cores=None,
        gpu_cores=None,
        memory_gb=None,
        storage_gb=None,
    )
    spu_title = spec_label or product_label or item.title

    spu_attributes: list[dict[str, Any]] = []
    _append_text_value(spu_attributes, "product_line", product_line)
    _append_text_value(spu_attributes, "model_name", model_name)
    _append_text_value(spu_attributes, "generation", generation)
    _append_text_value(spu_attributes, "display_type", display_type)
    _append_number_value(spu_attributes, "case_size_mm", case_size_mm, unit="mm")
    _append_bool_value(spu_attributes, "is_solar", is_solar)
    if edition_tags:
        spu_attributes.append({"attributeCode": "edition_tags", "jsonValue": edition_tags})

    return _build_single_sku_payload(
        item=item,
        blueprint=blueprint,
        category_id=category_id,
        template_id=template_id,
        spu_title=spu_title,
        spu_attributes=spu_attributes,
        sku_attributes=[],
        sale_attributes=[],
    )


def _build_single_sku_payload(
    *,
    item: Item,
    blueprint: CatalogBackfillBlueprint,
    category_id: str,
    template_id: str,
    spu_title: str,
    spu_attributes: list[dict[str, Any]],
    sku_attributes: list[dict[str, Any]],
    sale_attributes: list[dict[str, Any]],
) -> dict[str, Any]:
    merchant_id = None
    if item.seller is not None and item.seller.seller_id:
        merchant_id = str(item.seller.seller_id)

    brand_id = _first_text(item.normalized_brand, item.spec_enrichment.brand if item.spec_enrichment else None)
    status = ProductStatus.ACTIVE.value if item.is_active else ProductStatus.INACTIVE.value
    price = _decimal_to_number(item.current_price) or 0

    return {
        "requestId": f"legacy-backfill-{item.business_domain}-{item.item_id}",
        "spu": {
            "id": _legacy_spu_id(item.business_domain, item.item_id),
            "categoryId": category_id,
            "templateId": template_id,
            "merchantId": merchant_id,
            "brandId": brand_id,
            "title": spu_title,
            "status": status,
        },
        "templateItems": [dict(item) for item in blueprint.template_items],
        "attributes": [dict(item) for item in blueprint.attributes],
        "spuAttributes": spu_attributes,
        "skus": [
            {
                "skuCode": _legacy_sku_code(item.business_domain, item.item_id),
                "price": price,
                "stock": 1,
                "barcode": None,
                "status": status,
                "saleAttributes": [dict(value) for value in sale_attributes],
                "attributes": sku_attributes,
            }
        ],
    }


def _build_legacy_summary(item: Item, spec: ItemSpecEnrichment | None) -> dict[str, Any]:
    return {
        "itemId": item.item_id,
        "businessDomain": item.business_domain,
        "title": item.title,
        "normalizedBrand": item.normalized_brand,
        "normalizedModelFamily": item.normalized_model_family,
        "normalizedModel": item.normalized_model,
        "normalizedChip": item.normalized_chip,
        "normalizedMemoryGb": item.normalized_memory_gb,
        "normalizedStorageGb": item.normalized_storage_gb,
        "currentPrice": _decimal_to_number(item.current_price),
        "isActive": item.is_active,
        "specEnrichment": None
        if spec is None
        else {
            "status": spec.status,
            "confidence": _decimal_to_number(spec.confidence),
            "brand": spec.brand,
            "productLine": spec.product_line,
            "modelName": spec.model_name,
            "generation": spec.generation,
            "displayType": spec.display_type,
            "caseSizeMm": spec.case_size_mm,
            "isSolar": spec.is_solar,
            "screenSizeIn": _decimal_to_number(spec.screen_size_in),
            "chipFamily": spec.chip_family,
            "cpuCores": spec.cpu_cores,
            "gpuCores": spec.gpu_cores,
            "memoryGb": spec.memory_gb,
            "storageGb": spec.storage_gb,
            "editionTags": list(spec.edition_tags or []),
        },
    }


def _append_text_value(values: list[dict[str, Any]], attribute_code: str, value: str | None) -> None:
    if value is None:
        return
    values.append({"attributeCode": attribute_code, "textValue": value})


def _append_number_value(
    values: list[dict[str, Any]],
    attribute_code: str,
    value: Decimal | int | float | None,
    *,
    unit: str | None = None,
) -> None:
    number = _decimal_to_number(value)
    if number is None:
        return
    values.append(
        {
            "attributeCode": attribute_code,
            "numberValue": number,
            "normalizedNumberValue": number,
            "unit": unit,
        }
    )


def _append_bool_value(values: list[dict[str, Any]], attribute_code: str, value: bool | None) -> None:
    if value is None:
        return
    values.append({"attributeCode": attribute_code, "boolValue": value})


def _legacy_sku_code(business_domain: str, item_id: str) -> str:
    digest = sha256(f"{business_domain}:{item_id}".encode("utf-8")).hexdigest()[:12].upper()
    domain_code = business_domain.replace("_", "").upper()[:8]
    return f"LGC-{domain_code}-{digest}"


def _legacy_spu_id(business_domain: str, item_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"goofish:catalog-spu:{business_domain}:{item_id}"))


def _drain_catalog_outbox(*, limit: int) -> dict[str, Any]:
    processed_count = 0
    failed_count = 0
    passes = 0
    while True:
        result = process_catalog_outbox_events(limit=limit, dry_run=False)
        passes += 1
        processed_count += int(result["processedCount"])
        failed_count += int(result["failedCount"])
        if result["eventCount"] == 0 or result["processedCount"] == 0:
            break
    total = processed_count + failed_count
    return {
        "passes": passes,
        "processedCount": processed_count,
        "failedCount": failed_count,
        "successRate": round(processed_count / total, 4) if total > 0 else None,
    }


def _require_blueprint(business_domain: str) -> CatalogBackfillBlueprint:
    normalized_domain = business_domain.strip()
    canonical_domain = resolve_category_code(normalized_domain)
    blueprint = BACKFILL_BLUEPRINTS.get(normalized_domain)
    if blueprint is None and canonical_domain:
        for candidate in BACKFILL_BLUEPRINTS.values():
            if candidate.category_code == canonical_domain:
                blueprint = candidate
                break
    if blueprint is None:
        raise CatalogBackfillPreviewError(
            f"Unsupported business_domain for catalog backfill: {business_domain}"
        )
    return blueprint


def _resolve_apple_memory_storage(
    *,
    item: Item,
    spec: ItemSpecEnrichment | None,
) -> dict[str, Any]:
    spec_memory_gb = _first_int(spec.memory_gb if spec else None)
    normalized_memory_gb = _first_int(item.normalized_memory_gb)
    spec_storage_gb = _first_int(spec.storage_gb if spec else None)
    normalized_storage_gb = _first_int(normalize_storage_gb(item.normalized_storage_gb))
    rule_memory_gb = None
    rule_storage_gb = None

    if spec_memory_gb is None or spec_storage_gb is None:
        rule_spec = extract_rule_specs(item)
        if str(getattr(rule_spec, "status", "") or "").lower() != "unresolved":
            rule_memory_gb = _first_int(getattr(rule_spec, "memory_gb", None))
            rule_storage_gb = _first_int(getattr(rule_spec, "storage_gb", None))

    memory_source = "spec"
    memory_gb = spec_memory_gb
    if memory_gb is None:
        if normalized_memory_gb is not None:
            memory_source = "normalized"
            memory_gb = normalized_memory_gb
        else:
            memory_source = "rule"
            memory_gb = rule_memory_gb

    storage_source = "spec"
    storage_gb = spec_storage_gb
    if storage_gb is None:
        if normalized_storage_gb is not None:
            storage_source = "normalized"
            storage_gb = normalized_storage_gb
        else:
            storage_source = "rule"
            storage_gb = rule_storage_gb

    return {
        "memoryGb": memory_gb,
        "storageGb": storage_gb,
        "usedRuleFallback": memory_source == "rule" or storage_source == "rule",
    }


def _infer_garmin_display_case_defaults(*, item: Item) -> tuple[str | None, int | None]:
    normalized_text = " ".join(
        part
        for part in [
            str(item.title or "").strip(),
            str(item.normalized_model_family or "").strip(),
            str(item.normalized_model or "").strip(),
        ]
        if part
    ).lower()
    compact_text = re.sub(r"\s+", "", normalized_text)

    if "forerunner" in normalized_text:
        case_size_mm = 46
        if any(token in compact_text for token in ("265s", "255s", "165s")):
            case_size_mm = 42
        elif "965" in compact_text:
            case_size_mm = 47
        elif "165" in compact_text:
            case_size_mm = 43

        if any(token in compact_text for token in _GARMIN_FORERUNNER_MIP_MODEL_TOKENS):
            display_type = "MIP"
        elif any(token in compact_text for token in _GARMIN_FORERUNNER_AMOLED_MODEL_TOKENS):
            display_type = "AMOLED"
        else:
            display_type = "AMOLED"
        return display_type, case_size_mm

    if "instinct" in normalized_text:
        case_size_mm = 45
        if any(token in compact_text for token in ("2s", "instincts")):
            case_size_mm = 40
        elif any(token in compact_text for token in ("2x", "instinctx")):
            case_size_mm = 50
        return "MIP", case_size_mm

    if "tactix" in normalized_text:
        return "MIP", 51

    return None, None


def _first_text(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned:
            return cleaned
    return None


def _first_int(*values: int | None) -> int | None:
    for value in values:
        if value is not None:
            return int(value)
    return None


def _decimal_to_number(value: Decimal | float | int | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value
