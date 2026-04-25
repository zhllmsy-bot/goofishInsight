#!/usr/bin/env zsh
# Start the resident batch collector from the repository root.
# Usage: GOOFISH_ROOT_DIR=/path/to/goofish-insight ./scripts/start-batch-collect-resident.sh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

CONFIG_PATH="${CONFIG_PATH:-apps/collector/configs/monitor_tasks.json}"
PROFILE_KEY="${PROFILE_KEY:-chrome-attached}"
CDP_URL="${CDP_URL:-http://127.0.0.1:9223}"
PARALLEL_TABS="${PARALLEL_TABS:-1}"
LOGIN_WAIT_SECONDS="${LOGIN_WAIT_SECONDS:-180}"
ONLY_TASK="${ONLY_TASK:-}"
MAX_PLANS_PER_RUN="${MAX_PLANS_PER_RUN:-10}"
PROBE_PLAN_COUNT="${PROBE_PLAN_COUNT:-1}"
PROBE_LOGIN_WAIT_SECONDS="${PROBE_LOGIN_WAIT_SECONDS:-5}"
PROBE_MAX_PAGES_PER_PLAN="${PROBE_MAX_PAGES_PER_PLAN:-1}"
CHECKPOINT_MODE="${CHECKPOINT_MODE:-commit}"
BATCH_CURSOR_STATE_PATH="${BATCH_CURSOR_STATE_PATH:-reports/runtime/batch_collect_cursor.json}"
RISK_BACKOFF_STATE_PATH="${RISK_BACKOFF_STATE_PATH:-reports/runtime/batch_collect_risk_backoff.json}"
RISK_EVENT_LOG_PATH="${RISK_EVENT_LOG_PATH:-reports/runtime/batch_collect_risk_events.jsonl}"
RISK_BACKOFF_BASE_SECONDS="${RISK_BACKOFF_BASE_SECONDS:-600}"
RISK_BACKOFF_MAX_SECONDS="${RISK_BACKOFF_MAX_SECONDS:-21600}"
RISK_EVENT_EXIT_CODE="${RISK_EVENT_EXIT_CODE:-19}"
RECOVERY_INITIAL_SLEEP_SECONDS="${RECOVERY_INITIAL_SLEEP_SECONDS:-600}"
RECOVERY_RETRY_SLEEP_SECONDS="${RECOVERY_RETRY_SLEEP_SECONDS:-1200}"
RECOVERY_MAX_SLEEP_SECONDS="${RECOVERY_MAX_SLEEP_SECONDS:-21600}"
BATCH_BROWSER_LABEL="${BATCH_BROWSER_LABEL:-com.admin.goofish-browser-batch-9223}"
LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-${HOME}/Library/LaunchAgents}"
LAUNCH_DOMAIN="gui/$(id -u)"
BATCH_BROWSER_PLIST="${LAUNCH_AGENTS_DIR}/${BATCH_BROWSER_LABEL}.plist"
CDP_PORT="${CDP_URL##*:}"
CDP_PORT="${CDP_PORT%%/*}"

STARTUP_POLL_SECONDS="${STARTUP_POLL_SECONDS:-5}"
SUCCESS_SLEEP_SECONDS="${SUCCESS_SLEEP_SECONDS:-600}"
ERROR_SLEEP_SECONDS="${ERROR_SLEEP_SECONDS:-60}"
PYTHONPATH_RUNTIME="${PYTHONPATH_RUNTIME:-apps/collector/src:apps/analyzer/src:packages/schema/src}"

timestamp() {
  /bin/date '+%Y-%m-%dT%H:%M:%S%z'
}

log() {
  print -- "[$(timestamp)] $*"
}

