from __future__ import annotations

from ...settings import get_settings


def price_template_feature_flags() -> dict[str, bool]:
    settings = get_settings()
    return {
        "priceTemplateContractEnabled": bool(settings.price_template_contract_enabled),
        "priceTemplateDashboardEnabled": bool(settings.price_template_dashboard_enabled),
        "priceTemplateOpportunityEnabled": bool(settings.price_template_opportunity_enabled),
        "priceTemplateTrendEnabled": bool(settings.price_template_trend_enabled),
        "priceTemplateAlertStrictMode": bool(settings.price_template_alert_strict_mode),
    }


def is_price_template_contract_enabled() -> bool:
    return bool(get_settings().price_template_contract_enabled)


def is_price_template_dashboard_enabled() -> bool:
    return bool(get_settings().price_template_dashboard_enabled)


def is_price_template_opportunity_enabled() -> bool:
    return bool(get_settings().price_template_opportunity_enabled)


def is_price_template_trend_enabled() -> bool:
    return bool(get_settings().price_template_trend_enabled)


def is_price_template_alert_strict_mode_enabled() -> bool:
    return bool(get_settings().price_template_alert_strict_mode)
