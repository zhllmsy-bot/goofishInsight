from __future__ import annotations

import json
import re
import time
from typing import Any

from ...logging import get_logger
from ...domain.review.contracts import (
    INVALID_REASONS,
    REVIEW_STATUS_INVALID,
    REVIEW_STATUS_VALID,
    coerce_bool,
    coerce_decimal,
    normalize_invalid_reason,
    normalize_review_status,
    normalize_text,
)
from ...settings import get_settings
from ...specs import call_openai_compatible_chat, extract_message_content, llm_is_configured
from .review_batches import extract_json_array

logger = get_logger(__name__)

SUSPICIOUS_LISTING_PATTERNS = (
    re.compile(r"\u62b5\u62bc"),
    re.compile(r"(\u9ad8\u4ef7\u56de\u6536|\u73b0\u91d1\u56de\u6536|\u56de\u6536(?:\u82af\u7247|ic|\u7535\u5b50\u5143\u5668\u4ef6|\u4f73\u660e|garmin|mac|macbook|\u7535\u8111|\u7b14\u8bb0\u672c))", re.IGNORECASE),
    re.compile(r"(\u6c42\u8d2d|\u6536\u4e2a|\u6536\u4e00\u53f0|\u6162\u6536|\u4ee3\u62cd|\u4ee3\u8d2d)"),
)
INTAKE_SCREENING_VALID_CONFIDENCE = 0.90
INTAKE_SCREENING_MAX_ATTEMPTS = 2


def contains_suspicious_listing_keyword(
    *,
    title: Any,
) -> bool:
    title_text = normalize_text(title)
    if not title_text:
        return False
    return any(pattern.search(title_text) for pattern in SUSPICIOUS_LISTING_PATTERNS)


def screen_suspicious_intake_candidates(
    *,
    candidates: list[dict[str, Any]],
    batch_size: int = 12,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    if not llm_is_configured():
        return [
            {
                "item_id": candidate["item_id"],
                "is_valid": False,
                "invalid_reason": "llm_unavailable",
            }
            for candidate in candidates
        ]

    decisions: list[dict[str, Any]] = []
    safe_batch_size = max(batch_size, 1)
    for index in range(0, len(candidates), safe_batch_size):
        batch = candidates[index : index + safe_batch_size]
        batch_decision_map: dict[str, dict[str, Any]]
        try:
            response_payload = call_intake_screening_chat_with_retry(batch=batch)
            content = extract_message_content(response_payload)
            batch_decisions = sanitize_intake_screening_response(
                raw_items=extract_json_array(content),
                batch=batch,
            )
            batch_decision_map = {
                entry["item_id"]: entry
                for entry in batch_decisions
            }
        except Exception:
            logger.exception("failed to screen suspicious intake batch", extra={"batch_size": len(batch)})
            batch_decision_map = {}

        for candidate in batch:
            decisions.append(
                batch_decision_map.get(
                    candidate["item_id"],
                    {
                        "item_id": candidate["item_id"],
                        "is_valid": False,
                        "invalid_reason": "review_failed",
                    },
                )
            )
    return decisions


def call_intake_screening_chat_with_retry(*, batch: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    messages = [
        {"role": "system", "content": build_intake_screening_system_prompt()},
        {"role": "user", "content": build_intake_screening_user_prompt(batch=batch)},
    ]
    last_error: Exception | None = None
    for attempt in range(1, INTAKE_SCREENING_MAX_ATTEMPTS + 1):
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
            logger.warning(
                "intake screening llm request failed",
                extra={"attempt": attempt, "max_attempts": INTAKE_SCREENING_MAX_ATTEMPTS},
                exc_info=True,
            )
            if not is_retryable_llm_error(exc) or attempt >= INTAKE_SCREENING_MAX_ATTEMPTS:
                raise
            time.sleep(min(attempt, 2))
    raise RuntimeError("LLM intake screening request failed without an exception.") from last_error


def is_retryable_llm_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("timeout", "http 502", "http 503", "http 504", "10054"))


def build_intake_screening_system_prompt() -> str:
    invalid_reasons = ", ".join(sorted(INVALID_REASONS))
    return (
        "You gate suspicious Goofish listings before they enter the cleaned items table. "
        "Return JSON only. The root must be a JSON array. "
        "Return one result for every input item. "
        'Each result must use this shape: [{"item_id":"<id>","is_valid":true|false,"invalid_reason":"optional enum when false","confidence":0.0}]. '
        "Only return these fields. Do not echo titles, input fields, URLs, tags, or explanations. "
        "Only mark is_valid=true when you are at least 0.90 confident the listing is a genuine for-sale target product listing for the requested business domain. "
        "If the listing is a recycling or buyback post, pawn or mortgage offer, accessory sale, ad, service, electronic-parts offer, or non-target product, mark it invalid. "
        "If uncertain, mark it invalid. "
        f"Allowed invalid_reason values: {invalid_reasons}. "
        "Do not include markdown or explanations."
    )


def build_intake_screening_user_prompt(*, batch: list[dict[str, Any]]) -> str:
    serialized_items = [_serialize_intake_screening_item(item) for item in batch]
    payload = {
        "task": "Decide whether each suspicious listing should be allowed into the cleaned items table.",
        "suspicious_rule": "These listings were flagged because the title contains strong buyback/wanted/proxy-buy/pawn intent, not normal device descriptions like bundled straps or maps.",
        "validity_rule": "Only allow genuine for-sale target product listings. Reject buyback, recycling, pawn, accessory, ad, service, parts, and non-target listings.",
        "confidence_rule": "If self-confidence is below 0.90, return is_valid=false.",
        "output_rule": "Return only item_id, is_valid, invalid_reason, and confidence. Do not return input titles or other original fields.",
        "items": serialized_items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _serialize_intake_screening_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "item_id": normalize_text(item.get("item_id")),
        "business_domain": normalize_text(item.get("business_domain")),
        "source_keyword": normalize_text(item.get("source_keyword")),
        "title": normalize_text(item.get("title")),
        "current_price": item.get("current_price"),
        "condition_tags": [normalize_text(tag) for tag in list(item.get("condition_tags") or []) if normalize_text(tag)],
    }
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", [], {})
    }


