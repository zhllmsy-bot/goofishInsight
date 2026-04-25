"""add category task foundation tables

Revision ID: 20260406_0012
Revises: 20260406_0011
Create Date: 2026-04-06 21:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260406_0012"
down_revision = "20260406_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crawl_tasks", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "crawl_tasks",
        sa.Column("task_type", sa.String(length=32), nullable=False, server_default="PRODUCTION"),
    )
    op.add_column(
        "crawl_tasks",
        sa.Column("profile_key", sa.String(length=64), nullable=False, server_default="default"),
    )
    op.add_column(
        "crawl_tasks",
        sa.Column("parallel_tabs", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "crawl_tasks",
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_foreign_key(
        "fk_crawl_tasks_category_id",
        "crawl_tasks",
        "category",
        ["category_id"],
        ["id"],
    )
    op.create_index(
        "idx_crawl_tasks_category_status",
        "crawl_tasks",
        ["category_id", "task_type", "status"],
    )

    op.create_table(
        "category_model_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("category.id"), nullable=False),
        sa.Column("brand_name", sa.String(length=128), nullable=True),
        sa.Column("series_name", sa.String(length=128), nullable=True),
        sa.Column("model_code", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("category_id", "model_code", name="uq_category_model_catalog_code"),
    )
    op.create_index(
        "idx_category_model_catalog_lookup",
        "category_model_catalog",
        ["category_id", "brand_name", "status"],
    )

    op.create_table(
        "category_model_alias",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "model_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category_model_catalog.id"),
            nullable=False,
        ),
        sa.Column("alias_text", sa.String(length=255), nullable=False),
        sa.Column("alias_normalized", sa.String(length=255), nullable=False),
        sa.Column("alias_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("model_id", "alias_normalized", name="uq_category_model_alias_normalized"),
    )
    op.create_index(
        "idx_category_model_alias_lookup",
        "category_model_alias",
        ["alias_normalized", "status"],
    )

    op.create_table(
        "crawl_task_query",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("crawl_tasks.id"), nullable=False),
        sa.Column("query_text", sa.String(length=255), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_id", "query_text", name="uq_crawl_task_query_text"),
    )
    op.create_index(
        "idx_crawl_task_query_schedule",
        "crawl_task_query",
        ["task_id", "status", "priority"],
    )

    op.create_table(
        "crawl_task_lexicon",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("crawl_tasks.id"), nullable=False),
        sa.Column("lexicon_type", sa.String(length=32), nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_id", "lexicon_type", "term", name="uq_crawl_task_lexicon_term"),
    )
    op.create_index(
        "idx_crawl_task_lexicon_lookup",
        "crawl_task_lexicon",
        ["task_id", "lexicon_type", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_crawl_task_lexicon_lookup", table_name="crawl_task_lexicon")
    op.drop_table("crawl_task_lexicon")

    op.drop_index("idx_crawl_task_query_schedule", table_name="crawl_task_query")
    op.drop_table("crawl_task_query")

    op.drop_index("idx_category_model_alias_lookup", table_name="category_model_alias")
    op.drop_table("category_model_alias")

    op.drop_index("idx_category_model_catalog_lookup", table_name="category_model_catalog")
    op.drop_table("category_model_catalog")

    op.drop_index("idx_crawl_tasks_category_status", table_name="crawl_tasks")
    op.drop_constraint("fk_crawl_tasks_category_id", "crawl_tasks", type_="foreignkey")
    op.drop_column("crawl_tasks", "metadata_json")
    op.drop_column("crawl_tasks", "parallel_tabs")
    op.drop_column("crawl_tasks", "profile_key")
    op.drop_column("crawl_tasks", "task_type")
    op.drop_column("crawl_tasks", "category_id")