browser_guard_ready() {
  local scope_key="${ONLY_TASK:-}"
  eval "$(
    env PYTHONPATH="$PYTHONPATH_RUNTIME" ./.venv/bin/python - "$PROFILE_KEY" "$CDP_URL" "$scope_key" <<'PY'
import json
import sys
from urllib.error import URLError
from urllib.request import urlopen

from goofish_insight.application.services.browser_guard import (
    evaluate_browser_guard_preflight,
    format_browser_guard_preflight_message,
    render_browser_guard_shell_exports,
)

profile_key = sys.argv[1]
cdp_url = sys.argv[2]
scope_key = sys.argv[3] or None

decision = evaluate_browser_guard_preflight(
    profile_key=profile_key,
    feature="collect_batch",
    scope_key=scope_key,
)
if decision.get("allowed"):
    try:
        with urlopen(f"{cdp_url.rstrip('/')}/json/version", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        browser_ready = isinstance(payload, dict) and bool(payload)
    except (OSError, TimeoutError, URLError, json.JSONDecodeError):
        browser_ready = False
    if not browser_ready:
        decision = {
            "allowed": False,
            "decision": "browser_unavailable",
            "profile_key": profile_key,
            "feature": "collect_batch",
            "scope_key": scope_key,
            "auth_state": "browser_unavailable",
            "source": "browser_preflight",
            "reason": "cdp_unreachable",
            "wait_seconds": 0,
            "recommended_sleep_seconds": 5,
            "next_retry_at": None,
            "cooldown_started_at": None,
            "error_message": None,
            "cdp_url": cdp_url,
        }
print(render_browser_guard_shell_exports(decision))
PY
  )"
  [[ "${GUARD_ALLOWED:-0}" == "1" ]]
}

iso_now() {
  ./.venv/bin/python - <<'PY'
from datetime import UTC, datetime
print(datetime.now(UTC).isoformat())
PY
}

iso_after_seconds() {
  local seconds="$1"
  ./.venv/bin/python - "$seconds" <<'PY'
from datetime import UTC, datetime, timedelta
import sys

wait_seconds = int(sys.argv[1])
print((datetime.now(UTC) + timedelta(seconds=wait_seconds)).isoformat())
PY
}

write_runtime_state() {
  local phase="$1"
  local runtime_status="$2"
  local cooldown_reason="${3:-}"
  local cooldown_started_at="${4:-}"
  local recovery_eta="${5:-}"
  local next_retry_at="${6:-}"
  local recent_risk_event="${7:-}"
  local recent_failure_reason="${8:-}"
  local cooldown_seconds="${9:-}"
  local next_cooldown_seconds="${10:-}"

  env PYTHONPATH="$PYTHONPATH_RUNTIME" ./.venv/bin/python - \
    "$phase" \
    "$runtime_status" \
    "$cooldown_reason" \
    "$cooldown_started_at" \
    "$recovery_eta" \
    "$next_retry_at" \
    "$recent_risk_event" \
    "$recent_failure_reason" \
    "$cooldown_seconds" \
    "$next_cooldown_seconds" \
    "${RECOVERY_INITIAL_SLEEP_SECONDS}" \
    "${RECOVERY_MAX_SLEEP_SECONDS}" >/dev/null 2>&1 <<'PY' || \
    log "batch_runtime_state_write_failed phase=$phase status=$runtime_status"
from datetime import UTC, datetime
import sys

from goofish_insight.application.services.collector_runtime import (
    normalize_resident_recovery_state,
    upsert_collector_job_run_state,
)

phase = sys.argv[1]
runtime_status = sys.argv[2]
cooldown_reason = sys.argv[3] or None
cooldown_started_at = sys.argv[4] or None
recovery_eta = sys.argv[5] or None
next_retry_at = sys.argv[6] or None
recent_risk_event = sys.argv[7] or None
recent_failure_reason = sys.argv[8] or None
cooldown_seconds = sys.argv[9] or None
next_cooldown_seconds = sys.argv[10] or None
initial_seconds = int(sys.argv[11])
max_seconds = int(sys.argv[12])

def maybe_int(value):
    if value in (None, ""):
        return None
    return int(value)

metadata = {
    "cooldown_reason": cooldown_reason,
    "cooldown_started_at": cooldown_started_at,
    "recovery_eta": recovery_eta,
    "next_retry_at": next_retry_at,
    "recent_risk_event": recent_risk_event,
    "recent_failure_reason": recent_failure_reason,
    "cooldown_seconds": maybe_int(cooldown_seconds),
    "next_cooldown_seconds": maybe_int(next_cooldown_seconds),
    "state_updated_at": datetime.now(UTC).isoformat(),
}
metadata = {key: value for key, value in metadata.items() if value is not None}
upsert_collector_job_run_state(
    job_name="batch_collect",
    phase=phase,
    status=runtime_status,
    metadata=metadata,
)
normalized = normalize_resident_recovery_state(
    metadata,
    initial_seconds=initial_seconds,
    max_seconds=max_seconds,
)
metadata.update(
    {
        "recovery_baseline_seconds": normalized["baseline_seconds"],
        "recovery_last_applied_cooldown_seconds": normalized["last_applied_cooldown_seconds"] or 0,
        "recovery_failed_cooldown_seconds": normalized["failed_cooldown_seconds"] or 0,
        "next_cooldown_seconds": normalized["next_cooldown_seconds"],
    }
)
upsert_collector_job_run_state(
    job_name="batch_collect",
    phase=phase,
    status=runtime_status,
    metadata=metadata,
)
PY
}

