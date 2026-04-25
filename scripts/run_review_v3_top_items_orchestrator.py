#!/usr/bin/env python3
from __future__ import annotations

import atexit
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from sqlalchemy import desc, func, select

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "apps/collector/src"))

from goofish_insight.db import SessionLocal  # noqa: E402
from goofish_insight.models import Item, ItemReviewV3  # noqa: E402


@dataclass(frozen=True)
class FirstPassBatch:
    business_domain: str
    item_ids: tuple[str, ...]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_non_empty_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]


def load_first_pass_batches(path: Path) -> list[FirstPassBatch]:
    batches: list[FirstPassBatch] = []
    for raw in read_non_empty_lines(path):
        if "|" not in raw:
            continue
        domain, ids_raw = raw.split("|", 1)
        item_ids = tuple(part.strip() for part in ids_raw.split(",") if part.strip())
        domain = domain.strip()
        if not domain or not item_ids:
            continue
        batches.append(FirstPassBatch(business_domain=domain, item_ids=item_ids))
    return batches


def line_count(path: Path) -> int:
    return len(read_non_empty_lines(path))


def find_latest_incomplete_prefix(reports_dir: Path, base_prefix: str) -> str | None:
    candidates: list[tuple[float, str]] = []
    for cohort_path in reports_dir.glob(f"{base_prefix}-*.itemids.txt"):
        run_prefix = cohort_path.name[: -len(".itemids.txt")]
        final_summary = reports_dir / f"{run_prefix}.final-summary.json"
        if final_summary.exists():
            continue

        batches_path = reports_dir / f"{run_prefix}.first-pass.batches"
        if not batches_path.exists():
            continue

        total = line_count(cohort_path)
        if total <= 0:
            continue

        processed = line_count(reports_dir / f"{run_prefix}.first-pass.done") + line_count(
            reports_dir / f"{run_prefix}.first-pass.failed"
        )
        if processed < total or not final_summary.exists():
            candidates.append((cohort_path.stat().st_mtime, run_prefix))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def resolve_run_prefix(*, reports_dir: Path, base_prefix: str, explicit_run_prefix: str, resume_mode: str) -> tuple[str, bool]:
    explicit = explicit_run_prefix.strip()
    mode = resume_mode.strip().lower() or "auto"

    if explicit:
        existing = (reports_dir / f"{explicit}.itemids.txt").exists()
        if mode == "force" and not existing:
            raise RuntimeError(f"run prefix not found for force mode: {explicit}")
        return explicit, existing

    if mode in {"auto", "force"}:
        latest = find_latest_incomplete_prefix(reports_dir, base_prefix)
        if latest:
            return latest, True
        if mode == "force":
            raise RuntimeError(f"no incomplete run found for base prefix: {base_prefix}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{base_prefix}-{stamp}", False


LIMIT = _env_int("LIMIT", 1000)
WORKERS = max(_env_int("WORKERS", 15), 1)
FIRST_PASS_BATCH_SIZE = max(_env_int("FIRST_PASS_BATCH_SIZE", 4), 1)
AI_TIMEOUT_SEC = max(_env_int("AI_TIMEOUT_SEC", 90), 5)
BASE_PREFIX = os.environ.get("PREFIX", "review-v3-top1000-orchestrated")
EXPLICIT_RUN_PREFIX = os.environ.get("RUN_PREFIX", "")
RESUME_MODE = os.environ.get("REVIEW_V3_RESUME_MODE", "auto")
RETRY_FAILED_FIRST_PASS = _env_bool("REVIEW_V3_RETRY_FAILED_FIRST_PASS", False)
FIRST_PASS_RETRY_MAX = max(_env_int("FIRST_PASS_RETRY_MAX", 3), 1)
SECOND_PASS_RETRY_MAX = max(_env_int("SECOND_PASS_RETRY_MAX", 2), 1)
RETRY_BACKOFF_BASE_SEC = max(_env_float("RETRY_BACKOFF_BASE_SEC", 2.0), 0.5)
RETRY_BACKOFF_MAX_SEC = max(_env_float("RETRY_BACKOFF_MAX_SEC", 30.0), RETRY_BACKOFF_BASE_SEC)
CLI_TIMEOUT_SEC = max(_env_int("REVIEW_V3_CLI_TIMEOUT_SEC", AI_TIMEOUT_SEC + 60), AI_TIMEOUT_SEC + 5)
QUOTA_BACKOFF_SEC = max(_env_int("REVIEW_V3_QUOTA_BACKOFF_SEC", 900), 30)
QUOTA_WAIT_GRACE_SEC = max(_env_int("REVIEW_V3_QUOTA_WAIT_GRACE_SEC", 5), 0)

REPORTS_DIR = ROOT_DIR / "reports"
START_UTC = utc_now_iso()

RUN_PREFIX, RESUMED = resolve_run_prefix(
    reports_dir=REPORTS_DIR,
    base_prefix=BASE_PREFIX,
    explicit_run_prefix=EXPLICIT_RUN_PREFIX,
    resume_mode=RESUME_MODE,
)

COHORT_PATH = REPORTS_DIR / f"{RUN_PREFIX}.itemids.txt"
FIRST_BATCHES_PATH = REPORTS_DIR / f"{RUN_PREFIX}.first-pass.batches"
FIRST_DONE_PATH = REPORTS_DIR / f"{RUN_PREFIX}.first-pass.done"
FIRST_FAILED_PATH = REPORTS_DIR / f"{RUN_PREFIX}.first-pass.failed"
SECOND_DONE_PATH = REPORTS_DIR / f"{RUN_PREFIX}.second-pass.done"
SECOND_FAILED_PATH = REPORTS_DIR / f"{RUN_PREFIX}.second-pass.failed"
PENDING_PATH = REPORTS_DIR / f"{RUN_PREFIX}.pending-second-pass.txt"
SUMMARY_PATH = REPORTS_DIR / f"{RUN_PREFIX}.final-summary.json"
RUN_STATE_PATH = REPORTS_DIR / f"{RUN_PREFIX}.run-state.json"

STATE_LOCK = Lock()
QUOTA_LOCK = Lock()
QUOTA_WAIT_UNTIL_TS: float | None = None
QUOTA_WAIT_REASON: str | None = None
FINAL_STATE_RECORDED = False
TERMINATION_REQUESTED: str | None = None
QUOTA_RESET_AT_PATTERN = re.compile(
    r"reset at (?P<reset_at>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})(?: [A-Z]+)?",
    re.IGNORECASE,
)

STATE: dict[str, Any] = {
    "run_prefix": RUN_PREFIX,
    "prefix_base": BASE_PREFIX,
    "resume_mode": RESUME_MODE,
    "resumed": RESUMED,
    "pid": os.getpid(),
    "started_at": START_UTC,
    "updated_at": START_UTC,
    "status": "initializing",
    "phase": "bootstrap",
    "config": {
        "limit": LIMIT,
        "workers": WORKERS,
        "first_pass_batch_size": FIRST_PASS_BATCH_SIZE,
        "ai_timeout_sec": AI_TIMEOUT_SEC,
        "first_pass_retry_max": FIRST_PASS_RETRY_MAX,
        "second_pass_retry_max": SECOND_PASS_RETRY_MAX,
        "retry_backoff_base_sec": RETRY_BACKOFF_BASE_SEC,
        "retry_backoff_max_sec": RETRY_BACKOFF_MAX_SEC,
        "cli_timeout_sec": CLI_TIMEOUT_SEC,
        "retry_failed_first_pass": RETRY_FAILED_FIRST_PASS,
    },
    "paths": {
        "itemids": str(COHORT_PATH),
        "first_pass_batches": str(FIRST_BATCHES_PATH),
        "first_pass_done": str(FIRST_DONE_PATH),
        "first_pass_failed": str(FIRST_FAILED_PATH),
        "pending_second_pass": str(PENDING_PATH),
        "second_pass_done": str(SECOND_DONE_PATH),
        "second_pass_failed": str(SECOND_FAILED_PATH),
        "final_summary": str(SUMMARY_PATH),
        "run_state": str(RUN_STATE_PATH),
    },
    "counts": {
        "total": 0,
        "first_pass_done": 0,
        "first_pass_failed": 0,
        "first_pass_remaining": 0,
        "pending_second_pass": 0,
        "second_pass_done": 0,
        "second_pass_failed": 0,
    },
    "last_event": None,
    "last_error": None,
}


def write_state(*, status: str | None = None, phase: str | None = None, last_event: str | None = None, error: str | None = None, **extra: Any) -> None:
    with STATE_LOCK:
        if status is not None:
            STATE["status"] = status
        if phase is not None:
            STATE["phase"] = phase
        if last_event is not None:
            STATE["last_event"] = last_event
        if error is not None:
            STATE["last_error"] = error
        STATE["updated_at"] = utc_now_iso()
        for key, value in extra.items():
            STATE[key] = value
        RUN_STATE_PATH.write_text(json.dumps(STATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _mark_final_state_recorded() -> None:
    global FINAL_STATE_RECORDED
    FINAL_STATE_RECORDED = True


def _clear_quota_wait_state() -> None:
    write_state(
        quota_wait_until=None,
        quota_wait_seconds=None,
        quota_wait_reason=None,
    )


def record_final_state(*, status: str, phase: str, error: str | None = None) -> None:
    write_state(status=status, phase=phase, error=error)
    _mark_final_state_recorded()


def _handle_termination(signum: int, _frame: object) -> None:
    global TERMINATION_REQUESTED
    TERMINATION_REQUESTED = signal.Signals(signum).name
    raise KeyboardInterrupt


def _record_unexpected_exit() -> None:
    if FINAL_STATE_RECORDED:
        return
    error = TERMINATION_REQUESTED or "process_exited_without_final_state"
    try:
        record_final_state(status="failed", phase="terminated", error=error)
    except Exception:
        return


atexit.register(_record_unexpected_exit)
signal.signal(signal.SIGINT, _handle_termination)
signal.signal(signal.SIGTERM, _handle_termination)


def refresh_counts(
    *,
    total: int | None = None,
    first_done: int | None = None,
    first_failed: int | None = None,
    pending_second: int | None = None,
    second_done: int | None = None,
    second_failed: int | None = None,
) -> None:
    current_total = total if total is not None else STATE["counts"].get("total", 0)
    done_count = first_done if first_done is not None else line_count(FIRST_DONE_PATH)
    failed_count = first_failed if first_failed is not None else line_count(FIRST_FAILED_PATH)
    first_remaining = max(current_total - done_count - failed_count, 0)
    pending_count = pending_second if pending_second is not None else line_count(PENDING_PATH)
    second_done_count = second_done if second_done is not None else line_count(SECOND_DONE_PATH)
    second_failed_count = second_failed if second_failed is not None else line_count(SECOND_FAILED_PATH)

    write_state(
        counts={
            "total": current_total,
            "first_pass_done": done_count,
            "first_pass_failed": failed_count,
            "first_pass_remaining": first_remaining,
            "pending_second_pass": pending_count,
            "second_pass_done": second_done_count,
            "second_pass_failed": second_failed_count,
        }
    )


def emit(event: dict[str, Any]) -> None:
    print(json.dumps(event, ensure_ascii=False))
    event_name = str(event.get("event") or "")
    write_state(last_event=event_name)


def _python_bin() -> str:
    candidate = ROOT_DIR / ".venv/bin/python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _base_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = "apps/collector/src"
    env["AI_TIMEOUT_SEC"] = str(AI_TIMEOUT_SEC)
    return env


def _normalize_stderr(stderr: str | bytes | None) -> str:
    if stderr is None:
        return ""
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", errors="ignore").strip()
    return str(stderr).strip()


def _write_lines(path: Path, values: list[str]) -> None:
    if not values:
        return
    with path.open("a", encoding="utf-8") as handle:
        for value in values:
            handle.write(f"{value}\n")


def _rewrite_lines(path: Path, values: set[str]) -> None:
    ordered = sorted(values)
    path.write_text("\n".join(ordered) + ("\n" if ordered else ""), encoding="utf-8")


def _iso_from_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_quota_reset_at(stderr: str) -> float | None:
    match = QUOTA_RESET_AT_PATTERN.search(stderr)
    if not match:
        return None
    try:
        reset_dt = datetime.strptime(match.group("reset_at"), "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return None
    return reset_dt.timestamp()


def _is_quota_exhausted(stderr: str) -> bool:
    normalized = stderr.lower()
    return "http 429" in normalized and (
        "accountquotaexceeded" in normalized or "quota" in normalized or "too many requests" in normalized
    )


def _activate_quota_wait(*, phase: str, stderr: str, retry_events: list[dict[str, Any]], context: dict[str, Any]) -> None:
    global QUOTA_WAIT_UNTIL_TS, QUOTA_WAIT_REASON

    if not _is_quota_exhausted(stderr):
        return

    proposed_until = _parse_quota_reset_at(stderr)
    if proposed_until is None:
        proposed_until = time.time() + QUOTA_BACKOFF_SEC
    proposed_until = max(proposed_until + QUOTA_WAIT_GRACE_SEC, time.time() + 1)

    with QUOTA_LOCK:
        if QUOTA_WAIT_UNTIL_TS is None or proposed_until > QUOTA_WAIT_UNTIL_TS:
            QUOTA_WAIT_UNTIL_TS = proposed_until
            QUOTA_WAIT_REASON = stderr[-800:] if stderr else "quota_exhausted"
        wait_until = QUOTA_WAIT_UNTIL_TS
        wait_reason = QUOTA_WAIT_REASON or "quota_exhausted"

    wait_seconds = max(int(wait_until - time.time()), 1)
    wait_until_iso = _iso_from_timestamp(wait_until)
    event = {
        "event": "quota_wait_scheduled",
        "phase": phase,
        "wait_seconds": wait_seconds,
        "wait_until": wait_until_iso,
        "reason": wait_reason[-500:],
        "run_prefix": RUN_PREFIX,
        **context,
    }
    retry_events.append(event)
    write_state(
        status=f"quota_waiting_{phase}",
        phase=phase,
        quota_wait_until=wait_until_iso,
        quota_wait_seconds=wait_seconds,
        quota_wait_reason=wait_reason[-500:],
    )


def _wait_for_quota_if_needed(*, phase: str, retry_events: list[dict[str, Any]], context: dict[str, Any]) -> None:
    global QUOTA_WAIT_UNTIL_TS, QUOTA_WAIT_REASON

    with QUOTA_LOCK:
        wait_until = QUOTA_WAIT_UNTIL_TS
        wait_reason = QUOTA_WAIT_REASON

    if wait_until is None:
        return

    remaining = max(int(wait_until - time.time()), 0)
    if remaining <= 0:
        with QUOTA_LOCK:
            QUOTA_WAIT_UNTIL_TS = None
            QUOTA_WAIT_REASON = None
        _clear_quota_wait_state()
        return

    wait_until_iso = _iso_from_timestamp(wait_until)
    retry_events.append(
        {
            "event": "quota_waiting",
            "phase": phase,
            "wait_seconds": remaining,
            "wait_until": wait_until_iso,
            "reason": (wait_reason or "quota_exhausted")[-500:],
            "run_prefix": RUN_PREFIX,
            **context,
        }
    )
    write_state(
        status=f"quota_waiting_{phase}",
        phase=phase,
        quota_wait_until=wait_until_iso,
        quota_wait_seconds=remaining,
        quota_wait_reason=(wait_reason or "quota_exhausted")[-500:],
    )
    time.sleep(remaining)


def build_cohort(limit: int, out: Path) -> list[str]:
    with SessionLocal() as session:
        ids = list(
            session.execute(
                select(Item.item_id)
                .where(Item.is_active.is_(True))
                .order_by(desc(Item.last_seen_at), desc(Item.id))
                .limit(limit)
            ).scalars()
        )
    out.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
    emit({"event": "cohort_created", "count": len(ids), "path": str(out), "run_prefix": RUN_PREFIX})
    return ids


def build_first_pass_batches(cohort: list[str], out: Path, batch_size: int) -> list[FirstPassBatch]:
    with SessionLocal() as session:
        rows = session.execute(select(Item.item_id, Item.business_domain).where(Item.item_id.in_(cohort))).all()
    domain_by_id = {row.item_id: row.business_domain for row in rows}
    grouped: dict[str, list[str]] = defaultdict(list)
    for item_id in cohort:
        business_domain = domain_by_id.get(item_id)
        if business_domain:
            grouped[str(business_domain)].append(item_id)

    batches: list[FirstPassBatch] = []
    serialized_lines: list[str] = []
    for business_domain, item_ids in grouped.items():
        for index in range(0, len(item_ids), batch_size):
            batch_ids = tuple(item_ids[index : index + batch_size])
            batches.append(FirstPassBatch(business_domain=business_domain, item_ids=batch_ids))
            serialized_lines.append(f"{business_domain}|{','.join(batch_ids)}")

    out.write_text("\n".join(serialized_lines) + ("\n" if serialized_lines else ""), encoding="utf-8")
    emit(
        {
            "event": "first_pass_batches_created",
            "batch_count": len(batches),
            "path": str(out),
            "batch_size": batch_size,
            "run_prefix": RUN_PREFIX,
        }
    )
    return batches


def backoff_seconds(attempt: int) -> float:
    raw = RETRY_BACKOFF_BASE_SEC * (2 ** max(attempt - 1, 0))
    return min(raw, RETRY_BACKOFF_MAX_SEC)


def run_first_pass_batch(batch: FirstPassBatch) -> tuple[FirstPassBatch, int, str, int, list[dict[str, Any]]]:
    command = [
        _python_bin(),
        "-m",
        "goofish_insight.cli",
        "review-v3-first-pass-batch",
        batch.business_domain,
        "--item-ids",
        ",".join(batch.item_ids),
        "--ai-timeout-sec",
        str(AI_TIMEOUT_SEC),
        "--executor",
        "direct",
        "--force",
    ]

    retry_events: list[dict[str, Any]] = []
    last_stderr = ""
    for attempt in range(1, FIRST_PASS_RETRY_MAX + 1):
        _wait_for_quota_if_needed(
            phase="first_pass",
            retry_events=retry_events,
            context={"business_domain": batch.business_domain, "item_ids": list(batch.item_ids)},
        )
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT_DIR,
                env=_base_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=CLI_TIMEOUT_SEC,
            )
            returncode = completed.returncode
            last_stderr = _normalize_stderr(completed.stderr)
        except subprocess.TimeoutExpired as timeout_exc:
            returncode = 124
            timeout_stderr = _normalize_stderr(timeout_exc.stderr)
            last_stderr = f"cli_timeout_exceeded_{CLI_TIMEOUT_SEC}s"
            if timeout_stderr:
                last_stderr = f"{last_stderr}; stderr={timeout_stderr}"

        if returncode == 0:
            return batch, 0, last_stderr, attempt, retry_events

        if attempt < FIRST_PASS_RETRY_MAX:
            _activate_quota_wait(
                phase="first_pass",
                stderr=last_stderr,
                retry_events=retry_events,
                context={"business_domain": batch.business_domain, "item_ids": list(batch.item_ids)},
            )
            if _is_quota_exhausted(last_stderr):
                continue

        if attempt < FIRST_PASS_RETRY_MAX:
            delay = backoff_seconds(attempt)
            retry_events.append(
                {
                    "event": "first_pass_batch_retry",
                    "business_domain": batch.business_domain,
                    "item_ids": list(batch.item_ids),
                    "attempt": attempt,
                    "max_attempts": FIRST_PASS_RETRY_MAX,
                    "backoff_sec": round(delay, 2),
                    "cli_timeout_sec": CLI_TIMEOUT_SEC,
                    "stderr": last_stderr[-500:] if last_stderr else "",
                    "run_prefix": RUN_PREFIX,
                }
            )
            time.sleep(delay)

    return batch, 1, last_stderr, FIRST_PASS_RETRY_MAX, retry_events


def run_second_pass_item(item_id: str) -> tuple[str, int, str, int, list[dict[str, Any]]]:
    command = [
        _python_bin(),
        "-m",
        "goofish_insight.cli",
        "review-v3-second-pass",
        "--item-id",
        item_id,
        "--limit",
        "1",
        "--ai-timeout-sec",
        str(AI_TIMEOUT_SEC),
        "--executor",
        "direct",
        "--force",
    ]

    retry_events: list[dict[str, Any]] = []
    last_stderr = ""
    for attempt in range(1, SECOND_PASS_RETRY_MAX + 1):
        _wait_for_quota_if_needed(
            phase="second_pass",
            retry_events=retry_events,
            context={"item_id": item_id},
        )
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT_DIR,
                env=_base_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=CLI_TIMEOUT_SEC,
            )
            returncode = completed.returncode
            last_stderr = _normalize_stderr(completed.stderr)
        except subprocess.TimeoutExpired as timeout_exc:
            returncode = 124
            timeout_stderr = _normalize_stderr(timeout_exc.stderr)
            last_stderr = f"cli_timeout_exceeded_{CLI_TIMEOUT_SEC}s"
            if timeout_stderr:
                last_stderr = f"{last_stderr}; stderr={timeout_stderr}"

        if returncode == 0:
            return item_id, 0, last_stderr, attempt, retry_events

        if attempt < SECOND_PASS_RETRY_MAX:
            _activate_quota_wait(
                phase="second_pass",
                stderr=last_stderr,
                retry_events=retry_events,
                context={"item_id": item_id},
            )
            if _is_quota_exhausted(last_stderr):
                continue

        if attempt < SECOND_PASS_RETRY_MAX:
            delay = backoff_seconds(attempt)
            retry_events.append(
                {
                    "event": "second_pass_item_retry",
                    "item_id": item_id,
                    "attempt": attempt,
                    "max_attempts": SECOND_PASS_RETRY_MAX,
                    "backoff_sec": round(delay, 2),
                    "cli_timeout_sec": CLI_TIMEOUT_SEC,
                    "stderr": last_stderr[-500:] if last_stderr else "",
                    "run_prefix": RUN_PREFIX,
                }
            )
            time.sleep(delay)

    return item_id, 1, last_stderr, SECOND_PASS_RETRY_MAX, retry_events


def run_first_pass_phase(*, batches: list[FirstPassBatch], total: int, resumed: bool) -> None:
    if not resumed:
        FIRST_DONE_PATH.write_text("", encoding="utf-8")
        FIRST_FAILED_PATH.write_text("", encoding="utf-8")

    done_set = set(read_non_empty_lines(FIRST_DONE_PATH))
    failed_set = set(read_non_empty_lines(FIRST_FAILED_PATH))
    retryable_failed_set = failed_set if RETRY_FAILED_FIRST_PASS else set()
    processed_set = done_set | (failed_set - retryable_failed_set)

    pending_batches = [batch for batch in batches if not set(batch.item_ids).issubset(processed_set)]

    emit(
        {
            "event": "first_pass_phase_started",
            "run_prefix": RUN_PREFIX,
            "batch_total": len(batches),
            "batch_pending": len(pending_batches),
            "completed_item_count": len(done_set),
            "failed_item_count": len(failed_set),
            "retry_failed_first_pass": RETRY_FAILED_FIRST_PASS,
            "retry_failed_item_count": len(retryable_failed_set),
            "resumed": resumed,
        }
    )
    write_state(status="running_first_pass", phase="first_pass")
    refresh_counts(total=total, first_done=len(done_set), first_failed=len(failed_set))

    if not pending_batches:
        emit(
            {
                "event": "first_pass_phase_already_complete",
                "run_prefix": RUN_PREFIX,
                "completed_item_count": len(done_set),
                "failed_item_count": len(failed_set),
                "retry_failed_first_pass": RETRY_FAILED_FIRST_PASS,
            }
        )
        return

    completed_item_count = len(done_set)
    failed_item_count = len(failed_set)

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(run_first_pass_batch, batch) for batch in pending_batches]
        for future in as_completed(futures):
            batch, returncode, stderr, attempts_used, retry_events = future.result()

            for retry_event in retry_events:
                emit(retry_event)
                write_state(status="retry_backoff_first_pass", phase="first_pass")

            if returncode == 0:
                retried_ids = [item_id for item_id in batch.item_ids if item_id in failed_set]
                if retried_ids:
                    failed_set.difference_update(retried_ids)
                    _rewrite_lines(FIRST_FAILED_PATH, failed_set)
                    failed_item_count = max(failed_item_count - len(retried_ids), 0)

                new_ids = [item_id for item_id in batch.item_ids if item_id not in done_set]
                if new_ids:
                    _write_lines(FIRST_DONE_PATH, new_ids)
                    done_set.update(new_ids)
                    completed_item_count += len(new_ids)
            else:
                new_ids = [item_id for item_id in batch.item_ids if item_id not in done_set and item_id not in failed_set]
                if new_ids:
                    _write_lines(FIRST_FAILED_PATH, new_ids)
                    failed_set.update(new_ids)
                    failed_item_count += len(new_ids)

                if stderr:
                    emit(
                        {
                            "event": "first_pass_batch_failed",
                            "business_domain": batch.business_domain,
                            "item_ids": list(batch.item_ids),
                            "attempts_used": attempts_used,
                            "stderr": stderr[-800:],
                            "run_prefix": RUN_PREFIX,
                        }
                    )

            emit(
                {
                    "event": "first_pass_batch_completed",
                    "business_domain": batch.business_domain,
                    "batch_size": len(batch.item_ids),
                    "completed_item_count": completed_item_count,
                    "failed_item_count": failed_item_count,
                    "attempts_used": attempts_used,
                    "run_prefix": RUN_PREFIX,
                }
            )
            write_state(status="running_first_pass", phase="first_pass")
            refresh_counts(total=total, first_done=completed_item_count, first_failed=failed_item_count)


def build_pending_second_pass(cohort: list[str], out: Path) -> list[str]:
    with SessionLocal() as session:
        rows = session.execute(
            select(Item.item_id)
            .join(ItemReviewV3, ItemReviewV3.item_id_ref == Item.id)
            .where(Item.item_id.in_(cohort), ItemReviewV3.resolution_status == "PENDING_REVIEW")
        ).scalars().all()
    out.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    emit({"event": "pending_second_pass_built", "count": len(rows), "path": str(out), "run_prefix": RUN_PREFIX})
    return list(rows)


def run_second_pass_phase(item_ids: list[str], total: int) -> None:
    SECOND_DONE_PATH.write_text("", encoding="utf-8")
    SECOND_FAILED_PATH.write_text("", encoding="utf-8")

    write_state(status="running_second_pass", phase="second_pass")
    refresh_counts(total=total, first_done=line_count(FIRST_DONE_PATH), first_failed=line_count(FIRST_FAILED_PATH))

    if not item_ids:
        emit({"event": "second_pass_skipped", "reason": "no_pending_items", "run_prefix": RUN_PREFIX})
        return

    completed_item_count = 0
    failed_item_count = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(run_second_pass_item, item_id) for item_id in item_ids]
        for future in as_completed(futures):
            item_id, returncode, stderr, attempts_used, retry_events = future.result()

            for retry_event in retry_events:
                emit(retry_event)
                write_state(status="retry_backoff_second_pass", phase="second_pass")

            target_path = SECOND_DONE_PATH if returncode == 0 else SECOND_FAILED_PATH
            _write_lines(target_path, [item_id])
            if returncode == 0:
                completed_item_count += 1
            else:
                failed_item_count += 1

            if stderr and returncode != 0:
                emit(
                    {
                        "event": "second_pass_item_failed",
                        "item_id": item_id,
                        "attempts_used": attempts_used,
                        "stderr": stderr[-800:],
                        "run_prefix": RUN_PREFIX,
                    }
                )

            emit(
                {
                    "event": "second_pass_item_completed",
                    "item_id": item_id,
                    "completed_item_count": completed_item_count,
                    "failed_item_count": failed_item_count,
                    "attempts_used": attempts_used,
                    "run_prefix": RUN_PREFIX,
                }
            )
            write_state(status="running_second_pass", phase="second_pass")
            refresh_counts(
                total=total,
                first_done=STATE["counts"].get("first_pass_done"),
                first_failed=STATE["counts"].get("first_pass_failed"),
                pending_second=STATE["counts"].get("pending_second_pass"),
                second_done=completed_item_count,
                second_failed=failed_item_count,
            )


