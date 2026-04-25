"""initial schema

Revision ID: 20260321_0001
Revises:
Create Date: 2026-03-21 16:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260321_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_key", sa.String(length=120), nullable=False),
        sa.Column("business_domain", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("brand_lexicon", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_lexicon", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config_lexicon", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("paging_limit", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_key", name="uq_crawl_tasks_task_key"),
    )

    op.create_table(
        "crawl_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("crawl_tasks.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tab_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pages_attempted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    op.create_table(
        "raw_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("crawl_runs.id"), nullable=False),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("crawl_tasks.id"), nullable=False),
        sa.Column("request_url", sa.Text(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False, server_default="POST"),
        sa.Column("request_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "raw_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("crawl_runs.id"), nullable=False),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("crawl_tasks.id"), nullable=False),
        sa.Column("raw_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_requests.id"), nullable=True),
        sa.Column("api_name", sa.String(length=128), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "seller_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("seller_id", sa.String(length=128), nullable=False),
        sa.Column("seller_name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("listing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("seller_id", name="uq_seller_profiles_seller_id"),
    )

    op.create_table(
        "items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("crawl_tasks.id"), nullable=False),
        sa.Column("seller_profile_id", sa.BigInteger(), sa.ForeignKey("seller_profiles.id"), nullable=True),
        sa.Column("current_raw_response_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_responses.id"), nullable=True),
        sa.Column("business_domain", sa.String(length=64), nullable=False),
        sa.Column("source_keyword", sa.String(length=128), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_tokens", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_brand", sa.String(length=128), nullable=True),
        sa.Column("normalized_model_family", sa.String(length=128), nullable=True),
        sa.Column("normalized_model", sa.String(length=128), nullable=True),
        sa.Column("normalized_chip", sa.String(length=64), nullable=True),
        sa.Column("normalized_memory_gb", sa.Integer(), nullable=True),
        sa.Column("normalized_storage_gb", sa.Integer(), nullable=True),
        sa.Column("condition_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("listing_url", sa.Text(), nullable=True),
        sa.Column("image_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_auction", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_ad", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_video", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("current_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("publish_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("item_id", name="uq_items_item_id"),
    )

    op.create_table(
        "item_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("item_id_ref", sa.BigInteger(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("raw_response_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_responses.id"), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("condition_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("publish_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint("item_id_ref", "snapshot_at", name="uq_item_snapshot_time"),
    )

    op.create_table(
        "daily_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("business_domain", sa.String(length=64), nullable=False),
        sa.Column("normalized_model", sa.String(length=128), nullable=True),
        sa.Column("listing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_seller_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("median_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("p25_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("p75_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("metric_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("metric_date", "business_domain", "normalized_model", name="uq_daily_metric_domain_model"),
    )

    op.create_table(
        "model_scores",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_domain", sa.String(length=64), nullable=False),
        sa.Column("normalized_model", sa.String(length=128), nullable=False),
        sa.Column("normalized_model_family", sa.String(length=128), nullable=True),
        sa.Column("score_date", sa.Date(), nullable=False),
        sa.Column("liquidity_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("profit_potential_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("selection_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("score_reason", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("business_domain", "normalized_model", "score_date", name="uq_model_score_domain_model_date"),
    )

    op.create_table(
        "analysis_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("business_domain", sa.String(length=64), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("analysis_reports")
    op.drop_table("model_scores")
    op.drop_table("daily_metrics")
    op.drop_table("item_snapshots")
    op.drop_table("items")
    op.drop_table("seller_profiles")
    op.drop_table("raw_responses")
    op.drop_table("raw_requests")
    op.drop_table("crawl_runs")
    op.drop_table("crawl_tasks")