read_runtime_state() {
  env PYTHONPATH="$PYTHONPATH_RUNTIME" ./.venv/bin/python - <<'PY' 2>/dev/null || print -- "{}"
import json

from goofish_insight.application.services.collector_runtime import get_latest_collector_job_run_state

print(json.dumps(get_latest_collector_job_run_state(job_name="batch_collect") or {}, ensure_ascii=False))
PY
}

restore_recovery_sleep_seconds() {
  local state_json
  state_json="$(read_runtime_state)"
  ./.venv/bin/python - "$RECOVERY_INITIAL_SLEEP_SECONDS" "$RECOVERY_MAX_SLEEP_SECONDS" "$state_json" <<'PY'
import json
import sys

from goofish_insight.application.services.collector_runtime import normalize_resident_recovery_state

initial_seconds = int(sys.argv[1])
max_value = int(sys.argv[2])
raw = sys.argv[3] if len(sys.argv) > 3 else "{}"
try:
    payload = json.loads(raw or "{}")
except json.JSONDecodeError:
    payload = {}
metadata = payload.get("metadata") if isinstance(payload, dict) else {}
if not isinstance(metadata, dict):
    metadata = {}
normalized = normalize_resident_recovery_state(
    metadata,
    initial_seconds=initial_seconds,
    max_seconds=max_value,
)
print(normalized["baseline_seconds"])
PY
}

persist_recovery_window() {
  local phase="$1"
  local runtime_status="$2"
  local cooldown_reason="$3"
  local cooldown_started_at="$4"
  local recovery_eta="$5"
  local next_retry_at="$6"
  local recent_risk_event="$7"
  local recent_failure_reason="$8"
  local cooldown_seconds="$9"
  local next_cooldown_seconds="${10}"
  write_runtime_state \
    "$phase" \
    "$runtime_status" \
    "$cooldown_reason" \
    "$cooldown_started_at" \
    "$recovery_eta" \
    "$next_retry_at" \
    "$recent_risk_event" \
    "$recent_failure_reason" \
    "$cooldown_seconds" \
    "$next_cooldown_seconds"
}

reset_recovery_sleep_seconds() {
  :
}

browser_ready() {
  /usr/bin/curl -fsS --max-time 5 "${CDP_URL}/json/version" >/dev/null
}

bootout_browser_service() {
  launchctl bootout "${LAUNCH_DOMAIN}/${BATCH_BROWSER_LABEL}" >/dev/null 2>&1 || \
    launchctl bootout "$LAUNCH_DOMAIN" "$BATCH_BROWSER_PLIST" >/dev/null 2>&1 || true
}

disable_browser_service() {
  launchctl disable "${LAUNCH_DOMAIN}/${BATCH_BROWSER_LABEL}" >/dev/null 2>&1 || true
  bootout_browser_service
}

enable_browser_service() {
  launchctl enable "${LAUNCH_DOMAIN}/${BATCH_BROWSER_LABEL}" >/dev/null 2>&1 || true
  if launchctl print "${LAUNCH_DOMAIN}/${BATCH_BROWSER_LABEL}" >/dev/null 2>&1; then
    launchctl kickstart -k "${LAUNCH_DOMAIN}/${BATCH_BROWSER_LABEL}" >/dev/null 2>&1 || true
    return
  fi
  if [[ -f "$BATCH_BROWSER_PLIST" ]]; then
    launchctl load "$BATCH_BROWSER_PLIST" >/dev/null 2>&1 || true
  fi
}

