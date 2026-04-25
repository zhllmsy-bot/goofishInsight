"""seed category runtime profiles and task category bindings

Revision ID: 20260406_0014
Revises: 20260406_0013
Create Date: 2026-04-06 22:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260406_0014"
down_revision = "20260406_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO category_runtime_profile (
                id, category_id, active_template_id, prompt_profile, extractor_profile, validator_profile,
                status, metadata_json, created_at, updated_at
            )
            SELECT
                :profile_id, :category_id, :template_id, :prompt_profile, :extractor_profile, :validator_profile,
                'ACTIVE', '{"source":"seed"}'::jsonb, now(), now()
            FROM category c
            JOIN category_attr_template t ON t.id = CAST(:template_id AS uuid)
            WHERE c.id = CAST(:category_id AS uuid)
              AND NOT EXISTS (
                SELECT 1 FROM category_runtime_profile WHERE category_id = CAST(:category_id AS uuid)
            )
            """
        ),
        {
            "profile_id": "11111111-1111-1111-1111-111111111501",
            "category_id": "11111111-1111-1111-1111-111111111101",
            "template_id": "11111111-1111-1111-1111-111111111403",
            "prompt_profile": "smartphone_extract_v1",
            "extractor_profile": "default",
            "validator_profile": "smartphone_basic_v1",
        },
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO category_runtime_profile (
                id, category_id, active_template_id, prompt_profile, extractor_profile, validator_profile,
                status, metadata_json, created_at, updated_at
            )
            SELECT
                :profile_id, :category_id, :template_id, :prompt_profile, :extractor_profile, :validator_profile,
                'ACTIVE', '{"source":"seed"}'::jsonb, now(), now()
            FROM category c
            JOIN category_attr_template t ON t.id = CAST(:template_id AS uuid)
            WHERE c.id = CAST(:category_id AS uuid)
              AND NOT EXISTS (
                SELECT 1 FROM category_runtime_profile WHERE category_id = CAST(:category_id AS uuid)
            )
            """
        ),
        {
            "profile_id": "22222222-2222-2222-2222-222222222501",
            "category_id": "22222222-2222-2222-2222-222222222101",
            "template_id": "22222222-2222-2222-2222-222222222401",
            "prompt_profile": "garmin_watch_extract_v1",
            "extractor_profile": "default",
            "validator_profile": "garmin_watch_basic_v1",
        },
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO category_runtime_profile (
                id, category_id, active_template_id, prompt_profile, extractor_profile, validator_profile,
                status, metadata_json, created_at, updated_at
            )
            SELECT
                :profile_id, :category_id, :template_id, :prompt_profile, :extractor_profile, :validator_profile,
                'ACTIVE', '{"source":"seed"}'::jsonb, now(), now()
            FROM category c
            JOIN category_attr_template t ON t.id = CAST(:template_id AS uuid)
            WHERE c.id = CAST(:category_id AS uuid)
              AND NOT EXISTS (
                SELECT 1 FROM category_runtime_profile WHERE category_id = CAST(:category_id AS uuid)
            )
            """
        ),
        {
            "profile_id": "33333333-3333-3333-3333-333333333501",
            "category_id": "33333333-3333-3333-3333-333333333101",
            "template_id": "33333333-3333-3333-3333-333333333401",
            "prompt_profile": "apple_computer_extract_v1",
            "extractor_profile": "default",
            "validator_profile": "apple_computer_basic_v1",
        },
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO category_runtime_profile (
                id, category_id, active_template_id, prompt_profile, extractor_profile, validator_profile,
                status, metadata_json, created_at, updated_at
            )
            SELECT
                :profile_id, :category_id, :template_id, :prompt_profile, :extractor_profile, :validator_profile,
                'ACTIVE', '{"source":"seed"}'::jsonb, now(), now()
            FROM category c
            JOIN category_attr_template t ON t.id = CAST(:template_id AS uuid)
            WHERE c.id = CAST(:category_id AS uuid)
              AND NOT EXISTS (
                SELECT 1 FROM category_runtime_profile WHERE category_id = CAST(:category_id AS uuid)
            )
            """
        ),
        {
            "profile_id": "abbf037f-3324-4892-aeb1-91ee89bdd701",
            "category_id": "abbf037f-3324-4892-aeb1-91ee89bdd7e6",
            "template_id": "78e3b40e-c6d3-485e-9cf7-beb9fd045d09",
            "prompt_profile": "camera_interchangeable_lens_extract_v1",
            "extractor_profile": "default",
            "validator_profile": "lens_basic_v1",
        },
    )

    connection.execute(
        sa.text(
            """
            UPDATE crawl_tasks
            SET category_id = :category_id
            WHERE category_id IS NULL
              AND business_domain IN ('garmin', 'garmin_watch')
            """
        ),
        {"category_id": "22222222-2222-2222-2222-222222222101"},
    )
    connection.execute(
        sa.text(
            """
            UPDATE crawl_tasks
            SET category_id = :category_id
            WHERE category_id IS NULL
              AND business_domain IN ('apple_m_series', 'apple_computer')
            """
        ),
        {"category_id": "33333333-3333-3333-3333-333333333101"},
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM category_runtime_profile
            WHERE id IN (
                '11111111-1111-1111-1111-111111111501',
                '22222222-2222-2222-2222-222222222501',
                '33333333-3333-3333-3333-333333333501',
                'abbf037f-3324-4892-aeb1-91ee89bdd701'
            )
              AND metadata_json @> '{"source":"seed"}'::jsonb
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE crawl_tasks
            SET category_id = NULL
            WHERE business_domain IN ('garmin', 'garmin_watch', 'apple_m_series', 'apple_computer')
            """
        )
    )
