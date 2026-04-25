#!/bin/zsh
set -euo pipefail

PYTHON_BIN=${PYTHON_BIN:-${LOCAL_QWEN_PYTHON_BIN:-python}}
MODEL_PATH=${MODEL_PATH:-${QWEN25_VL_MODEL_PATH:-Qwen2.5-VL-72B-Instruct-4bit-MLX}}
LISTEN_HOST=${LISTEN_HOST:-127.0.0.1}
PORT=${PORT:-8020}
PREFILL_STEP_SIZE=${PREFILL_STEP_SIZE:-256}
ROOT_DIR="$(cd -- "$(dirname "$0")/.." && pwd)"

exec "$PYTHON_BIN" "$ROOT_DIR/scripts/serve_qwen25_vl_72b.py" \
  --model "$MODEL_PATH" \
  --host "$LISTEN_HOST" \
  --port "$PORT" \
  --prefill-step-size "$PREFILL_STEP_SIZE"
