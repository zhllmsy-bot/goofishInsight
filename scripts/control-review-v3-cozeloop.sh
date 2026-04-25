#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "$0")/.." && pwd)"
GOOFISH_ENV_FILE="${GOOFISH_ENV_FILE:-$ROOT_DIR/.env}"
COZELOOP_BASE_URL_DEFAULT="${COZELOOP_BASE_URL_DEFAULT:-http://127.0.0.1:8888}"
COZELOOP_USER_EMAIL="${COZELOOP_USER_EMAIL:-goofish-local-ops@example.com}"
COZELOOP_PAT_NAME="${COZELOOP_PAT_NAME:-goofish-review-v3}"
COZELOOP_MYSQL_CONTAINER="${COZELOOP_MYSQL_CONTAINER:-coze-loop-mysql}"
COZELOOP_MYSQL_DB="${COZELOOP_MYSQL_DB:-cozeloop-mysql}"
COZELOOP_MYSQL_PASSWORD="${COZELOOP_MYSQL_PASSWORD:-cozeloop-mysql}"

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

upsert_env_value() {
  local key="$1"
  local value="$2"
  python3 - "$GOOFISH_ENV_FILE" "$key" "$value" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
target = sys.argv[2]
value = sys.argv[3]
lines = []
updated = False
if env_path.exists():
    lines = env_path.read_text(encoding="utf-8").splitlines()
new_lines = []
for raw in lines:
    if raw.strip().startswith(f"{target}="):
        new_lines.append(f"{target}={value}")
        updated = True
    else:
        new_lines.append(raw)
if not updated:
    new_lines.append(f"{target}={value}")
env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
PY
}

query_mysql_scalar() {
  local sql="$1"
  docker exec "$COZELOOP_MYSQL_CONTAINER" mysql -N -B -uroot "-p$COZELOOP_MYSQL_PASSWORD" -D "$COZELOOP_MYSQL_DB" -e "$sql" | tr -d '\r'
}

require_session_key() {
  local session_key
  session_key="$(query_mysql_scalar "select session_key from user where email='${COZELOOP_USER_EMAIL}' limit 1;")"
  if [[ -z "$session_key" ]]; then
    echo "failed_to_find_cozeloop_session_key email=$COZELOOP_USER_EMAIL" >&2
    return 1
  fi
  print -r -- "$session_key"
}

require_workspace_id() {
  local workspace_id
  workspace_id="$(load_env_value COZELOOP_WORKSPACE_ID)"
  if [[ -n "$workspace_id" ]]; then
    print -r -- "$workspace_id"
    return 0
  fi
  workspace_id="$(query_mysql_scalar "select s.id from space s join user u on u.id=s.owner_id where u.email='${COZELOOP_USER_EMAIL}' limit 1;")"
  if [[ -z "$workspace_id" ]]; then
    echo "failed_to_find_cozeloop_workspace_id email=$COZELOOP_USER_EMAIL" >&2
    return 1
  fi
  upsert_env_value COZELOOP_WORKSPACE_ID "$workspace_id"
  print -r -- "$workspace_id"
}

pat_is_valid() {
  local pat="$1"
  local workspace_id="$2"
  local response
  response="$(curl -sS -H "Authorization: Bearer $pat" -H 'Content-Type: application/json' \
    -d "{\"workspace_id\":\"$workspace_id\",\"page_number\":1,\"page_size\":1}" \
    "${COZELOOP_BASE_URL_DEFAULT}/v1/loop/prompts/list" || true)"
  [[ "$response" == *'"code":0'* ]]
}

create_pat() {
  local session_key="$1"
  curl -sS -H "Cookie: session_key=$session_key" -H 'Content-Type: application/json' \
    -d "{\"name\":\"${COZELOOP_PAT_NAME}\",\"duration_day\":\"permanent\"}" \
    "${COZELOOP_BASE_URL_DEFAULT}/api/auth/v1/personal_access_tokens" | \
    python3 -c 'import sys,json; payload=json.load(sys.stdin); print(payload.get("token",""))'
}