terminate_browser_by_port() {
  local pids
  pids="$(lsof -nP -t -iTCP:${CDP_PORT} -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return
  fi
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill "$pid" >/dev/null 2>&1 || true
  done <<< "$pids"
  /bin/sleep 2
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  done <<< "$pids"
}

cooldown_and_restart_browser() {
  local sleep_seconds="$1"
  local reason="$2"
  local next_cooldown_seconds="$3"
  local baseline_seconds="$4"
  local failed_cooldown_seconds="$5"
  local cooldown_started_at
  local recovery_eta
  local recent_risk_event
  cooldown_started_at="$(iso_now)"
  recovery_eta="$(iso_after_seconds "$sleep_seconds")"
  recent_risk_event="reason=${reason}; cooldown=${sleep_seconds}s; recovery_eta=${recovery_eta}; baseline=${baseline_seconds}s; failed=${failed_cooldown_seconds}s; next=${next_cooldown_seconds}s"
  log "batch_browser_cooldown_start reason=$reason sleep_seconds=$sleep_seconds baseline_seconds=$baseline_seconds failed_cooldown_seconds=$failed_cooldown_seconds next_cooldown_seconds=$next_cooldown_seconds browser_label=$BATCH_BROWSER_LABEL cdp_port=$CDP_PORT"
  env PYTHONPATH="$PYTHONPATH_RUNTIME" ./.venv/bin/python - \
    "$reason" \
    "$cooldown_started_at" \
    "$recovery_eta" \
    "$recent_risk_event" \
    "$sleep_seconds" \
    "$baseline_seconds" \
    "$sleep_seconds" \
    "$failed_cooldown_seconds" \
    "$next_cooldown_seconds" <<'PY' >/dev/null 2>&1 || \
    log "batch_runtime_state_write_failed phase=cooldown status=degraded"
from datetime import UTC, datetime
import sys

from goofish_insight.application.services.collector_runtime import upsert_collector_job_run_state

reason = sys.argv[1]
cooldown_started_at = sys.argv[2]
recovery_eta = sys.argv[3]
recent_risk_event = sys.argv[4]
cooldown_seconds = int(sys.argv[5])
baseline_seconds = int(sys.argv[6])
last_applied_cooldown_seconds = int(sys.argv[7])
failed_cooldown_seconds = int(sys.argv[8])
next_cooldown_seconds = int(sys.argv[9])

upsert_collector_job_run_state(
    job_name="batch_collect",
    phase="cooldown",
    status="degraded",
    metadata={
        "cooldown_reason": reason,
        "cooldown_started_at": cooldown_started_at,
        "recovery_eta": recovery_eta,
        "next_retry_at": recovery_eta,
        "recent_risk_event": recent_risk_event,
        "recent_failure_reason": reason,
        "cooldown_seconds": cooldown_seconds,
        "recovery_baseline_seconds": baseline_seconds,
        "recovery_last_applied_cooldown_seconds": last_applied_cooldown_seconds,
        "recovery_failed_cooldown_seconds": failed_cooldown_seconds,
        "next_cooldown_seconds": next_cooldown_seconds,
        "state_updated_at": datetime.now(UTC).isoformat(),
    },
)
PY
  disable_browser_service
  terminate_browser_by_port
  /bin/sleep "$sleep_seconds"
  enable_browser_service
  until browser_ready; do
    log "batch_browser_restarting cdp_url=$CDP_URL sleep_seconds=$STARTUP_POLL_SECONDS"
    /bin/sleep "$STARTUP_POLL_SECONDS"
  done
  log "batch_browser_cooldown_end reason=$reason cdp_url=$CDP_URL"
}

