"""add source platform columns

Revision ID: 20260321_0005
Revises: 20260321_0004
Create Date: 2026-03-21 23:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260321_0005"
down_revision = "20260321_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crawl_tasks",
        sa.Column("source_platform", sa.String(length=32), nullable=False, server_default="xianyu"),
    )
    op.add_column(
        "raw_requests",
        sa.Column("source_platform", sa.String(length=32), nullable=False, server_default="xianyu"),
    )
    op.add_column(
        "raw_responses",
        sa.Column("source_platform", sa.String(length=32), nullable=False, server_default="xianyu"),
    )
    op.add_column(
        "items",
        sa.Column("source_platform", sa.String(length=32), nullable=False, server_default="xianyu"),
    )


def downgrade() -> None:
    op.drop_column("items", "source_platform")
    op.drop_column("raw_responses", "source_platform")
    op.drop_column("raw_requests", "source_platform")
    op.drop_column("crawl_tasks", "source_platform")