bootstrap() {
  local session_key workspace_id pat
  session_key="$(require_session_key)"
  workspace_id="$(require_workspace_id)"
  pat="$(load_env_value COZELOOP_PAT)"

  if [[ -z "$pat" ]] || ! pat_is_valid "$pat" "$workspace_id"; then
    pat="$(create_pat "$session_key")"
    if [[ -z "$pat" ]]; then
      echo "failed_to_create_cozeloop_pat" >&2
      return 1
    fi
    upsert_env_value COZELOOP_PAT "$pat"
  fi

  upsert_env_value COZELOOP_BASE_URL "$COZELOOP_BASE_URL_DEFAULT"

  cat <<EOF
{
  "cozeloop_base_url": "$COZELOOP_BASE_URL_DEFAULT",
  "cozeloop_workspace_id": "$workspace_id",
  "cozeloop_pat_present": true,
  "cozeloop_session_email": "$COZELOOP_USER_EMAIL"
}
EOF
}

run_goofish_cli() {
  local session_key="$1"
  shift
  (
    cd "$ROOT_DIR"
    export PYTHONPATH=apps/collector/src
    export COZELOOP_BASE_URL="${COZELOOP_BASE_URL_DEFAULT}"
    export COZELOOP_SESSION_KEY="$session_key"
    exec ./.venv/bin/python -m goofish_insight.cli "$@"
  )
}

sync_prompts() {
  local session_key="$1"
  shift
  run_goofish_cli "$session_key" sync-review-v3-cozeloop-prompts "$@"
}

run_phase() {
  local phase="$1"
  shift
  local session_key
  session_key="$(require_session_key)"
  local sync_args=()
  if [[ -n "${BUSINESS_DOMAIN:-}" ]]; then
    sync_args+=(--business-domain "$BUSINESS_DOMAIN")
  fi
  sync_prompts "$session_key" "${sync_args[@]}"
  (
    cd "$ROOT_DIR"
    export PYTHONPATH=apps/collector/src
    export COZELOOP_BASE_URL="${COZELOOP_BASE_URL_DEFAULT}"
    export COZELOOP_SESSION_KEY="$session_key"
    export EXECUTOR=cozeloop
    export PHASE="$phase"
    exec ./scripts/start-review-v3.sh "$@"
  )
}

show_status() {
  local workspace_id pat
  workspace_id="$(require_workspace_id)"
  pat="$(load_env_value COZELOOP_PAT)"
  cat <<EOF
cozeloop_base_url=$COZELOOP_BASE_URL_DEFAULT
cozeloop_workspace_id=$workspace_id
cozeloop_pat_present=$([[ -n "$pat" ]] && echo true || echo false)
cozeloop_session_email=$COZELOOP_USER_EMAIL
EOF
  if [[ -n "$pat" ]]; then
    curl -sS -H "Authorization: Bearer $pat" -H 'Content-Type: application/json' \
      -d "{\"workspace_id\":\"$workspace_id\",\"page_number\":1,\"page_size\":20}" \
      "${COZELOOP_BASE_URL_DEFAULT}/v1/loop/prompts/list"
    printf '\n'
  fi
}

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
  bootstrap)
    bootstrap
    ;;
  status)
    show_status
    ;;
  sync)
    session_key="$(require_session_key)"
    sync_prompts "$session_key" "$@"
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
  $(basename "$0") bootstrap
  $(basename "$0") status
  $(basename "$0") sync [--business-domain ...] [--first-pass-only|--second-pass-only]
  $(basename "$0") first-pass [env: BUSINESS_DOMAIN ITEM_ID LIMIT FORCE AI_TIMEOUT_SEC OUTPUT_PATH]
  $(basename "$0") second-pass [env: BUSINESS_DOMAIN ITEM_ID LIMIT FORCE AI_TIMEOUT_SEC OUTPUT_PATH]
EOF
    exit 1
    ;;
esac
