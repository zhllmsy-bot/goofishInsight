from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from ...specs import normalize_chip_family

ITEM_FIELD_KEYS = {
    "item.normalized_brand",
    "item.normalized_model_family",
    "item.normalized_model",
    "item.normalized_chip",
    "item.normalized_memory_gb",
    "item.normalized_storage_gb",
}

SPEC_FIELD_KEYS = {
    "spec.brand",
    "spec.product_line",
    "spec.model_family",
    "spec.model_name",
    "spec.generation",
    "spec.case_size_mm",
    "spec.is_solar",
    "spec.display_type",
    "spec.screen_size_in",
    "spec.chip_family",
    "spec.cpu_model",
    "spec.cpu_cores",
    "spec.gpu_cores",
    "spec.memory_gb",
    "spec.storage_gb",
}

INVALID_FIELD_VALUE = object()
REVIEW_STATUS_VALID = "valid"
REVIEW_STATUS_INVALID = "invalid"
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_IN_PROGRESS = "in_progress"
REVIEW_STATUS_PENDING_AUDIT = "pending_audit"
VALID_REVIEW_STATUSES = {REVIEW_STATUS_VALID, REVIEW_STATUS_INVALID}
INVALID_REASONS = {
    "accessory",
    "ad",
    "electronic_parts",
    "garbage",
    "non_target",
    "pawn",
    "recycling",
    "service",
    "other",
}

FIELD_SCHEMA: dict[str, dict[str, Any]] = {
    "item.normalized_brand": {"type": "string"},
    "item.normalized_model_family": {"type": "string"},
    "item.normalized_model": {"type": "string"},
    "item.normalized_chip": {"type": "chip_string"},
    "item.normalized_memory_gb": {"type": "int"},
    "item.normalized_storage_gb": {"type": "int"},
    "spec.brand": {"type": "string"},
    "spec.product_line": {"type": "string"},
    "spec.model_family": {"type": "string"},
    "spec.model_name": {"type": "string"},
    "spec.generation": {"type": "string"},
    "spec.case_size_mm": {"type": "int"},
    "spec.is_solar": {"type": "bool"},
    "spec.display_type": {"type": "enum_string", "allowed": ("AMOLED", "MIP")},
    "spec.screen_size_in": {"type": "decimal"},
    "spec.chip_family": {"type": "chip_string"},
    "spec.cpu_model": {"type": "chip_string"},
    "spec.cpu_cores": {"type": "int"},
    "spec.gpu_cores": {"type": "int"},
    "spec.memory_gb": {"type": "int"},
    "spec.storage_gb": {"type": "int"},
}
ALLOWED_FIELD_KEYS = set(FIELD_SCHEMA)


def split_field_key(field_key: str) -> tuple[str, str]:
    if "." not in field_key:
        raise RuntimeError(f"Unsupported field key: {field_key}")
    return tuple(field_key.split(".", 1))  # type: ignore[return-value]


def field_schema(field_key: str) -> dict[str, Any]:
    schema = FIELD_SCHEMA.get(field_key)
    if schema is None:
        raise RuntimeError(f"Unsupported field key: {field_key}")
    return schema


def build_field_contract_lines() -> list[str]:
    lines: list[str] = []
    for field_key in sorted(ALLOWED_FIELD_KEYS):
        schema = field_schema(field_key)
        field_type = schema["type"]
        if field_type == "enum_string":
            allowed = "|".join(schema.get("allowed") or ())
            lines.append(f"{field_key}<{allowed}>")
        else:
            lines.append(f"{field_key}<{field_type}>")
    return lines


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def normalize_display_type(value: Any) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    compact = text.replace("-", "").replace("_", "").replace(" ", "").upper()
    if compact == "AMOLED":
        return "AMOLED"
    if compact == "MIP":
        return "MIP"
    return text.upper()


def normalize_chip_text(value: Any) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    match = re.fullmatch(r"(m[1-4])(?:\s+(pro|max|ultra))?", text, flags=re.IGNORECASE)
    if match:
        return normalize_chip_family(
            chip_family=match.group(1).upper(),
            cpu_model=text,
            model_name=text,
        )
    return normalize_chip_family(
        chip_family=text,
        cpu_model=text,
        model_name=text,
    )


def coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return None
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    text = normalize_text(value)
    if not text:
        return None
    try:
        decimal_value = Decimal(text)
    except InvalidOperation:
        return None
    if decimal_value == decimal_value.to_integral_value():
        return int(decimal_value)
    return None


def coerce_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    text = normalize_text(value)
    if not text:
        return None
    normalized = text.lower()
    if normalized in {"true", "1", "yes", "y", "solar"}:
        return True
    if normalized in {"false", "0", "no", "n", "non-solar", "nonsolar"}:
        return False
    return None


def coerce_decimal(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = normalize_text(value)
    if not text:
        return None
    try:
        return float(Decimal(text))
    except InvalidOperation:
        return None


def coerce_field_value(*, field_key: str, value: Any) -> Any:
    field_type = field_schema(field_key)["type"]
    if field_type == "bool":
        return coerce_bool(value)
    if field_type == "int":
        return coerce_int(value)
    if field_type == "decimal":
        return coerce_decimal(value)
    if field_type == "enum_string":
        return normalize_display_type(value)
    if field_type == "chip_string":
        return normalize_chip_text(value)
    return normalize_text(value)


def normalize_current_value(*, field_key: str, value: Any) -> Any:
    return coerce_field_value(field_key=field_key, value=value)


def to_storage_value(*, field_key: str, value: Any) -> Any:
    field_type = field_schema(field_key)["type"]
    if field_type == "decimal" and value is not None:
        return Decimal(str(value))
    return value


def validate_field_value(*, field_key: str, value: Any) -> Any:
    if value is None or value == "":
        return INVALID_FIELD_VALUE

    schema = field_schema(field_key)
    field_type = schema["type"]

    if field_type == "bool":
        normalized = coerce_bool(value)
        return normalized if normalized is not None else INVALID_FIELD_VALUE

    if field_type == "int":
        normalized = coerce_int(value)
        return normalized if normalized is not None else INVALID_FIELD_VALUE

    if field_type == "decimal":
        normalized = coerce_decimal(value)
        return normalized if normalized is not None else INVALID_FIELD_VALUE

    if field_type == "enum_string":
        if not isinstance(value, str):
            return INVALID_FIELD_VALUE
        normalized = normalize_display_type(value)
        allowed = set(schema.get("allowed") or ())
        return normalized if normalized in allowed else INVALID_FIELD_VALUE

    if field_type == "chip_string":
        if not isinstance(value, str):
            return INVALID_FIELD_VALUE
        normalized = normalize_chip_text(value)
        return normalized if normalized is not None else INVALID_FIELD_VALUE

    if not isinstance(value, str):
        return INVALID_FIELD_VALUE
    normalized = normalize_text(value)
    return normalized if normalized is not None else INVALID_FIELD_VALUE


def normalize_review_status(value: Any) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    normalized = text.lower()
    return normalized if normalized in VALID_REVIEW_STATUSES else None


def normalize_invalid_reason(value: Any) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    normalized = text.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in INVALID_REASONS else None
