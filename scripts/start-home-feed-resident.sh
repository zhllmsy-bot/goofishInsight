#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd -- "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

PROFILE_KEY="${PROFILE_KEY:-chrome-attached-mac}"
CDP_URL="${CDP_URL:-http://127.0.0.1:9222}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-20}"
MAX_MESSAGES="${MAX_MESSAGES:-0}"
MAX_CARDS="${MAX_CARDS:-20}"
MIN_MESSAGE_INTERVAL_SECONDS="${MIN_MESSAGE_INTERVAL_SECONDS:-15}"
FRESHNESS_DAYS="${FRESHNESS_DAYS:-30}"
MIN_SAMPLE_POINTS="${MIN_SAMPLE_POINTS:-4}"
MIN_PROFIT_MARGIN_PCT="${MIN_PROFIT_MARGIN_PCT:-10}"
STARTUP_POLL_SECONDS="${STARTUP_POLL_SECONDS:-5}"
DRY_RUN="${DRY_RUN:-1}"
REQUIRE_ACTIONABLE_BAND="${REQUIRE_ACTIONABLE_BAND:-0}"
ONLY_WITHIN_TARGET_PRICE="${ONLY_WITHIN_TARGET_PRICE:-0}"
PYTHONPATH_RUNTIME="${PYTHONPATH_RUNTIME:-apps/collector/src:apps/analyzer/src:packages/schema/src}"

timestamp() {
  /bin/date '+%Y-%m-%dT%H:%M:%S%z'
}

log() {
  print -- "[$(timestamp)] $*"
}

browser_ready() {
  /usr/bin/curl -fsS --max-time 5 "${CDP_URL}/json/version" >/dev/null
}

browser_guard_ready() {
  eval "$(
    env PYTHONPATH="$PYTHONPATH_RUNTIME" \
      ./.venv/bin/python -m goofish_insight.cli preflight-browser-job \
      --profile-key "$PROFILE_KEY" \
      --feature "home_feed" \
      --cdp-url "$CDP_URL" \
      --require-browser-ready \
      --output-format shell
  )"
  [[ "${GUARD_ALLOWED:-0}" == "1" ]]
}

cmd=(
  ./.venv/bin/python
  -m
  goofish_insight.cli
  watch-home-feed
  --profile-key "$PROFILE_KEY"
  --interval-seconds "$INTERVAL_SECONDS"
  --max-messages "$MAX_MESSAGES"
  --max-cards "$MAX_CARDS"
  --min-message-interval-seconds "$MIN_MESSAGE_INTERVAL_SECONDS"
  --freshness-days "$FRESHNESS_DAYS"
  --min-sample-points "$MIN_SAMPLE_POINTS"
  --min-profit-margin-pct "$MIN_PROFIT_MARGIN_PCT"
)

if [[ "$DRY_RUN" == "1" ]]; then
  cmd+=(--dry-run)
fi

if [[ "$REQUIRE_ACTIONABLE_BAND" == "1" ]]; then
  cmd+=(--require-actionable-band)
fi

if [[ "$ONLY_WITHIN_TARGET_PRICE" == "1" ]]; then
  cmd+=(--only-within-target-price)
fi

log "home_feed_resident_start profile_key=$PROFILE_KEY cdp_url=$CDP_URL dry_run=$DRY_RUN"

until browser_guard_ready; do
  log "browser_guard_blocked decision=${GUARD_DECISION:-unknown} auth_state=${GUARD_AUTH_STATE:-unknown} sleep_seconds=${GUARD_RECOMMENDED_SLEEP_SECONDS:-$STARTUP_POLL_SECONDS} message=${GUARD_MESSAGE:-blocked}"
  /bin/sleep "${GUARD_RECOMMENDED_SLEEP_SECONDS:-$STARTUP_POLL_SECONDS}"
done

exec env PYTHONPATH="$PYTHONPATH_RUNTIME" "${cmd[@]}"
