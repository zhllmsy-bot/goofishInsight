from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AttributeDataType(str, Enum):
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    JSON = "JSON"


class AttributeScopeType(str, Enum):
    PLATFORM = "PLATFORM"
    MERCHANT = "MERCHANT"
    CHANNEL = "CHANNEL"


class AttributeStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    DISABLED = "DISABLED"


class TemplateStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class ProductStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class XianyuCategoryMatchScope(str, Enum):
    CAT = "CAT"
    TB_CAT = "TB_CAT"
    CAT_TB = "CAT_TB"
    C_CAT = "C_CAT"


class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"
    DEAD = "DEAD"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BrowserSession(TimestampMixin, Base):
    __tablename__ = "browser_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    profile_dir: Mapped[str] = mapped_column(Text, nullable=False)
    browser_channel: Mapped[str] = mapped_column(String(64), nullable=False, default="msedge")
    auth_state: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    last_login_required_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class CrawlTask(TimestampMixin, Base):
    __tablename__ = "crawl_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    source_platform: Mapped[str] = mapped_column(String(32), nullable=False, default="xianyu")
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    business_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False, default="PRODUCTION")
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    brand_lexicon: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    model_lexicon: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    config_lexicon: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    paging_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    profile_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    parallel_tabs: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    category: Mapped["Category | None"] = relationship(back_populates="crawl_tasks")
    runs: Mapped[list["CrawlRun"]] = relationship(back_populates="task")
    queries: Mapped[list["CrawlTaskQuery"]] = relationship(back_populates="task")
    lexicons: Mapped[list["CrawlTaskLexicon"]] = relationship(back_populates="task")


class CollectorJobRun(Base):
    __tablename__ = "collector_job_run"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="probe")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    crawl_runs: Mapped[list["CrawlRun"]] = relationship(back_populates="job_run")


class CollectorJobCheckpoint(Base):
    __tablename__ = "collector_job_checkpoint"

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="eager")
    cursor_pending: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cursor_committed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("crawl_tasks.id"), nullable=False)
    job_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("collector_job_run.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tab_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pages_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)

    task: Mapped["CrawlTask"] = relationship(back_populates="runs")
    job_run: Mapped["CollectorJobRun | None"] = relationship(back_populates="crawl_runs")
    raw_requests: Mapped[list["RawRequest"]] = relationship(back_populates="run")
    raw_responses: Mapped[list["RawResponse"]] = relationship(back_populates="run")


class RawRequest(Base):
    __tablename__ = "raw_requests"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(ForeignKey("crawl_runs.id"), nullable=False)
    task_id: Mapped[int] = mapped_column(ForeignKey("crawl_tasks.id"), nullable=False)
    task_query_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_task_query.id"))
    source_platform: Mapped[str] = mapped_column(String(32), nullable=False, default="xianyu")
    request_url: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="POST")
    request_headers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    request_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped["CrawlRun"] = relationship(back_populates="raw_requests")


