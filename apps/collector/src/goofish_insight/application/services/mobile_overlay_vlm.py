from __future__ import annotations

import json
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Any, Callable

import httpx

from ...settings import get_settings

SUPPORTED_OVERLAY_DOMAINS = {"garmin", "apple_m_series"}
SYSTEM_PROMPT = """
你是二手商品截图识别助手。你的任务是根据截图和 OCR 信息，识别商品品牌、型号和规格，
给后续价格匹配提供稳定线索。请只输出 JSON，不要输出 Markdown，不要输出额外解释。

输出格式：
{
  "title_candidate": "优先保留品牌+型号的精简标题，不确定则 null",
  "brand_hint": "品牌，不确定则 null",
  "business_domain_hint": "garmin | apple_m_series | null",
  "model_hint": "型号或系列，不确定则 null",
  "spec_hint": "容量/尺寸/芯片/配色等规格，不确定则 null",
  "price_hint": "截图里最像商品当前售价的原始价格文本，不确定则 null",
  "confidence": 0.0,
  "reason": "一句话说明你为什么这么判断"
}

要求：
1. 不要把“闲鱼、首页、消息、发布、鱼塘、分享”等界面词当成商品标题。
2. 优先识别商品本身，尤其是型号、尺寸、芯片、容量、Solar 等关键字。
3. 如果证据不足，字段填 null，confidence 降低。
4. 最终答案严格是一个 JSON 对象。
""".strip()


@dataclass(slots=True)
class OverlayVlmAnalysis:
    title_candidate: str | None
    brand_hint: str | None
    business_domain_hint: str | None
    model_hint: str | None
    spec_hint: str | None
    price_hint: str | None
    confidence: float | None
    reason: str | None
    raw_output: str
    usage: dict[str, int]
    queue: dict[str, Any]
    thinking_enabled: bool
    model: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "title_candidate": self.title_candidate,
            "brand_hint": self.brand_hint,
            "business_domain_hint": self.business_domain_hint,
            "model_hint": self.model_hint,
            "spec_hint": self.spec_hint,
            "price_hint": self.price_hint,
            "confidence": self.confidence,
            "reason": self.reason,
            "raw_output": self.raw_output,
            "usage": self.usage,
            "queue": self.queue,
            "thinking_enabled": self.thinking_enabled,
            "model": self.model,
        }


@dataclass(slots=True)
class _OverlayVlmJob:
    screenshot_base64: str
    ocr_lines: list[dict[str, Any]]
    screen_width: int | None
    screen_height: int | None
    source_package: str | None
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at_monotonic: float = field(default_factory=time.monotonic)
    queue_position: int = 0
    started_at_monotonic: float | None = None
    finished_at_monotonic: float | None = None
    done: threading.Event = field(default_factory=threading.Event)
    result: OverlayVlmAnalysis | None = None
    error: BaseException | None = None


