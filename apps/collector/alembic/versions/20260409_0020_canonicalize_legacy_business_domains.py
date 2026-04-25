"""canonicalize legacy business domains

Revision ID: 20260409_0020
Revises: 20260408_0019
Create Date: 2026-04-09 00:35:00
"""

from __future__ import annotations

from alembic import op


revision = "20260409_0020"
down_revision = "20260408_0019"
branch_labels = None
depends_on = None


LEGACY_DOMAIN_MAPPING_SQL = """
with mapping(old_domain, new_domain) as (
  values
    ('apple_m_series', 'apple_computer'),
    ('garmin', 'garmin_watch')
)
"""


def upgrade() -> None:
    for table_name in (
        "items",
        "item_spec_enrichments",
        "daily_metrics",
        "analysis_reports",
        "outreach_records",
        "model_scores",
    ):
        op.execute(
            f"""
            {LEGACY_DOMAIN_MAPPING_SQL}
            update {table_name} t
            set business_domain = mapping.new_domain
            from mapping
            where t.business_domain = mapping.old_domain
            """
        )

    op.execute(
        f"""
        {LEGACY_DOMAIN_MAPPING_SQL}
        update items t
        set llm_review_input = jsonb_set(
          t.llm_review_input,
          '{{business_domain}}',
          to_jsonb(mapping.new_domain),
          false
        )
        from mapping
        where t.llm_review_input ->> 'business_domain' = mapping.old_domain
        """
    )

    op.execute(
        f"""
        {LEGACY_DOMAIN_MAPPING_SQL}
        update buy_price_baseline t
        set payload = jsonb_set(
          t.payload,
          '{{pricing_row,business_domain}}',
          to_jsonb(mapping.new_domain),
          false
        )
        from mapping
        where t.payload #>> '{{pricing_row,business_domain}}' = mapping.old_domain
        """
    )

    op.execute(
        f"""
        {LEGACY_DOMAIN_MAPPING_SQL}
        update buy_opportunity t
        set payload = jsonb_set(
          t.payload,
          '{{pricing_record,business_domain}}',
          to_jsonb(mapping.new_domain),
          false
        )
        from mapping
        where t.payload #>> '{{pricing_record,business_domain}}' = mapping.old_domain
        """
    )


def downgrade() -> None:
    # Data canonicalization is intentionally not reversed; rolling it back would
    # conflate newly collected canonical rows with old legacy rows.
    pass
