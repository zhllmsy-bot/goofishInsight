#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
RUNTIME_HOME="${HOME}/Library/Application Support/goofish-insight-launchd"
LAUNCH_DOMAIN="gui/$(id -u)"

WORKER_LABEL="com.admin.goofish-spec-enrichment-resident"

WORKER_SOURCE_PLIST="$ROOT_DIR/infra/launchd/${WORKER_LABEL}.plist"
WORKER_TARGET_PLIST="$LAUNCH_AGENTS_DIR/${WORKER_LABEL}.plist"
WORKER_STDOUT_LOG="${HOME}/Library/Logs/goofish-spec-enrichment-resident.log"
WORKER_STDERR_LOG="${HOME}/Library/Logs/goofish-spec-enrichment-resident.err.log"
WORKER_RUNTIME_SCRIPT="${RUNTIME_HOME}/start-spec-enrichment-resident.sh"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/control-local-resident-spec-enrichment.sh install
  ./scripts/control-local-resident-spec-enrichment.sh start
  ./scripts/control-local-resident-spec-enrichment.sh stop
  ./scripts/control-local-resident-spec-enrichment.sh restart
  ./scripts/control-local-resident-spec-enrichment.sh status
  ./scripts/control-local-resident-spec-enrichment.sh logs [lines]
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

copy_runtime() {
  sync_file_if_needed "$WORKER_SOURCE_PLIST" "$WORKER_TARGET_PLIST" 644
  sync_file_if_needed "$ROOT_DIR/scripts/start-spec-enrichment-resident.sh" "$WORKER_RUNTIME_SCRIPT" 755
}

enable_service() {
  launchctl enable "${LAUNCH_DOMAIN}/${WORKER_LABEL}" >/dev/null 2>&1 || true
}

disable_service() {
  launchctl disable "${LAUNCH_DOMAIN}/${WORKER_LABEL}" >/dev/null 2>&1 || true
}

latest_worker_log() {
  ls -1t "$ROOT_DIR"/reports/spec-enrichment-worker-*.jsonl 2>/dev/null | head -n 1
}

pending_enrichments() {
  env BUSINESS_DOMAIN="camera_interchangeable_lens" PYTHONPATH=apps/collector/src ./.venv/bin/python - <<'PY'
import os
from scripts.run_spec_enrichment_worker import count_pending_enrichments

domain = os.environ.get("BUSINESS_DOMAIN") or None
print(count_pending_enrichments(business_domain=domain))
PY
}

print_status() {
  echo "launchd label:"
  if is_label_loaded "$WORKER_LABEL"; then
    echo "$WORKER_LABEL: loaded"
  else
    echo "$WORKER_LABEL: not_loaded"
  fi
  echo

  echo "pending enrichments:"
  pending_enrichments || true
  echo

  local latest_log
  latest_log="$(latest_worker_log)"
  echo "latest worker log:"
  if [[ -n "$latest_log" ]]; then
    echo "$latest_log"
    tail -n 5 "$latest_log"
  else
    echo "no worker log yet"
  fi
}

install_service() {
  ensure_dirs
  copy_runtime
  bootout_label "$WORKER_LABEL"
  enable_service
  start_label "$WORKER_LABEL" "$WORKER_TARGET_PLIST"
}

start_service() {
  ensure_dirs
  copy_runtime
  enable_service
  start_label "$WORKER_LABEL" "$WORKER_TARGET_PLIST"
}

stop_service() {
  disable_service
  bootout_label "$WORKER_LABEL"
}

tail_logs() {
  local lines="${1:-80}"
  local log_path
  for log_path in "$WORKER_STDOUT_LOG" "$WORKER_STDERR_LOG"; do
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
    install_service
    sleep 3
    print_status
    ;;
  start)
    start_service
    sleep 3
    print_status
    ;;
  stop)
    stop_service
    print_status
    ;;
  restart)
    stop_service
    sleep 1
    start_service
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
