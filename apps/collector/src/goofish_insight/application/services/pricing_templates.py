from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...category_compat import resolve_category_code
from ...models import Category, CategoryRuntimeProfile
from .template_feature_flags import is_price_template_contract_enabled
from .catalog_queries import build_catalog_template_detail


SelectorRequirementResolver = Callable[[dict[str, Any], dict[str, list[dict[str, str]]]], tuple[str, ...]]
RecordValueResolver = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class PricingContractDefault:
    category_code: str
    pricing_key_fields: tuple[str, ...]
    required_pricing_fields: tuple[str, ...]
    selector_aliases: dict[str, str]
    supporting_fields: tuple[str, ...] = ()
    listing_adjustment_factors: tuple[str, ...] = ()
    required_selector_resolver: SelectorRequirementResolver | None = None
    record_value_resolver: RecordValueResolver | None = None


def _option_count(filter_catalog: dict[str, list[dict[str, str]]], key: str) -> int:
    return len(filter_catalog.get(key) or [])


def _apple_required_selector_fields(
    selected_filters: dict[str, Any],
    _filter_catalog: dict[str, list[dict[str, str]]],
) -> tuple[str, ...]:
    required = ["product_label", "chip_family", "memory_gb", "storage_gb"]
    product_label = str(selected_filters.get("product_label") or "")
    if product_label.startswith(("MacBook Air", "MacBook Pro", "iMac")):
        required.append("screen_size_in")
    return tuple(required)


def _garmin_required_selector_fields(
    selected_filters: dict[str, Any],
    filter_catalog: dict[str, list[dict[str, str]]],
) -> tuple[str, ...]:
    required = ["product_label", "case_size_mm"]
    if selected_filters.get("product_label"):
        if _option_count(filter_catalog, "display_type_options") > 1:
            required.append("display_type")
        if _option_count(filter_catalog, "is_solar_options") > 1:
            required.append("is_solar")
    return tuple(required)


def _apple_record_values(record: dict[str, Any]) -> dict[str, Any]:
    model_name = (
        record.get("product_label")
        or record.get("model_name")
        or record.get("spec_label")
        or record.get("label")
    )
    return {
        "model_name": model_name,
        "chip_family": record.get("chip_family"),
        "memory_gb": record.get("memory_gb"),
        "storage_gb": record.get("storage_gb"),
        "screen_size_in": record.get("screen_size_in"),
        "cpu_cores": record.get("cpu_cores"),
        "gpu_cores": record.get("gpu_cores"),
        "product_line": record.get("product_line"),
    }


def _garmin_record_values(record: dict[str, Any]) -> dict[str, Any]:
    model_name = (
        record.get("product_label")
        or record.get("model_name")
        or record.get("spec_label")
        or record.get("label")
    )
    return {
        "model_name": model_name,
        "case_size_mm": record.get("case_size_mm"),
        "display_type": record.get("display_type"),
        "is_solar": record.get("is_solar"),
        "generation": record.get("generation"),
        "product_line": record.get("product_line"),
        "edition_tags": list(record.get("edition_tags") or []),
    }


def _camera_body_record_values(record: dict[str, Any]) -> dict[str, Any]:
    model_name = (
        record.get("product_label")
        or record.get("model_name")
        or record.get("spec_label")
        or record.get("label")
    )
    return {
        "brand_name": record.get("brand_name") or record.get("brand"),
        "model_name": model_name,
        "mount_system": record.get("mount_system"),
        "sensor_format": record.get("sensor_format"),
        "generation": record.get("generation"),
        "pixel_resolution": record.get("pixel_resolution"),
        "camera_type": record.get("camera_type"),
    }


def _lens_record_values(record: dict[str, Any]) -> dict[str, Any]:
    model_name = (
        record.get("product_label")
        or record.get("model_name")
        or record.get("spec_label")
        or record.get("label")
    )
    return {
        "brand_name": record.get("brand_name") or record.get("brand"),
        "model_name": model_name,
        "mount_system": record.get("mount_system"),
        "focal_length_type": record.get("focal_length_type"),
        "focal_length_range": record.get("focal_length_range"),
        "max_aperture": record.get("max_aperture"),
    }


