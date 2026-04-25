from __future__ import annotations

import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from .category_compat import (
    compatible_scope_keys,
    display_label_for_scope,
    is_apple_computer_scope,
    is_garmin_watch_scope,
    non_analytics_scope_codes,
    resolve_category_code,
    token_aliases_for_scope,
)
from .compat import UTC
from .db import session_scope
from .application.services.pricing_domain import (
    APPLE_ANALYSIS_PRODUCT_LINES,
    GARMIN_ANALYSIS_PRODUCT_LINES,
    MIN_ACTIONABLE_PROFIT_AMOUNT,
    MIN_ACTIONABLE_PROFIT_FLOOR_RATIO,
    MIN_ACTIONABLE_PROFIT_MARGIN_PCT,
    classify_opportunity_tier,
    compute_profit_margin_pct,
    compute_opportunity_score,
    minimum_actionable_profit_amount,
    percentile,
    reliability_tier,
    round_money,
    sort_last_seen,
    spec_dimension_payload,
)
from .application.services.pricing_eligibility import (
    MIN_SPEC_CONFIDENCE_FOR_PRICING,
    NON_PRICING_SPEC_EXTRACTOR_TYPES,
    PRICING_GATE_REASON_LABELS,
    build_pricing_eligibility_snapshot,
    is_item_eligible_for_pricing,
    pricing_gate_exclusion_reason,
    spec_confidence_passes_pricing_gate,
    usable_spec_for_pricing,
)
from .application.services.spec_schema_snapshots import (
    evaluate_pricing_record_schema,
    load_active_spec_schema_for_pricing_with_session,
)
from .models import Item, ItemIngestRejection, ItemSpecEnrichment
from .normalizers import normalize_market_price
from .specs import extract_rule_specs, lens_title_is_non_target_body_listing

DOMAIN_ANALYSIS_TOKENS = {
    "camera_interchangeable_lens": [*token_aliases_for_scope("camera_interchangeable_lens")],
    "camera_body": [*token_aliases_for_scope("camera_body")],
    "graphics_card": [*token_aliases_for_scope("graphics_card")],
    "phone": [*token_aliases_for_scope("phone")],
    "garmin": [*token_aliases_for_scope("garmin"), "煮苧", "tactix", "enduro", "descent"],
    "garmin_watch": [*token_aliases_for_scope("garmin_watch"), "煮苧", "tactix", "enduro", "descent"],
    "apple_m_series": [*token_aliases_for_scope("apple_m_series"), "道惚"],
    "apple_computer": [*token_aliases_for_scope("apple_computer"), "道惚"],
    "apple_airpods": [*token_aliases_for_scope("apple_airpods")],
}

APPLE_CHIP_FAMILY_RE = re.compile(
    r"\b(m\d+)(?:\s*(pro|max|ultra))?\b",
    re.IGNORECASE,
)
APPLE_SCREEN_SIZE_BUCKETS: dict[str, tuple[Decimal, ...]] = {
    "MacBook Air": (Decimal("13"), Decimal("15")),
    "MacBook Pro": (Decimal("13"), Decimal("14"), Decimal("16")),
}
APPLE_SCREEN_SIZE_TOLERANCE: dict[str, Decimal] = {
    "MacBook Air": Decimal("0.75"),
    "MacBook Pro": Decimal("0.55"),
}

WANTED_TITLE_PATTERNS = (
    re.compile(r"^\s*[【\[]?\s*收(?:[】\]]|[\s!！])?", re.IGNORECASE),
    re.compile(r"^\s*求购", re.IGNORECASE),
    re.compile(r"^\s*诚收", re.IGNORECASE),
)
WANTED_TITLE_SUBSTRINGS = (
    "收一台",
    "诚心收",
    "仅收",
    "求购",
    "抵押",
)
BUYBACK_TITLE_PATTERNS = (
    re.compile(r"高价回收", re.IGNORECASE),
    re.compile(r"现金回收", re.IGNORECASE),
    re.compile(r"回收(芯片|ic|电子元器件|佳明|garmin|mac|macbook|电脑|笔记本)", re.IGNORECASE),
)
SOLD_TITLE_PATTERNS = (
    re.compile(r"^\s*[（(]已出[）)]", re.IGNORECASE),
    re.compile(r"^\s*[（(]已售[）)]", re.IGNORECASE),
)
COMMERCIAL_LISTING_STRONG_TOKENS = (
    "详情咨询客服",
    "联系客服",
    "咨询客服",
    "客户专拍",
    "型号齐全",
    "支持闪送",
    "当日达",
    "顺丰特快",
    "活动来袭",
    "预定",
    "验货报告",
    "只要在上架的就是有货",
    "可开发票",
    "全国联保",
)
COMMERCIAL_LISTING_HINT_TOKENS = (
    "全新未拆",
    "全新现货",
    "未拆封",
    "国行正品",
    "原价",
    "包邮到家",
    "顺丰包邮",
    "官方验货",
    "支持自提",
    "当天拍当天发货",
    "当天发货",
    "不议价",
)
COMMERCIAL_LISTING_STANDALONE_TOKENS = (
    "客户专拍",
    "详情咨询客服",
    "联系客服",
    "型号齐全",
    "验货报告",
    "只要在上架的就是有货",
)
GARMIN_WATCHFACE_SERVICE_TOKENS = (
    "解锁佳明表盘",
    "来图定制",
    "安装需要用电脑",
    "表盘定制",
)
GARMIN_ACCESSORY_SERVICE_TOKENS = (
    "心率带",
    "传感器",
    "码表",
    "小绿豆",
)
GARMIN_BAND_ACCESSORY_TOKENS = (
    "表带",
    "腕带",
    "表节",
    "钢带",
)
GARMIN_BAND_ACCESSORY_HINT_TOKENS = (
    "适用",
    "适配",
    "适合",
    "专用",
    "兼容",
    "配件",
    "快拆",
    "宽度",
    "22mm",
    "26mm",
    "接口",
    "原包装未拆",
    "买手表送的",
    "仅支持顺丰到付",
    "假一赔万",
    "尼龙表带",
    "编织表带",
    "织物表带",
    "硅胶表带",
    "钛金属表带",
    "延长表节",
)
GARMIN_LOW_PRICE_ACCESSORY_TOKENS = (
    "表盘",
    "新表盘",
    "动画表盘",
    "创意表盘",
    "趣味表盘",
    "中文表盘",
    "充电线",
    "数据线",
    "保护圈",
)
GARMIN_LOW_PRICE_PLACEHOLDER_TOKENS = (
    "批发价",
    "官方价",
    "官方质保",
    "国行正品",
    "原装正品",
    "高端系列",
    "全新腕表",
)
GARMIN_LOW_PRICE_PLACEHOLDER_DAMAGE_TOKENS = (
    "故障",
    "坏",
    "配件",
    "划痕",
    "磕碰",
    "成色垃圾",
    "不开机",
    "电池坏",
)
@dataclass(frozen=True, slots=True)
class PricingScope:
    requested_scope: str | None
    category_code: str | None
    legacy_business_domain: str | None
    scope_keys: tuple[str, ...]


def resolve_pricing_scope(
    *,
    business_domain: str | None = None,
    category_code: str | None = None,
) -> PricingScope:
    requested_scope = _requested_scope_key(business_domain=business_domain, category_code=category_code)
    if not requested_scope:
        return PricingScope(
            requested_scope=None,
            category_code=None,
            legacy_business_domain=None,
            scope_keys=(),
        )
    scope_keys = compatible_scope_keys(requested_scope)
    canonical_code = resolve_category_code(requested_scope)
    legacy_business_domain = next((key for key in scope_keys if key != canonical_code), canonical_code)
    return PricingScope(
        requested_scope=requested_scope,
        category_code=canonical_code or None,
        legacy_business_domain=legacy_business_domain or None,
        scope_keys=scope_keys,
    )


def build_spec_summary(
    *,
    business_domain: str | None = None,
    limit: int,
    category_code: str | None = None,
) -> list[dict[str, Any]]:
    rows = build_pricing_views(
        business_domain=business_domain,
        category_code=category_code,
        freshness_days=30,
        min_sample_points=4,
    )["spec"]
    return rows[:limit]


def build_model_discovery(
    *,
    business_domain: str | None = None,
    category_code: str | None = None,
    freshness_days: int = 30,
    min_sample_points: int = 4,
) -> list[dict[str, Any]]:
    views = build_pricing_views(
        business_domain=business_domain,
        category_code=category_code,
        freshness_days=freshness_days,
        min_sample_points=min_sample_points,
    )
    rows: list[dict[str, Any]] = []
    for view_name, view_rows in views.items():
        for row in view_rows:
            rows.append({"view": view_name, **row})
    return rows


def build_pricing_views(
    *,
    business_domain: str | None = None,
    category_code: str | None = None,
    freshness_days: int,
    min_sample_points: int,
) -> dict[str, list[dict[str, Any]]]:
    records = load_pricing_records(
        business_domain=business_domain,
        category_code=category_code,
        freshness_days=freshness_days,
    )
    return {
        "brand": aggregate_pricing_view(records=records, view="brand", min_sample_points=min_sample_points),
        "product": aggregate_pricing_view(records=records, view="product", min_sample_points=min_sample_points),
        "spec": aggregate_pricing_view(records=records, view="spec", min_sample_points=min_sample_points),
    }


def load_pricing_records(
    *,
    business_domain: str | None = None,
    category_code: str | None = None,
    freshness_days: int,
    heartbeat_days: int | None = None,
    session=None,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=max(freshness_days, 1))
    heartbeat_cutoff = None
    if heartbeat_days is not None:
        heartbeat_cutoff = now - timedelta(days=max(heartbeat_days, 1))
    if session is None:
        with session_scope() as db_session:
            return _load_pricing_records_from_session(
                session=db_session,
                business_domain=business_domain,
                category_code=category_code,
                cutoff=cutoff,
                heartbeat_cutoff=heartbeat_cutoff,
            )
    return _load_pricing_records_from_session(
        session=session,
        business_domain=business_domain,
        category_code=category_code,
        cutoff=cutoff,
        heartbeat_cutoff=heartbeat_cutoff,
    )


