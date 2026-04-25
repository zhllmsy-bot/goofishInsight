#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
RUNTIME_HOME="${GOOFISH_RUNTIME_HOME:-$HOME/Library/Application Support/goofish-insight-launchd}"
cd "$ROOT_DIR"

mkdir -p reports

WORKER_LABEL="${WORKER_LABEL:-resident-v3-full-active-worker}"
PREFIX_BASE="${PREFIX_BASE:-review-v3-full-active}"
WORKERS="${WORKERS:-16}"
FIRST_PASS_BATCH_SIZE="${FIRST_PASS_BATCH_SIZE:-4}"
AI_TIMEOUT_SEC="${AI_TIMEOUT_SEC:-90}"
FIRST_PASS_RETRY_MAX="${FIRST_PASS_RETRY_MAX:-3}"
SECOND_PASS_RETRY_MAX="${SECOND_PASS_RETRY_MAX:-2}"
RETRY_BACKOFF_BASE_SEC="${RETRY_BACKOFF_BASE_SEC:-2}"
RETRY_BACKOFF_MAX_SEC="${RETRY_BACKOFF_MAX_SEC:-30}"
REVIEW_V3_CLI_TIMEOUT_SEC="${REVIEW_V3_CLI_TIMEOUT_SEC:-$((AI_TIMEOUT_SEC + 60))}"
STATE_PATH="${STATE_PATH:-$HOME/Library/Application Support/goofish-insight-launchd/review-v3-full-active-resident-state.json}"

timestamp() {
  /bin/date '+%Y-%m-%dT%H:%M:%S%z'
}

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/ }"
  printf '%s' "$value"
}

resolve_latest_state_prefix() {
  env PREFIX_BASE="$PREFIX_BASE" python3 - <<'PY'
import os
from pathlib import Path

reports_dir = Path("reports")
prefix_base = (os.environ.get("PREFIX_BASE") or "review-v3-full-active").strip()

states = sorted(
    reports_dir.glob(f"{prefix_base}-*.run-state.json"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if states:
    print(states[0].name[: -len(".run-state.json")])
    raise SystemExit(0)

itemids = sorted(
    reports_dir.glob(f"{prefix_base}-*.itemids.txt"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if itemids:
    print(itemids[0].name[: -len(".itemids.txt")])
PY
}

save_state() {
  local state_status="$1"
  local phase="$2"
  local current_prefix="$3"
  local output_path="$4"
  local run_state_path="$5"
  mkdir -p "$(dirname "$STATE_PATH")"
  cat > "$STATE_PATH" <<EOF
{
  "updated_at": "$(timestamp)",
  "last_status": "$(json_escape "$state_status")",
  "phase": "$(json_escape "$phase")",
  "current_prefix": "$(json_escape "$current_prefix")",
  "output_path": "$(json_escape "$output_path")",
  "run_state_path": "$(json_escape "$run_state_path")",
  "worker_label": "$(json_escape "$WORKER_LABEL")"
}
EOF
}

log() {
  print -- "[$(timestamp)] $*"
}

run_one_shot() {
  local full_backfill_script="./scripts/start_review_v3_full_backfill.sh"
  if [[ -f "$RUNTIME_HOME/start_review_v3_full_backfill.sh" ]]; then
    full_backfill_script="$RUNTIME_HOME/start_review_v3_full_backfill.sh"
  fi

  log "start_full_active_orchestrator prefix_base=$PREFIX_BASE workers=$WORKERS first_pass_batch_size=$FIRST_PASS_BATCH_SIZE ai_timeout_sec=$AI_TIMEOUT_SEC"
  save_state "running" "orchestrator" "" "" ""

  set +e
  env \
    PREFIX="$PREFIX_BASE" \
    WORKERS="$WORKERS" \
    FIRST_PASS_BATCH_SIZE="$FIRST_PASS_BATCH_SIZE" \
    AI_TIMEOUT_SEC="$AI_TIMEOUT_SEC" \
    REVIEW_V3_RESUME_MODE="auto" \
    FIRST_PASS_RETRY_MAX="$FIRST_PASS_RETRY_MAX" \
    SECOND_PASS_RETRY_MAX="$SECOND_PASS_RETRY_MAX" \
    RETRY_BACKOFF_BASE_SEC="$RETRY_BACKOFF_BASE_SEC" \
    RETRY_BACKOFF_MAX_SEC="$RETRY_BACKOFF_MAX_SEC" \
    REVIEW_V3_CLI_TIMEOUT_SEC="$REVIEW_V3_CLI_TIMEOUT_SEC" \
    "$full_backfill_script"
  local exit_code=$?
  set -e

  local current_prefix=""
  current_prefix="$(resolve_latest_state_prefix || true)"
  local run_state_path=""
  local summary_path=""
  local run_state_status=""
  local run_state_phase=""
  local run_state_error=""
  if [[ -n "$current_prefix" ]]; then
    run_state_path="reports/${current_prefix}.run-state.json"
    summary_path="reports/${current_prefix}.final-summary.json"
    if [[ -f "$run_state_path" ]]; then
      run_state_status="$(python3 - "$run_state_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
value = payload.get("status")
if isinstance(value, str):
    print(value.strip())
PY
)"
      run_state_phase="$(python3 - "$run_state_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
value = payload.get("phase")
if isinstance(value, str):
    print(value.strip())
PY
)"
      run_state_error="$(python3 - "$run_state_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
value = payload.get("last_error")
if isinstance(value, str):
    print(value.strip())
PY
)"
    fi
  fi

  if (( exit_code == 0 )); then
    save_state "completed" "complete" "$current_prefix" "$summary_path" "$run_state_path"
    log "full_active_orchestrator_completed prefix=$current_prefix"
  else
    local resident_status="error"
    local resident_phase="orchestrator"
    if [[ -n "$run_state_status" ]]; then
      resident_status="$run_state_status"
    fi
    if [[ -n "$run_state_phase" ]]; then
      resident_phase="$run_state_phase"
    fi
    save_state "$resident_status" "$resident_phase" "$current_prefix" "$summary_path" "$run_state_path"
    if [[ -n "$run_state_error" ]]; then
      log "full_active_orchestrator_failed prefix=$current_prefix exit_code=$exit_code status=$resident_status phase=$resident_phase error=$run_state_error"
    else
      log "full_active_orchestrator_failed prefix=$current_prefix exit_code=$exit_code status=$resident_status phase=$resident_phase"
    fi
  fi

  return "$exit_code"
}

log "resident_full_active_start worker_label=$WORKER_LABEL prefix_base=$PREFIX_BASE workers=$WORKERS"
run_one_shot
