#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

mkdir -p reports

load_env_value() {
  local key="$1"
  python3 - "$key" <<'PY'
from pathlib import Path
import sys

key = sys.argv[1]
env_path = Path(".env")
if not env_path.exists():
    print("")
    raise SystemExit(0)

values = {}
for raw_line in env_path.read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    env_key, value = line.split("=", 1)
    values[env_key.strip()] = value.strip()
print(values.get(key, ""))
PY
}

AI_PROVIDER=${AI_PROVIDER:-openai_compatible}
AI_BASE_URL=${AI_BASE_URL:-${ARK_REVIEW_BASE_URL:-https://ark.cn-beijing.volces.com/api/coding/v3}}
AI_MODEL=${AI_MODEL:-${ARK_REVIEW_MODEL:-doubao-seed-2.0-pro}}
AI_API_KEY=${AI_API_KEY:-${ARK_REVIEW_API_KEY:-${ARK_AI_API_KEY:-${AI_API_KEY:-}}}}
if [[ -z "$AI_API_KEY" ]]; then
  AI_API_KEY="$(load_env_value ARK_AI_API_KEY)"
fi
if [[ -z "$AI_API_KEY" ]]; then
  AI_API_KEY="$(load_env_value AI_API_KEY)"
fi
if [[ -z "$AI_API_KEY" ]]; then
  echo "AI_API_KEY or ARK_AI_API_KEY is required" >&2
  exit 2
fi

WORKER_LABEL=${WORKER_LABEL:-resident-spec-enrichment-worker}
BUSINESS_DOMAIN=${BUSINESS_DOMAIN:-camera_interchangeable_lens}
BATCH_SIZE=${BATCH_SIZE:-6}
WORKER_CONCURRENCY=${WORKER_CONCURRENCY:-15}
AI_TIMEOUT_SEC=${AI_TIMEOUT_SEC:-120}
PAUSE_SECONDS=${PAUSE_SECONDS:-0}
IDLE_POLL_SECONDS=${IDLE_POLL_SECONDS:-30}
ERROR_POLL_SECONDS=${ERROR_POLL_SECONDS:-15}
MAX_CYCLES_PER_RUN=${MAX_CYCLES_PER_RUN:-0}

timestamp() {
  /bin/date '+%Y-%m-%dT%H:%M:%S%z'
}

log() {
  print -- "[$(timestamp)] $*"
}

log "spec_enrichment_resident_start worker_label=$WORKER_LABEL business_domain=${BUSINESS_DOMAIN:-all} ai_base_url=$AI_BASE_URL ai_model=$AI_MODEL batch_size=$BATCH_SIZE worker_concurrency=$WORKER_CONCURRENCY"

while true; do
  log "worker_cycle_start"
  run_timestamp="$("/bin/date" +%Y%m%d-%H%M%S)"
  log_path="reports/spec-enrichment-worker-${WORKER_LABEL}-${run_timestamp}.jsonl"
  cmd=(
    ./.venv/bin/python
    scripts/run_spec_enrichment_worker.py
    --batch-size "$BATCH_SIZE"
    --worker-concurrency "$WORKER_CONCURRENCY"
    --worker-label "$WORKER_LABEL"
    --ai-timeout-sec "$AI_TIMEOUT_SEC"
    --pause-seconds "$PAUSE_SECONDS"
    --max-cycles "$MAX_CYCLES_PER_RUN"
    --log-path "$log_path"
  )
  if [[ -n "$BUSINESS_DOMAIN" ]]; then
    cmd+=(--business-domain "$BUSINESS_DOMAIN")
  fi

  set +e
  env \
    AI_PROVIDER="$AI_PROVIDER" \
    AI_BASE_URL="$AI_BASE_URL" \
    AI_API_KEY="$AI_API_KEY" \
    AI_MODEL="$AI_MODEL" \
    AI_ENABLE_THINKING="false" \
    PYTHONPATH=apps/collector/src \
    "${cmd[@]}"
  exit_code=$?
  set -e

  if (( exit_code == 0 )); then
    log "worker_cycle_exit exit_code=0 sleep_seconds=$IDLE_POLL_SECONDS"
    /bin/sleep "$IDLE_POLL_SECONDS"
  else
    log "worker_cycle_exit exit_code=$exit_code sleep_seconds=$ERROR_POLL_SECONDS"
    /bin/sleep "$ERROR_POLL_SECONDS"
  fi
done