def build_pricing_gate_summary(
    *,
    business_domain: str | None = None,
    category_code: str | None = None,
    freshness_days: int,
    heartbeat_days: int | None = None,
    pricing_pool_count: int | None = None,
    session=None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=max(freshness_days, 1))
    heartbeat_cutoff = None
    if heartbeat_days is not None:
        heartbeat_cutoff = now - timedelta(days=max(heartbeat_days, 1))
    if session is None:
        with session_scope() as db_session:
            rows = _load_pricing_candidate_rows_from_session(
                session=db_session,
                business_domain=business_domain,
                category_code=category_code,
                cutoff=cutoff,
                heartbeat_cutoff=heartbeat_cutoff,
            )
    else:
        rows = _load_pricing_candidate_rows_from_session(
            session=session,
            business_domain=business_domain,
            category_code=category_code,
            cutoff=cutoff,
            heartbeat_cutoff=heartbeat_cutoff,
        )
    return summarize_pricing_gate(
        items=[item for item, _spec in rows],
        pricing_pool_count=pricing_pool_count,
    )


def _build_pricing_candidate_stmt(
    *,
    business_domain: str | None,
    category_code: str | None,
    cutoff: datetime,
    heartbeat_cutoff: datetime | None,
):
    stmt = (
        select(Item, ItemSpecEnrichment)
        .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
        .where(
            Item.is_active.is_(True),
            Item.current_price.is_not(None),
            Item.current_price > 0,
            Item.is_ad.is_(False),
            Item.is_auction.is_(False),
            Item.last_seen_at >= cutoff,
            ~(
                select(ItemIngestRejection.id)
                .where(ItemIngestRejection.source_platform == Item.source_platform)
                .where(ItemIngestRejection.item_id == Item.item_id)
                .exists()
            ),
        )
        .order_by(Item.last_seen_at.desc(), Item.id.desc())
    )
    scope_keys = _scope_keys_for_filter(business_domain=business_domain, category_code=category_code)
    if scope_keys:
        stmt = stmt.where(Item.business_domain.in_(scope_keys))
    else:
        stmt = stmt.where(~Item.business_domain.in_(non_analytics_scope_codes()))
    if heartbeat_cutoff is not None:
        stmt = stmt.where(Item.last_seen_at >= heartbeat_cutoff)
    return stmt


def _load_pricing_candidate_rows_from_session(
    *,
    session,
    business_domain: str | None,
    category_code: str | None,
    cutoff: datetime,
    heartbeat_cutoff: datetime | None,
) -> list[tuple[Item, ItemSpecEnrichment | None]]:
    stmt = _build_pricing_candidate_stmt(
        business_domain=business_domain,
        category_code=category_code,
        cutoff=cutoff,
        heartbeat_cutoff=heartbeat_cutoff,
    )
    return list(session.execute(stmt).all())


def _load_pricing_records_from_session(
    *,
    session,
    business_domain: str | None,
    category_code: str | None,
    cutoff: datetime,
    heartbeat_cutoff: datetime | None,
) -> list[dict[str, Any]]:
    rows = _load_pricing_candidate_rows_from_session(
        session=session,
        business_domain=business_domain,
        category_code=category_code,
        cutoff=cutoff,
        heartbeat_cutoff=heartbeat_cutoff,
    )
    records: list[dict[str, Any]] = []
    schema_by_category_code: dict[str, dict[str, Any] | None] = {}
    for item, spec in rows:
        item_category_code = resolve_category_code(item.business_domain)
        if item_category_code and item_category_code not in schema_by_category_code:
            schema_by_category_code[item_category_code] = load_active_spec_schema_for_pricing_with_session(
                session,
                category_code=item_category_code,
            )
        spec_schema = schema_by_category_code.get(item_category_code) if item_category_code else None
        record = resolve_pricing_record(
            item=item,
            spec=spec,
            spec_schema=spec_schema,
        )
        if record is not None:
            records.append(record)
    return records


