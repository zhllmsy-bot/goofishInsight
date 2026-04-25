"""add buy-side decision tables

Revision ID: 20260408_0019
Revises: 20260407_0018
Create Date: 2026-04-08 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260408_0019"
down_revision = "20260407_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "buy_watch_target",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("category.id"), nullable=False),
        sa.Column(
            "model_catalog_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category_model_catalog.id"),
            nullable=True,
        ),
        sa.Column("target_name", sa.String(length=255), nullable=False),
        sa.Column("profile_key", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("budget_ceiling", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("desired_memory_gb", sa.Integer(), nullable=True),
        sa.Column("desired_storage_gb", sa.Integer(), nullable=True),
        sa.Column("desired_region", sa.String(length=128), nullable=True),
        sa.Column("max_listing_age_hours", sa.Integer(), nullable=True),
        sa.Column("risk_tolerance", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("notify_cooldown_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "category_id",
            "model_catalog_id",
            "target_name",
            "profile_key",
            name="uq_buy_watch_target_scope",
        ),
    )
    op.create_index(
        "idx_buy_watch_target_category_status",
        "buy_watch_target",
        ["category_id", "status"],
    )

    op.create_table(
        "buy_price_baseline",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("category.id"), nullable=False),
        sa.Column(
            "model_catalog_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category_model_catalog.id"),
            nullable=True,
        ),
        sa.Column("baseline_key", sa.String(length=255), nullable=False),
        sa.Column("memory_gb", sa.Integer(), nullable=True),
        sa.Column("storage_gb", sa.Integer(), nullable=True),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("median_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("p25_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("p75_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("fair_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("buy_ceiling", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("baseline_date", sa.Date(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "category_id",
            "model_catalog_id",
            "baseline_key",
            "baseline_date",
            name="uq_buy_price_baseline_key_date",
        ),
    )
    op.create_index(
        "idx_buy_price_baseline_scope_date",
        "buy_price_baseline",
        ["category_id", "model_catalog_id", "baseline_date"],
    )

    op.create_table(
        "buy_opportunity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("item_id_ref", sa.BigInteger(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("category.id"), nullable=True),
        sa.Column(
            "model_catalog_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category_model_catalog.id"),
            nullable=True,
        ),
        sa.Column(
            "watch_target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("buy_watch_target.id"),
            nullable=False,
        ),
        sa.Column(
            "baseline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("buy_price_baseline.id"),
            nullable=True,
        ),
        sa.Column("current_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("fair_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("buy_ceiling", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("discount_rate", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("opportunity_score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("risk_score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("item_id_ref", "watch_target_id", name="uq_buy_opportunity_item_target"),
    )
    op.create_index(
        "idx_buy_opportunity_status_score",
        "buy_opportunity",
        ["status", "opportunity_score"],
    )
    op.create_index(
        "idx_buy_opportunity_category_status",
        "buy_opportunity",
        ["category_id", "status"],
    )

    op.create_table(
        "buy_opportunity_risk",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("buy_opportunity.id"),
            nullable=False,
        ),
        sa.Column("risk_code", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "evidence_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("opportunity_id", "risk_code", name="uq_buy_opportunity_risk_code"),
    )

    op.create_table(
        "buy_alert_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("buy_opportunity.id"),
            nullable=False,
        ),
        sa.Column(
            "watch_target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("buy_watch_target.id"),
            nullable=False,
        ),
        sa.Column("alert_channel", sa.String(length=64), nullable=False, server_default="dashboard"),
        sa.Column("alert_reason", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_buy_alert_event_target_status",
        "buy_alert_event",
        ["watch_target_id", "status"],
    )

    op.create_table(
        "buy_decision_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("buy_opportunity.id"),
            nullable=False,
        ),
        sa.Column("feedback_type", sa.String(length=64), nullable=False),
        sa.Column("feedback_label", sa.String(length=64), nullable=False),
        sa.Column("operator_id", sa.String(length=64), nullable=True),
        sa.Column("feedback_note", sa.Text(), nullable=True),
        sa.Column("purchase_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("expected_resale_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_buy_feedback_opportunity_type",
        "buy_decision_feedback",
        ["opportunity_id", "feedback_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_buy_feedback_opportunity_type", table_name="buy_decision_feedback")
    op.drop_table("buy_decision_feedback")

    op.drop_index("idx_buy_alert_event_target_status", table_name="buy_alert_event")
    op.drop_table("buy_alert_event")

    op.drop_table("buy_opportunity_risk")

    op.drop_index("idx_buy_opportunity_category_status", table_name="buy_opportunity")
    op.drop_index("idx_buy_opportunity_status_score", table_name="buy_opportunity")
    op.drop_table("buy_opportunity")

    op.drop_index("idx_buy_price_baseline_scope_date", table_name="buy_price_baseline")
    op.drop_table("buy_price_baseline")

    op.drop_index("idx_buy_watch_target_category_status", table_name="buy_watch_target")
    op.drop_table("buy_watch_target")
