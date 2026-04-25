"""add item_review_v3 table

Revision ID: 20260411_0029
Revises: 20260409_0028
Create Date: 2026-04-11 01:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260411_0029"
down_revision = "20260409_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_review_v3",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("item_id_ref", sa.BigInteger(), nullable=False),
        sa.Column("business_domain", sa.String(length=64), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("model_catalog_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("pipeline_version", sa.String(length=32), nullable=False, server_default="v3"),
        sa.Column("stage_status", sa.String(length=64), nullable=False, server_default="pending"),
        sa.Column("resolution_status", sa.String(length=64), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("reject_reason", sa.String(length=128), nullable=True),
        sa.Column("needs_human", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("first_pass_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("second_pass_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("llm_provider", sa.String(length=64), nullable=True),
        sa.Column("llm_model", sa.String(length=128), nullable=True),
        sa.Column("extracted_features", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("mapping_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("candidate_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("second_pass_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("final_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.ForeignKeyConstraint(["item_id_ref"], ["items.id"]),
        sa.ForeignKeyConstraint(["model_catalog_id"], ["category_model_catalog.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["category_attr_template.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id_ref", name="uq_item_review_v3_item_id_ref"),
    )
    op.create_index("ix_item_review_v3_resolution_status", "item_review_v3", ["resolution_status"])
    op.create_index("ix_item_review_v3_business_domain", "item_review_v3", ["business_domain"])


def downgrade() -> None:
    op.drop_index("ix_item_review_v3_business_domain", table_name="item_review_v3")
    op.drop_index("ix_item_review_v3_resolution_status", table_name="item_review_v3")
    op.drop_table("item_review_v3")
