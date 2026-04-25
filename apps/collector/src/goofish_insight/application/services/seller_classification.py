from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, func, select

from ...db import session_scope
from ...models import Item, SellerProfile

COMMERCIAL_NAME_TOKENS: tuple[str, ...] = (
    "严选",
    "爱回收",
    "回收",
    "仓",
    "店",
    "铺",
    "社",
    "数码",
    "优品",
    "寄卖",
    "专营",
    "商城",
    "官方",
)


@dataclass(frozen=True, slots=True)
class SellerClassificationInput:
    seller_name: str | None
    item_count: int
    active_item_count: int
    domain_count: int


@dataclass(frozen=True, slots=True)
class SellerClassification:
    seller_type: str
    confidence: float
    signals: list[str]


def classify_seller_profile(input_row: SellerClassificationInput) -> SellerClassification:
    name = str(input_row.seller_name or "")
    signals: list[str] = []
    commercial_hits = [token for token in COMMERCIAL_NAME_TOKENS if token in name]
    if commercial_hits:
        signals.append(f"name:{'/'.join(commercial_hits[:3])}")
    if input_row.item_count >= 30:
        signals.append("item_count>=30")
    elif input_row.item_count >= 10:
        signals.append("item_count>=10")
    if input_row.active_item_count >= 20:
        signals.append("active_item_count>=20")
    if input_row.domain_count >= 2 and input_row.item_count >= 10:
        signals.append("multi_domain_seller")

    if commercial_hits or input_row.item_count >= 30 or input_row.active_item_count >= 20:
        confidence = 0.85 if commercial_hits or input_row.item_count >= 30 else 0.75
        return SellerClassification("commercial_like", confidence, signals)
    if input_row.item_count >= 10:
        return SellerClassification("commercial_like", 0.65, signals)
    if input_row.item_count <= 2 and input_row.active_item_count <= 2:
        return SellerClassification("private_like", 0.55, signals or ["low_repeat_seller"])
    return SellerClassification("unknown", 0.40, signals or ["insufficient_signal"])


def classify_seller_types(*, dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
    with session_scope() as session:
        return classify_seller_types_with_session(session=session, dry_run=dry_run, limit=limit)


def classify_seller_types_with_session(*, session, dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
    stmt = (
        select(
            SellerProfile,
            func.count(Item.id).label("item_count"),
            func.count(Item.id).filter(Item.is_active.is_(True)).label("active_item_count"),
            func.count(func.distinct(Item.business_domain)).label("domain_count"),
        )
        .outerjoin(Item, Item.seller_profile_id == SellerProfile.id)
        .group_by(SellerProfile.id)
        .order_by(desc("item_count"), SellerProfile.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = session.execute(stmt).all()
    summary = Counter()
    updated_count = 0
    samples: list[dict[str, Any]] = []

    for seller, item_count, active_item_count, domain_count in rows:
        classification = classify_seller_profile(
            SellerClassificationInput(
                seller_name=seller.seller_name,
                item_count=int(item_count or 0),
                active_item_count=int(active_item_count or 0),
                domain_count=int(domain_count or 0),
            )
        )
        summary[classification.seller_type] += 1
        existing_metadata = dict(seller.metadata_json or {})
        next_metadata = {
            **existing_metadata,
            "sellerType": classification.seller_type,
            "sellerTypeConfidence": classification.confidence,
            "sellerTypeSignals": classification.signals,
            "sellerTypeSource": "heuristic_v1",
            "sellerTypeNote": "Heuristic only; Goofish did not provide a reliable private/merchant flag in captured rows.",
        }
        if existing_metadata != next_metadata:
            updated_count += 1
            if not dry_run:
                seller.metadata_json = next_metadata
        if len(samples) < 12:
            samples.append(
                {
                    "sellerId": seller.seller_id,
                    "sellerName": seller.seller_name,
                    "sellerType": classification.seller_type,
                    "confidence": classification.confidence,
                    "signals": classification.signals,
                    "itemCount": int(item_count or 0),
                    "activeItemCount": int(active_item_count or 0),
                    "domainCount": int(domain_count or 0),
                }
            )

    return {
        "dryRun": dry_run,
        "sellerCount": len(rows),
        "updatedCount": updated_count,
        "summary": dict(sorted(summary.items())),
        "samples": samples,
    }
