#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "$0")/.." && pwd)"
REPORTS_DIR="$ROOT_DIR/reports"
TARGET_PREFIX=""
JSON_MODE=0

usage() {
  cat <<'EOF'
Usage:
  ./scripts/show-review-v3-progress.sh [--json] [--prefix <run-prefix>] [--reports-dir <path>]

Options:
  --json                 Print machine-readable JSON.
  --prefix <run-prefix>  Inspect an explicit run prefix, for example:
                         review-v3-full-active-20260412-000645
  --reports-dir <path>   Override reports directory (default: <repo>/reports).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)
      JSON_MODE=1
      shift
      ;;
    --prefix)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --prefix" >&2
        exit 1
      fi
      TARGET_PREFIX="$2"
      shift 2
      ;;
    --reports-dir)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --reports-dir" >&2
        exit 1
      fi
      REPORTS_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

python3 - "$REPORTS_DIR" "$TARGET_PREFIX" "$JSON_MODE" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


reports_dir = Path(sys.argv[1]).expanduser()
target_prefix = str(sys.argv[2] or "").strip()
json_mode = str(sys.argv[3]).strip() == "1"
repo_root = reports_dir.parent
stale_sec_threshold = 180


def count_non_empty_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for line in handle if line.strip())


def parse_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def parse_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    return None


def iso_mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def mtime_age_seconds(path: Path | None) -> int | None:
    if path is None or not path.exists():
        return None
    return max(int(datetime.now().timestamp() - path.stat().st_mtime), 0)


def most_recent_age_seconds(paths: list[Path]) -> int | None:
    ages = [mtime_age_seconds(path) for path in paths]
    valid = [age for age in ages if age is not None]
    if not valid:
        return None
    return min(valid)


