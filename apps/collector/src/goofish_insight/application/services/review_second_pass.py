from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from ...domain.review.contracts import (
    INVALID_REASONS,
    REVIEW_STATUS_INVALID,
    build_field_contract_lines,
    normalize_invalid_reason,
)
from ...domain.review.policy import review_confidence_passes_acceptance_gate, review_decision_strength
from ...settings import get_settings
from ...specs import call_openai_compatible_chat, extract_message_content, extract_usage_stats, llm_is_configured
from .review_batches import (
    LLM_REVIEW_MAX_ATTEMPTS,
    build_review_audit_snapshot,
    build_preclassified_review_entries,
    build_review_input_signature,
    build_review_input_snapshot,
    build_review_system_prompt,
    build_review_user_prompt,
    compact_prompt_mapping,
    extract_json_array,
    is_retryable_llm_error,
    merge_review_entries,
    sanitize_review_entry,
)


@dataclass(slots=True)
class ReviewPassTrace:
    pass_name: str
    raw_items: list[Any]
    candidate: dict[str, Any] | None
    llm_usage: dict[str, int] | None
    llm_request_count: int
    error: str | None = None


@dataclass(slots=True)
class SecondPassBatchReviewResult:
    item_id: str
    batch_size: int
    review_count: int
    entries: list[dict[str, Any]]
    llm_request_count: int
    llm_usage: dict[str, int] | None
    garbage_hit_count: int
    low_confidence_filtered_count: int
    high_confidence_kept_count: int
    second_pass_requested_count: int
    second_pass_rescued_count: int
    second_pass_unresolved_count: int
    unresolved_details: list[dict[str, Any]]


SECOND_PASS_LOCAL_AI_DEFAULTS = {
    "AI_PROVIDER": "openai_compatible",
    "AI_BASE_URL": "http://127.0.0.1:8000/v1",
    "AI_API_KEY": "local-dev",
    "AI_MODEL": os.environ.get("QWEN3_MODEL_PATH", "Qwen3-30B-A3B-MLX-4bit"),
}

SECOND_PASS_EXPLICIT_AI_KEYS = (
    "AI_PROVIDER",
    "AI_BASE_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "ARK_AI_PROVIDER",
    "ARK_AI_BASE_URL",
    "ARK_AI_API_KEY",
    "ARK_AI_MODEL",
)


def apply_second_pass_local_ai_defaults(*, configured_settings: Any | None = None) -> bool:
    settings = configured_settings or get_settings()
    if settings.ai_base_url and settings.ai_model:
        return False

    if any(key in os.environ for key in SECOND_PASS_EXPLICIT_AI_KEYS):
        return False

    changed = False
    for key, value in SECOND_PASS_LOCAL_AI_DEFAULTS.items():
        if os.environ.get(key) == value:
            continue
        os.environ[key] = value
        changed = True
    return changed


async def run_second_pass_item_review_batches(
    *,
    items: list[dict[str, Any]],
    concurrency: int,
) -> list[SecondPassBatchReviewResult]:
    if not llm_is_configured():
        raise RuntimeError("LLM review is not configured.")

    semaphore = asyncio.Semaphore(max(concurrency, 1))

    async def run_item(item: dict[str, Any]) -> SecondPassBatchReviewResult:
        async with semaphore:
            return await asyncio.to_thread(review_item_with_second_pass, item=item)

    return await asyncio.gather(*(run_item(item) for item in items))


