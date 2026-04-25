#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

echo "[deprecated] start-review-v2-resident.sh now forwards to Review V3 resident." >&2
exec ./scripts/start-review-v3-resident.sh "$@"
