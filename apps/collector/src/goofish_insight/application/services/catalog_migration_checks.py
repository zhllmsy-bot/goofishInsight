from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ...logging import get_logger
from ...domain.catalog.blueprints import BACKFILL_BLUEPRINTS
from ...category_compat import compatible_scope_keys
from ...models import Item, OutboxEvent, OutboxStatus, ProductSku, ProductSpu
from ...normalizers import normalize_market_price
from ...pricing import load_pricing_records
from .catalog_backfill import (
    _legacy_sku_code,
    _legacy_spu_id,
    build_catalog_backfill_reconciliation_report_with_session,
    persist_catalog_backfill_item,
    preview_catalog_backfill_item,
)
from .catalog_outbox import (
    CATALOG_OUTBOX_AGGREGATE_TYPE,
    CATALOG_OUTBOX_EVENT_TYPE,
    process_catalog_outbox_events,
)
from .catalog_queries import (
    build_catalog_category_templates,
    build_catalog_pricing_contract_row,
    build_catalog_sku_page,
    build_catalog_spu_detail,
    build_catalog_spu_page,
)

DUAL_READ_DIFF_REPORT_VERSION = "catalog-dual-read-diff-v1"
CATALOG_ROLLBACK_SCRIPT_RELATIVE_PATH = "scripts/db/catalog_dual_read_rollback.sh"
logger = get_logger(__name__)


def build_catalog_migration_report(
    session: Session,
    *,
    category_id: str | None = None,
    spu_id: str | None = None,
    expected_template_id: str | None = None,
    page_size: int = 20,
) -> dict[str, Any]:
    alembic_revision = _load_alembic_revision(session)
    category_templates = (
        build_catalog_category_templates(session, category_id) if category_id else None
    )
    spu_page = build_catalog_spu_page(
        session,
        page=1,
        page_size=page_size,
        category_id=category_id,
    )
    sku_page = build_catalog_sku_page(
        session,
        page=1,
        page_size=page_size,
        spu_id=spu_id,
    ) if spu_id else None
    spu_detail = build_catalog_spu_detail(session, spu_id) if spu_id else None
    latest_outbox = _load_latest_catalog_outbox(session, aggregate_id=spu_id)
    pending_outbox_count = _count_catalog_outbox(
        session,
        aggregate_id=spu_id,
        statuses=[OutboxStatus.PENDING, OutboxStatus.FAILED, OutboxStatus.DEAD],
    )

    checks: list[dict[str, Any]] = [
        {
            "name": "alembic_revision_present",
            "ok": bool(alembic_revision),
            "detail": alembic_revision,
        }
    ]
    if category_id:
        checks.append(
            {
                "name": "category_templates_available",
                "ok": category_templates is not None and int(category_templates["templateCount"]) > 0,
                "detail": category_templates["latestTemplateId"] if category_templates else None,
            }
        )
    if spu_id:
        checks.append(
            {
                "name": "spu_exists",
                "ok": spu_detail is not None,
                "detail": spu_id,
            }
        )
        if expected_template_id:
            actual_template_id = spu_detail["spu"]["templateId"] if spu_detail else None
            checks.append(
                {
                    "name": "spu_template_matches_expected",
                    "ok": actual_template_id == expected_template_id,
                    "detail": {
                        "actualTemplateId": actual_template_id,
                        "expectedTemplateId": expected_template_id,
                    },
                }
            )
        checks.append(
            {
                "name": "catalog_outbox_cleared",
                "ok": pending_outbox_count == 0,
                "detail": {
                    "pendingCount": pending_outbox_count,
                    "latestOutboxStatus": latest_outbox["status"] if latest_outbox else None,
                },
            }
        )

    return {
        "alembicRevision": alembic_revision,
        "categoryTemplates": category_templates,
        "spuPage": spu_page,
        "skuPage": sku_page,
        "spuDetail": _summarize_spu_detail(spu_detail),
        "latestCatalogOutbox": latest_outbox,
        "checks": checks,
    }