def review_item_with_second_pass(*, item: dict[str, Any]) -> SecondPassBatchReviewResult:
    preclassified_entries, remaining_batch = build_preclassified_review_entries(batch=[item])
    if preclassified_entries:
        entries = merge_review_entries(preclassified_entries)
        garbage_hit_count = sum(
            1 for entry in entries if normalize_invalid_reason(entry.get("invalid_reason")) == "garbage"
        )
        return SecondPassBatchReviewResult(
            item_id=item["item_id"],
            batch_size=1,
            review_count=len(entries),
            entries=entries,
            llm_request_count=0,
            llm_usage=None,
            garbage_hit_count=garbage_hit_count,
            low_confidence_filtered_count=0,
            high_confidence_kept_count=len(entries),
            second_pass_requested_count=0,
            second_pass_rescued_count=0,
            second_pass_unresolved_count=0,
            unresolved_details=[],
        )

    review_item = remaining_batch[0]
    first_pass = execute_review_pass(
        item=review_item,
        pass_name="first_pass",
        system_prompt=build_review_system_prompt(),
        user_prompt=build_review_user_prompt(batch=[review_item]),
    )
    if is_high_confidence(first_pass.candidate):
        final_entries = merge_review_entries([first_pass.candidate])
        return SecondPassBatchReviewResult(
            item_id=item["item_id"],
            batch_size=1,
            review_count=len(final_entries),
            entries=final_entries,
            llm_request_count=first_pass.llm_request_count,
            llm_usage=first_pass.llm_usage,
            garbage_hit_count=count_garbage_hits(final_entries),
            low_confidence_filtered_count=0,
            high_confidence_kept_count=len(final_entries),
            second_pass_requested_count=0,
            second_pass_rescued_count=0,
            second_pass_unresolved_count=0,
            unresolved_details=[],
        )

    second_pass = execute_review_pass(
        item=review_item,
        pass_name="second_pass",
        system_prompt=build_second_pass_system_prompt(),
        user_prompt=build_second_pass_user_prompt(item=review_item, first_pass_candidate=first_pass.candidate),
    )
    total_usage = merge_usage_dicts(first_pass.llm_usage, second_pass.llm_usage)
    total_request_count = first_pass.llm_request_count + second_pass.llm_request_count
    if is_high_confidence(second_pass.candidate):
        final_entries = merge_review_entries([second_pass.candidate])
        return SecondPassBatchReviewResult(
            item_id=item["item_id"],
            batch_size=1,
            review_count=len(final_entries),
            entries=final_entries,
            llm_request_count=total_request_count,
            llm_usage=total_usage,
            garbage_hit_count=count_garbage_hits(final_entries),
            low_confidence_filtered_count=0,
            high_confidence_kept_count=len(final_entries),
            second_pass_requested_count=1,
            second_pass_rescued_count=1,
            second_pass_unresolved_count=0,
            unresolved_details=[],
        )

    return SecondPassBatchReviewResult(
        item_id=item["item_id"],
        batch_size=1,
        review_count=0,
        entries=[],
        llm_request_count=total_request_count,
        llm_usage=total_usage,
        garbage_hit_count=0,
        low_confidence_filtered_count=1,
        high_confidence_kept_count=0,
        second_pass_requested_count=1,
        second_pass_rescued_count=0,
        second_pass_unresolved_count=1,
        unresolved_details=[build_unresolved_detail(item=item, first_pass=first_pass, second_pass=second_pass)],
    )


