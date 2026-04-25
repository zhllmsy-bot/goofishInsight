from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError, URLError

from ...compat import UTC
from ...db import session_scope
from ...pricing import build_model_discovery
from ...settings import get_settings
from .pricing_templates import build_pricing_contract
from .pricing_thresholds import evaluate_pricing_row_availability


def reports_dir() -> Path:
    path = get_settings().base_dir / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_report_path() -> Path:
    return reports_dir() / "latest-model-discovery.json"


def write_model_discovery_report(
    *,
    business_domain: str | None,
    category_code: str | None,
    limit: int,
    freshness_days: int,
    min_sample_points: int,
    output: Path | None,
) -> Path:
    rows = build_model_discovery(
        business_domain=business_domain,
        category_code=category_code,
        freshness_days=freshness_days,
        min_sample_points=min_sample_points,
    )
    rows = _annotate_rows_with_availability(
        category_scope=category_code or business_domain,
        rows=rows,
    )
    by_domain: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_domain[row["category_code"]][row["view"]].append(row)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "business_domain": business_domain,
        "category_code": category_code or business_domain,
        "algorithm": {
            "freshness_days": freshness_days,
            "min_sample_points": min_sample_points,
            "listing_filters": [
                "current_price > 0",
                "is_active = true",
                "exclude ads",
                "exclude auctions",
                "last_seen_at within freshness window",
            ],
            "grouping": {
                "brand": "brand",
                "product": "brand + normalized product",
                "spec": "product + exact spec dimensions",
            },
            "pricing_method": "seller-median collapse -> log MAD filter -> IQR fence -> low-quantile buy zone",
            "buy_zone_definition": {
                "buy_floor_price": "P15 of cleaned seller medians",
                "target_buy_ceiling": "P35 of cleaned seller medians",
                "fair_price": "P50 / median of cleaned seller medians",
            },
        },
        "domains": {},
    }
    for domain, view_map in by_domain.items():
        report["domains"][domain] = {
            "brand": view_map["brand"][:limit],
            "product": view_map["product"][:limit],
            "spec": view_map["spec"][:limit],
        }

    output_path = output or reports_dir() / f"model-discovery-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    output_path.write_text(payload, encoding="utf-8")
    latest_report_path().write_text(payload, encoding="utf-8")
    return output_path