def build_catalog_scoped_migration_report(
    session: Session,
    *,
    category_id: str | None = None,
    spu_id: str | None = None,
    expected_template_id: str | None = None,
    page_size: int = 20,
    business_domains: list[str] | None = None,
    expected_coverage_ratio: float = 1.0,
) -> dict[str, Any]:
    migration_report = build_catalog_migration_report(
        session,
        category_id=category_id,
        spu_id=spu_id,
        expected_template_id=expected_template_id,
        page_size=page_size,
    )
    normalized_domains = business_domains or sorted(BACKFILL_BLUEPRINTS)
    reconciliation_reports: list[dict[str, Any]] = []
    checks = list(migration_report["checks"])

    for business_domain in normalized_domains:
        report = build_catalog_backfill_reconciliation_report_with_session(
            session,
            business_domain=business_domain,
        )
        reconciliation_reports.append(report)
        target = dict(report["target"])
        counts = dict(report["counts"])
        coverage_ratio = report["coverageRatio"]
        checks.extend(
            [
                {
                    "name": f"{business_domain}_target_ready",
                    "ok": bool(target["categoryExists"]) and bool(target["templateExists"]),
                    "detail": target,
                },
                {
                    "name": f"{business_domain}_coverage_complete",
                    "ok": coverage_ratio is not None and float(coverage_ratio) >= float(expected_coverage_ratio),
                    "detail": {
                        "actualCoverageRatio": coverage_ratio,
                        "expectedCoverageRatio": expected_coverage_ratio,
                        "legacyEnrichedItemTotal": counts["legacyEnrichedItemTotal"],
                        "migratedSpuTotal": counts["migratedSpuTotal"],
                    },
                },
                {
                    "name": f"{business_domain}_outbox_cleared",
                    "ok": int(counts["pendingOutboxTotal"]) == 0,
                    "detail": {
                        "pendingOutboxTotal": counts["pendingOutboxTotal"],
                    },
                },
            ]
        )

    return {
        "overallOk": all(bool(check["ok"]) for check in checks),
        "expectedCoverageRatio": expected_coverage_ratio,
        "businessDomains": normalized_domains,
        "catalogMigration": migration_report,
        "backfillReconciliation": reconciliation_reports,
        "checks": checks,
    }


def build_catalog_pricing_dual_read_report(
    session: Session,
    *,
    business_domains: list[str] | None = None,
    freshness_days: int = 30,
    expected_spu_coverage_ratio: float = 0.95,
    expected_price_match_ratio: float = 0.97,
    sample_limit: int = 20,
) -> dict[str, Any]:
    normalized_domains = business_domains or sorted(BACKFILL_BLUEPRINTS)
    domain_reports: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    for business_domain in normalized_domains:
        report = _build_catalog_pricing_dual_read_domain_report(
            session,
            business_domain=business_domain,
            freshness_days=freshness_days,
            sample_limit=sample_limit,
        )
        domain_reports.append(report)

        coverage_ratio = report["spuCoverageRatio"]
        price_ratio = report["priceParityRatio"]
        contract_ratio = report["contractParityRatio"]
        checks.extend(
            [
                {
                    "name": f"{business_domain}_dual_read_spu_coverage",
                    "ok": coverage_ratio is None
                    or float(coverage_ratio) >= float(expected_spu_coverage_ratio),
                    "detail": {
                        "actualCoverageRatio": coverage_ratio,
                        "expectedCoverageRatio": expected_spu_coverage_ratio,
                        "legacyPricingRecordCount": report["legacyPricingRecordCount"],
                        "catalogSpuMatchedCount": report["catalogSpuMatchedCount"],
                    },
                },
                {
                    "name": f"{business_domain}_dual_read_price_parity",
                    "ok": price_ratio is None
                    or float(price_ratio) >= float(expected_price_match_ratio),
                    "detail": {
                        "actualPriceParityRatio": price_ratio,
                        "expectedPriceParityRatio": expected_price_match_ratio,
                        "catalogPriceMatchedCount": report["catalogPriceMatchedCount"],
                        "legacyItemResolvedCount": report["legacyItemResolvedCount"],
                    },
                },
                {
                    "name": f"{business_domain}_dual_read_contract_parity",
                    "ok": contract_ratio is None or float(contract_ratio) >= 1.0,
                    "detail": {
                        "actualContractParityRatio": contract_ratio,
                        "expectedContractParityRatio": 1.0,
                        "contractComparedCount": report["contractComparedCount"],
                        "contractMismatchCount": report["contractMismatchCount"],
                    },
                },
            ]
        )

    rollback_artifact = _resolve_catalog_rollback_artifact()
    checks.append(
        {
            "name": "catalog_dual_read_rollback_script_ready",
            "ok": bool(rollback_artifact["exists"]) and bool(rollback_artifact["executable"]),
            "detail": {
                "path": rollback_artifact["path"],
                "exists": rollback_artifact["exists"],
                "executable": rollback_artifact["executable"],
            },
        }
    )
    diff_report = _build_catalog_pricing_dual_read_diff_report(
        domain_reports=domain_reports,
        sample_limit=sample_limit,
    )

    return {
        "reportFormatVersion": DUAL_READ_DIFF_REPORT_VERSION,
        "overallOk": all(bool(check["ok"]) for check in checks),
        "freshnessDays": freshness_days,
        "expectedSpuCoverageRatio": expected_spu_coverage_ratio,
        "expectedPriceMatchRatio": expected_price_match_ratio,
        "businessDomains": normalized_domains,
        "domainReports": domain_reports,
        "diffReport": diff_report,
        "rollbackArtifact": rollback_artifact,
        "checks": checks,
    }


