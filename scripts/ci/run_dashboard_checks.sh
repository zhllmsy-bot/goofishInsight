#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
NPM_BIN="${NPM_BIN:-npm}"

cd "$REPO_ROOT"

echo "[dashboard-checks] react typecheck"
"$NPM_BIN" run typecheck -w @goofish/dashboard-react

echo "[dashboard-checks] react test"
"$NPM_BIN" run test -w @goofish/dashboard-react

echo "[dashboard-checks] react design-system audit"
"$NPM_BIN" run design-system:audit -w @goofish/dashboard-react

echo "[dashboard-checks] nest typecheck"
"$NPM_BIN" run typecheck -w @goofish/dashboard-nest

echo "[dashboard-checks] react build"
"$NPM_BIN" run build -w @goofish/dashboard-react

echo "[dashboard-checks] nest build"
"$NPM_BIN" run build -w @goofish/dashboard-nest

echo "[dashboard-checks] nest test"
"$NPM_BIN" run test:e2e -w @goofish/dashboard-nest -- --runInBand
