"""add category-driven metrics and reporting fields

Revision ID: 20260407_0017
Revises: 20260407_0016
Create Date: 2026-04-07 00:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260407_0017"
down_revision = "20260407_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_metrics", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("daily_metrics", sa.Column("model_catalog_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_daily_metrics_category_id",
        "daily_metrics",
        "category",
        ["category_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_daily_metrics_model_catalog_id",
        "daily_metrics",
        "category_model_catalog",
        ["model_catalog_id"],
        ["id"],
    )
    op.drop_constraint("uq_daily_metric_domain_model", "daily_metrics", type_="unique")
    op.create_unique_constraint(
        "uq_daily_metric_category_model",
        "daily_metrics",
        ["metric_date", "category_id", "model_catalog_id"],
    )

    op.add_column("model_scores", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("model_scores", sa.Column("model_catalog_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_model_scores_category_id",
        "model_scores",
        "category",
        ["category_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_model_scores_model_catalog_id",
        "model_scores",
        "category_model_catalog",
        ["model_catalog_id"],
        ["id"],
    )
    op.drop_constraint("uq_model_score_domain_model_date", "model_scores", type_="unique")
    op.create_unique_constraint(
        "uq_model_score_category_model_date",
        "model_scores",
        ["category_id", "model_catalog_id", "score_date"],
    )

    op.add_column("analysis_reports", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("analysis_reports", sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_analysis_reports_category_id",
        "analysis_reports",
        "category",
        ["category_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_analysis_reports_template_id",
        "analysis_reports",
        "category_attr_template",
        ["template_id"],
        ["id"],
    )

    op.add_column("outreach_records", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("outreach_records", sa.Column("model_catalog_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_outreach_records_category_id",
        "outreach_records",
        "category",
        ["category_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_outreach_records_model_catalog_id",
        "outreach_records",
        "category_model_catalog",
        ["model_catalog_id"],
        ["id"],
    )

    op.execute(
        """
        UPDATE daily_metrics AS d
        SET category_id = c.id
        FROM category AS c
        WHERE c.code = CASE
          WHEN d.business_domain = 'apple_m_series' THEN 'apple_computer'
          WHEN d.business_domain = 'garmin' THEN 'garmin_watch'
          ELSE d.business_domain
        END
        """
    )
    op.execute(
        """
        UPDATE model_scores AS m
        SET category_id = c.id
        FROM category AS c
        WHERE c.code = CASE
          WHEN m.business_domain = 'apple_m_series' THEN 'apple_computer'
          WHEN m.business_domain = 'garmin' THEN 'garmin_watch'
          ELSE m.business_domain
        END
        """
    )
    op.execute(
        """
        UPDATE analysis_reports AS a
        SET category_id = c.id
        FROM category AS c
        WHERE c.code = CASE
          WHEN a.business_domain = 'apple_m_series' THEN 'apple_computer'
          WHEN a.business_domain = 'garmin' THEN 'garmin_watch'
          ELSE a.business_domain
        END
        """
    )
    op.execute(
        """
        UPDATE outreach_records AS o
        SET category_id = c.id
        FROM category AS c
        WHERE c.code = CASE
          WHEN o.business_domain = 'apple_m_series' THEN 'apple_computer'
          WHEN o.business_domain = 'garmin' THEN 'garmin_watch'
          ELSE o.business_domain
        END
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_outreach_records_model_catalog_id", "outreach_records", type_="foreignkey")
    op.drop_constraint("fk_outreach_records_category_id", "outreach_records", type_="foreignkey")
    op.drop_column("outreach_records", "model_catalog_id")
    op.drop_column("outreach_records", "category_id")

    op.drop_constraint("fk_analysis_reports_template_id", "analysis_reports", type_="foreignkey")
    op.drop_constraint("fk_analysis_reports_category_id", "analysis_reports", type_="foreignkey")
    op.drop_column("analysis_reports", "template_id")
    op.drop_column("analysis_reports", "category_id")

    op.drop_constraint("uq_model_score_category_model_date", "model_scores", type_="unique")
    op.create_unique_constraint(
        "uq_model_score_domain_model_date",
        "model_scores",
        ["business_domain", "normalized_model", "score_date"],
    )
    op.drop_constraint("fk_model_scores_model_catalog_id", "model_scores", type_="foreignkey")
    op.drop_constraint("fk_model_scores_category_id", "model_scores", type_="foreignkey")
    op.drop_column("model_scores", "model_catalog_id")
    op.drop_column("model_scores", "category_id")

    op.drop_constraint("uq_daily_metric_category_model", "daily_metrics", type_="unique")
    op.create_unique_constraint(
        "uq_daily_metric_domain_model",
        "daily_metrics",
        ["metric_date", "business_domain", "normalized_model"],
    )
    op.drop_constraint("fk_daily_metrics_model_catalog_id", "daily_metrics", type_="foreignkey")
    op.drop_constraint("fk_daily_metrics_category_id", "daily_metrics", type_="foreignkey")
    op.drop_column("daily_metrics", "model_catalog_id")
    op.drop_column("daily_metrics", "category_id")