def sanitize_intake_screening_response(
    *,
    raw_items: list[Any],
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    batch_ids = [normalize_text(item.get("item_id")) for item in batch]
    batch_id_set = {item_id for item_id in batch_ids if item_id}
    decisions_by_item: dict[str, dict[str, Any]] = {}

    for raw_item in raw_items:
        entry = sanitize_intake_screening_entry(raw_item=raw_item)
        if entry is None or entry["item_id"] not in batch_id_set:
            continue
        decisions_by_item[entry["item_id"]] = entry

    decisions: list[dict[str, Any]] = []
    for item_id in batch_ids:
        if not item_id:
            continue
        entry = decisions_by_item.get(item_id)
        if entry is None:
            continue
        decisions.append(entry)
    return decisions


def sanitize_intake_screening_entry(*, raw_item: Any) -> dict[str, Any] | None:
    if not isinstance(raw_item, dict):
        return None

    item_id = normalize_text(raw_item.get("item_id"))
    if not item_id:
        return None

    is_valid = normalize_intake_screening_verdict(raw_item)
    confidence = coerce_decimal(
        raw_item.get("confidence")
        if "confidence" in raw_item
        else raw_item.get("self_confidence")
    )
    if confidence is not None and confidence > 1:
        confidence /= 100
    if confidence is not None and confidence < INTAKE_SCREENING_VALID_CONFIDENCE:
        is_valid = False

    if is_valid is None:
        return None

    invalid_reason = normalize_invalid_reason(
        raw_item.get("invalid_reason") or raw_item.get("reason") or raw_item.get("invalid_type")
    )
    if not is_valid:
        return {
            "item_id": item_id,
            "is_valid": False,
            "invalid_reason": invalid_reason or "other",
        }

    return {
        "item_id": item_id,
        "is_valid": True,
        "invalid_reason": None,
    }


def normalize_intake_screening_verdict(raw_item: dict[str, Any]) -> bool | None:
    if "is_valid" in raw_item:
        verdict = coerce_bool(raw_item.get("is_valid"))
        if verdict is not None:
            return verdict

    review_status = normalize_review_status(
        raw_item.get("review_status") or raw_item.get("status")
    )
    if review_status == REVIEW_STATUS_VALID:
        return True
    if review_status == REVIEW_STATUS_INVALID:
        return False

    decision = normalize_text(raw_item.get("decision"))
    if not decision:
        return None
    normalized = decision.lower().replace("-", "_").replace(" ", "_")
    if normalized in {"valid", "allow", "approved", "keep"}:
        return True
    if normalized in {"invalid", "reject", "rejected", "block", "blocked", "skip"}:
        return False
    return None
