"""add xianyu category onboarding queue

Revision ID: 20260406_0010
Revises: 20260406_0009
Create Date: 2026-04-06 16:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260406_0010"
down_revision = "20260406_0009"
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

    op.create_table(
        "xianyu_category_onboarding_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("match_scope", xianyu_category_match_scope, nullable=False),
        sa.Column("match_key", sa.String(length=255), nullable=False),
        sa.Column("xianyu_cat_id", sa.String(length=64), nullable=True),
        sa.Column("xianyu_tb_cat_id", sa.String(length=64), nullable=True),
        sa.Column("xianyu_c_cat_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("owner_operator_id", sa.String(length=64), nullable=True),
        sa.Column("status_note", sa.Text(), nullable=True),
        sa.Column("item_count_snapshot", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "sample_item_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "sample_titles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "source_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "business_domains",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "resolved_mapping_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
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
            name="ck_xianyu_category_onboarding_queue_any_raw_id",
        ),
        sa.UniqueConstraint("match_key", name="uq_xianyu_category_onboarding_queue_match_key"),
    )
    op.create_index(
        "idx_xianyu_category_onboarding_queue_status",
        "xianyu_category_onboarding_queue",
        ["status", "item_count_snapshot"],
    )


def downgrade() -> None:
    op.drop_index("idx_xianyu_category_onboarding_queue_status", table_name="xianyu_category_onboarding_queue")
    op.drop_table("xianyu_category_onboarding_queue")
