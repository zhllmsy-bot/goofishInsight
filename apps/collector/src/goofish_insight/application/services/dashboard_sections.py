from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...category_compat import resolve_category_code
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
    build_overview,
    build_recent_items,
    build_recent_runs,
    build_top_models,
    dashboard_pricing_read_cache_signature,
    load_dashboard_pricing_records,
    load_available_domains,
)
from .llm_prompt_traces import build_dashboard_llm_traces_section_data as build_llm_trace_panel_data
from .mobile_market_dashboard import (
    build_mobile_market_calibration_panel,
    merge_mobile_market_into_top_models,
)
from .pricing_thresholds import evaluate_pricing_row_availability
from .pricing_templates import annotate_visible_filter_fields, build_pricing_contract
from .template_feature_flags import price_template_feature_flags
from .web_section_cache import get_ttl_cached_payload
from ...pricing import build_pricing_gate_summary

DASHBOARD_FILTER_KEYS = (
    "product_label",
    "spec_label",
    "display_type",
    "case_size_mm",
    "is_solar",
    "chip_family",
    "screen_size_in",
    "memory_gb",
    "storage_gb",
)


@dataclass(frozen=True, slots=True)
class DashboardSectionOptions:
    business_domain: str | None
    limit: int
    pricing_view: str
    pricing_scope: str
    pricing_limit: int
    pricing_freshness_days: int
    heartbeat_days: int
    pricing_min_samples: int
    raw_filters: dict[str, str | None]
    category_code: str | None = None

    def requested_scope(self) -> str | None:
        return self.category_code or self.business_domain

    def normalized_category_code(self) -> str | None:
        canonical_code = resolve_category_code(self.requested_scope())
        return canonical_code or None

    def scope_filter_value(self) -> str | None:
        return self.normalized_category_code() or self.requested_scope()

    def normalized_pricing_view(self) -> str:
        return self.pricing_view if self.pricing_view in PRICING_VIEW_LABELS else "product"

    def base_context_key(self) -> tuple[Any, ...]:
        pricing_read_signature = dashboard_pricing_read_cache_signature()
        return (
            self.normalized_category_code(),
            self.pricing_freshness_days,
            self.heartbeat_days,
            *pricing_read_signature,
            tuple(self.raw_filters.get(key) for key in DASHBOARD_FILTER_KEYS),
        )

    def overview_key(self) -> tuple[Any, ...]:
        return (
            self.normalized_category_code(),
            self.pricing_freshness_days,
            self.heartbeat_days,
        )

    def items_key(self) -> tuple[Any, ...]:
        return (
            *self.base_context_key(),
            self.limit,
        )

    def pricing_key(self) -> tuple[Any, ...]:
        return (
            *self.base_context_key(),
            self.normalized_pricing_view(),
            self.pricing_scope,
            self.pricing_limit,
            self.pricing_min_samples,
        )

    def calibration_key(self) -> tuple[Any, ...]:
        return (
            *self.base_context_key(),
            self.pricing_min_samples,
        )