def _annotate_rows_with_availability(
    *,
    category_scope: str | None,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not rows:
        return rows
    with session_scope() as session:
        pricing_contract = build_pricing_contract(
            business_domain=category_scope,
            selected_filters={},
            filter_catalog={},
            session=session,
        )
    template_complete = bool(((pricing_contract or {}).get("templateCompleteness") or {}).get("isComplete"))
    return [
        {
            **row,
            "pricingAvailability": availability,
            "pricingAvailabilitySummary": dict(availability.get("pricingSummary") or {}),
        }
        for row in rows
        for availability in (evaluate_pricing_row_availability(row, template_complete=template_complete),)
    ]


def run_template_mode_smoke(
    *,
    base_url: str,
    category_code: str,
    window_days: int,
    limit: int,
    pricing_view: str,
    pricing_scope: str,
    pricing_limit: int,
    pricing_freshness_days: int,
    heartbeat_days: int,
    pricing_min_samples: int,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    monitor = _http_get_json(
        base_url=base_url,
        path="/api/buy/template-monitoring",
        params={
            "category_code": category_code,
            "window_days": window_days,
        },
    )
    checks.append(_api_check("template-monitoring", monitor))
    monitoring_payload = dict(monitor.get("payload") or {})
    flags = dict(monitoring_payload.get("featureFlags") or {})
    checks.append(_feature_flag_check(flags))
    checks.append(
        _tier_distribution_check(
            baseline_tiers=dict(dict(monitoring_payload.get("baseline") or {}).get("tierCounts") or {}),
            opportunity_tiers=dict(dict(monitoring_payload.get("opportunity") or {}).get("tierCounts") or {}),
        )
    )

    opportunities = _http_get_json(
        base_url=base_url,
        path="/api/buy/opportunities",
        params={
            "category_code": category_code,
            "limit": limit,
        },
    )
    checks.append(_api_check("buy-opportunities", opportunities))
    opportunity_payload = dict(opportunities.get("payload") or {})
    summary = dict(opportunity_payload.get("summary") or {})
    checks.append(
        _simple_check(
            "opportunity-summary",
            "pass"
            if summary and "calibrationRecommendationCount" in summary and "feedbackCount" in summary
            else "warn",
            (
                f"opportunities={summary.get('opportunityCount')} "
                f"feedback={summary.get('feedbackCount')} "
                f"calibration={summary.get('calibrationRecommendationCount')}"
            )
            if summary
            else "missing summary",
        )
    )

    base_pricing_params = {
        "business_domain": category_code,
        "pricing_view": pricing_view,
        "pricing_scope": pricing_scope,
        "pricing_limit": pricing_limit,
        "pricing_freshness_days": pricing_freshness_days,
        "heartbeat_days": heartbeat_days,
        "pricing_min_samples": pricing_min_samples,
    }
    pricing_base = _http_get_json(
        base_url=base_url,
        path="/api/dashboard/sections/pricing",
        params=base_pricing_params,
    )
    checks.append(_api_check("dashboard-pricing-base", pricing_base))
    pricing_base_payload = dict(pricing_base.get("payload") or {})
    base_contract = dict(pricing_base_payload.get("pricing_contract") or {})
    base_completeness = dict(base_contract.get("templateCompleteness") or {})
    checks.append(
        _simple_check(
            "pricing-contract-present",
            "pass" if base_contract else "fail",
            f"contractSource={base_contract.get('contractSource')}" if base_contract else "pricing_contract missing",
        )
    )
    checks.append(
        _simple_check(
            "pricing-base-completeness",
            "pass" if base_completeness.get("status") in {"missing", "partial", "complete", "legacy"} else "warn",
            (
                f"status={base_completeness.get('status')} "
                f"missing={len(base_contract.get('missingPricingFields') or [])}"
            ),
        )
    )

    filters = _http_get_json(
        base_url=base_url,
        path="/api/dashboard/sections/filters",
        params={
            "business_domain": category_code,
            "pricing_view": pricing_view,
            "pricing_scope": pricing_scope,
            "pricing_limit": pricing_limit,
            "pricing_freshness_days": pricing_freshness_days,
            "heartbeat_days": heartbeat_days,
            "pricing_min_samples": pricing_min_samples,
        },
    )
    checks.append(_api_check("dashboard-filters", filters))
    filter_payload = dict(filters.get("payload") or {})
    filter_catalog = dict(filter_payload.get("filter_catalog") or {})
    selector_params, unresolved_selector_fields = _build_selector_params_for_required_fields(
        required_selector_fields=list(base_contract.get("requiredSelectorFields") or []),
        filter_catalog=filter_catalog,
    )
    pricing_selected = _http_get_json(
        base_url=base_url,
        path="/api/dashboard/sections/pricing",
        params={
            **base_pricing_params,
            **selector_params,
        },
    )
    checks.append(_api_check("dashboard-pricing-selected", pricing_selected))
    selected_payload = dict(pricing_selected.get("payload") or {})
    selected_contract = dict(selected_payload.get("pricing_contract") or {})
    selected_completeness = dict(selected_contract.get("templateCompleteness") or {})
    missing_fields = list(selected_contract.get("missingPricingFields") or [])
    template_key_preview = selected_contract.get("templateKeyPreview")
    if unresolved_selector_fields:
        checks.append(
            _simple_check(
                "selector-auto-fill",
                "warn",
                f"unresolved selector fields: {', '.join(unresolved_selector_fields)}",
            )
        )
    else:
        checks.append(_simple_check("selector-auto-fill", "pass", f"filled {len(selector_params)} selector fields"))
    checks.append(
        _simple_check(
            "pricing-selected-readiness",
            (
                "pass"
                if selected_completeness.get("status") == "complete"
                else "warn" if selected_completeness.get("status") in {"partial", "missing"} else "warn"
            ),
            (
                f"status={selected_completeness.get('status')} missing={len(missing_fields)} "
                f"templateKey={'set' if template_key_preview else 'none'}"
            ),
        )
    )

    insights = _http_get_json(
        base_url=base_url,
        path="/api/dashboard/sections/insights",
        params={
            **base_pricing_params,
            **selector_params,
        },
    )
    checks.append(_api_check("dashboard-insights", insights))
    trend_cards = list(dict(insights.get("payload") or {}).get("domain_trend_cards") or [])
    trend_template_mismatch_count = 0
    if template_key_preview and trend_cards:
        for card in trend_cards:
            if str(card.get("templateKey") or "").strip() != str(template_key_preview).strip():
                trend_template_mismatch_count += 1
    checks.append(
        _simple_check(
            "trend-template-alignment",
            "pass" if trend_template_mismatch_count == 0 else "warn",
            (
                f"trendCards={len(trend_cards)} mismatched={trend_template_mismatch_count}"
                if trend_cards
                else "no trend cards in current selector context"
            ),
        )
    )

    overall_status = "pass"
    if any(row["status"] == "fail" for row in checks):
        overall_status = "fail"
    elif any(row["status"] == "warn" for row in checks):
        overall_status = "warn"

    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "baseUrl": base_url.rstrip("/"),
        "categoryCode": category_code,
        "overallStatus": overall_status,
        "checkCount": len(checks),
        "checks": checks,
    }


def write_template_smoke_report(*, report: dict[str, Any], output: Path | None) -> Path:
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    output_path = output or reports_dir() / f"template-mode-smoke-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    output_path.write_text(payload, encoding="utf-8")
    latest_path = reports_dir() / "latest-template-mode-smoke.json"
    latest_path.write_text(payload, encoding="utf-8")
    return output_path


def _build_selector_params_for_required_fields(
    *,
    required_selector_fields: list[str],
    filter_catalog: dict[str, Any],
) -> tuple[dict[str, str], list[str]]:
    params: dict[str, str] = {}
    unresolved: list[str] = []
    for selector_field in required_selector_fields:
        options = _selector_options(filter_catalog=filter_catalog, selector_field=selector_field)
        value = None
        for option in options:
            candidate = _option_value(option)
            if candidate is None:
                continue
            value = candidate
            break
        if value is None:
            unresolved.append(selector_field)
            continue
        params[selector_field] = _stringify_query_value(value)
    return params, unresolved


def _selector_options(*, filter_catalog: dict[str, Any], selector_field: str) -> list[dict[str, Any]]:
    alias_keys = {
        "product_label": ("product_label_options", "product_options"),
        "spec_label": ("spec_label_options", "spec_options"),
        "memory_gb": ("memory_gb_options", "memory_options"),
        "storage_gb": ("storage_gb_options", "storage_options"),
        "case_size_mm": ("case_size_mm_options", "case_size_options"),
        "screen_size_in": ("screen_size_in_options", "screen_size_options"),
    }
    for key in alias_keys.get(selector_field, (f"{selector_field}_options",)):
        options = list(filter_catalog.get(key) or [])
        if options:
            return options
    return []


def _option_value(option: dict[str, Any]) -> Any:
    if not isinstance(option, dict):
        return None
    if "value" in option:
        return option.get("value")
    if "label" in option:
        return option.get("label")
    return None


def _stringify_query_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _api_check(name: str, response: dict[str, Any]) -> dict[str, Any]:
    status = "pass" if response.get("ok") else "fail"
    detail = (
        f"http={response.get('statusCode')} path={response.get('path')}"
        if response.get("ok")
        else f"http={response.get('statusCode')} error={response.get('error')}"
    )
    return _simple_check(name, status, detail)


def _feature_flag_check(flags: dict[str, Any]) -> dict[str, Any]:
    required_keys = (
        "priceTemplateContractEnabled",
        "priceTemplateDashboardEnabled",
        "priceTemplateOpportunityEnabled",
        "priceTemplateTrendEnabled",
        "priceTemplateAlertStrictMode",
    )
    missing_keys = [key for key in required_keys if key not in flags]
    if missing_keys:
        return _simple_check("template-feature-flags", "fail", f"missing keys: {', '.join(missing_keys)}")
    disabled_keys = [key for key in required_keys if not bool(flags.get(key))]
    if disabled_keys:
        return _simple_check("template-feature-flags", "warn", f"disabled keys: {', '.join(disabled_keys)}")
    return _simple_check("template-feature-flags", "pass", "all required flags enabled")


def _tier_distribution_check(
    *,
    baseline_tiers: dict[str, Any],
    opportunity_tiers: dict[str, Any],
) -> dict[str, Any]:
    required = {"guidance_ready", "reference_only", "blocked", "incomplete"}
    observed = set(baseline_tiers) | set(opportunity_tiers)
    missing = sorted(required - observed)
    if missing:
        return _simple_check(
            "template-tier-distribution",
            "warn",
            (
                f"missing tiers in window: {', '.join(missing)} | "
                f"baseline={baseline_tiers} opportunity={opportunity_tiers}"
            ),
        )
    return _simple_check(
        "template-tier-distribution",
        "pass",
        f"baseline={baseline_tiers} opportunity={opportunity_tiers}",
    )


def _simple_check(name: str, status: str, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "detail": detail,
    }


def _http_get_json(
    *,
    base_url: str,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_base = base_url.rstrip("/")
    query = parse.urlencode(
        {
            key: value
            for key, value in dict(params or {}).items()
            if value is not None and value != ""
        },
        doseq=True,
    )
    full_url = f"{normalized_base}{path}"
    if query:
        full_url = f"{full_url}?{query}"
    try:
        with request.urlopen(full_url, timeout=8) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw.strip() else {}
            return {
                "ok": True,
                "statusCode": int(getattr(response, "status", 200) or 200),
                "path": path,
                "payload": payload,
            }
    except HTTPError as exc:
        return {
            "ok": False,
            "statusCode": int(exc.code),
            "path": path,
            "error": str(exc),
            "payload": {},
        }
    except URLError as exc:
        return {
            "ok": False,
            "statusCode": None,
            "path": path,
            "error": str(exc.reason),
            "payload": {},
        }
