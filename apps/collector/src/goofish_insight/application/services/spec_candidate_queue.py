from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import and_, or_, select

from ...category_compat import compatible_scope_keys, resolve_category_code
from ...db import session_scope
from ...models import Item, ItemSpecEnrichment
from ...pricing import title_is_non_comparable_listing
from .pricing_eligibility import MIN_SPEC_CONFIDENCE_FOR_PRICING
from .spec_enrichment_policy import should_auto_retry_existing_enrichment

SessionFactory = Callable[[], Any]



def filter_frozen_db_item_ids(*, db_item_ids: list[int], frozen_db_ids: set[int]) -> list[int]:
    return [db_item_id for db_item_id in db_item_ids if db_item_id not in frozen_db_ids]



def load_items_for_enrichment(
    *,
    business_domain: str | None,
    item_id: str | None,
    limit: int,
    force: bool,
    session_factory: SessionFactory = session_scope,
) -> list[int]:
    with session_factory() as session:
        stmt = (
            select(Item, ItemSpecEnrichment)
            .outerjoin(ItemSpecEnrichment, ItemSpecEnrichment.item_id_ref == Item.id)
            .order_by(Item.last_seen_at.desc(), Item.id.desc())
        )
        scope_keys = compatible_scope_keys(business_domain)
        if scope_keys:
            stmt = stmt.where(Item.business_domain.in_(scope_keys))
        if item_id:
            stmt = stmt.where(Item.item_id == item_id)
        if not force:
            stmt = stmt.where(
                or_(
                    ItemSpecEnrichment.id.is_(None),
                    ItemSpecEnrichment.confidence.is_(None),
                    ItemSpecEnrichment.status.in_(("unresolved", "failed")),
                    and_(
                        ItemSpecEnrichment.status == "complete",
                        ItemSpecEnrichment.confidence < Decimal(str(MIN_SPEC_CONFIDENCE_FOR_PRICING)),
                    ),
                    and_(
                        ItemSpecEnrichment.status == "partial",
                        ItemSpecEnrichment.confidence < Decimal(str(MIN_SPEC_CONFIDENCE_FOR_PRICING)),
                        ItemSpecEnrichment.needs_review.is_(True),
                    ),
                )
            )
        fetch_limit = limit if limit >= 500 else max(limit * 8, 200)
        rows = list(session.execute(stmt.limit(fetch_limit)).all())
        selected_ids: list[int] = []
        for item, enrichment in rows:
            if (
                item_id is None
                and resolve_category_code(item.business_domain) == "camera_interchangeable_lens"
                and title_is_non_comparable_listing(
                    business_domain=item.business_domain,
                    title=item.title,
                    price=item.current_price,
                )
            ):
                continue
            if item_id is None and not force and not should_auto_retry_existing_enrichment(
                item=item,
                enrichment=enrichment,
            ):
                continue
            selected_ids.append(int(item.id))
            if len(selected_ids) >= limit:
                break
        return selected_ids



def load_pending_db_item_ids(
    *,
    business_domain: str | None,
    limit: int,
    frozen_db_ids: set[int],
    candidate_loader: Callable[..., list[int]] = load_items_for_enrichment,
) -> list[int]:
    candidate_ids = candidate_loader(
        business_domain=business_domain,
        item_id=None,
        limit=limit,
        force=False,
    )
    return filter_frozen_db_item_ids(db_item_ids=candidate_ids, frozen_db_ids=frozen_db_ids)



def count_pending_enrichments(
    *,
    business_domain: str | None,
    frozen_db_ids: set[int] | None = None,
    candidate_loader: Callable[..., list[int]] = load_items_for_enrichment,
) -> int:
    frozen = frozen_db_ids or set()
    return len(
        load_pending_db_item_ids(
            business_domain=business_domain,
            limit=100_000,
            frozen_db_ids=frozen,
            candidate_loader=candidate_loader,
        )
    )
