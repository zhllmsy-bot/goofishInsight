from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from ...category_compat import is_apple_computer_scope, resolve_category_code
from ...models import Category, CategoryRuntimeProfile
from ...presentation.web import (
    DOMAIN_FILTER_LAYOUTS,
    FILTER_LABELS,
    FILTER_LAYOUT_MAP,
    FILTER_OPTION_KEYS,
    FILTER_PLACEHOLDERS,
    NOISY_FILTER_TERMS,
    STRUCTURED_FILTER_KEYS,
    format_currency,
    format_screen_label,
    format_storage_label,
)
from .pricing_domain import APPLE_ANALYSIS_PRODUCT_LINES

APPLE_FILTER_NOISE_RE = re.compile(
    r"(感兴趣的话点|我想要|私聊|监管锁|已绕开|苹果ai|运行内存|国行黑色|深空灰国行|笔记本电脑)",
    re.IGNORECASE,
)


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def normalize_optional_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def normalize_optional_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


def normalize_optional_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def has_structured_filters(filters: dict[str, Any]) -> bool:
    return any(filters.get(key) is not None for key in STRUCTURED_FILTER_KEYS)


def _normalize_filter_fields(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        candidates = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        candidates = [str(entry).strip() for entry in value]
    else:
        return ()
    allowed_keys = set(STRUCTURED_FILTER_KEYS)
    normalized: list[str] = []
    for candidate in candidates:
        if candidate in allowed_keys and candidate not in normalized:
            normalized.append(candidate)
    return tuple(normalized)


def _runtime_filter_fields(*, business_domain: str | None, session=None) -> tuple[str, ...]:
    category_code = resolve_category_code(business_domain)
    if session is None or not category_code:
        return ()
    runtime_profile = session.execute(
        select(CategoryRuntimeProfile)
        .join(Category, Category.id == CategoryRuntimeProfile.category_id)
        .where(Category.code == category_code)
    ).scalar_one_or_none()
    metadata = dict(getattr(runtime_profile, "metadata_json", None) or {})
    for key in (
        "dashboardFilterFields",
        "dashboard_filter_fields",
        "filterLayout",
        "filter_layout",
    ):
        resolved = _normalize_filter_fields(metadata.get(key))
        if resolved:
            return resolved
    return ()


def fields_for_business_domain(business_domain: str | None, *, session=None) -> tuple[str, ...]:
    category_code = resolve_category_code(business_domain)
    runtime_fields = _runtime_filter_fields(
        business_domain=category_code or business_domain,
        session=session,
    )
    if runtime_fields:
        return runtime_fields
    return DOMAIN_FILTER_LAYOUTS.get(category_code, DOMAIN_FILTER_LAYOUTS.get(business_domain, DOMAIN_FILTER_LAYOUTS[None]))


def sanitize_structured_filters(
    *,
    business_domain: str | None,
    filters: dict[str, Any],
    session=None,
) -> dict[str, Any]:
    allowed_keys = set(fields_for_business_domain(business_domain, session=session))
    return {
        key: value if key in allowed_keys else None
        for key, value in filters.items()
    }


def stringify_selected_filters(filters: dict[str, Any]) -> dict[str, str]:
    serialized: dict[str, str] = {}
    for key in STRUCTURED_FILTER_KEYS:
        value = filters.get(key)
        if value is None:
            serialized[key] = ""
        elif isinstance(value, bool):
            serialized[key] = "true" if value else "false"
        else:
            serialized[key] = str(value)
    return serialized


def build_active_filter_summary(filters: dict[str, Any]) -> list[str]:
    summary: list[str] = []
    for key in STRUCTURED_FILTER_KEYS:
        value = filters.get(key)
        if value is None:
            continue
        if key == "is_solar":
            rendered = "Solar" if value is True else "Non-solar"
        elif key == "case_size_mm":
            rendered = f"{value}mm"
        elif key == "screen_size_in":
            rendered = format_screen_label(value)
        elif key == "storage_gb":
            rendered = format_storage_label(value)
        elif key == "memory_gb":
            rendered = f"{value}G"
        else:
            rendered = str(value)
        summary.append(f"{FILTER_LABELS[key]}: {rendered}")
    return summary


def is_clean_filter_label(*, label: str | None, max_length: int) -> bool:
    if not label:
        return False
    stripped = label.strip()
    if not stripped or len(stripped) > max_length:
        return False
    lowered = stripped.lower()
    return not any(term.lower() in lowered for term in NOISY_FILTER_TERMS)


def _matches_allowed_product_line_prefix(label: str | None, *, allowed_values: set[str]) -> bool:
    stripped = str(label or "").strip()
    if not stripped:
        return False
    return any(
        stripped == value or stripped.startswith(f"{value} / ")
        for value in sorted(allowed_values, key=lambda value: (-len(value), value))
    )


def _is_clean_apple_filter_label(*, label: str | None) -> bool:
    stripped = str(label or "").strip()
    if not stripped:
        return False
    return APPLE_FILTER_NOISE_RE.search(stripped) is None


def is_filterable_record(record: dict[str, Any], *, key: str, business_domain: str | None) -> bool:
    if key == "product_label":
        label = record.get("product_label")
        if not is_clean_filter_label(label=label, max_length=40):
            return False
        if is_apple_computer_scope(business_domain) and not _is_clean_apple_filter_label(label=label):
            return False
        if is_apple_computer_scope(business_domain) and not _matches_allowed_product_line_prefix(
            label,
            allowed_values=APPLE_ANALYSIS_PRODUCT_LINES,
        ):
            return False
        return bool(
            record.get("product_line")
            or record.get("model_name")
            or record.get("chip_family")
            or record.get("display_type")
            or record.get("case_size_mm") is not None
            or record.get("screen_size_in") is not None
            or record.get("memory_gb") is not None
            or record.get("storage_gb") is not None
            or resolve_category_code(business_domain) in {"camera_interchangeable_lens", "camera_body", "graphics_card", "phone"}
        )
    if key == "spec_label":
        label = record.get("spec_label")
        if not is_clean_filter_label(label=label, max_length=64):
            return False
        if is_apple_computer_scope(business_domain) and not _is_clean_apple_filter_label(label=label):
            return False
        if is_apple_computer_scope(business_domain) and not _matches_allowed_product_line_prefix(
            label,
            allowed_values=APPLE_ANALYSIS_PRODUCT_LINES,
        ):
            return False
        return bool(
            record.get("exact_spec_ready")
            or record.get("display_type")
            or record.get("case_size_mm") is not None
            or record.get("screen_size_in") is not None
            or record.get("memory_gb") is not None
            or record.get("storage_gb") is not None
        )
    return True


def record_matches_structured_filters(record: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key in STRUCTURED_FILTER_KEYS:
        selected = filters.get(key)
        if selected is None:
            continue
        if record.get(key) != selected:
            return False
    return True


def filter_pricing_records(records: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    if not has_structured_filters(filters):
        return records
    return [record for record in records if record_matches_structured_filters(record, filters)]


def option_row(value: Any, label: str, *, summary_label: str | None = None) -> dict[str, str]:
    if summary_label:
        return {"value": str(value), "label": label, "summaryLabel": summary_label}
    return {"value": str(value), "label": label}


def build_filter_catalog(
    records: list[dict[str, Any]],
    filters: dict[str, Any],
    *,
    business_domain: str | None,
) -> dict[str, list[dict[str, str]]]:
    product_source = [
        record
        for record in records
        if is_filterable_record(record, key="product_label", business_domain=business_domain)
    ]
    spec_source = [
        record
        for record in product_source
        if filters.get("product_label") is None or record.get("product_label") == filters["product_label"]
    ]
    spec_source = [
        record
        for record in spec_source
        if is_filterable_record(record, key="spec_label", business_domain=business_domain)
    ]
    detail_source = [
        record
        for record in spec_source
        if filters.get("spec_label") is None or record.get("spec_label") == filters["spec_label"]
    ]

    product_summary_by_label = build_product_option_summary_map(product_source)

    def string_options(source: list[dict[str, Any]], key: str) -> list[dict[str, str]]:
        values = sorted({str(record[key]) for record in source if record.get(key)})
        return [
            option_row(
                value,
                value,
                summary_label=product_summary_by_label.get(value) if key == "product_label" else None,
            )
            for value in values
        ]

    def int_options(source: list[dict[str, Any]], key: str, suffix: str = "") -> list[dict[str, str]]:
        values = sorted({int(record[key]) for record in source if record.get(key) is not None})
        return [option_row(value, f"{value}{suffix}") for value in values]

    screen_values = sorted(
        {float(record["screen_size_in"]) for record in detail_source if record.get("screen_size_in") is not None}
    )
    storage_values = sorted({int(record["storage_gb"]) for record in detail_source if record.get("storage_gb") is not None})
    solar_values: list[dict[str, str]] = []
    if any(record.get("is_solar") is True for record in detail_source):
        solar_values.append(option_row("true", "太阳能"))
    if any(record.get("is_solar") is False for record in detail_source):
        solar_values.append(option_row("false", "非太阳能"))

    return {
        "product_options": string_options(product_source, "product_label"),
        "spec_options": string_options(spec_source, "spec_label"),
        "display_type_options": string_options(detail_source, "display_type"),
        "case_size_options": int_options(detail_source, "case_size_mm", "mm"),
        "is_solar_options": solar_values,
        "chip_family_options": string_options(detail_source, "chip_family"),
        "screen_size_options": [option_row(value, format_screen_label(value)) for value in screen_values],
        "memory_options": int_options(detail_source, "memory_gb", "G"),
        "storage_options": [option_row(value, format_storage_label(value)) for value in storage_values],
    }


def build_product_option_summary_map(records: list[dict[str, Any]]) -> dict[str, str]:
    grouped_prices: dict[str, list[float]] = {}
    for record in records:
        label = str(record.get("product_label") or "").strip()
        price = record.get("price")
        if not label or price is None:
            continue
        try:
            numeric_price = float(price)
        except (TypeError, ValueError):
            continue
        if numeric_price <= 0:
            continue
        grouped_prices.setdefault(label, []).append(numeric_price)

    summaries: dict[str, str] = {}
    for label, prices in grouped_prices.items():
        if len(prices) < 3:
            continue
        sorted_prices = sorted(prices)
        normal_price = percentile(sorted_prices, 0.35)
        market_price = percentile(sorted_prices, 0.50)
        summaries[label] = f"正常 {format_currency(normal_price)} · 中位 {format_currency(market_price)} · {len(prices)} 样本"
    return summaries


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    position = max(0.0, min(1.0, q)) * (len(values) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    weight = position - lower_index
    return values[lower_index] * (1 - weight) + values[upper_index] * weight


def build_visible_filter_fields(
    *,
    business_domain: str | None,
    filter_catalog: dict[str, list[dict[str, str]]],
    selected_filters: dict[str, Any],
    session=None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for key in fields_for_business_domain(business_domain, session=session):
        options = filter_catalog.get(FILTER_OPTION_KEYS[key], [])
        if key not in {"product_label", "spec_label"} and not options and selected_filters.get(key) is None:
            continue
        fields.append(
            {
                "key": key,
                "label": FILTER_LABELS[key],
                "options": options,
                "placeholder": FILTER_PLACEHOLDERS[key],
                "layout": FILTER_LAYOUT_MAP[key],
            }
        )
    return fields