def execute_review_pass(
    *,
    item: dict[str, Any],
    pass_name: str,
    system_prompt: str,
    user_prompt: str,
) -> ReviewPassTrace:
    try:
        payload = call_review_pass_with_retry(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
    except Exception as exc:
        return ReviewPassTrace(
            pass_name=pass_name,
            raw_items=[],
            candidate=None,
            llm_usage=None,
            llm_request_count=1,
            error=str(exc),
        )

    usage = extract_usage_stats(payload)
    content = extract_message_content(payload)
    raw_items = extract_second_pass_json_items(content)
    candidate = select_best_candidate(item=item, raw_items=raw_items)
    return ReviewPassTrace(
        pass_name=pass_name,
        raw_items=raw_items,
        candidate=candidate,
        llm_usage=usage,
        llm_request_count=1,
        error=None,
    )


def call_review_pass_with_retry(*, messages: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
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
    raise RuntimeError("Second-pass LLM review request failed without an exception.") from last_error


def build_second_pass_system_prompt() -> str:
    allowed = ", ".join(build_field_contract_lines())
    invalid_reason_enum = "|".join(sorted(INVALID_REASONS))
    return (
        "You are running a second-pass reliability review for a single Goofish listing. "
        "Return JSON only. Return exactly one output object inside a one-element JSON array for the one input item. "
        'The output object must match {"item_id":"<id>","review_status":"valid|invalid","confidence":0.0,"invalid_reason":"' + invalid_reason_enum + '","not_match_field":[{"field_key":"<allowed field>","true_value":<json value>}]} '
        "Only return these fields. Do not echo titles, descriptions, tags, first-pass hints, input values, or explanations. "
        "item_id is locked. Copy it exactly from the input item and nowhere else. "
        "Every returned object must include the confidence field as a numeric value. Do not omit required fields. "
        'For valid items, invalid_reason must be "" and not_match_field may be []. '
        "For invalid items, not_match_field must be []. "
        "confidence estimates the probability that the listing is a real target-device sale listing. "
        "Goal: maximize downstream pricing reliability. Prefer a high-confidence valid decision only when the text clearly describes a real target-device sale listing with concrete device evidence. "
        "Prefer a low-confidence invalid decision only when the listing is clearly buying, recycling, service flow, commercial ad, accessory, parts, non-target, or otherwise not a real target-device sale listing. "
        "Normal second-hand phrasing like self-pickup, negotiable price, more photos in chat, or missing box does not by itself make a listing invalid. "
        "Commercial or channel-style bulk sales copy with multiple versions, repeated price menus, nationwide shipping, promotions, exchange and trade-in marketing, or service workflow should be invalid. "
        "Confidence rubric: 0.95-1.00 means explicit valid sale listing. "
        "0.70-0.94 means likely valid sale listing with some ambiguity. "
        "0.31-0.69 means mixed evidence and too risky for downstream pricing. "
        "0.00-0.30 means clearly invalid or not a real target-device sale listing. "
        "Use confidence decisively: if the listing is obviously valid or obviously invalid, do not stay vague. If evidence is still genuinely mixed, return your best judgment with honest confidence. "
        f"Allowed field_key/type: {allowed}."
    )


def build_second_pass_user_prompt(*, item: dict[str, Any], first_pass_candidate: dict[str, Any] | None) -> str:
    first_pass_hint = None
    if first_pass_candidate is not None:
        first_pass_hint = compact_prompt_mapping(
            {
                "review_status": first_pass_candidate.get("review_status"),
                "confidence": first_pass_candidate.get("confidence"),
                "invalid_reason": first_pass_candidate.get("invalid_reason"),
            }
        )
    payload = compact_prompt_mapping(
        {
            "task": "second_pass_reliability_review",
            "instruction": "Re-evaluate this single item because the first pass did not pass the confidence gate. Use the first-pass hint only as a weak hint, not as a final answer.",
            "item_id_rule": "return exactly one object for this one item and copy item_id exactly",
            "output_rule": "Return only item_id, review_status, confidence, invalid_reason, and not_match_field. Do not echo original input fields.",
            "item": build_review_input_snapshot(item),
            "first_pass_hint": first_pass_hint,
        }
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def extract_second_pass_json_items(text: str) -> list[Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = extract_json_array(text)
    except Exception:
        parsed = None
    else:
        if parsed or cleaned.startswith("["):
            return parsed

    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return [value]
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return []
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [value] if isinstance(value, dict) else []


def select_best_candidate(*, item: dict[str, Any], raw_items: list[Any]) -> dict[str, Any] | None:
    review_input = build_review_audit_snapshot(item)
    review_input_signature = build_review_input_signature(review_input)
    current_values = dict(item.get("current_values") or {})
    candidates: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        candidate_payload = dict(raw_item)
        candidate_payload["item_id"] = item["item_id"]
        entry = sanitize_review_entry(
            raw_item=candidate_payload,
            current_values=current_values,
            minimum_confidence=None,
        )
        if entry is None:
            continue
        entry["review_input"] = review_input
        entry["review_input_signature"] = review_input_signature
        candidates.append(entry)

    if not candidates:
        return None

    def sort_key(entry: dict[str, Any]) -> tuple[float, int, int]:
        confidence = review_decision_strength(
            review_status=entry.get("review_status"),
            confidence=entry.get("confidence"),
        )
        invalid_priority = 1 if entry.get("review_status") == REVIEW_STATUS_INVALID else 0
        field_count = len(entry.get("not_match_field") or [])
        return (confidence, invalid_priority, field_count)

    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]


def is_high_confidence(entry: dict[str, Any] | None) -> bool:
    if not entry:
        return False
    confidence = entry.get("confidence")
    if not isinstance(confidence, (int, float)):
        return False
    return review_confidence_passes_acceptance_gate(
        review_status=entry.get("review_status"),
        confidence=float(confidence),
    )


def count_garbage_hits(entries: list[dict[str, Any]]) -> int:
    return sum(1 for entry in entries if normalize_invalid_reason(entry.get("invalid_reason")) == "garbage")


def merge_usage_dicts(*usages: dict[str, int] | None) -> dict[str, int] | None:
    total = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
    }
    has_usage = False
    for usage in usages:
        if not usage:
            continue
        has_usage = True
        for key in total:
            total[key] += int(usage.get(key) or 0)
    return total if has_usage else None


def build_unresolved_detail(
    *,
    item: dict[str, Any],
    first_pass: ReviewPassTrace,
    second_pass: ReviewPassTrace,
) -> dict[str, Any]:
    return {
        "item_id": item["item_id"],
        "business_domain": item.get("business_domain"),
        "title": item.get("title"),
        "current_price": item.get("current_price"),
        "source_keyword": item.get("source_keyword"),
        "region": item.get("region"),
        "final_disposition": "unresolved_low_confidence",
        "first_pass": summarize_trace(first_pass),
        "second_pass": summarize_trace(second_pass),
    }


def summarize_trace(trace: ReviewPassTrace) -> dict[str, Any]:
    candidate = trace.candidate or {}
    return {
        "pass_name": trace.pass_name,
        "candidate": compact_prompt_mapping(
            {
                "review_status": candidate.get("review_status"),
                "confidence": candidate.get("confidence"),
                "invalid_reason": candidate.get("invalid_reason"),
                "not_match_field": candidate.get("not_match_field"),
            }
        ),
        "raw_item_count": len(trace.raw_items),
        "llm_usage": trace.llm_usage,
        "error": trace.error,
    }
