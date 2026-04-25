#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "apps" / "collector" / "src"
import sys

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from goofish_insight.settings import get_settings  # noqa: E402
from goofish_insight.specs import extract_usage_stats  # noqa: E402


@dataclass
class Counter:
    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    rate_limit_count: int = 0
    timeout_count: int = 0
    http_error_count: int = 0
    network_error_count: int = 0
    parse_error_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    sample_errors: list[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ark TPM/RPM pressure benchmark with concurrency ladder.")
    parser.add_argument("--duration-sec", type=int, default=40, help="Duration per concurrency level.")
    parser.add_argument("--cooldown-sec", type=int, default=4, help="Sleep between levels.")
    parser.add_argument(
        "--concurrency-levels",
        default="4,8,12,16",
        help="Comma-separated worker counts, for example: 4,8,12,16",
    )
    parser.add_argument(
        "--trace-path",
        default="",
        help="Optional trace JSON to replay request payload from reports/llm-traces.",
    )
    parser.add_argument(
        "--trace-dir",
        default=str(ROOT_DIR / "reports" / "llm-traces"),
        help="Trace directory for auto-picking latest Ark trace.",
    )
    parser.add_argument("--url", default="", help="Override request URL.")
    parser.add_argument("--model", default="", help="Override model.")
    parser.add_argument("--api-key", default="", help="Override API key.")
    parser.add_argument("--request-timeout-sec", type=int, default=90, help="HTTP timeout per request.")
    parser.add_argument("--max-tokens", type=int, default=0, help="Override payload max_tokens when > 0.")
    parser.add_argument("--output", default="", help="Output path (JSON).")
    parser.add_argument("--min-success-rate", type=float, default=0.98, help="Healthy threshold.")
    parser.add_argument("--max-rate-limit-ratio", type=float, default=0.02, help="Healthy threshold.")
    parser.add_argument("--dry-run", action="store_true", help="Only resolve config, do not run load.")
    return parser.parse_args()


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = max(min(int(round((len(ordered) - 1) * p)), len(ordered) - 1), 0)
    return ordered[idx]


def parse_levels(raw: str) -> list[int]:
    levels: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            continue
        if value > 0:
            levels.append(value)
    deduped: list[int] = []
    for value in levels:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _is_ark_url(url: str) -> bool:
    return "ark.cn-" in url.lower()


def _pick_latest_ark_trace(trace_dir: Path) -> Path | None:
    candidates: list[tuple[float, Path]] = []
    for path in trace_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        url = str(payload.get("url") or "")
        request_payload = payload.get("requestPayload")
        if not _is_ark_url(url) or not isinstance(request_payload, dict):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, path))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _load_template_payload(args: argparse.Namespace) -> tuple[str, dict[str, Any], str | None]:
    settings = get_settings()
    fallback_url = str(settings.ai_base_url or "").rstrip("/") + "/chat/completions"
    if "/chat/completions" not in fallback_url:
        fallback_url = fallback_url.rstrip("/") + "/chat/completions"
    fallback_payload: dict[str, Any] = {
        "model": args.model.strip() or settings.ai_model,
        "messages": [
            {
                "role": "system",
                "content": "You are a strict JSON assistant. Always return one JSON object.",
            },
            {
                "role": "user",
                "content": (
                    "Return JSON with keys: verdict, confidence, reason. "
                    "Keep reason around 120 Chinese characters."
                ),
            },
        ],
        "temperature": 0,
        "max_tokens": 220,
    }
    if _is_ark_url(fallback_url):
        fallback_payload["extra_body"] = {"enable_thinking": False}

    trace_path: Path | None = None
    if args.trace_path.strip():
        trace_path = Path(args.trace_path).expanduser().resolve()
        if not trace_path.exists():
            raise RuntimeError(f"trace path not found: {trace_path}")
    else:
        auto = _pick_latest_ark_trace(Path(args.trace_dir).expanduser())
        trace_path = auto

    if trace_path is None:
        url = args.url.strip() or fallback_url
        return url, fallback_payload, None

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    trace_url = str(payload.get("url") or "").strip()
    request_payload = payload.get("requestPayload")
    if not trace_url or not isinstance(request_payload, dict):
        url = args.url.strip() or fallback_url
        return url, fallback_payload, str(trace_path)

    result_payload = dict(request_payload)
    if args.model.strip():
        result_payload["model"] = args.model.strip()
    if args.max_tokens > 0:
        result_payload["max_tokens"] = args.max_tokens

    url = args.url.strip() or trace_url
    return url, result_payload, str(trace_path)


def _classify_rate_limit(message: str) -> bool:
    lowered = message.lower()
    return "429" in lowered or "too many" in lowered or "rate limit" in lowered or "requestbursttoofast" in lowered