def serialize_json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone().isoformat(timespec="seconds")
    if isinstance(value, dict):
        return {str(key): serialize_json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [serialize_json_safe(item) for item in value]
    return value


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def resolve_prefix_from_watch(path: Path) -> str | None:
    entries = parse_json_lines(path)
    cohort_entry = next(
        (
            entry
            for entry in reversed(entries)
            if str(entry.get("event") or "") == "cohort_created" and isinstance(entry.get("path"), str)
        ),
        None,
    )
    if cohort_entry:
        cohort_path = Path(str(cohort_entry["path"]))
        name = cohort_path.name
        if name.endswith(".itemids.txt"):
            return name[: -len(".itemids.txt")]

    start_entry = next(
        (
            entry
            for entry in entries
            if str(entry.get("event") or "") == "starting_full_backfill" and isinstance(entry.get("prefix"), str)
        ),
        None,
    )
    if start_entry:
        stem = str(start_entry["prefix"]).strip()
        if stem:
            candidates = sorted(
                reports_dir.glob(f"{stem}-*.itemids.txt"),
                key=lambda candidate: candidate.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                return candidates[0].name[: -len(".itemids.txt")]
    return None


@dataclass
class Selection:
    prefix: str
    watch_log: Path | None
    watch_entries: list[dict[str, Any]]
    run_state_path: Path | None
    run_state: dict[str, Any] | None


def pick_selection() -> Selection | None:
    watch_logs = sorted(
        reports_dir.glob("review-v3-*-watch-*.log"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    run_state_files = sorted(
        reports_dir.glob("review-v3-*.run-state.json"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )

    if target_prefix:
        run_state_path = reports_dir / f"{target_prefix}.run-state.json"
        run_state = parse_json_file(run_state_path)

        explicit_watch = None
        explicit_entries: list[dict[str, Any]] = []
        for candidate in watch_logs:
            entries = parse_json_lines(candidate)
            if any(target_prefix in json.dumps(entry, ensure_ascii=False) for entry in entries):
                explicit_watch = candidate
                explicit_entries = entries
                break

        return Selection(
            prefix=target_prefix,
            watch_log=explicit_watch,
            watch_entries=explicit_entries,
            run_state_path=run_state_path if run_state_path.exists() else None,
            run_state=run_state,
        )

    state_candidates: list[tuple[int, int, float, str, Path, dict[str, Any] | None]] = []
    for state_path in run_state_files:
        prefix = state_path.name[: -len(".run-state.json")]
        if not (reports_dir / f"{prefix}.itemids.txt").exists():
            continue
        state_data = parse_json_file(state_path)
        status = str((state_data or {}).get("status") or "")
        counts = (state_data or {}).get("counts") if isinstance((state_data or {}).get("counts"), dict) else {}
        remaining = int(counts.get("first_pass_remaining", 0) or 0)
        is_incomplete = 1 if (status not in {"completed"} or remaining > 0) else 0
        is_full_active = 1 if prefix.startswith("review-v3-full-active-") else 0
        state_candidates.append((is_incomplete, is_full_active, state_path.stat().st_mtime, prefix, state_path, state_data))

    preferred_state_candidates = [candidate for candidate in state_candidates if candidate[0] == 1 or candidate[1] == 1]
    if preferred_state_candidates:
        preferred_state_candidates.sort(reverse=True)
        _, _, _, prefix, state_path, state_data = preferred_state_candidates[0]
        matched_watch = None
        matched_entries: list[dict[str, Any]] = []
        for candidate in watch_logs:
            entries = parse_json_lines(candidate)
            if any(prefix in json.dumps(entry, ensure_ascii=False) for entry in entries):
                matched_watch = candidate
                matched_entries = entries
                break
        return Selection(
            prefix=prefix,
            watch_log=matched_watch,
            watch_entries=matched_entries,
            run_state_path=state_path,
            run_state=state_data,
        )

    latest_itemids = sorted(
        reports_dir.glob("review-v3-*.itemids.txt"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    if latest_itemids:
        itemid_candidates: list[tuple[int, int, float, str]] = []
        for candidate in latest_itemids:
            prefix = candidate.name[: -len(".itemids.txt")]
            is_full_active = 1 if prefix.startswith("review-v3-full-active-") else 0
            is_incomplete = 0 if (reports_dir / f"{prefix}.final-summary.json").exists() else 1
            itemid_candidates.append((is_incomplete, is_full_active, candidate.stat().st_mtime, prefix))

        preferred_itemids = [candidate for candidate in itemid_candidates if candidate[1] == 1]
        if not preferred_itemids:
            preferred_itemids = itemid_candidates
        preferred_itemids.sort(reverse=True)
        _, _, _, prefix = preferred_itemids[0]

        run_state_path = reports_dir / f"{prefix}.run-state.json"
        matched_watch = None
        matched_entries: list[dict[str, Any]] = []
        for candidate in watch_logs:
            entries = parse_json_lines(candidate)
            if any(prefix in json.dumps(entry, ensure_ascii=False) for entry in entries):
                matched_watch = candidate
                matched_entries = entries
                break
        return Selection(
            prefix=prefix,
            watch_log=matched_watch,
            watch_entries=matched_entries,
            run_state_path=run_state_path if run_state_path.exists() else None,
            run_state=parse_json_file(run_state_path),
        )

    for candidate in watch_logs:
        entries = parse_json_lines(candidate)
        prefix = resolve_prefix_from_watch(candidate)
        if prefix:
            itemids = reports_dir / f"{prefix}.itemids.txt"
            if itemids.exists():
                run_state_path = reports_dir / f"{prefix}.run-state.json"
                return Selection(
                    prefix=prefix,
                    watch_log=candidate,
                    watch_entries=entries,
                    run_state_path=run_state_path if run_state_path.exists() else None,
                    run_state=parse_json_file(run_state_path),
                )
    return None


def detect_active_workers() -> dict[str, int]:
    pattern_groups = {
        "cli_review_workers": [
            r"goofish_insight\.cli review-v3-(first-pass-batch|second-pass)",
        ],
        "orchestrator_workers": [
            r"run_review_v3_top_items_orchestrator\.py",
            r"resume_review_v3_first_pass\.py",
            r"finalize_review_v3_run\.py",
        ],
    }
    all_lines: set[str] = set()
    grouped_lines: dict[str, set[str]] = {key: set() for key in pattern_groups}

    for group, patterns in pattern_groups.items():
        for pattern in patterns:
            try:
                output = subprocess.check_output(["pgrep", "-af", pattern], text=True, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                continue
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                all_lines.add(line)
                grouped_lines[group].add(line)

    return {
        "total": len(all_lines),
        "cli_review_workers": len(grouped_lines["cli_review_workers"]),
        "orchestrator_workers": len(grouped_lines["orchestrator_workers"]),
    }


def load_db_overview() -> dict[str, Any] | None:
    collector_src = repo_root / "apps" / "collector" / "src"
    if not collector_src.exists():
        return None
    if str(collector_src) not in sys.path:
        sys.path.insert(0, str(collector_src))
    try:
        from sqlalchemy import func, select

        from goofish_insight.application.services.review_progress_page import (
            build_llm_review_overview,
            build_llm_review_progress,
        )
        from goofish_insight.db import SessionLocal
        from goofish_insight.models import Item
    except Exception as exc:  # pragma: no cover - operational fallback
        return {"error": f"db_overview_import_failed: {exc.__class__.__name__}"}

    try:
        with SessionLocal() as session:
            progress_rows = build_llm_review_progress(session, business_domain=None)
            overview = build_llm_review_overview(progress_rows)
            active_total = int(
                session.execute(
                    select(func.count()).select_from(Item).where(Item.is_active.is_(True))
                ).scalar_one()
            )
        payload = serialize_json_safe(dict(overview))
        payload["active_items_total"] = active_total
        return payload
    except Exception as exc:  # pragma: no cover - operational fallback
        return {"error": f"db_overview_query_failed: {exc.__class__.__name__}"}


if not reports_dir.exists():
    print(f"reports directory not found: {reports_dir}", file=sys.stderr)
    sys.exit(1)

selection = pick_selection()
if selection is None:
    print("no review-v3 artifacts found", file=sys.stderr)
    sys.exit(1)

prefix = selection.prefix
paths = {
    "itemids": reports_dir / f"{prefix}.itemids.txt",
    "first_pass_done": reports_dir / f"{prefix}.first-pass.done",
    "first_pass_failed": reports_dir / f"{prefix}.first-pass.failed",
    "first_pass_batches": reports_dir / f"{prefix}.first-pass.batches",
    "pending_second_pass": reports_dir / f"{prefix}.pending-second-pass.txt",
    "second_pass_done": reports_dir / f"{prefix}.second-pass.done",
    "second_pass_failed": reports_dir / f"{prefix}.second-pass.failed",
    "final_summary": reports_dir / f"{prefix}.final-summary.json",
    "second_pass_summary": reports_dir / f"{prefix}.second-pass-summary.json",
    "run_state": reports_dir / f"{prefix}.run-state.json",
}

total = count_non_empty_lines(paths["itemids"])
first_done = count_non_empty_lines(paths["first_pass_done"])
first_failed = count_non_empty_lines(paths["first_pass_failed"])
first_remaining = max(total - first_done - first_failed, 0)
first_percent = round((first_done / total) * 100, 2) if total > 0 else 0.0

pending_second_pass = count_non_empty_lines(paths["pending_second_pass"])
second_done = count_non_empty_lines(paths["second_pass_done"])
second_failed = count_non_empty_lines(paths["second_pass_failed"])
second_seed = pending_second_pass + second_done + second_failed
second_percent = round((second_done / second_seed) * 100, 2) if second_seed > 0 else None

last_event = selection.watch_entries[-1] if selection.watch_entries else None
active_workers = detect_active_workers()
active_worker_total = int(active_workers.get("total", 0))
orchestrator_worker_count = int(active_workers.get("orchestrator_workers", 0))
db_overview = load_db_overview()
run_state = selection.run_state if isinstance(selection.run_state, dict) else None
run_state_status = str((run_state or {}).get("status") or "")
run_state_phase = str((run_state or {}).get("phase") or "")
run_state_updated = parse_iso((run_state or {}).get("updated_at"))
stale_seconds = None
if run_state_updated is not None:
    stale_seconds = int((datetime.now(timezone.utc) - run_state_updated.astimezone(timezone.utc)).total_seconds())
watch_stale_seconds = mtime_age_seconds(selection.watch_log)
progress_signal_stale_seconds = most_recent_age_seconds(
    [
        paths["first_pass_done"],
        paths["first_pass_failed"],
        paths["second_pass_done"],
        paths["second_pass_failed"],
        paths["pending_second_pass"],
    ]
)
is_recent_signal = any(
    value is not None and value <= stale_sec_threshold for value in [watch_stale_seconds, progress_signal_stale_seconds]
)
run_state_active_statuses = {
    "running_first_pass",
    "retry_backoff_first_pass",
    "running_second_pass",
    "retry_backoff_second_pass",
    "writing_summary",
    "initializing",
}
run_state_quota_statuses = {
    "quota_waiting_first_pass",
    "quota_waiting_second_pass",
}

status = "idle"
if run_state_status == "completed":
    status = "completed"
elif run_state_status == "failed":
    status = "failed"
elif run_state_status in run_state_quota_statuses:
    if stale_seconds is not None and stale_seconds > stale_sec_threshold:
        status = "stalled"
    else:
        status = "quota_waiting"
elif run_state_status in run_state_active_statuses:
    if stale_seconds is not None and stale_seconds > stale_sec_threshold:
        status = "stalled"
    elif run_state_status.startswith("retry_backoff"):
        status = "retry_backoff"
    elif orchestrator_worker_count > 0 or (stale_seconds is not None and stale_seconds <= stale_sec_threshold):
        status = "running"
    else:
        status = "waiting"
elif active_worker_total > 0 and is_recent_signal:
    status = "running"
elif total > 0 and first_done + first_failed < total:
    status = "stalled"
elif total > 0 and first_done + first_failed >= total:
    status = "first_pass_completed"

payload = {
    "status": status,
    "prefix": prefix,
    "run_prefix": prefix,
    "reports_dir": str(reports_dir),
    "watch_log": str(selection.watch_log) if selection.watch_log else None,
    "watch_log_updated_at": iso_mtime(selection.watch_log) if selection.watch_log else None,
    "watch_log_stale_seconds": watch_stale_seconds,
    "run_state": run_state,
    "run_state_path": str(selection.run_state_path) if selection.run_state_path else None,
    "run_state_updated_at": run_state_updated.astimezone().isoformat(timespec="seconds") if run_state_updated else None,
    "run_state_stale_seconds": stale_seconds,
    "run_state_phase": run_state_phase,
    "progress_signal_stale_seconds": progress_signal_stale_seconds,
    "active_review_workers": active_worker_total,
    "active_review_worker_details": active_workers,
    "db_overview": db_overview,
    "counts": {
        "total": total,
        "first_pass_done": first_done,
        "first_pass_failed": first_failed,
        "first_pass_remaining": first_remaining,
        "first_pass_completion_percent": first_percent,
        "first_pass_batch_count": count_non_empty_lines(paths["first_pass_batches"]),
        "pending_second_pass": pending_second_pass,
        "second_pass_done": second_done,
        "second_pass_failed": second_failed,
        "second_pass_seed_total": second_seed,
        "second_pass_completion_percent": second_percent,
    },
    "files": {
        name: str(path)
        for name, path in paths.items()
        if path.exists()
    },
    "file_updated_at": {
        name: iso_mtime(path)
        for name, path in paths.items()
        if path.exists()
    },
    "last_watch_event": last_event,
    "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
}

if json_mode:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(0)

print(f"status={payload['status']}")
print(f"run_prefix={payload['run_prefix']}")
print(
    "active_review_workers="
    f"{payload['active_review_workers']} "
    f"details={payload['active_review_worker_details']}"
)
print(
    "run_first_pass: "
    f"done={first_done} failed={first_failed} total={total} "
    f"remaining={first_remaining} progress={first_percent:.2f}%"
)
if second_seed > 0:
    print(
        "run_second_pass: "
        f"done={second_done} failed={second_failed} seed_total={second_seed} "
        f"pending_file_count={pending_second_pass} progress={second_percent:.2f}%"
    )
else:
    print("run_second_pass: seed_total=0 (not started or no second-pass items)")
if isinstance(db_overview, dict) and db_overview.get("error"):
    print(f"db_overview_error={db_overview['error']}")
elif isinstance(db_overview, dict):
    print(
        "db_overview: "
        f"reviewed={db_overview.get('reviewed_total', 0)}/{db_overview.get('review_target_total', 0)} "
        f"completion={float(db_overview.get('completion_percent', 0.0)):.1f}% "
        f"pending={db_overview.get('pending_review_count', 0)} "
        f"pending_audit={db_overview.get('pending_audit_count', 0)} "
        f"in_progress={db_overview.get('in_progress_count', 0)}"
    )
if run_state:
    print(
        "run_state: "
        f"status={run_state_status or '-'} "
        f"phase={run_state_phase or '-'} "
        f"stale_seconds={stale_seconds if stale_seconds is not None else '-'}"
    )
if selection.watch_log:
    print(f"watch_log={selection.watch_log}")
    if last_event:
        print(f"last_event={last_event.get('event')}")
print(f"generated_at={payload['generated_at']}")
PY
