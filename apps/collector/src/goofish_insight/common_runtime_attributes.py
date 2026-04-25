from __future__ import annotations

from typing import Any


COMMON_RUNTIME_ATTRIBUTE_CODES: frozenset[str] = frozenset(
    {
        "brand_name",
        "generation",
        "is_chinese_mainland",
        "purchase_channel",
        "box_and_manual_complete",
        "has_invoice",
    }
)

COMMON_RUNTIME_ATTRIBUTE_FLAG_KEYS: tuple[str, ...] = (
    "runtimeCommon",
    "isCommon",
    "commonRuntime",
    "globalCommon",
)

COMMON_RUNTIME_TEMPLATE_HINTS: dict[str, dict[str, bool]] = {
    "brand_name": {"isRequired": True, "isSearch": True, "isFilter": True, "isDisplay": True},
    "generation": {"isRequired": False, "isSearch": True, "isFilter": True, "isDisplay": True},
    "is_chinese_mainland": {"isRequired": False, "isSearch": False, "isFilter": True, "isDisplay": True},
    "purchase_channel": {"isRequired": False, "isSearch": False, "isFilter": True, "isDisplay": True},
    "box_and_manual_complete": {"isRequired": False, "isSearch": False, "isFilter": True, "isDisplay": True},
    "has_invoice": {"isRequired": False, "isSearch": False, "isFilter": True, "isDisplay": True},
}


def is_runtime_common_attribute(
    *,
    code: str | None,
    validation_schema: dict[str, Any] | None,
) -> bool:
    normalized_code = str(code or "").strip()
    if not normalized_code:
        return False
    if normalized_code in COMMON_RUNTIME_ATTRIBUTE_CODES:
        return True
    schema = dict(validation_schema or {})
    for key in COMMON_RUNTIME_ATTRIBUTE_FLAG_KEYS:
        if key not in schema:
            continue
        return _coerce_bool(schema.get(key))
    return False


def merge_runtime_common_flag(
    *,
    code: str | None,
    validation_schema: dict[str, Any] | None,
    is_common: Any,
) -> dict[str, Any] | None:
    merged = dict(validation_schema or {})
    normalized_code = str(code or "").strip()
    if is_common is None:
        if normalized_code in COMMON_RUNTIME_ATTRIBUTE_CODES and "runtimeCommon" not in merged:
            merged["runtimeCommon"] = True
    else:
        merged["runtimeCommon"] = _coerce_bool(is_common)
    return merged or None


def common_runtime_template_hint(code: str | None) -> dict[str, bool]:
    normalized_code = str(code or "").strip()
    if not normalized_code:
        return {"isRequired": False, "isSearch": False, "isFilter": True, "isDisplay": True}
    return dict(
        COMMON_RUNTIME_TEMPLATE_HINTS.get(
            normalized_code,
            {"isRequired": False, "isSearch": False, "isFilter": True, "isDisplay": True},
        )
    )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    if not text:
        return False
    return text in {"1", "true", "yes", "y", "on"}

