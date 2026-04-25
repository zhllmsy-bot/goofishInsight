#!/bin/zsh

set -euo pipefail

ROOT="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
cd "$ROOT/apps/dashboard-nest"

export PORT="3030"
export GOOFISH_DASHBOARD_BACKEND_ORIGIN="http://127.0.0.1:8791"

exec "${GOOFISH_NODE_BIN:-node}" "$ROOT/apps/dashboard-nest/dist/main.js"
