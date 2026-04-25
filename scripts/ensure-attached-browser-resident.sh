#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

PROFILE_KEY="${PROFILE_KEY:-chrome-attached-mac}"
PORT="${PORT:-9222}"
START_URL="${START_URL:-https://www.goofish.com/}"
CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-15}"
START_WAIT_SECONDS="${START_WAIT_SECONDS:-20}"

timestamp() {
  /bin/date '+%Y-%m-%dT%H:%M:%S%z'
}

log() {
  print -- "[$(timestamp)] $*"
}

browser_ready() {
  /usr/bin/curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/json/version" >/dev/null
}

last_state="init"

while true; do
  if browser_ready; then
    if [[ "$last_state" != "ready" ]]; then
      log "browser_reused profile_key=$PROFILE_KEY port=$PORT"
      last_state="ready"
    fi
    /bin/sleep "$CHECK_INTERVAL_SECONDS"
    continue
  fi

  if [[ "$last_state" != "missing" ]]; then
    log "browser_missing profile_key=$PROFILE_KEY port=$PORT start_url=$START_URL"
    last_state="missing"
  fi

  set +e
  output="$(
    env PYTHONPATH=apps/collector/src ./.venv/bin/python scripts/open_attached_browser.py \
      --profile-key "$PROFILE_KEY" \
      --port "$PORT" \
      --start-url "$START_URL" \
      --wait-seconds "$START_WAIT_SECONDS" 2>&1
  )"
  exit_code=$?
  set -e

  output="${output//$'\n'/ }"
  if (( exit_code == 0 )); then
    log "browser_ensure_ok profile_key=$PROFILE_KEY port=$PORT output=$output"
  else
    log "browser_ensure_failed profile_key=$PROFILE_KEY port=$PORT exit_code=$exit_code output=$output"
  fi

  /bin/sleep "$CHECK_INTERVAL_SECONDS"
done