def summarize_pricing_gate(
    *,
    items: list[Any],
    pricing_pool_count: int | None = None,
) -> dict[str, Any]:
    reason_counts = {key: 0 for key in PRICING_GATE_REASON_LABELS}
    candidate_count = len(items)
    review_gate_pass_count = 0
    for item in items:
        reason = pricing_gate_exclusion_reason(item)
        if reason is None:
            review_gate_pass_count += 1
            continue
        reason_counts[reason] += 1

    review_gate_filtered_count = candidate_count - review_gate_pass_count
    final_pricing_pool_count = max(int(pricing_pool_count or 0), 0)
    if final_pricing_pool_count <= 0:
        final_pricing_pool_count = review_gate_pass_count
    structural_drop_count = max(review_gate_pass_count - final_pricing_pool_count, 0)
    return {
        "candidate_count": candidate_count,
        "review_gate_pass_count": review_gate_pass_count,
        "review_gate_filtered_count": review_gate_filtered_count,
        "review_gate_pass_ratio": round((100 * review_gate_pass_count / candidate_count), 1) if candidate_count else 0.0,
        "review_gate_filtered_ratio": round((100 * review_gate_filtered_count / candidate_count), 1) if candidate_count else 0.0,
        "pricing_pool_count": final_pricing_pool_count,
        "pricing_pool_ratio": round((100 * final_pricing_pool_count / candidate_count), 1) if candidate_count else 0.0,
        "structural_drop_count": structural_drop_count,
        "excluded_reasons": [
            {
                "key": key,
                "label": PRICING_GATE_REASON_LABELS[key],
                "count": count,
                "ratio_of_candidates": round((100 * count / candidate_count), 1) if candidate_count else 0.0,
                "ratio_of_filtered": round((100 * count / review_gate_filtered_count), 1) if review_gate_filtered_count else 0.0,
            }
            for key, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def resolve_pricing_record(
    item: Item,
    spec: ItemSpecEnrichment | None,
    *,
    spec_schema: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    raw_spec = spec
    spec = usable_spec_for_pricing(spec)
    category_code = resolve_category_code(item.business_domain)
    category_name = display_label_for_scope(category_code)
    resolved_category_id = (
        (spec.category_id if spec is not None else None)
        or item.resolved_category_id
        or item.target_category_id
    )
    resolved_template_id = (spec.template_id if spec is not None else None) or item.resolved_template_id
    resolved_model_catalog_id = spec.model_catalog_id if spec is not None else None
    if not is_item_eligible_for_pricing(item):
        return None
    # Dashboard pricing reads can scan many rows; keep this path rule-only to avoid
    # per-item runtime/template loading overhead.
    rule_candidate = extract_rule_specs(item)
    if not title_matches_domain(item.business_domain, item.title):
        return None
    if title_is_non_comparable_listing(
        business_domain=item.business_domain,
        title=item.title,
        price=item.current_price,
    ):
        return None
    brand = first_text(spec.brand if spec else None, rule_candidate.brand, item.normalized_brand)
    if is_garmin_watch_scope(item.business_domain):
        brand = brand or "Garmin"
        if brand != "Garmin":
            return None
    elif is_apple_computer_scope(item.business_domain):
        brand = brand or "Apple"
        if brand != "Apple":
            return None
    elif brand is None:
        return None

    product_line = first_text(
        spec.product_line if spec else None,
        rule_candidate.product_line,
        spec.model_family if spec else None,
        item.normalized_model_family,
    )
    model_name = first_text(
        spec.model_name if spec else None,
        rule_candidate.model_name,
        item.normalized_model,
        product_line,
    )
    display_type = first_text(spec.display_type if spec else None, rule_candidate.display_type)
    if display_type:
        display_type = display_type.upper()
    case_size_mm = first_non_null(spec.case_size_mm if spec else None, rule_candidate.case_size_mm)
    is_solar = first_non_null(spec.is_solar if spec else None, rule_candidate.is_solar)
    screen_size_in = first_non_null(spec.screen_size_in if spec else None, rule_candidate.screen_size_in)
    chip_family = first_text(spec.chip_family if spec else None, rule_candidate.chip_family, item.normalized_chip)
    cpu_cores = first_non_null(spec.cpu_cores if spec else None, rule_candidate.cpu_cores)
    gpu_cores = first_non_null(spec.gpu_cores if spec else None, rule_candidate.gpu_cores)
    memory_gb = first_non_null(
        spec.memory_gb if spec else None,
        rule_candidate.memory_gb,
        item.normalized_memory_gb,
    )
    storage_gb = first_non_null(
        spec.storage_gb if spec else None,
        rule_candidate.storage_gb,
        item.normalized_storage_gb,
    )
    spec_confidence = max_optional_float(
        decimal_to_float(spec.confidence) if spec and spec.confidence is not None else None,
        decimal_to_float(rule_candidate.confidence) if rule_candidate.confidence is not None else None,
    )
    spec_status = first_text(spec.status if spec else None, rule_candidate.status)
    if spec_status == "unresolved":
        return None
    if not spec_confidence_passes_pricing_gate(spec_confidence):
        return None

    if is_garmin_watch_scope(item.business_domain):
        product_line = normalize_product_line(
            product_line=product_line,
            model_name=model_name,
            allowed_values=GARMIN_ANALYSIS_PRODUCT_LINES,
        )
        if product_line not in GARMIN_ANALYSIS_PRODUCT_LINES:
            return None
    if is_apple_computer_scope(item.business_domain):
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
        business_domain=item.business_domain,
        product_line=product_line,
        model_name=model_name,
        screen_size_in=screen_size_in,
        chip_family=chip_family,
    )
    spec_label, exact_spec_ready = build_spec_label(
        business_domain=item.business_domain,
        product_label=product_label,
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
    if product_label is None:
        return None
    spec_contract = build_pricing_spec_contract_snapshot(
        spec=spec,
        rule_candidate=rule_candidate,
        spec_status=spec_status,
        spec_confidence=spec_confidence,
        exact_spec_ready=exact_spec_ready,
    )
    pricing_eligibility = build_pricing_eligibility_snapshot(
        item=item,
        raw_spec=raw_spec,
        spec_status=spec_status,
        spec_confidence=spec_confidence,
        exact_spec_ready=exact_spec_ready,
    )

    record = {
        "item_id_ref": item.id,
        "item_id": item.item_id,
        "source_platform": item.source_platform,
        "business_domain": category_code,
        "category_code": category_code,
        "category_name": category_name,
        "category_id": resolved_category_id,
        "template_id": resolved_template_id,
        "model_catalog_id": resolved_model_catalog_id,
        "seller_key": str(item.seller_profile_id) if item.seller_profile_id is not None else f"item:{item.item_id}",
        "title": item.title,
        "region": item.region,
        "listing_url": item.listing_url,
        "price": float(
            normalize_market_price(
                item.current_price,
                business_domain=item.business_domain,
                model_family=product_line or item.normalized_model_family,
            )
        )
        if item.current_price is not None
        else None,
        "last_seen_at": item.last_seen_at,
        "publish_time": item.publish_time,
        "first_seen_at": item.first_seen_at,
        "brand": brand,
        "product_line": product_line,
        "model_name": model_name,
        "product_label": product_label,
        "spec_label": spec_label,
        "exact_spec_ready": exact_spec_ready,
        "display_type": display_type,
        "case_size_mm": case_size_mm,
        "is_solar": is_solar,
        "screen_size_in": decimal_to_float(screen_size_in),
        "chip_family": chip_family,
        "cpu_cores": cpu_cores,
        "gpu_cores": gpu_cores,
        "memory_gb": memory_gb,
        "storage_gb": storage_gb,
        "spec_status": spec_status,
        "spec_confidence": spec_confidence,
        "spec_contract": spec_contract,
        "spec_source": dict(pricing_eligibility.get("specSource") or {}),
        "pricing_eligibility": pricing_eligibility,
    }
    schema_completeness = evaluate_pricing_record_schema(record=record, schema=spec_schema)
    record["schema_id"] = schema_completeness.get("schemaId")
    record["schema"] = dict(spec_schema or {})
    record["schema_completeness"] = schema_completeness
    if schema_completeness.get("status") == "incomplete":
        return None
    if (
        spec_schema
        and schema_completeness.get("status") == "complete"
        and schema_completeness.get("requiredAttrs")
    ):
        record["exact_spec_ready"] = True
    return record


def build_pricing_spec_contract_snapshot(
    *,
    spec: ItemSpecEnrichment | None,
    rule_candidate: Any,
    spec_status: str | None,
    spec_confidence: float | None,
    exact_spec_ready: bool,
) -> dict[str, Any]:
    contract_payload = (
        dict((getattr(spec, "extraction_payload", {}) or {}).get("contract") or {})
        if spec is not None
        else {}
    )
    snapshot_source = "stored_spec"
    if not contract_payload:
        contract_payload = dict((getattr(rule_candidate, "extraction_payload", {}) or {}).get("contract") or {})
        snapshot_source = "runtime_rule" if contract_payload else "runtime_rule"
    return {
        "snapshotSource": snapshot_source,
        "source": contract_payload.get("source"),
        "status": contract_payload.get("status") or spec_status,
        "confidence": spec_confidence,
        "exactSpecReady": bool(exact_spec_ready),
        "needsReview": bool(contract_payload.get("needsReview", False)),
        "requiredFields": list(contract_payload.get("requiredFields") or []),
        "missingRequiredFields": list(contract_payload.get("missingRequiredFields") or []),
        "identityFields": list(contract_payload.get("identityFields") or []),
    }


def aggregate_pricing_view(
    *,
    records: list[dict[str, Any]],
    view: str,
    min_sample_points: int,
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = pricing_group_key(record=record, view=view)
        if key is None:
            continue
        groups[key].append(record)

    rows: list[dict[str, Any]] = []
    for key, group_records in groups.items():
        row = summarize_pricing_group(
            view=view,
            key=key,
            group_records=group_records,
            min_sample_points=min_sample_points,
        )
        if row is not None:
            rows.append(row)

    rows.sort(
        key=lambda row: (
            1 if row["is_actionable"] else 0,
            row.get("opportunity_score") or 0,
            row["reliability_score"],
            row["seller_sample_count"],
            row["unique_seller_count"],
            row["median_price"] or 0,
        ),
        reverse=True,
    )
    return rows


def pricing_group_key(*, record: dict[str, Any], view: str) -> tuple[Any, ...] | None:
    scope_code = _record_scope_code(record)
    if view == "brand":
        return (scope_code, record["brand"])
    if view == "product":
        return (scope_code, record["brand"], record["product_label"])
    if view == "spec":
        return (
            scope_code,
            record["brand"],
            record["product_label"],
            record["spec_label"],
        )
    raise ValueError(f"Unsupported pricing view: {view}")


def summarize_pricing_group(
    *,
    view: str,
    key: tuple[Any, ...],
    group_records: list[dict[str, Any]],
    min_sample_points: int,
) -> dict[str, Any] | None:
    collapsed_records = collapse_records_by_seller(group_records)
    cleaned_records, filter_meta = filter_outlier_price_records(collapsed_records)
    if not cleaned_records:
        return None

    cleaned_prices = sorted(record["price"] for record in cleaned_records)
    median_price = percentile(cleaned_prices, 0.50)
    p15_price = percentile(cleaned_prices, 0.15)
    p25_price = percentile(cleaned_prices, 0.25)
    p35_price = percentile(cleaned_prices, 0.35)
    p65_price = percentile(cleaned_prices, 0.65)
    p75_price = percentile(cleaned_prices, 0.75)
    estimated_profit_floor = max((median_price or 0) - (p35_price or 0), 0) if median_price is not None and p35_price is not None else None
    estimated_profit_ceiling = max((median_price or 0) - (p15_price or 0), 0) if median_price is not None and p15_price is not None else None
    normal_margin_pct = compute_profit_margin_pct(
        buy_price=p35_price,
        fair_price=median_price,
    )
    safe_margin_pct = compute_profit_margin_pct(
        buy_price=p15_price,
        fair_price=median_price,
    )
    outlier_count = max(len(collapsed_records) - len(cleaned_records), 0)
    outlier_ratio = (outlier_count / len(collapsed_records)) if collapsed_records else 0.0
    price_band_width_pct = (
        (((p75_price - p25_price) / median_price) * 100)
        if median_price and p25_price is not None and p75_price is not None
        else None
    )
    price_stability_score = compute_price_stability_score(
        price_band_width_pct=price_band_width_pct,
        outlier_ratio=outlier_ratio,
    )
    listing_age_metrics = compute_listing_age_metrics(cleaned_records)
    unique_sellers = len({record["seller_key"] for record in group_records})
    latest_seen_at = max((record["last_seen_at"] for record in group_records if record["last_seen_at"] is not None), default=None)
    exact_ready_count = sum(1 for record in group_records if record["exact_spec_ready"])
    exact_ready_ratio = (exact_ready_count / len(group_records)) if group_records else 0
    spec_confidences = [record["spec_confidence"] for record in group_records if record["spec_confidence"] is not None]
    seller_diversity_ratio = round(unique_sellers / len(group_records), 4) if group_records else 0
    reliability_score = compute_reliability_score(
        view=view,
        cleaned_count=len(cleaned_records),
        unique_sellers=unique_sellers,
        seller_diversity_ratio=seller_diversity_ratio,
        latest_seen_at=latest_seen_at,
        exact_ready_ratio=exact_ready_ratio,
        avg_spec_confidence=statistics.mean(spec_confidences) if spec_confidences else None,
        price_stability_score=price_stability_score,
        listing_age_score=listing_age_metrics["score"],
    )
    if view == "spec":
        if exact_ready_ratio < 0.35:
            reliability_score = min(reliability_score, 59.9)
        elif exact_ready_ratio < 0.65:
            reliability_score = min(reliability_score, 69.9)

    actionable_threshold = max(min_sample_points, 3 if view != "brand" else 2)
    sample_confident = (
        len(cleaned_records) >= actionable_threshold
        and unique_sellers >= (2 if view == "brand" else 3)
        and (view != "spec" or exact_ready_ratio >= 0.65)
    )
    required_profit_amount = minimum_actionable_profit_amount(median_price)
    meets_profit_gate = (
        estimated_profit_floor is not None
        and normal_margin_pct is not None
        and estimated_profit_floor >= required_profit_amount
        and normal_margin_pct >= MIN_ACTIONABLE_PROFIT_MARGIN_PCT
    )
    opportunity_tier = classify_opportunity_tier(
        sample_confident=sample_confident,
        meets_profit_gate=meets_profit_gate,
        estimated_profit_floor=estimated_profit_floor,
        estimated_profit_ceiling=estimated_profit_ceiling,
        normal_margin_pct=normal_margin_pct,
        required_profit_amount=required_profit_amount,
    )
    opportunity_score = compute_opportunity_score(
        estimated_profit_floor=estimated_profit_floor,
        normal_margin_pct=normal_margin_pct,
        required_profit_amount=required_profit_amount,
    )
    is_actionable = sample_confident and meets_profit_gate
    sample_titles = [record["title"] for record in sorted(group_records, key=sort_last_seen, reverse=True)[:3]]

    result = {
        "business_domain": key[0],
        "category_code": key[0],
        "category_name": display_label_for_scope(key[0]),
        "view": view,
        "label": key[-1],
        "brand": group_records[0]["brand"],
        "product_label": group_records[0]["product_label"] if view in {"product", "spec"} else None,
        "spec_label": group_records[0]["spec_label"] if view == "spec" else None,
        "listing_count": len(group_records),
        "unique_seller_count": unique_sellers,
        "seller_sample_count": len(cleaned_records),
        "seller_sample_raw_count": len(collapsed_records),
        "outlier_count": outlier_count,
        "outlier_ratio": round_money(outlier_ratio, digits=4),
        "median_price": round_money(median_price),
        "safe_buy_price": round_money(p15_price),
        "normal_buy_price": round_money(p35_price),
        "market_mid_price": round_money(median_price),
        "estimated_profit_floor": round_money(estimated_profit_floor),
        "estimated_profit_ceiling": round_money(estimated_profit_ceiling),
        "normal_margin_pct": round_money(normal_margin_pct, digits=2),
        "safe_margin_pct": round_money(safe_margin_pct, digits=2),
        "buy_floor_price": round_money(p15_price),
        "target_buy_ceiling": round_money(p35_price),
        "good_value_price": round_money(p25_price),
        "fair_price": round_money(median_price),
        "premium_floor_price": round_money(p65_price),
        "high_price_floor": round_money(p75_price),
        "min_price": round_money(cleaned_prices[0]),
        "max_price": round_money(cleaned_prices[-1]),
        "price_band_width_pct": round_money(price_band_width_pct, digits=2),
        "price_stability_score": round_money(price_stability_score, digits=4),
        "seller_diversity_ratio": seller_diversity_ratio,
        "avg_spec_confidence": round_money(statistics.mean(spec_confidences), digits=4) if spec_confidences else None,
        "exact_spec_ratio": round_money(exact_ready_ratio, digits=4) if group_records else None,
        "median_listing_age_hours": round_money(listing_age_metrics["median_age_hours"], digits=2),
        "fresh_listing_ratio": round_money(listing_age_metrics["fresh_ratio"], digits=4),
        "aged_listing_ratio": round_money(listing_age_metrics["aged_ratio"], digits=4),
        "listing_age_score": round_money(listing_age_metrics["score"], digits=4),
        "listing_age_coverage_ratio": round_money(listing_age_metrics["coverage"], digits=4),
        "reliability_score": round(reliability_score, 1),
        "reliability_tier": reliability_tier(reliability_score),
        "sample_confident": sample_confident,
        "is_actionable": is_actionable,
        "required_profit_amount": round_money(required_profit_amount),
        "opportunity_score": round(opportunity_score, 1),
        "opportunity_tier": opportunity_tier,
        "latest_seen_at": latest_seen_at.isoformat() if latest_seen_at else None,
        "sample_titles": sample_titles,
        "filter_summary": filter_meta,
        "schema_id": group_records[0].get("schema_id"),
        "schema": dict(group_records[0].get("schema") or {}),
        "schema_completeness": dict(group_records[0].get("schema_completeness") or {}),
    }
    result.update(spec_dimension_payload(group_records[0]))
    return result


def collapse_records_by_seller(group_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in group_records:
        grouped[record["seller_key"]].append(record)

    collapsed: list[dict[str, Any]] = []
    for seller_key, seller_records in grouped.items():
        seller_prices = sorted(record["price"] for record in seller_records)
        seller_median_price = percentile(seller_prices, 0.50)
        representative = min(
            seller_records,
            key=lambda record: (
                abs(record["price"] - seller_median_price),
                -sort_last_seen(record),
            ),
        )
        collapsed.append(
            {
                **representative,
                "seller_key": seller_key,
                "price": seller_median_price,
                "seller_listing_count": len(seller_records),
            }
        )
    collapsed.sort(key=lambda record: record["price"])
    return collapsed


def filter_outlier_price_records(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(records) < 4:
        return records, {"method": "none", "low_fence": None, "high_fence": None}

    sorted_records = sorted(records, key=lambda record: record["price"])
    prefiltered_records = sorted_records
    prefilter_meta: dict[str, Any] = {}
    if len(sorted_records) >= 10:
        average_price = statistics.mean(record["price"] for record in sorted_records)
        if average_price > 1000:
            average_floor = average_price * 0.5
            floor_filtered = [
                record
                for record in sorted_records
                if record["price"] >= average_floor
            ]
            if floor_filtered:
                prefiltered_records = floor_filtered
                prefilter_meta = {
                    "pre_filter_method": "avg_floor_50pct",
                    "pre_filter_average_price": round_money(average_price),
                    "pre_filter_floor": round_money(average_floor),
                    "pre_filter_removed_count": max(len(sorted_records) - len(floor_filtered), 0),
                }

    log_prices = [math.log(record["price"]) for record in prefiltered_records if record["price"] > 0]
    mad_filtered = prefiltered_records
    mad_value = None
    if len(log_prices) == len(prefiltered_records) and log_prices:
        median_log = statistics.median(log_prices)
        deviations = [abs(value - median_log) for value in log_prices]
        mad_value = statistics.median(deviations)
        if mad_value and mad_value > 0:
            mad_filtered = []
            for record, log_price in zip(prefiltered_records, log_prices, strict=True):
                robust_z = 0.6745 * (log_price - median_log) / mad_value
                if abs(robust_z) <= 3.5:
                    mad_filtered.append(record)

    if len(mad_filtered) < 4:
        return mad_filtered or prefiltered_records, {
            "method": "log_mad",
            "low_fence": None,
            "high_fence": None,
            "mad": round_money(mad_value, digits=6) if mad_value is not None else None,
            **prefilter_meta,
        }

    mad_prices = sorted(record["price"] for record in mad_filtered)
    q1 = percentile(mad_prices, 0.25)
    q3 = percentile(mad_prices, 0.75)
    if q1 is None or q3 is None:
        return mad_filtered, {
            "method": "log_mad",
            "low_fence": None,
            "high_fence": None,
            **prefilter_meta,
        }
    iqr = q3 - q1
    if iqr <= 0:
        return mad_filtered, {
            "method": "log_mad",
            "low_fence": round_money(q1),
            "high_fence": round_money(q3),
            "mad": round_money(mad_value, digits=6) if mad_value is not None else None,
            **prefilter_meta,
        }

    low_fence = max(min(mad_prices), q1 - (1.5 * iqr))
    high_fence = q3 + (1.5 * iqr)
    iqr_filtered = [
        record
        for record in mad_filtered
        if low_fence <= record["price"] <= high_fence
    ]
    if len(iqr_filtered) < max(3, len(mad_filtered) // 2):
        iqr_filtered = mad_filtered

    return iqr_filtered, {
        "method": "log_mad_plus_iqr",
        "low_fence": round_money(low_fence),
        "high_fence": round_money(high_fence),
        "mad": round_money(mad_value, digits=6) if mad_value is not None else None,
        **prefilter_meta,
    }


def build_product_label(
    *,
    business_domain: str,
    product_line: str | None,
    model_name: str | None,
    screen_size_in: Decimal | None,
    chip_family: str | None,
) -> str | None:
    if is_garmin_watch_scope(business_domain):
        return first_text(model_name, product_line)

    if is_apple_computer_scope(business_domain):
        canonical_product_line = normalize_product_line(
            product_line=product_line,
            model_name=model_name,
            allowed_values=APPLE_ANALYSIS_PRODUCT_LINES,
        )
        if canonical_product_line not in APPLE_ANALYSIS_PRODUCT_LINES:
            return None
        normalized_chip_family = normalize_apple_chip_family(chip_family)
        if not normalized_chip_family:
            return None
        normalized_screen_size = normalize_apple_screen_size(
            product_line=canonical_product_line,
            screen_size_in=screen_size_in,
        )
        if canonical_product_line.startswith("MacBook") and screen_size_in is not None and normalized_screen_size is None:
            return None
        if not apple_product_line_allows_chip_family(
            product_line=canonical_product_line,
            chip_family=normalized_chip_family,
        ):
            return None
        parts = [canonical_product_line]
        if normalized_screen_size is not None and canonical_product_line.lower().startswith("macbook"):
            parts.append(f"{format_decimal_label(normalized_screen_size)}in")
        parts.append(normalized_chip_family)
        cleaned = [part for part in parts if part]
        return " / ".join(cleaned) if cleaned else None

    return first_text(model_name, product_line)


def _requested_scope_key(*, business_domain: str | None, category_code: str | None) -> str | None:
    candidate = str(category_code or business_domain or "").strip()
    return candidate or None


def _scope_keys_for_filter(*, business_domain: str | None, category_code: str | None) -> tuple[str, ...]:
    return resolve_pricing_scope(business_domain=business_domain, category_code=category_code).scope_keys


def _record_scope_code(record: dict[str, Any]) -> str:
    return resolve_category_code(
        str(record.get("category_code") or record.get("business_domain") or "").strip()
    )


def build_spec_label(
    *,
    business_domain: str,
    product_label: str | None,
    display_type: str | None,
    case_size_mm: int | None,
    is_solar: bool | None,
    screen_size_in: Decimal | None,
    chip_family: str | None,
    cpu_cores: int | None,
    gpu_cores: int | None,
    memory_gb: int | None,
    storage_gb: int | None,
) -> tuple[str | None, bool]:
    if product_label is None:
        return None, False

    if is_garmin_watch_scope(business_domain):
        parts = [product_label]
        if display_type:
            parts.append(display_type)
        if case_size_mm is not None:
            parts.append(f"{case_size_mm}mm")
        if is_solar is True:
            parts.append("Solar")
        elif is_solar is False:
            parts.append("Non-solar")
        exact_ready = bool(display_type and case_size_mm is not None)
        return " / ".join(parts), exact_ready

    if is_apple_computer_scope(business_domain):
        parts = [product_label]
        if cpu_cores is not None:
            parts.append(f"{cpu_cores}C CPU")
        if gpu_cores is not None:
            parts.append(f"{gpu_cores}C GPU")
        if memory_gb is not None:
            parts.append(f"{memory_gb}G")
        if storage_gb is not None:
            storage_label = f"{storage_gb // 1024}TB" if storage_gb >= 1024 and storage_gb % 1024 == 0 else f"{storage_gb}G"
            parts.append(storage_label)
        exact_ready = bool(chip_family and memory_gb is not None and storage_gb is not None)
        return " / ".join(parts), exact_ready

    return product_label, False


def compute_reliability_score(
    *,
    view: str,
    cleaned_count: int,
    unique_sellers: int,
    seller_diversity_ratio: float,
    latest_seen_at: datetime | None,
    exact_ready_ratio: float,
    avg_spec_confidence: float | None,
    price_stability_score: float,
    listing_age_score: float,
) -> float:
    sample_score = min(cleaned_count / (12 if view == "brand" else 8), 1.0)
    seller_score = min(unique_sellers / (10 if view == "brand" else 6), 1.0)
    diversity_score = min(seller_diversity_ratio / 0.6, 1.0)
    spec_score = min((avg_spec_confidence or 0.45), 1.0)
    exact_score = exact_ready_ratio if view == "spec" else min(max(exact_ready_ratio, 0.55), 1.0)
    freshness_score = 0.35
    if latest_seen_at is not None:
        age_hours = (datetime.now(UTC) - latest_seen_at.astimezone(UTC)).total_seconds() / 3600
        if age_hours <= 24:
            freshness_score = 1.0
        elif age_hours <= 72:
            freshness_score = 0.85
        elif age_hours <= 168:
            freshness_score = 0.70
        else:
            freshness_score = 0.50

    return 100 * (
        (0.28 * sample_score)
        + (0.20 * seller_score)
        + (0.10 * diversity_score)
        + (0.10 * freshness_score)
        + (0.08 * spec_score)
        + (0.08 * exact_score)
        + (0.10 * price_stability_score)
        + (0.06 * listing_age_score)
    )


def compute_price_stability_score(*, price_band_width_pct: float | None, outlier_ratio: float) -> float:
    if price_band_width_pct is None:
        dispersion_score = 0.6
    elif price_band_width_pct <= 12:
        dispersion_score = 1.0
    elif price_band_width_pct <= 20:
        dispersion_score = 0.9
    elif price_band_width_pct <= 30:
        dispersion_score = 0.78
    elif price_band_width_pct <= 45:
        dispersion_score = 0.58
    else:
        dispersion_score = 0.38

    if outlier_ratio <= 0.05:
        outlier_score = 1.0
    elif outlier_ratio <= 0.10:
        outlier_score = 0.92
    elif outlier_ratio <= 0.20:
        outlier_score = 0.78
    elif outlier_ratio <= 0.35:
        outlier_score = 0.58
    else:
        outlier_score = 0.35

    return (0.7 * dispersion_score) + (0.3 * outlier_score)


def compute_listing_age_metrics(
    records: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, float | None]:
    reference = now or datetime.now(UTC)
    age_hours: list[float] = []
    for record in records:
        started_at = first_non_null(
            record.get("publish_time"),
            record.get("first_seen_at"),
            record.get("last_seen_at"),
        )
        if not isinstance(started_at, datetime):
            continue
        age_hours.append(max((reference - started_at.astimezone(UTC)).total_seconds() / 3600, 0.0))

    coverage = (len(age_hours) / len(records)) if records else 0.0
    if not age_hours:
        return {
            "median_age_hours": None,
            "fresh_ratio": None,
            "aged_ratio": None,
            "coverage": coverage,
            "score": 0.6,
        }

    median_age_hours = float(statistics.median(age_hours))
    fresh_ratio = sum(1 for value in age_hours if value <= 6) / len(age_hours)
    aged_ratio = sum(1 for value in age_hours if value >= 24 * 14) / len(age_hours)

    score = 1.0
    if median_age_hours < 6:
        score *= 0.78
    elif median_age_hours < 24:
        score *= 0.90
    elif median_age_hours > 24 * 30:
        score *= 0.78
    elif median_age_hours > 24 * 14:
        score *= 0.88

    if fresh_ratio > 0.50:
        score *= 0.82
    elif fresh_ratio > 0.30:
        score *= 0.90

    if aged_ratio > 0.50:
        score *= 0.82
    elif aged_ratio > 0.30:
        score *= 0.90

    if coverage < 0.50:
        score *= 0.92

    return {
        "median_age_hours": median_age_hours,
        "fresh_ratio": fresh_ratio,
        "aged_ratio": aged_ratio,
        "coverage": coverage,
        "score": max(min(score, 1.0), 0.35),
    }


def first_text(*values: Any) -> str | None:
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def first_non_null(*values: Any) -> Any | None:
    for value in values:
        if value is not None:
            return value
    return None


def decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def format_decimal_label(value: Decimal) -> str:
    if value == value.to_integral():
        return str(int(value))
    return str(value.normalize())


def normalize_apple_chip_family(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    match = APPLE_CHIP_FAMILY_RE.search(normalized)
    if match is None:
        return normalized or None
    base = str(match.group(1) or "").upper()
    suffix = str(match.group(2) or "").strip().lower()
    if not suffix:
        return base
    return f"{base} {suffix.capitalize()}"


def normalize_apple_screen_size(*, product_line: str | None, screen_size_in: Decimal | None) -> Decimal | None:
    if screen_size_in is None:
        return None
    canonical_product_line = normalize_product_line(
        product_line=product_line,
        model_name=product_line,
        allowed_values=APPLE_ANALYSIS_PRODUCT_LINES,
    )
    buckets = APPLE_SCREEN_SIZE_BUCKETS.get(canonical_product_line or "")
    if not buckets:
        return screen_size_in
    tolerance = APPLE_SCREEN_SIZE_TOLERANCE.get(canonical_product_line or "", Decimal("0.50"))
    closest = min(buckets, key=lambda bucket: abs(bucket - screen_size_in))
    if abs(closest - screen_size_in) > tolerance:
        return None
    return closest


def apple_product_line_allows_chip_family(*, product_line: str | None, chip_family: str | None) -> bool:
    normalized_line = str(product_line or "").strip()
    normalized_chip = normalize_apple_chip_family(chip_family)
    if not normalized_line or not normalized_chip:
        return False
    if normalized_line == "MacBook Air":
        lowered_chip = normalized_chip.lower()
        return not any(token in lowered_chip for token in (" pro", " max", " ultra"))
    return True


def max_optional_float(*values: float | None) -> float | None:
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def normalize_product_line(
    *,
    product_line: str | None,
    model_name: str | None,
    allowed_values: set[str],
) -> str | None:
    ordered_allowed_values = sorted(allowed_values, key=lambda value: (-len(value), value))
    for candidate in (product_line, model_name):
        candidate_text = (candidate or "").strip()
        if not candidate_text:
            continue
        if candidate_text in allowed_values:
            return candidate_text

        compact_candidate = re.sub(r"[\s\-_+/（）()]+", "", candidate_text.lower())
        for value in ordered_allowed_values:
            compact_value = re.sub(r"[\s\-_+/（）()]+", "", value.lower())
            if compact_candidate.startswith(compact_value) or compact_value in compact_candidate:
                return value
    return product_line


def title_matches_domain(business_domain: str, title: str | None) -> bool:
    if not title:
        return False
    lowered = title.lower()
    resolved_scope = resolve_category_code(business_domain)
    if resolved_scope == "apple_computer":
        return _title_matches_apple_computer_domain(lowered)
    if resolved_scope == "apple_airpods":
        return _title_matches_apple_airpods_domain(lowered)
    if resolved_scope == "camera_body":
        return _title_matches_camera_body_domain(lowered)
    if resolved_scope == "camera_interchangeable_lens":
        return _title_matches_camera_interchangeable_lens_domain(lowered)
    tokens = list(DOMAIN_ANALYSIS_TOKENS.get(resolved_scope, []))
    if not tokens:
        tokens = list(token_aliases_for_scope(resolved_scope or business_domain))
    if not tokens:
        return True
    return any(token.lower() in lowered for token in tokens)


def resolve_domain_redirect_scope(business_domain: str, title: str | None) -> str | None:
    if not title:
        return None
    resolved_scope = resolve_category_code(business_domain)
    if resolved_scope == "camera_body":
        if _title_matches_camera_interchangeable_lens_domain(title) and not _title_matches_camera_body_domain(title):
            return "camera_interchangeable_lens"
        return None
    if resolved_scope == "camera_interchangeable_lens":
        if _title_matches_camera_body_domain(title) and not _title_matches_camera_interchangeable_lens_domain(title):
            return "camera_body"
        return None
    return None


def title_domain_mismatch_reason(business_domain: str, title: str | None) -> str | None:
    if not title:
        return None
    resolved_scope = resolve_category_code(business_domain)
    if resolved_scope == "apple_computer":
        return _title_apple_computer_mismatch_reason(title)
    if resolved_scope == "garmin_watch":
        return _title_garmin_watch_mismatch_reason(title)
    return None


def _title_matches_apple_computer_domain(lowered_title: str) -> bool:
    normalized = str(lowered_title or "").strip().lower()
    if not normalized:
        return False
    compact = re.sub(r"[\s\-_+/（）()]+", "", normalized)

    strong_tokens = (
        "macbook",
        "macbookair",
        "macbookpro",
        "macmini",
        "macstudio",
        "imac",
        "mbp",
        "mba",
        "苹果",
        "apple",
    )
    strong_mac_signal = any(token in compact for token in strong_tokens)

    chip_series_matches = re.findall(r"m[1-4](?:\s*(?:pro|max|ultra))?", normalized)
    if not chip_series_matches:
        chip_series_matches = re.findall(r"m[1-4](?:pro|max|ultra)?", compact)
    has_m_chip_signal = bool(chip_series_matches)

    apple_context_tokens = (
        "mac",
        "苹果",
        "apple",
        "book",
        "studio",
        "mini",
        "imac",
        "mbp",
        "mba",
        "芯片",
        "国行",
        "13寸",
        "14寸",
        "15寸",
        "16寸",
        "ac+",
    )
    has_apple_context = any(token in normalized or token in compact for token in apple_context_tokens)
    has_strong_mac_combo = strong_mac_signal or (has_m_chip_signal and has_apple_context)

    terse_mac_patterns = (
        re.compile(r"\b(13|14|15|16)(?:\.\d)?寸\s*(mac\s*)?(air|pro)\b", re.IGNORECASE),
        re.compile(r"\b(air|pro)\s*(13|14|15|16)(?:\.\d)?寸\b", re.IGNORECASE),
        re.compile(r"\ba(2141|2251|2337|2442|2485|2681|2779|2780|2918|2991|3112|3401|3403|3185)\b", re.IGNORECASE),
    )
    if any(pattern.search(normalized) for pattern in terse_mac_patterns):
        has_strong_mac_combo = True

    wrong_tokens = (
        "apple watch",
        "watch series",
        "watch ultra",
        "watch se",
        "iwatch",
        "airpods",
        "ipad",
        "iphone",
    )
    has_wrong_token = any(token in normalized or re.sub(r"\s+", "", token) in compact for token in wrong_tokens)
    has_watch_token = any(
        token in normalized or re.sub(r"\s+", "", token) in compact
        for token in ("apple watch", "watch series", "watch ultra", "watch se", "iwatch")
    )
    if has_watch_token:
        return False
    if has_wrong_token and not has_strong_mac_combo:
        return False

    if has_strong_mac_combo:
        return True

    # Allow terse but still recognizably Apple-computer titles like
    # "m4max 14寸 128+8t" or "m3pro 16寸 36g 1t".
    has_size_token = any(token in normalized or token in compact for token in ("13寸", "14寸", "15寸", "16寸"))
    has_memory_or_storage = bool(
        re.search(r"\b(16|18|24|32|36|48|64|96|128)\s*g\b", normalized, re.IGNORECASE)
        or re.search(r"\b(256|512|1024)\s*g\b", normalized, re.IGNORECASE)
        or re.search(r"\b([1248])\s*t\b", normalized, re.IGNORECASE)
        or re.search(r"(16|18|24|32|36|48|64|96|128)\+(256|512|1t|2t|4t|8t)", compact, re.IGNORECASE)
    )
    terse_chip_signal = bool(
        re.search(r"\bm[1-4](?:\s*(?:pro|max|ultra))?\b", normalized, re.IGNORECASE)
        or re.search(r"m[1-4](?:pro|max|ultra)?", compact, re.IGNORECASE)
    )
    return terse_chip_signal and has_size_token and has_memory_or_storage


def _title_apple_computer_mismatch_reason(title: str | None) -> str | None:
    if _title_matches_apple_computer_domain(title or ""):
        return None
    normalized = str(title or "").strip().lower()
    compact = re.sub(r"[\s\-_+/（）()]+", "", normalized)
    wrong_token_groups = (
        ("apple_watch_like", ("apple watch", "watch series", "watch ultra", "watch se", "iwatch", "手表")),
        ("apple_audio_like", ("airpods", "耳机")),
        ("apple_mobile_like", ("iphone", "ipad", "手机", "平板")),
    )
    for reason, tokens in wrong_token_groups:
        for token in tokens:
            lowered_token = token.lower()
            if lowered_token in normalized or re.sub(r"\s+", "", lowered_token) in compact:
                return reason
    return None


def _title_matches_apple_airpods_domain(lowered_title: str) -> bool:
    normalized = str(lowered_title or "").strip().lower()
    if not normalized:
        return False
    compact = re.sub(r"[\s\-_+/（）()]+", "", normalized)
    audio_tokens = (
        "airpods",
        "airpod",
        "pro2",
        "pro 2",
        "airpodspro",
        "airpodsmax",
        "耳机",
        "耳塞",
        "充电盒",
    )
    if not any(token in normalized or token in compact for token in audio_tokens):
        return False
    wrong_tokens = (
        "macbook",
        "macmini",
        "macstudio",
        "imac",
        "iphone",
        "ipad",
        "watch",
        "iwatch",
    )
    return not any(token in normalized or token in compact for token in wrong_tokens)


CAMERA_BRAND_TOKENS: tuple[str, ...] = (
    "索尼",
    "sony",
    "尼康",
    "nikon",
    "佳能",
    "canon",
    "富士",
    "fujifilm",
    "fuji",
    "松下",
    "panasonic",
    "lumix",
    "徕卡",
    "leica",
)
CAMERA_BODY_ALWAYS_EXPLICIT_TOKENS: tuple[str, ...] = (
    "单机身",
    "快门",
    "不含镜头",
    "镜头另售",
    "镜头另出",
    "不带镜头",
)
CAMERA_BODY_CONTEXTUAL_TOKENS: tuple[str, ...] = (
    "机身",
    "单机",
    "微单",
    "单反",
    "body",
)
CAMERA_BODY_BUNDLE_TOKENS: tuple[str, ...] = (
    "套机",
    "套装",
    "机身+",
    "+机身",
    "带机身",
    "含机身",
)
CAMERA_BODY_INCLUDED_ACCESSORY_PATTERN = re.compile(
    r"(带|送|含|配).{0,12}(电池|充电器|肩带|相机包|机身盖|镜头盖|镜头后盖|前后盖|前盖|后盖|转接环|转接头|遮光罩|滤镜|uv镜|兔笼|保护套|硅胶套|快门线)",
    re.IGNORECASE,
)
CAMERA_BODY_NON_TARGET_PACKAGING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(只有|仅|只卖|空).{0,4}(盒说|盒子|包装盒)", re.IGNORECASE),
    re.compile(r"(盒说|盒子|包装盒).{0,8}(没有|不含).{0,8}(相机|机身|机器)", re.IGNORECASE),
    re.compile(r"相机早卖了", re.IGNORECASE),
)
CAMERA_BODY_NON_TARGET_PART_TOKENS: tuple[str, ...] = (
    "盒说",
    "包装盒",
    "顶盖",
    "肩屏",
    "排线",
    "机身盖",
    "镜头盖",
    "镜头后盖",
    "镜头前盖",
    "前后盖",
    "前盖",
    "后盖",
    "电池盖",
    "电池仓盖",
    "皮堵",
    "胶皮",
    "侧皮",
    "饰皮",
    "转接环",
    "转接头",
)
CAMERA_NON_TARGET_LIGHTING_TOKENS: tuple[str, ...] = (
    "闪光灯",
    "机顶闪光灯",
    "补光灯",
)
CAMERA_BODY_MODEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![a-z0-9])a7c2?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a7cii(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a7m[234](?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a7\s*(?:ii|iii|iv|v)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a7iv(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a7r(?:3a?|4a?|5)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a7r\s*(?:iii|iv|v)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a7rm(?:3|4a?)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a7s3(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a7s(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a(?:6400|6600|6700)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])a6700(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"alpha\s*7c\s*ii", re.IGNORECASE),
    re.compile(r"alpha\s*7r\s*(?:iii|iv|v)", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])z(?:5|6|7|8|9|f|fc|50|30)(?:ii|iii|2|3|二代|三代|一代)?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])r(?:5|6|7|8|10|50|50v|100|p)(?:ii|iii|2|3|二代|三代|一代)?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"eos\s*r(?!f)(?:\s|$)", re.IGNORECASE),
    re.compile(r"eos\s*r(?:5|6|7|8|10|50|50v|100|p)(?:ii|iii|2|3|二代|三代|一代)?", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:xt|x-t)\s*(?:1|2|3|4|5|30(?:ii|2|二代)?|50)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:xa|x-a)\s*(?:3|5|7|10|20)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:xm|x-m)\s*5(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:xh|x-h)\s*2s?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:xs|x-s)\s*20(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:xs|x-s)\s*10(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:h2|h2s)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:xe|x-e)\s*4(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:xe|x-e)\s*(?:2|3|5)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:xpro|x-pro)\s*(?:2|3)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])x100(?:s|vi)?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])xhalf(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])gfx(?:50s|100s)(?:ii|2|二代)?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])s5(?:m2|ii|2|二代)(?:x)?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])s1m(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])s1[hr](?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])s9(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])g100d(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])g9(?:m2|ii|2|二代)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])gh(?:5(?:m2|ii|2|二代)?|6|7)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])zv[\s-]?e(?:1|10(?:m2|ii|2|二代)?)(?![a-z0-9])", re.IGNORECASE),
)
CAMERA_BODY_COMPACT_SAFE_SIGNATURES: tuple[str, ...] = (
    "a7r3",
    "a7r4",
    "a7r4a",
    "a7r5",
    "a7c2",
    "a7m3",
    "a7m4",
    "a6700",
    "a6400",
    "xt5",
    "xt50",
    "xt30ii",
    "xs20",
    "xs10",
    "xm5",
    "xe4",
    "xe3",
    "xe2",
    "xe5",
    "xpro3",
    "h2",
    "h2s",
    "gfx50sii",
    "gfx100sii",
    "g100d",
    "gh6",
    "gh7",
    "gh5ii",
    "gh5m2",
    "s5ii",
    "s5iix",
    "s5markii",
    "s5markiix",
    "s1m",
    "s1h",
    "s1r",
    "zve10m2",
    "zve10",
)
CAMERA_LENS_KEYWORD_TOKENS: tuple[str, ...] = (
    "镜头",
    "nikkor",
    "适马",
    "sigma",
    "腾龙",
    "tamron",
    "唯卓仕",
    "唯卓士",
    "viltrox",
    "美科",
    "meike",
    "永诺",
    "sirui",
    "思锐",
    "蔡司",
    "zeiss",
    "七工匠",
    "铭匠",
    "老蛙",
    "福伦达",
    "voigtlander",
)
CAMERA_LENS_DESCRIPTOR_TOKENS: tuple[str, ...] = (
    "定焦",
    "变焦",
    "长焦",
    "广角",
    "人像",
    "大三元",
    "挂机头",
    "饼干头",
    "银圈",
    "金圈",
)
CAMERA_LENS_SUPPORT_TOKENS: tuple[str, ...] = (
    "镜片",
    "镜身",
    "遮光罩",
    "前后盖",
    "前盖",
    "后盖",
    "成像",
    "对焦",
    "对焦环",
    "光圈环",
    "微灰",
    "脚架环",
    "脚架座",
    "原装前后盖",
)
CAMERA_LENS_MOUNT_TOKENS: tuple[str, ...] = (
    "e口",
    "z口",
    "z卡口",
    "rf",
    "rf-s",
    "ef",
    "ef-s",
    "xf",
    "gf",
    "卡口",
    "fe",
    "f卡口",
)
CAMERA_LENS_MOUNT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:e口|z口|z卡口|f卡口|卡口)", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:rf|rf-s|rfs|ef|ef-s|efs|xf|gf|fe)(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?:索尼|sony)\s*fe", re.IGNORECASE),
    re.compile(r"(?:佳能|canon)\s*rf", re.IGNORECASE),
    re.compile(r"(?:尼康|nikon)\s*z\s*(?:口|卡口)?", re.IGNORECASE),
)
CAMERA_LENS_COMPACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:rf|rfs|ef|efs|fe|xf|xcd|gf|nikkorz|nikkor|z)\d{1,3}(?:-\d{1,3})?(?:mm)?(?:f|/)?\d(?:\.\d)?(?:s|gm|art|pro|vr|dgdn|dn|lab|se|g2|g)?", re.IGNORECASE),
)
CAMERA_LENS_NORMALIZED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![a-z0-9])(?:rf|rfs|ef|efs|fe|xf|xcd|gf|z)\s*\d{1,3}(?:\s*-\s*\d{1,3})?(?:\s*mm)?\s*(?:f\s*/?\s*)?\d(?:\.\d)?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?:^|[^a-z0-9])\d{2,3}(?:-\d{2,3})?f\d(?:\.\d)?", re.IGNORECASE),
    re.compile(r"(?:^|[^a-z0-9])\d{2,3}(?:-\d{2,3})?/\d(?:\.\d)?", re.IGNORECASE),
)
CAMERA_LENS_ZOOM_SIGNATURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<!\d)\d{2,3}\s*[-~至到/]\s*\d{2,3}(?:\s*mm)?\s*(?:f\s*/?\s*|[-/.])?\s*\d(?:\.\d)?(?:\s*(?:gm|art|pro|g2|g|vr|lab|dn|dg|se|s))?(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)\d{2,3}\s*[-~至到/]\s*\d{2,3}(?:\s*mm)?\s*(?:z|s|gm|art|pro|g2|g|vr|lab|dn|dg|se)(?![a-z0-9])", re.IGNORECASE),
)
CAMERA_LENS_PRIME_SIGNATURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<!\d)\d{2,3}(?:\s*mm)?\s*(?:f\s*/?\s*|[-/.])\s*\d(?:\.\d)?\s*(?:gm|art|pro|g2|g|vr|lab|dn|dg|se|s)?(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)\d{2,3}\s+\d(?:\.\d)?\s*(?:gm|art|pro|g2|g|vr|lab|dn|dg|se|s)(?!\d)", re.IGNORECASE),
)
CAMERA_LENS_TIGHT_SIGNATURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<!\d)\d{2,3}(?:[-/])\d(?:\.\d)?(?:s|gm|art|pro|g2|g|vr|lab|dn|dg|se)?(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)\d{2,3}\.\d(?:s|gm|art|pro|g2|g|vr|lab|dn|dg|se)(?!\d)", re.IGNORECASE),
)
CAMERA_LENS_COMPACT_SIGNATURES: tuple[str, ...] = (
    "5014gm",
    "50mm14gm",
    "3514gm",
    "gm3514",
    "8514gm",
    "8514gm2",
    "85gm2f14",
    "5018s",
    "50rf18",
    "4018",
    "3518",
    "10528",
    "247028",
    "7020028",
    "180600",
    "28400",
    "24200",
    "24120",
)


