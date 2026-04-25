#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[deprecated] scripts/start-review-v2.sh now forwards to Review V3 second-pass." >&2

OUTPUT_DIR=${OUTPUT_DIR:-reports}
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_PATH=${OUTPUT_PATH:-"$OUTPUT_DIR/review-v3-second-pass-$TIMESTAMP.json"}
LIMIT=${LIMIT:-0}
AI_TIMEOUT_SEC=${AI_TIMEOUT_SEC:-10}

mkdir -p "$OUTPUT_DIR"

exec env \
  PHASE=second_pass \
  LIMIT="$LIMIT" \
  AI_TIMEOUT_SEC="$AI_TIMEOUT_SEC" \
  OUTPUT_PATH="$OUTPUT_PATH" \
  EXECUTOR=direct \
  ./scripts/start-review-v3.sh "$@"
