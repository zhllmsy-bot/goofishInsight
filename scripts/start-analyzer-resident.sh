#!/usr/bin/env zsh
# Start the analyzer resident job from the repository root.
# Usage: GOOFISH_ROOT_DIR=/path/to/goofish-insight ./scripts/start-analyzer-resident.sh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

METRIC_DATE="${METRIC_DATE:-}"
BUSINESS_DOMAIN="${BUSINESS_DOMAIN:-}"
CATEGORY_ID="${CATEGORY_ID:-}"
LOCK_PATH="${LOCK_PATH:-}"
ANALYZER_JOB="${ANALYZER_JOB:-all}"
SOURCE_MODE="${SOURCE_MODE:-legacy_items}"
CATCH_UP="${CATCH_UP:-true}"
CATCH_UP_LOOKBACK_DAYS="${CATCH_UP_LOOKBACK_DAYS:-7}"
REPLACE_EXISTING="${REPLACE_EXISTING:-true}"
DRY_RUN="${DRY_RUN:-false}"

cmd=(
  ./.venv/bin/python
  -m
  goofish_analyzer.cli
  --job "$ANALYZER_JOB"
  --source-mode "$SOURCE_MODE"
)

if [[ -n "$LOCK_PATH" ]]; then
  cmd+=(--lock-path "$LOCK_PATH")
fi
if [[ -n "$METRIC_DATE" ]]; then
  cmd+=(--metric-date "$METRIC_DATE")
fi
if [[ -n "$BUSINESS_DOMAIN" ]]; then
  cmd+=(--business-domain "$BUSINESS_DOMAIN")
fi
if [[ -n "$CATEGORY_ID" ]]; then
  cmd+=(--category-id "$CATEGORY_ID")
fi
if [[ "$REPLACE_EXISTING" == "true" ]]; then
  cmd+=(--replace-existing)
else
  cmd+=(--no-replace-existing)
fi
if [[ "$DRY_RUN" == "true" ]]; then
  cmd+=(--dry-run)
fi
if [[ "$CATCH_UP" == "true" ]]; then
  cmd+=(--catch-up --catch-up-lookback-days "$CATCH_UP_LOOKBACK_DAYS")
fi

env PYTHONPATH="apps/collector/src:apps/analyzer/src" "${cmd[@]}"
