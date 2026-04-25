"""lower title length tombstone gate to 500

Revision ID: 20260409_0028
Revises: 20260409_0027
Create Date: 2026-04-09 17:10:00
"""

from __future__ import annotations

from alembic import op


revision = "20260409_0028"
down_revision = "20260409_0027"
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
          'historical_title_length_v2' as rejection_stage,
          'title_length_gt_500' as rejection_reason,
          1 as hit_count,
          least(created_at, last_seen_at) as first_rejected_at,
          last_seen_at as last_rejected_at,
          now() as created_at,
          now() as updated_at
        from items
        where char_length(coalesce(title, '')) > 500
        on conflict (source_platform, item_id) do update
          set rejection_stage = excluded.rejection_stage,
              rejection_reason = excluded.rejection_reason,
              last_rejected_at = greatest(item_ingest_rejection.last_rejected_at, excluded.last_rejected_at),
              updated_at = now(),
              hit_count = item_ingest_rejection.hit_count + 1
        """
    )


def downgrade() -> None:
    op.execute(
        """
        delete from item_ingest_rejection
        where rejection_stage = 'historical_title_length_v2'
          and rejection_reason = 'title_length_gt_500'
        """
    )
