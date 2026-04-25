"""relax generic buyback tombstones

Revision ID: 20260409_0026
Revises: 20260409_0025
Create Date: 2026-04-09 03:50:00
"""

from __future__ import annotations

from alembic import op


revision = "20260409_0026"
down_revision = "20260409_0025"
branch_labels = None
depends_on = None


APPLE_STRONG_BLOCK = r"(高价回收|现金回收|回收芯片|回收ic|回收电子元器件|求购|收个|慢收|代拍|代购|主板|屏幕总成|硬盘颗粒)"
GARMIN_STRONG_BLOCK = r"(高价回收|现金回收|回收佳明|回收garmin|求购|收个|代拍|代购)"


def upgrade() -> None:
    op.execute(
        rf"""
        delete from item_ingest_rejection r
        using items i
        where r.source_platform = i.source_platform
          and r.item_id = i.item_id
          and r.business_domain = 'garmin_watch'
          and r.rejection_stage = 'historical_category_gate'
          and r.rejection_reason = 'garmin_hard_block'
          and regexp_replace(lower(coalesce(i.title, '')), '\s+', '', 'g') !~ '{GARMIN_STRONG_BLOCK}'
        """
    )
    op.execute(
        rf"""
        delete from item_ingest_rejection r
        using items i
        where r.source_platform = i.source_platform
          and r.item_id = i.item_id
          and r.business_domain = 'apple_computer'
          and r.rejection_stage = 'historical_category_gate'
          and r.rejection_reason = 'apple_hard_block'
          and regexp_replace(lower(coalesce(i.title, '')), '\s+', '', 'g') !~ '{APPLE_STRONG_BLOCK}'
        """
    )


def downgrade() -> None:
    pass
