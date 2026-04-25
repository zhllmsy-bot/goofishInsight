#!/bin/zsh
set -euo pipefail

if [[ -n "${LOCAL_QWEN_VENV:-}" ]]; then
  source "$LOCAL_QWEN_VENV/bin/activate"
fi

LISTEN_HOST=${LISTEN_HOST:-0.0.0.0}
PORT=${PORT:-8000}
BACKEND_HOST=${BACKEND_HOST:-127.0.0.1}
BACKEND_PORT=${BACKEND_PORT:-8001}
STANDBY_BACKEND_PORT=${STANDBY_BACKEND_PORT:-0}
PYTHON_BIN=${PYTHON_BIN:-${LOCAL_QWEN_PYTHON_BIN:-python}}
MODEL_PATH=${MODEL_PATH:-${QWEN25_MODEL_PATH:-Qwen2.5-32B-Instruct-4bit-MLX}}
REQUEST_LOG=${REQUEST_LOG:-${LOCAL_QWEN_REQUEST_LOG:-logs/qwen-requests.jsonl}}
QWEN_PROXY_SCRIPT=${QWEN_PROXY_SCRIPT:-serve_qwen_text_logged_proxy.py}
UPSTREAM_TIMEOUT_SECONDS=${UPSTREAM_TIMEOUT_SECONDS:-45}

exec "$PYTHON_BIN" "$QWEN_PROXY_SCRIPT" \
  --host "$LISTEN_HOST" \
  --port "$PORT" \
  --backend-host "$BACKEND_HOST" \
  --backend-port "$BACKEND_PORT" \
  --standby-backend-port "$STANDBY_BACKEND_PORT" \
  --model "$MODEL_PATH" \
  --temp 0.0 \
  --max-tokens 512 \
  --decode-concurrency 12 \
  --prompt-concurrency 4 \
  --prefill-step-size 2048 \
  --prompt-cache-size 32 \
  --prompt-cache-bytes 24GB \
  --chat-template-args '{"enable_thinking": false}' \
  --upstream-timeout-seconds "$UPSTREAM_TIMEOUT_SECONDS" \
  --request-log "$REQUEST_LOG"
