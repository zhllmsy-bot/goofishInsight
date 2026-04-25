from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any

from ...category_compat import is_apple_computer_scope, is_garmin_watch_scope
from ...domain.review.contracts import (
    ALLOWED_FIELD_KEYS,
    INVALID_FIELD_VALUE,
    INVALID_REASONS,
    REVIEW_STATUS_INVALID,
    REVIEW_STATUS_VALID,
    build_field_contract_lines,
    coerce_decimal,
    normalize_invalid_reason,
    normalize_text,
    validate_field_value,
)
from ...domain.review.policy import (
    resolve_review_status,
    review_confidence_passes_acceptance_gate,
)
from ...settings import get_settings
from ...specs import call_openai_compatible_chat, extract_message_content, extract_usage_stats, llm_is_configured

LLM_REVIEW_MAX_ATTEMPTS = 2
LISTING_DESCRIPTION_LENGTH_LIMIT = 400
PROMPT_CURRENT_VALUE_TEXT_LIMIT = 48
AUDIT_STRIPPED_REVIEW_INPUT_KEYS = frozenset(
    {
        "t",
        "title",
        "r",
        "region",
        "rule",
        "rule_candidate",
        "desc_len",
        "listing_description_length",
    }
)
HARD_REJECT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("recycling", ("回收", "高价回收", "求购", "收一台", "收个", "收你", "想收", "慢收", "边收边等", "以旧换新")),
    ("service", ("代下单", "代拍", "代购", "出租", "租赁", "维修", "上门维修", "安装服务", "支持上门服务")),
    ("accessory", ("表带", "保护壳", "壳子", "贴膜", "充电器", "适配器", "键盘膜", "鼠标")),
    ("ad", ("加v", "加vx", "加微信", "联系v", "引流", "微商")),
)

BUYING_INTENT_TOKENS: tuple[str, ...] = (
    "求",
    "求购",
    "想收",
    "收一个",
    "收一台",
    "收个",
    "收台",
    "收你",
    "带价来",
    "来价",
    "慢收",
    "边收边等",
    "有闲置的朋友",
    "欢迎骚扰",
    "收收收",
)

SERVICE_FLOW_TOKENS: tuple[str, ...] = (
    "先咨询",
    "不要直接拍",
    "勿直接拍",
    "不支持直接拍",
    "不走平台",
    "支持上门服务",
    "资格服务",
    "代操作",
    "代领",
    "代申领",
)

CHANNEL_SUBSIDY_TOKENS: tuple[str, ...] = (
    "补贴资格",
    "补贴名额",
    "员工价",
    "渠道价",
    "资格服务",
)

COMMERCIAL_AD_STRONG_TOKENS: tuple[str, ...] = (
    "活动来袭",
    "超值特惠",
    "抄底价",
    "全系列",
    "现货发",
    "全新现货",
    "专柜发",
    "全国联保",
)

COMMERCIAL_AD_HINT_TOKENS: tuple[str, ...] = (
    "可置换",
    "置换",
    "顺丰包邮",
    "包邮到家",
    "国行中文版",
    "原装正品",
    "速来选购",
    "私信",
    "咨询",
)

NON_DEVICE_TOKENS: tuple[str, ...] = (
    "空盒",
    "盒子单出",
    "单出盒子",
    "账号",
    "id锁",
    "激活锁",
)


@dataclass(slots=True)
class BatchReviewResult:
    batch_size: int
    review_count: int
    entries: list[dict[str, Any]]
    llm_request_count: int
    llm_usage: dict[str, int] | None
    garbage_hit_count: int
    low_confidence_filtered_count: int
    high_confidence_kept_count: int


async def run_llm_item_review_batches(
    *,
    items: list[dict[str, Any]],
    batch_size: int,
    concurrency: int,
) -> list[BatchReviewResult]:
    batches = [items[index : index + batch_size] for index in range(0, len(items), batch_size)]
    semaphore = asyncio.Semaphore(concurrency)

    async def run_batch(batch: list[dict[str, Any]]) -> BatchReviewResult:
        async with semaphore:
            try:
                return await asyncio.to_thread(review_item_batch, batch=batch)
            except Exception:
                return BatchReviewResult(
                    batch_size=len(batch),
                    review_count=0,
                    entries=[],
                    llm_request_count=1,
                    llm_usage=None,
                    garbage_hit_count=0,
                    low_confidence_filtered_count=0,
                    high_confidence_kept_count=0,
                )

    return await asyncio.gather(*(run_batch(batch) for batch in batches))