CONTRACT_DEFAULTS: dict[str, PricingContractDefault] = {
    "apple_computer": PricingContractDefault(
        category_code="apple_computer",
        pricing_key_fields=("model_name", "chip_family", "memory_gb", "storage_gb", "screen_size_in"),
        required_pricing_fields=("model_name", "chip_family", "memory_gb", "storage_gb"),
        selector_aliases={
            "model_name": "product_label",
            "chip_family": "chip_family",
            "memory_gb": "memory_gb",
            "storage_gb": "storage_gb",
            "screen_size_in": "screen_size_in",
        },
        supporting_fields=("product_line",),
        listing_adjustment_factors=(
            "condition",
            "battery_health",
            "bundle_accessories",
            "warranty_status",
            "box_and_receipt",
            "shipping_mode",
        ),
        required_selector_resolver=_apple_required_selector_fields,
        record_value_resolver=_apple_record_values,
    ),
    "garmin_watch": PricingContractDefault(
        category_code="garmin_watch",
        pricing_key_fields=("model_name", "case_size_mm", "display_type", "is_solar"),
        required_pricing_fields=("model_name", "case_size_mm"),
        selector_aliases={
            "model_name": "product_label",
            "case_size_mm": "case_size_mm",
            "display_type": "display_type",
            "is_solar": "is_solar",
        },
        supporting_fields=("product_line", "generation", "edition_tags"),
        listing_adjustment_factors=(
            "condition",
            "battery_health",
            "strap_originality",
            "screen_state",
            "bundle_accessories",
            "region_variant",
        ),
        required_selector_resolver=_garmin_required_selector_fields,
        record_value_resolver=_garmin_record_values,
    ),
    "camera_body": PricingContractDefault(
        category_code="camera_body",
        pricing_key_fields=("brand_name", "model_name", "mount_system", "sensor_format"),
        required_pricing_fields=("brand_name", "model_name", "mount_system", "sensor_format"),
        selector_aliases={
            "model_name": "product_label",
        },
        supporting_fields=("generation", "pixel_resolution", "camera_type"),
        listing_adjustment_factors=(
            "condition",
            "shutter_count",
            "repair_history",
            "bundle_accessories",
            "warranty_status",
            "shipping_mode",
        ),
        record_value_resolver=_camera_body_record_values,
    ),
    "camera_interchangeable_lens": PricingContractDefault(
        category_code="camera_interchangeable_lens",
        pricing_key_fields=("brand_name", "model_name", "mount_system", "focal_length_range", "max_aperture"),
        required_pricing_fields=("brand_name", "model_name", "mount_system", "focal_length_range", "max_aperture"),
        selector_aliases={
            "model_name": "product_label",
        },
        supporting_fields=("focal_length_type",),
        listing_adjustment_factors=(
            "condition",
            "glass_state",
            "focus_ring_state",
            "zoom_ring_state",
            "hood_and_caps",
            "box_and_receipt",
            "shipping_mode",
        ),
        record_value_resolver=_lens_record_values,
    ),
}


def load_active_template_detail(
    session: Session,
    *,
    business_domain: str | None = None,
    category_code: str | None = None,
) -> dict[str, Any] | None:
    canonical_code = resolve_category_code(category_code or business_domain)
    if not canonical_code:
        return None
    runtime_profile = session.execute(
        select(CategoryRuntimeProfile)
        .join(Category, Category.id == CategoryRuntimeProfile.category_id)
        .where(Category.code == canonical_code)
        .where(CategoryRuntimeProfile.status == "ACTIVE")
    ).scalar_one_or_none()
    if runtime_profile is None or not runtime_profile.active_template_id:
        return None
    return build_catalog_template_detail(session, runtime_profile.active_template_id)


