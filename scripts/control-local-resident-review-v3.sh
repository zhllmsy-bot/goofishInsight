#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
RUNTIME_HOME="${HOME}/Library/Application Support/goofish-insight-launchd"
LAUNCH_DOMAIN="gui/$(id -u)"

WORKER_LABEL="com.admin.goofish-review-v3-resident"
FULL_ACTIVE_LABEL="com.admin.goofish-review-v3-full-active-resident"
LEGACY_LABEL="com.admin.goofish-review-v2-resident"
ENABLE_SECOND_PASS_RESIDENT="${ENABLE_SECOND_PASS_RESIDENT:-0}"

WORKER_SOURCE_PLIST="$ROOT_DIR/infra/launchd/${WORKER_LABEL}.plist"
FULL_ACTIVE_SOURCE_PLIST="$ROOT_DIR/infra/launchd/${FULL_ACTIVE_LABEL}.plist"
WORKER_TARGET_PLIST="$LAUNCH_AGENTS_DIR/${WORKER_LABEL}.plist"
FULL_ACTIVE_TARGET_PLIST="$LAUNCH_AGENTS_DIR/${FULL_ACTIVE_LABEL}.plist"

WORKER_STDOUT_LOG="${HOME}/Library/Logs/goofish-review-v3-resident.log"
WORKER_STDERR_LOG="${HOME}/Library/Logs/goofish-review-v3-resident.err.log"
FULL_ACTIVE_STDOUT_LOG="${HOME}/Library/Logs/goofish-review-v3-full-active-resident.log"
FULL_ACTIVE_STDERR_LOG="${HOME}/Library/Logs/goofish-review-v3-full-active-resident.err.log"
WORKER_RUNTIME_SCRIPT="${RUNTIME_HOME}/start-review-v3-resident.sh"
FULL_ACTIVE_RUNTIME_SCRIPT="${RUNTIME_HOME}/start-review-v3-full-active-resident.sh"
WORKER_STATE_PATH="${RUNTIME_HOME}/review-v3-resident-state.json"
FULL_ACTIVE_STATE_PATH="${RUNTIME_HOME}/review-v3-full-active-resident-state.json"
DIRECT_RUNTIME_SCRIPT="${RUNTIME_HOME}/control-review-v3-direct.sh"
START_REVIEW_V3_RUNTIME_SCRIPT="${RUNTIME_HOME}/start-review-v3.sh"
FULL_BACKFILL_RUNTIME_SCRIPT="${RUNTIME_HOME}/start_review_v3_full_backfill.sh"
ORCHESTRATOR_RUNTIME_SCRIPT="${RUNTIME_HOME}/run_review_v3_top_items_orchestrator.sh"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/control-local-resident-review-v3.sh install
  ./scripts/control-local-resident-review-v3.sh start
  ./scripts/control-local-resident-review-v3.sh stop
  ./scripts/control-local-resident-review-v3.sh restart
  ./scripts/control-local-resident-review-v3.sh status
  ./scripts/control-local-resident-review-v3.sh logs [lines]

Optional:
  ENABLE_SECOND_PASS_RESIDENT=1 ./scripts/control-local-resident-review-v3.sh start
EOF
}

ensure_dirs() {
  mkdir -p "$LAUNCH_AGENTS_DIR" "$ROOT_DIR/reports" "${HOME}/Library/Logs" "$RUNTIME_HOME"
}

sync_file_if_needed() {
  local source_path="$1"
  local target_path="$2"
  local mode="$3"

  if [[ ! -f "$source_path" ]]; then
    echo "missing source file: $source_path" >&2
    return 1
  fi

  mkdir -p "$(dirname "$target_path")"

  if [[ -f "$target_path" ]] && cmp -s "$source_path" "$target_path"; then
    chmod "$mode" "$target_path" >/dev/null 2>&1 || true
    return 0
  fi

  local temp_path="${target_path}.tmp.$$"
  cp "$source_path" "$temp_path"
  chmod "$mode" "$temp_path"
  mv -f "$temp_path" "$target_path"
}