def review_item_batch(*, batch: list[dict[str, Any]]) -> BatchReviewResult:
    if not llm_is_configured():
        raise RuntimeError("LLM review is not configured.")

    preclassified_entries, remaining_batch = build_preclassified_review_entries(batch=batch)
    preclassified_garbage_count = sum(
        1 for entry in preclassified_entries if normalize_invalid_reason(entry.get("invalid_reason")) == "garbage"
    )
    if not remaining_batch:
        return BatchReviewResult(
            batch_size=len(batch),
            review_count=len(preclassified_entries),
            entries=preclassified_entries,
            llm_request_count=0,
            llm_usage=None,
            garbage_hit_count=preclassified_garbage_count,
            low_confidence_filtered_count=0,
            high_confidence_kept_count=len(preclassified_entries),
        )

    response_payload = call_review_chat_with_retry(batch=remaining_batch)
    usage = extract_usage_stats(response_payload)
    content = extract_message_content(response_payload)
    try:
        raw_items = extract_json_array(content)
    except Exception:
        raw_items = []
    llm_entries, llm_metrics = sanitize_review_response(raw_items=raw_items, batch=remaining_batch)
    entries = merge_review_entries(preclassified_entries + llm_entries)
    return BatchReviewResult(
        batch_size=len(batch),
        review_count=len(entries),
        entries=entries,
        llm_request_count=1,
        llm_usage=usage,
        garbage_hit_count=preclassified_garbage_count + llm_metrics["garbage_hit_count"],
        low_confidence_filtered_count=llm_metrics["low_confidence_filtered_count"],
        high_confidence_kept_count=len(preclassified_entries) + len(llm_entries),
    )


def call_review_chat_with_retry(*, batch: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    messages = [
        {"role": "system", "content": build_review_system_prompt()},
        {"role": "user", "content": build_review_user_prompt(batch=batch)},
    ]
    last_error: Exception | None = None
    for attempt in range(1, LLM_REVIEW_MAX_ATTEMPTS + 1):
        try:
            return call_openai_compatible_chat(
                base_url=settings.ai_base_url,
                api_key=settings.ai_api_key,
                model=settings.ai_model,
                timeout_sec=settings.ai_timeout_sec,
                enable_thinking=settings.ai_enable_thinking,
                messages=messages,
            )
        except Exception as exc:
            last_error = exc
            if not is_retryable_llm_error(exc) or attempt >= LLM_REVIEW_MAX_ATTEMPTS:
                raise
            time.sleep(min(attempt, 2))
    raise RuntimeError("LLM review request failed without an exception.") from last_error


def is_retryable_llm_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("http 502", "http 503", "http 504", "10054"))


