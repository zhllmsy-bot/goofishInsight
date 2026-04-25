"""add core attribute roles and spec schema snapshots

Revision ID: 20260425_0038
Revises: 20260421_0037
Create Date: 2026-04-25 15:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260425_0038"
down_revision = "20260421_0037"
branch_labels = None
depends_on = None


ROLE_VALUES = ("locking", "variant", "condition", "descriptive")


def upgrade() -> None:
    op.add_column(
        "category_attr_template_item",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="descriptive"),
    )
    op.add_column(
        "category_attr_template_item",
        sa.Column("weight", sa.Numeric(precision=4, scale=2), nullable=True, server_default="0"),
    )
    op.add_column(
        "category_attr_template_item",
        sa.Column("normalization", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "category_attr_template_item",
        sa.Column("enum_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        "ck_category_attr_template_item_role",
        "category_attr_template_item",
        "role IN ('locking', 'variant', 'condition', 'descriptive')",
    )
    op.create_check_constraint(
        "ck_category_attr_template_item_weight_range",
        "category_attr_template_item",
        "weight IS NULL OR (weight >= 0 AND weight <= 1)",
    )
    op.create_index(
        "idx_template_item_role",
        "category_attr_template_item",
        ["template_id", "role", "sort_no"],
    )

    _seed_known_category_roles()

    op.create_table(
        "sku_spec_schema_snapshots",
        sa.Column("schema_id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("category.id"), nullable=True),
        sa.Column("category_code", sa.Text(), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("category_attr_template.id"), nullable=True),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column(
            "locking_attrs",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "required_attrs",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "variant_attrs",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "condition_attrs",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "weights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("normalization", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("enum_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "category_code",
            "template_version",
            name="uq_sku_spec_schema_snapshot_category_version",
        ),
    )
    op.create_index(
        "ix_sku_spec_schema_snapshot_active",
        "sku_spec_schema_snapshots",
        ["category_code"],
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    _backfill_schema_snapshots()

    op.add_column("buy_price_baseline", sa.Column("schema_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_buy_price_baseline_schema_id",
        "buy_price_baseline",
        "sku_spec_schema_snapshots",
        ["schema_id"],
        ["schema_id"],
    )
    op.execute(
        """
        UPDATE buy_price_baseline AS baseline
        SET schema_id = snapshot.schema_id
        FROM category AS category
        JOIN sku_spec_schema_snapshots AS snapshot
          ON snapshot.category_code = category.code
         AND snapshot.valid_to IS NULL
        WHERE baseline.category_id = category.id
          AND baseline.schema_id IS NULL
        """
    )
    op.alter_column("buy_price_baseline", "schema_id", nullable=False)
    op.drop_constraint("uq_buy_price_baseline_key_date", "buy_price_baseline", type_="unique")
    op.create_unique_constraint(
        "uq_buy_price_baseline_key_date",
        "buy_price_baseline",
        ["category_id", "model_catalog_id", "schema_id", "baseline_key", "baseline_date"],
    )
    op.create_index(
        "idx_buy_price_baseline_schema_date",
        "buy_price_baseline",
        ["schema_id", "baseline_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_buy_price_baseline_schema_date", table_name="buy_price_baseline")
    op.drop_constraint("uq_buy_price_baseline_key_date", "buy_price_baseline", type_="unique")
    op.create_unique_constraint(
        "uq_buy_price_baseline_key_date",
        "buy_price_baseline",
        ["category_id", "model_catalog_id", "baseline_key", "baseline_date"],
    )
    op.drop_constraint("fk_buy_price_baseline_schema_id", "buy_price_baseline", type_="foreignkey")
    op.drop_column("buy_price_baseline", "schema_id")
    op.drop_index("ix_sku_spec_schema_snapshot_active", table_name="sku_spec_schema_snapshots")
    op.drop_table("sku_spec_schema_snapshots")
    op.drop_index("idx_template_item_role", table_name="category_attr_template_item")
    op.drop_constraint(
        "ck_category_attr_template_item_weight_range",
        "category_attr_template_item",
        type_="check",
    )
    op.drop_constraint(
        "ck_category_attr_template_item_role",
        "category_attr_template_item",
        type_="check",
    )
    op.drop_column("category_attr_template_item", "enum_values")
    op.drop_column("category_attr_template_item", "normalization")
    op.drop_column("category_attr_template_item", "weight")
    op.drop_column("category_attr_template_item", "role")


def _seed_known_category_roles() -> None:
    role_updates = [
        (
            "apple_computer",
            "locking",
            {
                "model_name": "0.25",
                "chip_family": "0.25",
                "cpu_cores": "0.10",
                "gpu_cores": "0.15",
                "memory_gb": "0.15",
                "storage_gb": "0.15",
                "screen_size_in": "0.05",
            },
        ),
        (
            "garmin_watch",
            "locking",
            {
                "model_name": "0.35",
                "case_size_mm": "0.25",
                "display_type": "0.20",
                "is_solar": "0.20",
            },
        ),
        (
            "camera_body",
            "locking",
            {
                "brand_name": "0.20",
                "model_name": "0.30",
                "mount_system": "0.20",
                "sensor_format": "0.20",
                "generation": "0.10",
            },
        ),
        (
            "camera_interchangeable_lens",
            "locking",
            {
                "brand_name": "0.20",
                "model_name": "0.25",
                "mount_system": "0.20",
                "focal_length_range": "0.20",
                "max_aperture": "0.15",
            },
        ),
    ]
    for category_code, role, weights in role_updates:
        for attr_code, weight in weights.items():
            op.execute(
                sa.text(
                    """
                    UPDATE category_attr_template_item AS item
                    SET role = :role,
                        weight = :weight,
                        is_required = true
                    FROM category_attr_template AS template,
                         category AS category,
                         attribute_definition AS attr
                    WHERE item.template_id = template.id
                      AND category.id = template.category_id
                      AND attr.id = item.attribute_id
                      AND category.code = :category_code
                      AND attr.code = :attr_code
                    """
                ).bindparams(
                    role=role,
                    weight=weight,
                    category_code=category_code,
                    attr_code=attr_code,
                )
            )

    variant_codes = ("color", "region_variant", "region", "carrier_region")
    condition_codes = (
        "condition",
        "condition_grade",
        "battery_health",
        "bundle_accessories",
        "warranty_status",
        "box_and_receipt",
        "screen_state",
        "strap_originality",
        "shutter_count",
        "repair_history",
        "glass_state",
        "focus_ring_state",
        "zoom_ring_state",
        "hood_and_caps",
    )
    _seed_role_by_attr_codes("variant", variant_codes)
    _seed_role_by_attr_codes("condition", condition_codes)


def _seed_role_by_attr_codes(role: str, attr_codes: tuple[str, ...]) -> None:
    quoted_codes = ", ".join(f"'{code}'" for code in attr_codes)
    op.execute(
        sa.text(
            f"""
            UPDATE category_attr_template_item AS item
            SET role = :role,
                weight = 0
            FROM attribute_definition AS attr
            WHERE attr.id = item.attribute_id
              AND attr.code IN ({quoted_codes})
            """
        ).bindparams(
            role=role,
        )
    )


def _backfill_schema_snapshots() -> None:
    op.execute(
        """
        WITH ranked_template AS (
          SELECT
            template.id,
            template.category_id,
            category.code AS category_code,
            template.version,
            template.effective_at,
            template.published_by,
            ROW_NUMBER() OVER (
              PARTITION BY template.category_id
              ORDER BY
                CASE WHEN runtime.active_template_id = template.id THEN 0 ELSE 1 END,
                CASE WHEN template.status = 'PUBLISHED' THEN 0 ELSE 1 END,
                template.version DESC,
                template.updated_at DESC
            ) AS row_num
          FROM category_attr_template AS template
          JOIN category AS category
            ON category.id = template.category_id
          LEFT JOIN category_runtime_profile AS runtime
            ON runtime.category_id = category.id
           AND runtime.status = 'ACTIVE'
        ),
        latest_template AS (
          SELECT *
          FROM ranked_template
          WHERE row_num = 1
        )
        INSERT INTO sku_spec_schema_snapshots (
          category_id,
          category_code,
          template_id,
          template_version,
          locking_attrs,
          required_attrs,
          variant_attrs,
          condition_attrs,
          weights,
          normalization,
          enum_values,
          valid_from,
          created_by
        )
        SELECT
          category.id,
          category.code,
          latest.id,
          COALESCE(latest.version, 1),
          COALESCE((
            SELECT array_agg(attr.code ORDER BY item.sort_no, attr.code)
            FROM category_attr_template_item AS item
            JOIN attribute_definition AS attr
              ON attr.id = item.attribute_id
            WHERE item.template_id = latest.id
              AND item.role = 'locking'
          ), ARRAY[]::text[]),
          COALESCE((
            SELECT array_agg(attr.code ORDER BY item.sort_no, attr.code)
            FROM category_attr_template_item AS item
            JOIN attribute_definition AS attr
              ON attr.id = item.attribute_id
            WHERE item.template_id = latest.id
              AND item.role = 'locking'
              AND item.is_required IS TRUE
          ), ARRAY[]::text[]),
          COALESCE((
            SELECT array_agg(attr.code ORDER BY item.sort_no, attr.code)
            FROM category_attr_template_item AS item
            JOIN attribute_definition AS attr
              ON attr.id = item.attribute_id
            WHERE item.template_id = latest.id
              AND item.role = 'variant'
          ), ARRAY[]::text[]),
          COALESCE((
            SELECT array_agg(attr.code ORDER BY item.sort_no, attr.code)
            FROM category_attr_template_item AS item
            JOIN attribute_definition AS attr
              ON attr.id = item.attribute_id
            WHERE item.template_id = latest.id
              AND item.role = 'condition'
          ), ARRAY[]::text[]),
          COALESCE((
            SELECT jsonb_object_agg(attr.code, to_jsonb(item.weight))
            FROM category_attr_template_item AS item
            JOIN attribute_definition AS attr
              ON attr.id = item.attribute_id
            WHERE item.template_id = latest.id
              AND item.role = 'locking'
              AND item.weight IS NOT NULL
              AND item.weight > 0
          ), '{}'::jsonb),
          (
            SELECT jsonb_object_agg(attr.code, item.normalization)
            FROM category_attr_template_item AS item
            JOIN attribute_definition AS attr
              ON attr.id = item.attribute_id
            WHERE item.template_id = latest.id
              AND item.normalization IS NOT NULL
          ),
          (
            SELECT jsonb_object_agg(attr.code, item.enum_values)
            FROM category_attr_template_item AS item
            JOIN attribute_definition AS attr
              ON attr.id = item.attribute_id
            WHERE item.template_id = latest.id
              AND item.enum_values IS NOT NULL
          ),
          COALESCE(latest.effective_at, now()),
          COALESCE(latest.published_by, 'migration:20260425_0038')
        FROM category AS category
        LEFT JOIN latest_template AS latest
          ON latest.category_id = category.id
        ON CONFLICT (category_code, template_version) DO NOTHING
        """
    )
