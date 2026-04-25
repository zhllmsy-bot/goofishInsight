from __future__ import annotations

from datetime import datetime
import json
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen
from uuid import uuid4

from sqlalchemy import select

from .common_runtime_attributes import (
    common_runtime_template_hint,
    is_runtime_common_attribute,
)
from .category_compat import (
    compatible_scope_keys,
    is_apple_computer_scope,
    is_garmin_watch_scope,
    normalize_scope_key,
    resolve_category_code,
)
from .application.services.catalog_queries import build_catalog_template_detail
from .application.services.model_config import normalize_model_alias
from .application.services.spec_normalization import normalize_chip_family, normalize_storage_gb
from .application.services.spec_enrichment_policy import apply_spec_enrichment_contract
from .application.services.xianyu_category_mapping import (
    load_catalog_template_detail_for_item as load_xianyu_catalog_template_detail_for_item,
)
from .db import session_scope
from .domain.catalog.blueprints import (
    build_blueprint_template_detail,
    get_catalog_backfill_blueprint,
)
from .models import (
    AttributeDefinition,
    AttributeScopeType,
    AttributeStatus,
    Category,
    CategoryModelCatalog,
    CategoryRuntimeProfile,
    Item,
)
from .settings import get_settings

EXTRACTOR_VERSION = "v1"
CATALOG_ATTRIBUTE_GROUPS = ("spuAttributes", "skuAttributes", "saleAttributes")
CANONICAL_ENRICHMENT_STATUSES = {"complete", "partial", "unresolved", "failed"}
LEGACY_DYNAMIC_ATTRIBUTE_CODES = (
    "product_line",
    "model_name",
    "generation",
    "case_size_mm",
    "is_solar",
    "display_type",
    "screen_size_in",
    "chip_family",
    "cpu_model",
    "cpu_cores",
    "gpu_cores",
    "memory_gb",
    "storage_gb",
    "edition_tags",
)

APPLE_CHIP_PATTERNS = (
    "m4 max",
    "m4 pro",
    "m4",
    "m3 ultra",
    "m3 max",
    "m3 pro",
    "m3",
    "m2 ultra",
    "m2 max",
    "m2 pro",
    "m2",
    "m1 ultra",
    "m1 max",
    "m1 pro",
    "m1",
)
APPLE_MEMORY_OPTIONS = (8, 16, 18, 24, 32, 36, 48, 64, 96, 128)
APPLE_STORAGE_GB_OPTIONS = (128, 250, 256, 500, 512, 1000, 1024)
APPLE_STORAGE_TB_OPTIONS = (1, 2, 4, 8, 16)
APPLE_MEMORY_HINT_PATTERN = r"(?:统一内存|内存|ram|运存|运行内存|运行)"
APPLE_STORAGE_HINT_PATTERN = r"(?:ssd|硬盘|固态硬盘|固态|闪存|存储)"
APPLE_SPEC_TRANSLATION = str.maketrans(
    {
        "＋": "+",
        "➕": "+",
        "﹢": "+",
        "／": "/",
        "－": "-",
        "—": "-",
        "–": "-",
    }
)

FORERUNNER_MODEL_RE = re.compile(
    r"(?:forerunner\s*)?(965|955|945|265s?|255s?|245m?|165|55)(?!\d)",
    re.IGNORECASE,
)
MARQ_VARIANT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Athlete", ("athlete", "\u9886\u8dd1\u8005")),
    ("Golfer", ("golfer", "\u9ad8\u5c14\u592b")),
    ("Aviator", ("aviator", "\u98de\u884c\u5bb6")),
    ("Captain", ("captain", "\u822a\u6d77\u5bb6")),
    ("Adventurer", ("adventurer", "\u63a2\u9669\u5bb6")),
    ("Driver", ("driver", "\u9a7e\u9a76\u8005")),
    ("Commander", ("commander", "\u6307\u6325\u5b98")),
)

GARMIN_PRODUCT_LINES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Fenix", ("fenix", "飞耐时")),
    ("Epix", ("epix",)),
    ("Instinct", ("instinct", "本能")),
    ("Forerunner", ("forerunner", "领跑者")),
    ("Venu", ("venu",)),
    ("MARQ", ("marq",)),
    ("Approach", ("approach",)),
    ("Enduro", ("enduro", "安夺")),
    ("Tactix", ("tactix", "泰铁时")),
    ("Descent", ("descent", "mk1", "mk2", "mk3")),
)

GARMIN_EDITION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Pro", (" pro", "pro ")),
    ("Sapphire", ("sapphire", "蓝宝石")),
    ("Titanium", ("titanium", "钛")),
    ("Solar", ("solar", "太阳能", "双动力")),
    ("AMOLED", ("amoled", "a屏")),
    ("Crossover", ("crossover",)),
)
GARMIN_MODEL_DEFAULTS: dict[str, dict[str, Any]] = {
    "Forerunner 965": {"case_size_mm": 47, "display_type": "AMOLED"},
    "Forerunner 955": {"case_size_mm": 46, "display_type": "MIP"},
    "Forerunner 945": {"case_size_mm": 47, "display_type": "MIP"},
    "Forerunner 265": {"case_size_mm": 46, "display_type": "AMOLED"},
    "Forerunner 265S": {"case_size_mm": 42, "display_type": "AMOLED"},
    "Forerunner 255": {"case_size_mm": 46, "display_type": "MIP"},
    "Forerunner 255S": {"case_size_mm": 41, "display_type": "MIP"},
    "Forerunner 245": {"case_size_mm": 42, "display_type": "MIP"},
    "Forerunner 245M": {"case_size_mm": 42, "display_type": "MIP"},
    "Forerunner 165": {"case_size_mm": 43, "display_type": "AMOLED"},
    "Forerunner 55": {"case_size_mm": 42, "display_type": "MIP"},
    "Instinct 2X": {"case_size_mm": 50, "display_type": "MIP"},
    "Instinct 2": {"case_size_mm": 45, "display_type": "MIP"},
    "Tactix 7": {"case_size_mm": 51},
}

LENS_BRAND_LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("尼康", ("nikon", "尼康")),
    ("佳能", ("canon", "佳能")),
    ("索尼", ("sony", "索尼")),
    ("适马", ("sigma", "适马")),
    ("腾龙", ("tamron", "腾龙")),
    ("唯卓仕", ("viltrox", "唯卓仕")),
    ("美科", ("meike", "美科")),
    ("永诺", ("yongnuo", "永诺")),
    ("图丽", ("tokina", "图丽")),
    ("蔡司", ("zeiss", "蔡司")),
    ("老蛙", ("laowa", "老蛙")),
    ("铭匠", ("ttartisan", "铭匠")),
    ("七工匠", ("7artisans", "七工匠")),
    ("森养", ("samyang", "森养")),
)
LENS_EXPLICIT_HINT_TOKENS: tuple[str, ...] = (
    "镜头",
    "定焦",
    "变焦",
    "微距",
    "镜皇",
    "大三元",
    "挂机头",
)
LENS_BODY_STRONG_TOKENS: tuple[str, ...] = (
    "机身",
    "单机",
    "微单",
    "相机",
    "全画幅",
)
LENS_BODY_BUNDLE_TOKENS: tuple[str, ...] = (
    "套机",
    "套装",
    "机身+",
    "+机身",
    "带机身",
    "含机身",
)
LENS_BODY_MODEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bz\s*(?:5|6|7|8|9|f|fc)(?:ii|iii|2|3)?\b", re.IGNORECASE),
    re.compile(r"\br\s*(?:5|6|7|8|p|50|100)(?:ii|2)?\b", re.IGNORECASE),
    re.compile(r"\ba\s*(?:7|7c|7r|7s|6700|6600|6400|6300)\b", re.IGNORECASE),
    re.compile(r"\bx[-\s]?(?:t|h|s)\s*\d\b", re.IGNORECASE),
)


@dataclass(slots=True)
class SpecEnrichmentCandidate:
    category_id: str | None = None
    template_id: str | None = None
    model_catalog_id: str | None = None
    extractor_type: str = "rule"
    extractor_version: str = EXTRACTOR_VERSION
    llm_provider: str | None = None
    llm_model: str | None = None
    status: str = "partial"
    confidence: Decimal | None = None
    needs_review: bool = False
    brand: str | None = None
    product_line: str | None = None
    model_family: str | None = None
    model_name: str | None = None
    generation: str | None = None
    case_size_mm: int | None = None
    is_solar: bool | None = None
    display_type: str | None = None
    screen_size_in: Decimal | None = None
    chip_family: str | None = None
    cpu_model: str | None = None
    cpu_cores: int | None = None
    gpu_cores: int | None = None
    memory_gb: int | None = None
    storage_gb: int | None = None
    edition_tags: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    extraction_payload: dict[str, Any] = field(default_factory=dict)

    def to_record(self, *, item: Item) -> dict[str, Any]:
        return {
            "business_domain": item.business_domain,
            "item_id_ref": item.id,
            "category_id": self.category_id or item.resolved_category_id or item.target_category_id,
            "template_id": self.template_id or item.resolved_template_id,
            "model_catalog_id": self.model_catalog_id,
            "extractor_type": self.extractor_type,
            "extractor_version": self.extractor_version,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "status": self.status,
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "brand": self.brand,
            "product_line": self.product_line,
            "model_family": self.model_family,
            "model_name": self.model_name,
            "generation": self.generation,
            "case_size_mm": self.case_size_mm,
            "is_solar": self.is_solar,
            "display_type": self.display_type,
            "screen_size_in": self.screen_size_in,
            "chip_family": self.chip_family,
            "cpu_model": self.cpu_model,
            "cpu_cores": self.cpu_cores,
            "gpu_cores": self.gpu_cores,
            "memory_gb": self.memory_gb,
            "storage_gb": self.storage_gb,
            "edition_tags": list(self.edition_tags),
            "evidence": dict(self.evidence),
            "extraction_payload": dict(self.extraction_payload),
        }


def extract_item_specs(item: Item, *, allow_llm: bool) -> SpecEnrichmentCandidate:
    runtime_context = load_runtime_context_for_item(item)
    rule_candidate = enrich_candidate_with_catalog_attributes(
        item,
        extract_rule_specs(item),
        template_detail=runtime_context.get("templateDetail"),
    )
    rule_candidate = apply_runtime_context_to_candidate(
        item=item,
        candidate=rule_candidate,
        runtime_context=runtime_context,
    )
    if not allow_llm or not should_use_llm(item=item, candidate=rule_candidate):
        return rule_candidate

    try:
        llm_candidate = extract_llm_specs(
            item=item,
            rule_candidate=rule_candidate,
            runtime_context=runtime_context,
        )
    except Exception as exc:
        rule_candidate.extraction_payload = {
            **rule_candidate.extraction_payload,
            "llm_error": str(exc),
        }
        return rule_candidate
    if llm_candidate is None:
        return rule_candidate
    return apply_runtime_context_to_candidate(
        item=item,
        candidate=merge_candidates(item=item, rule_candidate=rule_candidate, llm_candidate=llm_candidate),
        runtime_context=runtime_context,
    )


def extract_rule_specs(item: Item) -> SpecEnrichmentCandidate:
    text = build_extraction_text(item, include_source_keyword=False)
    lowered = text.lower()

    if is_garmin_watch_scope(item.business_domain):
        candidate = extract_garmin_rule(item, lowered)
    elif is_apple_computer_scope(item.business_domain):
        candidate = extract_apple_rule(item, lowered)
    elif resolve_category_code(item.business_domain) == "camera_interchangeable_lens":
        candidate = extract_lens_rule(item, lowered)
    else:
        candidate = SpecEnrichmentCandidate(
        status="unresolved",
        confidence=Decimal("0.20"),
        needs_review=True,
        evidence={"reason": "unsupported_business_domain"},
        )
    return apply_spec_enrichment_contract(item=item, candidate=candidate, source="rule")


def load_template_detail_for_business_domain(business_domain: str) -> dict[str, Any] | None:
    normalized_domain = normalize_scope_key(business_domain)
    if not normalized_domain:
        return None
    category_code = resolve_category_code(normalized_domain)
    blueprint_keys = compatible_scope_keys(normalized_domain)

    try:
        with session_scope() as session:
            category = session.execute(
                select(Category).where(Category.code == category_code)
            ).scalar_one_or_none()
            if category is not None:
                runtime_profile = session.execute(
                    select(CategoryRuntimeProfile).where(
                        CategoryRuntimeProfile.category_id == category.id,
                        CategoryRuntimeProfile.status == "ACTIVE",
                    )
                ).scalar_one_or_none()
                if runtime_profile is not None and runtime_profile.active_template_id:
                    detail = build_catalog_template_detail(session, runtime_profile.active_template_id)
                    if detail is not None:
                        return _merge_common_runtime_attributes_into_template_detail(
                            session,
                            detail,
                        )

            for blueprint_key in blueprint_keys:
                blueprint = get_catalog_backfill_blueprint(blueprint_key)
                if blueprint is None:
                    continue
                detail = build_catalog_template_detail(session, blueprint.template_id)
                if detail is not None:
                    return _merge_common_runtime_attributes_into_template_detail(
                        session,
                        detail,
                    )
    except Exception:
        pass

    for blueprint_key in blueprint_keys:
        blueprint = get_catalog_backfill_blueprint(blueprint_key)
        if blueprint is not None:
            return build_blueprint_template_detail(blueprint)
    return None