run_collect_batch() {
  local mode="$1"
  local max_plans="$2"
  local login_wait="$3"
  local max_pages_per_plan="${4:-}"

  if (( max_plans <= 0 )); then
    log "batch_cycle_skip mode=$mode reason=no_plans max_plans=$max_plans"
    return 0
  fi

  local -a cmd=(
    ./.venv/bin/python
    -m
    goofish_insight.cli
    collect-batch
    --config-path "$CONFIG_PATH"
    --profile-key "$PROFILE_KEY"
    --login-wait-seconds "$login_wait"
    --checkpoint-mode "$CHECKPOINT_MODE"
    --job-phase "$mode"
    --parallel-tabs "$PARALLEL_TABS"
    --max-plans-per-run "$max_plans"
    --risk-backoff-state-path "$RISK_BACKOFF_STATE_PATH"
    --risk-event-log-path "$RISK_EVENT_LOG_PATH"
    --risk-backoff-base-seconds "$RISK_BACKOFF_BASE_SECONDS"
    --risk-backoff-max-seconds "$RISK_BACKOFF_MAX_SECONDS"
    --exit-on-risk-event
  )
  if [[ -n "$ONLY_TASK" ]]; then
    cmd+=(--only-task "$ONLY_TASK")
  fi
  if [[ -n "$BATCH_CURSOR_STATE_PATH" ]]; then
    cmd+=(--cursor-state-path "$BATCH_CURSOR_STATE_PATH")
  fi
  if [[ -n "$max_pages_per_plan" ]]; then
    cmd+=(--max-pages-per-plan "$max_pages_per_plan")
  fi

  log "batch_cycle_start mode=$mode profile_key=$PROFILE_KEY parallel_tabs=$PARALLEL_TABS max_plans=$max_plans login_wait_seconds=$login_wait max_pages_per_plan=${max_pages_per_plan:-none} cursor_state_path=$BATCH_CURSOR_STATE_PATH risk_backoff_state_path=$RISK_BACKOFF_STATE_PATH risk_event_log_path=$RISK_EVENT_LOG_PATH risk_backoff=${RISK_BACKOFF_BASE_SECONDS}-${RISK_BACKOFF_MAX_SECONDS}s"
  env PYTHONPATH="$PYTHONPATH_RUNTIME" "${cmd[@]}"
  local exit_code=$?
  log "batch_cycle_end mode=$mode exit_code=$exit_code"
  return "$exit_code"
}

log "batch_collect_resident_start profile_key=$PROFILE_KEY cdp_url=$CDP_URL config_path=$CONFIG_PATH"
current_recovery_sleep_seconds="$(restore_recovery_sleep_seconds)"
log "batch_collect_resident_recovery_window current_recovery_sleep_seconds=$current_recovery_sleep_seconds initial_sleep_seconds=$RECOVERY_INITIAL_SLEEP_SECONDS retry_sleep_seconds=$RECOVERY_RETRY_SLEEP_SECONDS max_sleep_seconds=$RECOVERY_MAX_SLEEP_SECONDS"

if (( PROBE_PLAN_COUNT < 1 )); then
  PROBE_PLAN_COUNT=1
fi

while true; do
  if ! browser_guard_ready; then
    guard_sleep_seconds="${GUARD_RECOMMENDED_SLEEP_SECONDS:-$STARTUP_POLL_SECONDS}"
    log "browser_guard_blocked decision=${GUARD_DECISION:-unknown} auth_state=${GUARD_AUTH_STATE:-unknown} sleep_seconds=$guard_sleep_seconds message=${GUARD_MESSAGE:-blocked}"
    write_runtime_state \
      "preflight" \
      "degraded" \
      "${GUARD_AUTH_STATE:-}" \
      "${GUARD_COOLDOWN_STARTED_AT:-}" \
      "${GUARD_NEXT_RETRY_AT:-}" \
      "${GUARD_NEXT_RETRY_AT:-}" \
      "${GUARD_MESSAGE:-}" \
      "${GUARD_ERROR_MESSAGE:-}" \
      "$guard_sleep_seconds"
    /bin/sleep "$guard_sleep_seconds"
    continue
  fi

  set +e
  run_collect_batch "probe" "$PROBE_PLAN_COUNT" "$PROBE_LOGIN_WAIT_SECONDS" "$PROBE_MAX_PAGES_PER_PLAN"
  probe_exit_code=$?
  set -e

  if (( probe_exit_code == 0 )); then
    log "batch_probe_passed next_action=start_batch_window"
    recovery_adjustment_json="$(
      env PYTHONPATH="$PYTHONPATH_RUNTIME" ./.venv/bin/python - \
        "$RECOVERY_INITIAL_SLEEP_SECONDS" \
        "$RECOVERY_MAX_SLEEP_SECONDS" \
        "$(read_runtime_state)" <<'PY'
