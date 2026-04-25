"""relax garmin ingest keyword tombstones

Revision ID: 20260409_0024
Revises: 20260409_0023
Create Date: 2026-04-09 03:05:00
"""

from __future__ import annotations

from alembic import op


revision = "20260409_0024"
down_revision = "20260409_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Garmin titles often mention maps, watch faces, straps, or extra bands as normal
    # device context. Keep permanent tombstones only for clear buyback/wanted/proxy-buy
    # signals; price-floor tombstones still catch obvious low-price accessory/service rows.
    op.execute(
        r"""
        delete from item_ingest_rejection r
        using items i
        where r.source_platform = i.source_platform
          and r.item_id = i.item_id
          and r.business_domain = 'garmin_watch'
          and r.rejection_stage = 'historical_category_gate'
          and r.rejection_reason = 'garmin_accessory'
        """
    )
    op.execute(
        r"""
        delete from item_ingest_rejection r
        using items i
        where r.source_platform = i.source_platform
          and r.item_id = i.item_id
          and r.business_domain = 'garmin_watch'
          and r.rejection_stage = 'historical_category_gate'
          and r.rejection_reason = 'garmin_hard_block'
          and regexp_replace(lower(coalesce(i.title, '')), '\s+', '', 'g') !~ '(高价回收|现金回收|回收佳明|回收garmin|求购|收个|代拍|代购)'
        """
    )


def downgrade() -> None:
    # Data relaxation is intentionally not reversible because the previous migration
    # over-tombstoned normal Garmin keyword context.
    pass