def write_summary(cohort: list[str], total: int) -> None:
    write_state(status="writing_summary", phase="summary")
    _clear_quota_wait_state()

    with SessionLocal() as session:
        rows = session.execute(
            select(
                Item.item_id,
                Item.business_domain,
                Item.llm_review_status,
                Item.llm_review_confidence,
                ItemReviewV3.stage_status,
                ItemReviewV3.resolution_status,
                ItemReviewV3.model_catalog_id,
                ItemReviewV3.first_pass_confidence,
                ItemReviewV3.second_pass_confidence,
            )
            .join(ItemReviewV3, ItemReviewV3.item_id_ref == Item.id, isouter=True)
            .where(Item.item_id.in_(cohort))
        ).all()

    status_counts = Counter()
    domain_status: dict[str, Counter[str]] = defaultdict(Counter)
    compat_counts = Counter()
    serialized = []
    for row in rows:
        status = row.resolution_status or "NO_V3_ROW"
        status_counts[status] += 1
        domain_status[row.business_domain][status] += 1
        compat_counts[row.llm_review_status or "NULL"] += 1
        serialized.append(
            {
                "item_id": row.item_id,
                "business_domain": row.business_domain,
                "compat_status": row.llm_review_status,
                "compat_confidence": float(row.llm_review_confidence) if row.llm_review_confidence is not None else None,
                "stage_status": row.stage_status,
                "resolution_status": row.resolution_status,
                "model_catalog_id": row.model_catalog_id,
                "first_pass_confidence": float(row.first_pass_confidence) if row.first_pass_confidence is not None else None,
                "second_pass_confidence": float(row.second_pass_confidence) if row.second_pass_confidence is not None else None,
            }
        )

    summary = {
        "startedAt": START_UTC,
        "completedAt": utc_now_iso(),
        "runPrefix": RUN_PREFIX,
        "prefixBase": BASE_PREFIX,
        "resumed": RESUMED,
        "cohortCount": len(cohort),
        "workers": WORKERS,
        "firstPassBatchSize": FIRST_PASS_BATCH_SIZE,
        "firstPassRetryMax": FIRST_PASS_RETRY_MAX,
        "secondPassRetryMax": SECOND_PASS_RETRY_MAX,
        "retryBackoffBaseSec": RETRY_BACKOFF_BASE_SEC,
        "retryBackoffMaxSec": RETRY_BACKOFF_MAX_SEC,
        "cliTimeoutSec": CLI_TIMEOUT_SEC,
        "firstPassDoneCount": line_count(FIRST_DONE_PATH),
        "firstPassFailedCount": line_count(FIRST_FAILED_PATH),
        "secondPassDoneCount": line_count(SECOND_DONE_PATH),
        "secondPassFailedCount": line_count(SECOND_FAILED_PATH),
        "pendingSecondPassCount": line_count(PENDING_PATH),
        "resolutionStatusCounts": dict(status_counts),
        "compatStatusCounts": dict(compat_counts),
        "domainResolutionStatusCounts": {domain: dict(counter) for domain, counter in sorted(domain_status.items())},
        "firstPassFailedItems": read_non_empty_lines(FIRST_FAILED_PATH),
        "secondPassFailedItems": read_non_empty_lines(SECOND_FAILED_PATH),
        "sample": serialized[:50],
        "total": total,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit({"event": "completed", "summary_path": str(SUMMARY_PATH), "run_prefix": RUN_PREFIX})


def ensure_first_pass_artifacts() -> tuple[list[str], list[FirstPassBatch]]:
    if RESUMED:
        if not COHORT_PATH.exists() or not FIRST_BATCHES_PATH.exists():
            raise RuntimeError(
                f"resume requested but artifacts missing for run {RUN_PREFIX}: "
                f"itemids={COHORT_PATH.exists()} batches={FIRST_BATCHES_PATH.exists()}"
            )

        cohort = read_non_empty_lines(COHORT_PATH)
        batches = load_first_pass_batches(FIRST_BATCHES_PATH)

        if not FIRST_DONE_PATH.exists():
            FIRST_DONE_PATH.write_text("", encoding="utf-8")
        if not FIRST_FAILED_PATH.exists():
            FIRST_FAILED_PATH.write_text("", encoding="utf-8")

        emit(
            {
                "event": "first_pass_resume_loaded",
                "run_prefix": RUN_PREFIX,
                "total": len(cohort),
                "batch_total": len(batches),
                "done": line_count(FIRST_DONE_PATH),
                "failed": line_count(FIRST_FAILED_PATH),
                "retry_failed_first_pass": RETRY_FAILED_FIRST_PASS,
            }
        )
        return cohort, batches

    cohort = build_cohort(LIMIT, COHORT_PATH)
    batches = build_first_pass_batches(cohort, FIRST_BATCHES_PATH, FIRST_PASS_BATCH_SIZE)
    return cohort, batches


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    emit(
        {
            "event": "orchestrator_bootstrap",
            "run_prefix": RUN_PREFIX,
            "prefix_base": BASE_PREFIX,
            "resumed": RESUMED,
            "resume_mode": RESUME_MODE,
            "workers": WORKERS,
            "limit": LIMIT,
            "first_pass_batch_size": FIRST_PASS_BATCH_SIZE,
            "ai_timeout_sec": AI_TIMEOUT_SEC,
            "cli_timeout_sec": CLI_TIMEOUT_SEC,
            "first_pass_retry_max": FIRST_PASS_RETRY_MAX,
            "second_pass_retry_max": SECOND_PASS_RETRY_MAX,
            "retry_failed_first_pass": RETRY_FAILED_FIRST_PASS,
        }
    )

    write_state(status="initializing", phase="bootstrap")

    try:
        cohort, batches = ensure_first_pass_artifacts()
        total = len(cohort)
        refresh_counts(total=total)

        run_first_pass_phase(batches=batches, total=total, resumed=RESUMED)
        refresh_counts(total=total)

        pending_item_ids = build_pending_second_pass(cohort, PENDING_PATH)
        refresh_counts(total=total)

        run_second_pass_phase(pending_item_ids, total=total)
        refresh_counts(total=total)

        write_summary(cohort, total=total)
        refresh_counts(total=total)

        record_final_state(status="completed", phase="completed")
        return 0
    except KeyboardInterrupt:
        error = TERMINATION_REQUESTED or "KeyboardInterrupt"
        emit({"event": "orchestrator_interrupted", "run_prefix": RUN_PREFIX, "error": error})
        record_final_state(status="failed", phase="terminated", error=error)
        return 130
    except BaseException as exc:
        emit({"event": "orchestrator_failed", "run_prefix": RUN_PREFIX, "error": f"{exc.__class__.__name__}: {exc}"})
        record_final_state(status="failed", phase="failed", error=f"{exc.__class__.__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
