#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
RUNTIME_HOME="${HOME}/Library/Application Support/goofish-insight-launchd"
LAUNCH_DOMAIN="gui/$(id -u)"
PYTHONPATH_RUNTIME="${PYTHONPATH_RUNTIME:-apps/collector/src:apps/analyzer/src:packages/schema/src}"

DASHBOARD_LABEL="com.admin.goofish-dashboard-8787"
BROWSER_FEED_LABEL="com.admin.goofish-browser-feed-9222"
HOME_FEED_LABEL="com.admin.goofish-home-feed-watch"
BROWSER_BATCH_LABEL="com.admin.goofish-browser-batch-9223"
BATCH_LABEL="com.admin.goofish-batch-collect"

DASHBOARD_SOURCE_PLIST="$ROOT_DIR/infra/launchd/${DASHBOARD_LABEL}.plist"
BROWSER_FEED_SOURCE_PLIST="$ROOT_DIR/infra/launchd/${BROWSER_FEED_LABEL}.plist"
HOME_FEED_SOURCE_PLIST="$ROOT_DIR/infra/launchd/${HOME_FEED_LABEL}.plist"
BROWSER_BATCH_SOURCE_PLIST="$ROOT_DIR/infra/launchd/${BROWSER_BATCH_LABEL}.plist"
BATCH_SOURCE_PLIST="$ROOT_DIR/infra/launchd/${BATCH_LABEL}.plist"

DASHBOARD_TARGET_PLIST="$LAUNCH_AGENTS_DIR/${DASHBOARD_LABEL}.plist"
BROWSER_FEED_TARGET_PLIST="$LAUNCH_AGENTS_DIR/${BROWSER_FEED_LABEL}.plist"
HOME_FEED_TARGET_PLIST="$LAUNCH_AGENTS_DIR/${HOME_FEED_LABEL}.plist"
BROWSER_BATCH_TARGET_PLIST="$LAUNCH_AGENTS_DIR/${BROWSER_BATCH_LABEL}.plist"
BATCH_TARGET_PLIST="$LAUNCH_AGENTS_DIR/${BATCH_LABEL}.plist"

HOME_FEED_RUNTIME_SCRIPT="$RUNTIME_HOME/start-home-feed-resident.sh"
BATCH_RUNTIME_SCRIPT="$RUNTIME_HOME/start-batch-collect-resident.sh"
BROWSER_RUNTIME_SCRIPT="$RUNTIME_HOME/ensure-attached-browser-resident.sh"

DASHBOARD_STDOUT_LOG="${HOME}/Library/Logs/goofish-dashboard-8787.log"
DASHBOARD_STDERR_LOG="${HOME}/Library/Logs/goofish-dashboard-8787.err.log"
BROWSER_FEED_STDOUT_LOG="${HOME}/Library/Logs/goofish-browser-feed-9222.log"
BROWSER_FEED_STDERR_LOG="${HOME}/Library/Logs/goofish-browser-feed-9222.err.log"
HOME_FEED_STDOUT_LOG="${HOME}/Library/Logs/goofish-home-feed-watch.log"
HOME_FEED_STDERR_LOG="${HOME}/Library/Logs/goofish-home-feed-watch.err.log"
BROWSER_BATCH_STDOUT_LOG="${HOME}/Library/Logs/goofish-browser-batch-9223.log"
BROWSER_BATCH_STDERR_LOG="${HOME}/Library/Logs/goofish-browser-batch-9223.err.log"
BATCH_STDOUT_LOG="${HOME}/Library/Logs/goofish-batch-collect.log"
BATCH_STDERR_LOG="${HOME}/Library/Logs/goofish-batch-collect.err.log"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/control-local-resident-market-runtime.sh install
  ./scripts/control-local-resident-market-runtime.sh start
  ./scripts/control-local-resident-market-runtime.sh stop-collectors
  ./scripts/control-local-resident-market-runtime.sh stop
  ./scripts/control-local-resident-market-runtime.sh restart
  ./scripts/control-local-resident-market-runtime.sh status
  ./scripts/control-local-resident-market-runtime.sh logs [lines]
EOF
}

labels=(
  "$DASHBOARD_LABEL"
  "$BROWSER_FEED_LABEL"
  "$HOME_FEED_LABEL"
  "$BROWSER_BATCH_LABEL"
  "$BATCH_LABEL"
)

