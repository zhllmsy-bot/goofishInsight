from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...common_runtime_attributes import is_runtime_common_attribute
from ...category_runtime_defaults import get_category_runtime_default
from ...db import session_scope
from ...models import Category, CategoryAttrTemplate, CategoryRuntimeProfile
from ...settings import get_settings
from ...specs import (
    call_openai_compatible_chat,
    extract_json_object,
    extract_message_content,
    llm_is_configured,
)
from .attribute_config import upsert_attribute_config_with_session
from .category_config import upsert_category_config_with_session
from .template_config import upsert_template_config_with_session


class CategoryAIConfigError(RuntimeError):
    pass


AI_DRAFT_SYSTEM_PROMPT = """
You are an e-commerce category onboarding planner.
Given a natural-language request, return a JSON object only.

JSON schema:
{
  "category": {
    "code": "snake_case_english",
    "name": "human readable Chinese or English",
    "path": "segment/segment",
    "level": 2,
    "status": "ACTIVE"
  },
  "runtime": {
    "promptProfile": "snake_case_extract_v1",
    "extractorProfile": "default",
    "validatorProfile": "optional",
    "llmProviderOverride": null,
    "llmModelOverride": null,
    "runtimeStatus": "ACTIVE"
  },
  "attributes": [
    {
      "code": "snake_case_english",
      "name": "Chinese display name",
      "dataType": "TEXT|NUMBER|BOOLEAN|ENUM|JSON",
      "valueScope": "SPU|SKU|SALE",
      "unit": null,
      "isMulti": false,
      "status": "ACTIVE",
      "options": [
        {"optionCode": "snake_case", "optionName": "label"}
      ]
    }
  ],
  "template": {
    "version": 1,
    "status": "PUBLISHED",
    "bindAsActiveTemplate": true,
    "items": [
      {
        "attributeCode": "snake_case_english",
        "isRequired": false,
        "isSale": false,
        "isFilter": true,
        "isSearch": false,
        "isDisplay": true,
        "sortNo": 10
      }
    ]
  }
}

Rules:
- Output JSON only; no markdown code fence.
- category.code and attribute.code must be English snake_case.
- Prefer practical attributes for second-hand listing parsing.
- Must include brand_name and model_name in attributes and template.items.
- template.items.attributeCode must refer to an attribute code in attributes.
- Keep enum options concise; include only high-confidence options.
- For lens domains, always keep one category (camera_interchangeable_lens).
- Do NOT split prime lens vs zoom lens into different categories.
- Represent prime/zoom as attribute focal_length_type with options prime/zoom.
""".strip()


@dataclass(frozen=True)
class GranularityVariantDimension:
    attribute_code: str
    dimension_name: str
    option_signals: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class CategoryGranularityPolicy:
    canonical_code: str
    aliases: tuple[str, ...]
    force_single_category: bool
    variant_dimensions: tuple[GranularityVariantDimension, ...]


@dataclass(frozen=True)
class CategoryAttributeSanitizationPolicy:
    blocked_attribute_codes: frozenset[str]
    blocked_code_keywords: tuple[str, ...]
    blocked_name_keywords: tuple[str, ...]


ATTRIBUTE_CODE_HINTS: tuple[tuple[str, str], ...] = (
    ("品牌", "brand_name"),
    ("厂商", "brand_name"),
    ("型号", "model_name"),
    ("机型", "model_name"),
    ("系列", "product_line"),
    ("卡口", "mount_system"),
    ("焦段", "focal_length_range"),
    ("焦距", "focal_length_range"),
    ("焦距类型", "focal_length_type"),
    ("定焦", "focal_length_type"),
    ("变焦", "focal_length_type"),
    ("光圈", "max_aperture"),
    ("镜头系列", "lens_series"),
    ("内存", "memory_gb"),
    ("存储", "storage_gb"),
    ("容量", "storage_gb"),
    ("颜色", "device_color"),
    ("屏幕", "screen_size_in"),
    ("尺寸", "case_size_mm"),
)

ATTRIBUTE_CODE_ALIASES: dict[str, str] = {
    "brand": "brand_name",
    "model": "model_name",
    "mount": "mount_system",
    "mount_type": "mount_system",
    "lens_mount": "mount_system",
    "mounting_system": "mount_system",
    "mount_system": "mount_system",
    "focal_length": "focal_length_range",
    "focal_range": "focal_length_range",
    "focal_length_mm": "focal_length_range",
    "focal_type": "focal_length_type",
    "focal_length_type": "focal_length_type",
    "zoom_type": "focal_length_type",
    "prime_or_zoom": "focal_length_type",
    "aperture": "max_aperture",
    "maximum_aperture": "max_aperture",
    "aperture_max": "max_aperture",
    "max_aperture": "max_aperture",
}

CATEGORY_CODE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "camera_interchangeable_lens",
            "interchangeable_lens",
            "lens",
            "镜头",
            "可换镜头",
            "定焦",
            "变焦",
            "焦距",
        ),
        "camera_interchangeable_lens",
    ),
    (("camera_body", "body", "机身", "相机机身"), "camera_body"),
    (("phone", "smartphone", "手机"), "phone"),
    (("apple_computer", "macbook", "mac", "苹果电脑"), "apple_computer"),
    (("garmin_watch", "garmin", "佳明", "手表"), "garmin_watch"),
)


