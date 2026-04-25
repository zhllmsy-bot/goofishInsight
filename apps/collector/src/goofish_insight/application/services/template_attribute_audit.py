from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...db import session_scope
from ...models import (
    AttributeDefinition,
    Category,
    CategoryAttrTemplate,
    CategoryAttrTemplateItem,
    CategoryRuntimeProfile,
)
from .attribute_config import serialize_attribute_config, upsert_attribute_config_with_session
from .template_config import serialize_template_config, upsert_template_config_with_session


@dataclass(frozen=True, slots=True)
class TemplateAttributeSupplement:
    attribute_payload: dict[str, Any]
    template_item: dict[str, Any]
    reason: str


DEFAULT_TOP_LEVEL_CATEGORY_CODES: tuple[str, ...] = (
    "apple_computer",
    "garmin_watch",
    "camera_body",
    "camera_interchangeable_lens",
    "phone",
    "apple_airpods",
)


SUPPLEMENTS_BY_CATEGORY: dict[str, tuple[TemplateAttributeSupplement, ...]] = {
    "camera_body": (
        TemplateAttributeSupplement(
            attribute_payload={
                "code": "product_line",
                "name": "产品线",
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "status": "ACTIVE",
            },
            template_item={
                "attributeCode": "product_line",
                "isRequired": False,
                "isSale": False,
                "isFilter": True,
                "isSearch": True,
                "isDisplay": True,
                "sortNo": 25,
            },
            reason="相机机身主链已经使用 product_line 区分 Alpha / EOS R / Z / X 等业务线，当前模板缺少该身份字段。",
        ),
    ),
    "camera_interchangeable_lens": (
        TemplateAttributeSupplement(
            attribute_payload={
                "code": "lens_series",
                "name": "镜头系列",
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "status": "ACTIVE",
            },
            template_item={
                "attributeCode": "lens_series",
                "isRequired": False,
                "isSale": False,
                "isFilter": True,
                "isSearch": False,
                "isDisplay": True,
                "sortNo": 70,
            },
            reason="镜头提取链和 prompt 已经稳定输出 lens_series，但现行模板没有挂这个字段。",
        ),
        TemplateAttributeSupplement(
            attribute_payload={
                "code": "generation",
                "name": "代际",
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "status": "ACTIVE",
            },
            template_item={
                "attributeCode": "generation",
                "isRequired": False,
                "isSale": False,
                "isFilter": True,
                "isSearch": False,
                "isDisplay": True,
                "sortNo": 80,
            },
            reason="镜头需要区分一代/二代/Mark II 这类同焦段同光圈版本，当前模板缺少 generation。",
        ),
    ),
    "phone": (
        TemplateAttributeSupplement(
            attribute_payload={
                "code": "product_line",
                "name": "产品线",
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": "TEXT",
                "valueScope": "SPU",
                "status": "ACTIVE",
            },
            template_item={
                "attributeCode": "product_line",
                "isRequired": False,
                "isSale": False,
                "isFilter": True,
                "isSearch": True,
                "isDisplay": True,
                "sortNo": 25,
            },
            reason="手机 prompt 以 series 为核心身份字段，当前模板缺少 canonical 的 product_line。",
        ),
        TemplateAttributeSupplement(
            attribute_payload={
                "code": "memory_gb",
                "name": "内存",
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": "NUMBER",
                "valueScope": "SKU",
                "unit": "GB",
                "status": "ACTIVE",
            },
            template_item={
                "attributeCode": "memory_gb",
                "isRequired": False,
                "isSale": False,
                "isFilter": True,
                "isSearch": True,
                "isDisplay": True,
                "sortNo": 45,
            },
            reason="当前主提取链统一产出 memory_gb，phone 模板仍停留在 legacy memory_size。",
        ),
        TemplateAttributeSupplement(
            attribute_payload={
                "code": "storage_gb",
                "name": "存储",
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": "NUMBER",
                "valueScope": "SKU",
                "unit": "GB",
                "status": "ACTIVE",
            },
            template_item={
                "attributeCode": "storage_gb",
                "isRequired": False,
                "isSale": False,
                "isFilter": True,
                "isSearch": True,
                "isDisplay": True,
                "sortNo": 55,
            },
            reason="当前主提取链统一产出 storage_gb，phone 模板缺少 canonical 存储字段。",
        ),
        TemplateAttributeSupplement(
            attribute_payload={
                "code": "screen_size_in",
                "name": "屏幕尺寸",
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": "NUMBER",
                "valueScope": "SPU",
                "unit": "inch",
                "status": "ACTIVE",
            },
            template_item={
                "attributeCode": "screen_size_in",
                "isRequired": False,
                "isSale": False,
                "isFilter": True,
                "isSearch": False,
                "isDisplay": True,
                "sortNo": 65,
            },
            reason="phone 主提取链已经使用 canonical screen_size_in，模板仍只保留 legacy screen_size。",
        ),
    ),
}


