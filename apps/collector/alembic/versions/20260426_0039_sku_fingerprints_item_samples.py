"""add sku_fingerprints and item_samples

Revision ID: 20260426_0039
Revises: 20260425_0038
Create Date: 2026-04-26 10:20:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260426_0039"
down_revision = "20260425_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sku_fingerprints",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "schema_id",
            sa.BigInteger(),
            sa.ForeignKey("sku_spec_schema_snapshots.schema_id"),
            nullable=False,
        ),
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "lock_signature",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("variant_signature", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_signature", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("schema_id", "fingerprint_hash", name="uq_sku_fingerprint_schema_hash"),
    )
    op.create_index(
        "ix_sku_fingerprint_schema",
        "sku_fingerprints",
        ["schema_id", "fingerprint_hash"],
    )

    op.create_table(
        "item_samples",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("item_id_ref", sa.BigInteger(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("sku_fingerprint_id", sa.BigInteger(), sa.ForeignKey("sku_fingerprints.id"), nullable=False),
        sa.Column("sample_state", sa.String(length=32), nullable=False),
        sa.Column(
            "sample_quality_score",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "missing_required_attrs",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "sample_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("condition_multiplier", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "item_id_ref",
            "sku_fingerprint_id",
            name="uq_item_sample_item_fingerprint",
        ),
    )
    op.create_index("ix_item_sample_item", "item_samples", ["item_id_ref"])
    op.create_index("ix_item_sample_fingerprint", "item_samples", ["sku_fingerprint_id"])
    op.create_index("ix_item_sample_state", "item_samples", ["sample_state"])


def downgrade() -> None:
    op.drop_index("ix_item_sample_state", table_name="item_samples")
    op.drop_index("ix_item_sample_fingerprint", table_name="item_samples")
    op.drop_index("ix_item_sample_item", table_name="item_samples")
    op.drop_table("item_samples")
    op.drop_index("ix_sku_fingerprint_schema", table_name="sku_fingerprints")
    op.drop_table("sku_fingerprints")