def _camera_title_normalized_parts(value: str | None) -> tuple[str, str]:
    normalized = (
        str(value or "")
        .strip()
        .lower()
        .replace("α", "a")
        .replace("—", "-")
        .replace("–", "-")
        .replace("－", "-")
        .replace("／", "/")
        .replace("．", ".")
        .replace(" ", " ")
    )
    compact = re.sub(r"[\s\-_+/（）()]+", "", normalized)
    return normalized, compact


def _camera_title_slug(normalized: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _camera_title_leading_clause(normalized: str) -> str:
    clause = re.split(r"[，,。；;!！?？]", normalized, maxsplit=1)[0]
    return clause[:20]


def _camera_title_has_brand_signal(normalized: str) -> bool:
    return any(token in normalized for token in CAMERA_BRAND_TOKENS)


def _camera_title_has_body_model_signal(normalized: str) -> bool:
    compact = re.sub(r"[\s\-_+/（）()]+", "", normalized)
    slug = _camera_title_slug(normalized)
    return any(pattern.search(normalized) for pattern in CAMERA_BODY_MODEL_PATTERNS) or any(
        signature in compact or signature in slug for signature in CAMERA_BODY_COMPACT_SAFE_SIGNATURES
    )


def _camera_title_has_body_prefix_signal(normalized: str) -> bool:
    prefix = normalized[:40]
    return _camera_title_has_body_model_signal(prefix)


def _camera_title_has_body_primary_signal(normalized: str) -> bool:
    brand_present = _camera_title_has_brand_signal(normalized)
    body_model_present = _camera_title_has_body_model_signal(normalized)
    if any(token in normalized for token in CAMERA_BODY_ALWAYS_EXPLICIT_TOKENS):
        return True
    if any(token in normalized for token in CAMERA_BODY_BUNDLE_TOKENS) and (brand_present or body_model_present):
        return True
    if any(token in normalized for token in ("机身", "单机", "body")) and (brand_present or body_model_present):
        return True
    if any(token in normalized for token in ("相机", "微单", "单反")) and body_model_present:
        return True
    return _camera_title_has_body_prefix_signal(normalized)


def _camera_title_has_body_non_target_signal(normalized: str) -> bool:
    if any(pattern.search(normalized) for pattern in CAMERA_BODY_NON_TARGET_PACKAGING_PATTERNS):
        return True
    if any(token in normalized for token in CAMERA_NON_TARGET_LIGHTING_TOKENS):
        return True
    if not any(token in normalized for token in CAMERA_BODY_NON_TARGET_PART_TOKENS):
        return False
    if "单机" in normalized or "单机身" in normalized or "机身" in _camera_title_leading_clause(normalized):
        return False
    if CAMERA_BODY_INCLUDED_ACCESSORY_PATTERN.search(normalized) and _camera_title_has_body_model_signal(normalized):
        return False
    if re.search(r"(不含镜头|镜头另售|镜头另出|不带镜头)", normalized, re.IGNORECASE):
        return False
    return True


def _camera_title_has_lens_identity_signal(normalized: str, compact: str) -> bool:
    slug = _camera_title_slug(normalized)
    if any(token in normalized for token in CAMERA_NON_TARGET_LIGHTING_TOKENS):
        return False
    if any(token in normalized for token in CAMERA_LENS_KEYWORD_TOKENS):
        return True
    if any(token in normalized for token in CAMERA_LENS_DESCRIPTOR_TOKENS):
        return True
    has_brand_context = _camera_title_has_brand_signal(normalized) or any(
        token in normalized for token in CAMERA_LENS_KEYWORD_TOKENS
    )
    has_support_context = any(token in normalized for token in CAMERA_LENS_SUPPORT_TOKENS)
    if any(pattern.search(normalized) for pattern in CAMERA_LENS_ZOOM_SIGNATURE_PATTERNS):
        return True
    if has_brand_context and any(pattern.search(normalized) for pattern in CAMERA_LENS_PRIME_SIGNATURE_PATTERNS):
        return True
    if has_brand_context and any(pattern.search(compact) or pattern.search(slug) for pattern in CAMERA_LENS_TIGHT_SIGNATURE_PATTERNS):
        return True
    if has_brand_context and any(signature in compact for signature in CAMERA_LENS_COMPACT_SIGNATURES):
        return True
    if has_brand_context and any(signature in slug for signature in CAMERA_LENS_COMPACT_SIGNATURES):
        return True

    focal_match = re.search(r"(?<![a-z0-9])\d{1,3}(?:\s*-\s*\d{1,3})?\s*mm(?![a-z0-9])", normalized, re.IGNORECASE)
    aperture_match = re.search(r"(?<![a-z0-9])f\s*/?\s*\d(?:\.\d)?(?![a-z0-9])", normalized, re.IGNORECASE)
    focal_aperture_pattern = re.compile(
        r"(?<![a-z0-9])\d{1,3}(?:\s*-\s*\d{1,3})?(?:\s*mm)?\s*(?:f\s*/?\s*|/)\d(?:\.\d)?(?![a-z0-9])",
        re.IGNORECASE,
    )
    if focal_match and aperture_match:
        return True
    if focal_aperture_pattern.search(normalized):
        return True

    has_mount_context = _camera_title_has_lens_mount_context(normalized)
    if has_mount_context and re.search(r"\d{1,3}(?:\s*-\s*\d{1,3})?(?:\s*mm)?", normalized, re.IGNORECASE):
        return True
    if has_support_context and re.search(r"\d{2,3}(?:\s*[-~至到/]\s*\d{2,3})?(?:\s*mm)?", normalized, re.IGNORECASE):
        return True
    if any(pattern.search(normalized) for pattern in CAMERA_LENS_NORMALIZED_PATTERNS):
        return True
    return any(pattern.search(compact) for pattern in CAMERA_LENS_COMPACT_PATTERNS)


def _camera_title_has_lens_mount_context(normalized: str) -> bool:
    return any(pattern.search(normalized) for pattern in CAMERA_LENS_MOUNT_PATTERNS)


def _camera_title_has_lens_prefix_signal(normalized: str, compact: str) -> bool:
    prefix = _camera_title_leading_clause(normalized)
    compact_prefix = re.sub(r"[\s\-_+/（）()]+", "", prefix)
    if any(token in prefix for token in CAMERA_LENS_KEYWORD_TOKENS):
        return True
    if any(token in prefix for token in CAMERA_LENS_DESCRIPTOR_TOKENS):
        return True
    if _camera_title_has_lens_identity_signal(prefix, compact_prefix):
        return True
    return False


def _title_matches_camera_body_domain(lowered_title: str) -> bool:
    normalized, compact = _camera_title_normalized_parts(lowered_title)
    if not normalized:
        return False
    if _camera_title_has_body_non_target_signal(normalized):
        return False
    lens_identity = _camera_title_has_lens_identity_signal(normalized, compact)
    if _camera_title_has_body_primary_signal(normalized):
        return True
    if lens_identity and not _camera_title_has_lens_prefix_signal(normalized, compact):
        return False
    return _camera_title_has_body_model_signal(normalized) and not lens_identity


def _title_matches_camera_interchangeable_lens_domain(lowered_title: str) -> bool:
    normalized, compact = _camera_title_normalized_parts(lowered_title)
    if not normalized:
        return False
    if not _camera_title_has_lens_identity_signal(normalized, compact):
        return False
    if _camera_title_has_body_primary_signal(normalized) and not _camera_title_has_lens_prefix_signal(normalized, compact):
        return False
    return True


def _title_garmin_watch_mismatch_reason(title: str | None) -> str | None:
    if _title_matches_garmin_watch_domain(title or ""):
        return None
    normalized = str(title or "").strip().lower()
    compact = re.sub(r"[\s\-_+/（）()]+", "", normalized)
    wrong_token_groups = (
        ("apple_watch_like", ("apple watch", "watch ultra", "watch series", "iwatch")),
        ("competitor_watch_like", ("coros", "高驰", "suunto", "颂拓", "amazfit", "华米")),
        ("computer_or_mobile_like", ("macbook", "电脑", "笔记本", "iphone", "ipad", "手机")),
        ("drone_or_device_like", ("dji", "大疆", "无人机", "飞控", "航模", "遥控", "地面站", "录像机", "海康")),
        ("camera_like", ("镜头", "相机", "机身")),
    )
    for reason, tokens in wrong_token_groups:
        for token in tokens:
            lowered_token = token.lower()
            if lowered_token in normalized or re.sub(r"\s+", "", lowered_token) in compact:
                return reason
    return None


def _title_matches_garmin_watch_domain(lowered_title: str) -> bool:
    normalized = str(lowered_title or "").strip().lower()
    if not normalized:
        return False
    compact = re.sub(r"[\s\-_+/（）()]+", "", normalized)

    hard_negative_tokens = (
        "macbook",
        "iphone",
        "ipad",
        "applewatch",
        "apple watch",
        "airpods",
        "大疆",
        "dji",
        "无人机",
        "飞控",
        "航模",
        "镜头",
        "相机",
        "机身",
        "录像机",
        "海康",
        "硬盘录像机",
    )
    if any(token in normalized or token in compact for token in hard_negative_tokens):
        return False

    strong_brand_tokens = ("garmin", "佳明")
    strong_family_tokens = (
        "fenix",
        "forerunner",
        "instinct",
        "epix",
        "tactix",
        "enduro",
        "descent",
        "marq",
        "venu",
        "approach",
        "vivoactive",
        "vivomove",
        "quatix",
        "lily",
    )
    watch_context_tokens = (
        "手表",
        "表",
        "运动表",
        "跑表",
        "gps",
        "心率",
        "血氧",
        "太阳能",
        "solar",
        "蓝宝石",
        "sapphire",
        "amoled",
        "47mm",
        "51mm",
        "42mm",
        "43mm",
        "45mm",
        "49mm",
    )

    if any(token in normalized for token in strong_brand_tokens):
        return True
    if any(token in normalized for token in strong_family_tokens):
        return True

    shorthand_watch_patterns = (
        re.compile(r"\b(165|255|265|955|965)\b"),
        re.compile(r"飞\s*(7|8)(?:\s*pro)?", re.IGNORECASE),
        re.compile(r"泰\s*8", re.IGNORECASE),
        re.compile(r"本能\s*[123]", re.IGNORECASE),
    )
    has_shorthand = any(pattern.search(normalized) for pattern in shorthand_watch_patterns)
    has_watch_context = any(token in normalized or token in compact for token in watch_context_tokens)
    return has_shorthand and has_watch_context


def title_is_non_comparable_listing(
    *,
    business_domain: str,
    title: str | None,
    price: Decimal | float | int | None = None,
) -> bool:
    if not title:
        return True
    normalized = title.strip()
    lowered = normalized.lower()
    compact_lowered = re.sub(r"\s+", "", lowered)
    resolved_scope = resolve_category_code(business_domain)
    normalized_price = decimal_to_float(price) if isinstance(price, Decimal) else (float(price) if price is not None else None)

    def contains(token: str) -> bool:
        lowered_token = token.lower()
        compact_token = re.sub(r"\s+", "", lowered_token)
        return lowered_token in lowered or compact_token in compact_lowered

    if any(pattern.search(normalized) for pattern in WANTED_TITLE_PATTERNS):
        return True
    if any(pattern.search(normalized) for pattern in SOLD_TITLE_PATTERNS):
        return True
    if any(token in normalized for token in WANTED_TITLE_SUBSTRINGS):
        return True
    if any(pattern.search(normalized) for pattern in BUYBACK_TITLE_PATTERNS):
        return True
    if has_commercial_listing_signal(normalized):
        return True
    if resolved_scope in {"camera_body", "camera_interchangeable_lens"}:
        if any(contains(token) for token in ("出租", "租赁", "租机", "租用")):
            return True

    if is_apple_computer_scope(business_domain):
        if "套装" in normalized:
            return True
        if "studio display" in lowered:
            return True
        if "显示器" in normalized and "mac studio" in lowered:
            return True
    if is_garmin_watch_scope(business_domain):
        if any(contains(token) for token in GARMIN_WATCHFACE_SERVICE_TOKENS):
            return True
        if normalized_price is not None and normalized_price <= 300:
            if any(contains(token) for token in GARMIN_ACCESSORY_SERVICE_TOKENS):
                return True
            if any(contains(token) for token in GARMIN_BAND_ACCESSORY_TOKENS) and any(
                contains(token) for token in GARMIN_BAND_ACCESSORY_HINT_TOKENS
            ):
                return True
        if normalized_price is not None and normalized_price <= 150:
            if any(contains(token) for token in GARMIN_LOW_PRICE_ACCESSORY_TOKENS):
                return True
        if normalized_price is not None and normalized_price <= 50:
            placeholder_signal = any(contains(token) for token in GARMIN_LOW_PRICE_PLACEHOLDER_TOKENS)
            exchange_signal = contains("置换") and (
                contains("全新") or contains("正品") or contains("国行") or contains("可议价")
            )
            damage_signal = any(contains(token) for token in GARMIN_LOW_PRICE_PLACEHOLDER_DAMAGE_TOKENS)
            if (placeholder_signal or exchange_signal) and not damage_signal:
                return True
    if resolved_scope == "camera_body":
        body_normalized, _ = _camera_title_normalized_parts(normalized)
        if _camera_title_has_body_non_target_signal(body_normalized):
            return True
    if resolved_scope == "camera_interchangeable_lens":
        if lens_title_is_non_target_body_listing(normalized):
            return True

    return False


def has_commercial_listing_signal(title: str) -> bool:
    lowered = title.lower()
    compact_lowered = re.sub(r"\s+", "", lowered)

    def contains(token: str) -> bool:
        lowered_token = token.lower()
        compact_token = re.sub(r"\s+", "", lowered_token)
        return lowered_token in lowered or compact_token in compact_lowered

    strong_hits = sum(contains(token) for token in COMMERCIAL_LISTING_STRONG_TOKENS)
    hint_hits = sum(contains(token) for token in COMMERCIAL_LISTING_HINT_TOKENS)
    many_price_points = len(re.findall(r"\b\d{4,5}\b", title)) >= 3
    size_variants = {match for match in re.findall(r"(42|43|47|51)\s*mm", lowered)}
    multi_variant_signal = (
        len(size_variants) >= 2
        or ("amoled" in lowered and "mip" in lowered)
    )
    if any(contains(token) for token in COMMERCIAL_LISTING_STANDALONE_TOKENS):
        return True
    return (
        strong_hits >= 2
        or (strong_hits >= 1 and (hint_hits >= 1 or multi_variant_signal or many_price_points))
        or (hint_hits >= 2 and ("全新" in compact_lowered or "未拆" in compact_lowered or "现货" in compact_lowered))
        or (multi_variant_signal and (hint_hits >= 1 or many_price_points))
    )


__all__ = [
    "aggregate_pricing_view",
    "build_model_discovery",
    "build_pricing_views",
    "build_spec_summary",
    "classify_opportunity_tier",
    "compute_opportunity_score",
    "compute_profit_margin_pct",
    "filter_outlier_price_records",
    "load_pricing_records",
    "minimum_actionable_profit_amount",
    "percentile",
    "reliability_tier",
    "resolve_pricing_record",
    "resolve_pricing_scope",
    "round_money",
    "sort_last_seen",
    "spec_dimension_payload",
    "title_is_non_comparable_listing",
    "title_matches_domain",
]
