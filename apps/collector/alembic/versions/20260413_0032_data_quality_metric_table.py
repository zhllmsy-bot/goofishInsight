"""add data quality metric table

Revision ID: 20260413_0032
Revises: 20260413_0031
Create Date: 2026-04-13 15:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260413_0032"
down_revision = "20260413_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_quality_metric",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("metric_hour", sa.Integer(), nullable=False),
        sa.Column("metric_key", sa.Text(), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_key", sa.Text(), nullable=True),
        sa.Column("metric_value", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # Global metric index (no task_key, no category_id)
    op.create_index(
        "ux_dqm_global",
        "data_quality_metric",
        ["metric_date", "metric_hour", "metric_key"],
        unique=True,
        postgresql_where=sa.text("task_key is null and category_id is null"),
    )

    # Task-level metric index (has task_key, no category_id)
    op.create_index(
        "ux_dqm_task",
        "data_quality_metric",
        ["metric_date", "metric_hour", "metric_key", "task_key"],
        unique=True,
        postgresql_where=sa.text("task_key is not null and category_id is null"),
    )

    # Category-level metric index (no task_key, has category_id)
    op.create_index(
        "ux_dqm_category",
        "data_quality_metric",
        ["metric_date", "metric_hour", "metric_key", "category_id"],
        unique=True,
        postgresql_where=sa.text("task_key is null and category_id is not null"),
    )

    # Task + Category metric index (has both)
    op.create_index(
        "ux_dqm_task_category",
        "data_quality_metric",
        ["metric_date", "metric_hour", "metric_key", "task_key", "category_id"],
        unique=True,
        postgresql_where=sa.text("task_key is not null and category_id is not null"),
    )

    # Additional index for time-based queries
    op.create_index(
        "ix_dqm_created_at",
        "data_quality_metric",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_dqm_created_at", table_name="data_quality_metric")
    op.drop_index("ux_dqm_task_category", table_name="data_quality_metric")
    op.drop_index("ux_dqm_category", table_name="data_quality_metric")
    op.drop_index("ux_dqm_task", table_name="data_quality_metric")
    op.drop_index("ux_dqm_global", table_name="data_quality_metric")
    op.drop_table("data_quality_metric")
