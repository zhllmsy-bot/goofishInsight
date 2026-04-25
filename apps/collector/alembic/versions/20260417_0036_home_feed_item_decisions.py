"""add home_feed_item_decision table

Revision ID: 20260417_0036
Revises: 20260417_0035
Create Date: 2026-04-17 23:10:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260417_0036"
down_revision = "20260417_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "home_feed_item_decision",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("item_id_ref", sa.BigInteger(), nullable=True),
        sa.Column("source_platform", sa.String(length=32), nullable=False, server_default="xianyu"),
        sa.Column("decision_stage", sa.String(length=64), nullable=False),
        sa.Column("decision_status", sa.String(length=64), nullable=False),
        sa.Column("decision_source", sa.String(length=64), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("current_outreach_status", sa.String(length=32), nullable=True),
        sa.Column("resolved_business_domain", sa.String(length=64), nullable=True),
        sa.Column("resolved_category_id", sa.String(length=64), nullable=True),
        sa.Column("resolved_template_id", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("match_key", sa.String(length=255), nullable=True),
        sa.Column("match_scope", sa.String(length=32), nullable=True),
        sa.Column(
            "candidate_business_domains",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "active_candidate_business_domains",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["item_id_ref"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_platform",
            "item_id",
            "decision_stage",
            name="uq_home_feed_item_decision_stage",
        ),
    )
    op.create_index(
        "ix_home_feed_item_decision_status_time",
        "home_feed_item_decision",
        ["decision_status", "updated_at"],
    )
    op.create_index(
        "ix_home_feed_item_decision_domain_time",
        "home_feed_item_decision",
        ["resolved_business_domain", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_home_feed_item_decision_domain_time", table_name="home_feed_item_decision")
    op.drop_index("ix_home_feed_item_decision_status_time", table_name="home_feed_item_decision")
    op.drop_table("home_feed_item_decision")
