#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ARK_REVIEW_PROTOCOL="${ARK_REVIEW_PROTOCOL:-openai}"
ARK_REVIEW_MODEL="${ARK_REVIEW_MODEL:-doubao-seed-2.0-pro}"
ARK_REVIEW_API_KEY="${ARK_REVIEW_API_KEY:-${ARK_AI_API_KEY:-${AI_API_KEY:-}}}"

if [[ -z "$ARK_REVIEW_API_KEY" && -f "$REPO_ROOT/.env" ]]; then
  ARK_REVIEW_API_KEY="$(
    python3 - <<'PY'
from pathlib import Path
env_path = Path(".env")
values = {}
for raw_line in env_path.read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()
print(values.get("ARK_AI_API_KEY") or values.get("AI_API_KEY") or "")
PY
  )"
fi

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
ARK_MAX_TOKENS="${ARK_REVIEW_MAX_TOKENS:-${ARK_AI_MAX_TOKENS:-${AI_MAX_TOKENS:-5000}}}"

export AI_PROVIDER="$ARK_PROVIDER"
export AI_BASE_URL="$ARK_BASE_URL"
export AI_API_KEY="$ARK_REVIEW_API_KEY"
export AI_MODEL="$ARK_REVIEW_MODEL"
export AI_TIMEOUT_SEC="$ARK_TIMEOUT_SEC"
export AI_MAX_TOKENS="$ARK_MAX_TOKENS"
export AI_ENABLE_THINKING="false"

export ARK_AI_PROVIDER="$ARK_PROVIDER"
export ARK_AI_BASE_URL="$ARK_BASE_URL"
export ARK_AI_API_KEY="$ARK_REVIEW_API_KEY"
export ARK_AI_MODEL="$ARK_REVIEW_MODEL"
export ARK_AI_TIMEOUT_SEC="$ARK_TIMEOUT_SEC"
export ARK_AI_MAX_TOKENS="$ARK_MAX_TOKENS"
export ARK_AI_ENABLE_THINKING="false"
export PYTHONPATH="apps/collector/src"

exec ./.venv/bin/python -m goofish_insight.cli enrich-specs "$@"
