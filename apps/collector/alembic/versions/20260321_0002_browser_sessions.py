"""browser sessions

Revision ID: 20260321_0002
Revises: 20260321_0001
Create Date: 2026-03-21 16:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260321_0002"
down_revision = "20260321_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "browser_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("profile_key", sa.String(length=128), nullable=False),
        sa.Column("profile_dir", sa.Text(), nullable=False),
        sa.Column("browser_channel", sa.String(length=64), nullable=False, server_default="msedge"),
        sa.Column("auth_state", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("last_login_required_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("profile_key", name="uq_browser_sessions_profile_key"),
    )


def downgrade() -> None:
    op.drop_table("browser_sessions")