class RawResponse(Base):
    __tablename__ = "raw_responses"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(ForeignKey("crawl_runs.id"), nullable=False)
    task_id: Mapped[int] = mapped_column(ForeignKey("crawl_tasks.id"), nullable=False)
    task_query_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_task_query.id"))
    source_platform: Mapped[str] = mapped_column(String(32), nullable=False, default="xianyu")
    raw_request_id: Mapped[UUID | None] = mapped_column(ForeignKey("raw_requests.id"))
    api_name: Mapped[str] = mapped_column(String(128), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped["CrawlRun"] = relationship(back_populates="raw_responses")


class SellerProfile(TimestampMixin, Base):
    __tablename__ = "seller_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    seller_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    seller_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(String(128))
    listing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    items: Mapped[list["Item"]] = relationship(back_populates="seller")


class Item(TimestampMixin, Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    task_id: Mapped[int] = mapped_column(ForeignKey("crawl_tasks.id"), nullable=False)
    task_query_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_task_query.id"))
    seller_profile_id: Mapped[int | None] = mapped_column(ForeignKey("seller_profiles.id"))
    current_raw_response_id: Mapped[UUID | None] = mapped_column(ForeignKey("raw_responses.id"))
    source_platform: Mapped[str] = mapped_column(String(32), nullable=False, default="xianyu")
    business_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    target_category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    resolved_category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    resolved_template_id: Mapped[str | None] = mapped_column(ForeignKey("category_attr_template.id"))
    category_validation_status: Mapped[str] = mapped_column(String(64), nullable=False, default="PENDING")
    category_validation_reason: Mapped[str | None] = mapped_column(String(128))
    category_validation_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    source_keyword: Mapped[str | None] = mapped_column(String(128))
    xianyu_cat_id: Mapped[str | None] = mapped_column(String(64))
    xianyu_tb_cat_id: Mapped[str | None] = mapped_column(String(64))
    xianyu_c_cat_id: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_brand: Mapped[str | None] = mapped_column(String(128))
    normalized_model_family: Mapped[str | None] = mapped_column(String(128))
    normalized_model: Mapped[str | None] = mapped_column(String(128))
    normalized_chip: Mapped[str | None] = mapped_column(String(64))
    normalized_memory_gb: Mapped[int | None] = mapped_column(Integer)
    normalized_storage_gb: Mapped[int | None] = mapped_column(Integer)
    condition_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    region: Mapped[str | None] = mapped_column(String(128))
    listing_url: Mapped[str | None] = mapped_column(Text)
    image_urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_auction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_ad: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_video: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    llm_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    llm_review_reason: Mapped[str | None] = mapped_column(String(64))
    llm_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    llm_review_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    llm_review_input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    llm_review_input_signature: Mapped[str | None] = mapped_column(String(64))
    llm_review_needs_audit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_review_audit_reason: Mapped[str | None] = mapped_column(String(64))
    llm_review_decision: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    seller: Mapped["SellerProfile | None"] = relationship(back_populates="items")
    snapshots: Mapped[list["ItemSnapshot"]] = relationship(back_populates="item")
    samples: Mapped[list["ItemSample"]] = relationship("ItemSample", back_populates="item")
    spec_enrichment: Mapped["ItemSpecEnrichment | None"] = relationship(
        back_populates="item",
        uselist=False,
    )


class ItemIngestRejection(TimestampMixin, Base):
    __tablename__ = "item_ingest_rejection"
    __table_args__ = (
        UniqueConstraint(
            "source_platform",
            "item_id",
            name="uq_item_ingest_rejection_platform_item",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_platform: Mapped[str] = mapped_column(String(32), nullable=False, default="xianyu")
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    business_domain: Mapped[str | None] = mapped_column(String(64))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    rejection_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    rejection_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_rejected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_rejected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class HomeFeedItemDecision(TimestampMixin, Base):
    __tablename__ = "home_feed_item_decision"
    __table_args__ = (
        UniqueConstraint(
            "source_platform",
            "item_id",
            "decision_stage",
            name="uq_home_feed_item_decision_stage",
        ),
        Index("ix_home_feed_item_decision_status_time", "decision_status", "updated_at"),
        Index("ix_home_feed_item_decision_domain_time", "resolved_business_domain", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id_ref: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    source_platform: Mapped[str] = mapped_column(String(32), nullable=False, default="xianyu")
    decision_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_status: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_source: Mapped[str | None] = mapped_column(String(64))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    current_outreach_status: Mapped[str | None] = mapped_column(String(32))
    resolved_business_domain: Mapped[str | None] = mapped_column(String(64))
    resolved_category_id: Mapped[str | None] = mapped_column(String(64))
    resolved_template_id: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    match_key: Mapped[str | None] = mapped_column(String(255))
    match_scope: Mapped[str | None] = mapped_column(String(32))
    candidate_business_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    active_candidate_business_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class BatchCollectRiskEvent(TimestampMixin, Base):
    __tablename__ = "batch_collect_risk_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default="risk_control")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    scope_key: Mapped[str] = mapped_column(Text, nullable=False)
    config_path: Mapped[str | None] = mapped_column(Text)
    profile_key: Mapped[str | None] = mapped_column(String(128))
    task_key: Mapped[str | None] = mapped_column(String(128))
    task_query_id: Mapped[str | None] = mapped_column(String(64))
    query: Mapped[str | None] = mapped_column(Text)
    normalized_query: Mapped[str | None] = mapped_column(Text)
    auth_state: Mapped[str | None] = mapped_column(String(32))
    consecutive_risk_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    backoff_seconds: Mapped[int | None] = mapped_column(Integer)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class BrowserJobAttempt(TimestampMixin, Base):
    __tablename__ = "browser_job_attempt"
    __table_args__ = (
        Index("ix_browser_job_attempt_profile_time", "profile_key", "occurred_at"),
        Index("ix_browser_job_attempt_feature_stage_time", "feature", "stage", "occurred_at"),
        Index("ix_browser_job_attempt_task_time", "task_key", "occurred_at"),
        Index("ix_browser_job_attempt_outcome_time", "attempt_outcome", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    profile_key: Mapped[str] = mapped_column(String(128), nullable=False)
    feature: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="execute")
    scope_key: Mapped[str | None] = mapped_column(Text)
    task_key: Mapped[str | None] = mapped_column(String(128))
    task_query_id: Mapped[str | None] = mapped_column(String(64))
    query: Mapped[str | None] = mapped_column(Text)
    normalized_query: Mapped[str | None] = mapped_column(Text)
    business_domain: Mapped[str | None] = mapped_column(String(64))
    attempt_outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    auth_state: Mapped[str | None] = mapped_column(String(32))
    is_probe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_test_task: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    guard_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    browser_ready: Mapped[bool | None] = mapped_column(Boolean)
    job_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("collector_job_run.id"))
    error_signature: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class BrowserGuardEvent(TimestampMixin, Base):
    __tablename__ = "browser_guard_event"
    __table_args__ = (
        Index("ix_browser_guard_event_profile_time", "profile_key", "occurred_at"),
        Index("ix_browser_guard_event_feature_event_time", "feature", "event_type", "occurred_at"),
        Index("ix_browser_guard_event_scope_time", "scope_key", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    profile_key: Mapped[str] = mapped_column(String(128), nullable=False)
    feature: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    auth_state: Mapped[str | None] = mapped_column(String(32))
    consecutive_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    backoff_seconds: Mapped[int | None] = mapped_column(Integer)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    keep_page_open: Mapped[bool | None] = mapped_column(Boolean)
    error_signature: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ItemSnapshot(Base):
    __tablename__ = "item_snapshots"
    __table_args__ = (
        UniqueConstraint("item_id_ref", "snapshot_at", name="uq_item_snapshot_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id_ref: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    task_query_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_task_query.id"))
    raw_response_id: Mapped[UUID | None] = mapped_column(ForeignKey("raw_responses.id"))
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    region: Mapped[str | None] = mapped_column(String(128))
    condition_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    item: Mapped["Item"] = relationship(back_populates="snapshots")


class SkuFingerprint(TimestampMixin, Base):
    __tablename__ = "sku_fingerprints"
    __table_args__ = (
        UniqueConstraint(
            "schema_id",
            "fingerprint_hash",
            name="uq_sku_fingerprint_schema_hash",
        ),
        Index(
            "ix_sku_fingerprint_schema",
            "schema_id",
            "fingerprint_hash",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    schema_id: Mapped[int] = mapped_column(
        ForeignKey("sku_spec_schema_snapshots.schema_id"),
        nullable=False,
    )
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lock_signature: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    variant_signature: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_signature: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    schema_snapshot: Mapped["SkuSpecSchemaSnapshot"] = relationship(back_populates="sku_fingerprints")
    samples: Mapped[list["ItemSample"]] = relationship(back_populates="sku_fingerprint")


class ItemSample(TimestampMixin, Base):
    __tablename__ = "item_samples"
    __table_args__ = (
        UniqueConstraint(
            "item_id_ref",
            "sku_fingerprint_id",
            name="uq_item_sample_item_fingerprint",
        ),
        Index("ix_item_sample_item", "item_id_ref"),
        Index("ix_item_sample_fingerprint", "sku_fingerprint_id"),
        Index("ix_item_sample_state", "sample_state"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id_ref: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    sku_fingerprint_id: Mapped[int] = mapped_column(
        ForeignKey("sku_fingerprints.id"),
        nullable=False,
    )
    sample_state: Mapped[str] = mapped_column(String(32), nullable=False)
    sample_quality_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        default=Decimal("0"),
    )
    missing_required_attrs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    sample_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    condition_multiplier: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 3),
        nullable=True,
    )

    item: Mapped["Item"] = relationship(back_populates="samples")
    sku_fingerprint: Mapped["SkuFingerprint"] = relationship(back_populates="samples")


class ConditionAdjuster(TimestampMixin, Base):
    __tablename__ = "condition_adjusters"
    __table_args__ = (
        UniqueConstraint("scope_key", "condition_code", name="uq_condition_adjuster_scope_code"),
        Index("ix_condition_adjuster_scope_status", "scope_key", "status", "priority"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_code: Mapped[str] = mapped_column(String(32), nullable=False)
    condition_label: Mapped[str | None] = mapped_column(String(64))
    match_tokens: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class SkuNeighbor(TimestampMixin, Base):
    __tablename__ = "sku_neighbors"
    __table_args__ = (
        UniqueConstraint("sku_fingerprint_id", "neighbor_fingerprint_id", name="uq_sku_neighbor_pair"),
        Index("ix_sku_neighbor_lookup", "sku_fingerprint_id", "neighbor_rank"),
        Index("ix_sku_neighbor_schema", "schema_id", "neighbor_rank"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    schema_id: Mapped[int] = mapped_column(ForeignKey("sku_spec_schema_snapshots.schema_id"), nullable=False)
    sku_fingerprint_id: Mapped[int] = mapped_column(ForeignKey("sku_fingerprints.id"), nullable=False)
    neighbor_fingerprint_id: Mapped[int] = mapped_column(ForeignKey("sku_fingerprints.id"), nullable=False)
    neighbor_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    similarity_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class MsrpAnchor(TimestampMixin, Base):
    __tablename__ = "msrp_anchors"
    __table_args__ = (
        UniqueConstraint(
            "scope_key",
            "model_catalog_id",
            "schema_id",
            "anchor_key",
            name="uq_msrp_anchor_scope_model_schema_key",
        ),
        Index("ix_msrp_anchor_scope_status", "scope_key", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("category_model_catalog.id"))
    schema_id: Mapped[int | None] = mapped_column(ForeignKey("sku_spec_schema_snapshots.schema_id"))
    anchor_key: Mapped[str] = mapped_column(String(255), nullable=False)
    msrp_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    buy_ceiling_ratio: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    source_label: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    effective_from: Mapped[date | None] = mapped_column(Date)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ItemSpecEnrichment(TimestampMixin, Base):
    __tablename__ = "item_spec_enrichments"
    __table_args__ = (
        UniqueConstraint("item_id_ref", name="uq_item_spec_enrichments_item_id_ref"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id_ref: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    business_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    template_id: Mapped[str | None] = mapped_column(ForeignKey("category_attr_template.id"))
    model_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("category_model_catalog.id"))
    extractor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="rule")
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    llm_provider: Mapped[str | None] = mapped_column(String(64))
    llm_model: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="partial")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    brand: Mapped[str | None] = mapped_column(String(128))
    product_line: Mapped[str | None] = mapped_column(String(128))
    model_family: Mapped[str | None] = mapped_column(String(128))
    model_name: Mapped[str | None] = mapped_column(String(255))
    generation: Mapped[str | None] = mapped_column(String(64))
    case_size_mm: Mapped[int | None] = mapped_column(Integer)
    is_solar: Mapped[bool | None] = mapped_column(Boolean)
    display_type: Mapped[str | None] = mapped_column(String(32))
    screen_size_in: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    chip_family: Mapped[str | None] = mapped_column(String(64))
    cpu_model: Mapped[str | None] = mapped_column(String(64))
    cpu_cores: Mapped[int | None] = mapped_column(Integer)
    gpu_cores: Mapped[int | None] = mapped_column(Integer)
    memory_gb: Mapped[int | None] = mapped_column(Integer)
    storage_gb: Mapped[int | None] = mapped_column(Integer)
    edition_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    extraction_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    item: Mapped["Item"] = relationship(back_populates="spec_enrichment")


class ItemReviewV3(TimestampMixin, Base):
    __tablename__ = "item_review_v3"
    __table_args__ = (
        UniqueConstraint("item_id_ref", name="uq_item_review_v3_item_id_ref"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    item_id_ref: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    business_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    template_id: Mapped[str | None] = mapped_column(ForeignKey("category_attr_template.id"))
    model_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("category_model_catalog.id"))
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v3")
    stage_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    resolution_status: Mapped[str] = mapped_column(String(64), nullable=False, default="PENDING_REVIEW")
    reject_reason: Mapped[str | None] = mapped_column(String(128))
    needs_human: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_pass_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    second_pass_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    llm_provider: Mapped[str | None] = mapped_column(String(64))
    llm_model: Mapped[str | None] = mapped_column(String(128))
    extracted_features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    mapping_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    candidate_payload: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    second_pass_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    final_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class DailyMetric(Base):
    __tablename__ = "daily_metrics"
    __table_args__ = (
        UniqueConstraint(
            "metric_date",
            "category_id",
            "model_catalog_id",
            name="uq_daily_metric_category_model",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    business_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    model_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("category_model_catalog.id"))
    normalized_model: Mapped[str | None] = mapped_column(String(128))
    listing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_seller_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    median_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    p25_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    p75_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    metric_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelScore(Base):
    __tablename__ = "model_scores"
    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "model_catalog_id",
            "score_date",
            name="uq_model_score_category_model_date",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    model_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("category_model_catalog.id"))
    normalized_model: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_model_family: Mapped[str | None] = mapped_column(String(128))
    score_date: Mapped[date] = mapped_column(Date, nullable=False)
    liquidity_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    profit_potential_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    selection_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    score_reason: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    business_domain: Mapped[str | None] = mapped_column(String(64))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    template_id: Mapped[str | None] = mapped_column(ForeignKey("category_attr_template.id"))
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutreachRecord(TimestampMixin, Base):
    __tablename__ = "outreach_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    item_id_ref: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    business_domain: Mapped[str | None] = mapped_column(String(64))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    model_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("category_model_catalog.id"))
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="home_feed")
    target_label: Mapped[str | None] = mapped_column(String(255))
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    feed_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    target_buy_ceiling: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_status: Mapped[str | None] = mapped_column(String(32))
    deal_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operator_note: Mapped[str | None] = mapped_column(Text)


class BuyWatchTarget(TimestampMixin, Base):
    __tablename__ = "buy_watch_target"
    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "model_catalog_id",
            "target_name",
            "profile_key",
            name="uq_buy_watch_target_scope",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    category_id: Mapped[str] = mapped_column(ForeignKey("category.id"), nullable=False)
    model_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("category_model_catalog.id"))
    target_name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    budget_ceiling: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    desired_memory_gb: Mapped[int | None] = mapped_column(Integer)
    desired_storage_gb: Mapped[int | None] = mapped_column(Integer)
    desired_region: Mapped[str | None] = mapped_column(String(128))
    max_listing_age_hours: Mapped[int | None] = mapped_column(Integer)
    risk_tolerance: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    notify_cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class BuyPriceBaseline(TimestampMixin, Base):
    __tablename__ = "buy_price_baseline"
    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "model_catalog_id",
            "schema_id",
            "baseline_key",
            "baseline_date",
            name="uq_buy_price_baseline_key_date",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    category_id: Mapped[str] = mapped_column(ForeignKey("category.id"), nullable=False)
    model_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("category_model_catalog.id"))
    schema_id: Mapped[int | None] = mapped_column(ForeignKey("sku_spec_schema_snapshots.schema_id"))
    baseline_key: Mapped[str] = mapped_column(String(255), nullable=False)
    memory_gb: Mapped[int | None] = mapped_column(Integer)
    storage_gb: Mapped[int | None] = mapped_column(Integer)
    region: Mapped[str | None] = mapped_column(String(128))
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    median_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    p25_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    p75_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    fair_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    buy_ceiling: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    baseline_date: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    schema_snapshot: Mapped["SkuSpecSchemaSnapshot | None"] = relationship(
        back_populates="buy_price_baselines"
    )


class BuyOpportunity(TimestampMixin, Base):
    __tablename__ = "buy_opportunity"
    __table_args__ = (
        UniqueConstraint("item_id_ref", "watch_target_id", name="uq_buy_opportunity_item_target"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    item_id_ref: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    model_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("category_model_catalog.id"))
    watch_target_id: Mapped[str] = mapped_column(ForeignKey("buy_watch_target.id"), nullable=False)
    baseline_id: Mapped[str | None] = mapped_column(ForeignKey("buy_price_baseline.id"))
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    fair_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    buy_ceiling: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    discount_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    opportunity_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    decision: Mapped[str | None] = mapped_column(String(32))
    decision_note: Mapped[str | None] = mapped_column(Text)
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class BuyOpportunityRisk(TimestampMixin, Base):
    __tablename__ = "buy_opportunity_risk"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "risk_code", name="uq_buy_opportunity_risk_code"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("buy_opportunity.id"), nullable=False)
    risk_code: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    detail: Mapped[str | None] = mapped_column(Text)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class BuyAlertEvent(TimestampMixin, Base):
    __tablename__ = "buy_alert_event"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("buy_opportunity.id"), nullable=False)
    watch_target_id: Mapped[str] = mapped_column(ForeignKey("buy_watch_target.id"), nullable=False)
    alert_channel: Mapped[str] = mapped_column(String(64), nullable=False, default="dashboard")
    alert_reason: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class NotificationDelivery(TimestampMixin, Base):
    __tablename__ = "notification_delivery"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    alert_event_id: Mapped[str | None] = mapped_column(ForeignKey("buy_alert_event.id"))
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="dashboard")
    destination: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        Index(
            "ix_notification_delivery_pending_retry",
            "next_retry_at",
            postgresql_where=(status == "pending"),
        ),
        Index("ix_notification_delivery_alert_event", "alert_event_id"),
    )


class BuyDecisionFeedback(TimestampMixin, Base):
    __tablename__ = "buy_decision_feedback"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("buy_opportunity.id"), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(64), nullable=False)
    feedback_label: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_id: Mapped[str | None] = mapped_column(String(64))
    feedback_note: Mapped[str | None] = mapped_column(Text)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    expected_resale_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class DecisionFeedbackLog(Base):
    __tablename__ = "decision_feedback_log"
    __table_args__ = (
        UniqueConstraint("feedback_id", name="uq_decision_feedback_log_feedback"),
        Index("ix_decision_feedback_log_opportunity_time", "opportunity_id", "recorded_at"),
        Index("ix_decision_feedback_log_scope_time", "scope_key", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    feedback_id: Mapped[str] = mapped_column(ForeignKey("buy_decision_feedback.id"), nullable=False)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("buy_opportunity.id"), nullable=False)
    item_id_ref: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    scope_key: Mapped[str | None] = mapped_column(String(64))
    model_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("category_model_catalog.id"))
    schema_id: Mapped[int | None] = mapped_column(ForeignKey("sku_spec_schema_snapshots.schema_id"))
    fingerprint_hash: Mapped[str | None] = mapped_column(String(64))
    baseline_match_level: Mapped[str | None] = mapped_column(String(64))
    baseline_match_key: Mapped[str | None] = mapped_column(String(255))
    feedback_type: Mapped[str] = mapped_column(String(64), nullable=False)
    feedback_label: Mapped[str] = mapped_column(String(64), nullable=False)
    feedback_action: Mapped[str] = mapped_column(String(32), nullable=False)
    feedback_category: Mapped[str | None] = mapped_column(String(64))
    opportunity_status: Mapped[str | None] = mapped_column(String(32))
    operator_id: Mapped[str | None] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class UserListingPreference(TimestampMixin, Base):
    __tablename__ = "user_listing_preference"
    __table_args__ = (
        UniqueConstraint("operator_id", "source", "item_id", name="uq_user_listing_preference_scope"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    operator_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="dashboard")
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id_ref: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    preference: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Category(TimestampMixin, Base):
    __tablename__ = "category"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")

    parent: Mapped["Category | None"] = relationship(
        "Category",
        remote_side="Category.id",
        back_populates="children",
    )
    children: Mapped[list["Category"]] = relationship("Category", back_populates="parent")
    templates: Mapped[list["CategoryAttrTemplate"]] = relationship(back_populates="category")
    spec_schema_snapshots: Mapped[list["SkuSpecSchemaSnapshot"]] = relationship(back_populates="category")
    runtime_profile: Mapped["CategoryRuntimeProfile | None"] = relationship(
        back_populates="category",
        uselist=False,
        foreign_keys="CategoryRuntimeProfile.category_id",
    )
    model_catalog_entries: Mapped[list["CategoryModelCatalog"]] = relationship(back_populates="category")
    crawl_tasks: Mapped[list["CrawlTask"]] = relationship(back_populates="category")
    spus: Mapped[list["ProductSpu"]] = relationship(back_populates="category")
    xianyu_mappings: Mapped[list["XianyuCategoryMapping"]] = relationship(back_populates="category")


class AttributeDefinition(TimestampMixin, Base):
    __tablename__ = "attribute_definition"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "code", name="uq_attribute_definition_scope_code"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    scope_type: Mapped[AttributeScopeType] = mapped_column(
        SAEnum(AttributeScopeType, name="attribute_scope_type"),
        nullable=False,
        default=AttributeScopeType.PLATFORM,
    )
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, default="platform")
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[AttributeDataType] = mapped_column(
        SAEnum(AttributeDataType, name="attribute_data_type"),
        nullable=False,
    )
    value_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    is_multi: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    validation_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[AttributeStatus] = mapped_column(
        SAEnum(AttributeStatus, name="attribute_status"),
        nullable=False,
        default=AttributeStatus.DRAFT,
    )

    options: Mapped[list["AttributeOption"]] = relationship(back_populates="attribute")
    template_items: Mapped[list["CategoryAttrTemplateItem"]] = relationship(back_populates="attribute")
    spu_values: Mapped[list["ProductSpuAttrValue"]] = relationship(back_populates="attribute")
    sku_values: Mapped[list["ProductSkuAttrValue"]] = relationship(back_populates="attribute")


class AttributeOption(TimestampMixin, Base):
    __tablename__ = "attribute_option"
    __table_args__ = (
        UniqueConstraint("attribute_id", "option_code", name="uq_attribute_option_code"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    attribute_id: Mapped[str] = mapped_column(ForeignKey("attribute_definition.id"), nullable=False)
    option_code: Mapped[str] = mapped_column(String(64), nullable=False)
    option_name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[AttributeStatus] = mapped_column(
        SAEnum(AttributeStatus, name="attribute_status"),
        nullable=False,
        default=AttributeStatus.ACTIVE,
    )

    attribute: Mapped["AttributeDefinition"] = relationship(back_populates="options")
    spu_values: Mapped[list["ProductSpuAttrValue"]] = relationship(back_populates="option")
    sku_values: Mapped[list["ProductSkuAttrValue"]] = relationship(back_populates="option")


class CategoryAttrTemplate(TimestampMixin, Base):
    __tablename__ = "category_attr_template"
    __table_args__ = (
        UniqueConstraint("category_id", "version", name="uq_category_attr_template_version"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    category_id: Mapped[str] = mapped_column(ForeignKey("category.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TemplateStatus] = mapped_column(
        SAEnum(TemplateStatus, name="template_status"),
        nullable=False,
        default=TemplateStatus.DRAFT,
    )
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[str | None] = mapped_column(String(64))

    category: Mapped["Category"] = relationship(back_populates="templates")
    items: Mapped[list["CategoryAttrTemplateItem"]] = relationship(back_populates="template")
    spec_schema_snapshots: Mapped[list["SkuSpecSchemaSnapshot"]] = relationship(back_populates="template")
    active_runtime_profiles: Mapped[list["CategoryRuntimeProfile"]] = relationship(
        back_populates="active_template",
        foreign_keys="CategoryRuntimeProfile.active_template_id",
    )
    spus: Mapped[list["ProductSpu"]] = relationship(back_populates="template")
    xianyu_mappings: Mapped[list["XianyuCategoryMapping"]] = relationship(
        back_populates="template",
        foreign_keys="XianyuCategoryMapping.template_id",
    )


class CategoryRuntimeProfile(TimestampMixin, Base):
    __tablename__ = "category_runtime_profile"
    __table_args__ = (
        UniqueConstraint("category_id", name="uq_category_runtime_profile_category"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    category_id: Mapped[str] = mapped_column(ForeignKey("category.id"), nullable=False)
    active_template_id: Mapped[str | None] = mapped_column(ForeignKey("category_attr_template.id"))
    prompt_profile: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_profile: Mapped[str | None] = mapped_column(String(64))
    validator_profile: Mapped[str | None] = mapped_column(String(64))
    llm_provider_override: Mapped[str | None] = mapped_column(String(64))
    llm_model_override: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    category: Mapped["Category"] = relationship(
        back_populates="runtime_profile",
        foreign_keys=[category_id],
    )
    active_template: Mapped["CategoryAttrTemplate | None"] = relationship(
        back_populates="active_runtime_profiles",
        foreign_keys=[active_template_id],
    )


class CategoryModelCatalog(TimestampMixin, Base):
    __tablename__ = "category_model_catalog"
    __table_args__ = (
        UniqueConstraint("category_id", "model_code", name="uq_category_model_catalog_code"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    category_id: Mapped[str] = mapped_column(ForeignKey("category.id"), nullable=False)
    brand_name: Mapped[str | None] = mapped_column(String(128))
    series_name: Mapped[str | None] = mapped_column(String(128))
    model_code: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    category: Mapped["Category"] = relationship(back_populates="model_catalog_entries")
    aliases: Mapped[list["CategoryModelAlias"]] = relationship(back_populates="model")


class CategoryModelAlias(TimestampMixin, Base):
    __tablename__ = "category_model_alias"
    __table_args__ = (
        UniqueConstraint("model_id", "alias_normalized", name="uq_category_model_alias_normalized"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    model_id: Mapped[str] = mapped_column(ForeignKey("category_model_catalog.id"), nullable=False)
    alias_text: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_type: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    model: Mapped["CategoryModelCatalog"] = relationship(back_populates="aliases")


class XianyuCategoryMapping(TimestampMixin, Base):
    __tablename__ = "xianyu_category_mapping"
    __table_args__ = (
        UniqueConstraint("match_key", name="uq_xianyu_category_mapping_match_key"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    match_scope: Mapped[XianyuCategoryMatchScope] = mapped_column(
        SAEnum(XianyuCategoryMatchScope, name="xianyu_category_match_scope"),
        nullable=False,
    )
    match_key: Mapped[str] = mapped_column(String(255), nullable=False)
    xianyu_cat_id: Mapped[str | None] = mapped_column(String(64))
    xianyu_tb_cat_id: Mapped[str | None] = mapped_column(String(64))
    xianyu_c_cat_id: Mapped[str | None] = mapped_column(String(64))
    raw_category_name: Mapped[str | None] = mapped_column(String(255))
    raw_category_path: Mapped[str | None] = mapped_column(String(512))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    template_id: Mapped[str | None] = mapped_column(ForeignKey("category_attr_template.id"))
    policy_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="FORCE_TEMPLATE")
    template_override_id: Mapped[str | None] = mapped_column(ForeignKey("category_attr_template.id"))
    resolution_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    category: Mapped["Category | None"] = relationship(back_populates="xianyu_mappings")
    template: Mapped["CategoryAttrTemplate | None"] = relationship(
        back_populates="xianyu_mappings",
        foreign_keys=[template_id],
    )
    template_override: Mapped["CategoryAttrTemplate | None"] = relationship(
        foreign_keys=[template_override_id],
    )


class XianyuCategoryOnboardingQueue(TimestampMixin, Base):
    __tablename__ = "xianyu_category_onboarding_queue"
    __table_args__ = (
        UniqueConstraint("match_key", name="uq_xianyu_category_onboarding_queue_match_key"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    match_scope: Mapped[XianyuCategoryMatchScope] = mapped_column(
        SAEnum(XianyuCategoryMatchScope, name="xianyu_category_match_scope"),
        nullable=False,
    )
    match_key: Mapped[str] = mapped_column(String(255), nullable=False)
    xianyu_cat_id: Mapped[str | None] = mapped_column(String(64))
    xianyu_tb_cat_id: Mapped[str | None] = mapped_column(String(64))
    xianyu_c_cat_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    owner_operator_id: Mapped[str | None] = mapped_column(String(64))
    status_note: Mapped[str | None] = mapped_column(Text)
    item_count_snapshot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sample_item_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sample_titles: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    business_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    resolved_mapping_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class CrawlTaskQuery(TimestampMixin, Base):
    __tablename__ = "crawl_task_query"
    __table_args__ = (
        UniqueConstraint("task_id", "query_text", name="uq_crawl_task_query_text"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("crawl_tasks.id"), nullable=False)
    query_text: Mapped[str] = mapped_column(String(255), nullable=False)
    pages: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    task: Mapped["CrawlTask"] = relationship(back_populates="queries")


class CrawlTaskLexicon(TimestampMixin, Base):
    __tablename__ = "crawl_task_lexicon"
    __table_args__ = (
        UniqueConstraint("task_id", "lexicon_type", "term", name="uq_crawl_task_lexicon_term"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("crawl_tasks.id"), nullable=False)
    lexicon_type: Mapped[str] = mapped_column(String(32), nullable=False)
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    task: Mapped["CrawlTask"] = relationship(back_populates="lexicons")


class CategoryAttrTemplateItem(TimestampMixin, Base):
    __tablename__ = "category_attr_template_item"
    __table_args__ = (
        UniqueConstraint("template_id", "attribute_id", name="uq_category_attr_template_item"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    template_id: Mapped[str] = mapped_column(ForeignKey("category_attr_template.id"), nullable=False)
    attribute_id: Mapped[str] = mapped_column(ForeignKey("attribute_definition.id"), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_sale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_filter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_search: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_display: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="descriptive")
    weight: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), default=Decimal("0"))
    normalization: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enum_values: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSONB)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    template: Mapped["CategoryAttrTemplate"] = relationship(back_populates="items")
    attribute: Mapped["AttributeDefinition"] = relationship(back_populates="template_items")


class SkuSpecSchemaSnapshot(TimestampMixin, Base):
    __tablename__ = "sku_spec_schema_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "category_code",
            "template_version",
            name="uq_sku_spec_schema_snapshot_category_version",
        ),
        Index(
            "ix_sku_spec_schema_snapshot_active",
            "category_code",
            postgresql_where=text("valid_to IS NULL"),
        ),
    )

    schema_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    category_code: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[str | None] = mapped_column(ForeignKey("category_attr_template.id"))
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    locking_attrs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    required_attrs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    variant_attrs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    condition_attrs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    normalization: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enum_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(Text)

    category: Mapped["Category | None"] = relationship(back_populates="spec_schema_snapshots")
    template: Mapped["CategoryAttrTemplate | None"] = relationship(back_populates="spec_schema_snapshots")
    buy_price_baselines: Mapped[list["BuyPriceBaseline"]] = relationship(back_populates="schema_snapshot")
    sku_fingerprints: Mapped[list["SkuFingerprint"]] = relationship(back_populates="schema_snapshot")


class ProductSpu(TimestampMixin, Base):
    __tablename__ = "product_spu"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    category_id: Mapped[str] = mapped_column(ForeignKey("category.id"), nullable=False)
    template_id: Mapped[str] = mapped_column(ForeignKey("category_attr_template.id"), nullable=False)
    merchant_id: Mapped[str | None] = mapped_column(String(64))
    brand_id: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus, name="product_status"),
        nullable=False,
        default=ProductStatus.DRAFT,
    )
    attr_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    category: Mapped["Category"] = relationship(back_populates="spus")
    template: Mapped["CategoryAttrTemplate"] = relationship(back_populates="spus")
    skus: Mapped[list["ProductSku"]] = relationship(back_populates="spu")
    attributes: Mapped[list["ProductSpuAttrValue"]] = relationship(back_populates="spu")


class ProductSku(TimestampMixin, Base):
    __tablename__ = "product_sku"
    __table_args__ = (
        UniqueConstraint("sku_code", name="uq_product_sku_code"),
        UniqueConstraint("spu_id", "sales_signature_hash", name="uq_product_sku_signature"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    spu_id: Mapped[str] = mapped_column(ForeignKey("product_spu.id"), nullable=False)
    sku_code: Mapped[str] = mapped_column(String(64), nullable=False)
    sales_signature_raw: Mapped[str] = mapped_column(Text, nullable=False)
    sales_signature_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    barcode: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus, name="product_status"),
        nullable=False,
        default=ProductStatus.DRAFT,
    )
    attr_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    spu: Mapped["ProductSpu"] = relationship(back_populates="skus")
    attributes: Mapped[list["ProductSkuAttrValue"]] = relationship(back_populates="sku")


class ProductSpuAttrValue(TimestampMixin, Base):
    __tablename__ = "product_spu_attr_value"
    __table_args__ = (
        UniqueConstraint("spu_id", "attribute_id", "value_seq", name="uq_product_spu_attr_value"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    spu_id: Mapped[str] = mapped_column(ForeignKey("product_spu.id"), nullable=False)
    attribute_id: Mapped[str] = mapped_column(ForeignKey("attribute_definition.id"), nullable=False)
    value_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text_value: Mapped[str | None] = mapped_column(Text)
    number_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    normalized_number_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    bool_value: Mapped[bool | None] = mapped_column(Boolean)
    option_id: Mapped[str | None] = mapped_column(ForeignKey("attribute_option.id"))
    json_value: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB(none_as_null=True))

    spu: Mapped["ProductSpu"] = relationship(back_populates="attributes")
    attribute: Mapped["AttributeDefinition"] = relationship(back_populates="spu_values")
    option: Mapped["AttributeOption | None"] = relationship(back_populates="spu_values")


class ProductSkuAttrValue(TimestampMixin, Base):
    __tablename__ = "product_sku_attr_value"
    __table_args__ = (
        UniqueConstraint("sku_id", "attribute_id", "value_seq", name="uq_product_sku_attr_value"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    sku_id: Mapped[str] = mapped_column(ForeignKey("product_sku.id"), nullable=False)
    attribute_id: Mapped[str] = mapped_column(ForeignKey("attribute_definition.id"), nullable=False)
    value_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text_value: Mapped[str | None] = mapped_column(Text)
    number_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    normalized_number_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    bool_value: Mapped[bool | None] = mapped_column(Boolean)
    option_id: Mapped[str | None] = mapped_column(ForeignKey("attribute_option.id"))
    json_value: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB(none_as_null=True))

    sku: Mapped["ProductSku"] = relationship(back_populates="attributes")
    attribute: Mapped["AttributeDefinition"] = relationship(back_populates="sku_values")
    option: Mapped["AttributeOption | None"] = relationship(back_populates="sku_values")


class OutboxEvent(TimestampMixin, Base):
    __tablename__ = "outbox_event"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[OutboxStatus] = mapped_column(
        SAEnum(OutboxStatus, name="outbox_status"),
        nullable=False,
        default=OutboxStatus.PENDING,
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductAttrAuditLog(Base):
    __tablename__ = "product_attr_audit_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    operator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DataQualityMetric(Base):
    __tablename__ = "data_quality_metric"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True))
    task_key: Mapped[str | None] = mapped_column(Text)
    metric_value: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