ensure_dirs() {
  mkdir -p "$LAUNCH_AGENTS_DIR" "$RUNTIME_HOME" "$ROOT_DIR/reports" "${HOME}/Library/Logs"
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

copy_runtime_files() {
  sync_file_if_needed "$ROOT_DIR/scripts/ensure-attached-browser-resident.sh" "$BROWSER_RUNTIME_SCRIPT" 755
  sync_file_if_needed "$ROOT_DIR/scripts/start-home-feed-resident.sh" "$HOME_FEED_RUNTIME_SCRIPT" 755
  sync_file_if_needed "$ROOT_DIR/scripts/start-batch-collect-resident.sh" "$BATCH_RUNTIME_SCRIPT" 755

  sync_file_if_needed "$DASHBOARD_SOURCE_PLIST" "$DASHBOARD_TARGET_PLIST" 644
  sync_file_if_needed "$BROWSER_FEED_SOURCE_PLIST" "$BROWSER_FEED_TARGET_PLIST" 644
  sync_file_if_needed "$HOME_FEED_SOURCE_PLIST" "$HOME_FEED_TARGET_PLIST" 644
  sync_file_if_needed "$BROWSER_BATCH_SOURCE_PLIST" "$BROWSER_BATCH_TARGET_PLIST" 644
  sync_file_if_needed "$BATCH_SOURCE_PLIST" "$BATCH_TARGET_PLIST" 644
}

stop_manual_processes() {
  pkill -f 'goofish_insight.cli serve-web --host 127.0.0.1 --port 8787' >/dev/null 2>&1 || true
  pkill -f 'goofish_insight.cli watch-home-feed' >/dev/null 2>&1 || true
  pkill -f 'goofish_insight.cli collect-batch' >/dev/null 2>&1 || true
}

enable_services() {
  local label
  for label in "${labels[@]}"; do
    launchctl enable "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 || true
  done
}

install_services() {
  ensure_dirs
  copy_runtime_files
  local label
  for label in "${labels[@]}"; do
    bootout_label "$label"
  done
  stop_manual_processes
  enable_services
  start_label "$DASHBOARD_LABEL" "$DASHBOARD_TARGET_PLIST"
  start_label "$BROWSER_FEED_LABEL" "$BROWSER_FEED_TARGET_PLIST"
  start_label "$BROWSER_BATCH_LABEL" "$BROWSER_BATCH_TARGET_PLIST"
  /bin/sleep 4
  start_label "$HOME_FEED_LABEL" "$HOME_FEED_TARGET_PLIST"
  start_label "$BATCH_LABEL" "$BATCH_TARGET_PLIST"
}

start_services() {
  ensure_dirs
  copy_runtime_files
  stop_manual_processes
  enable_services

  start_label "$DASHBOARD_LABEL" "$DASHBOARD_TARGET_PLIST"
  start_label "$BROWSER_FEED_LABEL" "$BROWSER_FEED_TARGET_PLIST"
  start_label "$BROWSER_BATCH_LABEL" "$BROWSER_BATCH_TARGET_PLIST"
  /bin/sleep 4
  start_label "$HOME_FEED_LABEL" "$HOME_FEED_TARGET_PLIST"
  start_label "$BATCH_LABEL" "$BATCH_TARGET_PLIST"
}

stop_services() {
  local label
  for label in "$BATCH_LABEL" "$HOME_FEED_LABEL" "$BROWSER_BATCH_LABEL" "$BROWSER_FEED_LABEL" "$DASHBOARD_LABEL"; do
    launchctl disable "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 || true
    bootout_label "$label"
  done
}

stop_collectors() {
  local label
  for label in "$BATCH_LABEL" "$HOME_FEED_LABEL" "$BROWSER_BATCH_LABEL" "$BROWSER_FEED_LABEL"; do
    launchctl disable "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 || true
    bootout_label "$label"
  done
}

tail_logs() {
  local lines="${1:-80}"
  local log_path
  for log_path in \
    "$DASHBOARD_STDOUT_LOG" \
    "$DASHBOARD_STDERR_LOG" \
    "$BROWSER_FEED_STDOUT_LOG" \
    "$BROWSER_FEED_STDERR_LOG" \
    "$HOME_FEED_STDOUT_LOG" \
    "$HOME_FEED_STDERR_LOG" \
    "$BROWSER_BATCH_STDOUT_LOG" \
    "$BROWSER_BATCH_STDERR_LOG" \
    "$BATCH_STDOUT_LOG" \
    "$BATCH_STDERR_LOG"; do
    echo "===== $log_path ====="
    if [[ -f "$log_path" ]]; then
      tail -n "$lines" "$log_path"
    else
      echo "missing"
    fi
    echo
  done
}

print_status() {
  echo "launchd labels:"
  local label
  for label in "${labels[@]}"; do
    if is_label_loaded "$label"; then
      echo "$label: loaded"
    else
      echo "$label: not_loaded"
    fi
  done
  echo

  echo "dashboard health:"
  lsof -nP -iTCP:8787 -sTCP:LISTEN || true
  curl -s http://127.0.0.1:8787/healthz || true
  echo

  echo "attached browsers:"
  lsof -nP -iTCP:9222 -sTCP:LISTEN || true
  lsof -nP -iTCP:9223 -sTCP:LISTEN || true
  PYTHONPATH="$PYTHONPATH_RUNTIME" ./.venv/bin/python -m goofish_insight.cli show-attached-browsers || true
  echo

  echo "recent crawl health:"
  PYTHONPATH="$PYTHONPATH_RUNTIME" ./.venv/bin/python -m goofish_insight.cli show-health | head -n 3 || true
  echo

  echo "latest feed log:"
  tail -n 5 "$HOME_FEED_STDOUT_LOG" 2>/dev/null || true
  echo

  echo "latest batch log:"
  tail -n 5 "$BATCH_STDOUT_LOG" 2>/dev/null || true
}

action="${1:-status}"

case "$action" in
  install)
    install_services
    /bin/sleep 6
    print_status
    ;;
  start)
    start_services
    /bin/sleep 6
    print_status
    ;;
  stop-collectors)
    stop_collectors
    print_status
    ;;
  stop)
    stop_services
    print_status
    ;;
  restart)
    stop_services
    /bin/sleep 1
    start_services
    /bin/sleep 6
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