def run_catalog_pricing_dual_read_backfill(
    session: Session,
    *,
    business_domains: list[str] | None = None,
    operator_id: str = "catalog-pricing-dual-read",
    freshness_days: int = 7,
    limit: int = 100,
    offset: int = 0,
    dry_run: bool = True,
    allow_warnings: bool = True,
    process_outbox: bool = False,
    min_sku_attribute_count: int = 0,
    min_spu_attribute_count: int = 0,
    sample_limit: int = 20,
) -> dict[str, Any]:
    normalized_domains = business_domains or sorted(BACKFILL_BLUEPRINTS)
    normalized_limit = max(int(limit), 1)
    normalized_offset = max(int(offset), 0)
    domain_reports: list[dict[str, Any]] = []
    total_candidate_count = 0
    total_attempted_count = 0
    total_processed_count = 0
    total_skipped_count = 0
    total_failed_count = 0
    normalized_min_sku_attribute_count = max(int(min_sku_attribute_count), 0)
    normalized_min_spu_attribute_count = max(int(min_spu_attribute_count), 0)

    for business_domain in normalized_domains:
        pricing_records, expected_rows, missing_item_samples = _load_pricing_dual_read_expected_rows(
            session,
            business_domain=business_domain,
            freshness_days=freshness_days,
            sample_limit=sample_limit,
        )
        catalog_rows = _load_catalog_rows_by_spu_id(
            session,
            sorted(
                {
                    str(candidate["spuId"])
                    for row in expected_rows
                    for candidate in row["catalogKeyCandidates"]
                }
            ),
        )
        spus_by_id: dict[str, ProductSpu] = catalog_rows["spus"]
        missing_rows = [
            row
            for row in expected_rows
            if not any(
                str(candidate["spuId"]) in spus_by_id
                for candidate in row["catalogKeyCandidates"]
            )
        ]
        selected_rows = missing_rows[normalized_offset : normalized_offset + normalized_limit]
        item_results: list[dict[str, Any]] = []
        warning_counts: dict[str, int] = {}
        processed_count = 0
        skipped_count = 0
        failed_count = 0

        for row in selected_rows:
            item = row["item"]
            try:
                preview = preview_catalog_backfill_item(item_id=item.item_id)
                for warning in list(preview.get("warnings") or []):
                    warning_counts[str(warning)] = warning_counts.get(str(warning), 0) + 1
                spu_attribute_count = len(list(preview.get("payload", {}).get("spuAttributes") or []))
                sku_attribute_count = len(
                    list((preview.get("persistPlan") or {}).get("skuAttributeRows") or [])
                )
                if spu_attribute_count < normalized_min_spu_attribute_count:
                    skipped_count += 1
                    item_results.append(
                        {
                            "itemId": item.item_id,
                            "status": "skipped_low_spu_attribute_count",
                            "warnings": list(preview.get("warnings") or []),
                            "spuAttributeCount": spu_attribute_count,
                            "minSpuAttributeCount": normalized_min_spu_attribute_count,
                            "skuAttributeCount": sku_attribute_count,
                        }
                    )
                    continue
                if sku_attribute_count < normalized_min_sku_attribute_count:
                    skipped_count += 1
                    item_results.append(
                        {
                            "itemId": item.item_id,
                            "status": "skipped_low_sku_attribute_count",
                            "warnings": list(preview.get("warnings") or []),
                            "spuAttributeCount": spu_attribute_count,
                            "skuAttributeCount": sku_attribute_count,
                            "minSkuAttributeCount": normalized_min_sku_attribute_count,
                        }
                    )
                    continue
                detail = persist_catalog_backfill_item(
                    item_id=item.item_id,
                    operator_id=operator_id,
                    dry_run=dry_run,
                    allow_warnings=allow_warnings,
                )
                processed_count += 1
                item_results.append(
                    {
                        "itemId": item.item_id,
                        "status": "would_backfill" if dry_run else "backfilled",
                        "warnings": list(preview.get("warnings") or []),
                        "spuId": detail.get("spuId"),
                        "skuCount": detail.get("skuCount"),
                        "spuAttributeCount": spu_attribute_count,
                        "skuAttributeCount": detail.get("skuAttributeCount"),
                    }
                )
            except Exception as exc:  # pragma: no cover - exercised through service mocks in tests
                failed_count += 1
                logger.exception(
                    "catalog backfill item failed",
                    extra={"business_domain": business_domain, "item_id": getattr(item, "item_id", None)},
                )
                item_results.append(
                    {
                        "itemId": getattr(item, "item_id", None),
                        "status": "failed",
                        "error": str(exc),
                    }
                )

        outbox_result = None
        if process_outbox and not dry_run and processed_count > 0:
            outbox_result = process_catalog_outbox_events(
                limit=max(processed_count * 2, 50),
                dry_run=False,
            )
            outbox_result = _summarize_outbox_result(outbox_result, sample_limit=sample_limit)

        domain_report = {
            "businessDomain": business_domain,
            "dryRun": dry_run,
            "freshnessDays": freshness_days,
            "legacyPricingRecordCount": len(pricing_records),
            "legacyItemResolvedCount": len(expected_rows),
            "missingLegacyItemCount": len(missing_item_samples),
            "candidateMissingSpuCount": len(missing_rows),
            "offset": normalized_offset,
            "attemptedCount": len(selected_rows),
            "processedCount": processed_count,
            "skippedCount": skipped_count,
            "failedCount": failed_count,
            "warningCounts": warning_counts,
            "missingLegacyItemSamples": missing_item_samples,
            "items": item_results[:sample_limit],
            "outbox": outbox_result,
        }
        domain_reports.append(domain_report)
        total_candidate_count += len(missing_rows)
        total_attempted_count += len(selected_rows)
        total_processed_count += processed_count
        total_skipped_count += skipped_count
        total_failed_count += failed_count

    return {
        "dryRun": dry_run,
        "businessDomains": normalized_domains,
        "freshnessDays": freshness_days,
        "limitPerDomain": normalized_limit,
        "offset": normalized_offset,
        "minSpuAttributeCount": normalized_min_spu_attribute_count,
        "minSkuAttributeCount": normalized_min_sku_attribute_count,
        "totalCandidateMissingSpuCount": total_candidate_count,
        "totalAttemptedCount": total_attempted_count,
        "totalProcessedCount": total_processed_count,
        "totalSkippedCount": total_skipped_count,
        "totalFailedCount": total_failed_count,
        "domainReports": domain_reports,
    }