import json
import sys

from goofish_insight.application.services.collector_runtime import (
    normalize_resident_recovery_state,
    resolve_resident_cooldown_after_success,
)

initial_seconds = int(sys.argv[1])
max_seconds = int(sys.argv[2])
raw = sys.argv[3] if len(sys.argv) > 3 else "{}"
try:
    payload = json.loads(raw or "{}")
except json.JSONDecodeError:
    payload = {}
metadata = payload.get("metadata") if isinstance(payload, dict) else {}
if not isinstance(metadata, dict):
    metadata = {}
normalized = normalize_resident_recovery_state(
    metadata,
    initial_seconds=initial_seconds,
    max_seconds=max_seconds,
)
result = resolve_resident_cooldown_after_success(
    baseline_seconds=normalized["baseline_seconds"],
    last_applied_cooldown_seconds=normalized["last_applied_cooldown_seconds"],
    failed_cooldown_seconds=normalized["failed_cooldown_seconds"],
    max_seconds=max_seconds,
)
print(json.dumps({"normalized": normalized, "result": result}, ensure_ascii=False))
PY
    )"
    eval "$(
      ./.venv/bin/python - "$recovery_adjustment_json" <<'PY'
import json
import shlex
import sys

payload = json.loads(sys.argv[1])
normalized = payload["normalized"]
result = payload["result"]
exports = {
    "RECOVERY_BASELINE_BEFORE": str(normalized["baseline_seconds"]),
    "RECOVERY_LAST_APPLIED_BEFORE": str(normalized["last_applied_cooldown_seconds"] or 0),
    "RECOVERY_FAILED_BEFORE": str(normalized["failed_cooldown_seconds"] or 0),
    "RECOVERY_BASELINE_AFTER": str(result["baseline_seconds"]),
    "RECOVERY_NEXT_AFTER": str(result["next_cooldown_seconds"]),
    "RECOVERY_ADJUSTED": "1" if result["adjusted"] else "0",
    "RECOVERY_STRATEGY": str(result["strategy"]),
}
print("\n".join(f"{key}={shlex.quote(value)}" for key, value in exports.items()))
PY
    )"
    current_recovery_sleep_seconds="$RECOVERY_BASELINE_AFTER"
    log "batch_recovery_baseline_update event=probe_success strategy=$RECOVERY_STRATEGY adjusted=$RECOVERY_ADJUSTED baseline_before=$RECOVERY_BASELINE_BEFORE last_applied_before=$RECOVERY_LAST_APPLIED_BEFORE failed_before=$RECOVERY_FAILED_BEFORE baseline_after=$RECOVERY_BASELINE_AFTER"
    env PYTHONPATH="$PYTHONPATH_RUNTIME" ./.venv/bin/python - \
      "$RECOVERY_BASELINE_AFTER" \
      "$RECOVERY_NEXT_AFTER" \
      "$RECOVERY_STRATEGY" \
      "$RECOVERY_ADJUSTED" <<'PY' >/dev/null 2>&1 || \
      log "batch_runtime_state_write_failed phase=resume status=running"
from datetime import UTC, datetime
import sys

from goofish_insight.application.services.collector_runtime import upsert_collector_job_run_state

baseline_seconds = int(sys.argv[1])
next_cooldown_seconds = int(sys.argv[2])
strategy = sys.argv[3]
adjusted = sys.argv[4] == "1"

