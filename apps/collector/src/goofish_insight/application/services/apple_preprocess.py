from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from ...compat import UTC
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ...category_compat import compatible_scope_keys, is_apple_computer_scope
from ...db import session_scope
from ...models import Item
from ...normalizers import normalize_title
from ...settings import get_settings
from ...specs import extract_item_specs

APPLE_BASE_PRICE_FLOORS: dict[str, Decimal] = {
    "MacBook Air": Decimal("800"),
    "MacBook Pro": Decimal("1200"),
    "Mac mini": Decimal("800"),
    "Mac Studio": Decimal("2500"),
    "iMac": Decimal("1000"),
}

APPLE_CHIP_FLOOR_BY_TIER: dict[str, Decimal] = {
    "pro": Decimal("1500"),
    "max": Decimal("2500"),
    "ultra": Decimal("4000"),
}

APPLE_STUDIO_CHIP_FLOOR_BY_TIER: dict[str, Decimal] = {
    "max": Decimal("3500"),
    "ultra": Decimal("7000"),
}
APPLE_M_SERIES_TOKEN_PATTERNS = (
    re.compile(r"(?<![a-z0-9])m[1-5](?:\s*(?:pro|max|ultra)|(?:pro|max|ultra))?(?![a-z0-9])", re.IGNORECASE),
)
APPLE_LEGACY_INTEL_TOKENS = (
    re.compile(r"(?<![a-z0-9])intel(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])core\s*i[3579](?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])i[3579](?![a-z0-9])", re.IGNORECASE),
)

MAX_EXAMPLES = 25


def preprocess_apple_items(
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    summary: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "dry_run": dry_run,
        "items_scanned": 0,
        "items_backfilled": 0,
        "fields_backfilled": 0,
        "items_deactivated": 0,
        "deactivated_by_reason": {},
        "backfill_examples": [],
        "deactivation_examples": [],
        "report_path": None,
    }
    deactivated_by_reason: dict[str, int] = defaultdict(int)

    with session_scope() as session:
        scope_keys = compatible_scope_keys("apple_computer")
        stmt = (
            select(Item)
            .where(Item.business_domain.in_(scope_keys))
            .order_by(Item.id)
        )
        if limit is not None:
            stmt = stmt.limit(limit)

        for item in session.execute(stmt).scalars():
            summary["items_scanned"] += 1
            inferred = build_apple_inference(item)

            fields_changed = apply_static_backfill(item=item, inferred=inferred, dry_run=dry_run)
            if fields_changed:
                summary["items_backfilled"] += 1
                summary["fields_backfilled"] += len(fields_changed)
                if len(summary["backfill_examples"]) < MAX_EXAMPLES:
                    summary["backfill_examples"].append(
                        {
                            "item_id": item.item_id,
                            "title": item.title[:160],
                            "fields": fields_changed,
                        }
                    )

            reason = infer_apple_deactivation_reason(item=item, inferred=inferred)
            if reason is None or not item.is_active:
                continue

            summary["items_deactivated"] += 1
            deactivated_by_reason[reason] += 1
            if len(summary["deactivation_examples"]) < MAX_EXAMPLES:
                summary["deactivation_examples"].append(
                    {
                        "item_id": item.item_id,
                        "title": item.title[:160],
                        "current_price": float(item.current_price) if item.current_price is not None else None,
                        "normalized_model_family": item.normalized_model_family or inferred.get("model_family"),
                        "normalized_chip": item.normalized_chip or inferred.get("chip"),
                        "reason": reason,
                        "min_plausible_price": float(
                            infer_apple_min_plausible_price(
                                model_family=item.normalized_model_family or inferred.get("model_family"),
                                chip_family=item.normalized_chip or inferred.get("chip"),
                            )
                            or Decimal("0")
                        ),
                    }
                )

            if not dry_run:
                item.is_active = False
                apply_apple_rule_deactivation_review_state(item=item, reason=reason)

    summary["deactivated_by_reason"] = dict(sorted(deactivated_by_reason.items()))
    summary["finished_at"] = datetime.now(UTC).isoformat()
    report_path = write_apple_preprocess_report(summary)
    summary["report_path"] = str(report_path)
    return summary