def load_runtime_context_for_item(item: Item) -> dict[str, Any]:
    with session_scope() as session:
        category = None
        runtime_profile = None
        template_detail = None

        resolved_category_id = getattr(item, "resolved_category_id", None) or getattr(item, "target_category_id", None)
        if resolved_category_id:
            category = session.get(Category, resolved_category_id)
            if category is not None:
                runtime_profile = session.execute(
                    select(CategoryRuntimeProfile).where(
                        CategoryRuntimeProfile.category_id == category.id,
                        CategoryRuntimeProfile.status == "ACTIVE",
                    )
                ).scalar_one_or_none()

        resolved_template_id = getattr(item, "resolved_template_id", None)
        if resolved_template_id:
            template_detail = build_catalog_template_detail(session, resolved_template_id)
        elif runtime_profile is not None and runtime_profile.active_template_id:
            template_detail = build_catalog_template_detail(session, runtime_profile.active_template_id)

        if template_detail is None:
            template_detail = load_xianyu_catalog_template_detail_for_item(item)
        if template_detail is None:
            template_detail = load_template_detail_for_business_domain(item.business_domain)
        if template_detail is not None:
            template_detail = _merge_common_runtime_attributes_into_template_detail(
                session,
                template_detail,
            )

        if category is None and template_detail is not None:
            category_id = (template_detail.get("category") or {}).get("id")
            if category_id:
                category = session.get(Category, category_id)
        if runtime_profile is None and category is not None:
            runtime_profile = session.execute(
                select(CategoryRuntimeProfile).where(
                    CategoryRuntimeProfile.category_id == category.id,
                    CategoryRuntimeProfile.status == "ACTIVE",
                )
            ).scalar_one_or_none()

        model_catalog = _load_model_catalog_entries(
            session,
            category_id=str(category.id) if category is not None else None,
        )

    return {
        "category": category,
        "runtimeProfile": runtime_profile,
        "templateDetail": template_detail,
        "promptProfile": getattr(runtime_profile, "prompt_profile", None),
        "modelCatalog": model_catalog,
    }


def load_template_detail_for_item(item: Item) -> dict[str, Any] | None:
    return load_runtime_context_for_item(item).get("templateDetail")


def enrich_candidate_with_catalog_attributes(
    item: Item,
    candidate: SpecEnrichmentCandidate,
    *,
    template_detail: dict[str, Any] | None = None,
) -> SpecEnrichmentCandidate:
    detail = template_detail or load_template_detail_for_item(item)
    if detail is None:
        return candidate

    payload = dict(candidate.extraction_payload or {})
    groups = _extract_catalog_attribute_groups(payload)
    if not any(groups[group] for group in CATALOG_ATTRIBUTE_GROUPS):
        groups = build_candidate_catalog_attributes(
            item=item,
            candidate=candidate,
            template_detail=detail,
        )

    payload["catalogTemplate"] = _catalog_template_metadata(detail)
    if any(groups[group] for group in CATALOG_ATTRIBUTE_GROUPS):
        payload["catalogAttributes"] = groups
    candidate.extraction_payload = payload
    return candidate


