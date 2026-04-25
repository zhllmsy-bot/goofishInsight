#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
COLLECTOR_SRC = ROOT_DIR / "apps" / "collector" / "src"
if str(COLLECTOR_SRC) not in sys.path:
    sys.path.insert(0, str(COLLECTOR_SRC))

from goofish_insight.normalizers import normalize_title  # noqa: E402

DEFAULT_FIXTURE_GLOB = "apps/collector/tests/fixtures/rule_replay/*.jsonl"
DEFAULT_REPORT_DIR = ROOT_DIR / "reports" / "rules"
LATEST_REPORT_PATH = DEFAULT_REPORT_DIR / "latest-rule-replay-report.json"
CHECK_WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "balanced": {
        "brand": 1.0,
        "model_family": 1.2,
        "chip": 1.0,
        "memory_gb": 1.0,
        "storage_gb": 1.0,
    },
    "family_focus": {
        "brand": 1.0,
        "model_family": 1.8,
        "chip": 0.8,
        "memory_gb": 0.8,
        "storage_gb": 0.8,
    },
    "spec_focus": {
        "brand": 0.8,
        "model_family": 1.0,
        "chip": 1.2,
        "memory_gb": 1.4,
        "storage_gb": 1.4,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay rule-alias normalization fixtures.")
    parser.add_argument("--fixture", action="append", help="JSONL fixture path. Can be passed multiple times.")
    parser.add_argument("--min-accuracy", type=float, default=0.85)
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional JSON report output path. Defaults to reports/rules/rule-replay-<timestamp>.json",
    )
    args = parser.parse_args()

    fixture_paths = [Path(value) for value in args.fixture or []]
    if not fixture_paths:
        fixture_paths = sorted(ROOT_DIR.glob(DEFAULT_FIXTURE_GLOB))

    records = []
    for path in fixture_paths:
        records.extend(_load_fixture(path))

    results = [_evaluate_record(record) for record in records]
    total_checks = sum(result["checkCount"] for result in results)
    passed_checks = sum(result["passCount"] for result in results)
    accuracy = (passed_checks / total_checks) if total_checks else 0.0
    grouped = _group_results_by_fixture(results)
    per_fixture = [_summarize_fixture(fixture, rows, args.min_accuracy) for fixture, rows in sorted(grouped.items())]
    generated_at = datetime.now().astimezone().isoformat()
    report_output = _resolve_output_path(args.output, generated_at)
    _write_json(report_output, _json_ready_placeholder())
    report = {
        "generatedAt": generated_at,
        "fixtureCount": len(fixture_paths),
        "recordCount": len(records),
        "checkCount": total_checks,
        "passCount": passed_checks,
        "accuracy": round(accuracy, 4),
        "minAccuracy": args.min_accuracy,
        "status": "pass" if accuracy >= args.min_accuracy else "fail",
        "sampleCountByFixture": {row["fixture"]: row["recordCount"] for row in per_fixture},
        "fixtureSummaries": per_fixture,
        "weightSensitivity": _build_weight_sensitivity(results),
        "failures": [result for result in results if result["passCount"] < result["checkCount"]],
        "reportPath": str(report_output),
    }
    _write_json(report_output, report)
    _write_json(LATEST_REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


def _load_fixture(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        row = json.loads(line)
        row["_fixture"] = str(path)
        row["_fixture_name"] = path.stem
        row["_line"] = line_number
        rows.append(row)
    return rows


def _evaluate_record(record: dict[str, Any]) -> dict[str, Any]:
    actual = normalize_title(str(record.get("title") or ""))
    expected = dict(record.get("expected") or {})
    checks = []
    for field, expected_value in expected.items():
        actual_value = actual.get(field)
        checks.append(
            {
                "field": field,
                "expected": expected_value,
                "actual": actual_value,
                "ok": actual_value == expected_value,
            }
        )
    pass_count = sum(1 for check in checks if check["ok"])
    return {
        "fixture": record.get("_fixture"),
        "fixtureName": record.get("_fixture_name"),
        "line": record.get("_line"),
        "title": record.get("title"),
        "checkCount": len(checks),
        "passCount": pass_count,
        "checks": checks,
    }


def _group_results_by_fixture(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        fixture_name = str(result.get("fixtureName") or "unknown")
        grouped.setdefault(fixture_name, []).append(result)
    return grouped


def _summarize_fixture(
    fixture_name: str,
    rows: list[dict[str, Any]],
    min_accuracy: float,
) -> dict[str, Any]:
    check_count = sum(row["checkCount"] for row in rows)
    pass_count = sum(row["passCount"] for row in rows)
    accuracy = (pass_count / check_count) if check_count else 0.0
    return {
        "fixture": fixture_name,
        "recordCount": len(rows),
        "checkCount": check_count,
        "passCount": pass_count,
        "accuracy": round(accuracy, 4),
        "status": "pass" if accuracy >= min_accuracy else "fail",
    }


def _build_weight_sensitivity(results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped = _group_results_by_fixture(results)
    profiles: list[dict[str, Any]] = []
    for profile_name, weight_map in CHECK_WEIGHT_PROFILES.items():
        fixture_scores: dict[str, float] = {}
        for fixture, rows in grouped.items():
            total_weight = 0.0
            passed_weight = 0.0
            for row in rows:
                for check in row.get("checks", []):
                    field = str(check.get("field") or "")
                    weight = float(weight_map.get(field, 1.0))
                    total_weight += weight
                    if check.get("ok"):
                        passed_weight += weight
            fixture_scores[fixture] = round((passed_weight / total_weight) if total_weight else 0.0, 4)
        profiles.append({"profile": profile_name, "weights": weight_map, "fixtureScores": fixture_scores})
    return {"profiles": profiles}


def _resolve_output_path(output: str | None, generated_at: str) -> Path:
    if output:
        return Path(output).expanduser().resolve()
    timestamp = (
        generated_at.replace("-", "")
        .replace(":", "")
        .replace("+", "_")
        .replace("T", "-")
    )
    return (DEFAULT_REPORT_DIR / f"rule-replay-{timestamp}.json").resolve()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _json_ready_placeholder() -> dict[str, Any]:
    return {"status": "running"}


if __name__ == "__main__":
    raise SystemExit(main())