def _send_one(*, url: str, api_key: str, request_payload: dict[str, Any], timeout_sec: int) -> tuple[bool, dict[str, int] | None, float, str | None]:
    started = time.perf_counter()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = Request(
        url=url,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8")
        parsed = json.loads(body)
        usage = extract_usage_stats(parsed)
        return True, usage, (time.perf_counter() - started) * 1000.0, None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        detail = f"HTTP {exc.code}: {body[:240]}".strip()
        return False, None, (time.perf_counter() - started) * 1000.0, detail
    except TimeoutError:
        return False, None, (time.perf_counter() - started) * 1000.0, "timeout"
    except URLError as exc:
        return False, None, (time.perf_counter() - started) * 1000.0, f"network_error: {exc.reason}"
    except json.JSONDecodeError:
        return False, None, (time.perf_counter() - started) * 1000.0, "json_decode_error"
    except Exception as exc:  # pragma: no cover - defensive
        return False, None, (time.perf_counter() - started) * 1000.0, f"unknown_error: {exc}"


def _worker(
    *,
    end_at: float,
    lock: threading.Lock,
    counter: Counter,
    url: str,
    api_key: str,
    request_payload: dict[str, Any],
    timeout_sec: int,
) -> None:
    while time.time() < end_at:
        ok, usage, latency_ms, error = _send_one(
            url=url,
            api_key=api_key,
            request_payload=request_payload,
            timeout_sec=timeout_sec,
        )
        with lock:
            counter.request_count += 1
            counter.latencies_ms.append(latency_ms)
            if ok:
                counter.success_count += 1
                counter.input_tokens += int((usage or {}).get("input_tokens") or 0)
                counter.output_tokens += int((usage or {}).get("output_tokens") or 0)
                counter.total_tokens += int((usage or {}).get("total_tokens") or 0)
            else:
                counter.error_count += 1
                detail = str(error or "unknown")
                if _classify_rate_limit(detail):
                    counter.rate_limit_count += 1
                elif "timeout" in detail.lower():
                    counter.timeout_count += 1
                elif detail.lower().startswith("http "):
                    counter.http_error_count += 1
                elif "network_error" in detail.lower():
                    counter.network_error_count += 1
                elif "json_decode_error" in detail.lower():
                    counter.parse_error_count += 1
                else:
                    counter.parse_error_count += 1
                if len(counter.sample_errors) < 12:
                    counter.sample_errors.append(detail)


def _run_level(
    *,
    concurrency: int,
    duration_sec: int,
    url: str,
    api_key: str,
    request_payload: dict[str, Any],
    timeout_sec: int,
) -> dict[str, Any]:
    lock = threading.Lock()
    counter = Counter()
    started_at = datetime.now(UTC)
    started = time.time()
    end_at = started + duration_sec

    threads: list[threading.Thread] = []
    for _ in range(concurrency):
        thread = threading.Thread(
            target=_worker,
            kwargs={
                "end_at": end_at,
                "lock": lock,
                "counter": counter,
                "url": url,
                "api_key": api_key,
                "request_payload": request_payload,
                "timeout_sec": timeout_sec,
            },
            daemon=True,
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    elapsed_sec = max(time.time() - started, 0.001)
    success_rate = counter.success_count / counter.request_count if counter.request_count else 0.0
    rate_limit_ratio = counter.rate_limit_count / counter.request_count if counter.request_count else 0.0
    p50 = percentile(counter.latencies_ms, 0.50)
    p90 = percentile(counter.latencies_ms, 0.90)
    p95 = percentile(counter.latencies_ms, 0.95)
    avg_latency = statistics.mean(counter.latencies_ms) if counter.latencies_ms else None

    return {
        "concurrency": concurrency,
        "started_at": started_at.isoformat(),
        "ended_at": datetime.now(UTC).isoformat(),
        "elapsed_sec": round(elapsed_sec, 3),
        "request_count": counter.request_count,
        "success_count": counter.success_count,
        "error_count": counter.error_count,
        "rate_limit_count": counter.rate_limit_count,
        "timeout_count": counter.timeout_count,
        "http_error_count": counter.http_error_count,
        "network_error_count": counter.network_error_count,
        "parse_error_count": counter.parse_error_count,
        "success_rate": round(success_rate, 6),
        "rate_limit_ratio": round(rate_limit_ratio, 6),
        "rpm": round(counter.request_count / elapsed_sec * 60.0, 2),
        "success_rpm": round(counter.success_count / elapsed_sec * 60.0, 2),
        "total_tpm": round(counter.total_tokens / elapsed_sec * 60.0, 2),
        "input_tpm": round(counter.input_tokens / elapsed_sec * 60.0, 2),
        "output_tpm": round(counter.output_tokens / elapsed_sec * 60.0, 2),
        "total_tokens": counter.total_tokens,
        "input_tokens": counter.input_tokens,
        "output_tokens": counter.output_tokens,
        "avg_tokens_per_success": round(counter.total_tokens / counter.success_count, 2) if counter.success_count else 0.0,
        "latency_ms_avg": round(avg_latency, 2) if avg_latency is not None else None,
        "latency_ms_p50": round(p50, 2) if p50 is not None else None,
        "latency_ms_p90": round(p90, 2) if p90 is not None else None,
        "latency_ms_p95": round(p95, 2) if p95 is not None else None,
        "sample_errors": counter.sample_errors,
    }


def main() -> int:
    args = parse_args()
    levels = parse_levels(args.concurrency_levels)
    if not levels:
        raise RuntimeError("no valid concurrency levels")

    settings = get_settings()
    api_key = args.api_key.strip() or str(settings.ai_api_key or "")
    if not api_key:
        raise RuntimeError("AI API key missing; set AI_API_KEY or use --api-key")

    url, request_payload, trace_path = _load_template_payload(args)
    if args.max_tokens > 0:
        request_payload["max_tokens"] = args.max_tokens
    if args.model.strip():
        request_payload["model"] = args.model.strip()

    payload_preview = {
        "model": request_payload.get("model"),
        "max_tokens": request_payload.get("max_tokens"),
        "message_count": len(request_payload.get("messages") or []),
        "has_extra_body": isinstance(request_payload.get("extra_body"), dict),
    }

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_path = Path(args.output).expanduser() if args.output.strip() else ROOT_DIR / "reports" / f"ark-tpm-benchmark-{timestamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    benchmark: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "trace_replay" if trace_path else "synthetic_prompt",
        "trace_path": trace_path,
        "url": url,
        "duration_sec_per_level": args.duration_sec,
        "cooldown_sec": args.cooldown_sec,
        "levels": levels,
        "timeout_sec": args.request_timeout_sec,
        "payload_preview": payload_preview,
        "results": [],
        "recommendation": None,
    }

    print(json.dumps({"event": "benchmark_start", "levels": levels, "duration_sec": args.duration_sec, "url": url}, ensure_ascii=False))
    if args.dry_run:
        output_path.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"event": "benchmark_dry_run", "output": str(output_path)}, ensure_ascii=False))
        return 0

    for index, concurrency in enumerate(levels):
        print(json.dumps({"event": "level_start", "concurrency": concurrency}, ensure_ascii=False))
        result = _run_level(
            concurrency=concurrency,
            duration_sec=args.duration_sec,
            url=url,
            api_key=api_key,
            request_payload=request_payload,
            timeout_sec=args.request_timeout_sec,
        )
        benchmark["results"].append(result)
        print(
            json.dumps(
                {
                    "event": "level_done",
                    "concurrency": concurrency,
                    "request_count": result["request_count"],
                    "success_rate": result["success_rate"],
                    "rate_limit_ratio": result["rate_limit_ratio"],
                    "total_tpm": result["total_tpm"],
                    "success_rpm": result["success_rpm"],
                },
                ensure_ascii=False,
            )
        )
        if index < len(levels) - 1 and args.cooldown_sec > 0:
            time.sleep(args.cooldown_sec)

    healthy_results = [
        row
        for row in benchmark["results"]
        if float(row.get("success_rate") or 0.0) >= args.min_success_rate
        and float(row.get("rate_limit_ratio") or 0.0) <= args.max_rate_limit_ratio
    ]
    if healthy_results:
        recommended = max(healthy_results, key=lambda row: (float(row.get("total_tpm") or 0.0), int(row.get("concurrency") or 0)))
    else:
        recommended = max(benchmark["results"], key=lambda row: float(row.get("total_tpm") or 0.0))

    benchmark["recommendation"] = {
        "min_success_rate": args.min_success_rate,
        "max_rate_limit_ratio": args.max_rate_limit_ratio,
        "recommended_concurrency": int(recommended.get("concurrency") or 0),
        "recommended_total_tpm": float(recommended.get("total_tpm") or 0.0),
        "recommended_success_rpm": float(recommended.get("success_rpm") or 0.0),
        "recommended_success_rate": float(recommended.get("success_rate") or 0.0),
        "recommended_rate_limit_ratio": float(recommended.get("rate_limit_ratio") or 0.0),
    }
    benchmark["completed_at"] = datetime.now(UTC).isoformat()

    output_path.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"event": "benchmark_done", "output": str(output_path), "recommendation": benchmark["recommendation"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

