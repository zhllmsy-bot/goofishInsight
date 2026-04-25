"""add item category resolution fields

Revision ID: 20260407_0016
Revises: 20260406_0015
Create Date: 2026-04-07 00:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260407_0016"
down_revision = "20260406_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("task_query_id", sa.BigInteger(), nullable=True))
    op.add_column("items", sa.Column("target_category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("items", sa.Column("resolved_category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("items", sa.Column("resolved_template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "items",
        sa.Column("category_validation_status", sa.String(length=32), nullable=False, server_default="PENDING"),
    )
    op.add_column("items", sa.Column("category_validation_reason", sa.String(length=128), nullable=True))
    op.add_column("items", sa.Column("category_validation_confidence", sa.Numeric(5, 4), nullable=True))
    op.create_foreign_key("fk_items_task_query_id", "items", "crawl_task_query", ["task_query_id"], ["id"])
    op.create_foreign_key("fk_items_target_category_id", "items", "category", ["target_category_id"], ["id"])
    op.create_foreign_key("fk_items_resolved_category_id", "items", "category", ["resolved_category_id"], ["id"])
    op.create_foreign_key(
        "fk_items_resolved_template_id",
        "items",
        "category_attr_template",
        ["resolved_template_id"],
        ["id"],
    )
    op.create_index(
        "idx_items_category_resolution",
        "items",
        ["target_category_id", "resolved_category_id", "resolved_template_id", "category_validation_status"],
    )

    op.add_column("item_spec_enrichments", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("item_spec_enrichments", sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "item_spec_enrichments",
        sa.Column("model_catalog_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_item_spec_enrichments_category_id",
        "item_spec_enrichments",
        "category",
        ["category_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_item_spec_enrichments_template_id",
        "item_spec_enrichments",
        "category_attr_template",
        ["template_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_item_spec_enrichments_model_catalog_id",
        "item_spec_enrichments",
        "category_model_catalog",
        ["model_catalog_id"],
        ["id"],
    )

    op.execute(
        """
        UPDATE items AS i
        SET
          target_category_id = t.category_id,
          resolved_category_id = t.category_id,
          resolved_template_id = rp.active_template_id,
          category_validation_status = CASE
            WHEN t.category_id IS NOT NULL THEN 'MATCH_TASK_CATEGORY'
            ELSE 'PENDING'
          END,
          category_validation_reason = CASE
            WHEN t.category_id IS NOT NULL THEN 'backfilled_from_task_category'
            ELSE NULL
          END,
          category_validation_confidence = CASE
            WHEN t.category_id IS NOT NULL THEN 1.0
            ELSE NULL
          END
        FROM crawl_tasks AS t
        LEFT JOIN category_runtime_profile AS rp
          ON rp.category_id = t.category_id
         AND rp.status = 'ACTIVE'
        WHERE i.task_id = t.id
        """
    )

    op.execute(
        """
        UPDATE item_spec_enrichments AS s
        SET
          category_id = i.resolved_category_id,
          template_id = i.resolved_template_id
        FROM items AS i
        WHERE s.item_id_ref = i.id
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_item_spec_enrichments_model_catalog_id", "item_spec_enrichments", type_="foreignkey")
    op.drop_constraint("fk_item_spec_enrichments_template_id", "item_spec_enrichments", type_="foreignkey")
    op.drop_constraint("fk_item_spec_enrichments_category_id", "item_spec_enrichments", type_="foreignkey")
    op.drop_column("item_spec_enrichments", "model_catalog_id")
    op.drop_column("item_spec_enrichments", "template_id")
    op.drop_column("item_spec_enrichments", "category_id")

    op.drop_index("idx_items_category_resolution", table_name="items")
    op.drop_constraint("fk_items_resolved_template_id", "items", type_="foreignkey")
    op.drop_constraint("fk_items_resolved_category_id", "items", type_="foreignkey")
    op.drop_constraint("fk_items_target_category_id", "items", type_="foreignkey")
    op.drop_constraint("fk_items_task_query_id", "items", type_="foreignkey")
    op.drop_column("items", "category_validation_confidence")
    op.drop_column("items", "category_validation_reason")
    op.drop_column("items", "category_validation_status")
    op.drop_column("items", "resolved_template_id")
    op.drop_column("items", "resolved_category_id")
    op.drop_column("items", "target_category_id")
    op.drop_column("items", "task_query_id")
