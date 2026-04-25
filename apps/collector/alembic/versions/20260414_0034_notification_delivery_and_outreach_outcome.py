"""add notification delivery and outreach outcome fields

Revision ID: 20260414_0034
Revises: 20260414_0033
Create Date: 2026-04-14 11:45:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260414_0034"
down_revision = "20260414_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_delivery",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=64), nullable=False, server_default="dashboard"),
        sa.Column("destination", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["alert_event_id"], ["buy_alert_event.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_delivery_pending_retry",
        "notification_delivery",
        ["next_retry_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_notification_delivery_alert_event", "notification_delivery", ["alert_event_id"])

    op.add_column("outreach_records", sa.Column("outcome_status", sa.String(length=32), nullable=True))
    op.add_column("outreach_records", sa.Column("deal_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("outreach_records", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outreach_records", sa.Column("operator_note", sa.Text(), nullable=True))
    op.create_index("ix_outreach_records_outcome_status", "outreach_records", ["outcome_status", "closed_at"])


def downgrade() -> None:
    op.drop_index("ix_outreach_records_outcome_status", table_name="outreach_records")
    op.drop_column("outreach_records", "operator_note")
    op.drop_column("outreach_records", "closed_at")
    op.drop_column("outreach_records", "deal_price")
    op.drop_column("outreach_records", "outcome_status")

    op.drop_index("ix_notification_delivery_alert_event", table_name="notification_delivery")
    op.drop_index("ix_notification_delivery_pending_retry", table_name="notification_delivery")
    op.drop_table("notification_delivery")
