#!/bin/zsh
set -euo pipefail
PYTHON_BIN=${PYTHON_BIN:-${LOCAL_QWEN_PYTHON_BIN:-python}}
MODEL_PATH=${MODEL_PATH:-${QWEN3_MODEL_PATH:-Qwen3-30B-A3B-MLX-4bit}}
LISTEN_HOST=${LISTEN_HOST:-127.0.0.1}
PORT=${PORT:-8000}
ENABLE_THINKING=${ENABLE_THINKING:-false}
MAX_TOKENS=${MAX_TOKENS:-1024}
exec "$PYTHON_BIN" -m mlx_lm server \
  --model "$MODEL_PATH" \
  --host "$LISTEN_HOST" \
  --port "$PORT" \
  --use-default-chat-template \
  --temp 0.0 \
  --max-tokens "$MAX_TOKENS" \
  --chat-template-args "{\"enable_thinking\":${ENABLE_THINKING}}"
