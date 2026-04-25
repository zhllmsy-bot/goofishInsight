#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ARK_REVIEW_PROTOCOL="${ARK_REVIEW_PROTOCOL:-openai}"
ARK_REVIEW_MODEL="${ARK_REVIEW_MODEL:-doubao-seed-2.0-pro}"
ARK_REVIEW_API_KEY="${ARK_REVIEW_API_KEY:-${ARK_AI_API_KEY:-${AI_API_KEY:-}}}"

if [[ -z "$ARK_REVIEW_API_KEY" ]]; then
  echo "ARK_AI_API_KEY or ARK_REVIEW_API_KEY is required" >&2
  exit 2
fi

if [[ "$ARK_REVIEW_PROTOCOL" == "anthropic" ]]; then
  ARK_PROVIDER="anthropic_compatible"
  ARK_BASE_URL="${ARK_REVIEW_BASE_URL:-https://ark.cn-beijing.volces.com/api/coding}"
else
  ARK_PROVIDER="openai_compatible"
  ARK_BASE_URL="${ARK_REVIEW_BASE_URL:-https://ark.cn-beijing.volces.com/api/coding/v3}"
fi

ARK_TIMEOUT_SEC="${ARK_REVIEW_TIMEOUT_SEC:-${ARK_AI_TIMEOUT_SEC:-${AI_TIMEOUT_SEC:-120}}}"

# Force the process to use the requested Ark target even when repo .env already defines AI_* defaults.
export AI_PROVIDER="$ARK_PROVIDER"
export AI_BASE_URL="$ARK_BASE_URL"
export AI_API_KEY="$ARK_REVIEW_API_KEY"
export AI_MODEL="$ARK_REVIEW_MODEL"
export AI_TIMEOUT_SEC="$ARK_TIMEOUT_SEC"
export AI_ENABLE_THINKING="false"

export ARK_AI_PROVIDER="$ARK_PROVIDER"
export ARK_AI_BASE_URL="$ARK_BASE_URL"
export ARK_AI_API_KEY="$ARK_REVIEW_API_KEY"
export ARK_AI_MODEL="$ARK_REVIEW_MODEL"
export ARK_AI_TIMEOUT_SEC="$ARK_TIMEOUT_SEC"
export ARK_AI_ENABLE_THINKING="false"
export PYTHONPATH="apps/collector/src"

echo "[deprecated] run-ark-review-cleaning.sh now forwards to Review V3 second-pass." >&2
exec env PHASE=second_pass EXECUTOR=direct ./.venv/bin/python -m goofish_insight.cli review-v3-second-pass "$@"
