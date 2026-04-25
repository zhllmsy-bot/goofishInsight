"""add xianyu category mapping

Revision ID: 20260406_0009
Revises: 20260405_0008
Create Date: 2026-04-06 14:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260406_0009"
down_revision = "20260405_0008"
branch_labels = None
depends_on = None


xianyu_category_match_scope = postgresql.ENUM(
    "CAT",
    "TB_CAT",
    "CAT_TB",
    "C_CAT",
    name="xianyu_category_match_scope",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    xianyu_category_match_scope.create(bind, checkfirst=True)

    op.add_column("items", sa.Column("xianyu_cat_id", sa.String(length=64), nullable=True))
    op.add_column("items", sa.Column("xianyu_tb_cat_id", sa.String(length=64), nullable=True))
    op.add_column("items", sa.Column("xianyu_c_cat_id", sa.String(length=64), nullable=True))
    op.create_index(
        "idx_items_xianyu_category_ids",
        "items",
        ["source_platform", "xianyu_cat_id", "xianyu_tb_cat_id", "xianyu_c_cat_id"],
    )

    op.create_table(
        "xianyu_category_mapping",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("match_scope", xianyu_category_match_scope, nullable=False),
        sa.Column("match_key", sa.String(length=255), nullable=False),
        sa.Column("xianyu_cat_id", sa.String(length=64), nullable=True),
        sa.Column("xianyu_tb_cat_id", sa.String(length=64), nullable=True),
        sa.Column("xianyu_c_cat_id", sa.String(length=64), nullable=True),
        sa.Column("raw_category_name", sa.String(length=255), nullable=True),
        sa.Column("raw_category_path", sa.String(length=512), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("category.id"), nullable=False),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category_attr_template.id"),
            nullable=False,
        ),
        sa.Column("resolution_source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "(xianyu_cat_id IS NOT NULL) OR (xianyu_tb_cat_id IS NOT NULL) OR (xianyu_c_cat_id IS NOT NULL)",
            name="ck_xianyu_category_mapping_any_raw_id",
        ),
        sa.UniqueConstraint("match_key", name="uq_xianyu_category_mapping_match_key"),
    )
    op.create_index(
        "idx_xianyu_category_mapping_target",
        "xianyu_category_mapping",
        ["category_id", "template_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_xianyu_category_mapping_target", table_name="xianyu_category_mapping")
    op.drop_table("xianyu_category_mapping")

    op.drop_index("idx_items_xianyu_category_ids", table_name="items")
    op.drop_column("items", "xianyu_c_cat_id")
    op.drop_column("items", "xianyu_tb_cat_id")
    op.drop_column("items", "xianyu_cat_id")

    bind = op.get_bind()
    xianyu_category_match_scope.drop(bind, checkfirst=True)