class OverlayVlmQueue:
    def __init__(
        self,
        *,
        worker_fn: Callable[[_OverlayVlmJob], OverlayVlmAnalysis] | None = None,
        result_timeout_sec: float | None = None,
    ) -> None:
        settings = get_settings()
        self._worker_fn = worker_fn or _invoke_overlay_vlm
        self._result_timeout_sec = result_timeout_sec or float(settings.mobile_overlay_vlm_timeout_sec + 30)
        self._jobs: queue.Queue[_OverlayVlmJob] = queue.Queue()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._active_job_id: str | None = None
        self._active_job_started_at: float | None = None
        self._completed_jobs = 0
        self._failed_jobs = 0

    def submit_and_wait(
        self,
        *,
        screenshot_base64: str,
        ocr_lines: list[dict[str, Any]],
        screen_width: int | None,
        screen_height: int | None,
        source_package: str | None,
    ) -> OverlayVlmAnalysis:
        self._ensure_worker()
        with self._lock:
            queue_position = self._jobs.qsize() + (1 if self._active_job_id else 0) + 1
        job = _OverlayVlmJob(
            screenshot_base64=screenshot_base64,
            ocr_lines=ocr_lines,
            screen_width=screen_width,
            screen_height=screen_height,
            source_package=source_package,
            queue_position=queue_position,
        )
        self._jobs.put(job)
        if not job.done.wait(timeout=self._result_timeout_sec):
            raise TimeoutError("Overlay VLM queue timed out while waiting for the local 72B model.")
        if job.error is not None:
            raise RuntimeError("Overlay VLM job failed.") from job.error
        if job.result is None:
            raise RuntimeError("Overlay VLM job completed without a result.")
        return job.result

    def status(self) -> dict[str, Any]:
        with self._lock:
            pending_jobs = self._jobs.qsize()
            active_job_id = self._active_job_id
            active_seconds = None
            if self._active_job_started_at is not None:
                active_seconds = round(max(time.monotonic() - self._active_job_started_at, 0.0), 3)
            worker_alive = bool(self._worker and self._worker.is_alive())
            completed_jobs = self._completed_jobs
            failed_jobs = self._failed_jobs
        return {
            "worker_alive": worker_alive,
            "pending_jobs": pending_jobs,
            "active_job_id": active_job_id,
            "active_seconds": active_seconds,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
        }

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="goofish-mobile-overlay-vlm",
                daemon=True,
            )
            self._worker.start()

    def _worker_loop(self) -> None:
        while True:
            job = self._jobs.get()
            with self._lock:
                self._active_job_id = job.job_id
                self._active_job_started_at = time.monotonic()
            job.started_at_monotonic = time.monotonic()
            try:
                job.result = self._worker_fn(job)
            except BaseException as exc:  # pragma: no cover - defensive guard
                job.error = exc
            finally:
                job.finished_at_monotonic = time.monotonic()
                with self._lock:
                    self._active_job_id = None
                    self._active_job_started_at = None
                    if job.error is None:
                        self._completed_jobs += 1
                    else:
                        self._failed_jobs += 1
                job.done.set()
                self._jobs.task_done()


_OVERLAY_VLM_QUEUE: OverlayVlmQueue | None = None
_OVERLAY_VLM_QUEUE_LOCK = threading.Lock()


def get_overlay_vlm_queue() -> OverlayVlmQueue:
    global _OVERLAY_VLM_QUEUE
    with _OVERLAY_VLM_QUEUE_LOCK:
        if _OVERLAY_VLM_QUEUE is None:
            _OVERLAY_VLM_QUEUE = OverlayVlmQueue()
        return _OVERLAY_VLM_QUEUE


def analyze_mobile_overlay_screenshot(
    *,
    screenshot_base64: str,
    ocr_lines: list[dict[str, Any]],
    screen_width: int | None,
    screen_height: int | None,
    source_package: str | None,
) -> OverlayVlmAnalysis:
    return get_overlay_vlm_queue().submit_and_wait(
        screenshot_base64=screenshot_base64,
        ocr_lines=ocr_lines,
        screen_width=screen_width,
        screen_height=screen_height,
        source_package=source_package,
    )


def build_overlay_vlm_runtime_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "enabled": settings.mobile_overlay_vlm_enabled,
        "base_url": settings.mobile_overlay_vlm_base_url,
        "model": settings.mobile_overlay_vlm_model,
        "thinking_enabled": settings.mobile_overlay_vlm_enable_thinking,
        "queue": get_overlay_vlm_queue().status(),
    }