def _load_alembic_revision(session: Session) -> str | None:
    row = session.execute(text("select version_num from alembic_version limit 1")).scalar_one_or_none()
    return str(row) if row else None


def _load_latest_catalog_outbox(session: Session, *, aggregate_id: str | None) -> dict[str, Any] | None:
    stmt = session.query(OutboxEvent).filter(
        OutboxEvent.event_type == CATALOG_OUTBOX_EVENT_TYPE,
        OutboxEvent.aggregate_type == CATALOG_OUTBOX_AGGREGATE_TYPE,
    )
    if aggregate_id:
        stmt = stmt.filter(OutboxEvent.aggregate_id == aggregate_id)
    event = stmt.order_by(OutboxEvent.created_at.desc()).first()
    if event is None:
        return None
    return {
        "id": event.id,
        "aggregateId": event.aggregate_id,
        "status": event.status.value,
        "retryCount": event.retry_count,
        "lastError": event.last_error,
        "createdAt": event.created_at,
        "updatedAt": event.updated_at,
    }


def _count_catalog_outbox(
    session: Session,
    *,
    aggregate_id: str | None,
    statuses: list[OutboxStatus],
) -> int:
    stmt = session.query(OutboxEvent).filter(
        OutboxEvent.event_type == CATALOG_OUTBOX_EVENT_TYPE,
        OutboxEvent.aggregate_type == CATALOG_OUTBOX_AGGREGATE_TYPE,
        OutboxEvent.status.in_(statuses),
    )
    if aggregate_id:
        stmt = stmt.filter(OutboxEvent.aggregate_id == aggregate_id)
    return int(stmt.count())


