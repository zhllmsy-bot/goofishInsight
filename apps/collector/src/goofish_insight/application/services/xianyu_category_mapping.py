from __future__ import annotations

from collections import Counter
from decimal import Decimal
import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ...category_compat import compatible_scope_keys, resolve_category_code
from ...db import session_scope
from ...models import (
    Category,
    CategoryAttrTemplate,
    Item,
    ProductAttrAuditLog,
    RawResponse,
    XianyuCategoryMapping,
    XianyuCategoryOnboardingQueue,
    XianyuCategoryMatchScope,
)
from ...normalizers import extract_items_from_response
from .catalog_queries import build_catalog_template_detail
from .catalog_template import persist_catalog_template_payload_with_session


class XianyuCategoryMappingError(RuntimeError):
    pass


DRAFT_ATTRIBUTE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"code": "brand_name", "name": "Brand", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 10},
    {"code": "product_line", "name": "Product Line", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 20},
    {"code": "model_name", "name": "Model Name", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 30},
    {"code": "generation", "name": "Generation", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 40},
    {"code": "chip_family", "name": "Chip Family", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 50},
    {"code": "gpu_vendor", "name": "GPU Vendor", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 55},
    {"code": "gpu_model", "name": "GPU Model", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 56},
    {"code": "cpu_model", "name": "CPU Model", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 60},
    {"code": "display_type", "name": "Display Type", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 70},
    {"code": "screen_size_in", "name": "Screen Size", "dataType": "NUMBER", "valueScope": "SPU", "unit": "inch", "sortNo": 80},
    {"code": "case_size_mm", "name": "Case Size", "dataType": "NUMBER", "valueScope": "SPU", "unit": "mm", "sortNo": 90},
    {"code": "cpu_cores", "name": "CPU Cores", "dataType": "NUMBER", "valueScope": "SPU", "sortNo": 100},
    {"code": "gpu_cores", "name": "GPU Cores", "dataType": "NUMBER", "valueScope": "SPU", "sortNo": 110},
    {"code": "memory_gb", "name": "Memory", "dataType": "NUMBER", "valueScope": "SKU", "unit": "GB", "sortNo": 120},
    {"code": "storage_gb", "name": "Storage", "dataType": "NUMBER", "valueScope": "SKU", "unit": "GB", "sortNo": 130},
    {"code": "vram_gb", "name": "VRAM", "dataType": "NUMBER", "valueScope": "SKU", "unit": "GB", "sortNo": 135},
    {"code": "is_solar", "name": "Is Solar", "dataType": "BOOLEAN", "valueScope": "SPU", "sortNo": 140},
    {"code": "edition_tags", "name": "Edition Tags", "dataType": "JSON", "valueScope": "SPU", "isMulti": True, "sortNo": 150},
    {"code": "mount_system", "name": "Mount System", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 160},
    {"code": "camera_series", "name": "Camera Series", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 165},
    {"code": "sensor_format", "name": "Sensor Format", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 168},
    {
        "code": "focal_length_range",
        "name": "Focal Length Range",
        "dataType": "TEXT",
        "valueScope": "SPU",
        "unit": "mm",
        "sortNo": 170,
    },
    {"code": "max_aperture", "name": "Max Aperture", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 180},
    {"code": "lens_series", "name": "Lens Series", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 190},
    {"code": "phone_series", "name": "Phone Series", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 200},
    {"code": "device_color", "name": "Color", "dataType": "TEXT", "valueScope": "SKU", "sortNo": 210},
    {"code": "instrument_family", "name": "Instrument Family", "dataType": "TEXT", "valueScope": "SPU", "sortNo": 220},
)
DRAFT_ALWAYS_INCLUDED_ATTRIBUTE_CODES = {"brand_name", "model_name"}
DRAFT_PROFILE_ATTRIBUTE_BOOSTS: dict[str, set[str]] = {
    "camera_interchangeable_lens": {
        "mount_system",
        "focal_length_range",
        "max_aperture",
        "lens_series",
    },
    "camera_body": {
        "mount_system",
        "camera_series",
        "sensor_format",
    },
    "computer_device": {
        "chip_family",
        "memory_gb",
        "storage_gb",
        "screen_size_in",
    },
    "graphics_card": {
        "gpu_vendor",
        "gpu_model",
        "vram_gb",
    },
    "smartphone_device": {
        "phone_series",
        "memory_gb",
        "storage_gb",
        "device_color",
    },
    "sports_watch": {
        "case_size_mm",
        "display_type",
        "is_solar",
    },
    "musical_instrument": {
        "instrument_family",
    },
}
TITLE_BRAND_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Apple", ("苹果", "apple", "macbook", "mac mini", "mac studio", "imac")),
    ("Garmin", ("佳明", "garmin")),
    ("Nikon", ("尼康", "nikon", "nikkor")),
    ("Canon", ("佳能", "canon")),
    ("Sony", ("索尼", "sony")),
    ("Fujifilm", ("富士", "fujifilm", "fuji")),
    ("Leica", ("徕卡", "leica")),
    ("Sigma", ("适马", "sigma")),
    ("Tamron", ("腾龙", "tamron")),
    ("DJI", ("大疆", "dji")),
    ("GoPro", ("gopro",)),
    ("Huawei", ("华为", "huawei")),
    ("Xiaomi", ("小米", "xiaomi", "redmi")),
    ("OPPO", ("oppo", "一加", "oneplus", "realme")),
    ("vivo", ("vivo", "iqoo")),
    ("Samsung", ("三星", "samsung", "galaxy")),
    ("Honor", ("荣耀", "honor")),
    ("NVIDIA", ("nvidia", "rtx", "gtx", "quadro")),
    ("AMD", ("amd", "radeon", "rx ")),
    ("Intel", ("intel arc", "arc a", "intel")),
    ("Yamaha", ("雅马哈", "yamaha")),
    ("Fender", ("芬达", "fender")),
    ("Gibson", ("吉普森", "gibson")),
    ("Taylor", ("taylor",)),
)
LENS_FOCAL_RANGE_PATTERN = re.compile(r"(?P<range>\d{1,3}\s*-\s*\d{1,3})(?:\s*mm)?", re.IGNORECASE)
LENS_APERTURE_PATTERN = re.compile(r"f\s*/?\s*(?P<aperture>\d(?:\.\d)?)", re.IGNORECASE)
LENS_COMPACT_APERTURE_PATTERN = re.compile(
    r"(?P<range>\d{1,3}\s*-\s*\d{1,3})\s*/\s*(?P<aperture>\d(?:\.\d)?)",
    re.IGNORECASE,
)
GPU_MODEL_PATTERN = re.compile(
    r"(?P<model>(?:rtx|gtx|rx|arc)\s*[a-z]?\s*\d{3,4}(?:\s*(?:ti|super|xt|xtx)){0,2})",
    re.IGNORECASE,
)
VRAM_PATTERN = re.compile(r"(?P<value>\d{1,2})\s*g(?:b)?\s*(?:显存)?", re.IGNORECASE)
ONBOARDING_QUEUE_STATUSES = {"PENDING", "IN_PROGRESS", "RESOLVED", "IGNORED"}


def _scope_keys_for_filter(business_domain: str | None) -> tuple[str, ...]:
    normalized = str(business_domain or "").strip()
    if not normalized:
        return ()
    return compatible_scope_keys(normalized)


def _apply_business_domain_filter(stmt, *, business_domain: str | None):
    scope_keys = _scope_keys_for_filter(business_domain)
    if not scope_keys:
        return stmt
    return stmt.where(Item.business_domain.in_(scope_keys))


def build_xianyu_category_match_key(
    *,
    match_scope: XianyuCategoryMatchScope | str,
    xianyu_cat_id: str | None = None,
    xianyu_tb_cat_id: str | None = None,
    xianyu_c_cat_id: str | None = None,
) -> str:
    scope = _coerce_match_scope(match_scope)
    cat_id = _normalize_optional_string(xianyu_cat_id)
    tb_cat_id = _normalize_optional_string(xianyu_tb_cat_id)
    c_cat_id = _normalize_optional_string(xianyu_c_cat_id)

    if scope == XianyuCategoryMatchScope.C_CAT:
        if not c_cat_id:
            raise XianyuCategoryMappingError("xianyu_c_cat_id is required for C_CAT mapping.")
        return f"C_CAT:{c_cat_id}"
    if scope == XianyuCategoryMatchScope.CAT_TB:
        if not cat_id or not tb_cat_id:
            raise XianyuCategoryMappingError("xianyu_cat_id and xianyu_tb_cat_id are required for CAT_TB mapping.")
        return f"CAT_TB:{cat_id}:{tb_cat_id}"
    if scope == XianyuCategoryMatchScope.TB_CAT:
        if not tb_cat_id:
            raise XianyuCategoryMappingError("xianyu_tb_cat_id is required for TB_CAT mapping.")
        return f"TB_CAT:{tb_cat_id}"
    if scope == XianyuCategoryMatchScope.CAT:
        if not cat_id:
            raise XianyuCategoryMappingError("xianyu_cat_id is required for CAT mapping.")
        return f"CAT:{cat_id}"
    raise XianyuCategoryMappingError(f"Unsupported match_scope: {match_scope}")


def build_xianyu_category_match_candidates(
    *,
    xianyu_cat_id: str | None = None,
    xianyu_tb_cat_id: str | None = None,
    xianyu_c_cat_id: str | None = None,
) -> list[dict[str, Any]]:
    cat_id = _normalize_optional_string(xianyu_cat_id)
    tb_cat_id = _normalize_optional_string(xianyu_tb_cat_id)
    c_cat_id = _normalize_optional_string(xianyu_c_cat_id)

    seen_keys: set[str] = set()
    candidates: list[dict[str, Any]] = []
    definitions: list[tuple[XianyuCategoryMatchScope, dict[str, str | None]]] = []
    if c_cat_id:
        definitions.append((XianyuCategoryMatchScope.C_CAT, {"xianyu_c_cat_id": c_cat_id}))
    if cat_id and tb_cat_id:
        definitions.append(
            (
                XianyuCategoryMatchScope.CAT_TB,
                {"xianyu_cat_id": cat_id, "xianyu_tb_cat_id": tb_cat_id},
            )
        )
    if tb_cat_id:
        definitions.append((XianyuCategoryMatchScope.TB_CAT, {"xianyu_tb_cat_id": tb_cat_id}))
    if cat_id:
        definitions.append((XianyuCategoryMatchScope.CAT, {"xianyu_cat_id": cat_id}))

    for scope, payload in definitions:
        match_key = build_xianyu_category_match_key(match_scope=scope, **payload)
        if match_key in seen_keys:
            continue
        seen_keys.add(match_key)
        candidates.append(
            {
                "matchScope": scope.value,
                "matchKey": match_key,
                "xianyuCatId": payload.get("xianyu_cat_id"),
                "xianyuTbCatId": payload.get("xianyu_tb_cat_id"),
                "xianyuCCatId": payload.get("xianyu_c_cat_id"),
            }
        )
    return candidates


def resolve_xianyu_category_mapping(
    *,
    xianyu_cat_id: str | None = None,
    xianyu_tb_cat_id: str | None = None,
    xianyu_c_cat_id: str | None = None,
    active_only: bool = True,
) -> XianyuCategoryMapping | None:
    with session_scope() as session:
        return resolve_xianyu_category_mapping_with_session(
            session,
            xianyu_cat_id=xianyu_cat_id,
            xianyu_tb_cat_id=xianyu_tb_cat_id,
            xianyu_c_cat_id=xianyu_c_cat_id,
            active_only=active_only,
        )