def _normalize_selected_filters(
    *,
    business_domain: str | None,
    raw_filters: dict[str, str | None],
    session=None,
) -> dict[str, Any]:
    return sanitize_structured_filters(
        business_domain=business_domain,
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


def build_dashboard_base_context(session, *, options: DashboardSectionOptions) -> dict[str, Any]:
    def builder() -> dict[str, Any]:
        scope_value = options.scope_filter_value()
        category_code = options.normalized_category_code()
        selected_filters = _normalize_selected_filters(
            business_domain=scope_value,
            raw_filters=options.raw_filters,
            session=session,
        )
        # Pricing/trend/filter selectors should use the selected freshness window.
        # Heartbeat remains an operational freshness signal for overview panels,
        # but should not silently trim model/template candidate sets here.
        pricing_read = load_dashboard_pricing_records(
            session,
            business_domain=options.business_domain,
            category_code=category_code,
            freshness_days=options.pricing_freshness_days,
            heartbeat_days=None,
        )
        pricing_records = list(pricing_read.get("records") or [])
        filter_catalog = build_filter_catalog(
            pricing_records,
            selected_filters,
            business_domain=scope_value,
        )
        visible_filter_fields = build_visible_filter_fields(
            business_domain=scope_value,
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
        pricing_contract = build_pricing_contract(
            business_domain=scope_value,
            selected_filters=selected_filters,
            filter_catalog=filter_catalog,
            session=session,
        )
        return {
            "selected_filters": selected_filters,
            "selected_filter_values": stringify_selected_filters(selected_filters),
            "active_filter_summary": build_active_filter_summary(selected_filters),
            "filter_catalog": filter_catalog,
            "visible_filter_fields": annotate_visible_filter_fields(
                visible_filter_fields,
                pricing_contract=pricing_contract,
            ),
            "pricing_records": pricing_records,
            "pricing_read_source": pricing_read.get("readSource"),
            "pricing_read_mode": pricing_read.get("readMode"),
            "pricing_catalog_record_count": int(pricing_read.get("catalogRecordCount") or 0),
            "pricing_legacy_record_count": int(pricing_read.get("legacyRecordCount") or 0),
            "pricing_fallback_used": bool(pricing_read.get("fallbackUsed")),
            "pricing_fallback_reason": pricing_read.get("fallbackReason"),
            "pricing_legacy_fallback_enabled": bool(pricing_read.get("legacyFallbackEnabled", True)),
            "filtered_item_ids": filtered_item_ids,
            "pricing_contract": pricing_contract,
            "template_feature_flags": price_template_feature_flags(),
        }

    return get_ttl_cached_payload(
        namespace="dashboard-base",
        key=options.base_context_key(),
        ttl_seconds=20.0,
        builder=builder,
    )


def build_dashboard_overview_context(session, *, options: DashboardSectionOptions) -> dict[str, Any]:
    def builder() -> dict[str, Any]:
        category_code = options.normalized_category_code()
        return {
            "overview": build_overview(
                session,
                business_domain=options.business_domain,
                category_code=category_code,
                window_days=options.pricing_freshness_days,
                heartbeat_days=options.heartbeat_days,
            ),
            "domain_cards": build_domain_cards(
                session,
                business_domain=options.business_domain,
                category_code=category_code,
                window_days=options.pricing_freshness_days,
                heartbeat_days=options.heartbeat_days,
            ),
        }

    return get_ttl_cached_payload(
        namespace="dashboard-overview",
        key=options.overview_key(),
        ttl_seconds=15.0,
        builder=builder,
    )


def build_dashboard_hero_section_data(session, *, options: DashboardSectionOptions) -> dict[str, Any]:
    overview_context = build_dashboard_overview_context(session, options=options)
    return {
        "selected_domain": options.requested_scope(),
        "selected_category_code": options.normalized_category_code(),
        "overview": overview_context["overview"],
    }


def build_dashboard_filters_section_data(session, *, options: DashboardSectionOptions) -> dict[str, Any]:
    base_context = build_dashboard_base_context(session, options=options)
    available_domains = load_available_domains(session)
    return {
        "selected_domain": options.requested_scope(),
        "selected_category_code": options.normalized_category_code(),
        "limit": options.limit,
        "pricing_view": options.normalized_pricing_view(),
        "pricing_scope": options.pricing_scope,
        "pricing_limit": options.pricing_limit,
        "pricing_freshness_days": options.pricing_freshness_days,
        "heartbeat_days": options.heartbeat_days,
        "pricing_min_samples": options.pricing_min_samples,
        "pricing_view_options": list(PRICING_VIEW_LABELS.items()),
        "available_domains": available_domains,
        "available_categories": available_domains,
        "selected_filters": base_context["selected_filters"],
        "selected_filter_values": base_context["selected_filter_values"],
        "active_filter_summary": base_context["active_filter_summary"],
        "filter_catalog": base_context["filter_catalog"],
        "visible_filter_fields": base_context["visible_filter_fields"],
        "pricing_contract": base_context["pricing_contract"],
        "template_feature_flags": base_context["template_feature_flags"],
    }


def build_dashboard_focus_section_data(session, *, options: DashboardSectionOptions) -> dict[str, Any]:
    base_context = build_dashboard_base_context(session, options=options)
    return {
        "market_focus_cards": build_market_focus(
            pricing_records=base_context["pricing_records"],
            filters=base_context["selected_filters"],
            min_sample_points=options.pricing_min_samples,
            pricing_contract=base_context["pricing_contract"],
        )
    }


def build_dashboard_insights_section_data(session, *, options: DashboardSectionOptions) -> dict[str, Any]:
    base_context = build_dashboard_base_context(session, options=options)
    overview_context = build_dashboard_overview_context(session, options=options)
    trend_pricing_records = filter_pricing_records(
        base_context["pricing_records"],
        base_context["selected_filters"],
    )
    return {
        "overview": overview_context["overview"],
        "domain_cards": overview_context["domain_cards"],
        "template_feature_flags": base_context["template_feature_flags"],
        "domain_trend_cards": build_domain_trend_cards(
            session,
            business_domain=options.business_domain,
            category_code=options.normalized_category_code(),
            window_days=options.pricing_freshness_days,
            heartbeat_days=options.heartbeat_days,
            pricing_records=trend_pricing_records,
            pricing_contract=base_context["pricing_contract"],
            filtered_item_ids=base_context["filtered_item_ids"],
        ),
    }


def build_dashboard_pricing_section_data(session, *, options: DashboardSectionOptions) -> dict[str, Any]:
    def builder() -> dict[str, Any]:
        base_context = build_dashboard_base_context(session, options=options)
        pricing_panel = build_pricing_band_panel(
            pricing_records=base_context["pricing_records"],
            filters=base_context["selected_filters"],
            pricing_view=options.normalized_pricing_view(),
            actionable_only=options.pricing_scope != "all",
            min_sample_points=options.pricing_min_samples,
            limit=options.pricing_limit,
            freshness_days=options.pricing_freshness_days,
        )
        pricing_panel = _annotate_pricing_panel_availability(
            pricing_panel,
            pricing_contract=base_context["pricing_contract"],
        )
        return {
            "pricing_panel": pricing_panel,
            "pricing_gate_summary": build_pricing_gate_summary(
                session=session,
                business_domain=options.business_domain,
                category_code=options.normalized_category_code(),
                freshness_days=options.pricing_freshness_days,
                heartbeat_days=options.heartbeat_days,
                pricing_pool_count=len(base_context["pricing_records"]),
            ),
            "active_filter_summary": base_context["active_filter_summary"],
            "heartbeat_days": options.heartbeat_days,
            "pricing_contract": base_context["pricing_contract"],
            "pricing_availability": pricing_panel.get("selected_pricing_availability"),
            "template_feature_flags": base_context["template_feature_flags"],
        }

    return get_ttl_cached_payload(
        namespace="dashboard-pricing",
        key=options.pricing_key(),
        ttl_seconds=20.0,
        builder=builder,
    )


def build_dashboard_ops_section_data(session, *, options: DashboardSectionOptions) -> dict[str, Any]:
    overview_context = build_dashboard_overview_context(session, options=options)
    return {
        "overview": overview_context["overview"],
        "domain_cards": overview_context["domain_cards"],
        "recent_runs": build_recent_runs(session),
    }


def build_dashboard_llm_traces_section_data() -> dict[str, Any]:
    return get_ttl_cached_payload(
        namespace="dashboard-llm-traces",
        key=("latest",),
        ttl_seconds=3.0,
        builder=lambda: build_llm_trace_panel_data(),
    )


def build_dashboard_calibration_section_data(session, *, options: DashboardSectionOptions) -> dict[str, Any]:
    def builder() -> dict[str, Any]:
        base_context = build_dashboard_base_context(session, options=options)
        top_models = build_top_models(
            session,
            business_domain=options.business_domain,
            category_code=options.normalized_category_code(),
            window_days=options.pricing_freshness_days,
            heartbeat_days=options.heartbeat_days,
            filtered_item_ids=base_context["filtered_item_ids"],
        )
        mobile_market_panel = build_mobile_market_calibration_panel(
            business_domain=options.scope_filter_value(),
            top_models=top_models,
        )
        return {
            "mobile_market_panel": mobile_market_panel,
            "top_models": merge_mobile_market_into_top_models(top_models, mobile_market_panel["rows"]),
        }

    return get_ttl_cached_payload(
        namespace="dashboard-calibration",
        key=options.calibration_key(),
        ttl_seconds=20.0,
        builder=builder,
    )


def build_dashboard_items_section_data(session, *, options: DashboardSectionOptions) -> dict[str, Any]:
    def builder() -> dict[str, Any]:
        base_context = build_dashboard_base_context(session, options=options)
        return {
            "items": build_recent_items(
                session,
                business_domain=options.business_domain,
                category_code=options.normalized_category_code(),
                limit=options.limit,
                window_days=options.pricing_freshness_days,
                heartbeat_days=options.heartbeat_days,
                filtered_item_ids=base_context["filtered_item_ids"],
            )
        }

    return get_ttl_cached_payload(
        namespace="dashboard-items",
        key=options.items_key(),
        ttl_seconds=15.0,
        builder=builder,
    )


def _annotate_pricing_panel_availability(
    pricing_panel: dict[str, Any],
    *,
    pricing_contract: dict[str, Any],
) -> dict[str, Any]:
    template_complete = bool(
        ((pricing_contract or {}).get("templateCompleteness") or {}).get("isComplete")
    )
    rows = []
    for row in pricing_panel.get("rows", []):
        availability = evaluate_pricing_row_availability(row, template_complete=template_complete)
        rows.append(
            {
                **row,
                "pricingAvailability": availability,
                "pricingAvailabilitySummary": dict(availability.get("pricingSummary") or {}),
            }
        )

    selected_row = rows[0] if rows else None
    selected_pricing_availability = evaluate_pricing_row_availability(
        selected_row or {},
        template_complete=template_complete,
    )

    return {
        **pricing_panel,
        "rows": rows,
        "selected_pricing_availability": selected_pricing_availability,
        "selected_pricing_availability_summary": dict(selected_pricing_availability.get("pricingSummary") or {}),
    }
