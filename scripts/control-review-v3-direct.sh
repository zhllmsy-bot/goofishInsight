#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
RUNTIME_HOME="${GOOFISH_RUNTIME_HOME:-$HOME/Library/Application Support/goofish-insight-launchd}"
GOOFISH_ENV_FILE="${GOOFISH_ENV_FILE:-$ROOT_DIR/.env}"

load_env_value() {
  local key="$1"
  python3 - "$GOOFISH_ENV_FILE" "$key" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
target = sys.argv[2]
if not env_path.exists():
    sys.exit(0)
for raw in env_path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == target:
        print(value.strip())
        break
PY
}

run_phase() {
  local phase="$1"
  shift || true
  local start_script="$ROOT_DIR/scripts/start-review-v3.sh"
  if [[ -f "$RUNTIME_HOME/start-review-v3.sh" ]]; then
    start_script="$RUNTIME_HOME/start-review-v3.sh"
  fi
  (
    cd "$ROOT_DIR"
    export EXECUTOR=direct
    export PHASE="$phase"
    exec "$start_script" "$@"
  )
}

show_status() {
  local provider base_url model timeout
  provider="$(load_env_value AI_PROVIDER)"
  base_url="$(load_env_value AI_BASE_URL)"
  model="$(load_env_value AI_MODEL)"
  timeout="$(load_env_value AI_TIMEOUT_SEC)"
  cat <<EOF
review_v3_executor=direct
ai_provider=${provider:-}
ai_base_url=${base_url:-}
ai_model=${model:-}
ai_timeout_sec=${timeout:-}
EOF
}

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
  status)
    show_status
    ;;
  first-pass)
    run_phase first_pass "$@"
    ;;
  second-pass)
    run_phase second_pass "$@"
    ;;
  *)
    cat <<EOF
Usage:
  $(basename "$0") status
  $(basename "$0") first-pass [env: BUSINESS_DOMAIN ITEM_ID LIMIT FORCE AI_TIMEOUT_SEC OUTPUT_PATH]
  $(basename "$0") second-pass [env: BUSINESS_DOMAIN ITEM_ID LIMIT FORCE AI_TIMEOUT_SEC OUTPUT_PATH]
EOF
    exit 1
    ;;
esac
