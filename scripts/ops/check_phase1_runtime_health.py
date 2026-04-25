#!/usr/bin/env python3
"""Phase 0-1 temporary runtime health check.

This is intentionally lightweight: it reuses the runtime control panel contract,
writes a JSON report, and exits non-zero when monitored checks are unhealthy.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
COLLECTOR_SRC = ROOT_DIR / "apps" / "collector" / "src"
if str(COLLECTOR_SRC) not in sys.path:
    sys.path.insert(0, str(COLLECTOR_SRC))

from goofish_insight.application.services.runtime_controls import build_runtime_control_panel_data
from goofish_insight.settings import get_settings

DEFAULT_GROUP_KEYS = ("quality_metrics",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Phase 0-1 runtime health and exit non-zero on failure.")
    parser.add_argument(
        "--group-key",
        action="append",
        dest="group_keys",
        help="Runtime group key to monitor. Can be passed multiple times. Defaults to quality_metrics.",
    )
    parser.add_argument(
        "--output",
        default="reports/runtime/phase1-runtime-health.json",
        help="Path for the JSON health report, relative to repo root unless absolute.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = settings.base_dir / output_path

    group_keys = tuple(args.group_keys or DEFAULT_GROUP_KEYS)
    payload = build_runtime_control_panel_data()
    groups_by_key = {str(group.get("key")): group for group in payload.get("groups", [])}

    missing_groups = [key for key in group_keys if key not in groups_by_key]
    failing_checks: list[dict[str, Any]] = []
    monitored_groups: list[dict[str, Any]] = []
    for key in group_keys:
        group = groups_by_key.get(key)
        if group is None:
            continue
        monitored_groups.append(group)
        for check in group.get("checks", []):
            if not bool(check.get("ok")):
                failing_checks.append(
                    {
                        "groupKey": key,
                        "groupTitle": group.get("title"),
                        "label": check.get("label"),
                        "detail": check.get("detail"),
                    }
                )

    report = {
        "ok": not missing_groups and not failing_checks,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "groupKeys": list(group_keys),
        "missingGroups": missing_groups,
        "failingChecks": failing_checks,
        "groups": monitored_groups,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

    if missing_groups:
        print(f"missing runtime groups: {', '.join(missing_groups)}", file=sys.stderr)
        return 2
    if failing_checks:
        rendered = "; ".join(
            f"{item['groupKey']}/{item['label']}: {item['detail']}" for item in failing_checks
        )
        print(f"runtime health check failed: {rendered}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
