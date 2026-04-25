#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import and_, desc, not_, or_, select

from goofish_insight.application.services.review_v3_pipeline import (
    run_review_v3_first_pass,
    run_review_v3_second_pass,
)
from goofish_insight.db import SessionLocal
from goofish_insight.models import Item, ItemReviewV3

DEFAULT_CATEGORIES = (
    "apple_airpods",
    "apple_computer",
    "camera_body",
    "camera_interchangeable_lens",
    "garmin_watch",
    "phone",
)


@dataclass
class SampleSelection:
    business_domain: str
    item_id: str
    source_business_domain: str | None
    title: str
    last_seen_at: str | None


KEYWORD_IPHONE = or_(Item.title.ilike("%iphone%"), Item.title.ilike("%苹果手机%"))
KEYWORD_AIRPODS = or_(Item.title.ilike("%airpods%"), Item.title.ilike("%苹果耳机%"))
KEYWORD_MAC = or_(
    Item.title.ilike("%macbook%"),
    Item.title.ilike("%mac studio%"),
    Item.title.ilike("%mac mini%"),
    Item.title.ilike("%macbook pro%"),
    Item.title.ilike("%macbook air%"),
)
KEYWORD_GARMIN = or_(Item.title.ilike("%garmin%"), Item.title.ilike("%佳明%"))
KEYWORD_AIRPODS_SPAM = or_(
    Item.title.ilike("%官网直发%"),
    Item.title.ilike("%接单中%"),
    Item.title.ilike("%手机壳%"),
)


def selection_condition(domain: str):
    if domain == "camera_body":
        return Item.business_domain == domain
    if domain == "camera_interchangeable_lens":
        return Item.business_domain == domain
    if domain == "garmin_watch":
        return Item.business_domain == domain
    if domain == "apple_computer":
        return and_(Item.business_domain == domain, not_(KEYWORD_IPHONE), not_(KEYWORD_AIRPODS))
    if domain == "phone":
        return and_(KEYWORD_IPHONE, not_(KEYWORD_AIRPODS), not_(KEYWORD_MAC), not_(KEYWORD_GARMIN))
    if domain == "apple_airpods":
        return and_(KEYWORD_AIRPODS, not_(KEYWORD_MAC), not_(KEYWORD_AIRPODS_SPAM))
    raise ValueError(f"Unsupported category: {domain}")


def select_samples(*, business_domain: str, count: int) -> list[SampleSelection]:
    stmt = (
        select(Item.item_id, Item.business_domain, Item.title, Item.last_seen_at)
        .where(Item.is_active.is_(True))
        .where(selection_condition(business_domain))
        .order_by(desc(Item.last_seen_at), desc(Item.created_at))
        .limit(count)
    )
    with SessionLocal() as session:
        rows = session.execute(stmt).all()
    return [
        SampleSelection(
            business_domain=business_domain,
            item_id=item_id,
            source_business_domain=source_business_domain,
            title=title,
            last_seen_at=last_seen_at.isoformat() if last_seen_at else None,
        )
        for item_id, source_business_domain, title, last_seen_at in rows
    ]


def load_review_row(*, business_domain: str, item_id: str) -> tuple[ItemReviewV3 | None, Item | None]:
    with SessionLocal() as session:
        row = session.execute(
            select(ItemReviewV3, Item)
            .join(Item, Item.id == ItemReviewV3.item_id_ref)
            .where(Item.item_id == item_id)
            .where(ItemReviewV3.business_domain == business_domain)
        ).first()
    if row is None:
        return None, None
    return row[0], row[1]


def collect_sample_state(
    *,
    business_domain: str,
    item_id: str,
    first_pass: dict[str, Any] | None = None,
    second_pass: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review_row, item_row = load_review_row(business_domain=business_domain, item_id=item_id)
    payload: dict[str, Any] = {
        "item_id": item_id,
        "business_domain": business_domain,
        "source_business_domain": item_row.business_domain if item_row else None,
        "title": item_row.title if item_row else None,
        "first_pass": first_pass,
        "second_pass": second_pass,
        "final": None,
    }
    if review_row is not None:
        payload["final"] = {
            "resolution_status": review_row.resolution_status,
            "stage_status": review_row.stage_status,
            "model_catalog_id": str(review_row.model_catalog_id) if review_row.model_catalog_id else None,
            "first_pass_confidence": float(review_row.first_pass_confidence) if review_row.first_pass_confidence is not None else None,
            "second_pass_confidence": float(review_row.second_pass_confidence) if review_row.second_pass_confidence is not None else None,
            "needs_human": bool(review_row.needs_human),
            "candidate_count": len(list(review_row.candidate_payload or [])),
            "reject_reason": review_row.reject_reason,
        }
    return payload


def run_sample(*, business_domain: str, item_id: str, execute: bool) -> dict[str, Any]:
    first_pass: dict[str, Any] | None = None
    second_pass: dict[str, Any] | None = None
    if execute:
        first_pass_results = run_review_v3_first_pass(
            business_domain=business_domain,
            item_id=item_id,
            limit=1,
            force=True,
        )
        first_pass = first_pass_results[0] if first_pass_results else {"item_id": item_id, "business_domain": business_domain}
        if first_pass.get("resolution_status") == "PENDING_REVIEW":
            second_pass_results = run_review_v3_second_pass(
                business_domain=business_domain,
                item_id=item_id,
                limit=1,
                force=True,
            )
            second_pass = second_pass_results[0] if second_pass_results else None
    return collect_sample_state(
        business_domain=business_domain,
        item_id=item_id,
        first_pass=first_pass,
        second_pass=second_pass,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run review-v3 validation samples across categories.")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--category", action="append", dest="categories")
    parser.add_argument(
        "--skip-execution",
        action="store_true",
        help="Only inspect current review_v3 rows for the selected samples; do not call the model.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/review_v3_validation_samples_20260411.json"),
    )
    args = parser.parse_args()

    categories = tuple(args.categories or DEFAULT_CATEGORIES)
    report: dict[str, Any] = {
        "countPerCategory": args.count,
        "categories": {},
        "summary": {},
    }

    overall_counter: Counter[str] = Counter()
    for category in categories:
        selections = select_samples(business_domain=category, count=args.count)
        entries = [
            run_sample(
                business_domain=category,
                item_id=sample.item_id,
                execute=not args.skip_execution,
            )
            for sample in selections
        ]
        status_counter = Counter((entry.get("final") or {}).get("resolution_status") or "NO_V3_ROW" for entry in entries)
        overall_counter.update(status_counter)
        report["categories"][category] = {
            "selected": [asdict(sample) for sample in selections],
            "results": entries,
            "statusCounts": dict(status_counter),
        }

    report["summary"] = {
        "categories": list(categories),
        "overallStatusCounts": dict(overall_counter),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
