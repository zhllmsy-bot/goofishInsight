#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
WORKER_LABEL=${WORKER_LABEL:-v2-worker}
BUSINESS_DOMAIN=${BUSINESS_DOMAIN:-}
BATCH_SIZE=${BATCH_SIZE:-10}
LLM_CONCURRENCY=${LLM_CONCURRENCY:-1}
AI_PROVIDER=${AI_PROVIDER:-openai_compatible}
AI_BASE_URL=${AI_BASE_URL:-http://127.0.0.1:8000/v1}
AI_API_KEY=${AI_API_KEY:-local-dev}
AI_MODEL=${AI_MODEL:-${QWEN3_MODEL_PATH:-Qwen3-30B-A3B-MLX-4bit}}
AI_TIMEOUT_SEC=${AI_TIMEOUT_SEC:-30}
PAUSE_SECONDS=${PAUSE_SECONDS:-1}
CLAIM_TTL_SEC=${CLAIM_TTL_SEC:-1800}
MAX_BATCHES=${MAX_BATCHES:-0}

LOG_PATH=${LOG_PATH:-"reports/llm-review-v2-worker-${WORKER_LABEL}-${TIMESTAMP}.log"}
LOW_CONFIDENCE_PATH=${LOW_CONFIDENCE_PATH:-"reports/llm-review-v2-worker-${WORKER_LABEL}-${TIMESTAMP}.low-confidence.jsonl"}

echo "Starting review v2 worker"
echo "worker_label=$WORKER_LABEL"
echo "business_domain=${BUSINESS_DOMAIN:-ALL}"
echo "ai_base_url=$AI_BASE_URL"
echo "ai_model=$AI_MODEL"
echo "batch_size=$BATCH_SIZE llm_concurrency=$LLM_CONCURRENCY timeout=$AI_TIMEOUT_SEC"

CMD=(
  ./.venv/bin/python
  scripts/run_item_llm_review_v2_worker.py
  --batch-size "$BATCH_SIZE"
  --llm-concurrency "$LLM_CONCURRENCY"
  --worker-label "$WORKER_LABEL"
  --ai-timeout-sec "$AI_TIMEOUT_SEC"
  --pause-seconds "$PAUSE_SECONDS"
  --claim-ttl-sec "$CLAIM_TTL_SEC"
  --max-batches "$MAX_BATCHES"
  --log-path "$LOG_PATH"
  --low-confidence-path "$LOW_CONFIDENCE_PATH"
)

if [[ -n "$BUSINESS_DOMAIN" ]]; then
  CMD+=(--business-domain "$BUSINESS_DOMAIN")
fi

exec env \
  AI_PROVIDER="$AI_PROVIDER" \
  AI_BASE_URL="$AI_BASE_URL" \
  AI_API_KEY="$AI_API_KEY" \
  AI_MODEL="$AI_MODEL" \
  PYTHONPATH=apps/collector/src \
  "${CMD[@]}" \
  "$@"
