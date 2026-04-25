"""add xianyu raw cate policy fields

Revision ID: 20260406_0015
Revises: 20260406_0014
Create Date: 2026-04-06 23:59:30.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260406_0015"
down_revision = "20260406_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "xianyu_category_mapping",
        sa.Column(
            "policy_mode",
            sa.String(length=32),
            nullable=False,
            server_default="FORCE_TEMPLATE",
        ),
    )
    op.add_column(
        "xianyu_category_mapping",
        sa.Column("template_override_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_xianyu_category_mapping_template_override_id",
        "xianyu_category_mapping",
        "category_attr_template",
        ["template_override_id"],
        ["id"],
    )
    op.alter_column(
        "xianyu_category_mapping",
        "category_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.alter_column(
        "xianyu_category_mapping",
        "template_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "xianyu_category_mapping",
        "template_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "xianyu_category_mapping",
        "category_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_constraint(
        "fk_xianyu_category_mapping_template_override_id",
        "xianyu_category_mapping",
        type_="foreignkey",
    )
    op.drop_column("xianyu_category_mapping", "template_override_id")
    op.drop_column("xianyu_category_mapping", "policy_mode")
