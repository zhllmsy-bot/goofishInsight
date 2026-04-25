"""add category runtime profile

Revision ID: 20260406_0011
Revises: 20260406_0010
Create Date: 2026-04-06 20:52:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260406_0011"
down_revision = "20260406_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "category_runtime_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("category.id"), nullable=False),
        sa.Column(
            "active_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category_attr_template.id"),
            nullable=True,
        ),
        sa.Column("prompt_profile", sa.String(length=64), nullable=False),
        sa.Column("extractor_profile", sa.String(length=64), nullable=True),
        sa.Column("validator_profile", sa.String(length=64), nullable=True),
        sa.Column("llm_provider_override", sa.String(length=64), nullable=True),
        sa.Column("llm_model_override", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("category_id", name="uq_category_runtime_profile_category"),
    )
    op.create_index(
        "idx_category_runtime_profile_status",
        "category_runtime_profile",
        ["status", "prompt_profile"],
    )


def downgrade() -> None:
    op.drop_index("idx_category_runtime_profile_status", table_name="category_runtime_profile")
    op.drop_table("category_runtime_profile")
