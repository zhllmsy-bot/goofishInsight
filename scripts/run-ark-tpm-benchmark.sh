#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

DURATION_SEC="${DURATION_SEC:-45}"
COOLDOWN_SEC="${COOLDOWN_SEC:-5}"
CONCURRENCY_LEVELS="${CONCURRENCY_LEVELS:-4,8,12,16}"
REQUEST_TIMEOUT_SEC="${REQUEST_TIMEOUT_SEC:-90}"
MAX_TOKENS="${MAX_TOKENS:-0}"
TRACE_PATH="${TRACE_PATH:-}"
OUTPUT_PATH="${OUTPUT_PATH:-}"

ARGS=(
  --duration-sec "$DURATION_SEC"
  --cooldown-sec "$COOLDOWN_SEC"
  --concurrency-levels "$CONCURRENCY_LEVELS"
  --request-timeout-sec "$REQUEST_TIMEOUT_SEC"
)

if [[ -n "$TRACE_PATH" ]]; then
  ARGS+=(--trace-path "$TRACE_PATH")
fi

if [[ "$MAX_TOKENS" =~ ^[0-9]+$ ]] && (( MAX_TOKENS > 0 )); then
  ARGS+=(--max-tokens "$MAX_TOKENS")
fi

if [[ -n "$OUTPUT_PATH" ]]; then
  ARGS+=(--output "$OUTPUT_PATH")
fi

if [[ $# -gt 0 ]]; then
  ARGS+=("$@")
fi

exec ./.venv/bin/python ./scripts/benchmark_ark_tpm_isolated.py "${ARGS[@]}"
