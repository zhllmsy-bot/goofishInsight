"""add batch_collect_risk_event table

Revision ID: 20260412_0030
Revises: 20260411_0029
Create Date: 2026-04-12 16:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260412_0030"
down_revision = "20260411_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batch_collect_risk_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False, server_default="risk_control"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("config_path", sa.Text(), nullable=True),
        sa.Column("profile_key", sa.String(length=128), nullable=True),
        sa.Column("task_key", sa.String(length=128), nullable=True),
        sa.Column("task_query_id", sa.String(length=64), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("normalized_query", sa.Text(), nullable=True),
        sa.Column("auth_state", sa.String(length=32), nullable=True),
        sa.Column("consecutive_risk_hits", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("backoff_seconds", sa.Integer(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_batch_collect_risk_event_occurred_at",
        "batch_collect_risk_event",
        ["occurred_at"],
    )
    op.create_index(
        "ix_batch_collect_risk_event_scope_query_time",
        "batch_collect_risk_event",
        ["scope_key", "normalized_query", "occurred_at"],
    )
    op.create_index(
        "ix_batch_collect_risk_event_task_time",
        "batch_collect_risk_event",
        ["task_key", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_batch_collect_risk_event_task_time", table_name="batch_collect_risk_event")
    op.drop_index("ix_batch_collect_risk_event_scope_query_time", table_name="batch_collect_risk_event")
    op.drop_index("ix_batch_collect_risk_event_occurred_at", table_name="batch_collect_risk_event")
    op.drop_table("batch_collect_risk_event")