CATEGORY_GRANULARITY_POLICIES: dict[str, CategoryGranularityPolicy] = {
    "camera_interchangeable_lens": CategoryGranularityPolicy(
        canonical_code="camera_interchangeable_lens",
        aliases=(
            "camera_interchangeable_lens",
            "interchangeable_lens",
            "lens",
            "prime_lens",
            "zoom_lens",
            "镜头",
            "可换镜头",
            "定焦",
            "变焦",
            "f1.2",
            "f1.4",
            "f2.8",
        ),
        force_single_category=True,
        variant_dimensions=(
            GranularityVariantDimension(
                attribute_code="focal_length_type",
                dimension_name="焦距类型",
                option_signals={
                    "prime": (
                        "prime",
                        "定焦",
                        "f1.2",
                        "f1.4",
                        "f1.8",
                        "50 1.2",
                        "50mm",
                        "85mm",
                        "105mm",
                    ),
                    "zoom": (
                        "zoom",
                        "变焦",
                        "24-70",
                        "24 70",
                        "70-200",
                        "100-400",
                        "16-35",
                        "18-55",
                    ),
                },
            ),
        ),
    ),
}


CATEGORY_REQUIRED_ATTRIBUTES: dict[str, tuple[dict[str, Any], ...]] = {
    "camera_body": (
        {
            "code": "mount_system",
            "name": "机身卡口",
            "dataType": "TEXT",
            "valueScope": "SPU",
            "unit": None,
            "isMulti": False,
            "status": "ACTIVE",
            "options": [],
        },
        {
            "code": "sensor_format",
            "name": "传感器画幅",
            "dataType": "TEXT",
            "valueScope": "SPU",
            "unit": None,
            "isMulti": False,
            "status": "ACTIVE",
            "options": [],
        },
        {
            "code": "pixel_resolution",
            "name": "像素分辨率",
            "dataType": "TEXT",
            "valueScope": "SPU",
            "unit": None,
            "isMulti": False,
            "status": "ACTIVE",
            "options": [],
        },
        {
            "code": "camera_type",
            "name": "相机类型",
            "dataType": "TEXT",
            "valueScope": "SPU",
            "unit": None,
            "isMulti": False,
            "status": "ACTIVE",
            "options": [],
        },
    ),
    "camera_interchangeable_lens": (
        {
            "code": "mount_system",
            "name": "镜头卡口",
            "dataType": "TEXT",
            "valueScope": "SPU",
            "unit": None,
            "isMulti": False,
            "status": "ACTIVE",
            "options": [],
        },
        {
            "code": "focal_length_range",
            "name": "焦段",
            "dataType": "TEXT",
            "valueScope": "SPU",
            "unit": "mm",
            "isMulti": False,
            "status": "ACTIVE",
            "options": [],
        },
        {
            "code": "max_aperture",
            "name": "最大光圈",
            "dataType": "TEXT",
            "valueScope": "SPU",
            "unit": None,
            "isMulti": False,
            "status": "ACTIVE",
            "options": [],
        },
        {
            "code": "focal_length_type",
            "name": "焦距类型",
            "dataType": "ENUM",
            "valueScope": "SPU",
            "unit": None,
            "isMulti": False,
            "status": "ACTIVE",
            "options": [
                {"optionCode": "prime", "optionName": "定焦", "sortNo": 10, "status": "ACTIVE"},
                {"optionCode": "zoom", "optionName": "变焦", "sortNo": 20, "status": "ACTIVE"},
            ],
        },
    ),
}


CATEGORY_REQUIRED_TEMPLATE_LAYOUTS: dict[str, tuple[tuple[str, bool, bool, bool, bool, int], ...]] = {
    "camera_body": (
        ("brand_name", True, True, True, True, 10),
        ("model_name", True, True, True, True, 20),
        ("mount_system", True, False, True, True, 30),
        ("sensor_format", True, False, True, True, 40),
        ("pixel_resolution", False, False, True, True, 50),
        ("camera_type", False, False, True, True, 60),
        ("generation", False, False, False, True, 70),
    ),
    "camera_interchangeable_lens": (
        ("brand_name", True, True, True, True, 10),
        ("model_name", True, True, True, True, 20),
        ("mount_system", True, False, True, True, 30),
        ("focal_length_type", False, False, True, True, 40),
        ("focal_length_range", True, False, True, True, 50),
        ("max_aperture", True, False, True, True, 60),
    )
}


CATEGORY_ATTRIBUTE_SANITIZATION_POLICIES: dict[str, CategoryAttributeSanitizationPolicy] = {
    "camera_interchangeable_lens": CategoryAttributeSanitizationPolicy(
        blocked_attribute_codes=frozenset(
            {
                "camera_type",
                "camera_body_type",
                "sensor_type",
                "sensor_format",
                "sensor_size",
                "pixel_count",
                "megapixels",
                "shutter_count",
                "continuous_shooting_speed",
                "video_resolution",
                "body_weight",
                "body_color",
                "body_condition",
                "camera_serial",
                "ibis",
            }
        ),
        blocked_code_keywords=(
            "sensor",
            "pixel",
            "megapixel",
            "shutter",
            "body",
            "camera_type",
            "video_resolution",
            "连拍",
        ),
        blocked_name_keywords=(
            "机身",
            "传感器",
            "像素",
            "快门",
            "连拍",
            "视频分辨率",
            "机身防抖",
            "机身序列号",
        ),
    ),
}