def resolve_xianyu_category_mapping_with_session(
    session: Session,
    *,
    xianyu_cat_id: str | None = None,
    xianyu_tb_cat_id: str | None = None,
    xianyu_c_cat_id: str | None = None,
    active_only: bool = True,
) -> XianyuCategoryMapping | None:
    candidates = build_xianyu_category_match_candidates(
        xianyu_cat_id=xianyu_cat_id,
        xianyu_tb_cat_id=xianyu_tb_cat_id,
        xianyu_c_cat_id=xianyu_c_cat_id,
    )
    if not candidates:
        return None

    rows = (
        session.execute(
            select(XianyuCategoryMapping).where(
                XianyuCategoryMapping.match_key.in_([candidate["matchKey"] for candidate in candidates])
            )
        )
        .scalars()
        .all()
    )
    mapping_by_key = {
        row.match_key: row
        for row in rows
        if not active_only or str(row.status).upper() == "ACTIVE"
    }
    for candidate in candidates:
        row = mapping_by_key.get(candidate["matchKey"])
        if row is not None:
            return row
    return None


def load_catalog_template_detail_for_item(item: Item) -> dict[str, Any] | None:
    if not any((item.xianyu_cat_id, item.xianyu_tb_cat_id, item.xianyu_c_cat_id)):
        return None

    with session_scope() as session:
        mapping = resolve_xianyu_category_mapping_with_session(
            session,
            xianyu_cat_id=item.xianyu_cat_id,
            xianyu_tb_cat_id=item.xianyu_tb_cat_id,
            xianyu_c_cat_id=item.xianyu_c_cat_id,
        )
        if mapping is None:
            return None
        resolved_template_id = _normalize_optional_string(mapping.template_override_id) or _normalize_optional_string(mapping.template_id)
        if not resolved_template_id:
            return None
        return build_catalog_template_detail(session, resolved_template_id)


