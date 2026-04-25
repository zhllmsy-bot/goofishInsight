#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "apps/collector/src"))

from goofish_insight.db import SessionLocal  # noqa: E402
from goofish_insight.models import Item, ItemReviewV3  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize an existing review-v3 run prefix with second-pass and summary.")
    parser.add_argument("--prefix", required=True, help="Existing run prefix, e.g. review-v3-full-active-20260412-000645")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--ai-timeout-sec", type=int, default=90)
    parser.add_argument("--reports-dir", default="reports")
    return parser.parse_args()


def _python_bin() -> str:
    candidate = ROOT_DIR / ".venv/bin/python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _base_env(ai_timeout_sec: int) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = "apps/collector/src"
    env["AI_TIMEOUT_SEC"] = str(ai_timeout_sec)
    return env


def _write_lines(path: Path, values: list[str]) -> None:
    if not values:
        return
    with path.open("a", encoding="utf-8") as handle:
        for value in values:
            handle.write(f"{value}\n")


def _read_non_empty_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_pending_second_pass(*, cohort: list[str], out: Path) -> list[str]:
    with SessionLocal() as session:
        rows = session.execute(
            select(Item.item_id)
            .join(ItemReviewV3, ItemReviewV3.item_id_ref == Item.id)
            .where(Item.item_id.in_(cohort), ItemReviewV3.resolution_status == "PENDING_REVIEW")
        ).scalars().all()
    out.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    print(json.dumps({"event": "pending_second_pass_built", "count": len(rows), "path": str(out)}, ensure_ascii=False))
    return list(rows)


def run_second_pass_item(*, item_id: str, ai_timeout_sec: int) -> tuple[str, int, str]:
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
        str(ai_timeout_sec),
        "--executor",
        "direct",
        "--force",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT_DIR,
        env=_base_env(ai_timeout_sec),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    return item_id, completed.returncode, completed.stderr.strip()


def run_second_pass_phase(
    *,
    item_ids: list[str],
    workers: int,
    ai_timeout_sec: int,
    second_done_path: Path,
    second_failed_path: Path,
) -> None:
    second_done_path.write_text("", encoding="utf-8")
    second_failed_path.write_text("", encoding="utf-8")
    if not item_ids:
        return

    completed_item_count = 0
    failed_item_count = 0
    with ThreadPoolExecutor(max_workers=max(workers, 1)) as executor:
        futures = [
            executor.submit(run_second_pass_item, item_id=item_id, ai_timeout_sec=max(ai_timeout_sec, 5))
            for item_id in item_ids
        ]
        for future in as_completed(futures):
            item_id, returncode, stderr = future.result()
            target_path = second_done_path if returncode == 0 else second_failed_path
            _write_lines(target_path, [item_id])
            if returncode == 0:
                completed_item_count += 1
            else:
                failed_item_count += 1
            if stderr and returncode != 0:
                print(
                    json.dumps(
                        {
                            "event": "second_pass_item_failed",
                            "item_id": item_id,
                            "stderr": stderr[-800:],
                        },
                        ensure_ascii=False,
                    )
                )
            print(
                json.dumps(
                    {
                        "event": "second_pass_item_completed",
                        "item_id": item_id,
                        "completed_item_count": completed_item_count,
                        "failed_item_count": failed_item_count,
                    },
                    ensure_ascii=False,
                )
            )


def write_summary(
    *,
    cohort: list[str],
    prefix: str,
    summary_path: Path,
    pending_path: Path,
    first_done_path: Path,
    first_failed_path: Path,
    second_done_path: Path,
    second_failed_path: Path,
    workers: int,
    started_at: str,
) -> None:
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
        "startedAt": started_at,
        "prefix": prefix,
        "cohortCount": len(cohort),
        "workers": workers,
        "firstPassDoneCount": len(_read_non_empty_lines(first_done_path)),
        "firstPassFailedCount": len(_read_non_empty_lines(first_failed_path)),
        "secondPassDoneCount": len(_read_non_empty_lines(second_done_path)),
        "secondPassFailedCount": len(_read_non_empty_lines(second_failed_path)),
        "pendingSecondPassCount": len(_read_non_empty_lines(pending_path)),
        "resolutionStatusCounts": dict(status_counts),
        "compatStatusCounts": dict(compat_counts),
        "domainResolutionStatusCounts": {domain: dict(counter) for domain, counter in sorted(domain_status.items())},
        "firstPassFailedItems": _read_non_empty_lines(first_failed_path),
        "secondPassFailedItems": _read_non_empty_lines(second_failed_path),
        "sample": serialized[:50],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"event": "completed", "summary_path": str(summary_path)}, ensure_ascii=False))


def main() -> int:
    args = parse_args()
    reports_dir = (ROOT_DIR / args.reports_dir).resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)

    prefix = args.prefix.strip()
    cohort_path = reports_dir / f"{prefix}.itemids.txt"
    first_done_path = reports_dir / f"{prefix}.first-pass.done"
    first_failed_path = reports_dir / f"{prefix}.first-pass.failed"
    pending_path = reports_dir / f"{prefix}.pending-second-pass.txt"
    second_done_path = reports_dir / f"{prefix}.second-pass.done"
    second_failed_path = reports_dir / f"{prefix}.second-pass.failed"
    summary_path = reports_dir / f"{prefix}.final-summary.json"

    if not cohort_path.exists():
        print(json.dumps({"event": "finalize_error", "reason": "cohort_missing", "path": str(cohort_path)}, ensure_ascii=False))
        return 1

    cohort = _read_non_empty_lines(cohort_path)
    if not cohort:
        print(json.dumps({"event": "finalize_error", "reason": "empty_cohort", "path": str(cohort_path)}, ensure_ascii=False))
        return 1

    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pending_item_ids = build_pending_second_pass(cohort=cohort, out=pending_path)
    run_second_pass_phase(
        item_ids=pending_item_ids,
        workers=args.workers,
        ai_timeout_sec=args.ai_timeout_sec,
        second_done_path=second_done_path,
        second_failed_path=second_failed_path,
    )
    write_summary(
        cohort=cohort,
        prefix=prefix,
        summary_path=summary_path,
        pending_path=pending_path,
        first_done_path=first_done_path,
        first_failed_path=first_failed_path,
        second_done_path=second_done_path,
        second_failed_path=second_failed_path,
        workers=args.workers,
        started_at=started_at,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
