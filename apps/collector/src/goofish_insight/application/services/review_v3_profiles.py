from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReviewV3Field:
    name: str
    description: str


@dataclass(frozen=True)
class ReviewV3Profile:
    business_domain: str
    item_type_values: tuple[str, ...]
    first_pass_fields: tuple[ReviewV3Field, ...]
    direct_map_confidence_threshold: float = 0.80
    second_pass_candidate_limit: int = 5


LENS_PROFILE = ReviewV3Profile(
    business_domain="camera_interchangeable_lens",
    item_type_values=("镜头本体", "配件", "机身", "其他"),
    first_pass_fields=(
        ReviewV3Field("is_main_product", "boolean，是否在卖镜头本体。"),
        ReviewV3Field("item_type", '枚举："镜头本体" | "配件" | "机身" | "其他"。'),
        ReviewV3Field("brand", "品牌，如 Nikon/Canon/Sony。"),
        ReviewV3Field("mount", "卡口，如 Z卡口 / RF卡口 / E卡口。"),
        ReviewV3Field("focal_length", "焦段，如 24-70mm / 85mm。"),
        ReviewV3Field("aperture", "最大光圈，如 f/2.8 / f/1.8。"),
        ReviewV3Field("is_flawless", "boolean，只有卖家明确表示充新、无划痕、完美、仅试机等极佳成色时才为 true；否则为 false。"),
        ReviewV3Field("confidence_score", "0.0-1.0，卖家描述清晰度与可判定性。"),
    ),
)

APPLE_PROFILE = ReviewV3Profile(
    business_domain="apple_computer",
    item_type_values=("电脑本体", "配件", "手机平板", "其他"),
    first_pass_fields=(
        ReviewV3Field("is_main_product", "boolean，是否在卖 Apple 电脑本体。"),
        ReviewV3Field("item_type", '枚举："电脑本体" | "配件" | "手机平板" | "其他"。'),
        ReviewV3Field("brand", "品牌，通常是 Apple。"),
        ReviewV3Field("product_line", "如 MacBook Air / MacBook Pro / Mac Studio / Mac mini / iMac。"),
        ReviewV3Field("chip_family", "如 M1 / M2 / M3 Pro / M4 Max。"),
        ReviewV3Field("memory_gb", "整数内存容量，如 16 / 18 / 24 / 36。"),
        ReviewV3Field("storage_gb", "整数存储容量，如 256 / 512 / 1024。"),
        ReviewV3Field("screen_size_in", "屏幕尺寸，如 13 / 14 / 15 / 16 / 24。"),
        ReviewV3Field("is_flawless", "boolean，只有卖家明确表示充新、无划痕、完美、仅试机等极佳成色时才为 true；否则为 false。"),
        ReviewV3Field("confidence_score", "0.0-1.0，卖家描述清晰度与可判定性。"),
    ),
)

GARMIN_PROFILE = ReviewV3Profile(
    business_domain="garmin_watch",
    item_type_values=("手表本体", "配件", "服务", "其他"),
    first_pass_fields=(
        ReviewV3Field("is_main_product", "boolean，是否在卖 Garmin 手表本体。"),
        ReviewV3Field("item_type", '枚举："手表本体" | "配件" | "服务" | "其他"。'),
        ReviewV3Field("brand", "品牌，通常是 Garmin/佳明。"),
        ReviewV3Field("product_line", "如 Fenix / Forerunner / Epix / Instinct。"),
        ReviewV3Field("model_hint", "卖家描述里的型号提示，如 Fenix 7 / 965 / Epix Pro。"),
        ReviewV3Field("case_size_mm", "表径毫米数，如 42 / 47 / 51。"),
        ReviewV3Field("is_solar", "boolean 或 null，是否明确提到 Solar / 太阳能。"),
        ReviewV3Field("display_type", "如 AMOLED / MIP。"),
        ReviewV3Field("is_flawless", "boolean，只有卖家明确表示充新、无划痕、完美、仅试机等极佳成色时才为 true；否则为 false。"),
        ReviewV3Field("confidence_score", "0.0-1.0，卖家描述清晰度与可判定性。"),
    ),
)