def backfill_xianyu_raw_category_signals(
    *,
    source_keyword: str | None = None,
    task_id: int | None = None,
    business_domain: str | None = None,
    limit: int = 500,
    dry_run: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        return backfill_xianyu_raw_category_signals_with_session(
            session,
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            limit=limit,
            dry_run=dry_run,
            overwrite=overwrite,
        )


def backfill_xianyu_raw_category_signals_with_session(
    session: Session,
    *,
    source_keyword: str | None = None,
    task_id: int | None = None,
    business_domain: str | None = None,
    limit: int = 500,
    dry_run: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    resolved_limit = min(max(int(limit), 1), 5000)
    stmt = (
        select(Item, RawResponse.response_body)
        .outerjoin(RawResponse, RawResponse.id == Item.current_raw_response_id)
        .where(
            Item.source_platform == "xianyu",
            Item.current_raw_response_id.is_not(None),
        )
    )
    if source_keyword:
        stmt = stmt.where(Item.source_keyword == source_keyword)
    if task_id is not None:
        stmt = stmt.where(Item.task_id == task_id)
    stmt = _apply_business_domain_filter(stmt, business_domain=business_domain)
    if not overwrite:
        stmt = stmt.where(
            or_(
                Item.xianyu_cat_id.is_(None),
                Item.xianyu_tb_cat_id.is_(None),
                Item.xianyu_c_cat_id.is_(None),
            )
        )

    rows = list(
        session.execute(
            stmt.order_by(Item.last_seen_at.desc(), Item.id.desc()).limit(resolved_limit)
        ).all()
    )

    response_item_cache: dict[Any, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    reason_counts = {
        "updated": 0,
        "already_complete": 0,
        "missing_raw_response": 0,
        "item_not_found_in_raw_response": 0,
        "missing_category_signal": 0,
    }
    matched_count = 0
    updated_count = 0

    for item, response_body in rows:
        if not isinstance(response_body, dict):
            reason_counts["missing_raw_response"] += 1
            items.append(_build_raw_signal_backfill_item_result(item=item, status="missing_raw_response"))
            continue

        cache_key = item.current_raw_response_id
        extracted_by_item_id = response_item_cache.get(cache_key)
        if extracted_by_item_id is None:
            extracted_by_item_id = {
                extracted.item_id: extracted
                for extracted in extract_items_from_response(response_body)
            }
            response_item_cache[cache_key] = extracted_by_item_id

        extracted = extracted_by_item_id.get(item.item_id)
        if extracted is None:
            reason_counts["item_not_found_in_raw_response"] += 1
            items.append(
                _build_raw_signal_backfill_item_result(
                    item=item,
                    status="item_not_found_in_raw_response",
                )
            )
            continue

        proposed = {
            "xianyu_c_cat_id": _normalize_optional_string(extracted.c_cat_id),
            "xianyu_cat_id": _normalize_optional_string(extracted.cat_id),
            "xianyu_tb_cat_id": _normalize_optional_string(extracted.tb_cat_id),
        }
        if not any(proposed.values()):
            reason_counts["missing_category_signal"] += 1
            items.append(
                _build_raw_signal_backfill_item_result(
                    item=item,
                    status="missing_category_signal",
                )
            )
            continue

        matched_count += 1
        updates: dict[str, str] = {}
        for field_name, proposed_value in proposed.items():
            if not proposed_value:
                continue
            current_value = _normalize_optional_string(getattr(item, field_name))
            if overwrite:
                if current_value != proposed_value:
                    updates[field_name] = proposed_value
                continue
            if not current_value:
                updates[field_name] = proposed_value

        if not updates:
            reason_counts["already_complete"] += 1
            items.append(
                _build_raw_signal_backfill_item_result(
                    item=item,
                    status="already_complete",
                    proposed=proposed,
                )
            )
            continue

        updated_count += 1
        reason_counts["updated"] += 1
        if not dry_run:
            for field_name, proposed_value in updates.items():
                setattr(item, field_name, proposed_value)
        items.append(
            _build_raw_signal_backfill_item_result(
                item=item,
                status="updated",
                updates=updates,
                proposed=proposed,
            )
        )

    return {
        "dryRun": dry_run,
        "overwrite": overwrite,
        "limit": resolved_limit,
        "candidateCount": len(rows),
        "matchedCount": matched_count,
        "updatedCount": updated_count,
        "reasonCounts": reason_counts,
        "items": items,
    }


def build_xianyu_raw_category_coverage_report(
    *,
    source_keyword: str | None = None,
    task_id: int | None = None,
    business_domain: str | None = None,
    unmapped_limit: int = 20,
    item_scan_limit: int = 2000,
) -> dict[str, Any]:
    with session_scope() as session:
        return build_xianyu_raw_category_coverage_report_with_session(
            session,
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            unmapped_limit=unmapped_limit,
            item_scan_limit=item_scan_limit,
        )


def build_xianyu_raw_category_coverage_report_with_session(
    session: Session,
    *,
    source_keyword: str | None = None,
    task_id: int | None = None,
    business_domain: str | None = None,
    unmapped_limit: int = 20,
    item_scan_limit: int = 2000,
) -> dict[str, Any]:
    base_stmt = select(Item).where(Item.source_platform == "xianyu")
    if source_keyword:
        base_stmt = base_stmt.where(Item.source_keyword == source_keyword)
    if task_id is not None:
        base_stmt = base_stmt.where(Item.task_id == task_id)
    base_stmt = _apply_business_domain_filter(base_stmt, business_domain=business_domain)

    total_items = int(session.execute(_count_stmt(base_stmt)).scalar_one() or 0)
    with_raw_response = int(
        session.execute(_count_stmt(base_stmt.where(Item.current_raw_response_id.is_not(None)))).scalar_one() or 0
    )
    with_any_signal = int(
        session.execute(
            _count_stmt(
                base_stmt.where(
                    or_(
                        Item.xianyu_cat_id.is_not(None),
                        Item.xianyu_tb_cat_id.is_not(None),
                        Item.xianyu_c_cat_id.is_not(None),
                    )
                )
            )
        ).scalar_one()
        or 0
    )
    fully_populated = int(
        session.execute(
            _count_stmt(
                base_stmt.where(
                    Item.xianyu_cat_id.is_not(None),
                    Item.xianyu_tb_cat_id.is_not(None),
                    Item.xianyu_c_cat_id.is_not(None),
                )
            )
        ).scalar_one()
        or 0
    )
    backfill_candidates = int(
        session.execute(
            _count_stmt(
                base_stmt.where(
                    Item.current_raw_response_id.is_not(None),
                    or_(
                        Item.xianyu_cat_id.is_(None),
                        Item.xianyu_tb_cat_id.is_(None),
                        Item.xianyu_c_cat_id.is_(None),
                    ),
                )
            )
        ).scalar_one()
        or 0
    )

    unmapped_summary = build_xianyu_raw_category_summary_with_session(
        session,
        source_keyword=source_keyword,
        task_id=task_id,
        business_domain=business_domain,
        limit=unmapped_limit,
        item_scan_limit=item_scan_limit,
        unmapped_only=True,
    )

    return {
        "filters": {
            "sourceKeyword": source_keyword,
            "taskId": task_id,
            "businessDomain": business_domain,
        },
        "counts": {
            "totalItems": total_items,
            "itemsWithCurrentRawResponse": with_raw_response,
            "itemsWithAnyRawCategorySignal": with_any_signal,
            "itemsWithCompleteRawCategorySignal": fully_populated,
            "itemsMissingAnyRawCategorySignal": max(total_items - with_any_signal, 0),
            "backfillCandidateItems": backfill_candidates,
        },
        "coverage": {
            "rawSignalCoverageRatio": _safe_ratio(with_any_signal, total_items),
            "completeSignalCoverageRatio": _safe_ratio(fully_populated, total_items),
            "rawResponseRetentionRatio": _safe_ratio(with_raw_response, total_items),
        },
        "topUnmappedRawCategories": list(unmapped_summary.get("items") or []),
        "unmappedScan": {
            "limit": unmapped_summary.get("limit"),
            "itemScanLimit": unmapped_summary.get("itemScanLimit"),
            "returnedCount": unmapped_summary.get("returnedCount"),
            "scannedItemCount": unmapped_summary.get("scannedItemCount"),
            "totalGroupedCount": unmapped_summary.get("totalGroupedCount"),
        },
    }


def build_xianyu_raw_category_summary(
    *,
    source_keyword: str | None = None,
    task_id: int | None = None,
    business_domain: str | None = None,
    limit: int = 20,
    item_scan_limit: int = 2000,
    unmapped_only: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        return build_xianyu_raw_category_summary_with_session(
            session,
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            limit=limit,
            item_scan_limit=item_scan_limit,
            unmapped_only=unmapped_only,
        )


def build_xianyu_raw_category_summary_with_session(
    session: Session,
    *,
    source_keyword: str | None = None,
    task_id: int | None = None,
    business_domain: str | None = None,
    limit: int = 20,
    item_scan_limit: int = 2000,
    unmapped_only: bool = False,
) -> dict[str, Any]:
    resolved_limit = min(max(int(limit), 1), 5000)
    resolved_item_scan_limit = min(max(int(item_scan_limit), 1), 5000)
    stmt = select(Item).where(
        Item.source_platform == "xianyu",
        or_(
            Item.xianyu_cat_id.is_not(None),
            Item.xianyu_tb_cat_id.is_not(None),
            Item.xianyu_c_cat_id.is_not(None),
        ),
    )
    if source_keyword:
        stmt = stmt.where(Item.source_keyword == source_keyword)
    if task_id is not None:
        stmt = stmt.where(Item.task_id == task_id)
    stmt = _apply_business_domain_filter(stmt, business_domain=business_domain)

    items = list(
        session.execute(
            stmt.order_by(Item.last_seen_at.desc(), Item.id.desc()).limit(resolved_item_scan_limit)
        ).scalars()
    )

    grouped: dict[tuple[str | None, str | None, str | None], dict[str, Any]] = {}
    all_match_keys: set[str] = set()
    for item in items:
        key = (item.xianyu_c_cat_id, item.xianyu_cat_id, item.xianyu_tb_cat_id)
        entry = grouped.setdefault(
            key,
            {
                "xianyuCCatId": item.xianyu_c_cat_id,
                "xianyuCatId": item.xianyu_cat_id,
                "xianyuTbCatId": item.xianyu_tb_cat_id,
                "itemCount": 0,
                "sampleItemIds": [],
                "sampleTitles": [],
                "sourceKeywords": [],
                "businessDomains": [],
            },
        )
        entry["itemCount"] += 1
        if len(entry["sampleItemIds"]) < 3:
            entry["sampleItemIds"].append(item.item_id)
        if len(entry["sampleTitles"]) < 3:
            entry["sampleTitles"].append(item.title)
        if item.source_keyword and item.source_keyword not in entry["sourceKeywords"]:
            entry["sourceKeywords"].append(item.source_keyword)
        resolved_scope = resolve_category_code(item.business_domain) or _normalize_optional_string(item.business_domain)
        if resolved_scope and resolved_scope not in entry["businessDomains"]:
            entry["businessDomains"].append(resolved_scope)
        candidates = build_xianyu_category_match_candidates(
            xianyu_cat_id=item.xianyu_cat_id,
            xianyu_tb_cat_id=item.xianyu_tb_cat_id,
            xianyu_c_cat_id=item.xianyu_c_cat_id,
        )
        entry["candidateMatchKeys"] = [candidate["matchKey"] for candidate in candidates]
        all_match_keys.update(entry["candidateMatchKeys"])

    mapping_by_key: dict[str, XianyuCategoryMapping] = {}
    if all_match_keys:
        mapping_rows = (
            session.execute(
                select(XianyuCategoryMapping).where(XianyuCategoryMapping.match_key.in_(sorted(all_match_keys)))
            )
            .scalars()
            .all()
        )
        mapping_by_key = {
            row.match_key: row
            for row in mapping_rows
            if str(row.status).upper() == "ACTIVE"
        }

    rows: list[dict[str, Any]] = []
    for entry in grouped.values():
        resolved_mapping = None
        for match_key in entry["candidateMatchKeys"]:
            resolved_mapping = mapping_by_key.get(match_key)
            if resolved_mapping is not None:
                break
        entry["resolvedMapping"] = serialize_xianyu_category_mapping(resolved_mapping)
        entry["needsOnboarding"] = resolved_mapping is None
        if unmapped_only and resolved_mapping is not None:
            continue
        rows.append(entry)

    rows.sort(key=lambda row: (-row["itemCount"], row["xianyuCCatId"] or "", row["xianyuCatId"] or ""))
    returned_rows = rows[:resolved_limit]
    return {
        "sourcePlatform": "xianyu",
        "sourceKeyword": source_keyword,
        "taskId": task_id,
        "businessDomain": business_domain,
        "limit": resolved_limit,
        "itemScanLimit": resolved_item_scan_limit,
        "sampledItemCount": len(items),
        "scannedItemCount": len(items),
        "returnedCount": len(returned_rows),
        "totalGroupedCount": len(rows),
        "categoryCount": len(returned_rows),
        "items": returned_rows,
    }


def build_xianyu_category_onboarding_draft(
    *,
    source_keyword: str | None = None,
    task_id: int | None = None,
    business_domain: str | None = None,
    xianyu_cat_id: str | None = None,
    xianyu_tb_cat_id: str | None = None,
    xianyu_c_cat_id: str | None = None,
    sample_limit: int = 25,
    prefer_unmapped: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        return build_xianyu_category_onboarding_draft_with_session(
            session,
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            xianyu_cat_id=xianyu_cat_id,
            xianyu_tb_cat_id=xianyu_tb_cat_id,
            xianyu_c_cat_id=xianyu_c_cat_id,
            sample_limit=sample_limit,
            prefer_unmapped=prefer_unmapped,
        )


def build_xianyu_category_onboarding_draft_with_session(
    session: Session,
    *,
    source_keyword: str | None = None,
    task_id: int | None = None,
    business_domain: str | None = None,
    xianyu_cat_id: str | None = None,
    xianyu_tb_cat_id: str | None = None,
    xianyu_c_cat_id: str | None = None,
    sample_limit: int = 25,
    prefer_unmapped: bool = True,
) -> dict[str, Any]:
    selection = _resolve_draft_selection(
        session,
        source_keyword=source_keyword,
        task_id=task_id,
        business_domain=business_domain,
        xianyu_cat_id=xianyu_cat_id,
        xianyu_tb_cat_id=xianyu_tb_cat_id,
        xianyu_c_cat_id=xianyu_c_cat_id,
        prefer_unmapped=prefer_unmapped,
    )
    existing_mapping = resolve_xianyu_category_mapping_with_session(
        session,
        xianyu_cat_id=selection["xianyuCatId"],
        xianyu_tb_cat_id=selection["xianyuTbCatId"],
        xianyu_c_cat_id=selection["xianyuCCatId"],
    )
    items = _load_draft_items(
        session,
        source_keyword=source_keyword,
        task_id=task_id,
        business_domain=business_domain,
        xianyu_cat_id=selection["xianyuCatId"],
        xianyu_tb_cat_id=selection["xianyuTbCatId"],
        xianyu_c_cat_id=selection["xianyuCCatId"],
        sample_limit=sample_limit,
    )
    if not items:
        raise XianyuCategoryMappingError("No sample items found for the selected raw category.")

    analysis = _build_draft_analysis(items)
    reuse_suggestion = _build_reuse_suggestion(session, analysis=analysis)
    payload = _build_draft_payload(
        selection=selection,
        analysis=analysis,
        source_keyword=source_keyword,
        reuse_suggestion=reuse_suggestion,
    )
    return {
        "selection": {
            **selection,
            "existingMapping": serialize_xianyu_category_mapping(existing_mapping),
            "allMatchCandidates": build_xianyu_category_match_candidates(
                xianyu_cat_id=selection["xianyuCatId"],
                xianyu_tb_cat_id=selection["xianyuTbCatId"],
                xianyu_c_cat_id=selection["xianyuCCatId"],
            ),
        },
        "analysis": analysis,
        "reuseSuggestion": reuse_suggestion,
        "payload": payload,
    }


def persist_xianyu_category_onboarding(
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = persist_xianyu_category_onboarding_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def persist_xianyu_category_onboarding_with_session(
    session: Session,
    *,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not operator_id.strip():
        raise XianyuCategoryMappingError("operator_id is required.")

    catalog_payload = _extract_catalog_payload(payload)
    mapping_payloads = _extract_mapping_payloads(payload)
    if not mapping_payloads:
        raise XianyuCategoryMappingError("mappings are required.")

    catalog_result = None
    category_id = _normalize_optional_string(payload.get("categoryId"))
    template_id = _normalize_optional_string(payload.get("templateId"))
    if catalog_payload is not None:
        catalog_result = persist_catalog_template_payload_with_session(
            session,
            payload=catalog_payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        category_id = str(catalog_result["categoryId"])
        template_id = str(catalog_result["templateId"])

    if not category_id:
        raise XianyuCategoryMappingError("categoryId is required when catalog payload is absent.")
    if not template_id:
        raise XianyuCategoryMappingError("templateId is required when catalog payload is absent.")
    if session.get(Category, category_id) is None:
        raise XianyuCategoryMappingError(f"Category not found: {category_id}")
    if session.get(CategoryAttrTemplate, template_id) is None:
        raise XianyuCategoryMappingError(f"Template not found: {template_id}")

    allow_remap = bool(payload.get("allowRemap", False))
    created_count = 0
    updated_count = 0
    resolved_queue_count = 0
    persisted_rows: list[dict[str, Any]] = []

    for mapping_payload in mapping_payloads:
        normalized = _normalize_mapping_payload(mapping_payload)
        match_key = build_xianyu_category_match_key(
            match_scope=normalized["match_scope"],
            xianyu_cat_id=normalized["xianyu_cat_id"],
            xianyu_tb_cat_id=normalized["xianyu_tb_cat_id"],
            xianyu_c_cat_id=normalized["xianyu_c_cat_id"],
        )
        existing = session.execute(
            select(XianyuCategoryMapping).where(XianyuCategoryMapping.match_key == match_key)
        ).scalar_one_or_none()
        if (
            existing is not None
            and (existing.category_id != category_id or existing.template_id != template_id)
            and not (allow_remap or normalized["allow_remap"])
        ):
            raise XianyuCategoryMappingError(
                f"Mapping already points to another target: {match_key} -> "
                f"{existing.category_id}/{existing.template_id}"
            )

        before_json = serialize_xianyu_category_mapping(existing)
        if existing is None:
            row = XianyuCategoryMapping(
                match_scope=normalized["match_scope"],
                match_key=match_key,
                xianyu_cat_id=normalized["xianyu_cat_id"],
                xianyu_tb_cat_id=normalized["xianyu_tb_cat_id"],
                xianyu_c_cat_id=normalized["xianyu_c_cat_id"],
                raw_category_name=normalized["raw_category_name"],
                raw_category_path=normalized["raw_category_path"],
                category_id=category_id,
                template_id=template_id,
                policy_mode="FORCE_TEMPLATE",
                template_override_id=None,
                resolution_source=normalized["resolution_source"],
                status=normalized["status"],
                confidence=normalized["confidence"],
                metadata_json=normalized["metadata_json"],
            )
            session.add(row)
            session.flush()
            created_count += 1
            action = "CREATE_XIANYU_CATEGORY_MAPPING_DRY_RUN" if dry_run else "CREATE_XIANYU_CATEGORY_MAPPING"
        else:
            row = existing
            row.match_scope = normalized["match_scope"]
            row.xianyu_cat_id = normalized["xianyu_cat_id"]
            row.xianyu_tb_cat_id = normalized["xianyu_tb_cat_id"]
            row.xianyu_c_cat_id = normalized["xianyu_c_cat_id"]
            row.raw_category_name = normalized["raw_category_name"]
            row.raw_category_path = normalized["raw_category_path"]
            row.category_id = category_id
            row.template_id = template_id
            row.policy_mode = "FORCE_TEMPLATE"
            row.template_override_id = None
            row.resolution_source = normalized["resolution_source"]
            row.status = normalized["status"]
            row.confidence = normalized["confidence"]
            row.metadata_json = normalized["metadata_json"]
            session.flush()
            updated_count += 1
            action = "UPDATE_XIANYU_CATEGORY_MAPPING_DRY_RUN" if dry_run else "UPDATE_XIANYU_CATEGORY_MAPPING"

        after_json = serialize_xianyu_category_mapping(row)
        audit_log = ProductAttrAuditLog(
            operator_id=operator_id,
            resource_type="xianyu_category_mapping",
            resource_id=row.id,
            action=action,
            before_json=before_json,
            after_json=after_json,
        )
        session.add(audit_log)
        session.flush()
        persisted_rows.append({**after_json, "auditLogId": audit_log.id})
        resolved_queue_count += _resolve_onboarding_queue_rows_for_mapping(
            session=session,
            operator_id=operator_id,
            match_key=match_key,
            mapping_snapshot=after_json,
            dry_run=dry_run,
        )

    return {
        "dryRun": dry_run,
        "requestId": payload.get("requestId") or (catalog_payload or {}).get("requestId"),
        "categoryId": category_id,
        "templateId": template_id,
        "catalog": catalog_result,
        "mappingCount": len(persisted_rows),
        "createdCount": created_count,
        "updatedCount": updated_count,
        "resolvedQueueCount": resolved_queue_count,
        "mappings": persisted_rows,
    }


def serialize_xianyu_category_mapping(mapping: XianyuCategoryMapping | None) -> dict[str, Any] | None:
    if mapping is None:
        return None
    confidence = mapping.confidence
    category = getattr(mapping, "category", None)
    template = getattr(mapping, "template", None)
    template_override = getattr(mapping, "template_override", None)
    return {
        "id": mapping.id,
        "matchScope": mapping.match_scope.value if hasattr(mapping.match_scope, "value") else str(mapping.match_scope),
        "matchKey": mapping.match_key,
        "xianyuCatId": mapping.xianyu_cat_id,
        "xianyuTbCatId": mapping.xianyu_tb_cat_id,
        "xianyuCCatId": mapping.xianyu_c_cat_id,
        "rawCategoryName": mapping.raw_category_name,
        "rawCategoryPath": mapping.raw_category_path,
        "categoryId": mapping.category_id,
        "categoryCode": getattr(category, "code", None),
        "categoryName": getattr(category, "name", None),
        "templateId": mapping.template_id,
        "templateVersion": getattr(template, "version", None),
        "policyMode": getattr(mapping, "policy_mode", None) or "FORCE_TEMPLATE",
        "templateOverrideId": getattr(mapping, "template_override_id", None),
        "templateOverrideVersion": getattr(template_override, "version", None),
        "resolutionSource": mapping.resolution_source,
        "status": mapping.status,
        "confidence": float(confidence) if confidence is not None else None,
        "metadata": _json_safe_value(dict(mapping.metadata_json or {})),
    }


def serialize_xianyu_category_onboarding_queue(
    row: XianyuCategoryOnboardingQueue | None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "matchScope": row.match_scope.value if hasattr(row.match_scope, "value") else str(row.match_scope),
        "matchKey": row.match_key,
        "xianyuCatId": row.xianyu_cat_id,
        "xianyuTbCatId": row.xianyu_tb_cat_id,
        "xianyuCCatId": row.xianyu_c_cat_id,
        "status": row.status,
        "ownerOperatorId": row.owner_operator_id,
        "statusNote": row.status_note,
        "itemCountSnapshot": row.item_count_snapshot,
        "sampleItemIds": list(row.sample_item_ids or []),
        "sampleTitles": list(row.sample_titles or []),
        "sourceKeywords": list(row.source_keywords or []),
        "businessDomains": list(row.business_domains or []),
        "resolvedMapping": _json_safe_value(dict(row.resolved_mapping_json or {})) or None,
        "metadata": _json_safe_value(dict(row.metadata_json or {})),
        "createdAt": _json_safe_value(row.created_at),
        "updatedAt": _json_safe_value(row.updated_at),
    }


def sync_xianyu_category_onboarding_queue(
    *,
    operator_id: str,
    source_keyword: str | None = None,
    task_id: int | None = None,
    business_domain: str | None = None,
    item_scan_limit: int = 2000,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = sync_xianyu_category_onboarding_queue_with_session(
            session,
            operator_id=operator_id,
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            item_scan_limit=item_scan_limit,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def sync_xianyu_category_onboarding_queue_with_session(
    session: Session,
    *,
    operator_id: str,
    source_keyword: str | None = None,
    task_id: int | None = None,
    business_domain: str | None = None,
    item_scan_limit: int = 2000,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not operator_id.strip():
        raise XianyuCategoryMappingError("operator_id is required.")

    summary = build_xianyu_raw_category_summary_with_session(
        session,
        source_keyword=source_keyword,
        task_id=task_id,
        business_domain=business_domain,
        limit=5000,
        item_scan_limit=item_scan_limit,
        unmapped_only=False,
    )
    entries = list(summary.get("items") or [])
    primary_match_keys = [
        candidate["matchKey"]
        for candidate in (_build_primary_match_candidate(entry) for entry in entries)
        if candidate is not None
    ]
    existing_rows = (
        session.execute(
            select(XianyuCategoryOnboardingQueue).where(
                XianyuCategoryOnboardingQueue.match_key.in_(sorted(set(primary_match_keys)))
            )
        ).scalars().all()
        if primary_match_keys
        else []
    )
    row_by_key = {row.match_key: row for row in existing_rows}

    created_count = 0
    updated_count = 0
    resolved_count = 0
    reopened_count = 0
    unchanged_count = 0
    persisted_items: list[dict[str, Any]] = []

    for entry in entries:
        primary_candidate = _build_primary_match_candidate(entry)
        if primary_candidate is None:
            continue
        match_key = primary_candidate["matchKey"]
        existing = row_by_key.get(match_key)
        resolved_mapping = entry.get("resolvedMapping")
        needs_onboarding = bool(entry.get("needsOnboarding"))

        if existing is None and resolved_mapping is not None and not needs_onboarding:
            continue

        before_json = serialize_xianyu_category_onboarding_queue(existing)
        if existing is None:
            row = XianyuCategoryOnboardingQueue(
                match_scope=_coerce_match_scope(primary_candidate["matchScope"]),
                match_key=match_key,
                xianyu_cat_id=_normalize_optional_string(entry.get("xianyuCatId")),
                xianyu_tb_cat_id=_normalize_optional_string(entry.get("xianyuTbCatId")),
                xianyu_c_cat_id=_normalize_optional_string(entry.get("xianyuCCatId")),
                status="PENDING",
            )
            _apply_onboarding_queue_snapshot(
                row=row,
                entry=entry,
                resolved_mapping=resolved_mapping,
            )
            session.add(row)
            session.flush()
            row_by_key[match_key] = row
            created_count += 1
            action = (
                "CREATE_XIANYU_CATEGORY_ONBOARDING_QUEUE_DRY_RUN"
                if dry_run
                else "CREATE_XIANYU_CATEGORY_ONBOARDING_QUEUE"
            )
            after_json = serialize_xianyu_category_onboarding_queue(row)
            audit_log = ProductAttrAuditLog(
                operator_id=operator_id,
                resource_type="xianyu_category_onboarding_queue",
                resource_id=row.id,
                action=action,
                before_json=before_json,
                after_json=after_json,
            )
            session.add(audit_log)
            session.flush()
            persisted_items.append(
                {
                    "changeType": "created",
                    "queue": after_json,
                    "auditLogId": audit_log.id,
                }
            )
            continue

        if existing is None:
            continue

        previous_status = str(existing.status or "").upper()
        desired_status = _resolve_onboarding_queue_status(
            current_status=previous_status,
            resolved_mapping=resolved_mapping,
        )
        _apply_onboarding_queue_snapshot(
            row=existing,
            entry=entry,
            resolved_mapping=resolved_mapping,
        )
        existing.status = desired_status
        after_json = serialize_xianyu_category_onboarding_queue(existing)
        if before_json == after_json:
            unchanged_count += 1
            persisted_items.append(
                {
                    "changeType": "unchanged",
                    "queue": after_json,
                }
            )
            continue

        session.flush()
        if previous_status != "RESOLVED" and desired_status == "RESOLVED":
            resolved_count += 1
            change_type = "resolved"
        elif previous_status == "RESOLVED" and desired_status != "RESOLVED":
            reopened_count += 1
            change_type = "reopened"
        else:
            updated_count += 1
            change_type = "updated"
        action = (
            "SYNC_XIANYU_CATEGORY_ONBOARDING_QUEUE_DRY_RUN"
            if dry_run
            else "SYNC_XIANYU_CATEGORY_ONBOARDING_QUEUE"
        )
        audit_log = ProductAttrAuditLog(
            operator_id=operator_id,
            resource_type="xianyu_category_onboarding_queue",
            resource_id=existing.id,
            action=action,
            before_json=before_json,
            after_json=after_json,
        )
        session.add(audit_log)
        session.flush()
        persisted_items.append(
            {
                "changeType": change_type,
                "queue": after_json,
                "auditLogId": audit_log.id,
            }
        )

    return {
        "dryRun": dry_run,
        "operatorId": operator_id,
        "sourceKeyword": source_keyword,
        "taskId": task_id,
        "businessDomain": business_domain,
        "itemScanLimit": item_scan_limit,
        "scannedItemCount": summary.get("scannedItemCount"),
        "candidateCount": len(entries),
        "createdCount": created_count,
        "updatedCount": updated_count,
        "resolvedCount": resolved_count,
        "reopenedCount": reopened_count,
        "unchangedCount": unchanged_count,
        "items": persisted_items,
    }


def list_xianyu_category_onboarding_queue(
    *,
    status: str | None = None,
    include_closed: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    with session_scope() as session:
        return list_xianyu_category_onboarding_queue_with_session(
            session,
            status=status,
            include_closed=include_closed,
            limit=limit,
        )


def list_xianyu_category_onboarding_queue_with_session(
    session: Session,
    *,
    status: str | None = None,
    include_closed: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    resolved_limit = min(max(int(limit), 1), 500)
    stmt = select(XianyuCategoryOnboardingQueue)
    normalized_status = _normalize_queue_status(status) if status else None
    if normalized_status:
        stmt = stmt.where(XianyuCategoryOnboardingQueue.status == normalized_status)
    elif not include_closed:
        stmt = stmt.where(XianyuCategoryOnboardingQueue.status.in_(("PENDING", "IN_PROGRESS")))

    total = int(session.execute(_count_stmt(stmt)).scalar_one() or 0)
    rows = list(
        session.execute(
            stmt.order_by(
                XianyuCategoryOnboardingQueue.item_count_snapshot.desc(),
                XianyuCategoryOnboardingQueue.updated_at.desc(),
            ).limit(resolved_limit)
        ).scalars().all()
    )
    return {
        "status": normalized_status,
        "includeClosed": include_closed,
        "limit": resolved_limit,
        "total": total,
        "items": [serialize_xianyu_category_onboarding_queue(row) for row in rows],
    }


def update_xianyu_category_onboarding_queue_status(
    *,
    operator_id: str,
    status: str,
    queue_id: str | None = None,
    match_key: str | None = None,
    owner_operator_id: str | None = None,
    status_note: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = update_xianyu_category_onboarding_queue_status_with_session(
            session,
            operator_id=operator_id,
            status=status,
            queue_id=queue_id,
            match_key=match_key,
            owner_operator_id=owner_operator_id,
            status_note=status_note,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def update_xianyu_category_onboarding_queue_status_with_session(
    session: Session,
    *,
    operator_id: str,
    status: str,
    queue_id: str | None = None,
    match_key: str | None = None,
    owner_operator_id: str | None = None,
    status_note: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not operator_id.strip():
        raise XianyuCategoryMappingError("operator_id is required.")
    normalized_status = _normalize_queue_status(status)
    normalized_queue_id = _normalize_optional_string(queue_id)
    normalized_match_key = _normalize_optional_string(match_key)
    if not normalized_queue_id and not normalized_match_key:
        raise XianyuCategoryMappingError("queue_id or match_key is required.")

    stmt = select(XianyuCategoryOnboardingQueue)
    if normalized_queue_id:
        stmt = stmt.where(XianyuCategoryOnboardingQueue.id == normalized_queue_id)
    else:
        stmt = stmt.where(XianyuCategoryOnboardingQueue.match_key == normalized_match_key)
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        raise XianyuCategoryMappingError("Onboarding queue row not found.")

    before_json = serialize_xianyu_category_onboarding_queue(row)
    row.status = normalized_status
    if owner_operator_id is not None:
        row.owner_operator_id = _normalize_optional_string(owner_operator_id)
    if status_note is not None:
        row.status_note = _normalize_optional_string(status_note)
    session.flush()
    after_json = serialize_xianyu_category_onboarding_queue(row)
    action = (
        "UPDATE_XIANYU_CATEGORY_ONBOARDING_QUEUE_DRY_RUN"
        if dry_run
        else "UPDATE_XIANYU_CATEGORY_ONBOARDING_QUEUE"
    )
    audit_log = ProductAttrAuditLog(
        operator_id=operator_id,
        resource_type="xianyu_category_onboarding_queue",
        resource_id=row.id,
        action=action,
        before_json=before_json,
        after_json=after_json,
    )
    session.add(audit_log)
    session.flush()
    return {
        "dryRun": dry_run,
        "queue": after_json,
        "auditLogId": audit_log.id,
    }


def _build_primary_match_candidate(entry: dict[str, Any]) -> dict[str, Any] | None:
    candidates = build_xianyu_category_match_candidates(
        xianyu_cat_id=_normalize_optional_string(entry.get("xianyuCatId")),
        xianyu_tb_cat_id=_normalize_optional_string(entry.get("xianyuTbCatId")),
        xianyu_c_cat_id=_normalize_optional_string(entry.get("xianyuCCatId")),
    )
    if not candidates:
        return None
    return dict(candidates[0])


def _apply_onboarding_queue_snapshot(
    *,
    row: XianyuCategoryOnboardingQueue,
    entry: dict[str, Any],
    resolved_mapping: dict[str, Any] | None,
) -> None:
    row.xianyu_cat_id = _normalize_optional_string(entry.get("xianyuCatId"))
    row.xianyu_tb_cat_id = _normalize_optional_string(entry.get("xianyuTbCatId"))
    row.xianyu_c_cat_id = _normalize_optional_string(entry.get("xianyuCCatId"))
    row.item_count_snapshot = int(entry.get("itemCount") or 0)
    row.sample_item_ids = [str(value) for value in list(entry.get("sampleItemIds") or [])]
    row.sample_titles = [str(value) for value in list(entry.get("sampleTitles") or [])]
    row.source_keywords = [str(value) for value in list(entry.get("sourceKeywords") or []) if str(value).strip()]
    row.business_domains = [str(value) for value in list(entry.get("businessDomains") or []) if str(value).strip()]
    row.resolved_mapping_json = dict(resolved_mapping or {}) or None
    row.metadata_json = {
        "candidateMatchKeys": [str(value) for value in list(entry.get("candidateMatchKeys") or [])],
        "needsOnboarding": bool(entry.get("needsOnboarding")),
        "sourcePlatform": "xianyu",
    }


def _resolve_onboarding_queue_status(
    *,
    current_status: str | None,
    resolved_mapping: dict[str, Any] | None,
) -> str:
    normalized_current = _normalize_queue_status(current_status or "PENDING")
    if resolved_mapping is not None:
        return "RESOLVED"
    if normalized_current == "RESOLVED":
        return "PENDING"
    return normalized_current


def _normalize_queue_status(value: str | None) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in ONBOARDING_QUEUE_STATUSES:
        raise XianyuCategoryMappingError(f"Unsupported onboarding queue status: {value}")
    return normalized


def _resolve_onboarding_queue_rows_for_mapping(
    *,
    session: Session,
    operator_id: str,
    match_key: str,
    mapping_snapshot: dict[str, Any],
    dry_run: bool,
) -> int:
    queue_rows = list(session.execute(select(XianyuCategoryOnboardingQueue)).scalars().all())
    resolved_count = 0
    for row in queue_rows:
        candidate_match_keys = list((row.metadata_json or {}).get("candidateMatchKeys") or [])
        if row.match_key != match_key and match_key not in candidate_match_keys:
            continue
        if str(row.status or "").upper() == "RESOLVED" and dict(row.resolved_mapping_json or {}) == dict(mapping_snapshot):
            continue
        before_json = serialize_xianyu_category_onboarding_queue(row)
        row.status = "RESOLVED"
        row.resolved_mapping_json = dict(mapping_snapshot)
        session.flush()
        after_json = serialize_xianyu_category_onboarding_queue(row)
        audit_log = ProductAttrAuditLog(
            operator_id=operator_id,
            resource_type="xianyu_category_onboarding_queue",
            resource_id=row.id,
            action=(
                "RESOLVE_XIANYU_CATEGORY_ONBOARDING_QUEUE_DRY_RUN"
                if dry_run
                else "RESOLVE_XIANYU_CATEGORY_ONBOARDING_QUEUE"
            ),
            before_json=before_json,
            after_json=after_json,
        )
        session.add(audit_log)
        session.flush()
        resolved_count += 1
    return resolved_count


def _resolve_draft_selection(
    session: Session,
    *,
    source_keyword: str | None,
    task_id: int | None,
    business_domain: str | None,
    xianyu_cat_id: str | None,
    xianyu_tb_cat_id: str | None,
    xianyu_c_cat_id: str | None,
    prefer_unmapped: bool,
) -> dict[str, Any]:
    cat_id = _normalize_optional_string(xianyu_cat_id)
    tb_cat_id = _normalize_optional_string(xianyu_tb_cat_id)
    c_cat_id = _normalize_optional_string(xianyu_c_cat_id)
    if any((cat_id, tb_cat_id, c_cat_id)):
        return {
            "xianyuCatId": cat_id,
            "xianyuTbCatId": tb_cat_id,
            "xianyuCCatId": c_cat_id,
            "itemCount": None,
            "sampleItemIds": [],
            "sampleTitles": [],
            "sourceKeywords": [source_keyword] if source_keyword else [],
            "businessDomains": [resolve_category_code(business_domain) or business_domain] if business_domain else [],
        }

    summary = build_xianyu_raw_category_summary_with_session(
        session,
        source_keyword=source_keyword,
        task_id=task_id,
        business_domain=business_domain,
        limit=1,
        item_scan_limit=2000,
        unmapped_only=prefer_unmapped,
    )
    items = list(summary.get("items") or [])
    if not items and prefer_unmapped:
        summary = build_xianyu_raw_category_summary_with_session(
            session,
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            limit=1,
            item_scan_limit=2000,
            unmapped_only=False,
        )
        items = list(summary.get("items") or [])
    if not items:
        raise XianyuCategoryMappingError("No raw category candidates found for onboarding draft.")
    return dict(items[0])


def _load_draft_items(
    session: Session,
    *,
    source_keyword: str | None,
    task_id: int | None,
    business_domain: str | None,
    xianyu_cat_id: str | None,
    xianyu_tb_cat_id: str | None,
    xianyu_c_cat_id: str | None,
    sample_limit: int,
) -> list[Item]:
    resolved_limit = min(max(int(sample_limit), 1), 100)
    stmt = (
        select(Item)
        .options(selectinload(Item.spec_enrichment))
        .where(Item.source_platform == "xianyu")
        .order_by(Item.last_seen_at.desc(), Item.id.desc())
        .limit(resolved_limit)
    )
    if source_keyword:
        stmt = stmt.where(Item.source_keyword == source_keyword)
    if task_id is not None:
        stmt = stmt.where(Item.task_id == task_id)
    stmt = _apply_business_domain_filter(stmt, business_domain=business_domain)
    if xianyu_cat_id:
        stmt = stmt.where(Item.xianyu_cat_id == xianyu_cat_id)
    if xianyu_tb_cat_id:
        stmt = stmt.where(Item.xianyu_tb_cat_id == xianyu_tb_cat_id)
    if xianyu_c_cat_id:
        stmt = stmt.where(Item.xianyu_c_cat_id == xianyu_c_cat_id)
    return list(session.execute(stmt).scalars().all())


def _build_draft_analysis(items: list[Item]) -> dict[str, Any]:
    brand_counter = Counter()
    for item in items:
        brand_value = _first_item_value(_draft_values_for_attribute(item, "brand_name"))
        if brand_value:
            brand_counter[brand_value] += 1
    domain_counter = Counter(
        str(item.business_domain).strip()
        for item in items
        if _normalize_optional_string(item.business_domain)
    )
    matched_profiles = _build_draft_profile_hints(items)
    boosted_attribute_codes = {
        code
        for profile in matched_profiles
        for code in DRAFT_PROFILE_ATTRIBUTE_BOOSTS.get(str(profile.get("key") or ""), set())
    }
    attribute_observations: list[dict[str, Any]] = []
    selected_attribute_codes: list[str] = []

    for definition in DRAFT_ATTRIBUTE_DEFINITIONS:
        code = str(definition["code"])
        observed_count = 0
        sample_values: list[Any] = []
        for item in items:
            values = _draft_values_for_attribute(item, code)
            if not values:
                continue
            observed_count += 1
            for value in values:
                friendly = _json_friendly_value(value)
                if friendly in sample_values:
                    continue
                sample_values.append(friendly)
                if len(sample_values) >= 5:
                    break
        visible = (
            observed_count > 0
            or code in DRAFT_ALWAYS_INCLUDED_ATTRIBUTE_CODES
            or code in boosted_attribute_codes
        )
        observed_ratio = _safe_ratio(observed_count, len(items))
        selected = (
            code in DRAFT_ALWAYS_INCLUDED_ATTRIBUTE_CODES
            or (
                observed_count > 0
                and (
                    code in boosted_attribute_codes
                    or observed_count >= 2
                    or observed_ratio >= 0.3
                )
            )
        )
        if selected:
            selected_attribute_codes.append(code)
        attribute_observations.append(
            {
                "attributeCode": code,
                "attributeName": definition["name"],
                "observedCount": observed_count,
                "sampleValues": sample_values,
                "selected": selected,
                "visible": visible,
                "profileSuggested": code in boosted_attribute_codes,
                "dataType": definition["dataType"],
                "valueScope": definition["valueScope"],
                "isMulti": bool(definition.get("isMulti", False)),
                "unit": definition.get("unit"),
                "sortNo": int(definition["sortNo"]),
                "suggestedCode": code,
                "optionSuggestions": _build_option_suggestions(sample_values),
            }
        )

    return {
        "sampleCount": len(items),
        "sampleItemIds": [item.item_id for item in items[:5]],
        "sampleTitles": [item.title for item in items[:5]],
        "brandHints": [{"value": value, "count": count} for value, count in brand_counter.most_common(5)],
        "businessDomainHints": [{"value": value, "count": count} for value, count in domain_counter.most_common(5)],
        "matchedProfiles": matched_profiles,
        "categoryHints": [
            {
                "code": profile["categoryCode"],
                "name": profile["categoryName"],
                "path": profile["categoryPath"],
                "confidence": profile["confidence"],
            }
            for profile in matched_profiles
        ],
        "selectedAttributeCodes": selected_attribute_codes,
        "attributeObservations": attribute_observations,
    }


def _build_draft_payload(
    *,
    selection: dict[str, Any],
    analysis: dict[str, Any],
    source_keyword: str | None,
    reuse_suggestion: dict[str, Any] | None,
) -> dict[str, Any]:
    raw_suffix = _build_raw_category_suffix(
        xianyu_cat_id=selection.get("xianyuCatId"),
        xianyu_tb_cat_id=selection.get("xianyuTbCatId"),
        xianyu_c_cat_id=selection.get("xianyuCCatId"),
    )
    request_id = f"xianyu-onboarding-draft-{raw_suffix}"
    dominant_brand = _first_hint_value(analysis.get("brandHints"))
    primary_profile = _first_profile_hint(analysis.get("categoryHints"))
    profile_code = _normalize_optional_string(primary_profile.get("code")) if primary_profile else None
    profile_name = _normalize_optional_string(primary_profile.get("name")) if primary_profile else None
    profile_path = _normalize_optional_string(primary_profile.get("path")) if primary_profile else None
    if profile_code:
        category_code = _truncate_code(f"{profile_code}_{raw_suffix}")
    else:
        category_code = _truncate_code(f"xianyu_{raw_suffix}")
    if profile_name and dominant_brand:
        category_name = f"{dominant_brand} {profile_name}"
    elif profile_name:
        category_name = profile_name
    else:
        category_name = f"{dominant_brand or 'xianyu'}_{raw_suffix}"
    if profile_path:
        category_path = f"{profile_path}/{dominant_brand or raw_suffix}"
    else:
        category_path = f"xianyu/draft/{source_keyword or dominant_brand or raw_suffix}"

    selected_codes = set(analysis.get("selectedAttributeCodes") or [])
    attributes = []
    template_items = []
    for definition in DRAFT_ATTRIBUTE_DEFINITIONS:
        code = str(definition["code"])
        if code not in selected_codes:
            continue
        attributes.append(
            {
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "code": code,
                "name": definition["name"],
                "dataType": definition["dataType"],
                "valueScope": definition["valueScope"],
                "isMulti": bool(definition.get("isMulti", False)),
                "unit": definition.get("unit"),
                "status": "DRAFT",
                "options": [],
            }
        )
        template_items.append(
            {
                "attributeCode": code,
                "isRequired": code in DRAFT_ALWAYS_INCLUDED_ATTRIBUTE_CODES,
                "isSale": False,
                "isFilter": str(definition["valueScope"]).upper() == "SPU",
                "isSearch": code in {"brand_name", "product_line", "model_name"},
                "isDisplay": True,
                "sortNo": int(definition["sortNo"]),
            }
        )

    payload = {
        "requestId": request_id,
        "catalog": {
            "requestId": request_id,
            "category": {
                "code": category_code,
                "name": category_name,
                "path": category_path,
                "level": 2,
                "status": "ACTIVE",
            },
            "attributes": attributes,
            "template": {
                "version": 1,
                "status": "DRAFT",
                "items": template_items,
            },
        },
        "mappings": [_build_recommended_mapping(selection)],
    }
    if reuse_suggestion:
        payload["categoryId"] = reuse_suggestion["category"]["id"]
        payload["templateId"] = reuse_suggestion["template"]["id"]
        payload["reuseSuggestion"] = reuse_suggestion
    return payload


def _build_reuse_suggestion(
    session: Session,
    *,
    analysis: dict[str, Any],
) -> dict[str, Any] | None:
    primary_profile = _first_profile_hint(analysis.get("categoryHints"))
    if not primary_profile:
        return None
    category_code = _normalize_optional_string(primary_profile.get("code"))
    if not category_code:
        return None

    category_rows = list(
        session.execute(
            select(Category).where(
                Category.code == category_code,
                Category.status == "ACTIVE",
            )
        ).scalars().all()
    )
    category = category_rows[0] if category_rows else None
    if category is None:
        return None

    template_rows = list(
        session.execute(
            select(CategoryAttrTemplate).where(CategoryAttrTemplate.category_id == category.id)
        ).scalars().all()
    )
    candidate_templates = [
        row
        for row in template_rows
        if _normalize_optional_string(getattr(getattr(row, "status", None), "value", getattr(row, "status", None)))
        != "RETIRED"
    ]
    if not candidate_templates:
        return None
    template = sorted(
        candidate_templates,
        key=lambda row: (
            _template_reuse_rank(getattr(row, "status", None)),
            -int(getattr(row, "version", 0) or 0),
        ),
    )[0]
    template_detail = build_catalog_template_detail(session, template.id)
    if not template_detail:
        return None

    selected_codes = [str(value) for value in list(analysis.get("selectedAttributeCodes") or []) if str(value).strip()]
    selected_code_set = set(selected_codes)
    template_codes = [
        str(item.get("attributeCode"))
        for item in list(template_detail.get("items") or [])
        if _normalize_optional_string(item.get("attributeCode"))
    ]
    template_code_set = set(template_codes)
    covered_codes = [code for code in selected_codes if code in template_code_set]
    missing_codes = [code for code in selected_codes if code not in template_code_set]
    extra_codes = [code for code in template_codes if code not in selected_code_set]

    return {
        "mode": "reuse_existing_template",
        "reason": (
            f"Primary profile {category_code} already has a canonical category and template; "
            "prefer adding a raw cate mapping instead of creating a new category."
        ),
        "category": {
            "id": category.id,
            "code": category.code,
            "name": category.name,
            "path": category.path,
            "level": category.level,
            "status": category.status,
        },
        "template": {
            "id": template.id,
            "version": template.version,
            "status": getattr(template.status, "value", template.status),
            "itemCount": len(list(template_detail.get("items") or [])),
        },
        "coverage": {
            "selectedAttributeCount": len(selected_codes),
            "coveredSuggestedAttributeCodes": covered_codes,
            "missingSuggestedAttributeCodes": missing_codes,
            "extraTemplateAttributeCodes": extra_codes,
            "coverageRatio": _safe_ratio(len(covered_codes), len(selected_codes)),
        },
    }


def _template_reuse_rank(status: Any) -> int:
    normalized = _normalize_optional_string(getattr(status, "value", status)) or ""
    if normalized == "PUBLISHED":
        return 0
    if normalized == "DRAFT":
        return 1
    return 2


def _build_recommended_mapping(selection: dict[str, Any]) -> dict[str, Any]:
    xianyu_cat_id = _normalize_optional_string(selection.get("xianyuCatId"))
    xianyu_tb_cat_id = _normalize_optional_string(selection.get("xianyuTbCatId"))
    xianyu_c_cat_id = _normalize_optional_string(selection.get("xianyuCCatId"))
    if xianyu_c_cat_id:
        return {
            "matchScope": "C_CAT",
            "xianyuCCatId": xianyu_c_cat_id,
            "resolutionSource": "draft",
            "status": "ACTIVE",
        }
    if xianyu_cat_id and xianyu_tb_cat_id:
        return {
            "matchScope": "CAT_TB",
            "xianyuCatId": xianyu_cat_id,
            "xianyuTbCatId": xianyu_tb_cat_id,
            "resolutionSource": "draft",
            "status": "ACTIVE",
        }
    if xianyu_tb_cat_id:
        return {
            "matchScope": "TB_CAT",
            "xianyuTbCatId": xianyu_tb_cat_id,
            "resolutionSource": "draft",
            "status": "ACTIVE",
        }
    return {
        "matchScope": "CAT",
        "xianyuCatId": xianyu_cat_id,
        "resolutionSource": "draft",
        "status": "ACTIVE",
    }


def _draft_values_for_attribute(item: Item, attribute_code: str) -> list[Any]:
    spec = item.spec_enrichment
    if attribute_code == "brand_name":
        explicit_brand = _normalize_optional_string(item.normalized_brand or getattr(spec, "brand", None))
        if explicit_brand:
            return [explicit_brand]
        inferred_brand = _infer_brand_name_from_title(item.title)
        return _value_list(inferred_brand)
    if attribute_code == "product_line":
        return _value_list(getattr(spec, "product_line", None) or item.normalized_model_family)
    if attribute_code == "model_name":
        inferred_lens_model = _infer_lens_model_name(item)
        if inferred_lens_model:
            return [inferred_lens_model]
        explicit_model = _normalize_optional_string(getattr(spec, "model_name", None) or item.normalized_model)
        if explicit_model:
            return [explicit_model]
        return _value_list(_compact_title_value(item.title))
    if attribute_code == "generation":
        return _value_list(getattr(spec, "generation", None))
    if attribute_code == "chip_family":
        return _value_list(getattr(spec, "chip_family", None) or item.normalized_chip)
    if attribute_code == "gpu_vendor":
        return _value_list(_infer_gpu_vendor(item))
    if attribute_code == "gpu_model":
        return _value_list(_infer_gpu_model(item))
    if attribute_code == "cpu_model":
        return _value_list(getattr(spec, "cpu_model", None))
    if attribute_code == "display_type":
        return _value_list(getattr(spec, "display_type", None))
    if attribute_code == "screen_size_in":
        return _value_list(getattr(spec, "screen_size_in", None))
    if attribute_code == "case_size_mm":
        return _value_list(getattr(spec, "case_size_mm", None))
    if attribute_code == "cpu_cores":
        return _value_list(getattr(spec, "cpu_cores", None))
    if attribute_code == "gpu_cores":
        return _value_list(getattr(spec, "gpu_cores", None))
    if attribute_code == "memory_gb":
        return _value_list(getattr(spec, "memory_gb", None) or item.normalized_memory_gb)
    if attribute_code == "storage_gb":
        return _value_list(getattr(spec, "storage_gb", None) or item.normalized_storage_gb)
    if attribute_code == "vram_gb":
        return _value_list(_infer_vram_gb(item))
    if attribute_code == "is_solar":
        return _value_list(getattr(spec, "is_solar", None))
    if attribute_code == "edition_tags":
        return _value_list(getattr(spec, "edition_tags", None))
    if attribute_code == "mount_system":
        return _value_list(_infer_mount_system(item))
    if attribute_code == "camera_series":
        return _value_list(_infer_camera_series(item))
    if attribute_code == "sensor_format":
        return _value_list(_infer_sensor_format(item))
    if attribute_code == "focal_length_range":
        return _value_list(_infer_focal_length_range(item.title))
    if attribute_code == "max_aperture":
        return _value_list(_infer_max_aperture(item.title))
    if attribute_code == "lens_series":
        return _value_list(_infer_lens_series(item))
    if attribute_code == "phone_series":
        return _value_list(_infer_phone_series(item))
    if attribute_code == "device_color":
        return _value_list(_infer_device_color(item))
    if attribute_code == "instrument_family":
        return _value_list(_infer_instrument_family(item))
    return []


def _value_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [entry for entry in value if entry not in (None, "")]
    if value == "":
        return []
    return [value]


def _build_draft_profile_hints(items: list[Item]) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    if not items:
        return profiles

    lens_confidence = _match_ratio(items, _item_looks_like_interchangeable_lens)
    if lens_confidence >= 0.4:
        profiles.append(
            {
                "key": "camera_interchangeable_lens",
                "label": "Interchangeable Lens",
                "categoryCode": "camera_interchangeable_lens",
                "categoryName": "可换镜头",
                "categoryPath": "摄影器材/镜头/可换镜头",
                "confidence": round(lens_confidence, 4),
            }
        )

    camera_body_confidence = _match_ratio(items, _item_looks_like_camera_body)
    if camera_body_confidence >= 0.4:
        profiles.append(
            {
                "key": "camera_body",
                "label": "Camera Body",
                "categoryCode": "camera_body",
                "categoryName": "相机机身",
                "categoryPath": "摄影器材/相机/机身",
                "confidence": round(camera_body_confidence, 4),
            }
        )

    computer_confidence = _match_ratio(items, _item_looks_like_computer)
    if computer_confidence >= 0.4:
        profiles.append(
            {
                "key": "computer_device",
                "label": "Computer Device",
                "categoryCode": "computer_device",
                "categoryName": "电脑设备",
                "categoryPath": "数码设备/电脑",
                "confidence": round(computer_confidence, 4),
            }
        )

    graphics_card_confidence = _match_ratio(items, _item_looks_like_graphics_card)
    if graphics_card_confidence >= 0.4:
        profiles.append(
            {
                "key": "graphics_card",
                "label": "Graphics Card",
                "categoryCode": "graphics_card",
                "categoryName": "显卡",
                "categoryPath": "电脑硬件/显卡",
                "confidence": round(graphics_card_confidence, 4),
            }
        )

    smartphone_confidence = _match_ratio(items, _item_looks_like_smartphone)
    if smartphone_confidence >= 0.4:
        profiles.append(
            {
                "key": "smartphone_device",
                "label": "Smartphone",
                "categoryCode": "smartphone_device",
                "categoryName": "手机",
                "categoryPath": "数码设备/手机",
                "confidence": round(smartphone_confidence, 4),
            }
        )

    watch_confidence = _match_ratio(items, _item_looks_like_watch)
    if watch_confidence >= 0.4:
        profiles.append(
            {
                "key": "sports_watch",
                "label": "Sports Watch",
                "categoryCode": "sports_watch",
                "categoryName": "运动手表",
                "categoryPath": "可穿戴设备/运动手表",
                "confidence": round(watch_confidence, 4),
            }
        )

    musical_instrument_confidence = _match_ratio(items, _item_looks_like_musical_instrument)
    if musical_instrument_confidence >= 0.4:
        profiles.append(
            {
                "key": "musical_instrument",
                "label": "Musical Instrument",
                "categoryCode": "musical_instrument",
                "categoryName": "乐器",
                "categoryPath": "文体乐器/乐器",
                "confidence": round(musical_instrument_confidence, 4),
            }
        )

    profiles.sort(key=lambda profile: (-float(profile["confidence"]), str(profile["key"])))
    return profiles


def _match_ratio(items: list[Item], predicate) -> float:
    if not items:
        return 0.0
    matched_count = sum(1 for item in items if predicate(item))
    return float(matched_count) / float(len(items))


def _item_looks_like_interchangeable_lens(item: Item) -> bool:
    title = _normalized_title_text(item.title)
    if not title:
        return False
    if "镜头" in title or "nikkor" in title:
        return True
    return bool(LENS_FOCAL_RANGE_PATTERN.search(title) and (LENS_APERTURE_PATTERN.search(title) or "/" in title))


def _item_looks_like_camera_body(item: Item) -> bool:
    title = _normalized_title_text(item.title)
    if not title or _item_looks_like_interchangeable_lens(item):
        return False
    camera_tokens = ("机身", "单机", "微单", "单反", "相机", "body", "camera", "alpha ", "z6", "z7", "r6", "a7")
    return any(token in title for token in camera_tokens)


def _item_looks_like_computer(item: Item) -> bool:
    if any((item.normalized_chip, item.normalized_memory_gb)):
        return True
    title = _normalized_title_text(item.title)
    return any(token in title for token in ("macbook", "mac mini", "mac studio", "imac", "笔记本", "电脑"))


def _item_looks_like_graphics_card(item: Item) -> bool:
    title = _normalized_title_text(item.title)
    return any(token in title for token in ("显卡", "rtx", "gtx", "radeon", "rx ", "quadro", "arc a"))


def _item_looks_like_smartphone(item: Item) -> bool:
    title = _normalized_title_text(item.title)
    phone_tokens = (
        "iphone",
        "手机",
        "pro max",
        "ultra",
        "mate ",
        "pura ",
        "小米",
        "redmi",
        "find x",
        "vivo",
        "iqoo",
        "galaxy",
        "荣耀",
    )
    return any(token in title for token in phone_tokens)


def _item_looks_like_watch(item: Item) -> bool:
    title = _normalized_title_text(item.title)
    return any(token in title for token in ("佳明", "garmin", "fenix", "forerunner", "epix", "instinct", "手表", "腕表"))


def _item_looks_like_musical_instrument(item: Item) -> bool:
    title = _normalized_title_text(item.title)
    return any(
        token in title
        for token in ("吉他", "钢琴", "电钢", "小提琴", "大提琴", "萨克斯", "长笛", "贝斯", "鼓", "古筝", "ukulele")
    )


def _infer_brand_name_from_title(title: str | None) -> str | None:
    normalized_title = _normalized_title_text(title)
    if not normalized_title:
        return None
    for canonical_name, hints in TITLE_BRAND_HINTS:
        if any(hint in normalized_title for hint in hints):
            return canonical_name
    return None


def _infer_mount_system(item: Item) -> str | None:
    title = _normalized_title_text(item.title)
    if not title:
        return None
    brand_name = _first_item_value(_draft_values_for_attribute(item, "brand_name"))
    if brand_name == "Nikon":
        if any(token in title for token in ("nikkor z", "尼康z", "尼康 z", "nikon z", "z卡口", "z口")):
            return "Nikon Z"
        if any(token in title for token in ("nikkor f", "尼康f", "尼康 f", "nikon f", "f卡口", "f口")):
            return "Nikon F"
    if brand_name == "Canon":
        if any(token in title for token in ("canon rf", "佳能rf", "佳能 rf", "rf卡口", "rf口")):
            return "Canon RF"
        if any(token in title for token in ("canon ef", "佳能ef", "佳能 ef", "ef卡口", "ef口")):
            return "Canon EF"
    if brand_name == "Sony":
        if any(token in title for token in ("sony fe", "索尼fe", "索尼 fe", "fe卡口", "e-mount")):
            return "Sony FE"
    if brand_name == "Fujifilm" and any(token in title for token in ("fujifilm x", "富士x", "富士 x", "x卡口", "x-mount")):
        return "Fujifilm X"
    if brand_name == "Leica" and any(token in title for token in ("leica l", "徕卡l", "徕卡 l", "l卡口", "l-mount")):
        return "Leica L"
    return None


def _infer_focal_length_range(title: str | None) -> str | None:
    normalized_title = _normalized_title_text(title)
    if not normalized_title:
        return None
    match = LENS_FOCAL_RANGE_PATTERN.search(normalized_title)
    if match is None:
        return None
    focal_range = re.sub(r"\s*-\s*", "-", str(match.group("range")))
    return f"{focal_range}mm"


def _infer_max_aperture(title: str | None) -> str | None:
    normalized_title = _normalized_title_text(title)
    if not normalized_title:
        return None
    compact_match = LENS_COMPACT_APERTURE_PATTERN.search(normalized_title)
    if compact_match is not None:
        return f"f/{compact_match.group('aperture')}"
    match = LENS_APERTURE_PATTERN.search(normalized_title)
    if match is None:
        return None
    return f"f/{match.group('aperture')}"


def _infer_lens_series(item: Item) -> str | None:
    title = _normalized_title_text(item.title)
    if not title or not _item_looks_like_interchangeable_lens(item):
        return None
    brand_name = _first_item_value(_draft_values_for_attribute(item, "brand_name"))
    if brand_name == "Nikon" and any(token in title for token in ("sline", "s line", " 2.8 s", "/2.8 s", " z 24-70 2.8 s")):
        return "S Line"
    if "g master" in title or " gm" in title:
        return "G Master"
    if " art" in title:
        return "Art"
    if brand_name == "Canon" and re.search(r"(^|[^a-z])l([^a-z]|$)", title):
        return "L"
    if " pro" in title:
        return "Pro"
    return None


def _infer_camera_series(item: Item) -> str | None:
    title = _normalized_title_text(item.title)
    if not title or not _item_looks_like_camera_body(item):
        return None
    patterns = (
        re.compile(r"(a7c\s*ii|a7\s*iv|a6700|a6400|a7r\s*v)", re.IGNORECASE),
        re.compile(r"(zf|zfc|z6\s*ii|z7\s*ii|z8|z9)", re.IGNORECASE),
        re.compile(r"(r6\s*mark\s*ii|r6\s*ii|r5\s*mark\s*ii|r5|r8)", re.IGNORECASE),
        re.compile(r"(x[-\s]?t5|x[-\s]?t4|x[-\s]?s20|gfx\s*100s)", re.IGNORECASE),
    )
    for pattern in patterns:
        match = pattern.search(title)
        if match is not None:
            return re.sub(r"\s+", " ", match.group(1)).strip().upper().replace("MARK", "Mark")
    return _normalize_optional_string(item.normalized_model_family)


def _infer_sensor_format(item: Item) -> str | None:
    title = _normalized_title_text(item.title)
    if not title:
        return None
    if any(token in title for token in ("全画幅", "full frame")):
        return "Full Frame"
    if any(token in title for token in ("aps-c", "apsc", "半画幅")):
        return "APS-C"
    if any(token in title for token in ("m43", "m4/3", "micro four thirds")):
        return "Micro Four Thirds"
    if any(token in title for token in ("一英寸", "1 inch", "1-inch")):
        return "1-inch"
    if "gfx" in title:
        return "Medium Format"
    return None


def _infer_gpu_vendor(item: Item) -> str | None:
    title = _normalized_title_text(item.title)
    if not title or not _item_looks_like_graphics_card(item):
        return None
    if any(token in title for token in ("rtx", "gtx", "quadro", "nvidia")):
        return "NVIDIA"
    if any(token in title for token in ("radeon", " rx ", "rx6600", "rx6700", "rx6800", "rx6900", "rx7600", "rx7700", "rx7800", "amd")):
        return "AMD"
    if "arc" in title:
        return "Intel"
    return None


def _infer_gpu_model(item: Item) -> str | None:
    title = _normalized_title_text(item.title)
    if not title or not _item_looks_like_graphics_card(item):
        return None
    match = GPU_MODEL_PATTERN.search(title)
    if match is None:
        return _normalize_optional_string(item.normalized_model or item.normalized_model_family)
    return re.sub(r"\s+", " ", str(match.group("model"))).strip().upper()


def _infer_vram_gb(item: Item) -> int | None:
    title = _normalized_title_text(item.title)
    if not title or not _item_looks_like_graphics_card(item):
        return None
    if "显存" not in title and "rtx" not in title and "gtx" not in title and "rx" not in title:
        return None
    match = VRAM_PATTERN.search(title)
    if match is None:
        return None
    try:
        return int(match.group("value"))
    except (TypeError, ValueError):
        return None


def _infer_phone_series(item: Item) -> str | None:
    title = _normalized_title_text(item.title)
    if not title or not _item_looks_like_smartphone(item):
        return None
    patterns = (
        re.compile(r"(iphone\s*\d{1,2}(?:\s*(?:pro\s*max|pro|max|plus|mini))?)", re.IGNORECASE),
        re.compile(r"(mate\s*\d{2}(?:\s*pro)?)", re.IGNORECASE),
        re.compile(r"(pura\s*\d{2}(?:\s*ultra|\s*pro)?)", re.IGNORECASE),
        re.compile(r"(xiaomi\s*\d{1,2}(?:\s*ultra|\s*pro)?)", re.IGNORECASE),
        re.compile(r"(find\s*x\d(?:\s*ultra|\s*pro)?)", re.IGNORECASE),
        re.compile(r"(x\d{2}\s*pro(?:\s*\+)?)", re.IGNORECASE),
        re.compile(r"(galaxy\s*s\d{2}(?:\s*ultra|\s*\+)?)", re.IGNORECASE),
    )
    for pattern in patterns:
        match = pattern.search(title)
        if match is not None:
            return re.sub(r"\s+", " ", str(match.group(1))).strip().title().replace("Iphone", "iPhone")
    return _normalize_optional_string(item.normalized_model_family or item.normalized_model)


def _infer_device_color(item: Item) -> str | None:
    title = _normalized_title_text(item.title)
    if not title:
        return None
    color_tokens = (
        ("Titanium", ("原色钛金", "钛色", "钛金", "titanium")),
        ("Black", ("黑色", "黑", "black", "曜黑")),
        ("White", ("白色", "白", "white", "月光白")),
        ("Silver", ("银色", "银", "silver")),
        ("Gold", ("金色", "金", "gold")),
        ("Blue", ("蓝色", "蓝", "blue")),
        ("Green", ("绿色", "绿", "green")),
        ("Purple", ("紫色", "紫", "purple")),
        ("Pink", ("粉色", "粉", "pink")),
        ("Red", ("红色", "红", "red")),
    )
    for canonical, tokens in color_tokens:
        if any(token in title for token in tokens):
            return canonical
    return None


def _infer_instrument_family(item: Item) -> str | None:
    title = _normalized_title_text(item.title)
    if not title or not _item_looks_like_musical_instrument(item):
        return None
    families = (
        ("Guitar", ("吉他", "guitar")),
        ("Bass", ("贝斯", "bass")),
        ("Piano", ("钢琴", "电钢", "piano")),
        ("Violin", ("小提琴", "violin")),
        ("Cello", ("大提琴", "cello")),
        ("Saxophone", ("萨克斯", "saxophone")),
        ("Drum", ("架子鼓", "鼓", "drum")),
        ("Ukulele", ("ukulele", "尤克里里")),
        ("Guzheng", ("古筝",)),
    )
    for canonical, tokens in families:
        if any(token in title for token in tokens):
            return canonical
    return None


def _infer_lens_model_name(item: Item) -> str | None:
    if not _item_looks_like_interchangeable_lens(item):
        return None
    brand_name = _first_item_value(_draft_values_for_attribute(item, "brand_name"))
    mount_system = _infer_mount_system(item)
    focal_range = _infer_focal_length_range(item.title)
    max_aperture = _infer_max_aperture(item.title)
    lens_series = _infer_lens_series(item)
    if not any((mount_system, focal_range, max_aperture)):
        return None

    parts: list[str] = []
    if brand_name:
        parts.append(brand_name)
    if mount_system:
        mount_label = mount_system
        if brand_name and mount_system.startswith(f"{brand_name} "):
            mount_label = mount_system[len(brand_name) + 1 :]
        parts.append(mount_label)
    if focal_range:
        parts.append(focal_range)
    if max_aperture:
        parts.append(max_aperture)
    if lens_series:
        parts.append(lens_series)
    return " ".join(part for part in parts if part).strip() or None


def _build_option_suggestions(values: list[Any]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, value in enumerate(values, start=1):
        if not isinstance(value, (str, int, float, Decimal)):
            continue
        option_name = str(value).strip()
        if not option_name or len(option_name) > 40:
            continue
        option_code = _suggest_option_code(option_name, index=index)
        if option_code in seen_codes:
            continue
        seen_codes.add(option_code)
        suggestions.append(
            {
                "optionCode": option_code,
                "optionName": option_name,
                "sortNo": index * 10,
            }
        )
        if len(suggestions) >= 8:
            break
    return suggestions


def _suggest_option_code(option_name: str, *, index: int) -> str:
    normalized = _normalized_title_text(option_name)
    explicit_mappings = (
        ("black", ("黑色", "黑", "black", "曜黑")),
        ("white", ("白色", "白", "white")),
        ("silver", ("银色", "银", "silver")),
        ("gold", ("金色", "金", "gold")),
        ("blue", ("蓝色", "蓝", "blue")),
        ("green", ("绿色", "绿", "green")),
        ("purple", ("紫色", "紫", "purple")),
        ("pink", ("粉色", "粉", "pink")),
        ("red", ("红色", "红", "red")),
        ("titanium", ("钛色", "钛金", "titanium")),
        ("full_frame", ("全画幅", "full frame")),
        ("aps_c", ("aps-c", "apsc", "半画幅")),
        ("micro_four_thirds", ("m43", "m4/3", "micro four thirds")),
    )
    for code, tokens in explicit_mappings:
        if any(token in normalized for token in tokens):
            return code
    ascii_slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if ascii_slug:
        return ascii_slug[:48]
    return f"option_{index}"


def _compact_title_value(title: str | None) -> str | None:
    normalized_title = _normalize_optional_string(title)
    if not normalized_title:
        return None
    compact = re.split(r"[，。,；;|]", normalized_title, maxsplit=1)[0]
    compact = re.sub(r"^(95新|98新|99新|9成新|全新|国行|自用)\s*", "", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\s+", " ", compact).strip()
    return compact[:80] if compact else None


def _normalized_title_text(title: str | None) -> str:
    normalized_title = _normalize_optional_string(title)
    if not normalized_title:
        return ""
    return re.sub(r"\s+", " ", normalized_title).strip().lower()


def _first_item_value(values: list[Any]) -> str | None:
    if not values:
        return None
    return _normalize_optional_string(values[0])


def _json_friendly_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_json_friendly_value(entry) for entry in value]
    return value


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _json_friendly_value(value)
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except TypeError:
            pass
    if isinstance(value, list):
        return [_json_safe_value(entry) for entry in value]
    if isinstance(value, tuple):
        return [_json_safe_value(entry) for entry in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_value(nested) for key, nested in value.items()}
    return value


def _first_hint_value(values: Any) -> str | None:
    if not isinstance(values, list) or not values:
        return None
    first = values[0]
    if not isinstance(first, dict):
        return None
    return _normalize_optional_string(first.get("value"))


def _first_profile_hint(values: Any) -> dict[str, Any] | None:
    if not isinstance(values, list) or not values:
        return None
    first = values[0]
    if not isinstance(first, dict):
        return None
    return dict(first)


def _build_raw_category_suffix(
    *,
    xianyu_cat_id: str | None,
    xianyu_tb_cat_id: str | None,
    xianyu_c_cat_id: str | None,
) -> str:
    if xianyu_c_cat_id:
        return f"ccat_{xianyu_c_cat_id}"
    if xianyu_cat_id and xianyu_tb_cat_id:
        return f"cat_{xianyu_cat_id}_tb_{xianyu_tb_cat_id}"
    if xianyu_tb_cat_id:
        return f"tb_{xianyu_tb_cat_id}"
    if xianyu_cat_id:
        return f"cat_{xianyu_cat_id}"
    return "unknown_category"


def _truncate_code(value: str, *, limit: int = 64) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit]


def _build_raw_signal_backfill_item_result(
    *,
    item: Item,
    status: str,
    updates: dict[str, str] | None = None,
    proposed: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    return {
        "itemId": item.item_id,
        "taskId": item.task_id,
        "businessDomain": item.business_domain,
        "sourceKeyword": item.source_keyword,
        "status": status,
        "current": {
            "xianyuCCatId": item.xianyu_c_cat_id,
            "xianyuCatId": item.xianyu_cat_id,
            "xianyuTbCatId": item.xianyu_tb_cat_id,
        },
        "proposed": {
            "xianyuCCatId": proposed.get("xianyu_c_cat_id") if proposed else None,
            "xianyuCatId": proposed.get("xianyu_cat_id") if proposed else None,
            "xianyuTbCatId": proposed.get("xianyu_tb_cat_id") if proposed else None,
        },
        "updates": {
            "xianyuCCatId": updates.get("xianyu_c_cat_id") if updates else None,
            "xianyuCatId": updates.get("xianyu_cat_id") if updates else None,
            "xianyuTbCatId": updates.get("xianyu_tb_cat_id") if updates else None,
        },
    }


def _count_stmt(stmt):
    return select(func.count()).select_from(stmt.order_by(None).limit(None).offset(None).subquery())


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def _extract_catalog_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    catalog_payload = payload.get("catalog")
    if isinstance(catalog_payload, dict):
        return dict(catalog_payload)
    if all(payload.get(key) is not None for key in ("category", "template", "attributes")):
        return {
            "requestId": payload.get("requestId"),
            "category": payload["category"],
            "template": payload["template"],
            "attributes": payload["attributes"],
        }
    return None


def _extract_mapping_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    mappings = payload.get("mappings")
    if isinstance(mappings, list):
        return [dict(entry) for entry in mappings]
    mapping = payload.get("mapping")
    if isinstance(mapping, dict):
        return [dict(mapping)]
    return []


def _normalize_mapping_payload(mapping_payload: dict[str, Any]) -> dict[str, Any]:
    xianyu_cat_id = _normalize_optional_string(
        mapping_payload.get("xianyuCatId") or mapping_payload.get("xianyu_cat_id")
    )
    xianyu_tb_cat_id = _normalize_optional_string(
        mapping_payload.get("xianyuTbCatId") or mapping_payload.get("xianyu_tb_cat_id")
    )
    xianyu_c_cat_id = _normalize_optional_string(
        mapping_payload.get("xianyuCCatId") or mapping_payload.get("xianyu_c_cat_id")
    )
    match_scope = _infer_match_scope(
        mapping_payload.get("matchScope") or mapping_payload.get("match_scope"),
        xianyu_cat_id=xianyu_cat_id,
        xianyu_tb_cat_id=xianyu_tb_cat_id,
        xianyu_c_cat_id=xianyu_c_cat_id,
    )
    confidence = mapping_payload.get("confidence")
    return {
        "match_scope": match_scope,
        "xianyu_cat_id": xianyu_cat_id,
        "xianyu_tb_cat_id": xianyu_tb_cat_id,
        "xianyu_c_cat_id": xianyu_c_cat_id,
        "raw_category_name": _normalize_optional_string(
            mapping_payload.get("rawCategoryName") or mapping_payload.get("raw_category_name")
        ),
        "raw_category_path": _normalize_optional_string(
            mapping_payload.get("rawCategoryPath") or mapping_payload.get("raw_category_path")
        ),
        "resolution_source": _normalize_optional_string(
            mapping_payload.get("resolutionSource") or mapping_payload.get("resolution_source")
        )
        or "manual",
        "status": _normalize_optional_string(mapping_payload.get("status")) or "ACTIVE",
        "confidence": Decimal(str(confidence)) if confidence is not None else None,
        "metadata_json": dict(mapping_payload.get("metadata") or mapping_payload.get("metadata_json") or {}),
        "allow_remap": bool(mapping_payload.get("allowRemap") or mapping_payload.get("allow_remap")),
    }


def _coerce_match_scope(value: XianyuCategoryMatchScope | str) -> XianyuCategoryMatchScope:
    if isinstance(value, XianyuCategoryMatchScope):
        return value
    raw = str(value or "").strip().upper()
    try:
        return XianyuCategoryMatchScope(raw)
    except ValueError as exc:
        raise XianyuCategoryMappingError(f"Invalid matchScope: {value}") from exc


def _infer_match_scope(
    value: Any,
    *,
    xianyu_cat_id: str | None,
    xianyu_tb_cat_id: str | None,
    xianyu_c_cat_id: str | None,
) -> XianyuCategoryMatchScope:
    if value:
        return _coerce_match_scope(value)
    signals = int(bool(xianyu_cat_id)) + int(bool(xianyu_tb_cat_id)) + int(bool(xianyu_c_cat_id))
    if signals == 0:
        raise XianyuCategoryMappingError("At least one raw category id is required.")
    if signals > 1:
        raise XianyuCategoryMappingError("matchScope is required when multiple raw category ids are provided.")
    if xianyu_c_cat_id:
        return XianyuCategoryMatchScope.C_CAT
    if xianyu_tb_cat_id:
        return XianyuCategoryMatchScope.TB_CAT
    return XianyuCategoryMatchScope.CAT


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
