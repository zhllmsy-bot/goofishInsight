#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
RUNTIME_HOME="${GOOFISH_RUNTIME_HOME:-$HOME/Library/Application Support/goofish-insight-launchd}"
cd "$ROOT_DIR"

WORKERS="${WORKERS:-16}"
FIRST_PASS_BATCH_SIZE="${FIRST_PASS_BATCH_SIZE:-4}"
AI_TIMEOUT_SEC="${AI_TIMEOUT_SEC:-90}"
PREFIX="${PREFIX:-review-v3-full-active}"
RUN_PREFIX="${RUN_PREFIX:-}"
REVIEW_V3_RESUME_MODE="${REVIEW_V3_RESUME_MODE:-auto}"
REVIEW_V3_RETRY_FAILED_FIRST_PASS="${REVIEW_V3_RETRY_FAILED_FIRST_PASS:-0}"
FIRST_PASS_RETRY_MAX="${FIRST_PASS_RETRY_MAX:-3}"
SECOND_PASS_RETRY_MAX="${SECOND_PASS_RETRY_MAX:-2}"
RETRY_BACKOFF_BASE_SEC="${RETRY_BACKOFF_BASE_SEC:-2}"
RETRY_BACKOFF_MAX_SEC="${RETRY_BACKOFF_MAX_SEC:-30}"
REVIEW_V3_CLI_TIMEOUT_SEC="${REVIEW_V3_CLI_TIMEOUT_SEC:-$((AI_TIMEOUT_SEC + 60))}"
WAIT_PATTERN="${WAIT_PATTERN:-}"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

LIMIT="$(ROOT_DIR="$ROOT_DIR" "$PYTHON_BIN" - <<'PY'
import os
import sys
root_dir = os.environ.get("ROOT_DIR", "").strip()
if root_dir:
    sys.path.insert(0, f"{root_dir}/apps/collector/src")
from sqlalchemy import select, func
from goofish_insight.db import SessionLocal
from goofish_insight.models import Item
with SessionLocal() as session:
    total = session.execute(
        select(func.count()).select_from(Item).where(Item.is_active.is_(True))
    ).scalar_one()
print(int(total))
PY
)"

if [[ -n "$WAIT_PATTERN" ]]; then
  while pgrep -f "$WAIT_PATTERN" >/dev/null 2>&1; do
    sleep 10
  done
fi

echo "{\"event\":\"starting_full_backfill\",\"limit\":${LIMIT},\"workers\":${WORKERS},\"first_pass_batch_size\":${FIRST_PASS_BATCH_SIZE},\"prefix\":\"${PREFIX}\",\"resume_mode\":\"${REVIEW_V3_RESUME_MODE}\",\"retry_failed_first_pass\":${REVIEW_V3_RETRY_FAILED_FIRST_PASS}}"
ORCHESTRATOR_SCRIPT="$ROOT_DIR/scripts/run_review_v3_top_items_orchestrator.sh"
if [[ -n "${GOOFISH_ROOT_DIR:-}" && -f "$RUNTIME_HOME/run_review_v3_top_items_orchestrator.sh" ]]; then
  ORCHESTRATOR_SCRIPT="$RUNTIME_HOME/run_review_v3_top_items_orchestrator.sh"
fi

env \
  LIMIT="$LIMIT" \
  WORKERS="$WORKERS" \
  FIRST_PASS_BATCH_SIZE="$FIRST_PASS_BATCH_SIZE" \
  AI_TIMEOUT_SEC="$AI_TIMEOUT_SEC" \
  PREFIX="$PREFIX" \
  RUN_PREFIX="$RUN_PREFIX" \
  REVIEW_V3_RESUME_MODE="$REVIEW_V3_RESUME_MODE" \
  REVIEW_V3_RETRY_FAILED_FIRST_PASS="$REVIEW_V3_RETRY_FAILED_FIRST_PASS" \
  FIRST_PASS_RETRY_MAX="$FIRST_PASS_RETRY_MAX" \
  SECOND_PASS_RETRY_MAX="$SECOND_PASS_RETRY_MAX" \
  RETRY_BACKOFF_BASE_SEC="$RETRY_BACKOFF_BASE_SEC" \
  RETRY_BACKOFF_MAX_SEC="$RETRY_BACKOFF_MAX_SEC" \
  REVIEW_V3_CLI_TIMEOUT_SEC="$REVIEW_V3_CLI_TIMEOUT_SEC" \
  "$ORCHESTRATOR_SCRIPT"