def apply_apple_rule_deactivation_review_state(
    *,
    item: Item,
    reason: str,
    reviewed_at: datetime | None = None,
) -> None:
    review_time = reviewed_at or datetime.now(UTC)
    item.llm_reviewed = True
    item.llm_review_status = "invalid"
    item.llm_review_reason = reason
    item.llm_reviewed_at = review_time
    item.llm_review_confidence = Decimal("1.0")
    item.llm_review_needs_audit = False
    item.llm_review_audit_reason = None
    item.llm_review_decision = {
        "review_status": "invalid",
        "invalid_reason": reason,
        "confidence": 1.0,
        "review_origin": "rule_precheck",
    }


def apply_static_backfill(
    *,
    item: Item,
    inferred: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    if item.normalized_brand is None and inferred.get("brand"):
        changed["normalized_brand"] = inferred["brand"]
        if not dry_run:
            item.normalized_brand = inferred["brand"]
    if item.normalized_model_family is None and inferred.get("model_family"):
        changed["normalized_model_family"] = inferred["model_family"]
        if not dry_run:
            item.normalized_model_family = inferred["model_family"]
    if item.normalized_model is None and inferred.get("model"):
        changed["normalized_model"] = inferred["model"]
        if not dry_run:
            item.normalized_model = inferred["model"]
    if item.normalized_chip is None and inferred.get("chip"):
        changed["normalized_chip"] = inferred["chip"]
        if not dry_run:
            item.normalized_chip = inferred["chip"]
    if item.normalized_memory_gb is None and inferred.get("memory_gb") is not None:
        changed["normalized_memory_gb"] = inferred["memory_gb"]
        if not dry_run:
            item.normalized_memory_gb = inferred["memory_gb"]
    if item.normalized_storage_gb is None and inferred.get("storage_gb") is not None:
        changed["normalized_storage_gb"] = inferred["storage_gb"]
        if not dry_run:
            item.normalized_storage_gb = inferred["storage_gb"]
    return changed


def build_apple_inference(item: Item) -> dict[str, Any]:
    title_inferred = normalize_title(item.title)
    rule_candidate = extract_item_specs(item, allow_llm=False)
    return {
        "brand": rule_candidate.brand or title_inferred.get("brand"),
        "model_family": rule_candidate.product_line or rule_candidate.model_family or title_inferred.get("model_family"),
        "model": rule_candidate.model_name or title_inferred.get("model"),
        "chip": rule_candidate.chip_family or title_inferred.get("chip"),
        "memory_gb": rule_candidate.memory_gb if rule_candidate.memory_gb is not None else title_inferred.get("memory_gb"),
        "storage_gb": rule_candidate.storage_gb if rule_candidate.storage_gb is not None else title_inferred.get("storage_gb"),
    }


def infer_apple_deactivation_reason(
    *,
    item: Item,
    inferred: dict[str, Any],
) -> str | None:
    if not is_apple_computer_scope(item.business_domain):
        return None

    if title_is_legacy_intel_apple(item.title):
        return "apple_non_m_series"

    if item.current_price is None:
        return None

    model_family = item.normalized_model_family or inferred.get("model_family")
    chip_family = item.normalized_chip or inferred.get("chip")
    min_plausible_price = infer_apple_min_plausible_price(
        model_family=model_family,
        chip_family=chip_family,
    )
    if min_plausible_price is None:
        return None
    if item.current_price < min_plausible_price:
        return "apple_price_below_floor"
    return None


def infer_apple_min_plausible_price(
    *,
    model_family: str | None,
    chip_family: str | None,
) -> Decimal | None:
    if not model_family:
        return None

    floor = APPLE_BASE_PRICE_FLOORS.get(model_family)
    if floor is None:
        return None

    normalized_chip = (chip_family or "").lower()
    if model_family == "Mac Studio":
        for tier, tier_floor in APPLE_STUDIO_CHIP_FLOOR_BY_TIER.items():
            if tier in normalized_chip:
                floor = max(floor, tier_floor)
    for tier, tier_floor in APPLE_CHIP_FLOOR_BY_TIER.items():
        if tier in normalized_chip:
            floor = max(floor, tier_floor)
    return floor


def title_is_legacy_intel_apple(title: str) -> bool:
    lowered = title.lower()
    if any(pattern.search(lowered) for pattern in APPLE_M_SERIES_TOKEN_PATTERNS):
        return False
    return any(pattern.search(lowered) for pattern in APPLE_LEGACY_INTEL_TOKENS)


def write_apple_preprocess_report(summary: dict[str, Any]) -> Path:
    settings = get_settings()
    report_dir = settings.base_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report_path = report_dir / f"apple-preprocess-{timestamp}.json"
    report_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report_path
