"""item spec enrichments

Revision ID: 20260321_0003
Revises: 20260321_0002
Create Date: 2026-03-21 19:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260321_0003"
down_revision = "20260321_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_spec_enrichments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("item_id_ref", sa.BigInteger(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("business_domain", sa.String(length=64), nullable=False),
        sa.Column("extractor_type", sa.String(length=32), nullable=False, server_default="rule"),
        sa.Column("extractor_version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("llm_provider", sa.String(length=64), nullable=True),
        sa.Column("llm_model", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="partial"),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("product_line", sa.String(length=128), nullable=True),
        sa.Column("model_family", sa.String(length=128), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("generation", sa.String(length=64), nullable=True),
        sa.Column("case_size_mm", sa.Integer(), nullable=True),
        sa.Column("is_solar", sa.Boolean(), nullable=True),
        sa.Column("display_type", sa.String(length=32), nullable=True),
        sa.Column("screen_size_in", sa.Numeric(4, 1), nullable=True),
        sa.Column("chip_family", sa.String(length=64), nullable=True),
        sa.Column("cpu_model", sa.String(length=64), nullable=True),
        sa.Column("cpu_cores", sa.Integer(), nullable=True),
        sa.Column("gpu_cores", sa.Integer(), nullable=True),
        sa.Column("memory_gb", sa.Integer(), nullable=True),
        sa.Column("storage_gb", sa.Integer(), nullable=True),
        sa.Column("edition_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("extraction_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("item_id_ref", name="uq_item_spec_enrichments_item_id_ref"),
    )
    op.create_index(
        "ix_item_spec_enrichments_business_domain_model_name",
        "item_spec_enrichments",
        ["business_domain", "model_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_item_spec_enrichments_business_domain_model_name", table_name="item_spec_enrichments")
    op.drop_table("item_spec_enrichments")
