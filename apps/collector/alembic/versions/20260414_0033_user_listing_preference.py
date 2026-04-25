"""add user listing preference table

Revision ID: 20260414_0033
Revises: 20260413_0032
Create Date: 2026-04-14 10:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260414_0033"
down_revision = "20260413_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_listing_preference",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", sa.String(length=64), nullable=False, server_default="local"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="dashboard"),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("item_id_ref", sa.BigInteger(), nullable=True),
        sa.Column("preference", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["item_id_ref"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operator_id", "source", "item_id", name="uq_user_listing_preference_scope"),
    )
    op.create_index("ix_user_listing_preference_item", "user_listing_preference", ["item_id"])
    op.create_index(
        "ix_user_listing_preference_operator_status",
        "user_listing_preference",
        ["operator_id", "status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_listing_preference_operator_status", table_name="user_listing_preference")
    op.drop_index("ix_user_listing_preference_item", table_name="user_listing_preference")
    op.drop_table("user_listing_preference")