def _summarize_spu_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    if detail is None:
        return None
    snapshot = dict(detail["spu"].get("attrSnapshotJson") or {})
    return {
        "id": detail["spu"]["id"],
        "categoryId": detail["spu"]["categoryId"],
        "templateId": detail["spu"]["templateId"],
        "title": detail["spu"]["title"],
        "status": detail["spu"]["status"],
        "skuCount": len(list(detail["skus"])),
        "snapshotSkuCount": len(list(snapshot.get("skus") or [])),
    }


def _build_catalog_pricing_dual_read_domain_report(
    session: Session,
    *,
    business_domain: str,
    freshness_days: int,
    sample_limit: int,
) -> dict[str, Any]:
    pricing_records, expected_rows, missing_item_samples = _load_pricing_dual_read_expected_rows(
        session,
        business_domain=business_domain,
        freshness_days=freshness_days,
        sample_limit=sample_limit,
    )

    catalog_rows = _load_catalog_rows_by_spu_id(
        session,
        sorted(
            {
                str(candidate["spuId"])
                for row in expected_rows
                for candidate in row["catalogKeyCandidates"]
            }
        ),
    )
    spus_by_id: dict[str, ProductSpu] = catalog_rows["spus"]
    skus_by_key: dict[tuple[str, str], ProductSku] = catalog_rows["skus"]

    catalog_spu_matched_count = 0
    catalog_sku_matched_count = 0
    catalog_price_matched_count = 0
    matched_domain_variant_counts: dict[str, int] = {}
    missing_catalog_samples: list[dict[str, Any]] = []
    price_mismatch_samples: list[dict[str, Any]] = []
    contract_mismatch_samples: list[dict[str, Any]] = []
    contract_compared_count = 0
    contract_matched_count = 0

    for expected in expected_rows:
        item = expected["item"]
        record = expected["record"]
        candidates = list(expected["catalogKeyCandidates"])
        matched_candidate = next(
            (
                candidate
                for candidate in candidates
                if str(candidate["spuId"]) in spus_by_id
            ),
            None,
        )

        if matched_candidate is None:
            if len(missing_catalog_samples) < sample_limit:
                missing_catalog_samples.append(
                    _catalog_dual_read_sample(
                        item=item,
                        record=record,
                        matched_candidate=None,
                        candidate_keys=candidates,
                        reason="missing_spu",
                    )
                )
            continue
        catalog_spu_matched_count += 1
        matched_domain_variant = str(matched_candidate["businessDomain"])
        matched_domain_variant_counts[matched_domain_variant] = (
            matched_domain_variant_counts.get(matched_domain_variant, 0) + 1
        )

        spu_id = str(matched_candidate["spuId"])
        sku_code = str(matched_candidate["skuCode"])
        spu = spus_by_id.get(spu_id)
        sku = skus_by_key.get((spu_id, sku_code))

        if sku is None:
            if len(missing_catalog_samples) < sample_limit:
                missing_catalog_samples.append(
                    _catalog_dual_read_sample(
                        item=item,
                        record=record,
                        matched_candidate=matched_candidate,
                        candidate_keys=candidates,
                        reason="missing_sku",
                    )
                )
            continue
        catalog_sku_matched_count += 1

        legacy_contract_row = _build_legacy_pricing_contract_row(
            item=item,
            record=record,
            matched_candidate=matched_candidate,
            candidate_keys=candidates,
        )
        catalog_contract_row = build_catalog_pricing_contract_row(
            business_domain=matched_candidate.get("businessDomain"),
            item_id=getattr(item, "item_id", None),
            spu=spu,
            sku=sku,
            fallback_spu_id=spu_id,
            fallback_sku_code=sku_code,
            title=record.get("title"),
            price=sku.price,
        )
        contract_diff_fields = _contract_row_diff_fields(
            legacy_contract_row,
            catalog_contract_row,
        )
        contract_compared_count += 1
        if not contract_diff_fields:
            contract_matched_count += 1
        elif len(contract_mismatch_samples) < sample_limit:
            contract_mismatch_samples.append(
                {
                    "reason": "contract_mismatch",
                    "diffFields": contract_diff_fields,
                    "legacyRow": legacy_contract_row,
                    "catalogRow": catalog_contract_row,
                }
            )

        legacy_price = _float_or_none(record.get("price"))
        catalog_price = _normalized_catalog_price(sku=sku, item=item, record=record)
        if _prices_match(legacy_price, catalog_price):
            catalog_price_matched_count += 1
            continue

        if len(price_mismatch_samples) < sample_limit:
            price_mismatch_samples.append(
                {
                    **_catalog_dual_read_sample(
                        item=item,
                        record=record,
                        matched_candidate=matched_candidate,
                        candidate_keys=candidates,
                        reason="price_mismatch",
                    ),
                    "legacyPrice": legacy_price,
                    "catalogPrice": catalog_price,
                }
            )

    expected_count = len(expected_rows)
    return {
        "businessDomain": business_domain,
        "freshnessDays": freshness_days,
        "legacyPricingRecordCount": len(pricing_records),
        "legacyItemResolvedCount": expected_count,
        "missingLegacyItemCount": len(pricing_records) - expected_count,
        "catalogSpuMatchedCount": catalog_spu_matched_count,
        "catalogSkuMatchedCount": catalog_sku_matched_count,
        "catalogPriceMatchedCount": catalog_price_matched_count,
        "contractComparedCount": contract_compared_count,
        "contractMatchedCount": contract_matched_count,
        "contractMismatchCount": max(contract_compared_count - contract_matched_count, 0),
        "matchedDomainVariantCounts": matched_domain_variant_counts,
        "spuCoverageRatio": _safe_ratio(catalog_spu_matched_count, expected_count),
        "skuCoverageRatio": _safe_ratio(catalog_sku_matched_count, expected_count),
        "priceParityRatio": _safe_ratio(catalog_price_matched_count, expected_count),
        "contractParityRatio": _safe_ratio(contract_matched_count, contract_compared_count),
        "missingLegacyItemSamples": missing_item_samples,
        "missingCatalogSamples": missing_catalog_samples,
        "priceMismatchSamples": price_mismatch_samples,
        "contractMismatchSamples": contract_mismatch_samples,
    }


