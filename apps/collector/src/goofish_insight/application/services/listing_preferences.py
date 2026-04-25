from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Item, UserListingPreference

ListingPreferenceValue = Literal["interested", "not_interested"]


def upsert_user_listing_preference(
    session: Session,
    *,
    item_id: str,
    preference: ListingPreferenceValue,
    operator_id: str = "local",
    source: str = "dashboard",
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_item_id = item_id.strip()
    if not normalized_item_id:
        raise ValueError("item_id is required")

    item = session.execute(select(Item).where(Item.item_id == normalized_item_id)).scalar_one_or_none()
    existing = session.execute(
        select(UserListingPreference)
        .where(UserListingPreference.operator_id == operator_id)
        .where(UserListingPreference.source == source)
        .where(UserListingPreference.item_id == normalized_item_id)
    ).scalar_one_or_none()

    row = existing or UserListingPreference(
        operator_id=operator_id,
        source=source,
        item_id=normalized_item_id,
    )
    row.item_id_ref = item.id if item else None
    row.preference = preference
    row.status = "active"
    row.reason = reason
    row.metadata_json = {
        **(row.metadata_json or {}),
        **(metadata or {}),
        "item_found": bool(item),
    }
    if existing is None:
        session.add(row)

    session.flush()
    return serialize_user_listing_preference(row)


def serialize_user_listing_preference(row: UserListingPreference) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "operatorId": row.operator_id,
        "source": row.source,
        "itemId": row.item_id,
        "preference": row.preference,
        "status": row.status,
        "reason": row.reason,
        "metadata": row.metadata_json or {},
        "updatedAt": row.updated_at,
    }
