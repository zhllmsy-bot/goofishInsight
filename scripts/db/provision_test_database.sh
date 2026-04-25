#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/../.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TEST_DATABASE_NAME="${TEST_DATABASE_NAME:-}"
TEST_DATABASE_SUFFIX="${TEST_DATABASE_SUFFIX:-_test}"
RECREATE_DATABASE="${RECREATE_DATABASE:-true}"

cd "$ROOT_DIR"

resolve_database_url() {
  if [[ -n "${DATABASE_URL:-}" ]]; then
    print -- "$DATABASE_URL"
    return
  fi

  PYTHONPATH=apps/collector/src "$PYTHON_BIN" - <<'PY'
from goofish_insight.settings import get_settings

print(get_settings().database_url)
PY
}

parse_database_urls() {
  local raw_url="$1"
  PYTHONPATH=apps/collector/src "$PYTHON_BIN" - "$raw_url" "$TEST_DATABASE_NAME" "$TEST_DATABASE_SUFFIX" <<'PY'
import sys

from sqlalchemy.engine import make_url

raw_url = sys.argv[1]
explicit_name = sys.argv[2].strip()
suffix = sys.argv[3]
url = make_url(raw_url)
base_database = url.database or "goofish_insight"
test_database = explicit_name or f"{base_database}{suffix}"
admin_url = url.set(drivername="postgresql", database="postgres", query={})
test_url = url.set(drivername="postgresql+psycopg", database=test_database)

print(admin_url.render_as_string(hide_password=False))
print(test_url.render_as_string(hide_password=False))
print(test_database)
PY
}

if ! command -v psql >/dev/null 2>&1; then
  print -- "psql not found in PATH" >&2
  exit 1
fi

DATABASE_URL_RAW="$(resolve_database_url)"
typeset -a parsed_urls
parsed_urls=("${(@f)$(parse_database_urls "$DATABASE_URL_RAW")}")
ADMIN_DATABASE_URL="${parsed_urls[1]}"
TEST_DATABASE_URL="${parsed_urls[2]}"
TEST_DATABASE_NAME_RESOLVED="${parsed_urls[3]}"

print -- "[test-db] admin_url=${ADMIN_DATABASE_URL}"
print -- "[test-db] test_database=${TEST_DATABASE_NAME_RESOLVED}"

if [[ "$RECREATE_DATABASE" == "true" ]]; then
  psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '${TEST_DATABASE_NAME_RESOLVED}'
  AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "${TEST_DATABASE_NAME_RESOLVED}";
CREATE DATABASE "${TEST_DATABASE_NAME_RESOLVED}";
SQL
else
  psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 <<SQL
SELECT 'exists'
WHERE EXISTS (
  SELECT 1
  FROM pg_database
  WHERE datname = '${TEST_DATABASE_NAME_RESOLVED}'
);
SQL
  if [[ "$?" -ne 0 ]]; then
    psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${TEST_DATABASE_NAME_RESOLVED}\";"
  fi
fi

print -- "[test-db] DATABASE_URL=${TEST_DATABASE_URL}"