is_label_loaded() {
  local label="$1"
  launchctl print "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1
}

bootout_label() {
  local label="$1"
  launchctl bootout "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 || \
    launchctl bootout "$LAUNCH_DOMAIN" "${LAUNCH_AGENTS_DIR}/${label}.plist" >/dev/null 2>&1 || true
}

start_label() {
  local label="$1"
  local plist_path="$2"
  if is_label_loaded "$label"; then
    launchctl kickstart -k "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 || true
    return
  fi
  launchctl load "$plist_path"
}

start_label_if_needed() {
  local label="$1"
  local plist_path="$2"
  if is_label_loaded "$label"; then
    launchctl kickstart "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 || true
    return
  fi
  launchctl load "$plist_path"
}

enable_label() {
  local label="$1"
  launchctl enable "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 || true
}

disable_label() {
  local label="$1"
  launchctl disable "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 || true
}

copy_plists() {
  sync_file_if_needed "$WORKER_SOURCE_PLIST" "$WORKER_TARGET_PLIST" 644
  sync_file_if_needed "$FULL_ACTIVE_SOURCE_PLIST" "$FULL_ACTIVE_TARGET_PLIST" 644
  sync_file_if_needed "$ROOT_DIR/scripts/start-review-v3-resident.sh" "$WORKER_RUNTIME_SCRIPT" 755
  sync_file_if_needed "$ROOT_DIR/scripts/start-review-v3-full-active-resident.sh" "$FULL_ACTIVE_RUNTIME_SCRIPT" 755
  sync_file_if_needed "$ROOT_DIR/scripts/control-review-v3-direct.sh" "$DIRECT_RUNTIME_SCRIPT" 755
  sync_file_if_needed "$ROOT_DIR/scripts/start-review-v3.sh" "$START_REVIEW_V3_RUNTIME_SCRIPT" 755
  sync_file_if_needed "$ROOT_DIR/scripts/start_review_v3_full_backfill.sh" "$FULL_BACKFILL_RUNTIME_SCRIPT" 755
  sync_file_if_needed "$ROOT_DIR/scripts/run_review_v3_top_items_orchestrator.sh" "$ORCHESTRATOR_RUNTIME_SCRIPT" 755
  sync_file_if_needed "$ROOT_DIR/scripts/finalize_review_v3_run.py" "${RUNTIME_HOME}/finalize_review_v3_run.py" 755
  sync_file_if_needed "$ROOT_DIR/scripts/resume_review_v3_first_pass.py" "${RUNTIME_HOME}/resume_review_v3_first_pass.py" 755
}

pending_reviews() {
  env PYTHONPATH=apps/collector/src ./.venv/bin/python - <<'PY'
from sqlalchemy import select
from goofish_insight.db import session_scope
from goofish_insight.models import ItemReviewV3

with session_scope() as session:
    rows = session.execute(
        select(ItemReviewV3.candidate_payload).where(ItemReviewV3.resolution_status == "PENDING_REVIEW")
    ).scalars()
    count = 0
    for payload in rows:
        if isinstance(payload, list) and payload:
            count += 1
    print(count)
PY
}

print_status() {
  echo "launchd labels:"
  local label
  for label in "$WORKER_LABEL" "$FULL_ACTIVE_LABEL" "$LEGACY_LABEL"; do
    if is_label_loaded "$label"; then
      echo "$label: loaded"
    else
      echo "$label: not_loaded"
    fi
  done
  echo

  echo "pending review_v3 second-pass:"
  pending_reviews || true
  echo

  echo "resident state:"
  if is_label_loaded "$WORKER_LABEL"; then
    if [[ -f "$WORKER_STATE_PATH" ]]; then
      cat "$WORKER_STATE_PATH"
    else
      echo "missing"
    fi
  else
    echo "service_not_loaded"
    if [[ -f "$WORKER_STATE_PATH" ]]; then
      echo "stale_state_path=$WORKER_STATE_PATH"
    fi
  fi
  echo

  echo "full-active state:"
  if [[ -f "$FULL_ACTIVE_STATE_PATH" ]]; then
    cat "$FULL_ACTIVE_STATE_PATH"
  else
    echo "missing"
  fi
  echo

  echo "v3 progress snapshot:"
  if [[ -x "$ROOT_DIR/scripts/show-review-v3-progress.sh" ]]; then
    "$ROOT_DIR/scripts/show-review-v3-progress.sh" || true
  else
    echo "missing $ROOT_DIR/scripts/show-review-v3-progress.sh"
  fi
  echo
}