def build_pricing_contract(
    *,
    business_domain: str | None,
    selected_filters: dict[str, Any],
    filter_catalog: dict[str, list[dict[str, str]]] | None = None,
    session: Session | None = None,
    template_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    canonical_code = resolve_category_code(business_domain)
    if not is_price_template_contract_enabled():
        return _legacy_pricing_contract(canonical_code=canonical_code or business_domain)
    default = CONTRACT_DEFAULTS.get(canonical_code)
    detail = template_detail
    if detail is None and session is not None:
        detail = load_active_template_detail(
            session,
            business_domain=business_domain,
            category_code=canonical_code,
        )
    template_fields = {
        str(item.get("attributeCode"))
        for item in (detail or {}).get("items", [])
        if item.get("attributeCode")
    }
    if default is None:
        return {
            "categoryCode": canonical_code or business_domain,
            "contractSource": "unsupported_category",
            "pricingKeyFields": [],
            "requiredPricingFields": [],
            "selectorFieldAliases": {},
            "requiredSelectorFields": [],
            "optionalSelectorFields": [],
            "unsupportedPricingFields": [],
            "selectedPricingValues": {},
            "missingPricingFields": [],
            "templateCompleteness": {
                "status": "missing",
                "isComplete": False,
                "missingFields": [],
                "primarySelectorField": "product_label",
            },
            "supportingFields": [],
            "listingAdjustmentFactors": [],
            "templateDetail": _template_descriptor(detail),
        }

    catalog = filter_catalog or {}
    required_selector_fields = tuple(
        default.required_selector_resolver(selected_filters, catalog)
        if default.required_selector_resolver is not None
        else _required_selector_fields_from_defaults(default)
    )
    required_pricing_fields = tuple(
        field
        for field, selector_key in default.selector_aliases.items()
        if selector_key in required_selector_fields and field in default.required_pricing_fields + default.pricing_key_fields
    )
    required_pricing_fields = _merge_pricing_fields(
        required_pricing_fields,
        default.required_pricing_fields,
    )

    selected_pricing_values = _selected_pricing_values(
        default=default,
        selected_filters=selected_filters,
    )
    missing_pricing_fields = [
        field
        for field in required_pricing_fields
        if not _has_value(selected_pricing_values.get(field))
    ]
    primary_selector_field = "product_label"
    primary_selected = _has_value(selected_filters.get(primary_selector_field))
    completeness_status = "complete"
    if not primary_selected:
        completeness_status = "missing"
    elif missing_pricing_fields:
        completeness_status = "partial"

    optional_selector_fields = [
        selector_key
        for selector_key in dict.fromkeys(default.selector_aliases.values())
        if selector_key not in required_selector_fields
    ]
    unsupported_pricing_fields = [
        field
        for field in default.pricing_key_fields
        if not default.selector_aliases.get(field)
        or default.selector_aliases[field] not in selected_filters
        or field not in template_fields
    ]
    field_coverage = {
        field: {
            "presentInTemplate": field in template_fields,
            "selectorField": default.selector_aliases.get(field),
            "supportedByDashboard": bool(default.selector_aliases.get(field) in selected_filters),
        }
        for field in default.pricing_key_fields
    }

    return {
        "categoryCode": canonical_code,
        "contractSource": "phase0_design_table",
        "pricingKeyFields": list(default.pricing_key_fields),
        "requiredPricingFields": list(required_pricing_fields),
        "selectorFieldAliases": dict(default.selector_aliases),
        "requiredSelectorFields": list(required_selector_fields),
        "optionalSelectorFields": optional_selector_fields,
        "unsupportedPricingFields": unsupported_pricing_fields,
        "selectedPricingValues": selected_pricing_values,
        "missingPricingFields": missing_pricing_fields,
        "fieldCoverage": field_coverage,
        "templateKeyPreview": (
            build_template_key(
                category_code=canonical_code,
                pricing_key_fields=default.pricing_key_fields,
                selected_values=selected_pricing_values,
            )
            if completeness_status == "complete"
            else None
        ),
        "templateCompleteness": {
            "status": completeness_status,
            "isComplete": completeness_status == "complete",
            "missingFields": missing_pricing_fields,
            "primarySelectorField": primary_selector_field,
        },
        "supportingFields": list(default.supporting_fields),
        "listingAdjustmentFactors": list(default.listing_adjustment_factors),
        "templateDetail": _template_descriptor(detail),
    }


def _legacy_pricing_contract(*, canonical_code: str | None) -> dict[str, Any]:
    return {
        "categoryCode": canonical_code,
        "contractSource": "legacy_feature_flag_disabled",
        "pricingKeyFields": [],
        "requiredPricingFields": [],
        "selectorFieldAliases": {},
        "requiredSelectorFields": [],
        "optionalSelectorFields": [],
        "unsupportedPricingFields": [],
        "selectedPricingValues": {},
        "missingPricingFields": [],
        "templateKeyPreview": None,
        "templateLabelPreview": None,
        "templateCompleteness": {
            "status": "legacy",
            "isComplete": True,
            "missingFields": [],
            "primarySelectorField": "product_label",
        },
        "supportingFields": [],
        "listingAdjustmentFactors": [],
        "templateDetail": _template_descriptor(None),
    }


def annotate_visible_filter_fields(
    fields: list[dict[str, Any]],
    *,
    pricing_contract: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not pricing_contract:
        return fields
    required_selector_fields = set(pricing_contract.get("requiredSelectorFields") or [])
    optional_selector_fields = set(pricing_contract.get("optionalSelectorFields") or [])
    semantic_by_selector: dict[str, list[str]] = {}
    for semantic_key, selector_key in (pricing_contract.get("selectorFieldAliases") or {}).items():
        if not selector_key:
            continue
        semantic_by_selector.setdefault(str(selector_key), []).append(str(semantic_key))
    annotated: list[dict[str, Any]] = []
    for field in fields:
        key = str(field.get("key") or "")
        pricing_role = None
        if key in required_selector_fields:
            pricing_role = "required"
        elif key in optional_selector_fields:
            pricing_role = "optional"
        annotated.append(
            {
                **field,
                "pricingRole": pricing_role,
                "pricingSemanticFields": semantic_by_selector.get(key, []),
            }
        )
    return annotated


def build_pricing_record_template_snapshot(
    *,
    business_domain: str | None,
    record: dict[str, Any],
    session: Session | None = None,
    template_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    canonical_code = resolve_category_code(business_domain)
    default = CONTRACT_DEFAULTS.get(canonical_code)
    detail = template_detail
    if detail is None and session is not None:
        detail = load_active_template_detail(
            session,
            business_domain=business_domain,
            category_code=canonical_code,
        )
    template_fields = {
        str(item.get("attributeCode"))
        for item in (detail or {}).get("items", [])
        if item.get("attributeCode")
    }
    if default is None or default.record_value_resolver is None:
        return {
            "categoryCode": canonical_code or business_domain,
            "templateKey": None,
            "templateLabel": record.get("spec_label") or record.get("product_label") or record.get("label"),
            "resolvedFieldValues": {},
            "missingFields": [],
            "completenessStatus": "missing",
            "requiredPricingFields": [],
            "pricingKeyFields": [],
        }

    resolved_field_values = default.record_value_resolver(record)
    required_pricing_fields = tuple(default.required_pricing_fields)
    missing_fields = [
        field for field in required_pricing_fields if not _has_value(resolved_field_values.get(field))
    ]
    completeness_status = "complete"
    if missing_fields:
        completeness_status = "partial"
    if not _has_value(resolved_field_values.get("model_name")):
        completeness_status = "missing"

    unsupported_pricing_fields = [
        field for field in default.pricing_key_fields if field not in template_fields
    ]

    return {
        "categoryCode": canonical_code,
        "templateKey": (
            build_template_key(
                category_code=canonical_code,
                pricing_key_fields=default.pricing_key_fields,
                selected_values=resolved_field_values,
            )
            if completeness_status == "complete"
            else None
        ),
        "templateLabel": record.get("spec_label") or record.get("product_label") or record.get("label"),
        "resolvedFieldValues": {
            field: value
            for field, value in resolved_field_values.items()
            if _has_value(value)
        },
        "missingFields": missing_fields,
        "completenessStatus": completeness_status,
        "requiredPricingFields": list(required_pricing_fields),
        "pricingKeyFields": list(default.pricing_key_fields),
        "unsupportedPricingFields": unsupported_pricing_fields,
        "templateDetail": _template_descriptor(detail),
    }


def build_template_key(
    *,
    category_code: str,
    pricing_key_fields: tuple[str, ...],
    selected_values: dict[str, Any],
) -> str:
    parts = [resolve_category_code(category_code)]
    for field in pricing_key_fields:
        value = selected_values.get(field)
        if not _has_value(value):
            continue
        parts.append(f"{field}={_normalize_template_value(value)}")
    return "|".join(parts)


def _required_selector_fields_from_defaults(default: PricingContractDefault) -> tuple[str, ...]:
    keys: list[str] = []
    for field in default.required_pricing_fields:
        selector_key = default.selector_aliases.get(field)
        if selector_key and selector_key not in keys:
            keys.append(selector_key)
    return tuple(keys)


def _selected_pricing_values(
    *,
    default: PricingContractDefault,
    selected_filters: dict[str, Any],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for pricing_field, selector_key in default.selector_aliases.items():
        values[pricing_field] = selected_filters.get(selector_key) if selector_key else None
    return values


def _merge_pricing_fields(primary: tuple[str, ...], fallback: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for field in (*primary, *fallback):
        if field not in merged:
            merged.append(field)
    return tuple(merged)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _normalize_template_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(_normalize_template_value(entry) for entry in value if _has_value(entry))
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
    else:
        text = str(value).strip()
    return " ".join(text.split())


def _template_descriptor(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    if not detail:
        return None
    template = dict(detail.get("template") or {})
    category = dict(detail.get("category") or {})
    return {
        "templateId": template.get("id"),
        "templateVersion": template.get("version"),
        "categoryId": category.get("id"),
        "categoryCode": category.get("code"),
        "itemCount": len(detail.get("items") or []),
    }
