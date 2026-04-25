#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

cd "$REPO_ROOT"

echo "[python-quality] syntax check"
PYTHONPATH=apps/collector/src:apps/analyzer/src \
  "$PYTHON_BIN" -m compileall apps/collector/src apps/analyzer/src apps/collector/tests apps/analyzer/tests scripts

echo "[python-quality] selected integration"
bash ./scripts/ci/run_selected_integration.sh
