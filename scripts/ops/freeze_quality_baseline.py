#!/usr/bin/env python3
"""Freeze a data-quality baseline snapshot for Phase 1.

The script can be run in partial mode while the first 7-day window is still filling,
and in strict mode once the baseline window is ready.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
COLLECTOR_SRC = ROOT_DIR / "apps" / "collector" / "src"
if str(COLLECTOR_SRC) not in sys.path:
    sys.path.insert(0, str(COLLECTOR_SRC))

from goofish_insight.application.services.quality_metrics import QualityMetricsService
from goofish_insight.settings import get_settings

DEFAULT_METRIC_KEYS = (
    "collection_success_rate",
    "risk_hit_rate",
    "analyzer_job_success_rate",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze data-quality baseline metrics.")
    parser.add_argument("--days", type=int, default=7, help="Baseline lookback window in days.")
    parser.add_argument(
        "--metric-key",
        action="append",
        dest="metric_keys",
        help="Metric key to include. Can be passed multiple times. Defaults to Phase 1 W8 core metrics.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Write the report even when some metrics have no samples yet.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path. Defaults to reports/baselines/quality-baseline-YYYYMMDD.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    metric_keys = tuple(args.metric_keys or DEFAULT_METRIC_KEYS)
    today = date.today()

    output_path = Path(args.output) if args.output else Path(
        f"reports/baselines/quality-baseline-{today.isoformat()}.json"
    )
    if not output_path.is_absolute():
        output_path = settings.base_dir / output_path

    summaries: list[dict[str, Any]] = []
    missing: list[str] = []
    for metric_key in metric_keys:
        summary = QualityMetricsService.get_baseline_window(metric_key=metric_key, days=args.days)
        summaries.append(summary)
        if int(summary.get("sample_count") or 0) == 0:
            missing.append(metric_key)

    report = {
        "ok": not missing or bool(args.allow_partial),
        "frozenAt": datetime.now(timezone.utc).isoformat(),
        "windowDays": args.days,
        "allowPartial": bool(args.allow_partial),
        "metricKeys": list(metric_keys),
        "missingMetricKeys": missing,
        "summaries": summaries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

    if missing and not args.allow_partial:
        print(f"baseline has missing metrics: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
