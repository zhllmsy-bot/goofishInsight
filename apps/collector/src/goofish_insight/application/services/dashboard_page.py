from __future__ import annotations

from typing import Any

from ...category_compat import resolve_category_code
from ...pricing import build_pricing_gate_summary
from ...presentation.web import PRICING_VIEW_LABELS
from .dashboard_filters import (
    build_active_filter_summary,
    build_filter_catalog,
    build_visible_filter_fields,
    filter_pricing_records,
    has_structured_filters,
    normalize_optional_bool,
    normalize_optional_float,
    normalize_optional_int,
    normalize_optional_text,
    sanitize_structured_filters,
    stringify_selected_filters,
)
from .dashboard_panels import build_market_focus, build_pricing_band_panel
from .dashboard_queries import (
    build_domain_cards,
    build_domain_trend_cards,
    build_item_detail,
    build_overview,
    build_recent_items,
    build_recent_runs,
    build_top_models,
    load_dashboard_pricing_records,
    load_available_domains,
)
from .mobile_market_dashboard import (
    build_mobile_market_calibration_panel,
    merge_mobile_market_into_top_models,
)
from .pricing_templates import build_pricing_contract


def build_dashboard_page_data(
    session,
    *,
    business_domain: str | None,
    category_code: str | None = None,
    limit: int,
    pricing_view: str,
    pricing_scope: str,
    pricing_limit: int,
    pricing_freshness_days: int,
    heartbeat_days: int,
    pricing_min_samples: int,
    raw_filters: dict[str, str | None],
) -> dict[str, Any]:
    selected_scope = category_code or business_domain
    canonical_category_code = resolve_category_code(selected_scope) or None
    normalized_pricing_view = pricing_view if pricing_view in PRICING_VIEW_LABELS else "product"
    actionable_only = pricing_scope != "all"
    selected_filters = sanitize_structured_filters(
        business_domain=canonical_category_code or selected_scope,
        filters={
            "product_label": normalize_optional_text(raw_filters.get("product_label")),
            "spec_label": normalize_optional_text(raw_filters.get("spec_label")),
            "display_type": normalize_optional_text(raw_filters.get("display_type")),
            "case_size_mm": normalize_optional_int(raw_filters.get("case_size_mm")),
            "is_solar": normalize_optional_bool(raw_filters.get("is_solar")),
            "chip_family": normalize_optional_text(raw_filters.get("chip_family")),
            "screen_size_in": normalize_optional_float(raw_filters.get("screen_size_in")),
            "memory_gb": normalize_optional_int(raw_filters.get("memory_gb")),
            "storage_gb": normalize_optional_int(raw_filters.get("storage_gb")),
        },
        session=session,
    )

    pricing_read = load_dashboard_pricing_records(
        session,
        business_domain=business_domain,
        category_code=canonical_category_code,
        freshness_days=pricing_freshness_days,
        heartbeat_days=heartbeat_days,
    )
    pricing_records = list(pricing_read.get("records") or [])
    filter_catalog = build_filter_catalog(
        pricing_records,
        selected_filters,
        business_domain=canonical_category_code or selected_scope,
    )
    visible_filter_fields = build_visible_filter_fields(
        business_domain=canonical_category_code or selected_scope,
        filter_catalog=filter_catalog,
        selected_filters=selected_filters,
        session=session,
    )
    filtered_records = filter_pricing_records(pricing_records, selected_filters)
    filtered_item_ids = (
        {record["item_id"] for record in filtered_records}
        if has_structured_filters(selected_filters)
        else None
    )

    top_models = build_top_models(
        session,
        business_domain=business_domain,
        category_code=canonical_category_code,
        window_days=pricing_freshness_days,
        heartbeat_days=heartbeat_days,
        filtered_item_ids=filtered_item_ids,
    )
    mobile_market_panel = build_mobile_market_calibration_panel(
        business_domain=canonical_category_code or selected_scope,
        top_models=top_models,
    )
    top_models = merge_mobile_market_into_top_models(top_models, mobile_market_panel["rows"])

    available_domains = load_available_domains(session)
    return {
        "selected_domain": selected_scope,
        "selected_category_code": canonical_category_code,
        "limit": limit,
        "pricing_view": normalized_pricing_view,
        "pricing_scope": pricing_scope,
        "pricing_limit": pricing_limit,
        "pricing_freshness_days": pricing_freshness_days,
        "heartbeat_days": heartbeat_days,
        "pricing_min_samples": pricing_min_samples,
        "pricing_read_source": pricing_read.get("readSource"),
        "pricing_read_mode": pricing_read.get("readMode"),
        "pricing_catalog_record_count": int(pricing_read.get("catalogRecordCount") or 0),
        "pricing_legacy_record_count": int(pricing_read.get("legacyRecordCount") or 0),
        "pricing_fallback_used": bool(pricing_read.get("fallbackUsed")),
        "pricing_fallback_reason": pricing_read.get("fallbackReason"),
        "pricing_legacy_fallback_enabled": bool(pricing_read.get("legacyFallbackEnabled", True)),
        "pricing_view_options": list(PRICING_VIEW_LABELS.items()),
        "available_domains": available_domains,
        "available_categories": available_domains,
        "selected_filters": selected_filters,
        "selected_filter_values": stringify_selected_filters(selected_filters),
        "active_filter_summary": build_active_filter_summary(selected_filters),
        "filter_catalog": filter_catalog,
        "visible_filter_fields": visible_filter_fields,
        "market_focus_cards": build_market_focus(
            pricing_records=pricing_records,
            filters=selected_filters,
            min_sample_points=pricing_min_samples,
            pricing_contract=build_pricing_contract(
                business_domain=canonical_category_code or selected_scope,
                selected_filters=selected_filters,
                filter_catalog=filter_catalog,
                session=session,
            ),
        ),
        "overview": build_overview(
            session,
            business_domain=business_domain,
            category_code=canonical_category_code,
            window_days=pricing_freshness_days,
            heartbeat_days=heartbeat_days,
        ),
        "domain_cards": build_domain_cards(
            session,
            business_domain=business_domain,
            category_code=canonical_category_code,
            window_days=pricing_freshness_days,
            heartbeat_days=heartbeat_days,
        ),
        "domain_trend_cards": build_domain_trend_cards(
            session,
            business_domain=business_domain,
            category_code=canonical_category_code,
            window_days=pricing_freshness_days,
            heartbeat_days=heartbeat_days,
            pricing_records=pricing_records,
            pricing_contract=build_pricing_contract(
                business_domain=canonical_category_code or selected_scope,
                selected_filters=selected_filters,
                filter_catalog=filter_catalog,
                session=session,
            ),
        ),
        "mobile_market_panel": mobile_market_panel,
        "top_models": top_models,
        "pricing_panel": build_pricing_band_panel(
            pricing_records=pricing_records,
            filters=selected_filters,
            pricing_view=normalized_pricing_view,
            actionable_only=actionable_only,
            min_sample_points=pricing_min_samples,
            limit=pricing_limit,
            freshness_days=pricing_freshness_days,
        ),
        "pricing_gate_summary": build_pricing_gate_summary(
            session=session,
            business_domain=business_domain,
            category_code=canonical_category_code,
            freshness_days=pricing_freshness_days,
            heartbeat_days=heartbeat_days,
            pricing_pool_count=len(pricing_records),
        ),
        "recent_runs": build_recent_runs(session),
        "items": build_recent_items(
            session,
            business_domain=business_domain,
            category_code=canonical_category_code,
            limit=limit,
            window_days=pricing_freshness_days,
            heartbeat_days=heartbeat_days,
            filtered_item_ids=filtered_item_ids,
        ),
    }
