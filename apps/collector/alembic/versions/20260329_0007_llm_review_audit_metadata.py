"""add llm review audit metadata columns

Revision ID: 20260329_0007
Revises: 20260322_0006
Create Date: 2026-03-29 10:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260329_0007"
down_revision = "20260322_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("llm_review_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column(
            "llm_review_input",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "items",
        sa.Column("llm_review_input_signature", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column(
            "llm_review_needs_audit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "items",
        sa.Column("llm_review_audit_reason", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column(
            "llm_review_decision",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("items", "llm_review_decision")
    op.drop_column("items", "llm_review_audit_reason")
    op.drop_column("items", "llm_review_needs_audit")
    op.drop_column("items", "llm_review_input_signature")
    op.drop_column("items", "llm_review_input")
    op.drop_column("items", "llm_review_confidence")
