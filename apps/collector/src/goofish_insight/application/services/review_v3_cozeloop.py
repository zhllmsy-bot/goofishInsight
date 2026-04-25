from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
import time
from typing import Any, Iterable, Literal

from ...settings import get_settings
from .review_v3_profiles import (
    ReviewV3Profile,
    build_first_pass_system_prompt,
    build_second_pass_system_prompt,
    render_json_user_prompt,
)

ReviewV3Phase = Literal["first_pass", "second_pass"]


@dataclass(frozen=True)
class ReviewV3PromptSpec:
    phase: ReviewV3Phase
    prompt_key: str
    prompt_name: str
    prompt_description: str
    prompt_detail: dict[str, Any]


@dataclass(frozen=True)
class CozeloopExecutionResult:
    content: str
    usage: dict[str, int] | None
    provider: str
    model: str
    raw_payload: dict[str, Any]


def _cozeloop_phase_model_id(phase: ReviewV3Phase) -> str:
    settings = get_settings()
    if phase == "first_pass":
        model_id = settings.cozeloop_first_pass_model_id or settings.cozeloop_model_id
    else:
        model_id = settings.cozeloop_second_pass_model_id or settings.cozeloop_model_id
    return str(model_id)


def _cozeloop_phase_model_name(phase: ReviewV3Phase) -> str:
    settings = get_settings()
    if phase == "first_pass":
        return str(settings.cozeloop_first_pass_model_name or settings.ai_model or settings.cozeloop_model_id).strip()
    return str(settings.cozeloop_second_pass_model_name or settings.ai_model or settings.cozeloop_model_id).strip()


def _cozeloop_json_request(
    *,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    bearer_token: str | None = None,
    session_key: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    url = settings.cozeloop_base_url.rstrip("/") + path
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method=method.upper())
    request.add_header("Content-Type", "application/json")
    if bearer_token:
        request.add_header("Authorization", f"Bearer {bearer_token}")
    if session_key:
        request.add_header("Cookie", f"session_key={session_key}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cozeloop request failed: {method} {path} -> HTTP {exc.code}: {raw}") from exc
    try:
        payload_dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Cozeloop response is not JSON for {method} {path}: {raw}") from exc
    return payload_dict


def cozeloop_is_configured() -> bool:
    settings = get_settings()
    return bool(settings.cozeloop_base_url and settings.cozeloop_workspace_id and settings.cozeloop_pat)


def build_review_v3_cozeloop_prompt_key(profile: ReviewV3Profile, phase: ReviewV3Phase) -> str:
    prefix = str(get_settings().cozeloop_prompt_key_prefix or "goofish-review-v3").strip() or "goofish-review-v3"
    return f"{prefix}-{phase}-{profile.business_domain}"


def build_review_v3_cozeloop_prompt_name(profile: ReviewV3Profile, phase: ReviewV3Phase) -> str:
    stage_label = "First Pass" if phase == "first_pass" else "Second Pass"
    return f"Goofish Review V3 {stage_label} {profile.business_domain}"


def build_review_v3_cozeloop_prompt_description(profile: ReviewV3Profile, phase: ReviewV3Phase) -> str:
    if phase == "first_pass":
        return f"Flat factual extraction prompt for {profile.business_domain}."
    return f"Candidate-resolution prompt for {profile.business_domain}."


def build_review_v3_cozeloop_prompt_detail(profile: ReviewV3Profile, phase: ReviewV3Phase) -> dict[str, Any]:
    settings = get_settings()
    system_prompt = (
        build_first_pass_system_prompt(profile)
        if phase == "first_pass"
        else build_second_pass_system_prompt(profile)
    )
    max_tokens = 700 if phase == "first_pass" else 1000
    return {
        "prompt_template": {
            "template_type": "jinja2",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "{{ payload_json }}"},
            ],
            "variable_defs": [
                {"key": "payload_json", "desc": "Rendered JSON task payload.", "type": "string"},
            ],
        },
        "model_config": {
            "model_id": _cozeloop_phase_model_id(phase),
            "temperature": 0.0,
            "max_tokens": max_tokens,
            # Keep json_mode off for Ark coding/v3 compatibility; we enforce JSON via prompt contract.
            "json_mode": False,
            "thinking": {
                "thinking_option": "disabled",
                "reasoning_effort": "minimal",
            },
        },
    }


