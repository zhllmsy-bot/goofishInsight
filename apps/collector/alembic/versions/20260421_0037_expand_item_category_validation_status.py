"""expand items.category_validation_status length

Revision ID: 20260421_0037
Revises: 20260417_0036
Create Date: 2026-04-21 09:10:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260421_0037"
down_revision = "20260417_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "items",
        "category_validation_status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
        existing_server_default=sa.text("'PENDING'::character varying"),
    )


def downgrade() -> None:
    op.alter_column(
        "items",
        "category_validation_status",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default=sa.text("'PENDING'::character varying"),
    )
