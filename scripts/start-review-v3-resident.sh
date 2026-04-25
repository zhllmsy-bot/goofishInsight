#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
RUNTIME_HOME="${GOOFISH_RUNTIME_HOME:-$HOME/Library/Application Support/goofish-insight-launchd}"
cd "$ROOT_DIR"

mkdir -p reports

WORKER_LABEL="${WORKER_LABEL:-resident-v3-worker}"
BUSINESS_DOMAIN="${BUSINESS_DOMAIN:-}"
LIMIT="${LIMIT:-50}"
AI_TIMEOUT_SEC="${AI_TIMEOUT_SEC:-90}"
IDLE_POLL_SECONDS="${IDLE_POLL_SECONDS:-45}"
ERROR_POLL_SECONDS="${ERROR_POLL_SECONDS:-20}"
STATE_PATH="${STATE_PATH:-$HOME/Library/Application Support/goofish-insight-launchd/review-v3-resident-state.json}"

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

save_state() {
  local state_status="$1"
  local phase="$2"
  local pending="$3"
  local output_path="$4"
  local pending_json="null"
  if [[ "$pending" =~ ^[0-9]+$ ]]; then
    pending_json="$pending"
  fi
  mkdir -p "$(dirname "$STATE_PATH")"
  cat > "$STATE_PATH" <<EOF
{
  "updated_at": "$(timestamp)",
  "last_status": "$(json_escape "$state_status")",
  "phase": "$(json_escape "$phase")",
  "pending_reviews": $pending_json,
  "output_path": "${output_path:+$(json_escape "$output_path")}",
  "worker_label": "$(json_escape "$WORKER_LABEL")"
}
EOF
}

log() {
  print -- "[$(timestamp)] $*"
}

count_pending_reviews() {
  env BUSINESS_DOMAIN="$BUSINESS_DOMAIN" PYTHONPATH=apps/collector/src ./.venv/bin/python - <<'PY'
import os
from sqlalchemy import select
from goofish_insight.db import session_scope
from goofish_insight.models import ItemReviewV3

business_domain = (os.environ.get("BUSINESS_DOMAIN") or "").strip() or None

with session_scope() as session:
    stmt = select(ItemReviewV3.candidate_payload).where(ItemReviewV3.resolution_status == "PENDING_REVIEW")
    if business_domain:
        stmt = stmt.where(ItemReviewV3.business_domain == business_domain)
    rows = session.execute(stmt).scalars()
    count = 0
    for payload in rows:
        if isinstance(payload, list) and payload:
            count += 1
    print(count)
PY
}

log "resident_worker_start worker_label=$WORKER_LABEL limit=$LIMIT ai_timeout_sec=$AI_TIMEOUT_SEC business_domain=${BUSINESS_DOMAIN:-all}"

while true; do
  pending_reviews="$(count_pending_reviews 2>/tmp/goofish-review-v3-resident-pending.err || true)"
  if [[ -z "$pending_reviews" ]] || ! [[ "$pending_reviews" =~ ^[0-9]+$ ]]; then
    pending_error="$(cat /tmp/goofish-review-v3-resident-pending.err 2>/dev/null || true)"
    log "pending_count_failed sleep_seconds=$ERROR_POLL_SECONDS detail=${pending_error:-unknown}"
    save_state "pending_count_failed" "idle" "0" ""
    /bin/sleep "$ERROR_POLL_SECONDS"
    continue
  fi

  if (( pending_reviews <= 0 )); then
    log "resident_idle pending_reviews=0 sleep_seconds=$IDLE_POLL_SECONDS"
    save_state "idle" "second_pass" "$pending_reviews" ""
    /bin/sleep "$IDLE_POLL_SECONDS"
    continue
  fi

  run_timestamp="$("/bin/date" +%Y%m%d-%H%M%S)"
  output_path="reports/review-v3-resident-${WORKER_LABEL}-${run_timestamp}.json"
  log "worker_cycle_start pending_reviews=$pending_reviews output_path=$output_path"
  save_state "running" "second_pass" "$pending_reviews" "$output_path"

  set +e
  direct_script="$ROOT_DIR/scripts/control-review-v3-direct.sh"
  if [[ -f "$RUNTIME_HOME/control-review-v3-direct.sh" ]]; then
    direct_script="$RUNTIME_HOME/control-review-v3-direct.sh"
  fi
  env \
    BUSINESS_DOMAIN="$BUSINESS_DOMAIN" \
    LIMIT="$LIMIT" \
    AI_TIMEOUT_SEC="$AI_TIMEOUT_SEC" \
    OUTPUT_PATH="$output_path" \
    "$direct_script" second-pass
  exit_code=$?
  set -e

  pending_after="$(count_pending_reviews 2>/tmp/goofish-review-v3-resident-pending.err || true)"
  if [[ -z "$pending_after" ]] || ! [[ "$pending_after" =~ ^[0-9]+$ ]]; then
    pending_after="0"
  fi

  if (( exit_code == 0 )); then
    log "worker_cycle_exit exit_code=0 pending_after=$pending_after sleep_seconds=$IDLE_POLL_SECONDS"
    save_state "completed" "second_pass" "$pending_after" "$output_path"
    /bin/sleep "$IDLE_POLL_SECONDS"
  else
    log "worker_cycle_exit exit_code=$exit_code pending_after=$pending_after sleep_seconds=$ERROR_POLL_SECONDS"
    save_state "error" "second_pass" "$pending_after" "$output_path"
    /bin/sleep "$ERROR_POLL_SECONDS"
  fi
done
