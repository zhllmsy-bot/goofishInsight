"""backfill price floor ingest rejections

Revision ID: 20260409_0023
Revises: 20260409_0022
Create Date: 2026-04-09 02:25:00
"""

from __future__ import annotations

from alembic import op


revision = "20260409_0023"
down_revision = "20260409_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
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
          coalesce(resolved_category_id, target_category_id) as category_id,
          'historical_price_floor' as rejection_stage,
          case
            when business_domain = 'apple_computer' then 'apple_price_floor'
            when business_domain = 'garmin_watch' then 'garmin_price_floor'
          end as rejection_reason,
          1 as hit_count,
          least(created_at, last_seen_at) as first_rejected_at,
          last_seen_at as last_rejected_at,
          now() as created_at,
          now() as updated_at
        from items
        where (
            business_domain = 'apple_computer'
            and current_price is not null
            and current_price < 800
          )
          or (
            business_domain = 'garmin_watch'
            and current_price is not null
            and current_price <= 300
          )
        on conflict (source_platform, item_id) do nothing
        """
    )


def downgrade() -> None:
    op.execute(
        """
        delete from item_ingest_rejection
        where rejection_stage = 'historical_price_floor'
        """
    )
