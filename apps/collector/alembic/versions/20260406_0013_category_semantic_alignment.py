"""align legacy category semantics to category-driven naming

Revision ID: 20260406_0013
Revises: 20260406_0012
Create Date: 2026-04-06 22:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260406_0013"
down_revision = "20260406_0012"
branch_labels = None
depends_on = None


APPLE_CATEGORY_ID = "33333333-3333-3333-3333-333333333101"
GARMIN_CATEGORY_ID = "22222222-2222-2222-2222-222222222101"


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE category
            SET code = 'apple_computer',
                name = 'Apple电脑',
                path = 'computers/apple-computer',
                updated_at = now()
            WHERE id = :category_id
            """
        ),
        {"category_id": APPLE_CATEGORY_ID},
    )
    connection.execute(
        sa.text(
            """
            UPDATE category
            SET name = 'Garmin手表',
                path = 'wearables/garmin-watch',
                updated_at = now()
            WHERE id = :category_id
            """
        ),
        {"category_id": GARMIN_CATEGORY_ID},
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE category
            SET code = 'apple_m_series',
                name = 'Apple M 系列电脑',
                path = 'computers/apple-m-series',
                updated_at = now()
            WHERE id = :category_id
            """
        ),
        {"category_id": APPLE_CATEGORY_ID},
    )
    connection.execute(
        sa.text(
            """
            UPDATE category
            SET name = '佳明手表',
                path = 'wearables/garmin-watch',
                updated_at = now()
            WHERE id = :category_id
            """
        ),
        {"category_id": GARMIN_CATEGORY_ID},
    )