def build_review_system_prompt() -> str:
    allowed = ", ".join(build_field_contract_lines())
    invalid_reason_enum = "|".join(sorted(INVALID_REASONS))
    return (
        "You audit Goofish listings and return JSON only. "
        "Return one output object for every input item. Do not omit items. "
        "The output array length must equal the number of input items. "
        'Each output object must match {"item_id":"<id>","review_status":"valid|invalid","confidence":0.0,"invalid_reason":"' + invalid_reason_enum + '","not_match_field":[{"field_key":"<allowed field>","true_value":<json value>}]} '
        "Only return these fields. Do not echo titles, descriptions, tags, input values, rule candidates, or explanations. "
        "Hard constraints: "
        "item_id is a locked opaque string. Copy each item_id exactly from the input and only from the input. "
        "Never rewrite, concatenate, normalize, summarize, or invent item_id. "
        "If there is exactly one input item, the one output object must use that exact same item_id. "
        "Return JSON only. No prose. No markdown. "
        'For valid items, invalid_reason must be "" and not_match_field may be []. '
        "For invalid items, not_match_field must be []. "
        "Task: decide whether each listing is a real for-sale listing for the target product domain described by the query and item content. "
        "Do not use the upstream rule confidence as the answer. Treat it as a weak hint only. "
        "confidence estimates the probability that the listing is a real target-device sale listing. "
        'Mark invalid when any of the following is true: the post is buying/wanted/collecting instead of selling. Strong clues: "收", "求", "求购", "回收", "置换", "换购", "带价来", "来价", "想收", "收一个". '
        "The post is mainly a service, subsidy workaround, 代拍, 代下单, 导流, 资格服务, or other non-item service. "
        "The post is mainly an ad, accessory, parts listing, unrelated product, or a bulk commercial listing. "
        "Bulk commercial listings with many sizes, many versions, repeated price menus, nationwide shipping, current promotions, channel style sales copy, or exchange and trade-in marketing are invalid even if they mention real devices. "
        "The text explicitly says do not buy directly, asks users to contact privately for a service flow, or is mainly about the purchase channel, discount operation, subsidy flow, employee price, or education discount rather than the item itself. "
        "Mark valid when all of the following are true: the post is clearly selling a real device, not buying or offering a service. "
        "The device belongs to the target product family. "
        "The content contains concrete product evidence such as model family, chip generation, memory, storage, screen size, condition, battery, packaging, activation date, or price. "
        "Normal second-hand sale phrases such as self-pickup, price negotiable, can send more photos in private chat, or box missing do not by themselves make a listing invalid. "
        "Confidence rubric: 0.95-1.00 means explicit for-sale listing for a target device with strong concrete specs and no conflicting clues. "
        "0.80-0.94 means likely valid target-device sale listing, only minor ambiguity or one missing detail. "
        "0.60-0.79 means target-device sale listing is plausible, but there is notable ambiguity, noisy text, or incomplete evidence. "
        "0.00-0.30 means clearly invalid or strong reason to distrust the listing as a real target-device sale listing. "
        "0.31-0.59 means likely invalid or still too risky for downstream pricing. "
        "Use the confidence aggressively: clear direct sale listings with concrete model, chip, and spec clues should usually be at least 0.80 and often at least 0.90. "
        "Buying, wanted, service, subsidy, 代拍, or 导流 listings should usually be at most 0.30. "
        "Do not keep obviously valid sale listings stuck around 0.53 only because some fields are incomplete. "
        "Do not downgrade confidence only because the upstream rule confidence is low. "
        "not_match_field rules: only fill not_match_field for valid items when there is strong evidence that a whitelisted field is wrong. "
        "If the listing is valid but field evidence is incomplete, return not_match_field as []. "
        f"Allowed field_key/type: {allowed}."
    )


def build_review_user_prompt(*, batch: list[dict[str, Any]]) -> str:
    prompt_items = [build_review_input_snapshot(item) for item in batch]
    item_ids = [item["item_id"] for item in batch]
    payload = {
        "task": "return one result per item",
        "rule": "include all items; downstream filters by confidence",
        "item_id_rule": "item_id must be copied exactly from input and returned once per item; digits-only ids must stay byte-for-byte identical; if there is one item, the output item_id must equal that one input id exactly",
        "output_rule": "Return only item_id, review_status, confidence, invalid_reason, and not_match_field. Do not echo original input fields.",
        "input_item_ids": item_ids,
        "items": prompt_items,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def compact_prompt_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, nested in value.items():
            compact_nested = compact_prompt_mapping(nested)
            if compact_nested in (None, "", [], {}):
                continue
            compacted[key] = compact_nested
        return compacted
    if isinstance(value, list):
        compacted_list = [compact_prompt_mapping(item) for item in value]
        return [item for item in compacted_list if item not in (None, "", [], {})]
    return value


def build_review_input_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        "item_id": item["item_id"],
        "d": item["business_domain"],
        "t": item["title"],
        "p": item["current_price"],
        "k": item["source_keyword"],
        "tags": item["condition_tags"],
        "desc": normalize_text(item.get("listing_description")),
        "cur": _serialize_prompt_current_values(item.get("current_values") or {}),
    }
    return compact_prompt_mapping(snapshot)


def build_review_audit_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    return _strip_prompt_only_review_input_fields(build_review_input_snapshot(item))


def _strip_prompt_only_review_input_fields(review_input: dict[str, Any]) -> dict[str, Any]:
    audit_snapshot = dict(review_input)
    for key in AUDIT_STRIPPED_REVIEW_INPUT_KEYS:
        audit_snapshot.pop(key, None)
    return compact_prompt_mapping(audit_snapshot)