def build_review_v3_cozeloop_prompt_spec(profile: ReviewV3Profile, phase: ReviewV3Phase) -> ReviewV3PromptSpec:
    return ReviewV3PromptSpec(
        phase=phase,
        prompt_key=build_review_v3_cozeloop_prompt_key(profile, phase),
        prompt_name=build_review_v3_cozeloop_prompt_name(profile, phase),
        prompt_description=build_review_v3_cozeloop_prompt_description(profile, phase),
        prompt_detail=build_review_v3_cozeloop_prompt_detail(profile, phase),
    )


def list_internal_prompts(*, keyword: str | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.cozeloop_session_key:
        raise RuntimeError("COZELOOP_SESSION_KEY is required for prompt sync.")
    body = {
        "workspace_id": settings.cozeloop_workspace_id,
        "page_num": 1,
        "page_size": 50,
    }
    if keyword:
        body["key_word"] = keyword
    payload = _cozeloop_json_request(
        method="POST",
        path="/api/prompt/v1/prompts/list",
        body=body,
        session_key=settings.cozeloop_session_key,
    )
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(f"Cozeloop list prompts failed: {payload}")
    return list(payload.get("prompts") or [])


def find_internal_prompt_by_key(prompt_key: str) -> dict[str, Any] | None:
    for prompt in list_internal_prompts(keyword=prompt_key):
        if str(prompt.get("prompt_key") or "") == prompt_key:
            return prompt
    return None


def get_internal_prompt(prompt_id: str) -> dict[str, Any]:
    settings = get_settings()
    payload = _cozeloop_json_request(
        method="GET",
        path=(
            f"/api/prompt/v1/prompts/{urllib.parse.quote(prompt_id)}"
            f"?workspace_id={urllib.parse.quote(str(settings.cozeloop_workspace_id))}"
            "&with_commit=true&with_draft=true"
        ),
        session_key=settings.cozeloop_session_key,
    )
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(f"Cozeloop get prompt failed: {payload}")
    prompt = payload.get("prompt")
    if not isinstance(prompt, dict):
        raise RuntimeError(f"Cozeloop get prompt returned invalid prompt payload: {payload}")
    return prompt


def _managed_prompt_detail_snapshot(detail: dict[str, Any] | None) -> dict[str, Any]:
    detail = dict(detail or {})
    prompt_template = dict(detail.get("prompt_template") or {})
    model_config = dict(detail.get("model_config") or {})
    return {
        "prompt_template": {
            "template_type": prompt_template.get("template_type"),
            "messages": list(prompt_template.get("messages") or []),
            "variable_defs": list(prompt_template.get("variable_defs") or []),
        },
        "model_config": {
            "model_id": str(model_config.get("model_id") or ""),
            "temperature": model_config.get("temperature"),
            "max_tokens": model_config.get("max_tokens"),
            "json_mode": bool(model_config.get("json_mode")),
            "thinking": {
                "thinking_option": str(dict(model_config.get("thinking") or {}).get("thinking_option") or ""),
                "reasoning_effort": str(dict(model_config.get("thinking") or {}).get("reasoning_effort") or ""),
            },
        },
    }


def resolve_current_prompt_detail(prompt: dict[str, Any]) -> dict[str, Any]:
    prompt_draft = dict(prompt.get("prompt_draft") or {})
    prompt_commit = dict(prompt.get("prompt_commit") or {})
    draft_detail = prompt_draft.get("detail")
    if isinstance(draft_detail, dict) and draft_detail:
        return draft_detail
    commit_detail = prompt_commit.get("detail")
    if isinstance(commit_detail, dict):
        return commit_detail
    return {}


def resolve_current_prompt_version(prompt: dict[str, Any]) -> str | None:
    prompt_draft = dict(prompt.get("prompt_draft") or {})
    prompt_commit = dict(prompt.get("prompt_commit") or {})
    draft_info = dict(prompt_draft.get("draft_info") or {})
    commit_info = dict(prompt_commit.get("commit_info") or {})
    for candidate in (
        draft_info.get("base_version"),
        commit_info.get("version"),
    ):
        if candidate:
            return str(candidate)
    return None


def create_internal_prompt(spec: ReviewV3PromptSpec) -> str:
    settings = get_settings()
    payload = _cozeloop_json_request(
        method="POST",
        path="/api/prompt/v1/prompts",
        body={
            "workspace_id": settings.cozeloop_workspace_id,
            "prompt_name": spec.prompt_name,
            "prompt_key": spec.prompt_key,
            "prompt_description": spec.prompt_description,
            "prompt_type": "normal",
            "draft_detail": spec.prompt_detail,
        },
        session_key=settings.cozeloop_session_key,
    )
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(f"Cozeloop create prompt failed: {payload}")
    prompt_id = str(payload.get("prompt_id") or "").strip()
    if not prompt_id:
        raise RuntimeError(f"Cozeloop create prompt returned empty prompt_id: {payload}")
    return prompt_id


def save_internal_prompt_draft(*, prompt_id: str, prompt_detail: dict[str, Any]) -> None:
    payload = _cozeloop_json_request(
        method="POST",
        path=f"/api/prompt/v1/prompts/{urllib.parse.quote(prompt_id)}/drafts/save",
        body={
            "prompt_id": prompt_id,
            "prompt_draft": {
                "detail": prompt_detail,
                "draft_info": {},
            },
        },
        session_key=get_settings().cozeloop_session_key,
    )
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(f"Cozeloop save draft failed: {payload}")


def commit_internal_prompt(*, prompt_id: str, description: str) -> str:
    version = f"1.0.{time.time_ns()}"
    payload = _cozeloop_json_request(
        method="POST",
        path=f"/api/prompt/v1/prompts/{urllib.parse.quote(prompt_id)}/drafts/commit",
        body={
            "workspace_id": get_settings().cozeloop_workspace_id,
            "commit_version": version,
            "commit_description": description,
        },
        session_key=get_settings().cozeloop_session_key,
    )
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(f"Cozeloop commit prompt failed: {payload}")
    return version


def sync_review_v3_cozeloop_prompts(*, profiles: Iterable[ReviewV3Profile], phases: Iterable[ReviewV3Phase]) -> list[dict[str, Any]]:
    if not get_settings().cozeloop_session_key:
        raise RuntimeError("COZELOOP_SESSION_KEY is required for CozeLoop prompt sync.")
    results: list[dict[str, Any]] = []
    for profile in profiles:
        for phase in phases:
            spec = build_review_v3_cozeloop_prompt_spec(profile, phase)
            existing = find_internal_prompt_by_key(spec.prompt_key)
            if existing is None:
                prompt_id = create_internal_prompt(spec)
                action = "created"
                version = commit_internal_prompt(prompt_id=prompt_id, description=f"sync {spec.phase}")
            else:
                prompt_id = str(existing.get("id") or "").strip()
                if not prompt_id:
                    raise RuntimeError(f"Existing CozeLoop prompt is missing id: {existing}")
                current_prompt = get_internal_prompt(prompt_id)
                current_detail = resolve_current_prompt_detail(current_prompt)
                if _managed_prompt_detail_snapshot(current_detail) == _managed_prompt_detail_snapshot(spec.prompt_detail):
                    action = "unchanged"
                    version = resolve_current_prompt_version(current_prompt)
                else:
                    save_internal_prompt_draft(prompt_id=prompt_id, prompt_detail=spec.prompt_detail)
                    action = "updated"
                    version = commit_internal_prompt(prompt_id=prompt_id, description=f"sync {spec.phase}")
            results.append(
                {
                    "business_domain": profile.business_domain,
                    "phase": phase,
                    "prompt_id": prompt_id,
                    "prompt_key": spec.prompt_key,
                    "action": action,
                    "version": version,
                }
            )
    return results


def execute_review_v3_prompt_via_cozeloop(
    *,
    profile: ReviewV3Profile,
    phase: ReviewV3Phase,
    user_payload: dict[str, Any],
) -> CozeloopExecutionResult:
    settings = get_settings()
    if not cozeloop_is_configured():
        raise RuntimeError("Cozeloop executor is not configured.")
    prompt_key = build_review_v3_cozeloop_prompt_key(profile, phase)
    payload = _cozeloop_json_request(
        method="POST",
        path="/v1/loop/prompts/execute",
        body={
            "workspace_id": settings.cozeloop_workspace_id,
            "prompt_identifier": {"prompt_key": prompt_key},
            "variable_vals": [
                {"key": "payload_json", "value": render_json_user_prompt(user_payload)},
            ],
        },
        bearer_token=settings.cozeloop_pat,
    )
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(f"Cozeloop execute failed: {payload.get('msg') or payload}")
    data = dict(payload.get("data") or {})
    message = dict(data.get("message") or {})
    usage_payload = dict(data.get("usage") or {})
    usage = None
    if usage_payload:
        input_tokens = int(usage_payload.get("input_tokens") or 0)
        output_tokens = int(usage_payload.get("output_tokens") or 0)
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    return CozeloopExecutionResult(
        content=str(message.get("content") or ""),
        usage=usage,
        provider="cozeloop",
        model=_cozeloop_phase_model_name(phase),
        raw_payload=payload,
    )