install_services() {
  ensure_dirs
  copy_plists
  bootout_label "$LEGACY_LABEL"
  bootout_label "$FULL_ACTIVE_LABEL"
  bootout_label "$WORKER_LABEL"
  disable_label "$LEGACY_LABEL"
  enable_label "$FULL_ACTIVE_LABEL"
  start_label_if_needed "$FULL_ACTIVE_LABEL" "$FULL_ACTIVE_TARGET_PLIST"

  if [[ "$ENABLE_SECOND_PASS_RESIDENT" == "1" ]]; then
    enable_label "$WORKER_LABEL"
    start_label "$WORKER_LABEL" "$WORKER_TARGET_PLIST"
  else
    disable_label "$WORKER_LABEL"
    bootout_label "$WORKER_LABEL"
  fi
}

start_services() {
  ensure_dirs
  copy_plists
  bootout_label "$LEGACY_LABEL"
  disable_label "$LEGACY_LABEL"
  enable_label "$FULL_ACTIVE_LABEL"
  start_label_if_needed "$FULL_ACTIVE_LABEL" "$FULL_ACTIVE_TARGET_PLIST"

  if [[ "$ENABLE_SECOND_PASS_RESIDENT" == "1" ]]; then
    enable_label "$WORKER_LABEL"
    start_label "$WORKER_LABEL" "$WORKER_TARGET_PLIST"
  else
    disable_label "$WORKER_LABEL"
    bootout_label "$WORKER_LABEL"
  fi
}

stop_services() {
  disable_label "$FULL_ACTIVE_LABEL"
  disable_label "$WORKER_LABEL"
  disable_label "$LEGACY_LABEL"
  bootout_label "$FULL_ACTIVE_LABEL"
  bootout_label "$WORKER_LABEL"
  bootout_label "$LEGACY_LABEL"

  pkill -f 'run_review_v3_top_items_orchestrator.py' >/dev/null 2>&1 || true
  pkill -f 'start_review_v3_full_backfill.sh' >/dev/null 2>&1 || true
  pkill -f 'start-review-v3-full-active-resident.sh' >/dev/null 2>&1 || true
  pkill -f 'start-review-v3-resident.sh' >/dev/null 2>&1 || true
  pkill -f 'start-review-v3.sh' >/dev/null 2>&1 || true
}

tail_logs() {
  local lines="${1:-80}"
  local log_path
  for log_path in "$WORKER_STDOUT_LOG" "$WORKER_STDERR_LOG" "$FULL_ACTIVE_STDOUT_LOG" "$FULL_ACTIVE_STDERR_LOG"; do
    echo "===== $log_path ====="
    if [[ -f "$log_path" ]]; then
      tail -n "$lines" "$log_path"
    else
      echo "missing"
    fi
    echo
  done
}

action="${1:-status}"

case "$action" in
  install)
    install_services
    sleep 3
    print_status
    ;;
  start)
    start_services
    sleep 3
    print_status
    ;;
  stop)
    stop_services
    print_status
    ;;
  restart)
    stop_services
    sleep 1
    start_services
    sleep 3
    print_status
    ;;
  status)
    print_status
    ;;
  logs)
    tail_logs "${2:-80}"
    ;;
  *)
    usage
    exit 1
    ;;
esac
