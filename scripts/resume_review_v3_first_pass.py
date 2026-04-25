#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class FirstPassBatch:
    business_domain: str
    item_ids: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resume review-v3 first-pass from an existing run prefix, only processing unfinished batches."
    )
    parser.add_argument("--prefix", required=True, help="Run prefix, e.g. review-v3-full-active-20260412-000645")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--ai-timeout-sec", type=int, default=90)
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--watch-log", default="", help="Optional watch log path to append JSONL events")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Also retry batches recorded in .first-pass.failed instead of treating them as already processed.",
    )
    return parser.parse_args()


def read_non_empty_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]


def load_batches(path: Path) -> list[FirstPassBatch]:
    batches: list[FirstPassBatch] = []
    for raw in read_non_empty_lines(path):
        if "|" not in raw:
            continue
        domain, ids_raw = raw.split("|", 1)
        item_ids = tuple(x.strip() for x in ids_raw.split(",") if x.strip())
        if not domain.strip() or not item_ids:
            continue
        batches.append(FirstPassBatch(business_domain=domain.strip(), item_ids=item_ids))
    return batches


def detect_watch_log(reports_dir: Path, prefix: str) -> Path | None:
    if "-" not in prefix:
        return None
    # prefix pattern: <base>-YYYYMMDD-HHMMSS
    m = re.match(r"^(.*)-\d{8}-\d{6}$", prefix)
    if not m:
        return None
    base = m.group(1)
    candidates = sorted(
        reports_dir.glob(f"{base}-watch-*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def append_lines(path: Path, lines: list[str], lock: Lock) -> None:
    if not lines:
        return
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(f"{line}\n")


def rewrite_lines(path: Path, values: set[str], lock: Lock) -> None:
    ordered = sorted(values)
    with lock:
        path.write_text("\n".join(ordered) + ("\n" if ordered else ""), encoding="utf-8")


def append_json(path: Path | None, obj: dict, lock: Lock) -> None:
    if path is None:
        return
    line = json.dumps(obj, ensure_ascii=False)
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def run_first_pass_batch(root_dir: Path, ai_timeout_sec: int, batch: FirstPassBatch) -> tuple[FirstPassBatch, int, str]:
    python_bin = root_dir / ".venv/bin/python"
    if not python_bin.exists():
        python_bin = Path(sys.executable)
    command = [
        str(python_bin),
        "-m",
        "goofish_insight.cli",
        "review-v3-first-pass-batch",
        batch.business_domain,
        "--item-ids",
        ",".join(batch.item_ids),
        "--ai-timeout-sec",
        str(ai_timeout_sec),
        "--executor",
        "direct",
        "--force",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = "apps/collector/src"
    env["AI_TIMEOUT_SEC"] = str(ai_timeout_sec)
    completed = subprocess.run(
        command,
        cwd=root_dir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    return batch, completed.returncode, (completed.stderr or "").strip()


def main() -> int:
    args = parse_args()
    root_dir = Path(__file__).resolve().parents[1]
    reports_dir = (root_dir / args.reports_dir).resolve()

    done_path = reports_dir / f"{args.prefix}.first-pass.done"
    failed_path = reports_dir / f"{args.prefix}.first-pass.failed"
    batches_path = reports_dir / f"{args.prefix}.first-pass.batches"

    if not batches_path.exists():
        print(json.dumps({"event": "resume_error", "reason": "batches_file_missing", "path": str(batches_path)}, ensure_ascii=False))
        return 1

    watch_log: Path | None
    if args.watch_log.strip():
        watch_log = Path(args.watch_log).expanduser().resolve()
    else:
        watch_log = detect_watch_log(reports_dir, args.prefix)

    done_set = set(read_non_empty_lines(done_path))
    failed_set = set(read_non_empty_lines(failed_path))
    retryable_failed_set = failed_set if args.retry_failed else set()
    processed_set = done_set | (failed_set - retryable_failed_set)

    batches = load_batches(batches_path)
    pending_batches = [batch for batch in batches if not set(batch.item_ids).issubset(processed_set)]

    counters = {
        "completed_item_count": len(done_set),
        "failed_item_count": len(failed_set),
    }

    io_lock = Lock()

    start_event = {
        "event": "first_pass_resume_started",
        "prefix": args.prefix,
        "workers": max(args.workers, 1),
        "ai_timeout_sec": max(args.ai_timeout_sec, 5),
        "batch_total": len(batches),
        "batch_pending": len(pending_batches),
        "completed_item_count": counters["completed_item_count"],
        "failed_item_count": counters["failed_item_count"],
        "retry_failed": args.retry_failed,
        "retry_failed_item_count": len(retryable_failed_set),
    }
    print(json.dumps(start_event, ensure_ascii=False))
    append_json(watch_log, start_event, io_lock)

    if not pending_batches:
        done_event = {
            "event": "first_pass_resume_completed",
            "prefix": args.prefix,
            "completed_item_count": counters["completed_item_count"],
            "failed_item_count": counters["failed_item_count"],
            "batch_processed": 0,
        }
        print(json.dumps(done_event, ensure_ascii=False))
        append_json(watch_log, done_event, io_lock)
        return 0

    workers = max(args.workers, 1)
    ai_timeout_sec = max(args.ai_timeout_sec, 5)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(run_first_pass_batch, root_dir, ai_timeout_sec, batch) for batch in pending_batches]
        for future in as_completed(futures):
            batch, returncode, stderr = future.result()

            if returncode == 0:
                retried_ids = [item_id for item_id in batch.item_ids if item_id in failed_set]
                if retried_ids:
                    failed_set.difference_update(retried_ids)
                    rewrite_lines(failed_path, failed_set, io_lock)
                    counters["failed_item_count"] = max(counters["failed_item_count"] - len(retried_ids), 0)

                new_ids = [item_id for item_id in batch.item_ids if item_id not in done_set]
                if new_ids:
                    append_lines(done_path, new_ids, io_lock)
                    done_set.update(new_ids)
                    counters["completed_item_count"] += len(new_ids)
            else:
                new_ids = [item_id for item_id in batch.item_ids if item_id not in done_set and item_id not in failed_set]
                if new_ids:
                    append_lines(failed_path, new_ids, io_lock)
                    failed_set.update(new_ids)
                    counters["failed_item_count"] += len(new_ids)

                if stderr:
                    fail_event = {
                        "event": "first_pass_batch_failed",
                        "business_domain": batch.business_domain,
                        "item_ids": list(batch.item_ids),
                        "stderr": stderr[-800:],
                    }
                    print(json.dumps(fail_event, ensure_ascii=False))
                    append_json(watch_log, fail_event, io_lock)

            progress_event = {
                "event": "first_pass_batch_completed",
                "business_domain": batch.business_domain,
                "batch_size": len(batch.item_ids),
                "completed_item_count": counters["completed_item_count"],
                "failed_item_count": counters["failed_item_count"],
                "resume": True,
            }
            print(json.dumps(progress_event, ensure_ascii=False))
            append_json(watch_log, progress_event, io_lock)

    done_event = {
        "event": "first_pass_resume_completed",
        "prefix": args.prefix,
        "completed_item_count": counters["completed_item_count"],
        "failed_item_count": counters["failed_item_count"],
        "batch_processed": len(pending_batches),
    }
    print(json.dumps(done_event, ensure_ascii=False))
    append_json(watch_log, done_event, io_lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