def build_candidate_catalog_attributes(
    *,
    item: Item,
    candidate: SpecEnrichmentCandidate,
    template_detail: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    groups = {group: [] for group in CATALOG_ATTRIBUTE_GROUPS}
    item_map = _template_item_map(template_detail)

    for attribute_code, template_item in item_map.items():
        legacy_value = _legacy_value_for_attribute_code(
            attribute_code,
            item=item,
            candidate=candidate,
        )
        if legacy_value is None:
            continue
        groups[_catalog_group_for_item(template_item)].extend(
            _rows_from_attribute_value(
                attribute_code=attribute_code,
                value=legacy_value,
                template_item=template_item,
            )
        )

    for group in CATALOG_ATTRIBUTE_GROUPS:
        groups[group] = _dedupe_catalog_rows(groups[group])
    return groups


def _merge_common_runtime_attributes_into_template_detail(
    session,
    template_detail: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if template_detail is None:
        return None
    source_items = [dict(row) for row in list(template_detail.get("items") or []) if isinstance(row, dict)]
    if not source_items:
        source_items = []

    by_code: dict[str, dict[str, Any]] = {}
    for row in source_items:
        attribute_code = str(row.get("attributeCode") or "").strip()
        if not attribute_code:
            continue
        by_code[attribute_code] = row

    next_sort = max((int(row.get("sortNo") or 0) for row in source_items), default=0)
    injected_count = 0
    for attribute_row in _load_common_runtime_attribute_rows(session):
        attribute_code = str(getattr(attribute_row, "code", "") or "").strip()
        if not attribute_code:
            continue
        template_hint = common_runtime_template_hint(attribute_code)
        if attribute_code in by_code:
            target = by_code[attribute_code]
            # Common attributes should at least satisfy the baseline search/filter posture.
            target["isRequired"] = bool(target.get("isRequired") or template_hint.get("isRequired"))
            target["isSearch"] = bool(target.get("isSearch") or template_hint.get("isSearch"))
            target["isFilter"] = bool(target.get("isFilter") or template_hint.get("isFilter"))
            target["isDisplay"] = bool(target.get("isDisplay") if "isDisplay" in target else template_hint.get("isDisplay", True))
            target["source"] = "TEMPLATE_OR_COMMON"
            continue

        next_sort = next_sort + 10 if next_sort > 0 else 10
        options = _serialize_common_attribute_options(list(getattr(attribute_row, "options", []) or []))
        injected = {
            "attributeCode": attribute_code,
            "attributeId": getattr(attribute_row, "id", None),
            "attributeName": getattr(attribute_row, "name", attribute_code),
            "dataType": getattr(getattr(attribute_row, "data_type", None), "value", getattr(attribute_row, "data_type", None)),
            "valueScope": getattr(attribute_row, "value_scope", "SPU"),
            "isMulti": bool(getattr(attribute_row, "is_multi", False)),
            "isRequired": bool(template_hint.get("isRequired")),
            "isSale": False,
            "isFilter": bool(template_hint.get("isFilter", True)),
            "isSearch": bool(template_hint.get("isSearch")),
            "isDisplay": bool(template_hint.get("isDisplay", True)),
            "sortNo": next_sort,
            "unit": getattr(attribute_row, "unit", None),
            "options": options,
            "source": "COMMON_RUNTIME",
        }
        source_items.append(injected)
        by_code[attribute_code] = injected
        injected_count += 1

    merged = dict(template_detail)
    merged["items"] = sorted(
        source_items,
        key=lambda row: (
            int(row.get("sortNo") or 0),
            str(row.get("attributeCode") or ""),
        ),
    )
    merged["commonRuntimeAttributeCount"] = injected_count
    return merged


def _load_common_runtime_attribute_rows(session) -> list[AttributeDefinition]:
    rows = list(
        session.execute(
            select(AttributeDefinition).where(
                AttributeDefinition.scope_type == AttributeScopeType.PLATFORM,
                AttributeDefinition.scope_id == "platform",
                AttributeDefinition.status == AttributeStatus.ACTIVE,
            )
        ).scalars().all()
    )
    return [
        row
        for row in rows
        if is_runtime_common_attribute(
            code=str(getattr(row, "code", "") or ""),
            validation_schema=dict(getattr(row, "validation_schema", None) or {}),
        )
    ]


def _serialize_common_attribute_options(options: list[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for option in sorted(
        options,
        key=lambda row: (
            int(getattr(row, "sort_no", 0) or 0),
            str(getattr(row, "option_code", "") or ""),
        ),
    ):
        status = str(getattr(getattr(option, "status", None), "value", getattr(option, "status", "")) or "").upper()
        if status and status != "ACTIVE":
            continue
        option_code = str(getattr(option, "option_code", "") or "").strip()
        option_name = str(getattr(option, "option_name", option_code) or option_code).strip()
        if not option_code:
            continue
        serialized.append(
            {
                "optionId": getattr(option, "id", None),
                "optionCode": option_code,
                "optionName": option_name,
                "sortNo": int(getattr(option, "sort_no", 0) or 0),
                "status": "ACTIVE",
            }
        )
    return serialized


def _template_item_map(template_detail: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["attributeCode"]): dict(item)
        for item in list(template_detail.get("items") or [])
    }


def _catalog_template_metadata(template_detail: dict[str, Any]) -> dict[str, Any]:
    category = dict(template_detail.get("category") or {})
    template = dict(template_detail.get("template") or {})
    return {
        "categoryId": category.get("id"),
        "categoryCode": category.get("code"),
        "categoryName": category.get("name"),
        "templateId": template.get("id"),
        "templateVersion": template.get("version"),
    }


def _catalog_group_for_item(template_item: dict[str, Any]) -> str:
    if bool(template_item.get("isSale")):
        return "saleAttributes"
    if str(template_item.get("valueScope") or "").upper() == "SKU":
        return "skuAttributes"
    return "spuAttributes"


def _extract_catalog_attribute_groups(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    source = payload.get("catalogAttributes")
    if not isinstance(source, dict):
        source = payload
    return {
        group: [dict(row) for row in list(source.get(group) or []) if isinstance(row, dict)]
        for group in CATALOG_ATTRIBUTE_GROUPS
    }


def _legacy_value_for_attribute_code(
    attribute_code: str,
    *,
    item: Item,
    candidate: SpecEnrichmentCandidate,
) -> Any:
    if attribute_code == "product_line":
        return candidate.product_line or item.normalized_model_family
    if attribute_code == "model_name":
        return candidate.model_name or item.normalized_model
    if attribute_code == "generation":
        return candidate.generation
    if attribute_code == "case_size_mm":
        return candidate.case_size_mm
    if attribute_code == "is_solar":
        return candidate.is_solar
    if attribute_code == "display_type":
        return candidate.display_type
    if attribute_code == "screen_size_in":
        return candidate.screen_size_in
    if attribute_code == "chip_family":
        return candidate.chip_family or item.normalized_chip
    if attribute_code == "cpu_model":
        return candidate.cpu_model
    if attribute_code == "cpu_cores":
        return candidate.cpu_cores
    if attribute_code == "gpu_cores":
        return candidate.gpu_cores
    if attribute_code == "memory_gb":
        return candidate.memory_gb if candidate.memory_gb is not None else item.normalized_memory_gb
    if attribute_code == "storage_gb":
        if candidate.storage_gb is not None:
            return candidate.storage_gb
        return normalize_storage_gb(item.normalized_storage_gb)
    if attribute_code == "edition_tags":
        return list(candidate.edition_tags or [])
    return None


def _rows_from_attribute_value(
    *,
    attribute_code: str,
    value: Any,
    template_item: dict[str, Any],
) -> list[dict[str, Any]]:
    data_type = str(template_item.get("dataType") or "").upper()
    is_multi = bool(template_item.get("isMulti", False))
    unit = template_item.get("unit")

    if value is None or value == "":
        return []

    if data_type == "ENUM":
        values = value if isinstance(value, list) and is_multi else [value]
        rows: list[dict[str, Any]] = []
        for entry in values:
            option_code = None
            option_id = None
            if isinstance(entry, dict):
                option_code = entry.get("optionCode")
                option_id = entry.get("optionId")
            else:
                option_code = str(entry).strip()
            if option_code or option_id:
                rows.append(
                    {
                        "attributeCode": attribute_code,
                        "optionCode": option_code,
                        "optionId": option_id,
                    }
                )
        return rows

    if data_type == "TEXT":
        values = value if isinstance(value, list) and is_multi else [value]
        return [
            {"attributeCode": attribute_code, "textValue": str(entry).strip()}
            for entry in values
            if str(entry).strip()
        ]

    if data_type == "NUMBER":
        values = value if isinstance(value, list) and is_multi else [value]
        rows = []
        for entry in values:
            number_value = _to_number_value(entry)
            if number_value is None:
                continue
            rows.append(
                {
                    "attributeCode": attribute_code,
                    "numberValue": number_value,
                    "normalizedNumberValue": number_value,
                    "unit": unit,
                }
            )
        return rows

    if data_type == "BOOLEAN":
        values = value if isinstance(value, list) and is_multi else [value]
        rows = []
        for entry in values:
            bool_value = _to_bool_or_none(entry)
            if bool_value is None:
                continue
            rows.append({"attributeCode": attribute_code, "boolValue": bool_value})
        return rows

    if is_multi and isinstance(value, list):
        return [{"attributeCode": attribute_code, "jsonValue": list(value)}]
    return [{"attributeCode": attribute_code, "jsonValue": value}]


def _to_number_value(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    try:
        decimal_value = Decimal(str(value))
    except Exception:
        return None
    if decimal_value == decimal_value.to_integral_value():
        return int(decimal_value)
    return float(decimal_value)


def _dedupe_catalog_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique_rows: list[dict[str, Any]] = []
    for row in rows:
        signature = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        if signature in seen:
            continue
        seen.add(signature)
        unique_rows.append(dict(row))
    return unique_rows


def _normalize_lens_brand_label(value: Any) -> str | None:
    text = _normalize_optional_text(value)
    if not text:
        return None
    lowered = text.lower()
    for canonical, aliases in LENS_BRAND_LABELS:
        if any(alias in lowered or alias in text for alias in aliases):
            return canonical
    return text


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _contains_compact_token(text: str, token: str) -> bool:
    lowered = text.lower()
    compact = re.sub(r"\s+", "", lowered)
    lowered_token = token.lower()
    compact_token = re.sub(r"\s+", "", lowered_token)
    return lowered_token in lowered or compact_token in compact


def _has_explicit_lens_identity_signal(text: str | None, *, brand: str | None = None) -> bool:
    normalized = _normalize_optional_text(text)
    if not normalized:
        return False
    if any(_contains_compact_token(normalized, token) for token in LENS_EXPLICIT_HINT_TOKENS):
        return True
    focal = _extract_lens_focal_signature(normalized)
    aperture = _extract_lens_aperture_signature(normalized)
    badges = _extract_lens_badges(normalized)
    return bool(focal and (aperture or badges))


def lens_title_is_non_target_body_listing(title: str | None) -> bool:
    normalized = _normalize_optional_text(title)
    if not normalized:
        return False
    brand = _normalize_lens_brand_label(normalized)
    lens_signal = _has_explicit_lens_identity_signal(normalized, brand=brand)
    if any(_contains_compact_token(normalized, token) for token in LENS_BODY_BUNDLE_TOKENS):
        return True
    strong_body_signal = any(_contains_compact_token(normalized, token) for token in LENS_BODY_STRONG_TOKENS)
    if strong_body_signal and not lens_signal:
        return True
    if not lens_signal and any(pattern.search(normalized) for pattern in LENS_BODY_MODEL_PATTERNS):
        return True
    return False


_LENS_FOCAL_RANGE_RE = re.compile(r"(?<!\d)(\d{2,3})\s*[-~至到/]\s*(\d{2,3})(?:\s*mm)?(?!\d)", re.IGNORECASE)
_LENS_FOCAL_SINGLE_RE = re.compile(r"(?<!\d)(\d{2,3})(?:\s*mm)?(?!\d)", re.IGNORECASE)
_LENS_APERTURE_RE = re.compile(r"f\s*/?\s*([0-9](?:\.[0-9])?)", re.IGNORECASE)
_LENS_BADGE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("s", (" s", "s ", "镜皇s", " s-line", " sline")),
    ("vr", ("vr",)),
    ("gm", ("g master", "gm")),
    ("dn", ("dn",)),
    ("dg", ("dg",)),
    ("art", ("art",)),
    ("macro", ("macro", "微距")),
)
_LENS_MOUNT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nikon_z", ("尼康z", "nikkorz", "z卡口", " z mount", "zmount")),
    ("canon_rf", ("佳能rf", "canonrf", "rf卡口", "rfmount")),
    ("sony_e", ("索尼fe", "索尼e", "sonyfe", "sonye", "e卡口", "emount")),
)


def _extract_lens_focal_signature(value: Any) -> str | None:
    text = _normalize_optional_text(value)
    if not text:
        return None
    lowered = text.lower()
    range_match = _LENS_FOCAL_RANGE_RE.search(lowered)
    if range_match:
        start = str(int(range_match.group(1)))
        end = str(int(range_match.group(2)))
        return f"{start}-{end}"
    single_match = _LENS_FOCAL_SINGLE_RE.search(lowered)
    if single_match:
        return str(int(single_match.group(1)))
    return None


def _extract_lens_aperture_signature(value: Any) -> str | None:
    text = _normalize_optional_text(value)
    if not text:
        return None
    lowered = text.lower()
    match = _LENS_APERTURE_RE.search(lowered)
    if match:
        return str(Decimal(match.group(1)).normalize())
    range_match = _LENS_FOCAL_RANGE_RE.search(lowered)
    single_match = _LENS_FOCAL_SINGLE_RE.search(lowered)
    search_start = 0
    if range_match:
        search_start = range_match.end()
    elif single_match:
        search_start = single_match.end()
    trailing_text = lowered[search_start:]
    fallback_match = re.search(
        r"(?<!\d)([0-9](?:\.[0-9])?)\s*(?:s|gm|dn|dg|macro)?(?!\d)",
        trailing_text,
    )
    if fallback_match and _extract_lens_focal_signature(text):
        return str(Decimal(fallback_match.group(1)).normalize())
    return None


def _extract_lens_badges(value: Any) -> set[str]:
    text = _normalize_optional_text(value)
    if not text:
        return set()
    lowered = f" {text.lower()} "
    badges: set[str] = set()
    for canonical, tokens in _LENS_BADGE_PATTERNS:
        if any(token in lowered for token in tokens):
            badges.add(canonical)
    return badges


def _extract_lens_mount_signature(value: Any, *, brand: str | None = None) -> str | None:
    text = _normalize_optional_text(value)
    if not text:
        return None
    compact = normalize_model_alias(text)
    lowered = f" {text.lower()} "
    for canonical, tokens in _LENS_MOUNT_PATTERNS:
        if any(token in compact or token in lowered for token in tokens):
            return canonical
    normalized_brand = _normalize_lens_brand_label(brand or text)
    if normalized_brand == "尼康" and ("尼康z" in compact or "nikkorz" in compact):
        return "nikon_z"
    if normalized_brand == "佳能" and "rf" in compact:
        return "canon_rf"
    if normalized_brand == "索尼" and any(token in compact for token in ("索尼e", "索尼fe", "sonye", "sonyfe", "fe")):
        return "sony_e"
    return None


def _build_lens_match_signature(value: Any, *, brand: str | None = None) -> dict[str, Any]:
    text = _normalize_optional_text(value)
    if not text:
        return {}
    normalized_brand = _normalize_lens_brand_label(brand or text)
    return {
        "brand": normalized_brand,
        "focal": _extract_lens_focal_signature(text),
        "aperture": _extract_lens_aperture_signature(text),
        "mount": _extract_lens_mount_signature(text, brand=normalized_brand),
        "badges": _extract_lens_badges(text),
        "normalized": normalize_model_alias(text),
    }


def _format_lens_focal_range(value: Any) -> str | None:
    signature = _normalize_optional_text(_extract_lens_focal_signature(value))
    if not signature:
        return None
    return f"{signature}mm"


def _format_lens_aperture(value: Any) -> str | None:
    signature = _normalize_optional_text(_extract_lens_aperture_signature(value))
    if not signature:
        return None
    return f"f/{signature}"


def _preferred_lens_mount_label(*, candidate: SpecEnrichmentCandidate, matched_model_catalog: dict[str, Any] | None) -> str | None:
    mount_signature = _extract_lens_mount_signature(
        (matched_model_catalog or {}).get("modelName")
        or (matched_model_catalog or {}).get("seriesName")
        or candidate.model_name
        or candidate.product_line,
        brand=candidate.brand or (matched_model_catalog or {}).get("brandName"),
    )
    return {
        "nikon_z": "尼康Z卡口",
        "canon_rf": "佳能RF卡口",
        "sony_e": "索尼E卡口",
    }.get(mount_signature)


def _canonical_lens_series_label(*, brand: str | None, mount_signature: str | None) -> str | None:
    normalized_brand = _normalize_lens_brand_label(brand)
    if normalized_brand == "尼康" and mount_signature == "nikon_z":
        return "NIKKOR Z"
    if normalized_brand == "佳能" and mount_signature == "canon_rf":
        return "RF"
    if normalized_brand == "索尼" and mount_signature == "sony_e":
        return "FE"
    return None


def _build_partial_lens_model_name(value: Any, *, brand: str | None = None) -> str | None:
    text = _normalize_optional_text(value)
    if not text:
        return None
    normalized_brand = _normalize_lens_brand_label(brand or text)
    focal = _extract_lens_focal_signature(text)
    if not focal:
        return None
    aperture = _extract_lens_aperture_signature(text)
    badges = _extract_lens_badges(text)
    mount_signature = _extract_lens_mount_signature(text, brand=normalized_brand)

    prefix: str | None = None
    if normalized_brand == "尼康" and mount_signature == "nikon_z":
        prefix = "NIKKOR Z MC" if "macro" in badges else "NIKKOR Z"
    elif normalized_brand == "佳能" and mount_signature == "canon_rf":
        prefix = "RF"
    elif normalized_brand == "索尼" and mount_signature == "sony_e":
        prefix = "FE"
    if not prefix:
        return None

    parts = [prefix, f"{focal}mm"]
    if aperture:
        parts.append(f"f/{aperture}")
    if "vr" in badges:
        parts.append("VR")
    if "gm" in badges:
        parts.append("GM")
    if "art" in badges:
        parts.append("Art")
    if "dn" in badges:
        parts.append("DN")
    if "dg" in badges:
        parts.append("DG")
    if "macro" in badges and prefix != "NIKKOR Z MC":
        parts.append("Macro")
    if "s" in badges:
        parts.append("S")
    return " ".join(parts)


def _score_lens_signature_match(candidate_signature: dict[str, Any], known_signature: dict[str, Any]) -> int:
    candidate_focal = _normalize_optional_text(candidate_signature.get("focal"))
    known_focal = _normalize_optional_text(known_signature.get("focal"))
    candidate_aperture = _normalize_optional_text(candidate_signature.get("aperture"))
    known_aperture = _normalize_optional_text(known_signature.get("aperture"))
    if not candidate_focal or not known_focal or candidate_focal != known_focal:
        return -1
    if not candidate_aperture or not known_aperture or candidate_aperture != known_aperture:
        return -1

    score = 7
    candidate_brand = _normalize_optional_text(candidate_signature.get("brand"))
    known_brand = _normalize_optional_text(known_signature.get("brand"))
    if candidate_brand and known_brand:
        if candidate_brand != known_brand:
            return -1
        score += 2

    candidate_mount = _normalize_optional_text(candidate_signature.get("mount"))
    known_mount = _normalize_optional_text(known_signature.get("mount"))
    if candidate_mount and known_mount:
        if candidate_mount != known_mount:
            return -1
        score += 2
    elif candidate_mount == known_mount and candidate_mount:
        score += 1

    shared_badges = set(candidate_signature.get("badges") or set()) & set(known_signature.get("badges") or set())
    if shared_badges:
        score += 1
    return score


def build_extraction_text(item: Item, *, include_source_keyword: bool = False) -> str:
    parts = [item.title or ""]
    if include_source_keyword and item.source_keyword:
        parts.append(item.source_keyword)
    if item.condition_tags:
        parts.extend(item.condition_tags)
    return " | ".join(part for part in parts if part)


def compact_watch_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def pick_unique_marq_variant(title: str, lowered: str) -> str | None:
    compact_title = compact_watch_text(title)
    compact_lowered = compact_watch_text(lowered)
    matches: list[str] = []
    for label, tokens in MARQ_VARIANT_ALIASES:
        if any(compact_watch_text(token) in compact_title or compact_watch_text(token) in compact_lowered for token in tokens):
            matches.append(label)
    unique_matches = list(dict.fromkeys(matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    return None


def pick_garmin_product_line_v2(lowered: str) -> str | None:
    compact_lowered = compact_watch_text(lowered)
    if "marq" in compact_lowered:
        return "MARQ"
    for product_line, tokens in GARMIN_PRODUCT_LINES:
        if any(compact_watch_text(token) in compact_lowered for token in tokens):
            return product_line
    return None


def pick_garmin_model_name_v2(title: str, lowered: str, product_line: str | None) -> str | None:
    if product_line == "Forerunner":
        match = FORERUNNER_MODEL_RE.search(lowered)
        if match:
            return f"Forerunner {match.group(1).upper()}"
        return "Forerunner"
    if product_line == "MARQ":
        variant = pick_unique_marq_variant(title, lowered)
        if variant:
            return f"MARQ {variant}"
        return "MARQ"
    return pick_garmin_model_name(title, lowered, product_line)


def extract_garmin_rule(item: Item, lowered: str) -> SpecEnrichmentCandidate:
    product_line = pick_garmin_product_line_v2(lowered)
    model_name = pick_garmin_model_name_v2(item.title, lowered, product_line)
    generation = pick_garmin_generation(lowered, product_line)
    case_size_mm = pick_case_size_mm(lowered)
    edition_tags = pick_garmin_edition_tags(lowered)
    is_solar = True if "Solar" in edition_tags else None
    display_type = pick_garmin_display_type(lowered, edition_tags)
    case_size_mm, display_type = _apply_garmin_model_defaults(
        model_name=model_name,
        case_size_mm=case_size_mm,
        display_type=display_type,
    )

    confidence = Decimal("0.35")
    status = "partial"
    if product_line:
        confidence += Decimal("0.20")
    if model_name:
        confidence += Decimal("0.20")
    if case_size_mm is not None:
        confidence += Decimal("0.08")
    if display_type:
        confidence += Decimal("0.08")
    if is_solar is not None:
        confidence += Decimal("0.05")
    if generation:
        confidence += Decimal("0.04")

    if model_name and (case_size_mm is not None or display_type or is_solar is not None):
        status = "complete"
    elif model_name or product_line:
        status = "partial"
    else:
        status = "unresolved"
        confidence = Decimal("0.20")

    confidence = min(confidence, Decimal("0.95"))
    return SpecEnrichmentCandidate(
        extractor_type="rule",
        status=status,
        confidence=confidence,
        needs_review=confidence < Decimal("0.75"),
        brand="Garmin",
        product_line=product_line,
        model_family=product_line,
        model_name=model_name or item.normalized_model,
        generation=generation,
        case_size_mm=case_size_mm,
        is_solar=is_solar,
        display_type=display_type,
        edition_tags=edition_tags,
        evidence={
            "source": "title_and_tags",
            "title": item.title,
            "condition_tags": item.condition_tags or [],
        },
        extraction_payload={"rule_text": build_extraction_text(item, include_source_keyword=False)},
    )


def extract_apple_rule(item: Item, lowered: str) -> SpecEnrichmentCandidate:
    product_line = pick_apple_product_line(lowered)
    chip_family = pick_apple_chip(lowered) or item.normalized_chip
    screen_size = (
        pick_screen_size(lowered)
        if product_line in {"MacBook Air", "MacBook Pro", "iMac"}
        else None
    )
    memory_gb = pick_memory_gb(lowered) or item.normalized_memory_gb
    storage_gb = normalize_storage_gb(pick_storage_gb(lowered) or item.normalized_storage_gb)
    cpu_cores = pick_core_count(lowered, "cpu")
    gpu_cores = pick_core_count(lowered, "gpu")
    model_name = build_apple_model_name(
        product_line=product_line,
        screen_size=screen_size,
        chip_family=chip_family,
        memory_gb=memory_gb,
        storage_gb=storage_gb,
    )

    confidence = Decimal("0.35")
    status = "partial"
    if product_line:
        confidence += Decimal("0.18")
    if chip_family:
        confidence += Decimal("0.18")
    if memory_gb is not None:
        confidence += Decimal("0.08")
    if storage_gb is not None:
        confidence += Decimal("0.08")
    if screen_size is not None:
        confidence += Decimal("0.06")
    if cpu_cores is not None:
        confidence += Decimal("0.05")
    if gpu_cores is not None:
        confidence += Decimal("0.05")

    if product_line and chip_family and (memory_gb is not None or storage_gb is not None):
        status = "complete"
    elif product_line or chip_family:
        status = "partial"
    else:
        status = "unresolved"
        confidence = Decimal("0.20")

    confidence = min(confidence, Decimal("0.96"))
    return SpecEnrichmentCandidate(
        extractor_type="rule",
        status=status,
        confidence=confidence,
        needs_review=confidence < Decimal("0.75"),
        brand="Apple",
        product_line=product_line,
        model_family=product_line,
        model_name=model_name or item.normalized_model,
        screen_size_in=screen_size,
        chip_family=chip_family,
        cpu_model=chip_family,
        cpu_cores=cpu_cores,
        gpu_cores=gpu_cores,
        memory_gb=memory_gb,
        storage_gb=storage_gb,
        evidence={
            "source": "title_and_tags",
            "title": item.title,
            "condition_tags": item.condition_tags or [],
        },
        extraction_payload={"rule_text": build_extraction_text(item, include_source_keyword=False)},
    )


def extract_lens_rule(item: Item, lowered: str) -> SpecEnrichmentCandidate:
    text = build_extraction_text(item, include_source_keyword=False)
    if lens_title_is_non_target_body_listing(item.title):
        return SpecEnrichmentCandidate(
            extractor_type="rule",
            status="unresolved",
            confidence=Decimal("0.20"),
            needs_review=False,
            evidence={
                "reason": "non_target_camera_body",
                "title": item.title,
                "condition_tags": item.condition_tags or [],
            },
            extraction_payload={"rule_text": text},
        )

    brand = _normalize_lens_brand_label(item.normalized_brand or text)
    mount_signature = _extract_lens_mount_signature(text, brand=brand)
    product_line = _canonical_lens_series_label(brand=brand, mount_signature=mount_signature)
    canonical_model_name = (
        _build_partial_lens_model_name(item.normalized_model, brand=brand)
        or _build_partial_lens_model_name(item.title, brand=brand)
    )
    focal_range = _format_lens_focal_range(canonical_model_name or text)
    max_aperture = _format_lens_aperture(canonical_model_name or text)
    lens_signal = _has_explicit_lens_identity_signal(text, brand=brand)

    confidence = Decimal("0.20")
    if brand:
        confidence += Decimal("0.08")
    if mount_signature:
        confidence += Decimal("0.10")
    if focal_range:
        confidence += Decimal("0.14")
    if max_aperture:
        confidence += Decimal("0.14")
    if product_line:
        confidence += Decimal("0.10")
    if canonical_model_name:
        confidence += Decimal("0.18")
    if lens_signal:
        confidence += Decimal("0.08")

    if canonical_model_name and focal_range and max_aperture and product_line:
        status = "complete"
        confidence = max(confidence, Decimal("0.82"))
    elif canonical_model_name or focal_range or lens_signal:
        status = "partial"
        confidence = min(confidence, Decimal("0.78"))
    else:
        status = "unresolved"
        confidence = Decimal("0.20")

    return SpecEnrichmentCandidate(
        extractor_type="rule",
        status=status,
        confidence=min(confidence, Decimal("0.95")),
        needs_review=confidence < Decimal("0.75"),
        brand=brand,
        product_line=product_line,
        model_family=product_line,
        model_name=canonical_model_name,
        evidence={
            "source": "title_and_tags",
            "title": item.title,
            "condition_tags": item.condition_tags or [],
        },
        extraction_payload={"rule_text": text},
    )


def pick_garmin_product_line(lowered: str) -> str | None:
    for product_line, tokens in GARMIN_PRODUCT_LINES:
        if any(token in lowered for token in tokens):
            return product_line
    return None


def pick_garmin_model_name(title: str, lowered: str, product_line: str | None) -> str | None:
    if product_line == "Fenix":
        match = re.search(r"fenix\s*(\d{1,2})(x|s)?(?:\s*(pro|plus))?", lowered, re.IGNORECASE)
        if match:
            suffix = match.group(2).upper() if match.group(2) else ""
            extra = match.group(3).title() if match.group(3) else ""
            parts = [f"Fenix {match.group(1)}{suffix}".strip()]
            if extra:
                parts.append(extra)
            return " ".join(parts)
    if product_line == "Epix":
        match = re.search(r"epix(?:\s*(pro))?(?:\s*(gen\s*2|2))?", lowered, re.IGNORECASE)
        if match:
            parts = ["Epix"]
            if match.group(1):
                parts.append("Pro")
            if match.group(2):
                parts.append("Gen 2")
            return " ".join(parts)
        return "Epix"
    if product_line == "Instinct":
        match = re.search(r"instinct\s*(2x?|crossover|e)?", lowered, re.IGNORECASE)
        if match and match.group(1):
            return f"Instinct {match.group(1).upper()}"
        if re.search(r"\b2x\b", lowered, re.IGNORECASE):
            return "Instinct 2X"
        if re.search(r"\b2s\b", lowered, re.IGNORECASE):
            return "Instinct 2S"
        if re.search(r"\b2\b", lowered, re.IGNORECASE):
            return "Instinct 2"
        return "Instinct"
    if product_line == "Forerunner":
        match = re.search(r"(?:forerunner\s*)?(965|955|945|265s?|255s?|245m?|165|55)\b", lowered, re.IGNORECASE)
        if match:
            return f"Forerunner {match.group(1).upper()}"
        return "Forerunner"
    if product_line == "Venu":
        match = re.search(r"venu\s*(\d+|sq|x1)?", lowered, re.IGNORECASE)
        if match and match.group(1):
            return f"Venu {match.group(1).upper()}"
        return "Venu"
    if product_line == "MARQ":
        match = re.search(r"marq\s*(golfer|athlete|aviator|captain|driver|adventurer|commander)", lowered, re.IGNORECASE)
        if match:
            return f"MARQ {match.group(1).title()}"
        return "MARQ"
    if product_line == "Approach":
        match = re.search(r"approach\s*([sgx]?\d{2,3})", lowered, re.IGNORECASE)
        if match:
            return f"Approach {match.group(1).upper()}"
        return "Approach"
    if product_line == "Tactix":
        match = re.search(r"tactix\s*(\d+)?", lowered, re.IGNORECASE)
        if match and match.group(1):
            return f"Tactix {match.group(1)}"
        return "Tactix"
    if product_line == "Enduro":
        match = re.search(r"enduro\s*(\d+)?", lowered, re.IGNORECASE)
        if match and match.group(1):
            return f"Enduro {match.group(1)}"
        return "Enduro"
    if product_line == "Descent":
        match = re.search(r"\bmk\s*([123])\b", lowered, re.IGNORECASE)
        if match:
            return f"Descent MK{match.group(1)}"
        if "descent" in lowered:
            return "Descent"
    return title[:128] if product_line else None


def pick_garmin_generation(lowered: str, product_line: str | None) -> str | None:
    if product_line == "Fenix":
        match = re.search(r"fenix\s*(\d{1,2})", lowered, re.IGNORECASE)
        if match:
            return match.group(1)
    if product_line == "Epix":
        if "gen 2" in lowered or re.search(r"epix\s*2\b", lowered):
            return "Gen 2"
    if product_line == "Instinct":
        match = re.search(r"instinct\s*(2x?|e)", lowered, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    if product_line in {"Forerunner", "Venu", "Enduro", "Tactix"}:
        match = re.search(rf"{product_line.lower()}\s*(\d+)", lowered, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def pick_case_size_mm(lowered: str) -> int | None:
    match = re.search(r"(?<!\d)(40|41|42|43|45|46|47|49|50|51)\s*(?:mm|毫米)(?=\D|$)", lowered, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def pick_garmin_display_type(lowered: str, edition_tags: list[str]) -> str | None:
    if any(token in lowered for token in ("amoled", "amloed", "amoeld")) or "AMOLED" in edition_tags:
        return "AMOLED"
    if "mip" in lowered or "反射屏" in lowered:
        return "MIP"
    return None


def pick_garmin_edition_tags(lowered: str) -> list[str]:
    values: list[str] = []
    for label, tokens in GARMIN_EDITION_PATTERNS:
        if any(token in lowered for token in tokens):
            values.append(label)
    return values


def _apply_garmin_model_defaults(
    *,
    model_name: str | None,
    case_size_mm: int | None,
    display_type: str | None,
) -> tuple[int | None, str | None]:
    defaults = GARMIN_MODEL_DEFAULTS.get(str(model_name or "").strip())
    if defaults is None:
        return case_size_mm, display_type
    resolved_case_size = case_size_mm if case_size_mm is not None else defaults.get("case_size_mm")
    resolved_display_type = display_type or defaults.get("display_type")
    return resolved_case_size, resolved_display_type


def pick_apple_product_line(lowered: str) -> str | None:
    if "macbook air" in lowered:
        return "MacBook Air"
    if "macbook pro" in lowered:
        return "MacBook Pro"
    if "mac mini" in lowered:
        return "Mac mini"
    if "mac studio" in lowered:
        return "Mac Studio"
    if "imac" in lowered:
        return "iMac"
    return None


def pick_apple_chip(lowered: str) -> str | None:
    normalized = lowered.replace(" ", "")
    for token in APPLE_CHIP_PATTERNS:
        compact = token.replace(" ", "")
        if token in lowered or compact in normalized:
            return token.upper().replace("MAX", "Max").replace("PRO", "Pro").replace("ULTRA", "Ultra")
    return None


def pick_screen_size(lowered: str) -> Decimal | None:
    match = re.search(r"\b(13(?:\.\d)?|14(?:\.\d)?|15(?:\.\d)?|16|24)\s*(?:寸|英寸|inch|in)?\b", lowered)
    if not match:
        return None
    return Decimal(match.group(1))


def _spaced_numeric_pattern(values: tuple[int, ...]) -> str:
    return "|".join(r"\s*".join(str(value)) for value in values)


def _parse_spaced_numeric(value: str) -> int:
    return int(re.sub(r"\s+", "", value))


def _normalize_apple_spec_text(lowered: str) -> str:
    normalized = lowered.translate(APPLE_SPEC_TRANSLATION)
    normalized = re.sub(r"(?<=\d)\s+(?=(?:g|gb|t|tb)\b)", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"(?<!\d)(1\s*0\s*2\s*4|1\s*0\s*0\s*0|5\s*1\s*2|5\s*0\s*0|2\s*5\s*6|2\s*5\s*0|1\s*2\s*8)(?=\s*(?:g|gb|硬盘|固态硬盘|固态|闪存|存储|ssd))",
        lambda match: re.sub(r"\s+", "", match.group(1)),
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s*(\+|/|-)\s*", r"\1", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _extract_apple_memory_storage_pair(lowered: str) -> tuple[int | None, int | None]:
    normalized = _normalize_apple_spec_text(lowered)
    memory_pattern = _spaced_numeric_pattern(APPLE_MEMORY_OPTIONS)
    storage_gb_pattern = _spaced_numeric_pattern(APPLE_STORAGE_GB_OPTIONS)
    storage_tb_pattern = _spaced_numeric_pattern(APPLE_STORAGE_TB_OPTIONS)
    pair_patterns = (
        rf"(?<!\d)({memory_pattern})\s*g(?:b)?(?:\+|/|-)\s*({storage_gb_pattern})\s*g?(?:b)?(?=\D|$)",
        rf"(?<!\d)({memory_pattern})\s*g(?:b)?(?:\+|/|-)\s*({storage_tb_pattern})\s*t(?:b)?(?=\D|$)",
        rf"(?<!\d)({memory_pattern})(?:\+|/|-)\s*({storage_gb_pattern})\s*g?(?:b)?(?=\D|$)",
        rf"(?<!\d)({memory_pattern})(?:\+|/|-)\s*({storage_tb_pattern})\s*t(?:b)?(?=\D|$)",
        rf"(?<!\d)({memory_pattern})\s*g(?:b)?\s+({storage_gb_pattern})\s*g(?:b)?(?=\D|$)",
        rf"(?<!\d)({memory_pattern})\s*g(?:b)?\s+({storage_tb_pattern})\s*t(?:b)?(?=\D|$)",
    )
    for pattern in pair_patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if not match:
            continue
        memory_gb = _parse_spaced_numeric(match.group(1))
        storage_value = _parse_spaced_numeric(match.group(2))
        if "t" in match.group(0).lower():
            return memory_gb, normalize_storage_gb(storage_value * 1024)
        return memory_gb, normalize_storage_gb(storage_value)
    return None, None


def pick_memory_gb(lowered: str) -> int | None:
    pair_memory, _ = _extract_apple_memory_storage_pair(lowered)
    if pair_memory is not None:
        return pair_memory

    normalized = _normalize_apple_spec_text(lowered)
    memory_pattern = _spaced_numeric_pattern(APPLE_MEMORY_OPTIONS)
    explicit_patterns = (
        rf"({memory_pattern})\s*g(?:b)?\s*(?:大)?{APPLE_MEMORY_HINT_PATTERN}",
        rf"{APPLE_MEMORY_HINT_PATTERN}\s*[:：]?\s*({memory_pattern})\s*g(?:b)?",
    )
    for pattern in explicit_patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return _parse_spaced_numeric(match.group(1))

    return None


def pick_storage_gb(lowered: str) -> int | None:
    _, pair_storage = _extract_apple_memory_storage_pair(lowered)
    if pair_storage is not None:
        return pair_storage

    normalized = _normalize_apple_spec_text(lowered)
    storage_gb_pattern = _spaced_numeric_pattern(APPLE_STORAGE_GB_OPTIONS)
    storage_tb_pattern = _spaced_numeric_pattern(APPLE_STORAGE_TB_OPTIONS)
    explicit_patterns = (
        rf"({storage_gb_pattern})\s*g?(?:b)?\s*{APPLE_STORAGE_HINT_PATTERN}(?=\D|$)",
        rf"{APPLE_STORAGE_HINT_PATTERN}\s*[:：]?\s*({storage_gb_pattern})\s*g?(?:b)?(?=\D|$)",
    )
    for pattern in explicit_patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return normalize_storage_gb(_parse_spaced_numeric(match.group(1)))

    tb_patterns = (
        rf"({storage_tb_pattern})\s*t(?:b)?\s*{APPLE_STORAGE_HINT_PATTERN}?(?=\D|$)",
        rf"{APPLE_STORAGE_HINT_PATTERN}\s*[:：]?\s*({storage_tb_pattern})\s*t(?:b)?(?=\D|$)",
    )
    for pattern in tb_patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return normalize_storage_gb(_parse_spaced_numeric(match.group(1)) * 1024)

    tb_match = re.search(r"(1|2|4|8|16)\s*t(?:b)?(?=\D|$)", normalized, re.IGNORECASE)
    if tb_match:
        return normalize_storage_gb(int(tb_match.group(1)) * 1024)
    return None


def pick_core_count(lowered: str, component: str) -> int | None:
    patterns = (
        rf"(\d{{1,2}})\s*核\s*{component}",
        rf"{component}\s*(\d{{1,2}})\s*核",
        rf"(\d{{1,2}})\s*c\s*{component}",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def build_apple_model_name(
    *,
    product_line: str | None,
    screen_size: Decimal | None,
    chip_family: str | None,
    memory_gb: int | None,
    storage_gb: int | None,
) -> str | None:
    if not product_line:
        return None
    parts = [product_line]
    if screen_size is not None:
        parts.append(f"{screen_size.normalize()}in")
    if chip_family:
        parts.append(chip_family)
    if memory_gb is not None:
        parts.append(f"{memory_gb}G")
    if storage_gb is not None:
        parts.append(f"{storage_gb}G")
    return " ".join(parts)


def is_confident(candidate: SpecEnrichmentCandidate) -> bool:
    return candidate.status == "complete" and (candidate.confidence or Decimal("0")) >= Decimal("0.75")


def should_use_llm(*, item: Item, candidate: SpecEnrichmentCandidate) -> bool:
    if not llm_is_configured():
        return False

    text = build_extraction_text(item, include_source_keyword=False).lower()
    if is_apple_computer_scope(item.business_domain):
        if candidate.cpu_cores is None or candidate.gpu_cores is None:
            return True
        if candidate.chip_family in {"M1", "M2", "M3", "M4"} and (
            any(token in text for token in ("pro", "max", "ultra")) or re.search(r"\d+\s*\+\s*\d+\s*核", text)
        ):
            return True
        return not is_confident(candidate)

    if is_garmin_watch_scope(item.business_domain):
        if candidate.product_line and candidate.case_size_mm is None and re.search(r"\d{2}\s*(?:mm|毫米)\b", text):
            return True
        if candidate.product_line and candidate.display_type is None and "amoled" in text:
            return True
        return not is_confident(candidate)

    if resolve_category_code(item.business_domain) == "camera_interchangeable_lens":
        if str((candidate.evidence or {}).get("reason") or "") == "non_target_camera_body":
            return False
        return not is_confident(candidate)

    return not is_confident(candidate)


def llm_is_configured() -> bool:
    settings = get_settings()
    if not settings.ai_base_url or not settings.ai_model:
        return False
    if is_anthropic_compatible_provider(settings.ai_provider):
        return True
    return bool(settings.ai_api_key)


def extract_llm_specs(
    *,
    item: Item,
    rule_candidate: SpecEnrichmentCandidate,
    runtime_context: dict[str, Any] | None = None,
) -> SpecEnrichmentCandidate | None:
    settings = get_settings()
    if not llm_is_configured():
        return None

    resolved_runtime_context = runtime_context or load_runtime_context_for_item(item)
    template_detail = resolved_runtime_context.get("templateDetail")
    prompt_profile = resolved_runtime_context.get("promptProfile")
    model_catalog = resolved_runtime_context.get("modelCatalog")
    response_payload = call_openai_compatible_chat(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout_sec=settings.ai_timeout_sec,
        enable_thinking=settings.ai_enable_thinking,
        messages=[
            {
                "role": "system",
                "content": build_system_prompt(
                    template_detail=template_detail,
                    prompt_profile=prompt_profile,
                ),
            },
            {
                "role": "user",
                "content": build_user_prompt(
                    item=item,
                    rule_candidate=rule_candidate,
                    template_detail=template_detail,
                    runtime_context=resolved_runtime_context,
                    model_catalog=model_catalog,
                ),
            },
        ],
    )
    content = extract_message_content(response_payload)
    parsed = extract_json_object(content)
    candidate = candidate_from_llm_payload(
        parsed,
        item=item,
        provider=settings.ai_provider,
        model=settings.ai_model,
        template_detail=template_detail,
    )
    candidate = enrich_candidate_with_catalog_attributes(
        item,
        candidate,
        template_detail=template_detail,
    )
    return apply_runtime_context_to_candidate(
        item=item,
        candidate=candidate,
        runtime_context=resolved_runtime_context,
    )


def build_system_prompt(
    *,
    template_detail: dict[str, Any] | None = None,
    prompt_profile: str | None = None,
) -> str:
    profile_instruction = _prompt_profile_instruction(prompt_profile)
    parts = [
        "You extract structured specs from second-hand Goofish listings. "
        "Return only valid JSON. "
        "Do not invent fields. If uncertain, use null. "
        "Use this JSON shape: "
        "{status, confidence, needs_review, spuAttributes, skuAttributes, saleAttributes}. "
        "status must be one of complete, partial, or unresolved. "
        "Do not use valid, success, resolved, invalid, or other status words. "
        "Only return these keys and supported legacy summary fields such as brand, product_line, model_name, chip_family, memory_gb, and storage_gb when needed. "
        "Do not echo the title, catalog template, model catalog, prompt instructions, URLs, or other input fields. "
        "Prefer explicit listing text over query hints or world knowledge. "
        "Each attribute row must use one attributeCode from the provided template. "
        "Use textValue for TEXT, numberValue for NUMBER, boolValue for BOOLEAN, "
        "optionCode for ENUM, jsonValue for JSON. "
        "Put SPU values in spuAttributes, SKU values in skuAttributes, and sale ENUM selections in saleAttributes. "
        "For multi-value attributes, you may emit multiple rows with the same attributeCode. "
        "Prefer optionCode over optionName for ENUM fields and only use an option that exists in the template. "
        "Only fill CPU/GPU core counts when they are explicit or uniquely implied by a precise SKU. "
        "If a value is inferred from product catalog knowledge, keep confidence lower and set needs_review=true. "
        "Do not emit empty placeholder rows; omit attributes you cannot support. "
        "You may additionally include legacy summary fields like product_line or model_name, but catalog attribute arrays are the source of truth.",
    ]
    if prompt_profile:
        parts.append(f"Extraction profile: {prompt_profile}.")
    if profile_instruction:
        parts.append(profile_instruction)
    return " ".join(part for part in parts if part)


def build_user_prompt(
    *,
    item: Item,
    rule_candidate: SpecEnrichmentCandidate,
    template_detail: dict[str, Any] | None = None,
    runtime_context: dict[str, Any] | None = None,
    model_catalog: list[dict[str, Any]] | None = None,
) -> str:
    catalog_attributes = _extract_catalog_attribute_groups(rule_candidate.extraction_payload)
    resolved_runtime_context = runtime_context or {}
    resolved_model_catalog = list(model_catalog or resolved_runtime_context.get("modelCatalog") or [])
    prompt_payload = _compact_prompt_payload(
        {
        "business_domain": item.business_domain,
        "item_id": item.item_id,
        "title": item.title,
        "condition_tags": item.condition_tags or [],
        "catalog_template": _serialize_prompt_catalog_template(template_detail),
        "model_catalog": _serialize_prompt_model_catalog(resolved_model_catalog),
        "rule_candidate": _serialize_prompt_rule_candidate(
            rule_candidate=rule_candidate,
            catalog_attributes=catalog_attributes,
        ),
        }
    )
    return json.dumps(prompt_payload, ensure_ascii=False, indent=2)


def _serialize_prompt_catalog_template(template_detail: dict[str, Any] | None) -> dict[str, Any] | None:
    if template_detail is None:
        return None
    return _compact_prompt_payload(
        {
            "attributes": [
                _compact_prompt_payload(
                    {
                        "attributeCode": row["attributeCode"],
                        "attributeName": row["attributeName"],
                        "dataType": row["dataType"],
                        "valueScope": row["valueScope"],
                        "isMulti": row["isMulti"],
                        "isRequired": row["isRequired"],
                        "isSale": row["isSale"],
                        "unit": row.get("unit"),
                        "options": [
                            _compact_prompt_payload(
                                {
                                    "optionCode": option["optionCode"],
                                    "optionName": option["optionName"],
                                }
                            )
                            for option in list(row.get("options") or [])
                        ],
                    }
                )
                for row in list(template_detail.get("items") or [])
            ],
        }
    )


def _serialize_prompt_model_catalog(model_catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized = []
    for row in model_catalog:
        serialized.append(
            _compact_prompt_payload(
                {
                    "brandName": row.get("brandName"),
                    "seriesName": row.get("seriesName"),
                    "modelCode": row.get("modelCode"),
                    "modelName": row.get("modelName"),
                    "aliases": [
                        _compact_prompt_payload({"aliasText": alias.get("aliasText")})
                        for alias in list(row.get("aliases") or [])
                    ],
                }
            )
        )
    return [row for row in serialized if row]


def _serialize_prompt_rule_candidate(
    *,
    rule_candidate: SpecEnrichmentCandidate,
    catalog_attributes: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    return _compact_prompt_payload(
        {
            "brand": rule_candidate.brand,
            "product_line": rule_candidate.product_line,
            "model_family": rule_candidate.model_family,
            "model_name": rule_candidate.model_name,
            "generation": rule_candidate.generation,
            "case_size_mm": rule_candidate.case_size_mm,
            "is_solar": rule_candidate.is_solar,
            "display_type": rule_candidate.display_type,
            "screen_size_in": float(rule_candidate.screen_size_in)
            if rule_candidate.screen_size_in is not None
            else None,
            "chip_family": rule_candidate.chip_family,
            "cpu_model": rule_candidate.cpu_model,
            "cpu_cores": rule_candidate.cpu_cores,
            "gpu_cores": rule_candidate.gpu_cores,
            "memory_gb": rule_candidate.memory_gb,
            "storage_gb": rule_candidate.storage_gb,
            "edition_tags": rule_candidate.edition_tags,
            "catalogAttributes": catalog_attributes,
        }
    )


def _compact_prompt_payload(value: Any) -> Any:
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, nested in value.items():
            compacted_value = _compact_prompt_payload(nested)
            if compacted_value in (None, "", [], {}):
                continue
            compacted[key] = compacted_value
        return compacted
    if isinstance(value, list):
        compacted_list = [_compact_prompt_payload(item) for item in value]
        return [item for item in compacted_list if item not in (None, "", [], {})]
    return value


def _prompt_profile_instruction(prompt_profile: str | None) -> str | None:
    profile = str(prompt_profile or "").strip()
    if not profile:
        return None
    instructions = {
        "camera_interchangeable_lens_extract_v1": (
            "Focus on real lens identity. Distinguish lens listings from camera body bundles, "
            "and prioritize mount_system, focal_length_range, max_aperture, lens_series, generation, and exact model_name."
        ),
        "camera_body_extract_v1": (
            "Focus on camera body identity. Distinguish camera bodies from body-plus-lens bundles, "
            "and prioritize product_line, mount_system, sensor_format, pixel_resolution, camera_type, generation, and exact model_name."
        ),
        "apple_computer_extract_v1": (
            "Focus on Apple computer identity. Distinguish product line, chip generation, screen size, memory, and storage. "
            "Do not confuse accessories with the host computer."
        ),
        "garmin_watch_extract_v1": (
            "Focus on Garmin watch identity. Distinguish product line, exact model_name, case_size_mm, solar, display_type, and edition tags."
        ),
        "smartphone_extract_v1": (
            "Focus on phone identity. Distinguish series, storage, memory, color, and exact device model."
        ),
        "apple_airpods_extract_v1": (
            "Focus on Apple AirPods identity. Distinguish model generation, interface type (Lightning/USB-C), "
            "mainland/china variant, box/manual completeness, and invoice signal."
        ),
    }
    return instructions.get(profile)


def _load_model_catalog_entries(session: Session, category_id: str | None) -> list[dict[str, Any]]:
    if not category_id:
        return []
    rows = list(
        session.execute(
            select(CategoryModelCatalog).where(
                CategoryModelCatalog.category_id == category_id,
                CategoryModelCatalog.status == "ACTIVE",
            )
        ).scalars().all()
    )
    result = []
    for row in sorted(rows, key=lambda entry: (str(entry.brand_name or ""), str(entry.model_code or ""))):
        aliases = [
            {
                "aliasText": alias.alias_text,
                "aliasNormalized": alias.alias_normalized,
                "aliasType": alias.alias_type,
            }
            for alias in sorted(
                list(getattr(row, "aliases", []) or []),
                key=lambda alias: (str(alias.alias_type or ""), str(alias.alias_text or "")),
            )
            if str(alias.status or "").upper() == "ACTIVE"
        ]
        result.append(
            {
                "id": row.id,
                "brandName": row.brand_name,
                "seriesName": row.series_name,
                "modelCode": row.model_code,
                "modelName": row.model_name,
                "aliases": aliases,
            }
        )
    return result


def apply_runtime_context_to_candidate(
    *,
    item: Item,
    candidate: SpecEnrichmentCandidate,
    runtime_context: dict[str, Any] | None,
) -> SpecEnrichmentCandidate:
    context = runtime_context or {}
    template_detail = context.get("templateDetail") or {}
    template_meta = dict((candidate.extraction_payload or {}).get("catalogTemplate") or {})
    if not template_meta and template_detail:
        template_meta = _catalog_template_metadata(template_detail)
    category = context.get("category")
    candidate.category_id = (
        getattr(item, "resolved_category_id", None)
        or template_meta.get("categoryId")
        or getattr(category, "id", None)
        or getattr(item, "target_category_id", None)
    )
    candidate.template_id = (
        getattr(item, "resolved_template_id", None)
        or template_meta.get("templateId")
        or candidate.template_id
    )
    candidate.model_catalog_id = _match_model_catalog_id(
        candidate=candidate,
        item=item,
        runtime_context=context,
    )
    matched_model_catalog = _lookup_model_catalog_entry(
        model_catalog_id=candidate.model_catalog_id,
        runtime_context=context,
    )
    if resolve_category_code(item.business_domain) == "camera_interchangeable_lens":
        candidate = _apply_lens_catalog_canonicalization(
            candidate=candidate,
            matched_model_catalog=matched_model_catalog,
            item=item,
        )
    candidate.extraction_payload = {
        **dict(candidate.extraction_payload or {}),
        "runtimeProfile": {
            "promptProfile": context.get("promptProfile"),
            "categoryId": candidate.category_id,
            "templateId": candidate.template_id,
            "modelCatalogSize": len(list(context.get("modelCatalog") or [])),
        },
    }
    groups = _extract_catalog_attribute_groups(candidate.extraction_payload)
    if template_detail and any(groups[group] for group in CATALOG_ATTRIBUTE_GROUPS):
        candidate.extraction_payload["catalogAttributes"] = _normalize_catalog_attribute_groups(
            groups=groups,
            template_detail=template_detail,
            preferred_rows=_preferred_catalog_attribute_rows(
                candidate=candidate,
                matched_model_catalog=matched_model_catalog,
            ),
        )
    return candidate


def _lookup_model_catalog_entry(
    *,
    model_catalog_id: str | None,
    runtime_context: dict[str, Any],
) -> dict[str, Any] | None:
    if not model_catalog_id:
        return None
    for row in list(runtime_context.get("modelCatalog") or []):
        if str(row.get("id") or "") == str(model_catalog_id):
            return dict(row)
    return None


def _apply_lens_catalog_canonicalization(
    *,
    candidate: SpecEnrichmentCandidate,
    matched_model_catalog: dict[str, Any] | None,
    item: Item,
) -> SpecEnrichmentCandidate:
    if str((candidate.evidence or {}).get("reason") or "") == "non_target_camera_body":
        return candidate
    canonical_brand = _normalize_lens_brand_label(
        candidate.brand or item.normalized_brand or (matched_model_catalog or {}).get("brandName")
    )
    if canonical_brand:
        candidate.brand = canonical_brand

    if matched_model_catalog:
        series_name = _normalize_optional_text(matched_model_catalog.get("seriesName"))
        model_name = _normalize_optional_text(matched_model_catalog.get("modelName"))
        if series_name:
            candidate.product_line = series_name
            candidate.model_family = series_name
        if model_name:
            candidate.model_name = model_name
    else:
        partial_model_name = (
            _build_partial_lens_model_name(candidate.model_name, brand=candidate.brand)
            or _build_partial_lens_model_name(item.normalized_model, brand=candidate.brand or item.normalized_brand)
            or _build_partial_lens_model_name(item.title, brand=candidate.brand or item.normalized_brand)
        )
        if partial_model_name:
            candidate.model_name = partial_model_name
        mount_signature = _extract_lens_mount_signature(
            candidate.model_name or item.normalized_model or item.title,
            brand=candidate.brand or item.normalized_brand,
        )
        series_name = _canonical_lens_series_label(
            brand=candidate.brand or item.normalized_brand,
            mount_signature=mount_signature,
        )
        if series_name:
            candidate.product_line = series_name
            candidate.model_family = series_name
    return candidate


def _preferred_catalog_attribute_rows(
    *,
    candidate: SpecEnrichmentCandidate,
    matched_model_catalog: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    preferred: dict[str, dict[str, Any]] = {}
    brand_value = _normalize_lens_brand_label(candidate.brand)
    if brand_value:
        preferred["brand_name"] = {"attributeCode": "brand_name", "textValue": brand_value}

    model_name = _normalize_optional_text(candidate.model_name)
    if model_name:
        preferred["model_name"] = {"attributeCode": "model_name", "textValue": model_name}

    series_name = _normalize_optional_text(
        (matched_model_catalog or {}).get("seriesName")
        or candidate.product_line
        or candidate.model_family
    )
    if series_name:
        preferred["lens_series"] = {"attributeCode": "lens_series", "textValue": series_name}
        preferred["product_line"] = {"attributeCode": "product_line", "textValue": series_name}

    focal_range = _format_lens_focal_range(candidate.model_name)
    if focal_range:
        preferred["focal_length_range"] = {
            "attributeCode": "focal_length_range",
            "textValue": focal_range,
        }

    aperture = _format_lens_aperture(candidate.model_name)
    if aperture:
        preferred["max_aperture"] = {
            "attributeCode": "max_aperture",
            "textValue": aperture,
        }

    mount_system = _preferred_lens_mount_label(
        candidate=candidate,
        matched_model_catalog=matched_model_catalog,
    )
    if mount_system:
        preferred["mount_system"] = {
            "attributeCode": "mount_system",
            "textValue": mount_system,
        }
    return preferred


def _normalize_catalog_attribute_groups(
    *,
    groups: dict[str, list[dict[str, Any]]],
    template_detail: dict[str, Any],
    preferred_rows: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    item_map = _template_item_map(template_detail)
    normalized = {group: [] for group in CATALOG_ATTRIBUTE_GROUPS}
    for group in CATALOG_ATTRIBUTE_GROUPS:
        by_code: dict[str, list[dict[str, Any]]] = {}
        for row in list(groups.get(group) or []):
            code = str(row.get("attributeCode") or "").strip()
            if not code:
                continue
            by_code.setdefault(code, []).append(dict(row))

        for attribute_code, rows in by_code.items():
            template_item = item_map.get(attribute_code)
            deduped_rows = _dedupe_catalog_rows(rows)
            if template_item is None or bool(template_item.get("isMulti", False)):
                normalized[group].extend(deduped_rows)
                continue
            preferred_row = dict((preferred_rows or {}).get(attribute_code) or {})
            if preferred_row:
                normalized[group].append(preferred_row)
            elif deduped_rows:
                normalized[group].append(deduped_rows[0])

        normalized[group] = sorted(
            normalized[group],
            key=lambda row: (
                int(item_map.get(str(row.get("attributeCode") or ""), {}).get("sortNo") or 0),
                str(row.get("attributeCode") or ""),
                json.dumps(row, ensure_ascii=False, sort_keys=True, default=str),
            ),
        )
    return normalized


def _match_model_catalog_id(
    *,
    candidate: SpecEnrichmentCandidate,
    item: Item,
    runtime_context: dict[str, Any],
) -> str | None:
    model_catalog = list(runtime_context.get("modelCatalog") or [])
    if not model_catalog:
        return None
    normalized_candidates = {
        normalize_model_alias(candidate.model_name),
        normalize_model_alias(item.normalized_model),
        normalize_model_alias(item.title),
    }
    normalized_candidates.discard("")
    if not normalized_candidates:
        return None
    for model_entry in model_catalog:
        known_keys = {
            normalize_model_alias(model_entry.get("modelCode")),
            normalize_model_alias(model_entry.get("modelName")),
        }
        for alias in list(model_entry.get("aliases") or []):
            known_keys.add(normalize_model_alias(alias.get("aliasNormalized") or alias.get("aliasText")))
        known_keys.discard("")
        if normalized_candidates & known_keys:
            return str(model_entry.get("id"))

    if resolve_category_code(item.business_domain) != "camera_interchangeable_lens":
        return None

    candidate_signatures = [
        signature
        for signature in (
            _build_lens_match_signature(candidate.model_name, brand=candidate.brand),
            _build_lens_match_signature(item.normalized_model, brand=item.normalized_brand or candidate.brand),
            _build_lens_match_signature(item.title, brand=item.normalized_brand or candidate.brand),
        )
        if signature
    ]
    if not candidate_signatures:
        return None

    best_model_id: str | None = None
    best_score = -1
    is_tie = False
    for model_entry in model_catalog:
        known_signatures = [
            signature
            for signature in (
                _build_lens_match_signature(
                    model_entry.get("modelName"),
                    brand=model_entry.get("brandName"),
                ),
                _build_lens_match_signature(
                    model_entry.get("seriesName"),
                    brand=model_entry.get("brandName"),
                ),
                *[
                    _build_lens_match_signature(
                        alias.get("aliasText") or alias.get("aliasNormalized"),
                        brand=model_entry.get("brandName"),
                    )
                    for alias in list(model_entry.get("aliases") or [])
                ],
            )
            if signature
        ]
        if not known_signatures:
            continue
        entry_best = max(
            _score_lens_signature_match(candidate_signature, known_signature)
            for candidate_signature in candidate_signatures
            for known_signature in known_signatures
        )
        if entry_best < 8:
            continue
        model_id = str(model_entry.get("id") or "")
        if entry_best > best_score:
            best_model_id = model_id or None
            best_score = entry_best
            is_tie = False
        elif entry_best == best_score:
            is_tie = True
    if is_tie:
        return None
    return best_model_id


def call_openai_compatible_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout_sec: int,
    enable_thinking: bool,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    provider = normalize_ai_provider(settings.ai_provider)
    if is_anthropic_compatible_provider(provider):
        request = build_anthropic_request(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
        )
    elif provider == "ark_responses":
        request = build_ark_responses_request(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
        )
    else:
        request = build_openai_request(
            base_url=base_url,
            api_key=api_key,
            model=model,
            enable_thinking=enable_thinking,
            max_tokens=max_tokens if max_tokens is not None else settings.ai_max_tokens,
            messages=messages,
            response_format=response_format,
        )
    trace_context = build_llm_trace_context(
        settings=settings,
        provider=provider,
        model=model,
        request=request,
        messages=messages,
    )
    try:
        if should_bypass_proxy(base_url):
            opener = build_opener(ProxyHandler({}))
            response_ctx = opener.open(request, timeout=timeout_sec)
        else:
            response_ctx = urlopen(request, timeout=timeout_sec)
        with response_ctx as response:
            payload = json.loads(response.read().decode("utf-8"))
            write_llm_trace(
                trace_context,
                response_payload=payload,
                error_message=None,
            )
            return payload
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        write_llm_trace(
            trace_context,
            response_payload=None,
            error_message=f"HTTP {exc.code}: {body[:500]}",
        )
        raise RuntimeError(f"LLM request failed with HTTP {exc.code}: {body[:500]}") from exc
    except URLError as exc:
        write_llm_trace(
            trace_context,
            response_payload=None,
            error_message=str(exc),
        )
        raise RuntimeError(f"LLM request failed: {exc}") from exc


def normalize_ai_provider(provider: str | None) -> str:
    normalized = str(provider or "openai_compatible").strip().lower()
    aliases = {
        "ark_openai": "openai_compatible",
        "ark_openai_compatible": "openai_compatible",
        "doubao": "openai_compatible",
        "doubao_openai": "openai_compatible",
        "doubao_openai_compatible": "openai_compatible",
        "ark_anthropic": "anthropic_compatible",
        "ark_anthropic_compatible": "anthropic_compatible",
        "doubao_anthropic": "anthropic_compatible",
        "doubao_anthropic_compatible": "anthropic_compatible",
    }
    return aliases.get(normalized, normalized)


def is_anthropic_compatible_provider(provider: str | None) -> bool:
    return normalize_ai_provider(provider) == "anthropic_compatible"


def should_bypass_proxy(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    default_hosts = {"localhost", "127.0.0.1", "::1", "ark.cn-beijing.volces.com"}
    extra_hosts = {
        str(value).strip().lower()
        for value in os.getenv("AI_BYPASS_PROXY_HOSTS", "").split(",")
        if str(value).strip()
    }
    return host in default_hosts.union(extra_hosts)


def build_llm_trace_context(
    *,
    settings: Any,
    provider: str,
    model: str,
    request: Request,
    messages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not bool(getattr(settings, "ai_prompt_trace_enabled", False)):
        return None

    trace_dir = Path(getattr(settings, "ai_prompt_trace_dir", Path("reports/llm-traces")))
    request_payload = None
    if getattr(request, "data", None):
        try:
            request_payload = json.loads(request.data.decode("utf-8"))
        except Exception:
            request_payload = {"raw": request.data.decode("utf-8", errors="ignore")}

    return {
        "traceId": uuid4().hex,
        "generatedAt": datetime.now().isoformat(),
        "provider": provider,
        "model": model,
        "url": request.full_url,
        "method": request.get_method(),
        "requestHeaders": sanitize_request_headers(request.headers),
        "messages": messages,
        "requestPayload": request_payload,
        "traceDir": trace_dir,
    }


def write_llm_trace(
    trace_context: dict[str, Any] | None,
    *,
    response_payload: dict[str, Any] | None,
    error_message: str | None,
    latency_ms: float | None = None,
    item_id: str | None = None,
) -> Path | None:
    if not trace_context:
        return None
    trace_dir = Path(trace_context["traceDir"])
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"{trace_context['generatedAt'].replace(':', '-').replace('.', '-')}-{trace_context['traceId']}.json"
    
    usage_stats = extract_usage_stats(response_payload) if response_payload else None
    
    payload = {
        "generatedAt": trace_context["generatedAt"],
        "provider": trace_context["provider"],
        "model": trace_context["model"],
        "url": trace_context["url"],
        "method": trace_context["method"],
        "requestHeaders": trace_context["requestHeaders"],
        "messages": trace_context["messages"],
        "requestPayload": trace_context["requestPayload"],
        "responsePayload": response_payload,
        "error": error_message,
        "latencyMs": latency_ms,
        "itemId": item_id,
        "usage": usage_stats,
    }
    trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return trace_path


def sanitize_request_headers(headers: Any) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in dict(headers or {}).items():
        normalized_key = str(key)
        if normalized_key.lower() == "authorization":
            sanitized[normalized_key] = "[REDACTED]"
            continue
        sanitized[normalized_key] = value
    return sanitized


def extract_usage_stats(payload: dict[str, Any]) -> dict[str, int] | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tokens = usage.get("input_tokens")
    if input_tokens is None:
        input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens")
    if output_tokens is None:
        output_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")

    try:
        normalized_input = int(input_tokens) if input_tokens is not None else 0
        normalized_output = int(output_tokens) if output_tokens is not None else 0
        normalized_total = int(total_tokens) if total_tokens is not None else normalized_input + normalized_output
    except (TypeError, ValueError):
        return None

    cached_tokens = 0
    cache_details = usage.get("input_tokens_details")
    if isinstance(cache_details, dict):
        cached_value = cache_details.get("cached_tokens")
        try:
            cached_tokens = int(cached_value) if cached_value is not None else 0
        except (TypeError, ValueError):
            cached_tokens = 0

    return {
        "input_tokens": normalized_input,
        "output_tokens": normalized_output,
        "total_tokens": normalized_total,
        "cached_tokens": cached_tokens,
    }


def append_endpoint(base_url: str, endpoint: str) -> str:
    normalized_base = base_url.rstrip("/")
    normalized_endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    if normalized_base.endswith(normalized_endpoint):
        return normalized_base
    return f"{normalized_base}{normalized_endpoint}"


def openai_chat_completions_url(base_url: str) -> str:
    return append_endpoint(base_url, "/chat/completions")


def responses_url(base_url: str) -> str:
    return append_endpoint(base_url, "/responses")


def anthropic_messages_url(base_url: str) -> str:
    normalized_base = base_url.rstrip("/")
    parsed = urlparse(normalized_base)
    path = parsed.path.rstrip("/")
    if path.endswith("/messages"):
        return normalized_base
    if "ark.cn-" in (parsed.hostname or "").lower() and path.endswith("/api/coding"):
        return f"{normalized_base}/messages"
    if path.endswith("/v1"):
        return f"{normalized_base}/messages"
    return f"{normalized_base}/v1/messages"


def build_openai_request(
    *,
    base_url: str,
    api_key: str,
    model: str,
    enable_thinking: bool,
    max_tokens: int,
    messages: list[dict[str, Any]],
    response_format: dict[str, Any] | None = None,
) -> Request:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max(max_tokens, 1),
    }
    if response_format:
        payload["response_format"] = response_format
    if "ark.cn-" in (urlparse(base_url).hostname or "").lower():
        payload["extra_body"] = {"enable_thinking": bool(enable_thinking)}
    elif enable_thinking:
        payload["extra_body"] = {"enable_thinking": True}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return Request(
        url=openai_chat_completions_url(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )


def build_anthropic_request(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
) -> Request:
    system_prompt, converted_messages = convert_messages_to_anthropic(messages)
    payload: dict[str, Any] = {
        "model": model,
        "messages": converted_messages,
        "max_tokens": 600,
    }
    if system_prompt:
        payload["system"] = system_prompt

    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return Request(
        url=anthropic_messages_url(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )


def build_ark_responses_request(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
) -> Request:
    payload: dict[str, Any] = {
        "model": model,
        "input": convert_messages_to_responses_input(messages),
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return Request(
        url=responses_url(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )


def convert_messages_to_anthropic(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "").strip().lower()
        content = message.get("content")
        if role == "system":
            system_text = flatten_message_content(content)
            if system_text:
                system_parts.append(system_text)
            continue
        converted.append(
            {
                "role": role or "user",
                "content": anthropic_content_blocks(content),
            }
        )
    system_prompt = "\n\n".join(part for part in system_parts if part) or None
    return system_prompt, converted


def convert_messages_to_responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "").strip().lower() or "user"
        text = flatten_message_content(message.get("content"))
        if not text:
            continue
        converted.append(
            {
                "role": role,
                "content": [
                    {
                        "type": "input_text",
                        "text": text,
                    }
                ],
            }
        )
    return converted


def anthropic_content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, list):
        blocks: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                text = str(item.get("text") or "")
                if text:
                    blocks.append({"type": "text", "text": text})
                continue
            if item_type == "image":
                source = item.get("source") if isinstance(item.get("source"), dict) else {}
                media_type = str(source.get("media_type") or "image/png")
                data = source.get("data")
                if data:
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": data,
                            },
                        }
                    )
        if blocks:
            return blocks
    text = flatten_message_content(content)
    return [{"type": "text", "text": text}]


def flatten_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text") or "")
                if text:
                    texts.append(text)
        return "".join(texts)
    return ""


def extract_message_content(payload: dict[str, Any]) -> str:
    if payload.get("type") == "message":
        content = payload.get("content")
        text = flatten_message_content(content)
        if text:
            return text
        raise RuntimeError("Anthropic-compatible response content format is not supported.")
    if payload.get("object") == "response":
        output = payload.get("output") or []
        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content") or []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "output_text":
                    text = str(block.get("text") or "")
                    if text:
                        texts.append(text)
        if texts:
            return "".join(texts)
        raise RuntimeError("Responses API payload does not contain output_text.")
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("LLM response does not contain choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        if texts:
            return "".join(texts)
    raise RuntimeError("LLM response content format is not supported.")


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise RuntimeError("LLM response does not contain a JSON object.")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise RuntimeError("LLM response JSON root must be an object.")
    return value


def candidate_from_llm_payload(
    payload: dict[str, Any],
    *,
    item: Item,
    provider: str,
    model: str,
    template_detail: dict[str, Any] | None = None,
) -> SpecEnrichmentCandidate:
    confidence = payload.get("confidence")
    numeric_confidence = None
    if confidence is not None:
        numeric_confidence = Decimal(str(confidence)).quantize(Decimal("0.01"))

    catalog_groups = _normalize_llm_catalog_attribute_groups(
        payload=payload,
        template_detail=template_detail,
    )

    screen_size = payload.get("screen_size_in")
    if screen_size is None:
        screen_size = _first_catalog_number(catalog_groups, "screen_size_in")
    numeric_screen = Decimal(str(screen_size)) if screen_size is not None else None
    normalized_chip = normalize_chip_family(
        chip_family=payload.get("chip_family") or _first_catalog_text(catalog_groups, "chip_family"),
        cpu_model=payload.get("cpu_model"),
        model_name=payload.get("model_name") or _first_catalog_text(catalog_groups, "model_name"),
    )
    normalized_status = normalize_enrichment_status(payload.get("status"))

    candidate = SpecEnrichmentCandidate(
        extractor_type="llm",
        llm_provider=provider,
        llm_model=model,
        status=normalized_status,
        confidence=numeric_confidence,
        needs_review=bool(payload.get("needs_review", False)),
        brand=payload.get("brand") or item.normalized_brand,
        product_line=payload.get("product_line") or _first_catalog_text(catalog_groups, "product_line"),
        model_family=payload.get("model_family")
        or payload.get("product_line")
        or _first_catalog_text(catalog_groups, "product_line"),
        model_name=payload.get("model_name") or _first_catalog_text(catalog_groups, "model_name"),
        generation=payload.get("generation") or _first_catalog_text(catalog_groups, "generation"),
        case_size_mm=_to_int(payload.get("case_size_mm"))
        or _to_int(_first_catalog_number(catalog_groups, "case_size_mm")),
        is_solar=_to_bool_or_none(payload.get("is_solar"))
        if payload.get("is_solar") is not None
        else _to_bool_or_none(_first_catalog_bool(catalog_groups, "is_solar")),
        display_type=payload.get("display_type") or _first_catalog_text(catalog_groups, "display_type"),
        screen_size_in=numeric_screen,
        chip_family=normalized_chip,
        cpu_model=payload.get("cpu_model")
        or _first_catalog_text(catalog_groups, "cpu_model")
        or normalized_chip,
        cpu_cores=_to_int(payload.get("cpu_cores"))
        or _to_int(_first_catalog_number(catalog_groups, "cpu_cores")),
        gpu_cores=_to_int(payload.get("gpu_cores"))
        or _to_int(_first_catalog_number(catalog_groups, "gpu_cores")),
        memory_gb=_to_int(payload.get("memory_gb"))
        or _to_int(_first_catalog_number(catalog_groups, "memory_gb")),
        storage_gb=normalize_storage_gb(
            _to_int(payload.get("storage_gb"))
            or _to_int(_first_catalog_number(catalog_groups, "storage_gb"))
        ),
        edition_tags=_normalize_string_list(payload.get("edition_tags"))
        or _normalize_string_list(_first_catalog_json(catalog_groups, "edition_tags")),
        evidence={},
        extraction_payload={
            "catalogTemplate": _catalog_template_metadata(template_detail) if template_detail else None,
            "catalogAttributes": catalog_groups,
            "rawStatus": payload.get("status"),
        },
    )
    return apply_spec_enrichment_contract(item=item, candidate=candidate, source="llm")


def normalize_enrichment_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "partial"
    if text in {"complete", "completed", "success", "succeeded", "resolved", "valid", "ok", "done", "pass", "passed"}:
        return "complete"
    if text in {"partial", "incomplete", "mixed"}:
        return "partial"
    if text in {"unresolved", "unknown", "uncertain", "needs_review", "review_needed", "pending"}:
        return "unresolved"
    if text in {"failed", "failure", "error", "invalid"}:
        return "failed"
    return "partial"


def merge_candidates(
    *,
    item: Item,
    rule_candidate: SpecEnrichmentCandidate,
    llm_candidate: SpecEnrichmentCandidate,
) -> SpecEnrichmentCandidate:
    merged_catalog_groups = _merge_catalog_attribute_groups(
        _extract_catalog_attribute_groups(rule_candidate.extraction_payload),
        _extract_catalog_attribute_groups(llm_candidate.extraction_payload),
    )
    merged = SpecEnrichmentCandidate(
        category_id=llm_candidate.category_id or rule_candidate.category_id,
        template_id=llm_candidate.template_id or rule_candidate.template_id,
        model_catalog_id=llm_candidate.model_catalog_id or rule_candidate.model_catalog_id,
        extractor_type="hybrid",
        extractor_version=rule_candidate.extractor_version,
        llm_provider=llm_candidate.llm_provider,
        llm_model=llm_candidate.llm_model,
        status=llm_candidate.status if llm_candidate.status != "unresolved" else rule_candidate.status,
        confidence=max(
            rule_candidate.confidence or Decimal("0"),
            llm_candidate.confidence or Decimal("0"),
        ),
        needs_review=bool(rule_candidate.needs_review or llm_candidate.needs_review),
        brand=llm_candidate.brand or rule_candidate.brand,
        product_line=llm_candidate.product_line or rule_candidate.product_line,
        model_family=llm_candidate.model_family or rule_candidate.model_family,
        model_name=llm_candidate.model_name or rule_candidate.model_name,
        generation=llm_candidate.generation or rule_candidate.generation,
        case_size_mm=llm_candidate.case_size_mm or rule_candidate.case_size_mm,
        is_solar=llm_candidate.is_solar if llm_candidate.is_solar is not None else rule_candidate.is_solar,
        display_type=llm_candidate.display_type or rule_candidate.display_type,
        screen_size_in=llm_candidate.screen_size_in or rule_candidate.screen_size_in,
        chip_family=llm_candidate.chip_family or rule_candidate.chip_family,
        cpu_model=llm_candidate.cpu_model or rule_candidate.cpu_model,
        cpu_cores=llm_candidate.cpu_cores or rule_candidate.cpu_cores,
        gpu_cores=llm_candidate.gpu_cores or rule_candidate.gpu_cores,
        memory_gb=llm_candidate.memory_gb or rule_candidate.memory_gb,
        storage_gb=llm_candidate.storage_gb or rule_candidate.storage_gb,
        edition_tags=sorted(set(rule_candidate.edition_tags + llm_candidate.edition_tags)),
        evidence={
            "rule": rule_candidate.evidence,
            "llm": llm_candidate.evidence,
        },
        extraction_payload={
            "catalogTemplate": llm_candidate.extraction_payload.get("catalogTemplate")
            or rule_candidate.extraction_payload.get("catalogTemplate"),
            "catalogAttributes": merged_catalog_groups,
            "rule": rule_candidate.extraction_payload,
            "llm": llm_candidate.extraction_payload,
        },
    )
    return apply_spec_enrichment_contract(item=item, candidate=merged, source="hybrid")


def _normalize_llm_catalog_attribute_groups(
    *,
    payload: dict[str, Any],
    template_detail: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    groups = {group: [] for group in CATALOG_ATTRIBUTE_GROUPS}
    if template_detail is None:
        return groups

    item_map = _template_item_map(template_detail)
    for group in CATALOG_ATTRIBUTE_GROUPS:
        for raw_row in list(payload.get(group) or []):
            if not isinstance(raw_row, dict):
                continue
            normalized = _normalize_llm_attribute_row(raw_row=raw_row, item_map=item_map)
            if normalized is None:
                continue
            target_group = _catalog_group_for_item(item_map[normalized["attributeCode"]])
            groups[target_group].append(normalized)

    for attribute_code in LEGACY_DYNAMIC_ATTRIBUTE_CODES:
        if attribute_code not in payload:
            continue
        template_item = item_map.get(attribute_code)
        if template_item is None:
            continue
        target_group = _catalog_group_for_item(template_item)
        groups[target_group].extend(
            _rows_from_attribute_value(
                attribute_code=attribute_code,
                value=payload.get(attribute_code),
                template_item=template_item,
            )
        )

    for group in CATALOG_ATTRIBUTE_GROUPS:
        groups[group] = _dedupe_catalog_rows(groups[group])
    return groups


def _normalize_llm_attribute_row(
    *,
    raw_row: dict[str, Any],
    item_map: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    attribute_code = str(raw_row.get("attributeCode") or "").strip()
    if not attribute_code:
        return None
    template_item = item_map.get(attribute_code)
    if template_item is None:
        return None

    data_type = str(template_item.get("dataType") or "").upper()
    if data_type == "ENUM":
        option_code = str(raw_row.get("optionCode") or "").strip() or None
        option_id = str(raw_row.get("optionId") or "").strip() or None
        if option_code is None:
            option_name = str(raw_row.get("optionName") or "").strip().lower()
            if option_name:
                for option in list(template_item.get("options") or []):
                    if str(option.get("optionName") or "").strip().lower() == option_name:
                        option_code = str(option["optionCode"])
                        break
        if option_code is None and option_id is None:
            return None
        return {
            "attributeCode": attribute_code,
            "optionCode": option_code,
            "optionId": option_id,
        }

    if data_type == "TEXT":
        text_value = raw_row.get("textValue", raw_row.get("value"))
        if text_value is None:
            return None
        text = str(text_value).strip()
        if not text:
            return None
        return {"attributeCode": attribute_code, "textValue": text}

    if data_type == "NUMBER":
        number_value = raw_row.get("numberValue", raw_row.get("value"))
        normalized_number = _to_number_value(number_value)
        if normalized_number is None:
            return None
        return {
            "attributeCode": attribute_code,
            "numberValue": normalized_number,
            "normalizedNumberValue": normalized_number,
            "unit": raw_row.get("unit") or template_item.get("unit"),
        }

    if data_type == "BOOLEAN":
        bool_value = _to_bool_or_none(raw_row.get("boolValue", raw_row.get("value")))
        if bool_value is None:
            return None
        return {"attributeCode": attribute_code, "boolValue": bool_value}

    json_value = raw_row.get("jsonValue", raw_row.get("value"))
    if json_value is None:
        return None
    return {"attributeCode": attribute_code, "jsonValue": json_value}


def _merge_catalog_attribute_groups(
    rule_groups: dict[str, list[dict[str, Any]]],
    llm_groups: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    merged = {group: [] for group in CATALOG_ATTRIBUTE_GROUPS}
    for group in CATALOG_ATTRIBUTE_GROUPS:
        llm_rows = [dict(row) for row in list(llm_groups.get(group) or [])]
        rule_rows = [dict(row) for row in list(rule_groups.get(group) or [])]
        llm_codes = {str(row.get("attributeCode")) for row in llm_rows}
        merged[group].extend(llm_rows)
        merged[group].extend(
            row for row in rule_rows if str(row.get("attributeCode")) not in llm_codes
        )
        merged[group] = _dedupe_catalog_rows(merged[group])
    return merged


def _catalog_rows_for_code(
    groups: dict[str, list[dict[str, Any]]],
    attribute_code: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in CATALOG_ATTRIBUTE_GROUPS:
        rows.extend(
            row
            for row in list(groups.get(group) or [])
            if str(row.get("attributeCode")) == attribute_code
        )
    return rows


def _first_catalog_text(groups: dict[str, list[dict[str, Any]]], attribute_code: str) -> str | None:
    for row in _catalog_rows_for_code(groups, attribute_code):
        text_value = row.get("textValue")
        if text_value is None:
            continue
        text = str(text_value).strip()
        if text:
            return text
    return None


def _first_catalog_number(
    groups: dict[str, list[dict[str, Any]]],
    attribute_code: str,
) -> int | float | None:
    for row in _catalog_rows_for_code(groups, attribute_code):
        number_value = row.get("numberValue")
        if number_value is not None:
            return number_value
    return None


def _first_catalog_bool(groups: dict[str, list[dict[str, Any]]], attribute_code: str) -> bool | None:
    for row in _catalog_rows_for_code(groups, attribute_code):
        if row.get("boolValue") is not None:
            return bool(row["boolValue"])
    return None


def _first_catalog_json(groups: dict[str, list[dict[str, Any]]], attribute_code: str) -> Any:
    for row in _catalog_rows_for_code(groups, attribute_code):
        if row.get("jsonValue") is not None:
            return row["jsonValue"]
    return None


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None

