"""add task query links to raw capture chain

Revision ID: 20260407_0018
Revises: 20260407_0017
Create Date: 2026-04-07 01:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0018"
down_revision = "20260407_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_requests", sa.Column("task_query_id", sa.BigInteger(), nullable=True))
    op.add_column("raw_responses", sa.Column("task_query_id", sa.BigInteger(), nullable=True))
    op.add_column("item_snapshots", sa.Column("task_query_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_raw_requests_task_query_id", "raw_requests", "crawl_task_query", ["task_query_id"], ["id"])
    op.create_foreign_key("fk_raw_responses_task_query_id", "raw_responses", "crawl_task_query", ["task_query_id"], ["id"])
    op.create_foreign_key("fk_item_snapshots_task_query_id", "item_snapshots", "crawl_task_query", ["task_query_id"], ["id"])

    op.execute(
        """
        UPDATE item_snapshots AS s
        SET task_query_id = i.task_query_id
        FROM items AS i
        WHERE s.item_id_ref = i.id
          AND s.task_query_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_item_snapshots_task_query_id", "item_snapshots", type_="foreignkey")
    op.drop_constraint("fk_raw_responses_task_query_id", "raw_responses", type_="foreignkey")
    op.drop_constraint("fk_raw_requests_task_query_id", "raw_requests", type_="foreignkey")
    op.drop_column("item_snapshots", "task_query_id")
    op.drop_column("raw_responses", "task_query_id")
    op.drop_column("raw_requests", "task_query_id")
