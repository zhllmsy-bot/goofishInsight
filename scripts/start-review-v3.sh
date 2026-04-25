#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

mkdir -p reports

PHASE=${PHASE:-first_pass}
BUSINESS_DOMAIN=${BUSINESS_DOMAIN:-}
ITEM_ID=${ITEM_ID:-}
LIMIT=${LIMIT:-50}
FORCE=${FORCE:-false}
AI_TIMEOUT_SEC=${AI_TIMEOUT_SEC:-30}
EXECUTOR=${EXECUTOR:-}
OUTPUT_PATH=${OUTPUT_PATH:-"reports/review-v3-${PHASE}-$(date +%Y%m%d-%H%M%S).json"}

cmd=(./.venv/bin/python -m goofish_insight.cli)
if [[ "$PHASE" == "second_pass" ]]; then
  cmd+=(review-v3-second-pass)
else
  cmd+=(review-v3-first-pass)
fi
if [[ -n "$BUSINESS_DOMAIN" ]]; then
  cmd+=(--business-domain "$BUSINESS_DOMAIN")
fi
if [[ -n "$ITEM_ID" ]]; then
  cmd+=(--item-id "$ITEM_ID")
fi
cmd+=(--limit "$LIMIT" --ai-timeout-sec "$AI_TIMEOUT_SEC" --output "$OUTPUT_PATH")
if [[ -n "$EXECUTOR" ]]; then
  cmd+=(--executor "$EXECUTOR")
fi
if [[ "$FORCE" == "true" ]]; then
  cmd+=(--force)
fi

exec env PYTHONPATH=apps/collector/src "${cmd[@]}"
