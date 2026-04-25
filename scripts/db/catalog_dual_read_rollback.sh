#!/bin/zsh
set -euo pipefail

ROOT_DIR="${GOOFISH_ROOT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$ROOT_DIR"

export PYTHONPATH="apps/collector/src"

BACKUP_FILE="${1:-reports/rollbacks/catalog-dual-read-runtime-profile-backup-$(/bin/date +%Y%m%d-%H%M%S).json}"
TARGET_CATEGORY_CODE="${TARGET_CATEGORY_CODE:-}"
TARGET_CATEGORY_ID="${TARGET_CATEGORY_ID:-}"
DRY_RUN="${DRY_RUN:-true}"

mkdir -p "$(dirname "$BACKUP_FILE")"

./.venv/bin/python - "$BACKUP_FILE" "$TARGET_CATEGORY_CODE" "$TARGET_CATEGORY_ID" "$DRY_RUN" <<'PY'
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

from sqlalchemy import select

from goofish_insight.db import session_scope
from goofish_insight.models import Category, CategoryRuntimeProfile

backup_path = Path(sys.argv[1]).expanduser().resolve()
target_category_code = str(sys.argv[2] or "").strip()
target_category_id = str(sys.argv[3] or "").strip()
dry_run = str(sys.argv[4] or "true").strip().lower() not in {"0", "false", "no"}

with session_scope() as session:
    category_stmt = select(Category)
    if target_category_id:
        category_stmt = category_stmt.where(Category.id == target_category_id)
    if target_category_code:
        category_stmt = category_stmt.where(Category.code == target_category_code)
    categories = list(session.execute(category_stmt).scalars().all())
    category_ids = [str(row.id) for row in categories]
    profile_rows = list(
        session.execute(
            select(CategoryRuntimeProfile).where(CategoryRuntimeProfile.category_id.in_(category_ids))
        ).scalars().all()
    ) if category_ids else []

    backup_payload = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "dryRun": dry_run,
        "targetCategoryCode": target_category_code or None,
        "targetCategoryId": target_category_id or None,
        "profiles": [
            {
                "id": row.id,
                "categoryId": row.category_id,
                "activeTemplateId": row.active_template_id,
                "promptProfile": row.prompt_profile,
                "extractorProfile": row.extractor_profile,
                "validatorProfile": row.validator_profile,
                "llmProviderOverride": row.llm_provider_override,
                "llmModelOverride": row.llm_model_override,
                "status": row.status,
                "metadata": dict(row.metadata_json or {}),
                "createdAt": row.created_at.isoformat() if row.created_at else None,
                "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in profile_rows
        ],
        "rollbackSql": [
            "-- Catalog dual-read rollback SQL (review before execute):",
            "-- update category_runtime_profile set metadata_json = metadata_json - 'catalogReadMode' where category_id in (...);",
            "-- update category_runtime_profile set metadata_json = metadata_json - 'catalogCutoverAt' where category_id in (...);",
            "-- update category_runtime_profile set metadata_json = metadata_json - 'catalogDiffReportVersion' where category_id in (...);",
        ],
    }
    backup_path.write_text(json.dumps(backup_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if not profile_rows:
        print(json.dumps({"ok": True, "profileCount": 0, "backupFile": str(backup_path)}, ensure_ascii=False))
        raise SystemExit(0)

    if dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "dry_run",
                    "profileCount": len(profile_rows),
                    "backupFile": str(backup_path),
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(0)

    for row in profile_rows:
        metadata = dict(row.metadata_json or {})
        metadata.pop("catalogReadMode", None)
        metadata.pop("catalogCutoverAt", None)
        metadata.pop("catalogDiffReportVersion", None)
        row.metadata_json = metadata
    print(
        json.dumps(
            {
                "ok": True,
                "mode": "apply",
                "profileCount": len(profile_rows),
                "backupFile": str(backup_path),
            },
            ensure_ascii=False,
        )
    )
PY