def generate_category_ai_draft(
    *,
    description: str,
    category_code_hint: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return generate_category_ai_draft_with_session(
            session,
            description=description,
            category_code_hint=category_code_hint,
        )


def generate_category_ai_draft_with_session(
    session: Session,
    *,
    description: str,
    category_code_hint: str | None = None,
) -> dict[str, Any]:
    normalized_description = str(description or "").strip()
    if not normalized_description:
        raise CategoryAIConfigError("description is required.")
    if not llm_is_configured():
        raise CategoryAIConfigError("LLM is not configured. Please set AI_BASE_URL / AI_MODEL / AI_API_KEY.")

    settings = get_settings()
    user_prompt_parts = [
        "请基于以下自然语言需求，产出新品类配置草案 JSON：",
        normalized_description,
    ]
    if category_code_hint:
        user_prompt_parts.append(f"候选 category code 提示: {str(category_code_hint).strip()}")

    response_payload = call_openai_compatible_chat(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout_sec=settings.ai_timeout_sec,
        enable_thinking=settings.ai_enable_thinking,
        messages=[
            {"role": "system", "content": AI_DRAFT_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_prompt_parts)},
        ],
    )
    response_text = extract_message_content(response_payload)
    parsed = _extract_ai_json_payload(response_text)
    draft = normalize_category_ai_draft(parsed, description=normalized_description, category_code_hint=category_code_hint)

    return {
        "description": normalized_description,
        "provider": settings.ai_provider,
        "model": settings.ai_model,
        "draft": draft,
    }


