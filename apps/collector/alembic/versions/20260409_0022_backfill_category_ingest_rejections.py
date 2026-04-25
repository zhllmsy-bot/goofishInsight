"""backfill category ingest rejections

Revision ID: 20260409_0022
Revises: 20260409_0021
Create Date: 2026-04-09 02:05:00
"""

from __future__ import annotations

from alembic import op


revision = "20260409_0022"
down_revision = "20260409_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        with normalized as (
          select
            i.*,
            regexp_replace(lower(coalesce(i.title, '')), '\s+', '', 'g') as normalized_title
          from items i
        ),
        candidates as (
          select
            source_platform,
            item_id,
            business_domain,
            coalesce(resolved_category_id, target_category_id) as category_id,
            case
              when business_domain = 'apple_computer'
                and normalized_title ~ '(高价回收|现金回收|回收芯片|回收ic|回收电子元器件|求购|收个|慢收|代拍|代购|主板|屏幕总成|硬盘颗粒)'
                then 'apple_hard_block'
              when business_domain = 'apple_computer'
                and current_price is not null
                and current_price <= 800
                and normalized_title ~ '(空盒|包装盒|充电器|电源线|键帽|保护壳|保护膜|贴膜|支架|扩展坞|转接头|转接器)'
                then 'apple_accessory'
              when business_domain = 'garmin_watch'
                and normalized_title ~ '(高价回收|现金回收|回收佳明|回收garmin|求购|收个|代拍|代购)'
                then 'garmin_hard_block'
              else null
            end as rejection_reason,
            least(created_at, last_seen_at) as first_rejected_at,
            last_seen_at as last_rejected_at
          from normalized
        )
        insert into item_ingest_rejection (
          source_platform,
          item_id,
          business_domain,
          category_id,
          rejection_stage,
          rejection_reason,
          hit_count,
          first_rejected_at,
          last_rejected_at,
          created_at,
          updated_at
        )
        select
          source_platform,
          item_id,
          business_domain,
          category_id,
          'historical_category_gate' as rejection_stage,
          rejection_reason,
          1 as hit_count,
          first_rejected_at,
          last_rejected_at,
          now() as created_at,
          now() as updated_at
        from candidates
        where rejection_reason is not null
        on conflict (source_platform, item_id) do nothing
        """
    )


def downgrade() -> None:
    op.execute(
        """
        delete from item_ingest_rejection
        where rejection_stage = 'historical_category_gate'
        """
    )
