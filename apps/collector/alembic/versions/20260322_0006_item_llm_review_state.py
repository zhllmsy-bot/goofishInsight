"""add item llm review state columns

Revision ID: 20260322_0006
Revises: 20260321_0005
Create Date: 2026-03-22 10:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260322_0006"
down_revision = "20260321_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("llm_reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "items",
        sa.Column("llm_review_status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "items",
        sa.Column("llm_review_reason", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column("llm_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("items", "llm_reviewed_at")
    op.drop_column("items", "llm_review_reason")
    op.drop_column("items", "llm_review_status")
    op.drop_column("items", "llm_reviewed")
