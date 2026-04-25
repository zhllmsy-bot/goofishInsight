from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...settings import get_settings

TRACE_LIST_LIMIT = 12
TRACE_PREVIEW_LENGTH = 160
TRACE_PAYLOAD_MAX_CHARS = 24000
RETIRED_TRACE_TOKENS = ("title_tokens", "titletoken")


def build_dashboard_llm_traces_section_data(*, limit: int = TRACE_LIST_LIMIT) -> dict[str, Any]:
    settings = get_settings()
    trace_dir = Path(settings.ai_prompt_trace_dir)
    traces = list_recent_llm_traces(trace_dir=trace_dir, limit=limit)
    latest_trace = load_dashboard_llm_trace_detail(traces[0]["trace_key"], trace_dir=trace_dir) if traces else None
    return {
        "trace_enabled": bool(settings.ai_prompt_trace_enabled),
        "trace_dir": str(trace_dir),
        "trace_count": len(traces),
        "traces": traces,
        "latest_trace": latest_trace,
    }


def list_recent_llm_traces(*, trace_dir: Path | None = None, limit: int = TRACE_LIST_LIMIT) -> list[dict[str, Any]]:
    trace_root = resolve_trace_dir(trace_dir)
    if limit <= 0 or not trace_root.exists():
        return []

    traces: list[dict[str, Any]] = []
    for path in sorted(trace_root.glob("*.json"), reverse=True):
        if trace_contains_retired_fields(path):
            continue
        traces.append(_build_trace_summary(path))
        if len(traces) >= limit:
            break
    return traces


def load_dashboard_llm_trace_detail(trace_key: str, *, trace_dir: Path | None = None) -> dict[str, Any] | None:
    path = resolve_trace_path(trace_key, trace_dir=trace_dir)
    if path is None or not path.exists():
        return None

    raw_text = path.read_text(encoding="utf-8")
    if trace_text_contains_retired_fields(raw_text):
        return None
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        generated_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
        return {
            "trace_key": path.stem,
            "file_name": path.name,
            "generated_at": generated_at,
            "provider": "-",
            "model": "-",
            "url": "-",
            "method": "-",
            "status": "broken",
            "message_count": 0,
            "messages": [],
            "request_headers_json": "",
            "request_payload_json": "",
            "response_payload_json": "",
            "raw_json": truncate_text(raw_text, TRACE_PAYLOAD_MAX_CHARS),
            "error": "Trace JSON 解析失败",
        }

    messages = [_serialize_message(index=index, message=message) for index, message in enumerate(payload.get("messages") or [])]
    
    response_payload = payload.get("responsePayload") or {}
    choices = response_payload.get("choices") or []
    reasoning_content = ""
    if choices and len(choices) > 0:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message_data = first_choice.get("message") or {}
            reasoning_content = message_data.get("reasoning_content") or ""
    
    return {
        "trace_key": path.stem,
        "file_name": path.name,
        "generated_at": payload.get("generatedAt") or datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
        "provider": payload.get("provider") or "-",
        "model": payload.get("model") or "-",
        "url": payload.get("url") or "-",
        "method": payload.get("method") or "-",
        "status": "error" if payload.get("error") else "success",
        "message_count": len(messages),
        "messages": messages,
        "request_headers_json": to_pretty_json(payload.get("requestHeaders")),
        "request_payload_json": to_pretty_json(payload.get("requestPayload")),
        "response_payload_json": to_pretty_json(payload.get("responsePayload")),
        "raw_json": truncate_text(raw_text, TRACE_PAYLOAD_MAX_CHARS),
        "error": payload.get("error"),
        "latency_ms": payload.get("latencyMs"),
        "item_id": payload.get("itemId"),
        "usage": payload.get("usage"),
        "reasoning_content": reasoning_content,
    }


def resolve_trace_dir(trace_dir: Path | None = None) -> Path:
    if trace_dir is not None:
        return Path(trace_dir)
    return Path(get_settings().ai_prompt_trace_dir)


def resolve_trace_path(trace_key: str, *, trace_dir: Path | None = None) -> Path | None:
    normalized_key = (trace_key or "").strip()
    if not normalized_key or "/" in normalized_key or "\\" in normalized_key or normalized_key.startswith("."):
        return None

    root = resolve_trace_dir(trace_dir).resolve()
    candidate = (root / f"{normalized_key}.json").resolve()
    if candidate.parent != root:
        return None
    return candidate


def _build_trace_summary(path: Path) -> dict[str, Any]:
    generated_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
    provider = "-"
    model = "-"
    method = "-"
    url = "-"
    error = None
    status = "success"
    latency_ms = None
    item_id = None
    usage = None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        status = "broken"
        error = "Trace JSON 解析失败"
    else:
        generated_at = payload.get("generatedAt") or generated_at
        provider = payload.get("provider") or provider
        model = payload.get("model") or model
        method = payload.get("method") or method
        url = payload.get("url") or url
        error = payload.get("error")
        status = "error" if error else "success"
        latency_ms = payload.get("latencyMs")
        item_id = payload.get("itemId")
        usage = payload.get("usage")

    return {
        "trace_key": path.stem,
        "file_name": path.name,
        "generated_at": generated_at,
        "provider": provider,
        "model": model,
        "method": method,
        "url": url,
        "status": status,
        "error": error,
        "latency_ms": latency_ms,
        "item_id": item_id,
        "usage": usage,
    }


def trace_contains_retired_fields(path: Path) -> bool:
    try:
        return trace_text_contains_retired_fields(path.read_text(encoding="utf-8"))
    except OSError:
        return False


def trace_text_contains_retired_fields(raw_text: str) -> bool:
    normalized = raw_text.lower()
    return any(token in normalized for token in RETIRED_TRACE_TOKENS)


def summarize_messages(messages: list[dict[str, Any]]) -> tuple[str, str]:
    system_texts: list[str] = []
    user_texts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "")
        content_text = message_content_to_text(message.get("content"))
        if not content_text:
            continue
        if role == "system":
            system_texts.append(content_text)
        elif role == "user":
            user_texts.append(content_text)
    return truncate_text(" ".join(system_texts), TRACE_PREVIEW_LENGTH), truncate_text(" ".join(user_texts), TRACE_PREVIEW_LENGTH)


def _serialize_message(*, index: int, message: dict[str, Any]) -> dict[str, Any]:
    content_text = message_content_to_text(message.get("content"))
    return {
        "index": index + 1,
        "role": message.get("role") or "unknown",
        "content_text": content_text,
        "content_preview": truncate_text(content_text, TRACE_PREVIEW_LENGTH),
    }


def message_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            text = message_content_to_text(part)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        content_type = str(content.get("type") or "").strip()
        text_value = content.get("text")
        if isinstance(text_value, str) and text_value.strip():
            prefix = f"[{content_type}] " if content_type and content_type != "text" else ""
            return f"{prefix}{text_value.strip()}".strip()
        image_url = content.get("image_url") or content.get("image")
        if image_url:
            return f"[{content_type or 'image'}] {image_url}"
        return json.dumps(content, ensure_ascii=False, indent=2)
    return str(content).strip()


def truncate_text(value: str | None, max_chars: int) -> str:
    normalized = " ".join((value or "").split())
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= 1:
        return normalized[:max_chars]
    return f"{normalized[: max_chars - 1]}…"


def to_pretty_json(value: Any) -> str:
    if value is None:
        return ""
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) <= TRACE_PAYLOAD_MAX_CHARS:
        return text
    return f"{text[:TRACE_PAYLOAD_MAX_CHARS]}\n... [truncated]"
