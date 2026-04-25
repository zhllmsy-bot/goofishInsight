#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from goofish_insight.application.services.model_config import (
    list_model_configs_with_session,
    upsert_model_config_with_session,
)
from goofish_insight.application.services.task_model_catalog_sync import (
    sync_category_model_catalog_to_tasks_with_session,
)
from goofish_insight.db import session_scope
from goofish_insight.models import Category


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply an allowlist to category model catalog entries and sync tasks.",
    )
    parser.add_argument(
        "--config-path",
        required=True,
        help="Path to the scope allowlist JSON file.",
    )
    parser.add_argument(
        "--operator-id",
        default="admin",
        help="Operator id used for model config audit logs.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes. Without this flag the script runs in dry-run mode.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    category_code = str(config.get("categoryCode") or "").strip()
    allowed_model_codes = {
        str(value).strip()
        for value in list(config.get("allowedModelCodes") or [])
        if str(value).strip()
    }
    disabled_alias_texts = {
        str(value).strip().lower()
        for value in list(config.get("disabledAliasTexts") or [])
        if str(value).strip()
    }
    if not category_code:
        raise SystemExit("config.categoryCode is required")
    if not allowed_model_codes:
        raise SystemExit("config.allowedModelCodes must not be empty")

    dry_run = not bool(args.apply)
    summary: dict[str, Any] = {
        "dryRun": dry_run,
        "configPath": str(config_path),
        "categoryCode": category_code,
        "allowedModelCodeCount": len(allowed_model_codes),
        "activated": [],
        "disabled": [],
        "aliasAdjustedModels": [],
        "unchanged": [],
        "sync": None,
    }

    with session_scope() as session:
        payload = list_model_configs_with_session(session, category_code=category_code)
        items = list(payload.get("items") or [])
        category = session.query(Category).filter(Category.code == category_code).one_or_none()
        if category is None:
            raise SystemExit(f"category not found: {category_code}")

        for item in items:
            model_code = str(item.get("modelCode") or "").strip()
            if not model_code:
                continue
            desired_status = "ACTIVE" if model_code in allowed_model_codes else "DISABLED"
            current_status = str(item.get("status") or "").strip().upper() or "ACTIVE"
            desired_aliases = [
                {
                    "aliasId": alias.get("id"),
                    "aliasText": alias.get("aliasText"),
                    "aliasType": alias.get("aliasType"),
                    "status": _desired_alias_status(
                        alias_text=alias.get("aliasText"),
                        current_status=alias.get("status"),
                        disabled_alias_texts=disabled_alias_texts,
                    ),
                    "metadata": dict(alias.get("metadata") or {}),
                }
                for alias in list(item.get("aliases") or [])
            ]
            alias_changed = any(
                str(alias.get("status") or "").strip().upper() != str(desired.get("status") or "").strip().upper()
                for alias, desired in zip(list(item.get("aliases") or []), desired_aliases)
            )
            if current_status == desired_status and not alias_changed:
                summary["unchanged"].append(model_code)
                continue

            update_payload = {
                "modelId": item.get("id"),
                "categoryCode": item.get("categoryCode"),
                "brandName": item.get("brandName"),
                "seriesName": item.get("seriesName"),
                "modelCode": model_code,
                "modelName": item.get("modelName"),
                "status": desired_status,
                "metadata": dict(item.get("metadata") or {}),
                "aliases": desired_aliases,
            }
            upsert_model_config_with_session(
                session,
                payload=update_payload,
                operator_id=args.operator_id,
                dry_run=dry_run,
                sync_tasks=False,
            )
            if alias_changed:
                summary["aliasAdjustedModels"].append(model_code)
            if current_status != desired_status:
                summary["activated" if desired_status == "ACTIVE" else "disabled"].append(model_code)

        summary["sync"] = sync_category_model_catalog_to_tasks_with_session(session, category=category)
        if dry_run:
            session.rollback()

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def _desired_alias_status(
    *,
    alias_text: Any,
    current_status: Any,
    disabled_alias_texts: set[str],
) -> str:
    normalized_alias = str(alias_text or "").strip().lower()
    if normalized_alias and normalized_alias in disabled_alias_texts:
        return "DISABLED"
    normalized_status = str(current_status or "").strip().upper()
    return normalized_status or "ACTIVE"


if __name__ == "__main__":
    main()