CAMERA_BODY_PROFILE = ReviewV3Profile(
    business_domain="camera_body",
    item_type_values=("机身本体", "镜头", "配件", "其他"),
    first_pass_fields=(
        ReviewV3Field("is_main_product", "boolean，是否在卖相机机身本体。"),
        ReviewV3Field("item_type", '枚举："机身本体" | "镜头" | "配件" | "其他"。'),
        ReviewV3Field("brand", "品牌，如 Sony / Canon / Nikon / Fujifilm / Panasonic。"),
        ReviewV3Field("product_line", "业务线，如 Alpha / EOS R / Z / X / GFX / LUMIX。"),
        ReviewV3Field("model_hint", "卖家标题里的型号提示，如 A7R IV / R5 Mark II / Z8 / X-T5 / S5 IIX。"),
        ReviewV3Field("mount", "卡口，如 E卡口 / RF卡口 / Z卡口 / X卡口 / GFX / L卡口 / M43。"),
        ReviewV3Field("sensor_format", "画幅，如 全画幅 / APS-C / 中画幅 / M43。"),
        ReviewV3Field("is_flawless", "boolean，只有卖家明确表示充新、无划痕、完美、仅试机等极佳成色时才为 true；否则为 false。"),
        ReviewV3Field("confidence_score", "0.0-1.0，卖家描述清晰度与可判定性。"),
    ),
)

PHONE_PROFILE = ReviewV3Profile(
    business_domain="phone",
    item_type_values=("手机本体", "配件", "耳机手表", "其他"),
    first_pass_fields=(
        ReviewV3Field("is_main_product", "boolean，是否在卖手机本体。"),
        ReviewV3Field("item_type", '枚举："手机本体" | "配件" | "耳机手表" | "其他"。'),
        ReviewV3Field("brand", "品牌，如 Apple。"),
        ReviewV3Field("product_line", "产品线，如 iPhone。"),
        ReviewV3Field("model_hint", "型号提示，如 iPhone 13 Pro / iPhone 15 Pro Max / iPhone XR / iPhone 16。"),
        ReviewV3Field("storage_gb", "整数存储容量，如 128 / 256 / 512 / 1024。"),
        ReviewV3Field("is_flawless", "boolean，只有卖家明确表示充新、无划痕、完美、仅试机等极佳成色时才为 true；否则为 false。"),
        ReviewV3Field("confidence_score", "0.0-1.0，卖家描述清晰度与可判定性。"),
    ),
)

AIRPODS_PROFILE = ReviewV3Profile(
    business_domain="apple_airpods",
    item_type_values=("耳机本体", "配件", "手机电脑", "其他"),
    first_pass_fields=(
        ReviewV3Field("is_main_product", "boolean，是否在卖 AirPods 耳机本体。"),
        ReviewV3Field("item_type", '枚举："耳机本体" | "配件" | "手机电脑" | "其他"。'),
        ReviewV3Field("brand", "品牌，通常是 Apple。"),
        ReviewV3Field("product_line", "产品线，如 AirPods / AirPods Pro / AirPods Max。"),
        ReviewV3Field("model_hint", "型号提示，如 AirPods Pro 2 / AirPods 4 / AirPods 4 ANC / AirPods Max。"),
        ReviewV3Field("has_anc", "boolean 或 null，是否明确提到主动降噪/ANC。"),
        ReviewV3Field("is_flawless", "boolean，只有卖家明确表示充新、无划痕、完美、仅试机等极佳成色时才为 true；否则为 false。"),
        ReviewV3Field("confidence_score", "0.0-1.0，卖家描述清晰度与可判定性。"),
    ),
)

_PROFILE_REGISTRY = {
    profile.business_domain: profile
    for profile in (
        LENS_PROFILE,
        APPLE_PROFILE,
        GARMIN_PROFILE,
        CAMERA_BODY_PROFILE,
        PHONE_PROFILE,
        AIRPODS_PROFILE,
    )
}


def list_review_v3_profiles() -> tuple[ReviewV3Profile, ...]:
    return tuple(_PROFILE_REGISTRY.values())


def get_review_v3_profile(business_domain: str | None) -> ReviewV3Profile | None:
    normalized = str(business_domain or "").strip().lower()
    return _PROFILE_REGISTRY.get(normalized)


