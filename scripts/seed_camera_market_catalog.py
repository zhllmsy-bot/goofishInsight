from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from goofish_insight.application.services.category_config import upsert_category_config_with_session
from goofish_insight.application.services.model_config import upsert_model_config_with_session
from goofish_insight.application.services.task_model_catalog_sync import (
    sync_category_model_catalog_to_tasks_with_session,
)
from goofish_insight.application.services.template_config import upsert_template_config_with_session
from goofish_insight.db import session_scope
from goofish_insight.models import Category


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed camera body and Nikon lens model catalogs for batch collection.",
    )
    parser.add_argument(
        "--seed-path",
        default="apps/collector/configs/model_catalog_seeds/camera_market_seed.json",
        help="Path to the camera market seed JSON file.",
    )
    parser.add_argument(
        "--operator-id",
        default="admin",
        help="Operator id used for config upserts.",
    )
    parser.add_argument(
        "--group",
        action="append",
        dest="groups",
        default=[],
        help="Only apply a specific category group, for example camera_body or camera_interchangeable_lens.",
    )
    parser.add_argument(
        "--force-template-refresh",
        action="store_true",
        help="Always publish and bind the template definition from the seed, even if an active template already exists.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes. Without this flag the script runs in dry-run mode.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_path = Path(args.seed_path)
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    selected_groups = {str(value).strip() for value in list(args.groups or []) if str(value).strip()}
    dry_run = not bool(args.apply)

    category_rows = [
        dict(entry)
        for entry in list(payload.get("categories") or [])
        if _allow_group(entry.get("code"), selected_groups)
    ]
    model_rows = [
        dict(entry)
        for entry in list(payload.get("models") or [])
        if _allow_group(entry.get("categoryCode"), selected_groups)
    ]

    category_results: list[dict[str, Any]] = []
    model_results: list[dict[str, Any]] = []
    sync_summary: dict[str, int] = {
        "taskCount": 0,
        "autoCreatedTaskCount": 0,
        "queryCount": 0,
        "brandLexiconCount": 0,
        "modelLexiconCount": 0,
        "configLexiconCount": 0,
    }
    with session_scope() as session:
        category_results = [
            ensure_category_foundation(
                session=session,
                category_seed=row,
                operator_id=args.operator_id,
                dry_run=dry_run,
                force_template_refresh=bool(args.force_template_refresh),
            )
            for row in category_rows
        ]
        touched_category_ids: set[str] = set()
        for row in model_rows:
            result = upsert_model_config_with_session(
                session,
                payload=row,
                operator_id=args.operator_id,
                dry_run=dry_run,
                sync_tasks=False,
            )
            model_results.append(result)
            category_id = str(result.get("model", {}).get("categoryId") or "").strip()
            if category_id:
                touched_category_ids.add(category_id)
        for category_id in sorted(touched_category_ids):
            category = session.get(Category, category_id)
            if category is None:
                continue
            sync = sync_category_model_catalog_to_tasks_with_session(session, category=category)
            sync_summary["taskCount"] += int(sync.get("taskCount") or 0)
            sync_summary["autoCreatedTaskCount"] += int(sync.get("autoCreatedTaskCount") or 0)
            sync_summary["queryCount"] += int(sync.get("queryCount") or 0)
            sync_summary["brandLexiconCount"] += int(sync.get("brandLexiconCount") or 0)
            sync_summary["modelLexiconCount"] += int(sync.get("modelLexiconCount") or 0)
            sync_summary["configLexiconCount"] += int(sync.get("configLexiconCount") or 0)
        if dry_run:
            session.rollback()

    print(
        json.dumps(
            {
                "dryRun": dry_run,
                "seedPath": str(seed_path),
                "selectedGroups": sorted(selected_groups),
                "categoryCount": len(category_results),
                "modelCount": len(model_rows),
                "categories": category_results,
                "models": {
                    "importedCount": len(model_results),
                    "sync": sync_summary,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def ensure_category_foundation(
    *,
    session,
    category_seed: dict[str, Any],
    operator_id: str,
    dry_run: bool,
    force_template_refresh: bool,
) -> dict[str, Any]:
    runtime = dict(category_seed.get("runtime") or {})
    category_result = upsert_category_config_with_session(
        session,
        payload={
            "code": category_seed["code"],
            "name": category_seed["name"],
            "path": category_seed["path"],
            "level": int(category_seed.get("level", 2)),
            "status": category_seed.get("status", "ACTIVE"),
            "promptProfile": runtime.get("promptProfile"),
            "extractorProfile": runtime.get("extractorProfile"),
            "validatorProfile": runtime.get("validatorProfile"),
            "runtimeStatus": runtime.get("runtimeStatus", "ACTIVE"),
        },
        operator_id=operator_id,
        dry_run=dry_run,
    )

    active_template_id = (category_result.get("runtimeProfile") or {}).get("activeTemplateId")
    template_result = None
    if force_template_refresh or not active_template_id:
        template_seed = dict(category_seed.get("template") or {})
        if template_seed:
            template_result = upsert_template_config_with_session(
                session,
                payload={
                    "categoryCode": category_seed["code"],
                    "status": template_seed.get("status", "PUBLISHED"),
                    "items": list(template_seed.get("items") or []),
                    "bindAsActiveTemplate": bool(template_seed.get("bindAsActiveTemplate", True)),
                    "activateOnPublish": bool(template_seed.get("activateOnPublish", True)),
                    "promptProfile": runtime.get("promptProfile"),
                    "extractorProfile": runtime.get("extractorProfile"),
                    "validatorProfile": runtime.get("validatorProfile"),
                    "runtimeStatus": runtime.get("runtimeStatus", "ACTIVE"),
                },
                operator_id=operator_id,
                dry_run=dry_run,
            )
            active_template_id = (
                template_result.get("runtimeProfile", {}) or {}
            ).get("activeTemplateId") or active_template_id

    return {
        "categoryCode": category_seed["code"],
        "categoryId": category_result.get("category", {}).get("id"),
        "activeTemplateId": active_template_id,
        "templateCreated": bool(template_result),
        "runtimeProfile": category_result.get("runtimeProfile"),
    }


def _allow_group(candidate: Any, selected_groups: set[str]) -> bool:
    normalized = str(candidate or "").strip()
    if not selected_groups:
        return True
    return normalized in selected_groups


if __name__ == "__main__":
    main()
