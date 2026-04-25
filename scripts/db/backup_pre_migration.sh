#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/../.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-${ROOT_DIR}/backups/pre-migration}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TIMESTAMP="$(/bin/date '+%Y%m%d-%H%M%S')"

cd "$ROOT_DIR"
mkdir -p "$BACKUP_DIR"

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

normalize_pg_dump_url() {
  local raw_url="$1"
  PYTHONPATH=apps/collector/src "$PYTHON_BIN" - "$raw_url" <<'PY'
import sys

from sqlalchemy.engine import make_url

url = make_url(sys.argv[1])
normalized = url.set(drivername="postgresql", query={})
print(normalized.render_as_string(hide_password=False))
PY
}

if ! command -v pg_dump >/dev/null 2>&1; then
  print -- "pg_dump not found in PATH" >&2
  exit 1
fi

DATABASE_URL_RAW="$(resolve_database_url)"
DATABASE_URL_PG="$(normalize_pg_dump_url "$DATABASE_URL_RAW")"
OUTPUT_PATH="${BACKUP_DIR}/goofish-insight-pre-migration-${TIMESTAMP}.dump"

print -- "[backup] root=${ROOT_DIR}"
print -- "[backup] output=${OUTPUT_PATH}"

pg_dump \
  --format=custom \
  --verbose \
  --file "$OUTPUT_PATH" \
  "$DATABASE_URL_PG"

print -- "[backup] restore_command=pg_restore --clean --if-exists --no-owner --dbname '<target_database_url>' '${OUTPUT_PATH}'"
