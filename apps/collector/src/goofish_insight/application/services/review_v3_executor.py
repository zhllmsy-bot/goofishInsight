from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Literal

from ...settings import get_settings
from ...specs import call_openai_compatible_chat, extract_message_content, extract_usage_stats, llm_is_configured
from .review_v3_cozeloop import cozeloop_is_configured, execute_review_v3_prompt_via_cozeloop
from .review_v3_profiles import (
    ReviewV3Profile,
    build_first_pass_system_prompt,
    build_second_pass_system_prompt,
    render_json_user_prompt,
)

ReviewV3Phase = Literal["first_pass", "second_pass"]
DIRECT_RETRYABLE_ATTEMPTS = 4
DIRECT_RETRY_SLEEP_SECONDS = 1.0
DIRECT_429_RETRY_SLEEP_SECONDS = 3.0
DIRECT_RETRY_MAX_SLEEP_SECONDS = 20.0


@dataclass(frozen=True)
class ReviewV3ExecutionResult:
    content: str
    usage: dict[str, int] | None
    provider: str
    model: str
    raw_payload: dict[str, Any]


def review_v3_executor_name() -> str:
    executor = str(get_settings().review_v3_executor or "direct").strip().lower()
    return executor or "direct"


def review_v3_executor_is_configured() -> bool:
    executor = review_v3_executor_name()
    if executor == "cozeloop":
        return cozeloop_is_configured()
    if executor == "direct":
        return llm_is_configured()
    return False


def _is_retryable_direct_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if not isinstance(exc, RuntimeError):
        return False
    message = str(exc)
    retryable_tokens = (
        "HTTP 429",
        "RequestBurstTooFast",
        "rate limit",
        "too many requests",
        "temporarily unavailable",
    )
    return any(token.lower() in message.lower() for token in retryable_tokens)


def _direct_retry_sleep_seconds(exc: BaseException, attempt: int) -> float:
    base_sleep = (
        DIRECT_429_RETRY_SLEEP_SECONDS
        if isinstance(exc, RuntimeError) and "429" in str(exc)
        else DIRECT_RETRY_SLEEP_SECONDS
    )
    sleep_seconds = min(base_sleep * (2**attempt), DIRECT_RETRY_MAX_SLEEP_SECONDS)
    jitter = random.uniform(0.0, 0.75)
    return sleep_seconds + jitter


def execute_review_v3_prompt(
    *,
    profile: ReviewV3Profile,
    phase: ReviewV3Phase,
    user_payload: dict[str, Any],
    system_prompt_override: str | None = None,
) -> ReviewV3ExecutionResult:
    executor = review_v3_executor_name()
    if executor == "cozeloop":
        return execute_review_v3_prompt_via_cozeloop(
            profile=profile,
            phase=phase,
            user_payload=user_payload,
        )
    if executor != "direct":
        raise RuntimeError(f"Unsupported REVIEW_V3_EXECUTOR: {executor}")

    settings = get_settings()
    is_first_pass_batch = phase == "first_pass" and str(user_payload.get("task") or "").strip() == "first_pass_feature_extraction_batch"
    system_prompt = system_prompt_override or (
        build_first_pass_system_prompt(profile)
        if phase == "first_pass"
        else build_second_pass_system_prompt(profile)
    )
    payload = None
    last_error: BaseException | None = None
    for attempt in range(DIRECT_RETRYABLE_ATTEMPTS):
        try:
            response_format = None
            if "ark.cn-" not in (settings.ai_base_url or "").lower():
                response_format = {"type": "json_object"}
            max_tokens = (
                settings.review_v3_batch_ai_max_tokens
                if is_first_pass_batch
                else settings.review_v3_ai_max_tokens
            )
            payload = call_openai_compatible_chat(
                base_url=settings.ai_base_url,
                api_key=settings.ai_api_key,
                model=settings.ai_model,
                timeout_sec=settings.ai_timeout_sec,
                enable_thinking=settings.ai_enable_thinking,
                max_tokens=max_tokens,
                response_format=response_format,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": render_json_user_prompt(user_payload)},
                ],
            )
            break
        except (TimeoutError, RuntimeError) as exc:
            last_error = exc
            if not _is_retryable_direct_error(exc) or attempt >= DIRECT_RETRYABLE_ATTEMPTS - 1:
                raise
            time.sleep(_direct_retry_sleep_seconds(exc, attempt))
    if payload is None:
        raise last_error or RuntimeError("direct review_v3 prompt execution returned no payload")
    return ReviewV3ExecutionResult(
        content=extract_message_content(payload),
        usage=extract_usage_stats(payload),
        provider=settings.ai_provider,
        model=settings.ai_model,
        raw_payload=payload,
    )
