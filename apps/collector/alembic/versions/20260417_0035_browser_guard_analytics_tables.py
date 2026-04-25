"""add browser guard analytics tables

Revision ID: 20260417_0035
Revises: 20260414_0034
Create Date: 2026-04-17 11:20:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260417_0035"
down_revision = "20260414_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "browser_job_attempt",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("profile_key", sa.String(length=128), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False, server_default="execute"),
        sa.Column("scope_key", sa.Text(), nullable=True),
        sa.Column("task_key", sa.String(length=128), nullable=True),
        sa.Column("task_query_id", sa.String(length=64), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("normalized_query", sa.Text(), nullable=True),
        sa.Column("business_domain", sa.String(length=64), nullable=True),
        sa.Column("attempt_outcome", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("auth_state", sa.String(length=32), nullable=True),
        sa.Column("is_probe", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_test_task", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("guard_blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("browser_ready", sa.Boolean(), nullable=True),
        sa.Column("job_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_signature", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_run_id"], ["collector_job_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_browser_job_attempt_profile_time",
        "browser_job_attempt",
        ["profile_key", "occurred_at"],
    )
    op.create_index(
        "ix_browser_job_attempt_feature_stage_time",
        "browser_job_attempt",
        ["feature", "stage", "occurred_at"],
    )
    op.create_index(
        "ix_browser_job_attempt_task_time",
        "browser_job_attempt",
        ["task_key", "occurred_at"],
    )
    op.create_index(
        "ix_browser_job_attempt_outcome_time",
        "browser_job_attempt",
        ["attempt_outcome", "occurred_at"],
    )

    op.create_table(
        "browser_guard_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("profile_key", sa.String(length=128), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("auth_state", sa.String(length=32), nullable=True),
        sa.Column("consecutive_hits", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("backoff_seconds", sa.Integer(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("keep_page_open", sa.Boolean(), nullable=True),
        sa.Column("error_signature", sa.String(length=64), nullable=True),
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
        "ix_browser_guard_event_profile_time",
        "browser_guard_event",
        ["profile_key", "occurred_at"],
    )
    op.create_index(
        "ix_browser_guard_event_feature_event_time",
        "browser_guard_event",
        ["feature", "event_type", "occurred_at"],
    )
    op.create_index(
        "ix_browser_guard_event_scope_time",
        "browser_guard_event",
        ["scope_key", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_browser_guard_event_scope_time", table_name="browser_guard_event")
    op.drop_index("ix_browser_guard_event_feature_event_time", table_name="browser_guard_event")
    op.drop_index("ix_browser_guard_event_profile_time", table_name="browser_guard_event")
    op.drop_table("browser_guard_event")

    op.drop_index("ix_browser_job_attempt_outcome_time", table_name="browser_job_attempt")
    op.drop_index("ix_browser_job_attempt_task_time", table_name="browser_job_attempt")
    op.drop_index("ix_browser_job_attempt_feature_stage_time", table_name="browser_job_attempt")
    op.drop_index("ix_browser_job_attempt_profile_time", table_name="browser_job_attempt")
    op.drop_table("browser_job_attempt")
