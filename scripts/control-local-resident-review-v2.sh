#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[deprecated] control-local-resident-review-v2.sh now forwards to Review V3 resident." >&2
exec ./scripts/control-local-resident-review-v3.sh "$@"
