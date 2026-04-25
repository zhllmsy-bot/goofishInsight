#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$REPO_ROOT"

resolve_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    printf '%s\n' "$PYTHON_BIN"
    return 0
  fi

  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    printf '%s\n' "$REPO_ROOT/.venv/bin/python"
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  echo "python interpreter not found" >&2
  return 1
}

PYTHON_BIN="$(resolve_python_bin)"

PASS=0
FAIL=0
SKIP=0
RESULTS=()

step() {
  local label="$1"
  local cmd="$2"
  local allow_failure="${3:-false}"

  echo ""
  echo "========================================"
  echo "  $label"
  echo "========================================"

  if eval "$cmd"; then
    RESULTS+=("PASS  $label")
    PASS=$((PASS + 1))
  else
    if [[ "$allow_failure" == "true" ]]; then
      RESULTS+=("SKIP  $label (allowed failure)")
      SKIP=$((SKIP + 1))
    else
      RESULTS+=("FAIL  $label")
      FAIL=$((FAIL + 1))
    fi
  fi
}

run_optional_docker_build() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker not installed; skipping optional docker build"
    return 1
  fi

  "$PYTHON_BIN" - "$REPO_ROOT" <<'PY'
from __future__ import annotations

import shutil
import subprocess
import sys

repo_root = sys.argv[1]
docker_bin = shutil.which("docker")
if not docker_bin:
    print("docker not installed; skipping optional docker build", file=sys.stderr)
    raise SystemExit(1)

def stringify_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value

try:
    result = subprocess.run(
        [docker_bin, "build", "."],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
except subprocess.TimeoutExpired as exc:
    output = stringify_output(exc.stdout) + stringify_output(exc.stderr)
    tail = "\n".join(line for line in output.strip().splitlines()[-5:] if line)
    if tail:
        print(tail)
    print("docker build timed out after 120s", file=sys.stderr)
    raise SystemExit(1)

output = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
tail = "\n".join(output[-5:])
if tail:
    print(tail)
raise SystemExit(result.returncode)
PY
}

echo "Goofish Insight - Delivery Baseline Verification"
echo "Repo: $REPO_ROOT"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

echo "--- P0: Mandatory Gates ---"

step "React typecheck" \
  "npm run typecheck -w @goofish/dashboard-react"

step "React test" \
  "npm run test -w @goofish/dashboard-react"

step "Nest typecheck" \
  "npm run typecheck -w @goofish/dashboard-nest"

step "Nest test" \
  "npm run test:e2e -w @goofish/dashboard-nest -- --runInBand"

step "Python compile" \
  "\"$PYTHON_BIN\" -m compileall apps/collector/src apps/analyzer/src -q"

step "Python selected tests" \
  "PYTHONPATH=apps/collector/src:apps/analyzer/src:packages/schema/src \"$PYTHON_BIN\" -m unittest \
    apps.analyzer.tests.test_daily_metrics_job \
    apps.analyzer.tests.test_model_scores_job \
    apps.analyzer.tests.test_analysis_reports_job \
    apps.analyzer.tests.test_adapter_boundary_contract \
    apps.collector.tests.test_notification_delivery_service \
    apps.collector.tests.test_alert_dispatcher_service \
    apps.collector.tests.test_outreach_outcomes_service \
    apps.collector.tests.test_rule_alias_matcher \
    apps.collector.tests.test_normalizers \
    apps.collector.tests.test_pricing_filters \
    apps.collector.tests.test_catalog_backfill_service \
    apps.collector.tests.test_catalog_migration_checks \
    apps.collector.tests.test_catalog_admin_commands \
    apps.collector.tests.test_webapp_cors \
    apps.collector.tests.test_runtime_controls \
    apps.collector.tests.test_quality_metrics \
    apps.collector.tests.test_collect_runtime_queries \
    apps.collector.tests.test_catalog_models \
    apps.collector.tests.test_review_entrypoints \
    apps.collector.tests.test_buy_entrypoints \
    apps.collector.tests.test_buy_feedback_service \
    apps.collector.tests.test_pricing_entrypoints \
    apps.collector.tests.test_pricing_read_model \
    apps.collector.tests.test_config_entrypoints \
    apps.collector.tests.test_task_config_entrypoints \
    apps.collector.tests.test_template_config_entrypoints"

echo ""
echo "--- P1: Extended Gates ---"

step "React build" \
  "npm run build -w @goofish/dashboard-react"

step "Nest build" \
  "npm run build -w @goofish/dashboard-nest"

echo ""
echo "--- P2: Optional Gates ---"

step "Docker build" \
  "run_optional_docker_build" \
  "true"

echo ""
echo "========================================"
echo "  BASELINE SUMMARY"
echo "========================================"

for r in "${RESULTS[@]}"; do
  echo "  $r"
done

echo ""
echo "  Passed: $PASS  Failed: $FAIL  Skipped: $SKIP"
echo ""

if [[ $FAIL -gt 0 ]]; then
  echo "RESULT: BASELINE FAILED"
  exit 1
else
  echo "RESULT: BASELINE PASSED"
  exit 0
fi