SUPPLEMENTS_BY_PROMPT_PROFILE: dict[str, tuple[TemplateAttributeSupplement, ...]] = {
    "camera_interchangeable_lens_extract_v1": SUPPLEMENTS_BY_CATEGORY["camera_interchangeable_lens"],
    "smartphone_extract_v1": SUPPLEMENTS_BY_CATEGORY["phone"],
}


def build_template_attribute_audit(
    *,
    category_codes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return build_template_attribute_audit_with_session(
            session,
            category_codes=category_codes,
        )


def build_template_attribute_audit_with_session(
    session: Session,
    *,
    category_codes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    targets = _resolve_target_category_codes(session, category_codes=category_codes)
    contexts = _load_active_template_contexts(session, category_codes=targets)
    categories: list[dict[str, Any]] = []
    missing_total = 0
    for context in contexts:
        template_detail = serialize_template_config(
            context["template"],
            include_items=True,
            include_diff=False,
        ) or {}
        current_codes = [str(item.get("attributeCode") or "") for item in template_detail.get("items", [])]
        current_code_set = {code for code in current_codes if code}
        missing = _missing_supplements_for_category(
            category_code=context["category"].code,
            prompt_profile=context["runtime_profile"].prompt_profile,
            current_codes=current_code_set,
        )
        missing_total += len(missing)
        categories.append(
            {
                "categoryCode": context["category"].code,
                "categoryName": context["category"].name,
                "activeTemplateId": context["template"].id,
                "activeTemplateVersion": context["template"].version,
                "promptProfile": context["runtime_profile"].prompt_profile,
                "currentAttributeCodes": current_codes,
                "missingAttributes": [
                    {
                        "attributeCode": supplement.template_item["attributeCode"],
                        "reason": supplement.reason,
                        "templateItem": dict(supplement.template_item),
                        "attributePayload": dict(supplement.attribute_payload),
                    }
                    for supplement in missing
                ],
                "isTemplateSuitable": not missing,
            }
        )
    return {
        "categoryCount": len(categories),
        "categoriesWithGaps": sum(1 for item in categories if item["missingAttributes"]),
        "missingAttributeCount": missing_total,
        "categories": categories,
    }


def apply_template_attribute_supplements(
    *,
    operator_id: str,
    category_codes: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = apply_template_attribute_supplements_with_session(
            session,
            operator_id=operator_id,
            category_codes=category_codes,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def apply_template_attribute_supplements_with_session(
    session: Session,
    *,
    operator_id: str,
    category_codes: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    targets = _resolve_target_category_codes(session, category_codes=category_codes)
    contexts = _load_active_template_contexts(session, category_codes=targets)
    results: list[dict[str, Any]] = []
    for context in contexts:
        category = context["category"]
        runtime_profile = context["runtime_profile"]
        template = context["template"]
        template_detail = serialize_template_config(template, include_items=True, include_diff=False) or {}
        current_items = list(template_detail.get("items", []) or [])
        missing = _missing_supplements_for_category(
            category_code=category.code,
            prompt_profile=runtime_profile.prompt_profile,
            current_codes={
                str(item.get("attributeCode") or "")
                for item in current_items
                if str(item.get("attributeCode") or "")
            },
        )
        if not missing:
            results.append(
                {
                    "categoryCode": category.code,
                    "templateUpdated": False,
                    "missingAttributeCount": 0,
                    "template": template_detail,
                    "attributes": [],
                }
            )
            continue

        attribute_updates = [
            _ensure_attribute_active(
                session,
                code=str(supplement.template_item["attributeCode"]),
                payload=supplement.attribute_payload,
                operator_id=operator_id,
                dry_run=dry_run,
            )
            for supplement in missing
        ]
        merged_items = _merge_template_items(current_items=current_items, missing=missing)
        template_result = upsert_template_config_with_session(
            session,
            payload={
                "categoryId": category.id,
                "categoryCode": category.code,
                "status": "PUBLISHED",
                "promptProfile": runtime_profile.prompt_profile,
                "bindAsActiveTemplate": True,
                "extractorProfile": runtime_profile.extractor_profile,
                "validatorProfile": runtime_profile.validator_profile,
                "llmProviderOverride": runtime_profile.llm_provider_override,
                "llmModelOverride": runtime_profile.llm_model_override,
                "runtimeStatus": runtime_profile.status,
                "runtimeMetadata": dict(runtime_profile.metadata_json or {}),
                "items": merged_items,
            },
            operator_id=operator_id,
            dry_run=dry_run,
        )
        results.append(
            {
                "categoryCode": category.code,
                "templateUpdated": True,
                "missingAttributeCount": len(missing),
                "addedAttributeCodes": [supplement.template_item["attributeCode"] for supplement in missing],
                "attributes": [item["attribute"] for item in attribute_updates],
                "template": template_result["template"],
                "runtimeProfile": template_result.get("runtimeProfile"),
                "auditLogId": template_result.get("auditLogId"),
            }
        )
    return {
        "dryRun": dry_run,
        "categoryCount": len(results),
        "updatedCategoryCount": sum(1 for item in results if item["templateUpdated"]),
        "results": results,
    }


def _load_active_template_contexts(
    session: Session,
    *,
    category_codes: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows = list(
        session.execute(
            select(Category)
            .options(
                selectinload(Category.runtime_profile),
                selectinload(Category.templates)
                .selectinload(CategoryAttrTemplate.items)
                .selectinload(CategoryAttrTemplateItem.attribute),
            )
            .where(Category.code.in_(category_codes))
            .where(Category.status == "ACTIVE")
        ).scalars().all()
    )
    result: list[dict[str, Any]] = []
    for category in sorted(rows, key=lambda item: str(item.code or "")):
        runtime_profile = getattr(category, "runtime_profile", None)
        active_template_id = str(getattr(runtime_profile, "active_template_id", "") or "").strip()
        if runtime_profile is None or not active_template_id:
            continue
        template = next(
            (
                row
                for row in list(getattr(category, "templates", []) or [])
                if str(getattr(row, "id", "") or "") == active_template_id
            ),
            None,
        )
        if template is None:
            continue
        result.append(
            {
                "category": category,
                "runtime_profile": runtime_profile,
                "template": template,
            }
        )
    return result


def _resolve_target_category_codes(
    session: Session,
    *,
    category_codes: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if category_codes:
        return tuple(category_codes)
    rows = list(
        session.execute(
            select(Category.code)
            .join(CategoryRuntimeProfile, CategoryRuntimeProfile.category_id == Category.id)
            .where(Category.parent_id.is_(None))
            .where(Category.status == "ACTIVE")
            .where(CategoryRuntimeProfile.status == "ACTIVE")
            .order_by(Category.code.asc())
        ).scalars().all()
    )
    return tuple(rows or DEFAULT_TOP_LEVEL_CATEGORY_CODES)


def _missing_supplements_for_category(
    *,
    category_code: str,
    prompt_profile: str | None = None,
    current_codes: set[str],
) -> list[TemplateAttributeSupplement]:
    recommended: list[TemplateAttributeSupplement] = []
    seen_codes: set[str] = set()
    for supplement in SUPPLEMENTS_BY_CATEGORY.get(category_code, ()):
        code = str(supplement.template_item["attributeCode"])
        if code in seen_codes:
            continue
        recommended.append(supplement)
        seen_codes.add(code)
    for supplement in SUPPLEMENTS_BY_PROMPT_PROFILE.get(str(prompt_profile or "").strip(), ()):
        code = str(supplement.template_item["attributeCode"])
        if code in seen_codes:
            continue
        recommended.append(supplement)
        seen_codes.add(code)
    return [supplement for supplement in recommended if supplement.template_item["attributeCode"] not in current_codes]


def _merge_template_items(
    *,
    current_items: list[dict[str, Any]],
    missing: list[TemplateAttributeSupplement],
) -> list[dict[str, Any]]:
    merged = [
        {
            "attributeCode": str(item.get("attributeCode") or ""),
            "isRequired": bool(item.get("isRequired", False)),
            "isSale": bool(item.get("isSale", False)),
            "isFilter": bool(item.get("isFilter", False)),
            "isSearch": bool(item.get("isSearch", False)),
            "isDisplay": bool(item.get("isDisplay", True)),
            "sortNo": int(item.get("sortNo", 0) or 0),
        }
        for item in current_items
        if str(item.get("attributeCode") or "")
    ]
    seen = {item["attributeCode"] for item in merged}
    for supplement in missing:
        item = dict(supplement.template_item)
        code = str(item["attributeCode"])
        if code in seen:
            continue
        merged.append(item)
        seen.add(code)
    return sorted(merged, key=lambda item: (int(item.get("sortNo", 0) or 0), str(item.get("attributeCode") or "")))


def _ensure_attribute_active(
    session: Session,
    *,
    code: str,
    payload: dict[str, Any],
    operator_id: str,
    dry_run: bool,
) -> dict[str, Any]:
    existing = session.execute(
        select(AttributeDefinition).where(AttributeDefinition.code == code)
    ).scalars().all()
    row = existing[0] if existing else None
    if row is None:
        return upsert_attribute_config_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
    current = serialize_attribute_config(row) or {}
    if str(current.get("status") or "").upper() == "ACTIVE":
        return {
            "dryRun": dry_run,
            "attribute": current,
            "auditLogId": None,
        }
    merged_payload = {
        "attributeId": row.id,
        "code": current.get("code") or payload.get("code"),
        "name": current.get("name") or payload.get("name"),
        "scopeType": current.get("scopeType") or payload.get("scopeType", "PLATFORM"),
        "scopeId": current.get("scopeId") or payload.get("scopeId", "platform"),
        "dataType": current.get("dataType") or payload.get("dataType"),
        "valueScope": current.get("valueScope") or payload.get("valueScope"),
        "isMulti": bool(current.get("isMulti", payload.get("isMulti", False))),
        "unit": current.get("unit") or payload.get("unit"),
        "validationSchema": current.get("validationSchema"),
        "status": "ACTIVE",
    }
    return upsert_attribute_config_with_session(
        session,
        payload=merged_payload,
        operator_id=operator_id,
        dry_run=dry_run,
    )