def apply_category_ai_draft(
    *,
    operator_id: str,
    draft: dict[str, Any],
    dry_run: bool = False,
    allow_existing_category_update: bool = False,
    allow_active_template_rebind: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = apply_category_ai_draft_with_session(
            session,
            operator_id=operator_id,
            draft=draft,
            dry_run=dry_run,
            allow_existing_category_update=allow_existing_category_update,
            allow_active_template_rebind=allow_active_template_rebind,
        )
        if dry_run:
            session.rollback()
        return result


def apply_category_ai_draft_with_session(
    session: Session,
    *,
    operator_id: str,
    draft: dict[str, Any],
    dry_run: bool = False,
    allow_existing_category_update: bool = False,
    allow_active_template_rebind: bool = False,
) -> dict[str, Any]:
    normalized_operator = str(operator_id or "").strip()
    if not normalized_operator:
        raise CategoryAIConfigError("operator_id is required.")

    normalized = normalize_category_ai_draft(draft, description=None, category_code_hint=None)
    category = dict(normalized["category"])
    runtime = dict(normalized["runtime"])
    attributes = list(normalized["attributes"])
    template = dict(normalized["template"])
    template_items = list(template.get("items") or [])
    existing_category = session.execute(
        select(Category).where(Category.code == str(category["code"]))
    ).scalar_one_or_none()
    category_exists = existing_category is not None
    existing_active_template_id = None
    if category_exists and existing_category is not None:
        active_template = session.execute(
            select(CategoryRuntimeProfile.active_template_id).where(
                CategoryRuntimeProfile.category_id == str(existing_category.id)
            )
        ).scalar_one_or_none()
        if active_template:
            existing_active_template_id = str(active_template)

    if category_exists and not allow_existing_category_update:
        raise CategoryAIConfigError(
            "AI apply blocked: category code already exists. "
            "Use a new category code, or explicitly allow existing-category update in AI apply."
        )
    if category_exists and existing_category is not None:
        # Protect taxonomy identity from accidental semantic drift.
        category = {
            "code": str(existing_category.code),
            "name": str(existing_category.name),
            "path": str(existing_category.path),
            "level": int(existing_category.level or 2),
            "status": str(existing_category.status or "ACTIVE"),
        }

    bind_requested = bool(template.get("bindAsActiveTemplate", True))
    bind_as_active_template = bind_requested and (not category_exists or allow_active_template_rebind)

    category_result = upsert_category_config_with_session(
        session,
        payload={
            "code": category["code"],
            "name": category["name"],
            "path": category["path"],
            "level": int(category.get("level", 2) or 2),
            "status": category.get("status", "ACTIVE"),
            "activeTemplateId": existing_active_template_id,
            "promptProfile": runtime["promptProfile"],
            "extractorProfile": runtime.get("extractorProfile"),
            "validatorProfile": runtime.get("validatorProfile"),
            "llmProviderOverride": runtime.get("llmProviderOverride"),
            "llmModelOverride": runtime.get("llmModelOverride"),
            "runtimeStatus": runtime.get("runtimeStatus", "ACTIVE"),
            "runtimeMetadata": dict(runtime.get("runtimeMetadata") or {}),
        },
        operator_id=normalized_operator,
        dry_run=dry_run,
    )

    attribute_results: list[dict[str, Any]] = []
    for attribute_payload in attributes:
        result = upsert_attribute_config_with_session(
            session,
            payload={
                "code": attribute_payload["code"],
                "name": attribute_payload["name"],
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": attribute_payload["dataType"],
                "valueScope": attribute_payload["valueScope"],
                "unit": attribute_payload.get("unit"),
                "status": attribute_payload.get("status", "ACTIVE"),
                "isMulti": bool(attribute_payload.get("isMulti", False)),
                "isCommon": bool(
                    attribute_payload.get("isCommon")
                    or is_runtime_common_attribute(
                        code=str(attribute_payload.get("code") or ""),
                        validation_schema=dict(attribute_payload.get("validationSchema") or {}),
                    )
                ),
                "validationSchema": dict(attribute_payload.get("validationSchema") or {}),
                "options": list(attribute_payload.get("options") or []),
            },
            operator_id=normalized_operator,
            dry_run=dry_run,
        )
        attribute_results.append(result["attribute"])

    category_id = str(category_result["category"]["id"])
    version = _next_template_version(session, category_id=category_id)
    template_result = upsert_template_config_with_session(
        session,
        payload={
            "categoryId": category_id,
            "categoryCode": category["code"],
            "version": version,
            "status": template.get("status", "PUBLISHED"),
            "promptProfile": runtime["promptProfile"],
            "bindAsActiveTemplate": bind_as_active_template,
            "extractorProfile": runtime.get("extractorProfile"),
            "validatorProfile": runtime.get("validatorProfile"),
            "llmProviderOverride": runtime.get("llmProviderOverride"),
            "llmModelOverride": runtime.get("llmModelOverride"),
            "runtimeStatus": runtime.get("runtimeStatus", "ACTIVE"),
            "runtimeMetadata": dict(runtime.get("runtimeMetadata") or {}),
            "items": template_items,
        },
        operator_id=normalized_operator,
        dry_run=dry_run,
    )

    return {
        "dryRun": dry_run,
        "categoryExists": category_exists,
        "allowExistingCategoryUpdate": bool(allow_existing_category_update),
        "bindRequested": bind_requested,
        "bindApplied": bind_as_active_template,
        "allowActiveTemplateRebind": bool(allow_active_template_rebind),
        "category": category_result.get("category"),
        "runtimeProfile": template_result.get("runtimeProfile") or category_result.get("runtimeProfile"),
        "template": template_result.get("template"),
        "attributes": attribute_results,
        "attributeCount": len(attribute_results),
        "templateItemCount": len(template_items),
        "governance": normalized.get("governance"),
        "draft": normalized,
    }


def normalize_category_ai_draft(
    payload: dict[str, Any],
    *,
    description: str | None,
    category_code_hint: str | None,
) -> dict[str, Any]:
    raw = dict(payload or {})
    if "draft" in raw and isinstance(raw.get("draft"), dict):
        raw = dict(raw["draft"])

    category_raw = dict(raw.get("category") or {})
    runtime_raw = dict(raw.get("runtime") or {})
    attributes_raw = list(raw.get("attributes") or [])
    template_raw = dict(raw.get("template") or {})
    input_governance = dict(raw.get("governance") or {}) if isinstance(raw.get("governance"), dict) else {}

    input_category_code = _normalize_category_code(
        category_raw.get("code"),
        hint=category_code_hint,
        fallback_text=description or category_raw.get("name") or "new_category",
    )
    resolved_category_code = _canonicalize_category_code(
        input_category_code,
        description=description,
        category_code_hint=category_code_hint,
    )
    raw_category_name = _normalize_text(category_raw.get("name"))
    governance = _build_category_granularity_governance(
        input_category_code=input_category_code,
        resolved_category_code=resolved_category_code,
        category_name=raw_category_name,
        description=description,
        category_code_hint=category_code_hint,
    )
    governance = _merge_governance_payload(generated=governance, input_payload=input_governance)
    resolved_category_code = str(governance.get("canonicalCategoryCode") or resolved_category_code or "new_category")
    category_name = raw_category_name or _fallback_category_name(description, resolved_category_code)
    category_path = _normalize_text(category_raw.get("path")) or f"category/{resolved_category_code.replace('_', '-')}"
    category_level = _coerce_int(category_raw.get("level"), default=2, minimum=1, maximum=9)
    category_status = _coerce_status(category_raw.get("status"), allowed={"ACTIVE", "INACTIVE", "ARCHIVED"}, default="ACTIVE")

    runtime_default = get_category_runtime_default(resolved_category_code)
    prompt_profile = _normalize_profile_code(runtime_raw.get("promptProfile"))
    if not prompt_profile:
        prompt_profile = runtime_default.prompt_profile if runtime_default is not None else f"{resolved_category_code}_extract_v1"
    extractor_profile = _normalize_profile_code(runtime_raw.get("extractorProfile")) or (
        runtime_default.extractor_profile if runtime_default is not None else "default"
    )
    validator_profile = _normalize_profile_code(runtime_raw.get("validatorProfile")) or (
        runtime_default.validator_profile if runtime_default is not None else None
    )
    runtime_status = _coerce_status(
        runtime_raw.get("runtimeStatus") or runtime_raw.get("status"),
        allowed={"ACTIVE", "INACTIVE"},
        default="ACTIVE",
    )
    if governance.get("categoryCodeAdjusted") and runtime_default is not None:
        expected_prefix = f"{resolved_category_code}_"
        if not str(prompt_profile or "").startswith(expected_prefix):
            prompt_profile = runtime_default.prompt_profile
    runtime_metadata_payload = dict(runtime_raw.get("runtimeMetadata") or runtime_raw.get("metadata") or {})

    normalized_attributes = _normalize_attributes(attributes_raw)
    normalized_attributes = _ensure_minimum_attributes(normalized_attributes)
    normalized_attributes, removed_attributes = _sanitize_category_attributes(
        category_code=resolved_category_code,
        attributes=normalized_attributes,
    )
    normalized_attributes = _ensure_category_special_attributes(
        category_code=resolved_category_code,
        attributes=normalized_attributes,
    )
    attribute_codes = {row["code"] for row in normalized_attributes}
    requested_template_item_codes = _extract_requested_template_attribute_codes(template_raw.get("items"))

    normalized_template_items = _normalize_template_items(template_raw.get("items"), attribute_codes=attribute_codes)
    if not normalized_template_items:
        normalized_template_items = _build_template_items_from_attributes(normalized_attributes)
    normalized_template_items = _ensure_category_special_template_items(
        category_code=resolved_category_code,
        template_items=normalized_template_items,
    )
    final_template_item_codes = {str(row.get("attributeCode")) for row in normalized_template_items if str(row.get("attributeCode") or "").strip()}
    dropped_template_item_codes = sorted(
        code for code in requested_template_item_codes if code and code not in final_template_item_codes
    )
    governance = _merge_sanitization_governance(
        governance=governance,
        removed_attributes=removed_attributes,
        dropped_template_item_codes=dropped_template_item_codes,
    )
    runtime_metadata = _merge_runtime_metadata(
        runtime_metadata_payload,
        governance=governance,
    )

    if resolved_category_code == "camera_interchangeable_lens" and runtime_default is not None:
        if not prompt_profile or "lens" not in str(prompt_profile).lower():
            prompt_profile = runtime_default.prompt_profile
        if not validator_profile:
            validator_profile = runtime_default.validator_profile

    template_status = _coerce_status(template_raw.get("status"), allowed={"DRAFT", "PUBLISHED", "RETIRED"}, default="PUBLISHED")
    template_version = _coerce_int(template_raw.get("version"), default=1, minimum=1, maximum=9999)

    return {
        "category": {
            "code": resolved_category_code,
            "name": category_name,
            "path": category_path,
            "level": category_level,
            "status": category_status,
        },
        "runtime": {
            "promptProfile": prompt_profile,
            "extractorProfile": extractor_profile,
            "validatorProfile": validator_profile,
            "llmProviderOverride": _normalize_text(runtime_raw.get("llmProviderOverride")),
            "llmModelOverride": _normalize_text(runtime_raw.get("llmModelOverride")),
            "runtimeStatus": runtime_status,
            "runtimeMetadata": runtime_metadata,
        },
        "attributes": normalized_attributes,
        "template": {
            "version": template_version,
            "status": template_status,
            "bindAsActiveTemplate": bool(template_raw.get("bindAsActiveTemplate", True)),
            "items": normalized_template_items,
        },
        "governance": governance,
    }


def _normalize_attributes(values: list[Any]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        raw_name = _normalize_text(value.get("name")) or _normalize_text(value.get("attributeName"))
        code = _normalize_attribute_code(value.get("code") or value.get("attributeCode"), fallback_name=raw_name)
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        data_type = _coerce_status(value.get("dataType"), allowed={"TEXT", "NUMBER", "BOOLEAN", "ENUM", "JSON"}, default="TEXT")
        value_scope = _coerce_status(value.get("valueScope"), allowed={"SPU", "SKU", "SALE"}, default="SPU")
        options = _normalize_options(value.get("options"))
        normalized_rows.append(
            {
                "code": code,
                "name": raw_name or _humanize_attribute_name(code),
                "dataType": data_type,
                "valueScope": value_scope,
                "unit": _normalize_text(value.get("unit")),
                "isMulti": bool(value.get("isMulti", False)),
                "isCommon": bool(value.get("isCommon", False)),
                "validationSchema": dict(value.get("validationSchema") or {}),
                "status": _coerce_status(
                    value.get("status"),
                    allowed={"ACTIVE", "DRAFT", "DISABLED", "DEPRECATED"},
                    default="ACTIVE",
                ),
                "options": options if data_type == "ENUM" else [],
            }
        )
    return normalized_rows


def _ensure_minimum_attributes(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(values)
    code_set = {row["code"] for row in rows}
    minimum_rows = [
        {"code": "brand_name", "name": "品牌", "dataType": "TEXT", "valueScope": "SPU"},
        {"code": "model_name", "name": "型号", "dataType": "TEXT", "valueScope": "SPU"},
    ]
    for row in minimum_rows:
        if row["code"] in code_set:
            continue
        rows.append(
            {
                "code": row["code"],
                "name": row["name"],
                "dataType": row["dataType"],
                "valueScope": row["valueScope"],
                "unit": None,
                "isMulti": False,
                "status": "ACTIVE",
                "options": [],
            }
        )
    return rows


def _normalize_template_items(values: Any, *, attribute_codes: set[str]) -> list[dict[str, Any]]:
    rows = values if isinstance(values, list) else []
    normalized_rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, value in enumerate(rows):
        if not isinstance(value, dict):
            continue
        code = _normalize_attribute_code(
            value.get("attributeCode"),
            fallback_name=None,
        )
        if not code or code in seen_codes:
            continue
        if code not in attribute_codes:
            continue
        seen_codes.add(code)
        normalized_rows.append(
            {
                "attributeCode": code,
                "isRequired": bool(value.get("isRequired", code in {"brand_name", "model_name"})),
                "isSale": bool(value.get("isSale", False)),
                "isFilter": bool(value.get("isFilter", True)),
                "isSearch": bool(value.get("isSearch", code in {"brand_name", "model_name", "product_line"})),
                "isDisplay": bool(value.get("isDisplay", True)),
                "sortNo": _coerce_int(value.get("sortNo"), default=(index + 1) * 10, minimum=1, maximum=9999),
            }
        )
    return sorted(normalized_rows, key=lambda row: (int(row["sortNo"]), row["attributeCode"]))


def _build_template_items_from_attributes(attributes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, attribute in enumerate(attributes):
        code = str(attribute["code"])
        rows.append(
            {
                "attributeCode": code,
                "isRequired": code in {"brand_name", "model_name"},
                "isSale": False,
                "isFilter": True,
                "isSearch": code in {"brand_name", "model_name", "product_line"},
                "isDisplay": True,
                "sortNo": (index + 1) * 10,
            }
        )
    return rows


def _normalize_options(values: Any) -> list[dict[str, Any]]:
    rows = values if isinstance(values, list) else []
    normalized_rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, value in enumerate(rows):
        if not isinstance(value, dict):
            continue
        code = _normalize_category_code(
            value.get("optionCode"),
            hint=None,
            fallback_text=value.get("optionName") or f"option_{index+1}",
        )
        if not code or code == "new_category" or code in seen_codes:
            code = f"option_{index + 1}"
        name = _normalize_text(value.get("optionName")) or code
        if code in seen_codes:
            continue
        seen_codes.add(code)
        normalized_rows.append(
            {
                "optionCode": code,
                "optionName": name,
                "sortNo": _coerce_int(value.get("sortNo"), default=(index + 1) * 10, minimum=1, maximum=9999),
                "status": _coerce_status(
                    value.get("status"),
                    allowed={"ACTIVE", "DRAFT", "DISABLED", "DEPRECATED"},
                    default="ACTIVE",
                ),
            }
        )
    return normalized_rows


def _ensure_category_special_attributes(
    *,
    category_code: str,
    attributes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = list(attributes)
    required_attributes = CATEGORY_REQUIRED_ATTRIBUTES.get(category_code)
    if not required_attributes:
        return rows
    index_by_code = {str(row.get("code")): idx for idx, row in enumerate(rows)}

    def upsert(row: dict[str, Any]) -> None:
        code = str(row["code"])
        if code in index_by_code:
            existing = dict(rows[index_by_code[code]])
            existing.update({k: v for k, v in row.items() if v is not None})
            rows[index_by_code[code]] = existing
            return
        rows.append(row)
        index_by_code[code] = len(rows) - 1

    for required_row in required_attributes:
        upsert(dict(required_row))
    return rows


def _ensure_category_special_template_items(
    *,
    category_code: str,
    template_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in template_items]
    required_layout = CATEGORY_REQUIRED_TEMPLATE_LAYOUTS.get(category_code)
    if not required_layout:
        return sorted(rows, key=lambda row: (int(row.get("sortNo", 0) or 0), str(row.get("attributeCode") or "")))

    by_code = {str(row.get("attributeCode")): row for row in rows if str(row.get("attributeCode") or "").strip()}
    for code, required, search, filter_flag, display, sort_no in required_layout:
        existing = dict(by_code.get(code) or {})
        existing.update(
            {
                "attributeCode": code,
                "isRequired": bool(existing.get("isRequired", required)),
                "isSale": bool(existing.get("isSale", False)),
                "isFilter": bool(existing.get("isFilter", filter_flag)),
                "isSearch": bool(existing.get("isSearch", search)),
                "isDisplay": bool(existing.get("isDisplay", display)),
                "sortNo": int(existing.get("sortNo", sort_no) or sort_no),
            }
        )
        by_code[code] = existing
    return sorted(by_code.values(), key=lambda row: (int(row.get("sortNo", 0) or 0), str(row.get("attributeCode") or "")))


def _sanitize_category_attributes(
    *,
    category_code: str,
    attributes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    policy = CATEGORY_ATTRIBUTE_SANITIZATION_POLICIES.get(category_code)
    if policy is None:
        return list(attributes), []

    kept_rows: list[dict[str, Any]] = []
    removed_rows: list[dict[str, str]] = []
    for row in attributes:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        reason = _resolve_attribute_block_reason(
            policy=policy,
            attribute_code=code,
            attribute_name=name,
        )
        if reason is None:
            kept_rows.append(row)
            continue
        removed_rows.append(
            {
                "code": code,
                "name": name or code,
                "reason": reason,
            }
        )
    return kept_rows, removed_rows


def _resolve_attribute_block_reason(
    *,
    policy: CategoryAttributeSanitizationPolicy,
    attribute_code: str,
    attribute_name: str,
) -> str | None:
    normalized_code = str(attribute_code or "").strip().lower()
    normalized_name = str(attribute_name or "").strip().lower()

    if normalized_code in policy.blocked_attribute_codes:
        return "blocked_attribute_code"

    for token in policy.blocked_code_keywords:
        normalized_token = str(token or "").strip().lower()
        if normalized_token and normalized_token in normalized_code:
            return f"blocked_code_keyword:{normalized_token}"

    for token in policy.blocked_name_keywords:
        normalized_token = str(token or "").strip().lower()
        if normalized_token and normalized_token in normalized_name:
            return f"blocked_name_keyword:{normalized_token}"
    return None


def _extract_requested_template_attribute_codes(values: Any) -> list[str]:
    rows = values if isinstance(values, list) else []
    requested_codes: list[str] = []
    seen_codes: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _normalize_attribute_code(row.get("attributeCode"), fallback_name=None)
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        requested_codes.append(code)
    return requested_codes


def _merge_sanitization_governance(
    *,
    governance: dict[str, Any],
    removed_attributes: list[dict[str, str]],
    dropped_template_item_codes: list[str],
) -> dict[str, Any]:
    merged = dict(governance or {})
    removed_codes = [str(row.get("code") or "").strip() for row in removed_attributes if str(row.get("code") or "").strip()]
    merged["sanitizationApplied"] = bool(removed_attributes or dropped_template_item_codes)
    merged["removedAttributeCodes"] = sorted(set(removed_codes))
    merged["removedTemplateItemCodes"] = sorted(set(str(code or "").strip() for code in dropped_template_item_codes if str(code or "").strip()))
    merged["removedAttributes"] = list(removed_attributes)
    decision_log = list(merged.get("decisionLog") or [])
    if removed_codes:
        decision_log.append(
            "sanitized cross-domain attributes: " + ", ".join(sorted(set(removed_codes)))
        )
    if dropped_template_item_codes:
        decision_log.append(
            "removed template items without valid attributes: " + ", ".join(sorted(set(dropped_template_item_codes)))
        )
    merged["decisionLog"] = _dedupe_text_entries(decision_log)
    return merged


def _next_template_version(session: Session, *, category_id: str) -> int:
    current = session.execute(
        select(func.max(CategoryAttrTemplate.version)).where(CategoryAttrTemplate.category_id == category_id)
    ).scalar_one()
    return int(current or 0) + 1


def _normalize_category_code(value: Any, *, hint: str | None, fallback_text: Any) -> str:
    candidates = [value, hint, fallback_text]
    for candidate in candidates:
        normalized = _slugify(candidate)
        if normalized:
            return normalized
    return "new_category"


def _normalize_attribute_code(value: Any, *, fallback_name: str | None) -> str:
    direct = _slugify(value)
    direct = ATTRIBUTE_CODE_ALIASES.get(direct, direct)
    if direct:
        return direct
    normalized_name = str(fallback_name or "").strip()
    for keyword, mapped_code in ATTRIBUTE_CODE_HINTS:
        if keyword and keyword in normalized_name:
            return mapped_code
    fallback = _slugify(normalized_name)
    if fallback:
        return fallback
    return ""


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^\w\s\-\/]+", " ", text, flags=re.UNICODE)
    text = text.replace("/", "_")
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return ""
    if not re.search(r"[a-z]", text):
        return ""
    return text[:64]


def _humanize_attribute_name(code: str) -> str:
    return str(code or "").replace("_", " ").strip().title() or "Attribute"


def _fallback_category_name(description: str | None, category_code: str) -> str:
    text = str(description or "").strip()
    if text:
        return text[:48]
    return category_code.replace("_", " ").title()


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_profile_code(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    lowered = text.lower()
    placeholders = {"optional", "none", "null", "n/a", "-", "default_profile", "snake_case_extract_v1"}
    if lowered in placeholders:
        return None
    if "snake_case" in lowered:
        return None
    return text


def _canonicalize_category_code(
    category_code: str,
    *,
    description: str | None,
    category_code_hint: str | None,
) -> str:
    normalized = str(category_code or "").strip()
    if category_code_hint:
        hinted = _slugify(category_code_hint)
        if hinted:
            return hinted
    search_space = " ".join(
        value
        for value in [
            normalized.lower(),
            str(description or "").lower(),
        ]
        if value
    )
    for policy in CATEGORY_GRANULARITY_POLICIES.values():
        if any(alias and alias.lower() in search_space for alias in policy.aliases):
            return policy.canonical_code
    for aliases, canonical in CATEGORY_CODE_HINTS:
        if any(alias and alias.lower() in search_space for alias in aliases):
            return canonical
    return normalized or "new_category"


def _build_category_granularity_governance(
    *,
    input_category_code: str,
    resolved_category_code: str,
    category_name: str | None,
    description: str | None,
    category_code_hint: str | None,
) -> dict[str, Any]:
    search_space = _build_granularity_search_space(
        input_category_code=input_category_code,
        resolved_category_code=resolved_category_code,
        category_name=category_name,
        description=description,
        category_code_hint=category_code_hint,
    )
    policy, matched_alias = _resolve_granularity_policy(
        resolved_category_code=resolved_category_code,
        search_space=search_space,
    )
    canonical_category_code = str(resolved_category_code or "new_category")
    decision_log: list[str] = []
    variant_signals: list[dict[str, Any]] = []
    policy_applied = False

    if policy is not None:
        policy_applied = True
        if policy.force_single_category and canonical_category_code != policy.canonical_code:
            decision_log.append(
                f"category_code '{canonical_category_code}' matched policy '{policy.canonical_code}', canonicalized."
            )
            canonical_category_code = policy.canonical_code
        variant_signals = _collect_variant_signals(policy=policy, search_space=search_space)
        if variant_signals:
            signal_attr_codes = ", ".join(sorted({str(row.get('attributeCode')) for row in variant_signals}))
            decision_log.append(f"detected variant signals for attributes: {signal_attr_codes}.")

    if policy is not None and not decision_log:
        decision_log.append(f"matched policy '{policy.canonical_code}', no canonicalization needed.")
    if not decision_log:
        decision_log.append("no canonicalization rule triggered.")

    return {
        "policyVersion": "category_granularity_v1",
        "policyApplied": policy_applied,
        "policyCode": policy.canonical_code if policy is not None else None,
        "matchedAlias": matched_alias,
        "inputCategoryCode": input_category_code or None,
        "canonicalCategoryCode": canonical_category_code,
        "categoryCodeAdjusted": canonical_category_code != str(resolved_category_code or "new_category"),
        "variantSignals": variant_signals,
        "decisionLog": decision_log,
    }


def _build_granularity_search_space(
    *,
    input_category_code: str,
    resolved_category_code: str,
    category_name: str | None,
    description: str | None,
    category_code_hint: str | None,
) -> str:
    return " ".join(
        str(value).lower()
        for value in [
            input_category_code,
            resolved_category_code,
            category_name or "",
            description or "",
            category_code_hint or "",
        ]
        if str(value or "").strip()
    )


def _resolve_granularity_policy(
    *,
    resolved_category_code: str,
    search_space: str,
) -> tuple[CategoryGranularityPolicy | None, str | None]:
    direct = CATEGORY_GRANULARITY_POLICIES.get(str(resolved_category_code or "").strip())
    if direct is not None:
        return direct, direct.canonical_code
    for policy in CATEGORY_GRANULARITY_POLICIES.values():
        for alias in policy.aliases:
            token = str(alias or "").strip().lower()
            if token and token in search_space:
                return policy, alias
    return None, None


def _collect_variant_signals(
    *,
    policy: CategoryGranularityPolicy,
    search_space: str,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for dimension in policy.variant_dimensions:
        option_codes: list[str] = []
        matched_tokens: list[dict[str, str]] = []
        for option_code, tokens in dimension.option_signals.items():
            matched_token = next((token for token in tokens if token and token.lower() in search_space), None)
            if not matched_token:
                continue
            option_codes.append(option_code)
            matched_tokens.append(
                {
                    "optionCode": option_code,
                    "token": matched_token,
                }
            )
        if not option_codes:
            continue
        signals.append(
            {
                "attributeCode": dimension.attribute_code,
                "dimensionName": dimension.dimension_name,
                "optionCodes": option_codes,
                "matchedTokens": matched_tokens,
            }
        )
    return signals


def _merge_runtime_metadata(
    base_metadata: dict[str, Any],
    *,
    governance: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base_metadata or {})
    existing = merged.get("taxonomyGovernance")
    existing_dict = dict(existing) if isinstance(existing, dict) else {}
    existing_dict.update(governance)
    merged["taxonomyGovernance"] = existing_dict
    return merged


def _merge_governance_payload(
    *,
    generated: dict[str, Any],
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    if not input_payload:
        return generated
    merged = dict(generated)
    if not merged.get("policyVersion") and input_payload.get("policyVersion"):
        merged["policyVersion"] = input_payload.get("policyVersion")
    input_decisions = input_payload.get("decisionLog") if isinstance(input_payload.get("decisionLog"), list) else []
    generated_decisions = merged.get("decisionLog") if isinstance(merged.get("decisionLog"), list) else []
    merged["decisionLog"] = _dedupe_text_entries([*generated_decisions, *input_decisions])
    input_signals = input_payload.get("variantSignals") if isinstance(input_payload.get("variantSignals"), list) else []
    if input_signals and not merged.get("variantSignals"):
        merged["variantSignals"] = input_signals
    if input_payload.get("sanitizationApplied") and not merged.get("sanitizationApplied"):
        merged["sanitizationApplied"] = bool(input_payload.get("sanitizationApplied"))
    input_removed_attribute_codes = input_payload.get("removedAttributeCodes")
    if isinstance(input_removed_attribute_codes, list):
        existing_removed_codes = merged.get("removedAttributeCodes")
        existing_removed = existing_removed_codes if isinstance(existing_removed_codes, list) else []
        merged["removedAttributeCodes"] = sorted(
            set(str(code or "").strip() for code in [*existing_removed, *input_removed_attribute_codes] if str(code or "").strip())
        )
    input_removed_template_codes = input_payload.get("removedTemplateItemCodes")
    if isinstance(input_removed_template_codes, list):
        existing_removed_template_codes = merged.get("removedTemplateItemCodes")
        existing_removed_template = existing_removed_template_codes if isinstance(existing_removed_template_codes, list) else []
        merged["removedTemplateItemCodes"] = sorted(
            set(
                str(code or "").strip()
                for code in [*existing_removed_template, *input_removed_template_codes]
                if str(code or "").strip()
            )
        )
    input_removed_attributes = input_payload.get("removedAttributes")
    if isinstance(input_removed_attributes, list):
        existing_removed_attributes = merged.get("removedAttributes")
        existing_entries = existing_removed_attributes if isinstance(existing_removed_attributes, list) else []
        merged["removedAttributes"] = _dedupe_removed_attribute_entries([*existing_entries, *input_removed_attributes])
    return merged


def _dedupe_text_entries(values: list[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for row in values:
        text = str(row or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _dedupe_removed_attribute_entries(values: list[Any]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in values:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        name = str(row.get("name") or code).strip()
        reason = str(row.get("reason") or "").strip()
        key = (code, name, reason)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"code": code, "name": name, "reason": reason})
    return deduped


def _extract_ai_json_payload(response_text: Any) -> dict[str, Any]:
    text = str(response_text or "").strip()
    if not text:
        raise CategoryAIConfigError("LLM returned empty response.")
    try:
        return extract_json_object(text)
    except Exception:
        candidate = _extract_first_json_object(text)
        if not candidate:
            raise CategoryAIConfigError("LLM response does not contain a valid JSON object.")
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise CategoryAIConfigError("Failed to parse JSON from LLM response.") from exc
        if not isinstance(value, dict):
            raise CategoryAIConfigError("LLM JSON response must be an object.")
        return value


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _coerce_status(value: Any, *, allowed: set[str], default: str) -> str:
    raw = str(value or default).strip().upper()
    if raw in allowed:
        return raw
    return default


def _coerce_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = int(default)
    return max(minimum, min(maximum, numeric))
