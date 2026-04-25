from __future__ import annotations

import json
import os
from collections import defaultdict
from decimal import Decimal
from datetime import date, datetime, timedelta
from ...compat import UTC
import statistics
from typing import Any

from sqlalchemy import desc, func, literal, select

from ...category_compat import (
    compatible_scope_keys,
    display_label_for_scope,
    is_analytics_scope,
    is_apple_computer_scope,
    is_garmin_watch_scope,
    non_analytics_scope_codes,
    resolve_category_code,
)
from ...models import (
    BrowserSession,
    Category,
    CrawlRun,
    CrawlTask,
    Item,
    ItemSnapshot,
    ItemSpecEnrichment,
    ProductSku,
    ProductSpu,
    ProductStatus,
    RawResponse,
    SellerProfile,
    UserListingPreference,
)
from ...normalizers import normalize_market_price
from ...presentation.web import DOMAIN_TOKENS, domain_label, format_currency
from ...pricing import (
    apple_product_line_allows_chip_family,
    aggregate_pricing_view,
    build_product_label,
    build_spec_label,
    filter_outlier_price_records,
    load_pricing_records,
    normalize_apple_chip_family,
    normalize_apple_screen_size,
    normalize_product_line,
    percentile,
    resolve_pricing_record,
    resolve_pricing_scope,
)
from .pricing_domain import APPLE_ANALYSIS_PRODUCT_LINES, GARMIN_ANALYSIS_PRODUCT_LINES
from .pricing_thresholds import evaluate_pricing_row_availability
from .template_feature_flags import is_price_template_trend_enabled
from .pricing_templates import build_pricing_record_template_snapshot
from .catalog_category_quality import catalog_scope_mismatch_reason

TREND_CHART_WIDTH = 720
TREND_CHART_HEIGHT = 260
TREND_CHART_PADDING = {
    "top": 16.0,
    "right": 18.0,
    "bottom": 28.0,
    "left": 54.0,
}
TREND_PRICE_TICKS = 4
TREND_CARD_LIMIT_PER_DOMAIN = 2
TREND_CARD_LIMIT_FOR_SELECTED_DOMAIN = 4
TREND_CARD_CANDIDATE_LIMIT_PER_DOMAIN = 6
TREND_CARD_CANDIDATE_LIMIT_FOR_SELECTED_DOMAIN = 10
TREND_MIN_GROUP_SAMPLE_COUNT = 4
TREND_MIN_DAY_COUNT = 4
TREND_MIN_LATEST_SAMPLE_COUNT = 3
TREND_MIN_RECENT_AVG_SAMPLE_COUNT = 4.0

DASHBOARD_PRICING_READ_MODE_ENV = "DASHBOARD_PRICING_READ_MODE"
DASHBOARD_PRICING_LEGACY_FALLBACK_ENV = "DASHBOARD_PRICING_LEGACY_FALLBACK_ENABLED"
DASHBOARD_PRICING_READ_MODES = {"legacy", "dual", "catalog_primary", "catalog_only"}