def _serialize_prompt_current_values(current_values: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for field_key in sorted(ALLOWED_FIELD_KEYS):
        if field_key not in current_values:
            continue
        value = current_values.get(field_key)
        if isinstance(value, str):
            normalized = normalize_text(value)
            if not normalized or len(normalized) > PROMPT_CURRENT_VALUE_TEXT_LIMIT:
                continue
            sanitized[field_key] = normalized
            continue
        sanitized[field_key] = value
    return compact_prompt_mapping(sanitized)


def build_review_input_signature(review_input: dict[str, Any]) -> str:
    normalized_review_input = normalize_review_input(review_input) or {}
    payload = json.dumps(normalized_review_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sanitize_review_response(
    *,
    raw_items: list[Any],
    batch: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    batch_ids = [item["item_id"] for item in batch]
    batch_id_set = set(batch_ids)
    current_values_by_item = {
        item["item_id"]: dict(item.get("current_values") or {})
        for item in batch
    }
    review_input_by_item = {
        item["item_id"]: build_review_audit_snapshot(item)
        for item in batch
    }
    review_input_signature_by_item = {
        item_id: build_review_input_signature(review_input)
        for item_id, review_input in review_input_by_item.items()
    }
    sanitized_by_item: dict[str, dict[str, Any]] = {}
    per_item_metrics = {
        item_id: {
            "garbage_hit": False,
            "low_confidence": False,
        }
        for item_id in batch_ids
    }
    metrics = {
        "garbage_hit_count": 0,
        "low_confidence_filtered_count": 0,
    }

    single_item_id = batch_ids[0] if len(batch_ids) == 1 else None

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        item_id = single_item_id or normalize_text(raw_item.get("item_id"))
        if single_item_id:
            raw_item = dict(raw_item)
            raw_item["item_id"] = single_item_id
        if not item_id or item_id not in batch_id_set:
            continue
        invalid_reason = normalize_invalid_reason(
            raw_item.get("invalid_reason") or raw_item.get("invalid_type") or raw_item.get("reason")
        )
        if invalid_reason == "garbage":
            per_item_metrics[item_id]["garbage_hit"] = True
        confidence = normalize_review_confidence(raw_item)
        review_status = resolve_review_status(
            review_status=raw_item.get("review_status"),
            invalid_reason=raw_item.get("invalid_reason") or raw_item.get("invalid_type") or raw_item.get("reason"),
        )
        if not review_confidence_passes_acceptance_gate(review_status=review_status, confidence=confidence):
            per_item_metrics[item_id]["low_confidence"] = True
        entry = sanitize_review_entry(
            raw_item=raw_item,
            current_values=current_values_by_item[item_id],
            enforce_confidence_gate=True,
        )
        if entry is None:
            continue
        entry["review_input"] = review_input_by_item[item_id]
        entry["review_input_signature"] = review_input_signature_by_item[item_id]
        existing = sanitized_by_item.get(item_id)
        if existing is None or entry["review_status"] == REVIEW_STATUS_INVALID:
            sanitized_by_item[item_id] = entry
            continue
        if existing["review_status"] == REVIEW_STATUS_INVALID:
            continue
        merged_fields = {
            field["field_key"]: field
            for field in existing.get("not_match_field") or []
        }
        for field in entry.get("not_match_field") or []:
            merged_fields[field["field_key"]] = field
        existing["not_match_field"] = list(merged_fields.values())

    entries: list[dict[str, Any]] = []
    for item_id in batch_ids:
        entry = sanitized_by_item.get(item_id)
        if entry is None:
            if per_item_metrics[item_id]["low_confidence"]:
                metrics["low_confidence_filtered_count"] += 1
            if per_item_metrics[item_id]["garbage_hit"]:
                metrics["garbage_hit_count"] += 1
            continue
        if per_item_metrics[item_id]["garbage_hit"]:
            metrics["garbage_hit_count"] += 1
        entries.append(entry)
    return entries, metrics


def build_preclassified_review_entries(
    *,
    batch: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    remaining_batch: list[dict[str, Any]] = []
    for item in batch:
        preclassified_entry = classify_review_item_without_llm(item=item)
        if preclassified_entry is None:
            remaining_batch.append(item)
            continue
        entries.append(preclassified_entry)
    return entries, remaining_batch


def classify_review_item_without_llm(*, item: dict[str, Any]) -> dict[str, Any] | None:
    prompt_review_input = build_review_input_snapshot(item)
    review_input = _strip_prompt_only_review_input_fields(prompt_review_input)
    title = normalize_text(prompt_review_input.get("t")) or ""
    listing_description = normalize_text(prompt_review_input.get("desc"))
    combined_text = f"{title}\n{listing_description or ''}".lower()
    review_input_signature = build_review_input_signature(review_input)
    if listing_description and len(listing_description) > LISTING_DESCRIPTION_LENGTH_LIMIT:
        return {
            "item_id": item["item_id"],
            "review_status": REVIEW_STATUS_INVALID,
            "invalid_reason": "garbage",
            "not_match_field": [],
            "confidence": 1.0,
            "review_origin": "rule_precheck",
            "review_input": review_input,
            "review_input_signature": review_input_signature,
        }
    for invalid_reason, tokens in HARD_REJECT_PATTERNS:
        if any(token.lower() in combined_text for token in tokens):
            if invalid_reason == "accessory" and has_target_product_signal(item=item):
                continue
            return {
                "item_id": item["item_id"],
                "review_status": REVIEW_STATUS_INVALID,
                "invalid_reason": invalid_reason,
                "not_match_field": [],
                "confidence": 1.0,
                "review_origin": "rule_precheck",
                "review_input": review_input,
                "review_input_signature": review_input_signature,
            }
    if has_buying_intent_signal(title=title, listing_description=listing_description):
        return {
            "item_id": item["item_id"],
            "review_status": REVIEW_STATUS_INVALID,
            "invalid_reason": "recycling",
            "not_match_field": [],
            "confidence": 1.0,
            "review_origin": "rule_precheck",
            "review_input": review_input,
            "review_input_signature": review_input_signature,
        }
    if has_service_flow_signal(title=title, listing_description=listing_description):
        return {
            "item_id": item["item_id"],
            "review_status": REVIEW_STATUS_INVALID,
            "invalid_reason": "service",
            "not_match_field": [],
            "confidence": 1.0,
            "review_origin": "rule_precheck",
            "review_input": review_input,
            "review_input_signature": review_input_signature,
        }
    if has_channel_subsidy_signal(title=title, listing_description=listing_description):
        return {
            "item_id": item["item_id"],
            "review_status": REVIEW_STATUS_INVALID,
            "invalid_reason": "service",
            "not_match_field": [],
            "confidence": 1.0,
            "review_origin": "rule_precheck",
            "review_input": review_input,
            "review_input_signature": review_input_signature,
        }
    if has_commercial_ad_signal(title=title, listing_description=listing_description):
        return {
            "item_id": item["item_id"],
            "review_status": REVIEW_STATUS_INVALID,
            "invalid_reason": "ad",
            "not_match_field": [],
            "confidence": 1.0,
            "review_origin": "rule_precheck",
            "review_input": review_input,
            "review_input_signature": review_input_signature,
        }
    if has_non_device_signal(title=title, listing_description=listing_description):
        return {
            "item_id": item["item_id"],
            "review_status": REVIEW_STATUS_INVALID,
            "invalid_reason": "garbage",
            "not_match_field": [],
            "confidence": 1.0,
            "review_origin": "rule_precheck",
            "review_input": review_input,
            "review_input_signature": review_input_signature,
        }
    if is_probable_garbage_listing(title=title, listing_description=listing_description):
        return {
            "item_id": item["item_id"],
            "review_status": REVIEW_STATUS_INVALID,
            "invalid_reason": "garbage",
            "not_match_field": [],
            "confidence": 1.0,
            "review_origin": "rule_precheck",
            "review_input": review_input,
            "review_input_signature": review_input_signature,
        }
    return None


def _combined_listing_text(*, title: str, listing_description: str | None) -> str:
    return f"{title}\n{listing_description or ''}".lower()


def has_buying_intent_signal(*, title: str, listing_description: str | None) -> bool:
    combined_text = _combined_listing_text(title=title, listing_description=listing_description)
    return any(token.lower() in combined_text for token in BUYING_INTENT_TOKENS)


def has_service_flow_signal(*, title: str, listing_description: str | None) -> bool:
    combined_text = _combined_listing_text(title=title, listing_description=listing_description)
    return any(token.lower() in combined_text for token in SERVICE_FLOW_TOKENS)


def has_channel_subsidy_signal(*, title: str, listing_description: str | None) -> bool:
    combined_text = _combined_listing_text(title=title, listing_description=listing_description)
    return any(token.lower() in combined_text for token in CHANNEL_SUBSIDY_TOKENS)


def has_commercial_ad_signal(*, title: str, listing_description: str | None) -> bool:
    combined_text = _combined_listing_text(title=title, listing_description=listing_description)
    strong_hits = sum(token.lower() in combined_text for token in COMMERCIAL_AD_STRONG_TOKENS)
    hint_hits = sum(token.lower() in combined_text for token in COMMERCIAL_AD_HINT_TOKENS)
    multi_variant_signal = bool(
        re.search(r"(?:42|43|47|51)\s*(?:/|\s+)\s*(?:42|43|47|51)(?:\s*(?:/|\s+)\s*(?:42|43|47|51))?\s*mm", combined_text)
    )
    many_price_points = len(re.findall(r"\b\d{4,5}\b", combined_text)) >= 3
    return (
        strong_hits >= 2
        or (strong_hits >= 1 and (hint_hits >= 1 or multi_variant_signal or many_price_points))
        or (multi_variant_signal and (hint_hits >= 1 or many_price_points))
    )


def has_non_device_signal(*, title: str, listing_description: str | None) -> bool:
    combined_text = _combined_listing_text(title=title, listing_description=listing_description)
    return any(token.lower() in combined_text for token in NON_DEVICE_TOKENS)


def is_probable_garbage_listing(*, title: str, listing_description: str | None) -> bool:
    compact_title = re.sub(r"\s+", "", title)
    if len(compact_title) < 4:
        return True
    punctuation_count = sum(1 for char in title if char in "!?！？")
    if punctuation_count >= 6:
        return True
    if listing_description and len(set(listing_description)) <= 3 and len(listing_description) >= 30:
        return True
    return False


def has_target_product_signal(*, item: dict[str, Any]) -> bool:
    business_domain = normalize_text(item.get("business_domain")) or ""
    title = (normalize_text(item.get("title")) or "").lower()
    source_keyword = (normalize_text(item.get("source_keyword")) or "").lower()
    item_brand = (normalize_text((item.get("current_values") or {}).get("item.normalized_brand")) or "").lower()
    haystack = " ".join(part for part in (title, source_keyword, item_brand) if part)
    if is_apple_computer_scope(business_domain):
        return any(token in haystack for token in ("macbook", "mac mini", "mac studio", "imac", "apple"))
    if is_garmin_watch_scope(business_domain):
        return any(token in haystack for token in ("garmin", "fenix", "epix", "forerunner", "instinct", "marq", "tactix"))
    return False


def merge_review_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return normalize_review_entries(entries)


def normalize_review_entries(raw_entries: list[Any]) -> list[dict[str, Any]]:
    ordered_item_ids: list[str] = []
    merged_entries: dict[str, dict[str, Any]] = {}
    for raw_item in raw_entries:
        if not isinstance(raw_item, dict):
            continue
        item_id = normalize_text(raw_item.get("item_id"))
        if not item_id:
            continue
        if item_id not in merged_entries:
            ordered_item_ids.append(item_id)
        entry = sanitize_review_entry(raw_item=raw_item, current_values=None)
        if entry is None:
            continue
        existing = merged_entries.get(item_id)
        if existing is None or entry["review_status"] == REVIEW_STATUS_INVALID:
            merged_entries[item_id] = entry
            continue
        if existing["review_status"] == REVIEW_STATUS_INVALID:
            continue
        merged_fields = {
            field["field_key"]: field
            for field in existing.get("not_match_field") or []
        }
        for field in entry.get("not_match_field") or []:
            merged_fields[field["field_key"]] = field
        existing["not_match_field"] = list(merged_fields.values())

    return [
        merged_entries[item_id]
        for item_id in ordered_item_ids
        if item_id in merged_entries
    ]


def sanitize_review_entry(
    *,
    raw_item: dict[str, Any],
    current_values: dict[str, Any] | None,
    minimum_confidence: float | None = None,
    enforce_confidence_gate: bool = False,
) -> dict[str, Any] | None:
    item_id = normalize_text(raw_item.get("item_id"))
    if not item_id:
        return None

    confidence = normalize_review_confidence(raw_item)
    review_input = normalize_review_input(raw_item.get("review_input"))
    review_input_signature = normalize_text(raw_item.get("review_input_signature"))
    if review_input is not None:
        normalized_signature = build_review_input_signature(review_input)
        if review_input_signature != normalized_signature:
            review_input_signature = normalized_signature

    invalid_reason = normalize_invalid_reason(
        raw_item.get("invalid_reason") or raw_item.get("invalid_type") or raw_item.get("reason")
    )
    review_status = resolve_review_status(
        review_status=raw_item.get("review_status"),
        invalid_reason=invalid_reason,
    )
    if minimum_confidence is not None:
        if confidence is None or confidence < minimum_confidence:
            return None
    if enforce_confidence_gate and not review_confidence_passes_acceptance_gate(
        review_status=review_status,
        confidence=confidence,
    ):
        return None

    if review_status == REVIEW_STATUS_INVALID:
        entry = {
            "item_id": item_id,
            "review_status": REVIEW_STATUS_INVALID,
            "invalid_reason": invalid_reason or "other",
            "not_match_field": [],
        }
        review_origin = normalize_text(raw_item.get("review_origin"))
        if review_origin:
            entry["review_origin"] = review_origin
        if confidence is not None:
            entry["confidence"] = confidence
        if review_input is not None:
            entry["review_input"] = review_input
        if review_input_signature is not None:
            entry["review_input_signature"] = review_input_signature
        return entry

    raw_fields = raw_item.get("not_match_field")
    sanitized_fields: list[dict[str, Any]] = []
    if isinstance(raw_fields, list):
        merged_fields: dict[str, dict[str, Any]] = {}
        for raw_field in raw_fields:
            if current_values is None:
                sanitized = normalize_review_field(raw_field=raw_field)
            else:
                sanitized = sanitize_field_update(raw_field=raw_field, current_values=current_values)
            if sanitized is None:
                continue
            merged_fields[sanitized["field_key"]] = sanitized
        sanitized_fields = list(merged_fields.values())

    entry = {
        "item_id": item_id,
        "review_status": REVIEW_STATUS_VALID,
        "invalid_reason": None,
        "not_match_field": sanitized_fields,
    }
    if confidence is not None:
        entry["confidence"] = confidence
    if review_input is not None:
        entry["review_input"] = review_input
    if review_input_signature is not None:
        entry["review_input_signature"] = review_input_signature
    return entry


def normalize_review_confidence(raw_item: dict[str, Any]) -> float | None:
    confidence = coerce_decimal(
        raw_item.get("confidence")
        if "confidence" in raw_item
        else raw_item.get("self_confidence")
    )
    if confidence is None:
        return None
    if confidence > 1:
        confidence /= 100
    if confidence < 0:
        return None
    return confidence


def normalize_review_input(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized = compact_prompt_mapping(value)
    if isinstance(normalized, dict):
        normalized = _strip_prompt_only_review_input_fields(normalized)
    return normalized if normalized else None


def normalize_review_field(*, raw_field: Any) -> dict[str, Any] | None:
    if not isinstance(raw_field, dict):
        return None
    field_key = normalize_text(
        raw_field.get("field_key") or raw_field.get("field") or raw_field.get("key")
    )
    if not field_key or field_key not in ALLOWED_FIELD_KEYS:
        return None
    raw_value = raw_field.get("true_value") if "true_value" in raw_field else raw_field.get("value")
    normalized_value = validate_field_value(field_key=field_key, value=raw_value)
    if normalized_value is INVALID_FIELD_VALUE:
        return None
    return {
        "field_key": field_key,
        "true_value": normalized_value,
    }


def sanitize_field_update(
    *,
    raw_field: Any,
    current_values: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(raw_field, dict):
        return None

    field_key = normalize_text(
        raw_field.get("field_key") or raw_field.get("field") or raw_field.get("key")
    )
    if not field_key or field_key not in ALLOWED_FIELD_KEYS:
        return None

    if "true_value" in raw_field:
        raw_value = raw_field.get("true_value")
    else:
        raw_value = raw_field.get("value")
    normalized_value = validate_field_value(field_key=field_key, value=raw_value)
    if normalized_value is INVALID_FIELD_VALUE:
        return None
    if normalized_value == current_values.get(field_key):
        return None

    return {
        "field_key": field_key,
        "true_value": normalized_value,
    }


def extract_json_array(text: str) -> list[Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        value = json.loads(cleaned)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for key in ("items", "results", "anomalies", "data"):
                child = value.get(key)
                if isinstance(child, list):
                    return child
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if not match:
        raise RuntimeError("LLM response does not contain a JSON array.")
    value = json.loads(match.group(0))
    if not isinstance(value, list):
        raise RuntimeError("LLM response JSON root must be an array.")
    return value
