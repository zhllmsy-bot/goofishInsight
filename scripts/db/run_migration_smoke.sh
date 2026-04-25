#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/../.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"
ALEMBIC_BIN="${ALEMBIC_BIN:-./.venv/bin/alembic}"
TEST_DATABASE_NAME="${TEST_DATABASE_NAME:-}"
TEST_DATABASE_SUFFIX="${TEST_DATABASE_SUFFIX:-_test}"
RECREATE_DATABASE="${RECREATE_DATABASE:-true}"
RUN_DOWNGRADE_SMOKE="${RUN_DOWNGRADE_SMOKE:-false}"

cd "$ROOT_DIR"

provision_output="$(
  TEST_DATABASE_NAME="$TEST_DATABASE_NAME" \
  TEST_DATABASE_SUFFIX="$TEST_DATABASE_SUFFIX" \
  RECREATE_DATABASE="$RECREATE_DATABASE" \
  PYTHON_BIN="${PYTHON_BIN#./}" \
  ./scripts/db/provision_test_database.sh
)"
print -- "$provision_output"

TEST_DATABASE_URL="$(print -- "$provision_output" | sed -n 's/^\[test-db\] DATABASE_URL=//p' | tail -n 1)"
if [[ -z "$TEST_DATABASE_URL" ]]; then
  print -- "failed to resolve test database url" >&2
  exit 1
fi

print -- "[migration-smoke] upgrade head"
DATABASE_URL="$TEST_DATABASE_URL" PYTHONPATH=apps/collector/src "$ALEMBIC_BIN" upgrade head

if [[ "$RUN_DOWNGRADE_SMOKE" == "true" ]]; then
  print -- "[migration-smoke] downgrade base"
  DATABASE_URL="$TEST_DATABASE_URL" PYTHONPATH=apps/collector/src "$ALEMBIC_BIN" downgrade base

  print -- "[migration-smoke] upgrade head after downgrade"
  DATABASE_URL="$TEST_DATABASE_URL" PYTHONPATH=apps/collector/src "$ALEMBIC_BIN" upgrade head
fi

print -- "[migration-smoke] current"
DATABASE_URL="$TEST_DATABASE_URL" PYTHONPATH=apps/collector/src "$ALEMBIC_BIN" current

print -- "[migration-smoke] sanity query"
DATABASE_URL="$TEST_DATABASE_URL" PYTHONPATH=apps/collector/src "$PYTHON_BIN" - <<'PY'
from sqlalchemy import inspect
from goofish_insight.db import engine

inspector = inspect(engine)
tables = set(inspector.get_table_names())
required = {
    "collector_job_run",
    "collector_job_checkpoint",
    "data_quality_metric",
}
missing = sorted(required - tables)
print({"required_tables_present": not missing, "missing_tables": missing})
if missing:
    raise SystemExit(1)
PY
