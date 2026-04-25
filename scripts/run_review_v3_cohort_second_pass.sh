#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <cohort-itemids.txt>" >&2
  exit 1
fi

COHORT_PATH="$1"
if [[ ! -f "$COHORT_PATH" ]]; then
  echo "cohort file not found: $COHORT_PATH" >&2
  exit 1
fi

WORKERS="${WORKERS:-4}"
AI_TIMEOUT_SEC="${AI_TIMEOUT_SEC:-90}"
WAIT_PATTERN="${WAIT_PATTERN:-}"
PREFIX="${PREFIX:-$(basename "$COHORT_PATH" .txt)}"
STAMP="$(date +%Y%m%d-%H%M%S)"
START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

PENDING_PATH="reports/${PREFIX}-${STAMP}.pending-second-pass.txt"
SECOND_DONE_PATH="reports/${PREFIX}-${STAMP}.second-pass.done"
SECOND_FAILED_PATH="reports/${PREFIX}-${STAMP}.second-pass.failed"
SUMMARY_PATH="reports/${PREFIX}-${STAMP}.second-pass-summary.json"

export PYTHONPATH=apps/collector/src
export AI_TIMEOUT_SEC

if [[ -n "$WAIT_PATTERN" ]]; then
  while pgrep -f "$WAIT_PATTERN" >/dev/null 2>&1; do
    sleep 10
  done
fi

python3 - <<'PY' "$COHORT_PATH" "$PENDING_PATH"
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'apps' / 'collector' / 'src'))
from sqlalchemy import select
from goofish_insight.db import SessionLocal
from goofish_insight.models import Item, ItemReviewV3

cohort = [line.strip() for line in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines() if line.strip()]
out = Path(sys.argv[2])
with SessionLocal() as session:
    rows = session.execute(
        select(Item.item_id)
        .join(ItemReviewV3, ItemReviewV3.item_id_ref == Item.id)
        .where(Item.item_id.in_(cohort), ItemReviewV3.resolution_status == 'PENDING_REVIEW')
    ).scalars().all()
out.write_text('\n'.join(rows) + ('\n' if rows else ''), encoding='utf-8')
print({'event': 'pending_second_pass_built', 'count': len(rows), 'path': str(out)})
PY

: > "$SECOND_DONE_PATH"
: > "$SECOND_FAILED_PATH"
if [[ -s "$PENDING_PATH" ]]; then
  cat "$PENDING_PATH" | xargs -P "$WORKERS" -I{} sh -c '
    cd "$0" || exit 1
    if PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli review-v3-second-pass --item-id "$1" --limit 1 --ai-timeout-sec "$2" --executor direct --force >/dev/null; then
      printf "%s\n" "$1" >> "$3"
    else
      printf "%s\n" "$1" >> "$4"
    fi
    exit 0
  ' "$ROOT_DIR" {} "$AI_TIMEOUT_SEC" "$SECOND_DONE_PATH" "$SECOND_FAILED_PATH"
fi

python3 - <<'PY' "$COHORT_PATH" "$SUMMARY_PATH" "$START_UTC" "$PENDING_PATH" "$SECOND_DONE_PATH" "$SECOND_FAILED_PATH"
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'apps' / 'collector' / 'src'))
from sqlalchemy import select
from goofish_insight.db import SessionLocal
from goofish_insight.models import Item, ItemReviewV3

cohort = [line.strip() for line in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines() if line.strip()]
summary_path = Path(sys.argv[2])
start_utc = sys.argv[3]
pending_path = Path(sys.argv[4])
second_done_path = Path(sys.argv[5])
second_failed_path = Path(sys.argv[6])

with SessionLocal() as session:
    rows = session.execute(
        select(
            Item.item_id,
            Item.business_domain,
            Item.llm_review_status,
            Item.llm_review_confidence,
            ItemReviewV3.stage_status,
            ItemReviewV3.resolution_status,
            ItemReviewV3.model_catalog_id,
            ItemReviewV3.first_pass_confidence,
            ItemReviewV3.second_pass_confidence,
        )
        .join(ItemReviewV3, ItemReviewV3.item_id_ref == Item.id, isouter=True)
        .where(Item.item_id.in_(cohort))
    ).all()

status_counts = Counter()
domain_status = defaultdict(Counter)
compat_counts = Counter()
for row in rows:
    status = row.resolution_status or 'NO_V3_ROW'
    status_counts[status] += 1
    domain_status[row.business_domain][status] += 1
    compat_counts[row.llm_review_status or 'NULL'] += 1

summary = {
    'startedAt': start_utc,
    'cohortCount': len(cohort),
    'pendingSecondPassCount': len([line for line in pending_path.read_text(encoding='utf-8').splitlines() if line.strip()]) if pending_path.exists() else 0,
    'secondPassDoneCount': len([line for line in second_done_path.read_text(encoding='utf-8').splitlines() if line.strip()]) if second_done_path.exists() else 0,
    'secondPassFailedCount': len([line for line in second_failed_path.read_text(encoding='utf-8').splitlines() if line.strip()]) if second_failed_path.exists() else 0,
    'resolutionStatusCounts': dict(status_counts),
    'compatStatusCounts': dict(compat_counts),
    'domainResolutionStatusCounts': {domain: dict(counter) for domain, counter in sorted(domain_status.items())},
    'secondPassFailedItems': [line for line in second_failed_path.read_text(encoding='utf-8').splitlines() if line.strip()] if second_failed_path.exists() else [],
    'paths': {
      'pendingSecondPass': str(pending_path),
      'secondPassDone': str(second_done_path),
      'secondPassFailed': str(second_failed_path),
    },
}
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print({'event': 'completed', 'summary_path': str(summary_path)})
PY
