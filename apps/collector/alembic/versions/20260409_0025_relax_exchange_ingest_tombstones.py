"""relax exchange keyword ingest tombstones

Revision ID: 20260409_0025
Revises: 20260409_0024
Create Date: 2026-04-09 03:30:00
"""

from __future__ import annotations

from alembic import op


revision = "20260409_0025"
down_revision = "20260409_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 可置换 is not a durable garbage signal by itself. It often describes trade-in
    # willingness or commercial style around a real device, so do not permanently
    # tombstone it at ingest time unless another clear hard-block token is present.
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
    op.execute(
        r"""
        delete from item_ingest_rejection r
        using items i
        where r.source_platform = i.source_platform
          and r.item_id = i.item_id
          and r.business_domain = 'apple_computer'
          and r.rejection_stage = 'historical_category_gate'
          and r.rejection_reason = 'apple_hard_block'
          and regexp_replace(lower(coalesce(i.title, '')), '\s+', '', 'g') !~ '(高价回收|现金回收|回收芯片|回收ic|回收电子元器件|求购|收个|慢收|代拍|代购|主板|屏幕总成|硬盘颗粒)'
        """
    )


def downgrade() -> None:
    pass