upsert_collector_job_run_state(
    job_name="batch_collect",
    phase="resume",
    status="running",
    metadata={
        "cooldown_reason": "",
        "cooldown_seconds": 0,
        "recovery_baseline_seconds": baseline_seconds,
        "recovery_last_applied_cooldown_seconds": 0,
        "recovery_failed_cooldown_seconds": 0,
        "next_cooldown_seconds": next_cooldown_seconds,
        "recent_risk_event": f"probe_success strategy={strategy} adjusted={adjusted} baseline={baseline_seconds}s",
        "state_updated_at": datetime.now(UTC).isoformat(),
    },
)
PY
    remaining_plans=$(( MAX_PLANS_PER_RUN - PROBE_PLAN_COUNT ))
    set +e
    run_collect_batch "batch" "$remaining_plans" "$LOGIN_WAIT_SECONDS"
    batch_exit_code=$?
    set -e
    if (( batch_exit_code == 0 )); then
      log "batch_cycle_exit mode=batch exit_code=0 sleep_seconds=$SUCCESS_SLEEP_SECONDS"
      /bin/sleep "$SUCCESS_SLEEP_SECONDS"
    elif (( batch_exit_code == RISK_EVENT_EXIT_CODE )); then
      risk_plan_json="$(
        env PYTHONPATH="$PYTHONPATH_RUNTIME" ./.venv/bin/python - \
          "$RECOVERY_INITIAL_SLEEP_SECONDS" \
          "$RECOVERY_MAX_SLEEP_SECONDS" \
          "$(read_runtime_state)" <<'PY'
import json
import sys

from goofish_insight.application.services.collector_runtime import (
    normalize_resident_recovery_state,
    plan_resident_cooldown_after_risk,
)

initial_seconds = int(sys.argv[1])
max_seconds = int(sys.argv[2])
raw = sys.argv[3] if len(sys.argv) > 3 else "{}"
try:
    payload = json.loads(raw or "{}")
except json.JSONDecodeError:
    payload = {}
metadata = payload.get("metadata") if isinstance(payload, dict) else {}
if not isinstance(metadata, dict):
    metadata = {}
normalized = normalize_resident_recovery_state(
    metadata,
    initial_seconds=initial_seconds,
    max_seconds=max_seconds,
)
plan = plan_resident_cooldown_after_risk(
    baseline_seconds=normalized["baseline_seconds"],
    last_applied_cooldown_seconds=normalized["last_applied_cooldown_seconds"],
    max_seconds=max_seconds,
)
print(json.dumps({"normalized": normalized, "plan": plan}, ensure_ascii=False))
PY
      )"
      eval "$(
        ./.venv/bin/python - "$risk_plan_json" <<'PY'
import json
import shlex
import sys

payload = json.loads(sys.argv[1])
normalized = payload["normalized"]
plan = payload["plan"]
exports = {
    "RISK_BASELINE_SECONDS": str(normalized["baseline_seconds"]),
    "RISK_LAST_APPLIED_SECONDS": str(normalized["last_applied_cooldown_seconds"] or 0),
    "RISK_SLEEP_SECONDS": str(plan["sleep_seconds"]),
    "RISK_FAILED_SECONDS": str(plan["failed_cooldown_seconds"] or 0),
    "RISK_NEXT_SECONDS": str(plan["next_cooldown_seconds"]),
    "RISK_STRATEGY": str(plan["strategy"]),
}
print("\n".join(f"{key}={shlex.quote(value)}" for key, value in exports.items()))
PY
      )"
      cooldown_seconds="$RISK_SLEEP_SECONDS"
      next_cooldown_seconds="$RISK_NEXT_SECONDS"
      failed_cooldown_seconds="$RISK_FAILED_SECONDS"
      baseline_seconds="$RISK_BASELINE_SECONDS"
      log "batch_cycle_exit mode=batch exit_code=$batch_exit_code action=cooldown_recovery strategy=$RISK_STRATEGY baseline_seconds=$baseline_seconds previous_applied_seconds=$RISK_LAST_APPLIED_SECONDS sleep_seconds=$cooldown_seconds failed_cooldown_seconds=$failed_cooldown_seconds next_cooldown_seconds=$next_cooldown_seconds"
      cooldown_and_restart_browser "$cooldown_seconds" "risk_after_batch" "$next_cooldown_seconds" "$baseline_seconds" "$failed_cooldown_seconds"
      current_recovery_sleep_seconds="$next_cooldown_seconds"
    else
      log "batch_cycle_exit mode=batch exit_code=$batch_exit_code sleep_seconds=$ERROR_SLEEP_SECONDS"
      write_runtime_state \
        "batch" \
        "degraded" \
        "batch_exit_nonzero" \
        "" \
        "$(iso_after_seconds "$ERROR_SLEEP_SECONDS")" \
        "$(iso_after_seconds "$ERROR_SLEEP_SECONDS")" \
        "" \
        "batch_exit_code=${batch_exit_code}" \
        "$ERROR_SLEEP_SECONDS"
      /bin/sleep "$ERROR_SLEEP_SECONDS"
    fi
    continue
  fi

  if (( probe_exit_code == RISK_EVENT_EXIT_CODE )); then
    risk_plan_json="$(
      env PYTHONPATH="$PYTHONPATH_RUNTIME" ./.venv/bin/python - \
        "$RECOVERY_INITIAL_SLEEP_SECONDS" \
        "$RECOVERY_MAX_SLEEP_SECONDS" \
        "$(read_runtime_state)" <<'PY'
