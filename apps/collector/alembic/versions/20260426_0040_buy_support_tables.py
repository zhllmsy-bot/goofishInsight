"""add buy support tables

Revision ID: 20260426_0040
Revises: 20260426_0039
Create Date: 2026-04-26 15:40:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260426_0040"
down_revision = "20260426_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "condition_adjusters",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("scope_key", sa.String(length=64), nullable=False),
        sa.Column("condition_code", sa.String(length=32), nullable=False),
        sa.Column("condition_label", sa.String(length=64), nullable=True),
        sa.Column(
            "match_tokens",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("multiplier", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("scope_key", "condition_code", name="uq_condition_adjuster_scope_code"),
    )
    op.create_index(
        "ix_condition_adjuster_scope_status",
        "condition_adjusters",
        ["scope_key", "status", "priority"],
    )

    op.create_table(
        "sku_neighbors",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "schema_id",
            sa.BigInteger(),
            sa.ForeignKey("sku_spec_schema_snapshots.schema_id"),
            nullable=False,
        ),
        sa.Column(
            "sku_fingerprint_id",
            sa.BigInteger(),
            sa.ForeignKey("sku_fingerprints.id"),
            nullable=False,
        ),
        sa.Column(
            "neighbor_fingerprint_id",
            sa.BigInteger(),
            sa.ForeignKey("sku_fingerprints.id"),
            nullable=False,
        ),
        sa.Column("neighbor_rank", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("similarity_score", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("sku_fingerprint_id", "neighbor_fingerprint_id", name="uq_sku_neighbor_pair"),
    )
    op.create_index("ix_sku_neighbor_lookup", "sku_neighbors", ["sku_fingerprint_id", "neighbor_rank"])
    op.create_index("ix_sku_neighbor_schema", "sku_neighbors", ["schema_id", "neighbor_rank"])

    op.create_table(
        "msrp_anchors",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("scope_key", sa.String(length=64), nullable=False),
        sa.Column(
            "model_catalog_id",
            sa.String(length=64),
            sa.ForeignKey("category_model_catalog.id"),
            nullable=True,
        ),
        sa.Column(
            "schema_id",
            sa.BigInteger(),
            sa.ForeignKey("sku_spec_schema_snapshots.schema_id"),
            nullable=True,
        ),
        sa.Column("anchor_key", sa.String(length=255), nullable=False),
        sa.Column("msrp_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("buy_ceiling_ratio", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("source_label", sa.String(length=64), nullable=False, server_default="manual"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "scope_key",
            "model_catalog_id",
            "schema_id",
            "anchor_key",
            name="uq_msrp_anchor_scope_model_schema_key",
        ),
    )
    op.create_index("ix_msrp_anchor_scope_status", "msrp_anchors", ["scope_key", "status"])

    op.create_table(
        "decision_feedback_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column(
            "feedback_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("buy_decision_feedback.id"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("buy_opportunity.id"),
            nullable=False,
        ),
        sa.Column("item_id_ref", sa.BigInteger(), sa.ForeignKey("items.id"), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("category.id"), nullable=True),
        sa.Column("scope_key", sa.String(length=64), nullable=True),
        sa.Column(
            "model_catalog_id",
            sa.String(length=64),
            sa.ForeignKey("category_model_catalog.id"),
            nullable=True,
        ),
        sa.Column(
            "schema_id",
            sa.BigInteger(),
            sa.ForeignKey("sku_spec_schema_snapshots.schema_id"),
            nullable=True,
        ),
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=True),
        sa.Column("baseline_match_level", sa.String(length=64), nullable=True),
        sa.Column("baseline_match_key", sa.String(length=255), nullable=True),
        sa.Column("feedback_type", sa.String(length=64), nullable=False),
        sa.Column("feedback_label", sa.String(length=64), nullable=False),
        sa.Column("feedback_action", sa.String(length=32), nullable=False),
        sa.Column("feedback_category", sa.String(length=64), nullable=True),
        sa.Column("opportunity_status", sa.String(length=32), nullable=True),
        sa.Column("operator_id", sa.String(length=64), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint("feedback_id", name="uq_decision_feedback_log_feedback"),
    )
    op.create_index(
        "ix_decision_feedback_log_opportunity_time",
        "decision_feedback_log",
        ["opportunity_id", "recorded_at"],
    )
    op.create_index(
        "ix_decision_feedback_log_scope_time",
        "decision_feedback_log",
        ["scope_key", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_decision_feedback_log_scope_time", table_name="decision_feedback_log")
    op.drop_index("ix_decision_feedback_log_opportunity_time", table_name="decision_feedback_log")
    op.drop_table("decision_feedback_log")

    op.drop_index("ix_msrp_anchor_scope_status", table_name="msrp_anchors")
    op.drop_table("msrp_anchors")

    op.drop_index("ix_sku_neighbor_schema", table_name="sku_neighbors")
    op.drop_index("ix_sku_neighbor_lookup", table_name="sku_neighbors")
    op.drop_table("sku_neighbors")

    op.drop_index("ix_condition_adjuster_scope_status", table_name="condition_adjusters")
    op.drop_table("condition_adjusters")
