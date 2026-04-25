#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
OUTPUT_PATH="${REVIEW_OUTPUT_PATH:-reports/ark-batch-full/first-pass-${TIMESTAMP}.json}"
APPLY_OUTPUT_PATH="${REVIEW_APPLY_OUTPUT_PATH:-${OUTPUT_PATH%.json}.apply.json}"

mkdir -p "$(dirname "$OUTPUT_PATH")"
mkdir -p "$(dirname "$APPLY_OUTPUT_PATH")"

echo "start_time=$(date -Iseconds)"
echo "output_path=$OUTPUT_PATH"
echo "apply_path=$APPLY_OUTPUT_PATH"

./scripts/run-ark-review-batch-cleaning.sh "$@" --output "$OUTPUT_PATH"
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli apply-item-llm-review \
  "$OUTPUT_PATH" \
  --no-dry-run \
  --output "$APPLY_OUTPUT_PATH"