def _invoke_overlay_vlm(job: _OverlayVlmJob) -> OverlayVlmAnalysis:
    settings = get_settings()
    screenshot_data_url = _normalize_screenshot_data_url(job.screenshot_base64)
    payload = {
        "model": settings.mobile_overlay_vlm_model,
        "input": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": _build_user_prompt(
                            ocr_lines=job.ocr_lines,
                            screen_width=job.screen_width,
                            screen_height=job.screen_height,
                            source_package=job.source_package,
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": screenshot_data_url,
                    },
                ],
            },
        ],
        "max_output_tokens": settings.mobile_overlay_vlm_max_output_tokens,
        "enable_thinking": settings.mobile_overlay_vlm_enable_thinking,
        "stream": False,
        "temperature": 0.0,
    }
    timeout = httpx.Timeout(settings.mobile_overlay_vlm_timeout_sec, connect=5.0)
    started_at = time.monotonic()
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{settings.mobile_overlay_vlm_base_url.rstrip('/')}/responses", json=payload)
        response.raise_for_status()
        body = response.json()
    finished_at = time.monotonic()
    raw_output = _extract_vlm_text(body)
    parsed = _parse_vlm_json_output(raw_output)
    queue_wait_seconds = max((job.started_at_monotonic or started_at) - job.created_at_monotonic, 0.0)
    run_seconds = max(finished_at - (job.started_at_monotonic or started_at), 0.0)
    total_seconds = max(finished_at - job.created_at_monotonic, 0.0)
    queue_payload = {
        "job_id": job.job_id,
        "queue_position": job.queue_position,
        "queue_wait_seconds": round(queue_wait_seconds, 3),
        "run_seconds": round(run_seconds, 3),
        "total_seconds": round(total_seconds, 3),
        "pending_jobs_after_submit": get_overlay_vlm_queue().status()["pending_jobs"],
    }
    return OverlayVlmAnalysis(
        title_candidate=_clean_optional_text(parsed.get("title_candidate")),
        brand_hint=_clean_optional_text(parsed.get("brand_hint")),
        business_domain_hint=_normalize_domain_hint(parsed.get("business_domain_hint")),
        model_hint=_clean_optional_text(parsed.get("model_hint")),
        spec_hint=_clean_optional_text(parsed.get("spec_hint")),
        price_hint=_clean_optional_text(parsed.get("price_hint")),
        confidence=_to_confidence(parsed.get("confidence")),
        reason=_clean_optional_text(parsed.get("reason")),
        raw_output=raw_output,
        usage=_normalize_usage(body.get("usage")),
        queue=queue_payload,
        thinking_enabled=settings.mobile_overlay_vlm_enable_thinking,
        model=settings.mobile_overlay_vlm_model,
    )


def _build_user_prompt(
    *,
    ocr_lines: list[dict[str, Any]],
    screen_width: int | None,
    screen_height: int | None,
    source_package: str | None,
) -> str:
    summarized_lines = []
    for index, line in enumerate(ocr_lines[:24], start=1):
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        top = line.get("top")
        left = line.get("left")
        location = []
        if top is not None:
            location.append(f"top={top}")
        if left is not None:
            location.append(f"left={left}")
        suffix = f" ({', '.join(location)})" if location else ""
        summarized_lines.append(f"{index}. {text}{suffix}")

    prompt_lines = [
        "请分析这张截图里最核心的商品信息，输出上面约定的 JSON。",
        f"截图来源包名: {source_package or 'unknown'}",
        f"屏幕尺寸: {screen_width or '?'} x {screen_height or '?'}",
        "OCR 行如下：",
    ]
    prompt_lines.extend(summarized_lines or ["(OCR 未识别到有效文字，请优先看图判断)"])
    prompt_lines.append("如果截图里没有明确商品，就保持字段为空，不要编造。")
    return "\n".join(prompt_lines)


def _normalize_screenshot_data_url(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("data:image/"):
        return candidate
    if "," in candidate and candidate.split(",", 1)[0].startswith("data:image/"):
        return candidate
    return f"data:image/png;base64,{candidate}"


def _extract_vlm_text(body: dict[str, Any]) -> str:
    output_text = str(body.get("output_text") or "").strip()
    if output_text:
        return output_text
    chunks: list[str] = []
    for item in body.get("output") or []:
        content = item.get("content")
        if isinstance(content, str):
            if content.strip():
                chunks.append(content.strip())
            continue
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = str(part.get("text") or "").strip()
                if text:
                    chunks.append(text)
    return "\n".join(chunks).strip()


def _parse_vlm_json_output(raw_output: str) -> dict[str, Any]:
    if not raw_output.strip():
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_output, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, dict):
                return parsed
        except JSONDecodeError:
            pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", raw_output):
        try:
            parsed, _ = decoder.raw_decode(raw_output[match.start() :])
        except JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _normalize_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    return {
        "input_tokens": _to_int(value.get("input_tokens")) or 0,
        "output_tokens": _to_int(value.get("output_tokens")) or 0,
        "total_tokens": _to_int(value.get("total_tokens")) or 0,
    }


def _normalize_domain_hint(value: Any) -> str | None:
    candidate = _clean_optional_text(value)
    if candidate not in SUPPORTED_OVERLAY_DOMAINS:
        return None
    return candidate


def _to_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(round(numeric, 3), 1.0))


def _to_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None
