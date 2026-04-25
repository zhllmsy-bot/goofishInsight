"""add collector job runtime tables

Revision ID: 20260413_0031
Revises: 20260412_0030
Create Date: 2026-04-13 14:20:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260413_0031"
down_revision = "20260412_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collector_job_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="probe"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collector_job_run_job_status",
        "collector_job_run",
        ["job_name", "status", "started_at"],
    )

    op.create_table(
        "collector_job_checkpoint",
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("checkpoint_mode", sa.String(length=16), nullable=False, server_default="eager"),
        sa.Column("cursor_pending", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cursor_committed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("scope_key"),
    )

    op.add_column("crawl_runs", sa.Column("job_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_crawl_runs_job_run",
        "crawl_runs",
        "collector_job_run",
        ["job_run_id"],
        ["id"],
    )
    op.create_index("ix_crawl_runs_job_run_id", "crawl_runs", ["job_run_id"])


def downgrade() -> None:
    op.drop_index("ix_crawl_runs_job_run_id", table_name="crawl_runs")
    op.drop_constraint("fk_crawl_runs_job_run", "crawl_runs", type_="foreignkey")
    op.drop_column("crawl_runs", "job_run_id")

    op.drop_table("collector_job_checkpoint")

    op.drop_index("ix_collector_job_run_job_status", table_name="collector_job_run")
    op.drop_table("collector_job_run")