def _load_pricing_dual_read_expected_rows(
    session: Session,
    *,
    business_domain: str,
    freshness_days: int,
    sample_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    pricing_records = load_pricing_records(
        session=session,
        business_domain=business_domain,
        freshness_days=freshness_days,
    )
    item_ids = [
        record["item_id_ref"]
        for record in pricing_records
        if record.get("item_id_ref") is not None
    ]
    items_by_id = _load_items_by_internal_id(session, item_ids)

    expected_rows: list[dict[str, Any]] = []
    missing_item_samples: list[dict[str, Any]] = []
    for record in pricing_records:
        item_id_ref = str(record.get("item_id_ref") or "").strip()
        item = items_by_id.get(item_id_ref)
        if item is None:
            if len(missing_item_samples) < sample_limit:
                missing_item_samples.append(
                    {
                        "itemIdRef": item_id_ref,
                        "itemId": record.get("item_id"),
                        "title": record.get("title"),
                    }
                )
            continue
        expected_rows.append(
            {
                "record": record,
                "item": item,
                "catalogKeyCandidates": _catalog_key_candidates_for_item(item),
            }
        )
    return pricing_records, expected_rows, missing_item_samples


def _summarize_outbox_result(result: dict[str, Any], *, sample_limit: int) -> dict[str, Any]:
    events = list(result.get("events") or [])
    return {
        **{key: value for key, value in result.items() if key != "events"},
        "eventSampleCount": min(len(events), sample_limit),
        "eventTotalCount": len(events),
        "events": events[:sample_limit],
    }


def _load_items_by_internal_id(session: Session, item_ids: list[Any]) -> dict[str, Item]:
    if not item_ids:
        return {}
    items: dict[str, Item] = {}
    for chunk in _chunked(item_ids, 1000):
        rows = session.execute(select(Item).where(Item.id.in_(chunk))).scalars()
        items.update({str(item.id): item for item in rows})
    return items


def _load_catalog_rows_by_spu_id(
    session: Session,
    spu_ids: list[str],
) -> dict[str, dict[Any, Any]]:
    if not spu_ids:
        return {"spus": {}, "skus": {}}
    spus: dict[str, ProductSpu] = {}
    skus: dict[tuple[str, str], ProductSku] = {}
    for chunk in _chunked(spu_ids, 1000):
        rows = session.query(ProductSpu, ProductSku).outerjoin(
            ProductSku,
            ProductSku.spu_id == ProductSpu.id,
        ).filter(
            ProductSpu.id.in_(chunk),
        ).all()
        for spu, sku in rows:
            spus[str(spu.id)] = spu
            if sku is not None:
                skus[(str(sku.spu_id), str(sku.sku_code))] = sku
    return {"spus": spus, "skus": skus}


def _catalog_key_candidates_for_item(item: Item) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for business_domain in compatible_scope_keys(item.business_domain):
        candidate = {
            "businessDomain": business_domain,
            "spuId": _legacy_spu_id(business_domain, item.item_id),
            "skuCode": _legacy_sku_code(business_domain, item.item_id),
        }
        if candidate not in candidates:
            candidates.append(candidate)
    if not candidates:
        candidates.append(
            {
                "businessDomain": str(item.business_domain or ""),
                "spuId": _legacy_spu_id(item.business_domain, item.item_id),
                "skuCode": _legacy_sku_code(item.business_domain, item.item_id),
            }
        )
    return candidates


def _catalog_dual_read_sample(
    *,
    item: Item,
    record: dict[str, Any],
    matched_candidate: dict[str, str] | None,
    candidate_keys: list[dict[str, str]],
    reason: str,
) -> dict[str, Any]:
    primary_candidate = matched_candidate or (candidate_keys[0] if candidate_keys else {})
    return {
        "reason": reason,
        "itemIdRef": item.id,
        "itemId": item.item_id,
        "businessDomain": item.business_domain,
        "matchedBusinessDomainVariant": matched_candidate.get("businessDomain") if matched_candidate else None,
        "primaryCandidateBusinessDomain": primary_candidate.get("businessDomain"),
        "title": record.get("title") or item.title,
        "spuId": primary_candidate.get("spuId"),
        "skuCode": primary_candidate.get("skuCode"),
        "candidateKeys": candidate_keys[:4],
    }


def _build_legacy_pricing_contract_row(
    *,
    item: Item,
    record: dict[str, Any],
    matched_candidate: dict[str, str] | None,
    candidate_keys: list[dict[str, str]],
) -> dict[str, Any]:
    primary_candidate = matched_candidate or (candidate_keys[0] if candidate_keys else {})
    return {
        "businessDomain": str(primary_candidate.get("businessDomain") or item.business_domain or ""),
        "itemId": str(item.item_id or ""),
        "spuId": str(primary_candidate.get("spuId") or ""),
        "skuCode": str(primary_candidate.get("skuCode") or ""),
        "title": str(record.get("title") or item.title or ""),
        "price": _float_or_none(record.get("price")),
    }


def _contract_row_diff_fields(legacy_row: dict[str, Any], catalog_row: dict[str, Any]) -> list[str]:
    diff_fields: list[str] = []
    for field in ("businessDomain", "itemId", "spuId", "skuCode", "title"):
        if legacy_row.get(field) != catalog_row.get(field):
            diff_fields.append(field)
    return diff_fields


def _normalized_catalog_price(
    *,
    sku: ProductSku,
    item: Item,
    record: dict[str, Any],
) -> float | None:
    if sku.price is None:
        return None
    try:
        price = Decimal(str(sku.price))
    except (ArithmeticError, TypeError, ValueError):
        return None
    normalized = normalize_market_price(
        price,
        business_domain=item.business_domain,
        model_family=record.get("product_line") or getattr(item, "normalized_model_family", None),
    )
    return _float_or_none(normalized)


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _prices_match(left: float | None, right: float | None, *, tolerance: float = 0.01) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance


def _chunked(values: list[Any], size: int) -> list[list[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _build_catalog_pricing_dual_read_diff_report(
    *,
    domain_reports: list[dict[str, Any]],
    sample_limit: int,
) -> dict[str, Any]:
    domain_diff_rows: list[dict[str, Any]] = []
    total_records = 0
    total_missing_catalog = 0
    total_price_mismatch = 0
    total_contract_mismatch = 0
    worst_domain = None
    worst_score = -1

    for report in domain_reports:
        legacy_item_count = int(report.get("legacyItemResolvedCount") or 0)
        missing_catalog_count = len(list(report.get("missingCatalogSamples") or []))
        price_mismatch_count = len(list(report.get("priceMismatchSamples") or []))
        contract_mismatch_count = int(report.get("contractMismatchCount") or 0)
        total_records += legacy_item_count
        total_missing_catalog += missing_catalog_count
        total_price_mismatch += price_mismatch_count
        total_contract_mismatch += contract_mismatch_count
        severity_score = (
            missing_catalog_count * 3
            + price_mismatch_count * 2
            + contract_mismatch_count * 4
        )
        if severity_score > worst_score:
            worst_score = severity_score
            worst_domain = report.get("businessDomain")
        domain_diff_rows.append(
            {
                "businessDomain": report.get("businessDomain"),
                "legacyItemResolvedCount": legacy_item_count,
                "catalogSpuMatchedCount": int(report.get("catalogSpuMatchedCount") or 0),
                "catalogPriceMatchedCount": int(report.get("catalogPriceMatchedCount") or 0),
                "spuCoverageRatio": report.get("spuCoverageRatio"),
                "priceParityRatio": report.get("priceParityRatio"),
                "contractParityRatio": report.get("contractParityRatio"),
                "contractMismatchCount": contract_mismatch_count,
                "sample": {
                    "missingCatalog": list(report.get("missingCatalogSamples") or [])[:sample_limit],
                    "priceMismatch": list(report.get("priceMismatchSamples") or [])[:sample_limit],
                    "contractMismatch": list(report.get("contractMismatchSamples") or [])[:sample_limit],
                },
            }
        )

    return {
        "version": DUAL_READ_DIFF_REPORT_VERSION,
        "summary": {
            "domainCount": len(domain_reports),
            "legacyItemResolvedTotal": total_records,
            "missingCatalogSampleTotal": total_missing_catalog,
            "priceMismatchSampleTotal": total_price_mismatch,
            "contractMismatchTotal": total_contract_mismatch,
            "worstDomain": worst_domain,
        },
        "domains": domain_diff_rows,
    }


def _resolve_catalog_rollback_artifact() -> dict[str, Any]:
    root_dir = Path(__file__).resolve().parents[6]
    script_path = root_dir / CATALOG_ROLLBACK_SCRIPT_RELATIVE_PATH
    return {
        "path": str(script_path),
        "exists": script_path.exists(),
        "executable": bool(script_path.exists() and os.access(script_path, os.X_OK)),
    }