def _read_bool_env(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _resolve_dashboard_pricing_read_mode() -> str:
    raw_mode = str(os.getenv(DASHBOARD_PRICING_READ_MODE_ENV, "catalog_primary") or "").strip().lower()
    if raw_mode in DASHBOARD_PRICING_READ_MODES:
        return raw_mode
    return "catalog_primary"


def dashboard_pricing_read_cache_signature() -> tuple[str, bool]:
    return (
        _resolve_dashboard_pricing_read_mode(),
        _read_bool_env(
            DASHBOARD_PRICING_LEGACY_FALLBACK_ENV,
            default=True,
        ),
    )


def load_dashboard_pricing_records(
    session,
    *,
    business_domain: str | None,
    category_code: str | None = None,
    freshness_days: int,
    heartbeat_days: int | None = None,
) -> dict[str, Any]:
    read_mode = _resolve_dashboard_pricing_read_mode()
    fallback_enabled_by_env = _read_bool_env(
        DASHBOARD_PRICING_LEGACY_FALLBACK_ENV,
        default=True,
    )

    if read_mode == "legacy":
        legacy_records = load_pricing_records(
            session=session,
            business_domain=business_domain,
            category_code=category_code,
            freshness_days=freshness_days,
            heartbeat_days=heartbeat_days,
        )
        return {
            "records": legacy_records,
            "readMode": read_mode,
            "readSource": "legacy",
            "legacyFallbackEnabled": True,
            "fallbackUsed": False,
            "fallbackReason": None,
            "catalogRecordCount": 0,
            "legacyRecordCount": len(legacy_records),
        }

    catalog_records = _load_catalog_pricing_records(
        session=session,
        business_domain=business_domain,
        category_code=category_code,
        freshness_days=freshness_days,
        heartbeat_days=heartbeat_days,
    )
    catalog_count = len(catalog_records)
    fallback_allowed = fallback_enabled_by_env and read_mode != "catalog_only"

    if catalog_count > 0:
        return {
            "records": catalog_records,
            "readMode": read_mode,
            "readSource": "catalog",
            "legacyFallbackEnabled": fallback_allowed,
            "fallbackUsed": False,
            "fallbackReason": None,
            "catalogRecordCount": catalog_count,
            "legacyRecordCount": 0,
        }

    if fallback_allowed:
        legacy_records = load_pricing_records(
            session=session,
            business_domain=business_domain,
            category_code=category_code,
            freshness_days=freshness_days,
            heartbeat_days=heartbeat_days,
        )
        return {
            "records": legacy_records,
            "readMode": read_mode,
            "readSource": "legacy",
            "legacyFallbackEnabled": True,
            "fallbackUsed": True,
            "fallbackReason": "catalog_empty",
            "catalogRecordCount": catalog_count,
            "legacyRecordCount": len(legacy_records),
        }

    return {
        "records": [],
        "readMode": read_mode,
        "readSource": "catalog",
        "legacyFallbackEnabled": False,
        "fallbackUsed": False,
        "fallbackReason": "catalog_empty_no_fallback",
        "catalogRecordCount": 0,
        "legacyRecordCount": 0,
    }


def _load_catalog_pricing_records(
    session,
    *,
    business_domain: str | None,
    category_code: str | None = None,
    freshness_days: int,
    heartbeat_days: int | None = None,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    freshness_limit = freshness_cutoff(window_days=freshness_days, now=now)
    heartbeat_limit = (
        heartbeat_cutoff(heartbeat_days=heartbeat_days, now=now)
        if heartbeat_days is not None
        else None
    )
    scope_keys = _scope_keys_for_filter(
        business_domain=business_domain,
        category_code=category_code,
    )
    updated_at_expr = func.greatest(ProductSpu.updated_at, ProductSku.updated_at)
    stmt = (
        select(ProductSpu, ProductSku, Category.code)
        .join(ProductSku, ProductSku.spu_id == ProductSpu.id)
        .join(Category, Category.id == ProductSpu.category_id)
        .where(ProductSpu.status == ProductStatus.ACTIVE)
        .where(ProductSku.status == ProductStatus.ACTIVE)
        .where(ProductSku.price.is_not(None), ProductSku.price > 0)
        .where(updated_at_expr >= freshness_limit)
    )
    if heartbeat_limit is not None:
        stmt = stmt.where(updated_at_expr >= heartbeat_limit)
    if scope_keys:
        stmt = stmt.where(Category.code.in_(scope_keys))
    else:
        stmt = stmt.where(~Category.code.in_(non_analytics_scope_codes()))

    rows = session.execute(
        stmt.order_by(ProductSpu.updated_at.desc(), ProductSku.updated_at.desc())
    ).all()
    records: list[dict[str, Any]] = []
    for spu, sku, raw_category_code in rows:
        resolved_category_code = resolve_category_code(raw_category_code)
        if not resolved_category_code:
            continue
        record = _build_catalog_pricing_record(
            spu=spu,
            sku=sku,
            category_code=resolved_category_code,
        )
        if record is not None:
            records.append(record)
    return records


def _build_catalog_pricing_record(
    *,
    spu: ProductSpu,
    sku: ProductSku,
    category_code: str,
) -> dict[str, Any] | None:
    if catalog_scope_mismatch_reason(
        category_code,
        title=spu.title,
        spu_snapshot=spu.attr_snapshot_json,
        sku_snapshots=[sku.attr_snapshot_json],
    ):
        return None

    spu_snapshot = dict(spu.attr_snapshot_json or {})
    spu_attributes = list(spu_snapshot.get("attributes") or [])
    sku_snapshot = dict(sku.attr_snapshot_json or {})
    sku_attributes = list(sku_snapshot.get("attributes") or [])
    sku_sale_attributes = list(sku_snapshot.get("saleAttributes") or [])

    product_line = _snapshot_text_value(spu_attributes, "product_line")
    model_name = _snapshot_text_value(spu_attributes, "model_name")
    chip_family = _snapshot_text_value(spu_attributes, "chip_family")
    display_type = _snapshot_text_value(spu_attributes, "display_type") or _snapshot_text_value(
        sku_sale_attributes,
        "display_type",
    )
    case_size_mm = _snapshot_int_value(spu_attributes, "case_size_mm")
    is_solar = _snapshot_bool_value(spu_attributes, "is_solar")
    screen_size_in = _snapshot_decimal_value(spu_attributes, "screen_size_in")
    cpu_cores = _snapshot_int_value(spu_attributes, "cpu_cores")
    gpu_cores = _snapshot_int_value(spu_attributes, "gpu_cores")
    memory_gb = _snapshot_int_value(sku_attributes, "memory_gb")
    storage_gb = _snapshot_int_value(sku_attributes, "storage_gb")

    if is_garmin_watch_scope(category_code):
        product_line = normalize_product_line(
            product_line=product_line,
            model_name=model_name,
            allowed_values=GARMIN_ANALYSIS_PRODUCT_LINES,
        )
        if product_line not in GARMIN_ANALYSIS_PRODUCT_LINES:
            return None

    if is_apple_computer_scope(category_code):
        product_line = normalize_product_line(
            product_line=product_line,
            model_name=model_name,
            allowed_values=APPLE_ANALYSIS_PRODUCT_LINES,
        )
        raw_screen_size_in = screen_size_in
        chip_family = normalize_apple_chip_family(chip_family)
        screen_size_in = normalize_apple_screen_size(
            product_line=product_line,
            screen_size_in=screen_size_in,
        )
        if (
            product_line not in APPLE_ANALYSIS_PRODUCT_LINES
            or not chip_family
            or (str(product_line or "").startswith("MacBook") and raw_screen_size_in is not None and screen_size_in is None)
            or not apple_product_line_allows_chip_family(product_line=product_line, chip_family=chip_family)
        ):
            return None

    product_label = build_product_label(
        business_domain=category_code,
        product_line=product_line,
        model_name=model_name,
        screen_size_in=screen_size_in,
        chip_family=chip_family,
    )
    if is_apple_computer_scope(category_code) or is_garmin_watch_scope(category_code):
        resolved_product_label = product_label
    else:
        resolved_product_label = product_label or model_name or product_line or spu.title
    if not resolved_product_label:
        return None
    spec_label, exact_spec_ready = build_spec_label(
        business_domain=category_code,
        product_label=resolved_product_label,
        display_type=display_type,
        case_size_mm=case_size_mm,
        is_solar=is_solar,
        screen_size_in=screen_size_in,
        chip_family=chip_family,
        cpu_cores=cpu_cores,
        gpu_cores=gpu_cores,
        memory_gb=memory_gb,
        storage_gb=storage_gb,
    )
    normalized_price = normalize_market_price(
        sku.price,
        business_domain=category_code,
        model_family=product_line,
    )
    if normalized_price is None:
        return None
    price = float(normalized_price)
    if price <= 0:
        return None
    brand = _catalog_brand_for_scope(
        category_code=category_code,
        fallback=spu.brand_id,
    )
    if not brand:
        return None

    spec_status = "resolved" if exact_spec_ready else "partial"
    spec_confidence = 0.95 if exact_spec_ready else 0.70
    pricing_usable = bool(resolved_product_label)
    last_seen_at = sku.updated_at or spu.updated_at
    item_id = f"catalog:{spu.id}:{sku.sku_code}"
    return {
        "item_id_ref": None,
        "item_id": item_id,
        "source_platform": "catalog",
        "business_domain": category_code,
        "category_code": category_code,
        "category_name": display_label_for_scope(category_code),
        "category_id": spu.category_id,
        "template_id": spu.template_id,
        "model_catalog_id": None,
        "seller_key": str(spu.merchant_id or f"catalog:spu:{spu.id}"),
        "title": spu.title,
        "region": None,
        "listing_url": None,
        "price": price,
        "last_seen_at": last_seen_at,
        "publish_time": spu.created_at,
        "first_seen_at": spu.created_at,
        "brand": brand,
        "product_line": product_line,
        "model_name": model_name,
        "product_label": resolved_product_label,
        "spec_label": spec_label,
        "exact_spec_ready": bool(exact_spec_ready),
        "display_type": display_type,
        "case_size_mm": case_size_mm,
        "is_solar": is_solar,
        "screen_size_in": float(screen_size_in) if screen_size_in is not None else None,
        "chip_family": chip_family,
        "cpu_cores": cpu_cores,
        "gpu_cores": gpu_cores,
        "memory_gb": memory_gb,
        "storage_gb": storage_gb,
        "spec_status": spec_status,
        "spec_confidence": spec_confidence,
        "spec_contract": {
            "snapshotSource": "catalog_snapshot",
            "source": "catalog_snapshot",
            "status": spec_status,
            "confidence": spec_confidence,
            "exactSpecReady": bool(exact_spec_ready),
            "needsReview": not bool(exact_spec_ready),
            "requiredFields": [],
            "missingRequiredFields": [],
            "identityFields": [],
        },
        "spec_source": {
            "source": "catalog_snapshot",
            "status": spec_status,
            "pricingUsable": pricing_usable,
        },
        "pricing_eligibility": {
            "source": "catalog_snapshot",
            "pricingUsable": pricing_usable,
            "exactSpecReady": bool(exact_spec_ready),
        },
    }


def _catalog_brand_for_scope(*, category_code: str, fallback: Any) -> str | None:
    canonical_code = resolve_category_code(category_code) or category_code
    if canonical_code == "apple_computer":
        return "Apple"
    if canonical_code == "garmin_watch":
        return "Garmin"
    normalized_fallback = str(fallback or "").strip()
    if normalized_fallback:
        return normalized_fallback
    return canonical_code


def _snapshot_rows_for_code(rows: list[dict[str, Any]], attribute_code: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if isinstance(row, dict) and str(row.get("attributeCode") or "") == attribute_code
    ]


def _snapshot_text_value(rows: list[dict[str, Any]], attribute_code: str) -> str | None:
    for row in _snapshot_rows_for_code(rows, attribute_code):
        value_type = str(row.get("valueType") or "").upper()
        if value_type == "ENUM":
            candidate = row.get("optionName") or row.get("optionCode")
        else:
            candidate = row.get("value")
        normalized = str(candidate or "").strip()
        if normalized:
            return normalized
    return None


def _snapshot_bool_value(rows: list[dict[str, Any]], attribute_code: str) -> bool | None:
    for row in _snapshot_rows_for_code(rows, attribute_code):
        candidate = row.get("value")
        if isinstance(candidate, bool):
            return candidate
        normalized = str(candidate or "").strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _snapshot_decimal_value(rows: list[dict[str, Any]], attribute_code: str) -> Decimal | None:
    for row in _snapshot_rows_for_code(rows, attribute_code):
        candidate = row.get("normalizedValue", row.get("value"))
        normalized = _coerce_decimal(candidate)
        if normalized is not None:
            return normalized
    return None


def _snapshot_int_value(rows: list[dict[str, Any]], attribute_code: str) -> int | None:
    number = _snapshot_decimal_value(rows, attribute_code)
    if number is None:
        return None
    return int(number)


def _coerce_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def load_available_domains(session) -> list[str | None]:
    raw_values = list(session.execute(select(Item.business_domain).distinct().order_by(Item.business_domain)).scalars())
    seen: set[str] = set()
    values: list[str] = []
    for raw_value in raw_values:
        if not is_analytics_scope(raw_value):
            continue
        canonical_value = resolve_category_code(raw_value)
        if canonical_value and canonical_value not in seen:
            seen.add(canonical_value)
            values.append(canonical_value)
    return values


def _scope_keys_for_filter(
    *,
    business_domain: str | None = None,
    category_code: str | None = None,
) -> tuple[str, ...]:
    return resolve_pricing_scope(
        business_domain=business_domain,
        category_code=category_code,
    ).scope_keys


def _apply_visible_scope_filter(
    stmt,
    *,
    column,
    business_domain: str | None = None,
    category_code: str | None = None,
):
    scope_keys = _scope_keys_for_filter(
        business_domain=business_domain,
        category_code=category_code,
    )
    if scope_keys:
        return stmt.where(column.in_(scope_keys))
    return stmt.where(~column.in_(non_analytics_scope_codes()))


def freshness_cutoff(*, window_days: int, now: datetime | None = None) -> datetime:
    reference = now or datetime.now(UTC)
    return reference - timedelta(days=max(window_days, 1))


def heartbeat_cutoff(*, heartbeat_days: int, now: datetime | None = None) -> datetime:
    reference = now or datetime.now(UTC)
    return reference - timedelta(days=max(heartbeat_days, 1))


def heartbeat_state(
    *,
    last_seen_at: datetime | None,
    heartbeat_days: int,
    now: datetime | None = None,
) -> str:
    if last_seen_at is None:
        return "stale"
    cutoff = heartbeat_cutoff(heartbeat_days=heartbeat_days, now=now)
    return "active" if last_seen_at.astimezone(UTC) >= cutoff else "stale"


def heartbeat_state_label(value: str) -> str:
    return "心跳正常" if value == "active" else "疑似失活"


def heartbeat_state_class(value: str) -> str:
    return "active" if value == "active" else "stale"


def heartbeat_signal(
    *,
    active_count: int,
    stale_count: int,
    latest_seen_at: datetime | None,
    heartbeat_days: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    total = active_count + stale_count
    latest_state = heartbeat_state(
        last_seen_at=latest_seen_at,
        heartbeat_days=heartbeat_days,
        now=now,
    )
    stale_ratio = (stale_count / total * 100) if total else 0.0
    if total <= 0:
        return {
            "label": "暂无样本",
            "class_name": "watch",
            "stale_ratio": 0.0,
        }
    if active_count <= 0 or latest_state == "stale":
        return {
            "label": "心跳暂停",
            "class_name": "alert",
            "stale_ratio": round(stale_ratio, 1),
        }
    if stale_ratio >= 50:
        return {
            "label": "明显降温",
            "class_name": "alert",
            "stale_ratio": round(stale_ratio, 1),
        }
    if stale_ratio >= 25:
        return {
            "label": "供给回落",
            "class_name": "warm",
            "stale_ratio": round(stale_ratio, 1),
        }
    return {
        "label": "心跳正常",
        "class_name": "healthy",
        "stale_ratio": round(stale_ratio, 1),
    }


def stale_days(last_seen_at: datetime | None, *, now: datetime | None = None) -> int | None:
    if last_seen_at is None:
        return None
    reference = now or datetime.now(UTC)
    age_seconds = max((reference - last_seen_at.astimezone(UTC)).total_seconds(), 0)
    return int(age_seconds // 86400)


def display_model_expression():
    return func.coalesce(
        func.nullif(ItemSpecEnrichment.model_name, ""),
        func.nullif(Item.normalized_model, ""),
        func.nullif(Item.normalized_model_family, ""),
        func.nullif(Item.source_keyword, ""),
        literal("Unclassified"),
    )


def build_overview(
    session,
    *,
    business_domain: str | None,
    category_code: str | None = None,
    window_days: int,
    heartbeat_days: int,
) -> dict[str, Any]:
    scope = resolve_pricing_scope(
        business_domain=business_domain,
        category_code=category_code,
    )
    scope_label_value = scope.category_code or scope.requested_scope
    now = datetime.now(UTC)
    window_limit = freshness_cutoff(window_days=window_days, now=now)
    active_limit = heartbeat_cutoff(heartbeat_days=heartbeat_days, now=now)
    stmt = select(
        func.count(Item.id).label("total_items"),
        func.count(Item.id).filter(Item.last_seen_at >= active_limit).label("active_items"),
        func.count(Item.id).filter(Item.last_seen_at < active_limit).label("stale_items"),
        func.count(Item.id).filter(Item.first_seen_at >= window_limit).label("new_items"),
        func.count(func.distinct(Item.seller_profile_id)).label("total_sellers"),
        func.max(Item.last_seen_at).label("latest_seen"),
    ).where(
        Item.is_active.is_(True),
        Item.last_seen_at >= window_limit,
    )
    stmt = _apply_visible_scope_filter(
        stmt,
        column=Item.business_domain,
        business_domain=business_domain,
        category_code=category_code,
    )

    row = session.execute(stmt).one()

    latest_run_stmt = (
        select(CrawlRun, CrawlTask.display_name, CrawlTask.task_key)
        .join(CrawlTask, CrawlTask.id == CrawlRun.task_id)
        .order_by(CrawlRun.started_at.desc())
        .limit(1)
    )
    latest_run_stmt = _apply_visible_scope_filter(
        latest_run_stmt,
        column=CrawlTask.business_domain,
        business_domain=business_domain,
        category_code=category_code,
    )
    latest_run = session.execute(latest_run_stmt).first()

    browser_session = session.execute(
        select(BrowserSession).order_by(BrowserSession.updated_at.desc()).limit(1)
    ).scalar_one_or_none()

    total_items = int(row.total_items or 0)
    active_items = int(row.active_items or 0)
    stale_items = int(row.stale_items or 0)
    stale_ratio = (stale_items / total_items * 100) if total_items else 0.0

    return {
        "scope_label": display_label_for_scope(scope_label_value) if scope_label_value else "全部业务域",
        "window_days": window_days,
        "heartbeat_days": heartbeat_days,
        "total_items": total_items,
        "active_items": active_items,
        "stale_items": stale_items,
        "new_items": int(row.new_items or 0),
        "fresh_items": int(row.new_items or 0),
        "total_sellers": int(row.total_sellers or 0),
        "latest_seen": row.latest_seen,
        "stale_ratio": round(stale_ratio, 1),
        "latest_run": {
            "display_name": latest_run[1],
            "task_key": latest_run[2],
            "status": latest_run[0].status,
            "started_at": latest_run[0].started_at,
            "finished_at": latest_run[0].finished_at,
            "pages_succeeded": latest_run[0].pages_succeeded,
            "pages_attempted": latest_run[0].pages_attempted,
        }
        if latest_run
        else None,
        "browser_session": browser_session,
    }


def build_domain_cards(
    session,
    *,
    business_domain: str | None,
    category_code: str | None = None,
    window_days: int,
    heartbeat_days: int,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    window_limit = freshness_cutoff(window_days=window_days, now=now)
    active_limit = heartbeat_cutoff(heartbeat_days=heartbeat_days, now=now)

    stmt = (
        select(
            Item.business_domain,
            func.count(Item.id).label("listing_count"),
            func.count(Item.id).filter(Item.last_seen_at >= active_limit).label("active_count"),
            func.count(Item.id).filter(Item.last_seen_at < active_limit).label("stale_count"),
            func.count(Item.id).filter(Item.first_seen_at >= window_limit).label("new_count"),
            func.count(func.distinct(Item.seller_profile_id)).label("seller_count"),
            func.avg(Item.current_price).label("avg_price"),
            func.max(Item.last_seen_at).label("last_seen_at"),
        )
        .where(
            Item.is_active.is_(True),
            Item.last_seen_at >= window_limit,
        )
        .group_by(Item.business_domain)
        .order_by(desc("listing_count"))
    )
    stmt = _apply_visible_scope_filter(
        stmt,
        column=Item.business_domain,
        business_domain=business_domain,
        category_code=category_code,
    )

    rows = session.execute(stmt).all()
    cards_by_scope: dict[str, dict[str, Any]] = {}
    for row in rows:
        scope_code = resolve_category_code(row.business_domain)
        active_count = int(row.active_count or 0)
        stale_count = int(row.stale_count or 0)
        listing_count = int(row.listing_count or 0)
        card = cards_by_scope.setdefault(
            scope_code,
            {
                "business_domain": scope_code,
                "categoryCode": scope_code,
                "categoryName": display_label_for_scope(scope_code),
                "label": display_label_for_scope(scope_code),
                "listing_count": 0,
                "active_count": 0,
                "stale_count": 0,
                "new_count": 0,
                "seller_count": 0,
                "avg_price": None,
                "_avg_price_total": 0.0,
                "_avg_price_weight": 0,
                "last_seen_at": None,
            },
        )
        card["listing_count"] += listing_count
        card["active_count"] += active_count
        card["stale_count"] += stale_count
        card["new_count"] += int(row.new_count or 0)
        card["seller_count"] += int(row.seller_count or 0)
        if row.avg_price is not None and listing_count > 0:
            card["_avg_price_total"] += float(row.avg_price) * listing_count
            card["_avg_price_weight"] += listing_count
        if row.last_seen_at is not None and (
            card["last_seen_at"] is None or row.last_seen_at > card["last_seen_at"]
        ):
            card["last_seen_at"] = row.last_seen_at

    cards: list[dict[str, Any]] = []
    for card in cards_by_scope.values():
        listing_count = int(card["listing_count"])
        stale_count = int(card["stale_count"])
        signal = heartbeat_signal(
            active_count=int(card["active_count"]),
            stale_count=stale_count,
            latest_seen_at=card["last_seen_at"],
            heartbeat_days=heartbeat_days,
            now=now,
        )
        avg_weight = int(card.pop("_avg_price_weight"))
        avg_total = float(card.pop("_avg_price_total"))
        card["avg_price"] = (avg_total / avg_weight) if avg_weight > 0 else None
        card["stale_ratio"] = round((stale_count / listing_count * 100), 1) if listing_count else 0.0
        card["signal_label"] = signal["label"]
        card["signal_class"] = signal["class_name"]
        cards.append(card)
    cards.sort(key=lambda row: row["listing_count"], reverse=True)
    return cards


def build_top_models(
    session,
    *,
    business_domain: str | None,
    category_code: str | None = None,
    window_days: int,
    heartbeat_days: int,
    filtered_item_ids: set[str] | None,
) -> list[dict[str, Any]]:
    if filtered_item_ids is not None and not filtered_item_ids:
        return []

    now = datetime.now(UTC)
    window_limit = freshness_cutoff(window_days=window_days, now=now)
    active_limit = heartbeat_cutoff(heartbeat_days=heartbeat_days, now=now)
    model_expr = display_model_expression()
    stmt = (
        select(
            Item.business_domain,
            model_expr.label("model_name"),
            func.count(Item.id).label("listing_count"),
            func.count(func.distinct(Item.seller_profile_id)).label("seller_count"),
            func.avg(Item.current_price).label("avg_price"),
            func.max(Item.last_seen_at).label("last_seen_at"),
        )
        .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
        .where(
            Item.is_active.is_(True),
            Item.last_seen_at >= window_limit,
            Item.last_seen_at >= active_limit,
        )
        .group_by(Item.business_domain, model_expr)
        .order_by(desc("listing_count"), desc("seller_count"), desc("avg_price"))
        .limit(12)
    )
    stmt = _apply_visible_scope_filter(
        stmt,
        column=Item.business_domain,
        business_domain=business_domain,
        category_code=category_code,
    )
    if filtered_item_ids is not None:
        stmt = stmt.where(Item.item_id.in_(filtered_item_ids))

    rows = session.execute(stmt).all()
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        scope_code = resolve_category_code(row.business_domain)
        key = (scope_code, row.model_name)
        payload = merged.setdefault(
            key,
            {
                "business_domain": scope_code,
                "categoryCode": scope_code,
                "categoryName": display_label_for_scope(scope_code),
                "domain_label": display_label_for_scope(scope_code),
                "model_name": row.model_name,
                "listing_count": 0,
                "seller_count": 0,
                "avg_price": None,
                "_avg_price_total": 0.0,
                "_avg_price_weight": 0,
                "last_seen_at": None,
            },
        )
        listing_count = int(row.listing_count or 0)
        payload["listing_count"] += listing_count
        payload["seller_count"] += int(row.seller_count or 0)
        if row.avg_price is not None and listing_count > 0:
            payload["_avg_price_total"] += float(row.avg_price) * listing_count
            payload["_avg_price_weight"] += listing_count
        if row.last_seen_at is not None and (
            payload["last_seen_at"] is None or row.last_seen_at > payload["last_seen_at"]
        ):
            payload["last_seen_at"] = row.last_seen_at

    values = list(merged.values())
    for value in values:
        avg_weight = int(value.pop("_avg_price_weight"))
        avg_total = float(value.pop("_avg_price_total"))
        value["avg_price"] = (avg_total / avg_weight) if avg_weight > 0 else None
    values.sort(
        key=lambda row: (row["listing_count"], row["seller_count"], row["avg_price"] or 0),
        reverse=True,
    )
    return values[:12]


def build_recent_runs(session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(CrawlRun, CrawlTask.display_name, CrawlTask.task_key, CrawlTask.business_domain)
        .join(CrawlTask, CrawlTask.id == CrawlRun.task_id)
        .where(~CrawlTask.business_domain.in_(non_analytics_scope_codes()))
        .order_by(CrawlRun.started_at.desc())
        .limit(10)
    ).all()
    return [
        {
            "id": str(run.id),
            "display_name": display_name,
            "task_key": task_key,
            "business_domain": resolve_category_code(business_domain),
            "categoryCode": resolve_category_code(business_domain),
            "categoryName": display_label_for_scope(business_domain),
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "pages_succeeded": run.pages_succeeded,
            "pages_attempted": run.pages_attempted,
            "error_message": run.error_message,
        }
        for run, display_name, task_key, business_domain in rows
    ]


def is_probably_relevant(item: dict[str, Any]) -> bool:
    tokens = DOMAIN_TOKENS.get(item["business_domain"], [])
    haystack = " ".join(
        [
            item.get("title") or "",
            item.get("display_name") or "",
            item.get("source_keyword") or "",
        ]
    ).lower()
    return any(token.lower() in haystack for token in tokens)


def build_recent_items(
    session,
    *,
    business_domain: str | None,
    category_code: str | None = None,
    limit: int,
    window_days: int,
    heartbeat_days: int,
    filtered_item_ids: set[str] | None,
) -> list[dict[str, Any]]:
    if filtered_item_ids is not None and not filtered_item_ids:
        return []

    now = datetime.now(UTC)
    window_limit = freshness_cutoff(window_days=window_days, now=now)
    stmt = (
        select(Item, SellerProfile, CrawlTask.display_name, ItemSpecEnrichment)
        .outerjoin(SellerProfile, SellerProfile.id == Item.seller_profile_id)
        .join(CrawlTask, CrawlTask.id == Item.task_id)
        .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
        .where(
            Item.is_active.is_(True),
            Item.last_seen_at >= window_limit,
        )
        .order_by(Item.last_seen_at.desc(), Item.id.desc())
        .limit(max(limit * 6, 120))
    )
    stmt = _apply_visible_scope_filter(
        stmt,
        column=Item.business_domain,
        business_domain=business_domain,
        category_code=category_code,
    )
    if filtered_item_ids is not None:
        stmt = stmt.where(Item.item_id.in_(filtered_item_ids))

    rows = session.execute(stmt).all()
    serialized = []
    for item, seller, display_name, spec in rows:
        scope_code = resolve_category_code(item.business_domain)
        current_state = heartbeat_state(
            last_seen_at=item.last_seen_at,
            heartbeat_days=heartbeat_days,
            now=now,
        )
        serialized.append(
            {
                "item_id": item.item_id,
                "title": item.title,
                "business_domain": scope_code,
                "categoryCode": scope_code,
                "categoryName": display_label_for_scope(scope_code),
                "domain_label": display_label_for_scope(scope_code),
                "display_name": (
                    spec.model_name
                    if spec and spec.model_name
                    else item.normalized_model or item.normalized_model_family or item.source_keyword or "Unclassified"
                ),
                "price": item.current_price,
                "region": item.region,
                "publish_time": item.publish_time,
                "last_seen_at": item.last_seen_at,
                "seller_name": seller.seller_name if seller else None,
                "seller_id": seller.seller_id if seller else None,
                "listing_url": item.listing_url,
                "image_url": item.image_urls[0] if item.image_urls else None,
                "condition_tags": item.condition_tags or [],
                "has_video": item.has_video,
                "is_ad": item.is_ad,
                "spec_status": spec.status if spec else None,
                "spec_confidence": float(spec.confidence) if spec and spec.confidence is not None else None,
                "task_display_name": display_name,
                "source_keyword": item.source_keyword,
                "raw_response_id": str(item.current_raw_response_id) if item.current_raw_response_id else None,
                "heartbeat_state": current_state,
                "heartbeat_label": heartbeat_state_label(current_state),
                "heartbeat_class": heartbeat_state_class(current_state),
                "stale_days": stale_days(item.last_seen_at, now=now),
            }
        )
    preference_by_item_id = load_dashboard_listing_preferences(
        session,
        item_ids=[str(row["item_id"]) for row in serialized],
    )
    serialized = [
        {
            **row,
            "listing_preference": preference_by_item_id.get(str(row["item_id"])),
        }
        for row in serialized
        if preference_by_item_id.get(str(row["item_id"])) != "not_interested"
    ]
    relevant_ids = {row["item_id"] for row in serialized if is_probably_relevant(row)}
    prioritized = [row for row in serialized if row["item_id"] in relevant_ids]
    prioritized.extend(row for row in serialized if row["item_id"] not in relevant_ids)
    return prioritized[:limit]


def load_dashboard_listing_preferences(session, *, item_ids: list[str]) -> dict[str, str]:
    if not item_ids:
        return {}
    rows = session.execute(
        select(UserListingPreference.item_id, UserListingPreference.preference)
        .where(UserListingPreference.operator_id == "local")
        .where(UserListingPreference.source == "dashboard")
        .where(UserListingPreference.status == "active")
        .where(UserListingPreference.item_id.in_(tuple(item_ids)))
    ).all()
    return {str(item_id): str(preference) for item_id, preference in rows}


def summarize_daily_snapshots(
    *,
    snapshots: list[dict[str, Any]],
    max_points: int = 30,
) -> list[dict[str, Any]]:
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        snapshot_at = snapshot.get("snapshot_at")
        if snapshot_at is None:
            continue
        grouped[snapshot_at.astimezone(UTC).date()].append(snapshot)

    candles: list[dict[str, Any]] = []
    previous_median: float | None = None
    for day in sorted(grouped):
        entries = sorted(grouped[day], key=lambda value: value["snapshot_at"])
        collapsed_by_item: dict[str, list[float]] = defaultdict(list)
        for entry in entries:
            if entry.get("price") is None:
                continue
            collapsed_by_item[str(entry["item_id"])].append(float(entry["price"]))
        if not collapsed_by_item:
            continue
        collapsed_records = []
        for item_id, prices in collapsed_by_item.items():
            item_title = next(
                (entry["title"] for entry in entries if str(entry["item_id"]) == item_id),
                item_id,
            )
            collapsed_records.append(
                {
                    "seller_key": item_id,
                    "item_id": item_id,
                    "title": item_title,
                    "price": statistics.median(prices),
                }
            )
        cleaned_records, _ = filter_outlier_price_records(collapsed_records)
        cleaned_prices = sorted(float(record["price"]) for record in cleaned_records if record.get("price") is not None)
        if not cleaned_prices:
            continue
        median_price = percentile(cleaned_prices, 0.50)
        p25_price = percentile(cleaned_prices, 0.25)
        p75_price = percentile(cleaned_prices, 0.75)
        if median_price is None or p25_price is None or p75_price is None:
            continue
        open_price = previous_median if previous_median is not None else median_price
        close_price = median_price
        high_price = max(p75_price, open_price, close_price)
        low_price = min(p25_price, open_price, close_price)
        candles.append(
            {
                "date": day,
                "date_label": day.strftime("%m-%d"),
                "open_price": round(open_price, 2),
                "close_price": round(close_price, 2),
                "high_price": round(high_price, 2),
                "low_price": round(low_price, 2),
                "mid_price": round(median_price, 2),
                "band_low_price": round(p25_price, 2),
                "band_high_price": round(p75_price, 2),
                "sample_count": len(cleaned_prices),
                "snapshot_count": sum(len(prices) for prices in collapsed_by_item.values()),
            }
        )
        previous_median = median_price

    if len(candles) <= max_points:
        return candles
    return candles[-max_points:]


def _chart_y(
    *,
    price: float,
    min_price: float,
    max_price: float,
    plot_top: float,
    plot_height: float,
) -> float:
    span = max(max_price - min_price, 1.0)
    return plot_top + ((max_price - price) / span) * plot_height


def _signed_currency(value: float) -> str:
    if value > 0:
        return f"+{format_currency(value)}"
    if value < 0:
        return f"-{format_currency(abs(value))}"
    return format_currency(value)


def _normalize_template_key(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _downgrade_trend_availability_to_reference_only(
    availability: dict[str, Any],
) -> dict[str, Any]:
    downgraded = dict(availability or {})
    evidence = dict(downgraded.get("pricingEvidence") or {})
    summary = dict(downgraded.get("pricingSummary") or {})
    summary["readinessSummary"] = "仅参考：历史快照缺少模板归属，趋势暂不提供指导级口径"
    downgraded.update(
        {
            "availabilityTier": "reference_only",
            "pricingAvailable": True,
            "pricingBlockReason": None,
            "pricingBlockReasonLabel": None,
            "pricingEvidence": evidence,
            "pricingSummary": summary,
        }
    )
    return downgraded


def _date_tick_indices(count: int, desired: int = 4) -> list[int]:
    if count <= 0:
        return []
    if count <= desired:
        return list(range(count))
    denominator = max(desired - 1, 1)
    return sorted({round(index * (count - 1) / denominator) for index in range(desired)})


def _svg_path(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    commands = [f"M {points[0][0]:.2f} {points[0][1]:.2f}"]
    commands.extend(f"L {x:.2f} {y:.2f}" for x, y in points[1:])
    return " ".join(commands)


def _svg_band_path(
    *,
    upper_points: list[tuple[float, float]],
    lower_points: list[tuple[float, float]],
) -> str:
    if not upper_points or not lower_points:
        return ""
    if len(upper_points) == 1 and len(lower_points) == 1:
        x = upper_points[0][0]
        top = upper_points[0][1]
        bottom = lower_points[0][1]
        return f"M {x - 2:.2f} {top:.2f} L {x + 2:.2f} {top:.2f} L {x + 2:.2f} {bottom:.2f} L {x - 2:.2f} {bottom:.2f} Z"
    commands = [f"M {upper_points[0][0]:.2f} {upper_points[0][1]:.2f}"]
    commands.extend(f"L {x:.2f} {y:.2f}" for x, y in upper_points[1:])
    commands.extend(f"L {x:.2f} {y:.2f}" for x, y in reversed(lower_points))
    commands.append("Z")
    return " ".join(commands)


def select_trend_focus_groups(
    *,
    pricing_records: list[dict[str, Any]],
    business_domain: str | None,
) -> list[dict[str, Any]]:
    rows = aggregate_pricing_view(
        records=pricing_records,
        view="product",
        min_sample_points=TREND_MIN_GROUP_SAMPLE_COUNT,
    )
    candidates = [
        row
        for row in rows
        if row["seller_sample_count"] >= TREND_MIN_GROUP_SAMPLE_COUNT
        and row["listing_count"] >= TREND_MIN_GROUP_SAMPLE_COUNT
    ]
    if not candidates:
        candidates = rows

    candidates.sort(
        key=lambda row: (
            row["seller_sample_count"],
            row["listing_count"],
            row["reliability_score"],
            row.get("normal_margin_pct") or 0,
            row["label"],
        ),
        reverse=True,
    )

    if business_domain:
        return candidates[:TREND_CARD_CANDIDATE_LIMIT_FOR_SELECTED_DOMAIN]

    selected: list[dict[str, Any]] = []
    domain_counts: dict[str, int] = defaultdict(int)
    for row in candidates:
        domain = row["business_domain"]
        if domain_counts[domain] >= TREND_CARD_CANDIDATE_LIMIT_PER_DOMAIN:
            continue
        selected.append(row)
        domain_counts[domain] += 1
    return selected


def summarize_trend_quality(candles: list[dict[str, Any]]) -> dict[str, Any]:
    if not candles:
        return {
            "latest_sample_count": 0,
            "recent_average_sample_count": 0.0,
            "trend_quality_ok": False,
        }
    recent_candles = candles[-3:]
    latest_sample_count = int(candles[-1]["sample_count"])
    recent_average_sample_count = statistics.mean(
        int(candle["sample_count"]) for candle in recent_candles
    )
    meets_minimum = (
        len(candles) >= TREND_MIN_DAY_COUNT
        and latest_sample_count >= TREND_MIN_LATEST_SAMPLE_COUNT
        and recent_average_sample_count >= TREND_MIN_RECENT_AVG_SAMPLE_COUNT
    )
    return {
        "latest_sample_count": latest_sample_count,
        "recent_average_sample_count": round(recent_average_sample_count, 1),
        "trend_quality_ok": meets_minimum,
    }


def select_final_trend_cards(
    *,
    cards: list[dict[str, Any]],
    business_domain: str | None,
) -> list[dict[str, Any]]:
    ranked_cards = sorted(
        cards,
        key=lambda card: (
            1 if card["trend_quality_ok"] else 0,
            card["recent_average_sample_count"],
            card["latest_sample_count"],
            card["seller_sample_count"],
            card["reliability_score"],
            card["day_count"],
            card["label"],
        ),
        reverse=True,
    )

    if business_domain:
        quality_cards = [card for card in ranked_cards if card["trend_quality_ok"]]
        return (quality_cards or ranked_cards)[:TREND_CARD_LIMIT_FOR_SELECTED_DOMAIN]

    selected: list[dict[str, Any]] = []
    domain_counts: dict[str, int] = defaultdict(int)
    domain_seen_quality: dict[str, bool] = defaultdict(bool)
    for card in ranked_cards:
        domain = card["business_domain"]
        if domain_counts[domain] >= TREND_CARD_LIMIT_PER_DOMAIN:
            continue
        if not card["trend_quality_ok"] and domain_seen_quality[domain]:
            continue
        selected.append(card)
        domain_counts[domain] += 1
        domain_seen_quality[domain] = domain_seen_quality[domain] or card["trend_quality_ok"]
    return selected


def build_domain_trend_chart(
    *,
    domain_name: str,
    candles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candles:
        return None

    min_low = min(float(candle["low_price"]) for candle in candles)
    max_high = max(float(candle["high_price"]) for candle in candles)
    price_span = max(max_high - min_low, 1.0)
    price_padding = max(price_span * 0.08, max_high * 0.03, 1.0)
    chart_min = max(min_low - price_padding, 0)
    chart_max = max_high + price_padding

    plot_left = TREND_CHART_PADDING["left"]
    plot_top = TREND_CHART_PADDING["top"]
    plot_width = TREND_CHART_WIDTH - TREND_CHART_PADDING["left"] - TREND_CHART_PADDING["right"]
    plot_height = TREND_CHART_HEIGHT - TREND_CHART_PADDING["top"] - TREND_CHART_PADDING["bottom"]

    step = 0.0 if len(candles) == 1 else plot_width / (len(candles) - 1)

    rendered_points: list[dict[str, Any]] = []
    for index, candle in enumerate(candles):
        center_x = plot_left + (plot_width / 2 if len(candles) == 1 else index * step)
        mid_price = float(candle["mid_price"])
        band_high_price = float(candle["band_high_price"])
        band_low_price = float(candle["band_low_price"])
        mid_y = _chart_y(
            price=mid_price,
            min_price=chart_min,
            max_price=chart_max,
            plot_top=plot_top,
            plot_height=plot_height,
        )
        band_high_y = _chart_y(
            price=band_high_price,
            min_price=chart_min,
            max_price=chart_max,
            plot_top=plot_top,
            plot_height=plot_height,
        )
        band_low_y = _chart_y(
            price=band_low_price,
            min_price=chart_min,
            max_price=chart_max,
            plot_top=plot_top,
            plot_height=plot_height,
        )
        rendered_points.append(
            {
                **candle,
                "center_x": round(center_x, 2),
                "mid_y": round(mid_y, 2),
                "band_high_y": round(band_high_y, 2),
                "band_low_y": round(band_low_y, 2),
                "tooltip": (
                    f'{candle["date_label"]} 中位 {format_currency(mid_price)} / '
                    f'价格带 {format_currency(band_low_price)} ~ {format_currency(band_high_price)} / '
                    f'样本 {candle["sample_count"]}'
                ),
            }
        )

    line_points = [(float(point["center_x"]), float(point["mid_y"])) for point in rendered_points]
    upper_band_points = [(float(point["center_x"]), float(point["band_high_y"])) for point in rendered_points]
    lower_band_points = [(float(point["center_x"]), float(point["band_low_y"])) for point in rendered_points]
    line_path = _svg_path(line_points)
    band_path = _svg_band_path(
        upper_points=upper_band_points,
        lower_points=lower_band_points,
    )
    upper_band_path = _svg_path(upper_band_points)
    lower_band_path = _svg_path(lower_band_points)

    price_ticks = []
    for index in range(TREND_PRICE_TICKS):
        ratio = index / max(TREND_PRICE_TICKS - 1, 1)
        price_value = chart_max - (chart_max - chart_min) * ratio
        y = plot_top + plot_height * ratio
        price_ticks.append(
            {
                "y": round(y, 2),
                "label": format_currency(price_value),
            }
        )

    date_ticks = []
    for index in _date_tick_indices(len(rendered_points)):
        candle = rendered_points[index]
        date_ticks.append(
            {
                "x": candle["center_x"],
                "label": candle["date_label"],
            }
        )

    first_candle = rendered_points[0]
    last_candle = rendered_points[-1]
    change_value = float(last_candle["mid_price"]) - float(first_candle["mid_price"])
    base_price = float(first_candle["mid_price"]) or 1.0
    change_pct = change_value / base_price * 100
    volatility_pct = (
        (float(last_candle["band_high_price"]) - float(last_candle["band_low_price"]))
        / max(float(last_candle["mid_price"]) or 1.0, 1.0)
        * 100
    )
    direction_class = "up" if change_value > 0 else "down" if change_value < 0 else "flat"

    return {
        "chart_width": TREND_CHART_WIDTH,
        "chart_height": TREND_CHART_HEIGHT,
        "trend_points": rendered_points,
        "trend_line_path": line_path,
        "trend_band_path": band_path,
        "trend_upper_path": upper_band_path,
        "trend_lower_path": lower_band_path,
        "price_ticks": price_ticks,
        "date_ticks": date_ticks,
        "latest_close": float(last_candle["mid_price"]),
        "latest_sample_count": int(last_candle["sample_count"]),
        "latest_range_label": (
            f'{format_currency(float(last_candle["band_low_price"]))} ~ {format_currency(float(last_candle["band_high_price"]))}'
        ),
        "change_label": f'{_signed_currency(change_value)} / {change_pct:+.1f}%',
        "volatility_label": f"价带宽度 {volatility_pct:.1f}%",
        "change_class": direction_class,
        "day_count": len(rendered_points),
        "disclaimer": "按日级价格带汇总：主线表示当天中位价，虚线表示当天中间 50% 样本区间上下沿。",
        "aria_label": f"{domain_name} 近 {len(rendered_points)} 天价格波动折线图",
    }


def build_domain_trend_cards(
    session,
    *,
    business_domain: str | None,
    category_code: str | None = None,
    window_days: int,
    heartbeat_days: int,
    max_points: int = 30,
    pricing_records: list[dict[str, Any]] | None = None,
    pricing_contract: dict[str, Any] | None = None,
    filtered_item_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if filtered_item_ids is not None and not filtered_item_ids:
        return []

    if pricing_records is None:
        pricing_records = load_pricing_records(
            session=session,
            business_domain=business_domain,
            category_code=category_code,
            freshness_days=window_days,
            heartbeat_days=heartbeat_days,
        )
    if not pricing_records:
        return []

    focus_groups = select_trend_focus_groups(
        pricing_records=pricing_records,
        business_domain=category_code or business_domain,
    )
    if not focus_groups:
        return []

    template_trend_enabled = is_price_template_trend_enabled()
    selected_template_key = (
        _normalize_template_key((pricing_contract or {}).get("templateKeyPreview"))
        if template_trend_enabled
        else None
    )
    selected_group_keys = {
        (row["business_domain"], row["product_label"])
        for row in focus_groups
    }
    tracked_items = _tracked_items_from_pricing_records(
        pricing_records=pricing_records,
        selected_group_keys=selected_group_keys,
        selected_template_key=selected_template_key,
        filtered_item_ids=filtered_item_ids,
    )
    if not tracked_items:
        tracked_items = _load_tracked_items_for_trend_groups(
            session,
            business_domain=business_domain,
            category_code=category_code,
            selected_group_keys=selected_group_keys,
            selected_template_key=selected_template_key,
            filtered_item_ids=filtered_item_ids,
        )
    if not tracked_items:
        return []

    stmt = (
        select(
            Item.item_id.label("item_id"),
            Item.business_domain.label("business_domain"),
            ItemSnapshot.snapshot_at.label("snapshot_at"),
            ItemSnapshot.price.label("price"),
            ItemSnapshot.extra_json.label("extra_json"),
        )
        .join(Item, Item.id == ItemSnapshot.item_id_ref)
        .where(
            Item.item_id.in_(tuple(tracked_items)),
            ItemSnapshot.price.is_not(None),
            ItemSnapshot.price > 0,
        )
        .order_by(Item.business_domain, ItemSnapshot.snapshot_at.asc(), ItemSnapshot.id.asc())
    )

    rows = session.execute(stmt).all()
    snapshots_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    tagged_snapshot_counts: dict[tuple[str, str], int] = defaultdict(int)
    fallback_snapshot_counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        item_context = tracked_items.get(row.item_id)
        if item_context is None:
            continue
        group_key = (item_context["business_domain"], item_context["product_label"])
        snapshot_extra_json = dict(getattr(row, "extra_json", None) or {})
        snapshot_template_key = _normalize_template_key(snapshot_extra_json.get("template_key"))
        if selected_template_key:
            if snapshot_template_key:
                if snapshot_template_key != selected_template_key:
                    continue
                tagged_snapshot_counts[group_key] += 1
            else:
                if item_context.get("template_key") != selected_template_key:
                    continue
                fallback_snapshot_counts[group_key] += 1
        normalized_price = normalize_market_price(
            row.price,
            business_domain=row.business_domain,
            model_family=item_context.get("product_line"),
        )
        if normalized_price is None or normalized_price <= 0:
            continue
        snapshots_by_group[group_key].append(
            {
                "item_id": row.item_id,
                "title": item_context["title"],
                "snapshot_at": row.snapshot_at,
                "price": float(normalized_price),
            }
        )

    cards: list[dict[str, Any]] = []
    template_complete = bool(((pricing_contract or {}).get("templateCompleteness") or {}).get("isComplete"))
    for group in focus_groups:
        group_key = (group["business_domain"], group["product_label"])
        candles = summarize_daily_snapshots(
            snapshots=snapshots_by_group.get(group_key, []),
            max_points=max_points,
        )
        chart = build_domain_trend_chart(
            domain_name=group["product_label"],
            candles=candles,
        )
        if chart is None:
            continue
        quality = summarize_trend_quality(candles)
        pricing_availability = evaluate_pricing_row_availability(group, template_complete=template_complete)
        tagged_snapshot_count = int(tagged_snapshot_counts.get(group_key, 0))
        fallback_snapshot_count = int(fallback_snapshot_counts.get(group_key, 0))
        transition_fallback_used = bool(template_trend_enabled and selected_template_key and fallback_snapshot_count > 0)
        if transition_fallback_used and pricing_availability.get("availabilityTier") == "guidance_ready":
            pricing_availability = _downgrade_trend_availability_to_reference_only(pricing_availability)
        history_span_days = 0
        if candles:
            history_span_days = max(
                (candles[-1]["date"] - candles[0]["date"]).days + 1,
                len(candles),
            )
        cards.append(
            {
                "business_domain": group["business_domain"],
                "domain_label": domain_label(group["business_domain"]),
                "label": group["product_label"],
                "templateKey": selected_template_key,
                "window_days": history_span_days or window_days,
                "listing_count": group["listing_count"],
                "seller_sample_count": group["seller_sample_count"],
                "reliability_score": group["reliability_score"],
                "templateSnapshotTaggedCount": tagged_snapshot_count,
                "templateSnapshotFallbackCount": fallback_snapshot_count,
                "templateSnapshotCoverageMode": (
                    "full_tagged"
                    if selected_template_key and fallback_snapshot_count == 0 and tagged_snapshot_count > 0
                    else "fallback_item_template"
                    if selected_template_key and fallback_snapshot_count > 0
                    else "unscoped"
                ),
                "pricingAvailability": pricing_availability,
                "pricingAvailabilitySummary": dict(pricing_availability.get("pricingSummary") or {}),
                **quality,
                **chart,
            }
        )

    return select_final_trend_cards(
        cards=cards,
        business_domain=category_code or business_domain,
    )


def _tracked_items_from_pricing_records(
    *,
    pricing_records: list[dict[str, Any]],
    selected_group_keys: set[tuple[str, str]],
    selected_template_key: str | None,
    filtered_item_ids: set[str] | None,
) -> dict[str, dict[str, Any]]:
    tracked_items: dict[str, dict[str, Any]] = {}
    for record in pricing_records:
        item_id = str(record.get("item_id") or "").strip()
        business_domain = str(record.get("business_domain") or "").strip()
        product_label = str(record.get("product_label") or "").strip()
        if not item_id or not business_domain or not product_label:
            continue
        if filtered_item_ids is not None and item_id not in filtered_item_ids:
            continue
        if (business_domain, product_label) not in selected_group_keys:
            continue

        record_template_key = None
        if selected_template_key:
            template_snapshot = build_pricing_record_template_snapshot(
                business_domain=record.get("business_domain"),
                record=record,
            )
            record_template_key = _normalize_template_key(template_snapshot.get("templateKey"))
            if record_template_key != selected_template_key:
                continue

        tracked_items[item_id] = {
            **record,
            "template_key": record_template_key,
        }

    return tracked_items


def _load_tracked_items_for_trend_groups(
    session,
    *,
    business_domain: str | None,
    category_code: str | None,
    selected_group_keys: set[tuple[str, str]],
    selected_template_key: str | None,
    filtered_item_ids: set[str] | None,
) -> dict[str, dict[str, Any]]:
    tracked_items: dict[str, dict[str, Any]] = {}
    history_stmt = (
        select(Item, ItemSpecEnrichment)
        .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
        .where(Item.is_active.is_(True))
    )
    history_stmt = _apply_visible_scope_filter(
        history_stmt,
        column=Item.business_domain,
        business_domain=business_domain,
        category_code=category_code,
    )
    if filtered_item_ids is not None:
        history_stmt = history_stmt.where(Item.item_id.in_(tuple(filtered_item_ids)))

    for item, spec in session.execute(history_stmt).all():
        record = resolve_pricing_record(item, spec)
        if record is None:
            continue
        if filtered_item_ids is not None and record["item_id"] not in filtered_item_ids:
            continue
        if (record["business_domain"], record["product_label"]) not in selected_group_keys:
            continue

        record_template_key = None
        if selected_template_key:
            template_snapshot = build_pricing_record_template_snapshot(
                business_domain=record.get("business_domain"),
                record=record,
            )
            record_template_key = _normalize_template_key(template_snapshot.get("templateKey"))
            if record_template_key != selected_template_key:
                continue

        tracked_items[record["item_id"]] = {
            **record,
            "template_key": record_template_key,
        }

    return tracked_items


def build_item_detail(session, item_id: str) -> dict[str, Any] | None:
    record = session.execute(
        select(Item, SellerProfile, CrawlTask.display_name, ItemSpecEnrichment)
        .outerjoin(SellerProfile, SellerProfile.id == Item.seller_profile_id)
        .join(CrawlTask, CrawlTask.id == Item.task_id)
        .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
        .where(Item.item_id == item_id)
    ).first()
    if not record:
        return None

    item, seller, task_display_name, spec = record
    snapshots = session.execute(
        select(ItemSnapshot)
        .where(ItemSnapshot.item_id_ref == item.id)
        .order_by(ItemSnapshot.snapshot_at.desc())
        .limit(20)
    ).scalars()
    raw_response = session.get(RawResponse, item.current_raw_response_id) if item.current_raw_response_id else None

    return {
        "item": {
            "item_id": item.item_id,
            "title": item.title,
            "business_domain": resolve_category_code(item.business_domain),
            "categoryCode": resolve_category_code(item.business_domain),
            "categoryName": display_label_for_scope(item.business_domain),
            "domain_label": display_label_for_scope(item.business_domain),
            "price": item.current_price,
            "region": item.region,
            "publish_time": item.publish_time,
            "first_seen_at": item.first_seen_at,
            "last_seen_at": item.last_seen_at,
            "listing_url": item.listing_url,
            "image_urls": item.image_urls or [],
            "condition_tags": item.condition_tags or [],
            "normalized_brand": item.normalized_brand,
            "normalized_model_family": item.normalized_model_family,
            "normalized_model": item.normalized_model,
            "normalized_chip": item.normalized_chip,
            "normalized_memory_gb": item.normalized_memory_gb,
            "normalized_storage_gb": item.normalized_storage_gb,
            "source_keyword": item.source_keyword,
            "task_display_name": task_display_name,
            "raw_response_id": str(item.current_raw_response_id) if item.current_raw_response_id else None,
            "has_video": item.has_video,
            "is_ad": item.is_ad,
        },
        "spec": {
            "status": spec.status,
            "confidence": spec.confidence,
            "extractor_type": spec.extractor_type,
            "product_line": spec.product_line,
            "model_name": spec.model_name,
            "generation": spec.generation,
            "case_size_mm": spec.case_size_mm,
            "is_solar": spec.is_solar,
            "display_type": spec.display_type,
            "screen_size_in": spec.screen_size_in,
            "chip_family": spec.chip_family,
            "cpu_cores": spec.cpu_cores,
            "gpu_cores": spec.gpu_cores,
            "memory_gb": spec.memory_gb,
            "storage_gb": spec.storage_gb,
            "edition_tags": spec.edition_tags or [],
            "needs_review": spec.needs_review,
        }
        if spec
        else None,
        "seller": {
            "seller_name": seller.seller_name if seller else None,
            "seller_id": seller.seller_id if seller else None,
            "region": seller.region if seller else None,
        },
        "snapshots": [
            {
                "snapshot_at": snapshot.snapshot_at,
                "price": snapshot.price,
                "region": snapshot.region,
                "publish_time": snapshot.publish_time,
                "condition_tags": snapshot.condition_tags or [],
                "extra_json": snapshot.extra_json or {},
            }
            for snapshot in snapshots
        ],
        "raw_response_body": json.dumps(raw_response.response_body, ensure_ascii=False, indent=2)
        if raw_response
        else None,
    }
