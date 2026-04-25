#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi
RUN_MIGRATION_SMOKE="${RUN_MIGRATION_SMOKE:-false}"
RUN_DOWNGRADE_SMOKE="${RUN_DOWNGRADE_SMOKE:-false}"
TEST_DATABASE_NAME="${TEST_DATABASE_NAME:-goofish_insight_ci_smoke_test}"

cd "$REPO_ROOT"

echo "[selected-integration] python tests"
PYTHONPATH=apps/collector/src:apps/analyzer/src "$PYTHON_BIN" -m unittest \
  apps.analyzer.tests.test_daily_metrics_job \
  apps.analyzer.tests.test_model_scores_job \
  apps.analyzer.tests.test_analysis_reports_job \
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
  apps.collector.tests.test_catalog_models

echo "[selected-integration] rule replay"
PYTHONPATH=apps/collector/src "$PYTHON_BIN" scripts/rules/run_rule_replay.py --min-accuracy 0.85

if [[ "$RUN_MIGRATION_SMOKE" == "true" ]]; then
  echo "[selected-integration] migration smoke"
  GOOFISH_ROOT_DIR="$REPO_ROOT" \
    RUN_DOWNGRADE_SMOKE="$RUN_DOWNGRADE_SMOKE" \
    TEST_DATABASE_NAME="$TEST_DATABASE_NAME" \
    ./scripts/db/run_migration_smoke.sh
fi
