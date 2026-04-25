"""outreach records

Revision ID: 20260321_0004
Revises: 20260321_0003
Create Date: 2026-03-21 22:35:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260321_0004"
down_revision = "20260321_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outreach_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("item_id_ref", sa.BigInteger(), sa.ForeignKey("items.id"), nullable=True),
        sa.Column("business_domain", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="home_feed"),
        sa.Column("target_label", sa.String(length=255), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("feed_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("target_buy_ceiling", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("item_id", name="uq_outreach_records_item_id"),
    )
    op.create_index(
        "ix_outreach_records_business_domain_status",
        "outreach_records",
        ["business_domain", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outreach_records_business_domain_status", table_name="outreach_records")
    op.drop_table("outreach_records")