def build_first_pass_system_prompt(profile: ReviewV3Profile) -> str:
    field_lines = "\n".join(f'- `{field.name}`: {field.description}' for field in profile.first_pass_fields)
    item_type_values = " | ".join(f'"{value}"' for value in profile.item_type_values)
    return (
        "你是一个二手商品特征提取助手，只返回扁平事实字段。"
        "不要返回 catalog id、template id、spuAttributes、skuAttributes。\n"
        "规则：\n"
        "1. 只提取原文明确支持的事实；没有就返回 null。\n"
        "2. 如果不是目标商品本体，is_main_product=false，并把 item_type 设成最合适的非目标类型。\n"
        f"3. item_type 只能从 {item_type_values} 中选一个。\n"
        "4. 不要复述标题或成色原文，不要输出长文本。\n"
        "5. `is_flawless` 只有在原文明说充新、无划痕、完美、仅试机、全新未用时才为 true；否则 false。\n"
        "6. 如果容量、代际、尺寸、卡口等信息冲突，返回 null，不要猜。\n"
        "7. 返回必须是单个 JSON object，不能包代码块。\n"
        "输出字段：\n"
        f"{field_lines}"
    )


def build_first_pass_batch_system_prompt(profile: ReviewV3Profile) -> str:
    field_lines = "\n".join(f'- `{field.name}`: {field.description}' for field in profile.first_pass_fields)
    item_type_values = " | ".join(f'"{value}"' for value in profile.item_type_values)
    return (
        "你是一个二手商品特征提取助手，只返回扁平事实字段。"
        "不要返回 catalog id、template id、spuAttributes、skuAttributes。\n"
        "你会一次收到同一业务域下的多个商品。请逐条处理，不能漏 item_id。\n"
        "规则：\n"
        "1. 只提取原文明确支持的事实；没有就返回 null。\n"
        "2. 如果不是目标商品本体，is_main_product=false，并把 item_type 设成最合适的非目标类型。\n"
        f"3. item_type 只能从 {item_type_values} 中选一个。\n"
        "4. 不要复述标题或成色原文，不要输出长文本。\n"
        "5. `is_flawless` 只有在原文明说充新、无划痕、完美、仅试机、全新未用时才为 true；否则 false。\n"
        "6. 如果容量、代际、尺寸、卡口等信息冲突，返回 null，不要猜。\n"
        "7. 返回必须是单个 JSON object，格式为 {\"items\":[...]}，不能包代码块。\n"
        "8. `items` 数组中的每个对象都必须保留原始 `item_id`，且每个输入商品都必须输出一条结果。\n"
        "每条结果输出字段：\n"
        "- `item_id`: 原样返回输入 item_id。\n"
        f"{field_lines}"
    )


def build_first_pass_user_payload(*, item: dict[str, Any]) -> dict[str, Any]:
    description = str(item.get("listing_description") or "").strip()
    if len(description) > 160:
        description = description[:160]
    payload = {
        "task": "first_pass_feature_extraction",
        "business_domain": item.get("business_domain"),
        "item_id": item.get("item_id"),
        "title": item.get("title"),
        "condition_tags": list(item.get("condition_tags") or [])[:3],
        "listing_description": description or None,
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def build_first_pass_batch_user_payload(*, business_domain: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    serialized_items = [build_first_pass_user_payload(item=item) for item in items]
    return {
        "task": "first_pass_feature_extraction_batch",
        "business_domain": business_domain,
        "items": serialized_items,
    }


def build_second_pass_system_prompt(profile: ReviewV3Profile) -> str:
    return (
        "你是一个资深的二手商品鉴定专家。你会收到：原始标题、第一阶段提取结果、以及 3-5 个候选 catalog 型号。"
        "你的任务不是自由发挥，而是在候选列表里做严格判断。\n"
        "规则：\n"
        "1. 只能在候选列表里选 resolved_model_code；如果都不像，就返回 null。\n"
        "2. 只要 resolved_model_code 不是 null，就必须同时返回 is_resolved=true。\n"
        "3. 如果仍然不确定，needs_human=true，resolved_model_code=null。\n"
        "4. 返回必须是单个 JSON object，不能包 markdown。\n"
        "5. 不要回传原始 title，不要扩写候选列表之外的新型号。\n"
        f"6. 当前业务域是 {profile.business_domain}。"
    )


def build_second_pass_user_payload(
    *,
    item: dict[str, Any],
    first_pass_features: dict[str, Any],
    catalog_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "task": "second_pass_candidate_resolution",
        "raw_title": item.get("title"),
        "listing_description": item.get("listing_description"),
        "condition_tags": item.get("condition_tags") or [],
        "first_pass_extraction": first_pass_features,
        "catalog_candidates": catalog_candidates,
    }


def render_json_user_prompt(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
