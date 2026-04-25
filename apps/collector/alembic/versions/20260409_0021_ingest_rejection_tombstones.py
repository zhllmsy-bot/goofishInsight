"""ingest rejection tombstones

Revision ID: 20260409_0021
Revises: 20260409_0020
Create Date: 2026-04-09 01:20:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260409_0021"
down_revision = "20260409_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_ingest_rejection",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_platform", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("business_domain", sa.String(length=64), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("rejection_stage", sa.String(length=64), nullable=False),
        sa.Column("rejection_reason", sa.String(length=128), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "first_rejected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_rejected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_platform",
            "item_id",
            name="uq_item_ingest_rejection_platform_item",
        ),
    )
    op.create_index(
        "ix_item_ingest_rejection_domain_reason",
        "item_ingest_rejection",
        ["business_domain", "rejection_reason"],
    )
    op.create_index(
        "ix_item_ingest_rejection_last_rejected_at",
        "item_ingest_rejection",
        ["last_rejected_at"],
    )

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
          'historical_backfill' as rejection_stage,
          'title_length_gt_800' as rejection_reason,
          1 as hit_count,
          least(created_at, last_seen_at) as first_rejected_at,
          last_seen_at as last_rejected_at,
          now() as created_at,
          now() as updated_at
        from items
        where char_length(coalesce(title, '')) > 800
        on conflict (source_platform, item_id) do nothing
        """
    )

    op.drop_column("items", "title_tokens")


def downgrade() -> None:
    op.add_column(
        "items",
        sa.Column(
            "title_tokens",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("items", "title_tokens", server_default=None)
    op.drop_index("ix_item_ingest_rejection_last_rejected_at", table_name="item_ingest_rejection")
    op.drop_index("ix_item_ingest_rejection_domain_reason", table_name="item_ingest_rejection")
    op.drop_table("item_ingest_rejection")