import json
import sys

from goofish_insight.application.services.collector_runtime import (
    normalize_resident_recovery_state,
    plan_resident_cooldown_after_risk,
)

initial_seconds = int(sys.argv[1])
max_seconds = int(sys.argv[2])
raw = sys.argv[3] if len(sys.argv) > 3 else "{}"
try:
    payload = json.loads(raw or "{}")
except json.JSONDecodeError:
    payload = {}
metadata = payload.get("metadata") if isinstance(payload, dict) else {}
if not isinstance(metadata, dict):
    metadata = {}
normalized = normalize_resident_recovery_state(
    metadata,
    initial_seconds=initial_seconds,
    max_seconds=max_seconds,
)
plan = plan_resident_cooldown_after_risk(
    baseline_seconds=normalized["baseline_seconds"],
    last_applied_cooldown_seconds=normalized["last_applied_cooldown_seconds"],
    max_seconds=max_seconds,
)
print(json.dumps({"normalized": normalized, "plan": plan}, ensure_ascii=False))
PY
    )"
    eval "$(
      ./.venv/bin/python - "$risk_plan_json" <<'PY'
import json
import shlex
import sys

payload = json.loads(sys.argv[1])
normalized = payload["normalized"]
plan = payload["plan"]
exports = {
    "RISK_BASELINE_SECONDS": str(normalized["baseline_seconds"]),
    "RISK_LAST_APPLIED_SECONDS": str(normalized["last_applied_cooldown_seconds"] or 0),
    "RISK_SLEEP_SECONDS": str(plan["sleep_seconds"]),
    "RISK_FAILED_SECONDS": str(plan["failed_cooldown_seconds"] or 0),
    "RISK_NEXT_SECONDS": str(plan["next_cooldown_seconds"]),
    "RISK_STRATEGY": str(plan["strategy"]),
}
print("\n".join(f"{key}={shlex.quote(value)}" for key, value in exports.items()))
PY
    )"
    cooldown_seconds="$RISK_SLEEP_SECONDS"
    next_cooldown_seconds="$RISK_NEXT_SECONDS"
    failed_cooldown_seconds="$RISK_FAILED_SECONDS"
    baseline_seconds="$RISK_BASELINE_SECONDS"
    log "batch_probe_blocked exit_code=$probe_exit_code strategy=$RISK_STRATEGY baseline_seconds=$baseline_seconds previous_applied_seconds=$RISK_LAST_APPLIED_SECONDS sleep_seconds=$cooldown_seconds failed_cooldown_seconds=$failed_cooldown_seconds next_cooldown_seconds=$next_cooldown_seconds"
    cooldown_and_restart_browser "$cooldown_seconds" "probe_risk_control" "$next_cooldown_seconds" "$baseline_seconds" "$failed_cooldown_seconds"
    current_recovery_sleep_seconds="$next_cooldown_seconds"
  else
    log "batch_probe_error exit_code=$probe_exit_code sleep_seconds=$ERROR_SLEEP_SECONDS"
    write_runtime_state \
      "probe" \
      "degraded" \
      "probe_exit_nonzero" \
      "" \
      "$(iso_after_seconds "$ERROR_SLEEP_SECONDS")" \
      "$(iso_after_seconds "$ERROR_SLEEP_SECONDS")" \
      "" \
      "probe_exit_code=${probe_exit_code}" \
      "$ERROR_SLEEP_SECONDS"
    /bin/sleep "$ERROR_SLEEP_SECONDS"
  fi
done
