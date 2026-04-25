"""add catalog attribute schema

Revision ID: 20260405_0008
Revises: 20260329_0007
Create Date: 2026-04-05 05:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260405_0008"
down_revision = "20260329_0007"
branch_labels = None
depends_on = None


attribute_data_type = postgresql.ENUM(
    "TEXT",
    "NUMBER",
    "BOOLEAN",
    "ENUM",
    "JSON",
    name="attribute_data_type",
    create_type=False,
)
attribute_scope_type = postgresql.ENUM(
    "PLATFORM",
    "MERCHANT",
    "CHANNEL",
    name="attribute_scope_type",
    create_type=False,
)
attribute_status = postgresql.ENUM(
    "DRAFT",
    "ACTIVE",
    "DEPRECATED",
    "DISABLED",
    name="attribute_status",
    create_type=False,
)
template_status = postgresql.ENUM(
    "DRAFT",
    "PUBLISHED",
    "RETIRED",
    name="template_status",
    create_type=False,
)
product_status = postgresql.ENUM(
    "DRAFT",
    "ACTIVE",
    "INACTIVE",
    "ARCHIVED",
    name="product_status",
    create_type=False,
)
outbox_status = postgresql.ENUM(
    "PENDING",
    "PROCESSING",
    "DONE",
    "FAILED",
    "DEAD",
    name="outbox_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        attribute_data_type,
        attribute_scope_type,
        attribute_status,
        template_status,
        product_status,
        outbox_status,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "category",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("category.id"), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("code", name="uq_category_code"),
    )
    op.create_index("idx_category_parent_id", "category", ["parent_id"])

    op.create_table(
        "attribute_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "scope_type",
            attribute_scope_type,
            nullable=False,
            server_default="PLATFORM",
        ),
        sa.Column("scope_id", sa.String(length=64), nullable=False, server_default="platform"),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("data_type", attribute_data_type, nullable=False),
        sa.Column("value_scope", sa.String(length=16), nullable=False),
        sa.Column("is_multi", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("validation_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", attribute_status, nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("value_scope IN ('SPU', 'SKU')", name="ck_attribute_definition_value_scope"),
        sa.UniqueConstraint(
            "scope_type",
            "scope_id",
            "code",
            name="uq_attribute_definition_scope_code",
        ),
    )

    op.create_table(
        "attribute_option",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "attribute_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attribute_definition.id"),
            nullable=False,
        ),
        sa.Column("option_code", sa.String(length=64), nullable=False),
        sa.Column("option_name", sa.String(length=128), nullable=False),
        sa.Column("sort_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", attribute_status, nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("attribute_id", "option_code", name="uq_attribute_option_code"),
    )

    op.create_table(
        "category_attr_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", template_status, nullable=False, server_default="DRAFT"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("category_id", "version", name="uq_category_attr_template_version"),
    )
    op.create_index(
        "idx_template_category_status",
        "category_attr_template",
        ["category_id", "status"],
    )

    op.create_table(
        "category_attr_template_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category_attr_template.id"),
            nullable=False,
        ),
        sa.Column(
            "attribute_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attribute_definition.id"),
            nullable=False,
        ),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_sale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_filter", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_search", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_display", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("template_id", "attribute_id", name="uq_category_attr_template_item"),
    )
    op.create_index(
        "idx_template_item_template_sort",
        "category_attr_template_item",
        ["template_id", "sort_no", "attribute_id"],
    )

    op.create_table(
        "product_spu",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category.id"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category_attr_template.id"),
            nullable=False,
        ),
        sa.Column("merchant_id", sa.String(length=64), nullable=True),
        sa.Column("brand_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("status", product_status, nullable=False, server_default="DRAFT"),
        sa.Column(
            "attr_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_spu_category_status", "product_spu", ["category_id", "status"])

    op.create_table(
        "product_sku",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "spu_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_spu.id"),
            nullable=False,
        ),
        sa.Column("sku_code", sa.String(length=64), nullable=False),
        sa.Column("sales_signature_raw", sa.Text(), nullable=False),
        sa.Column("sales_signature_hash", sa.String(length=128), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("status", product_status, nullable=False, server_default="DRAFT"),
        sa.Column(
            "attr_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("sku_code", name="uq_product_sku_code"),
        sa.UniqueConstraint("spu_id", "sales_signature_hash", name="uq_product_sku_signature"),
    )
    op.create_index("idx_sku_spu_status", "product_sku", ["spu_id", "status"])

    value_check = (
        "((text_value IS NOT NULL)::int + "
        "(number_value IS NOT NULL)::int + "
        "(bool_value IS NOT NULL)::int + "
        "(option_id IS NOT NULL)::int + "
        "(json_value IS NOT NULL)::int) = 1"
    )

    op.create_table(
        "product_spu_attr_value",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "spu_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_spu.id"),
            nullable=False,
        ),
        sa.Column(
            "attribute_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attribute_definition.id"),
            nullable=False,
        ),
        sa.Column("value_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("number_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("normalized_number_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("bool_value", sa.Boolean(), nullable=True),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("attribute_option.id"), nullable=True),
        sa.Column("json_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(value_check, name="ck_product_spu_attr_value_single_value"),
        sa.UniqueConstraint("spu_id", "attribute_id", "value_seq", name="uq_product_spu_attr_value"),
    )
    op.create_index("idx_spu_attr_entity_attr", "product_spu_attr_value", ["spu_id", "attribute_id"])
    op.create_index("idx_spu_attr_option", "product_spu_attr_value", ["attribute_id", "option_id"])
    op.create_index(
        "idx_spu_attr_number",
        "product_spu_attr_value",
        ["attribute_id", "normalized_number_value"],
    )

    op.create_table(
        "product_sku_attr_value",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "sku_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_sku.id"),
            nullable=False,
        ),
        sa.Column(
            "attribute_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attribute_definition.id"),
            nullable=False,
        ),
        sa.Column("value_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("number_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("normalized_number_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("bool_value", sa.Boolean(), nullable=True),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("attribute_option.id"), nullable=True),
        sa.Column("json_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(value_check, name="ck_product_sku_attr_value_single_value"),
        sa.UniqueConstraint("sku_id", "attribute_id", "value_seq", name="uq_product_sku_attr_value"),
    )
    op.create_index("idx_sku_attr_entity_attr", "product_sku_attr_value", ["sku_id", "attribute_id"])
    op.create_index("idx_sku_attr_option", "product_sku_attr_value", ["attribute_id", "option_id"])
    op.create_index(
        "idx_sku_attr_number",
        "product_sku_attr_value",
        ["attribute_id", "normalized_number_value"],
    )

    op.create_table(
        "outbox_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", outbox_status, nullable=False, server_default="PENDING"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_outbox_status_retry",
        "outbox_event",
        ["status", "next_retry_at", "created_at"],
    )

    op.create_table(
        "product_attr_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("operator_id", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_audit_resource",
        "product_attr_audit_log",
        ["resource_type", "resource_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_audit_resource", table_name="product_attr_audit_log")
    op.drop_table("product_attr_audit_log")

    op.drop_index("idx_outbox_status_retry", table_name="outbox_event")
    op.drop_table("outbox_event")

    op.drop_index("idx_sku_attr_number", table_name="product_sku_attr_value")
    op.drop_index("idx_sku_attr_option", table_name="product_sku_attr_value")
    op.drop_index("idx_sku_attr_entity_attr", table_name="product_sku_attr_value")
    op.drop_table("product_sku_attr_value")

    op.drop_index("idx_spu_attr_number", table_name="product_spu_attr_value")
    op.drop_index("idx_spu_attr_option", table_name="product_spu_attr_value")
    op.drop_index("idx_spu_attr_entity_attr", table_name="product_spu_attr_value")
    op.drop_table("product_spu_attr_value")

    op.drop_index("idx_sku_spu_status", table_name="product_sku")
    op.drop_table("product_sku")

    op.drop_index("idx_spu_category_status", table_name="product_spu")
    op.drop_table("product_spu")

    op.drop_index("idx_template_item_template_sort", table_name="category_attr_template_item")
    op.drop_table("category_attr_template_item")

    op.drop_index("idx_template_category_status", table_name="category_attr_template")
    op.drop_table("category_attr_template")

    op.drop_table("attribute_option")
    op.drop_table("attribute_definition")

    op.drop_index("idx_category_parent_id", table_name="category")
    op.drop_table("category")

    bind = op.get_bind()
    for enum_type in (
        outbox_status,
        product_status,
        template_status,
        attribute_status,
        attribute_scope_type,
        attribute_data_type,
    ):
        enum_type.drop(bind, checkfirst=True)
