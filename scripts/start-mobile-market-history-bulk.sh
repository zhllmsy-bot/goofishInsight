#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="${PYTHONPATH:-apps/collector/src}"

QUEUE_STATE_PATH="${QUEUE_STATE_PATH:-$ROOT_DIR/reports/mobile-market-bulk/queue-state.json}"
TOP_N="${TOP_N:-12}"
WINDOW_DAYS="${WINDOW_DAYS:-30}"
HEARTBEAT_DAYS="${HEARTBEAT_DAYS:-7}"
MAX_TASKS="${MAX_TASKS:-3}"
MAX_SCROLLS="${MAX_SCROLLS:-1}"
SERIAL_ARG=()
PERSIST_REPORT_FLAG="--persist-report"

if [[ -n "${SERIAL:-}" ]]; then
  SERIAL_ARG=(--serial "$SERIAL")
fi

if [[ "${PERSIST_REPORT:-1}" != "1" ]]; then
  PERSIST_REPORT_FLAG="--no-persist-report"
fi

if [[ ! -f "$QUEUE_STATE_PATH" || "${RESET_QUEUE:-0}" == "1" ]]; then
  ./.venv/bin/python -m goofish_insight.cli init-mobile-market-history-bulk \
    --output "$QUEUE_STATE_PATH" \
    --top-n "$TOP_N" \
    --window-days "$WINDOW_DAYS" \
    --heartbeat-days "$HEARTBEAT_DAYS"
fi

exec ./.venv/bin/python -m goofish_insight.cli run-mobile-market-history-bulk \
  --state-path "$QUEUE_STATE_PATH" \
  --max-tasks "$MAX_TASKS" \
  --max-scrolls "$MAX_SCROLLS" \
  "${SERIAL_ARG[@]}" \
  "$PERSIST_REPORT_FLAG"
