"""Data quality metrics aggregation service for W8."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select

from ...db import session_scope
from ...models import AnalysisReport, DataQualityMetric, ItemReviewV3
from .review_v3_mapping import (
    V3_STATUS_INVALID_OR_NOT_SUPPORTED,
    V3_STATUS_MANUAL_AUDIT_REQUIRED,
    V3_STATUS_PENDING_REVIEW,
    V3_STATUS_REJECTED_ACCESSORY,
    V3_STATUS_REJECTED_STATIC_GUARD,
    V3_STATUS_VALID_READY_FOR_PRICING,
)

REVIEW_V3_TERMINAL_STATUSES = {
    V3_STATUS_VALID_READY_FOR_PRICING,
    V3_STATUS_REJECTED_ACCESSORY,
    V3_STATUS_REJECTED_STATIC_GUARD,
    V3_STATUS_INVALID_OR_NOT_SUPPORTED,
    V3_STATUS_MANUAL_AUDIT_REQUIRED,
}

PRICE_ANOMALY_REASON_PREFIXES = ("price_", "missing_price", "invalid_price")
PRICE_ANOMALY_REASON_EXACT = {"price_floor", "low_price", "missing_price", "invalid_price"}


class QualityMetricsService:
    """Service for aggregating and querying data quality metrics."""

    @staticmethod
    def record_metric(
        metric_date: date,
        metric_hour: int,
        metric_key: str,
        metric_value: Decimal | float,
        category_id: str | UUID | None = None,
        task_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DataQualityMetric:
        """Record or update an hourly data quality metric."""
        resolved_category_id = _normalize_category_id(category_id)
        with session_scope() as session:
            metric = _find_existing_metric(
                session=session,
                metric_date=metric_date,
                metric_hour=metric_hour,
                metric_key=metric_key,
                category_id=resolved_category_id,
                task_key=task_key,
            )
            if metric is None:
                metric = DataQualityMetric(
                    metric_date=metric_date,
                    metric_hour=metric_hour,
                    metric_key=metric_key,
                    metric_value=Decimal(str(metric_value)),
                    category_id=resolved_category_id,
                    task_key=task_key,
                    metadata_json=metadata or {},
                )
                session.add(metric)
            else:
                metric.metric_value = Decimal(str(metric_value))
                metric.metadata_json = metadata or {}
            session.flush()
            return metric

    @staticmethod
    def get_latest_metrics(
        metric_key: str,
        limit: int = 24,
        category_id: str | None = None,
        task_key: str | None = None,
    ) -> list[DataQualityMetric]:
        """Get latest metrics for a given key."""
        with session_scope() as session:
            query = select(DataQualityMetric).where(
                DataQualityMetric.metric_key == metric_key
            )

            if category_id:
                query = query.where(DataQualityMetric.category_id == category_id)
            if task_key:
                query = query.where(DataQualityMetric.task_key == task_key)

            query = query.order_by(
                DataQualityMetric.metric_date.desc(),
                DataQualityMetric.metric_hour.desc(),
            ).limit(limit)

            return session.execute(query).scalars().all()

    @staticmethod
    def get_metric_summary(
        metric_key: str,
        days: int = 7,
        category_id: str | None = None,
        task_key: str | None = None,
    ) -> dict[str, Any]:
        """Get summary statistics for a metric over a period."""
        with session_scope() as session:
            cutoff_date = date.today() - timedelta(days=days)

            query = select(
                func.avg(DataQualityMetric.metric_value).label("avg_value"),
                func.min(DataQualityMetric.metric_value).label("min_value"),
                func.max(DataQualityMetric.metric_value).label("max_value"),
                func.count(DataQualityMetric.id).label("count"),
            ).where(
                and_(
                    DataQualityMetric.metric_key == metric_key,
                    DataQualityMetric.metric_date >= cutoff_date,
                )
            )

            if category_id:
                query = query.where(DataQualityMetric.category_id == category_id)
            if task_key:
                query = query.where(DataQualityMetric.task_key == task_key)

            result = session.execute(query).first()

            return {
                "metric_key": metric_key,
                "period_days": days,
                "avg_value": _decimal_to_float(result.avg_value),
                "min_value": _decimal_to_float(result.min_value),
                "max_value": _decimal_to_float(result.max_value),
                "sample_count": result.count or 0,
            }

    @staticmethod
    def get_baseline_window(
        metric_key: str,
        days: int = 7,
    ) -> dict[str, Any]:
        """Get baseline metrics for a 7-day window (for Phase 1 baseline freeze)."""
        return QualityMetricsService.get_metric_summary(
            metric_key=metric_key,
            days=days,
        )

    @staticmethod
    def refresh_operational_quality_metrics(
        *,
        metric_date: date | None = None,
        metric_hour: int | None = None,
        window_hours: int = 24,
        business_domain: str | None = None,
        category_id: str | UUID | None = None,
        task_key: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Refresh W8 operational metrics that are derived from existing tables."""
        now = datetime.now(UTC)
        resolved_metric_date = metric_date or now.date()
        resolved_metric_hour = metric_hour if metric_hour is not None else now.hour
        return {
            "review_pass_rate": QualityMetricsService.record_recent_review_pass_rate(
                metric_date=resolved_metric_date,
                metric_hour=resolved_metric_hour,
                window_hours=window_hours,
                business_domain=business_domain,
                category_id=category_id,
                task_key=task_key,
            ),
            "price_anomaly_rate": QualityMetricsService.record_recent_price_anomaly_rate(
                metric_date=resolved_metric_date,
                metric_hour=resolved_metric_hour,
                window_hours=window_hours,
                business_domain=business_domain,
                category_id=category_id,
                task_key=task_key,
            ),
        }

    @staticmethod
    def record_recent_review_pass_rate(
        *,
        metric_date: date,
        metric_hour: int,
        window_hours: int = 24,
        business_domain: str | None = None,
        category_id: str | UUID | None = None,
        task_key: str | None = None,
    ) -> dict[str, Any]:
        """Record Review V3 pass rate for terminal reviews in the recent window."""
        cutoff = datetime.now(UTC) - timedelta(hours=max(window_hours, 1))
        resolved_category_id = _normalize_category_id(category_id)
        with session_scope() as session:
            base_query = select(ItemReviewV3.resolution_status).where(
                ItemReviewV3.updated_at >= cutoff,
                ItemReviewV3.resolution_status != V3_STATUS_PENDING_REVIEW,
            )
            if resolved_category_id is not None:
                base_query = base_query.where(ItemReviewV3.category_id == str(resolved_category_id))
            if business_domain:
                base_query = base_query.where(ItemReviewV3.business_domain == business_domain)
            rows = [str(row or "").strip().upper() for row in session.execute(base_query).scalars()]

        stats = build_review_pass_rate_stats(rows)
        if stats["terminal_count"] <= 0:
            return {"recorded": False, **stats, "window_hours": window_hours}

        QualityMetricsService.record_metric(
            metric_date=metric_date,
            metric_hour=metric_hour,
            metric_key="review_pass_rate",
            metric_value=stats["pass_rate"],
            category_id=resolved_category_id,
            task_key=task_key,
            metadata={
                **stats,
                "window_hours": window_hours,
                "business_domain": business_domain,
                "terminal_statuses": sorted(REVIEW_V3_TERMINAL_STATUSES),
            },
        )
        return {"recorded": True, **stats, "window_hours": window_hours, "business_domain": business_domain}

    @staticmethod
    def record_recent_price_anomaly_rate(
        *,
        metric_date: date,
        metric_hour: int,
        window_hours: int = 24,
        business_domain: str | None = None,
        category_id: str | UUID | None = None,
        task_key: str | None = None,
    ) -> dict[str, Any]:
        """Record price anomaly rate from recent collection AnalysisReport payloads."""
        cutoff = datetime.now(UTC) - timedelta(hours=max(window_hours, 1))
        resolved_category_id = _normalize_category_id(category_id)
        with session_scope() as session:
            query = select(AnalysisReport.payload).where(
                AnalysisReport.created_at >= cutoff,
                AnalysisReport.report_type == "live_search_capture",
            )
            if resolved_category_id is not None:
                query = query.where(AnalysisReport.category_id == str(resolved_category_id))
            if business_domain:
                query = query.where(AnalysisReport.business_domain == business_domain)
            payloads = list(session.execute(query).scalars())

        payloads = [payload for payload in payloads if isinstance(payload, dict)]
        if task_key:
            payloads = [payload for payload in payloads if str(payload.get("task_key") or "") == task_key]

        stats = build_price_anomaly_rate_stats(payloads)
        if stats["observed_count"] <= 0:
            return {"recorded": False, **stats, "window_hours": window_hours}

        QualityMetricsService.record_metric(
            metric_date=metric_date,
            metric_hour=metric_hour,
            metric_key="price_anomaly_rate",
            metric_value=stats["anomaly_rate"],
            category_id=resolved_category_id,
            task_key=task_key,
            metadata={
                **stats,
                "window_hours": window_hours,
                "business_domain": business_domain,
                "task_key": task_key,
            },
        )
        return {"recorded": True, **stats, "window_hours": window_hours, "business_domain": business_domain}


def build_review_pass_rate_stats(resolution_statuses: list[str]) -> dict[str, Any]:
    terminal_statuses = [
        status
        for status in (str(value or "").strip().upper() for value in resolution_statuses)
        if status in REVIEW_V3_TERMINAL_STATUSES
    ]
    pass_count = sum(1 for status in terminal_statuses if status == V3_STATUS_VALID_READY_FOR_PRICING)
    terminal_count = len(terminal_statuses)
    return {
        "pass_count": pass_count,
        "terminal_count": terminal_count,
        "pass_rate": (pass_count / terminal_count) if terminal_count else 0.0,
    }


def build_price_anomaly_rate_stats(report_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    item_count = 0
    missing_price_count = 0
    rejected_low_price_count = 0
    category_price_floor_count = 0

    for payload in report_payloads:
        if not isinstance(payload, dict):
            continue
        item_count += _coerce_int(payload.get("item_count"))
        missing_price_count += _coerce_int(payload.get("rejected_missing_price_count"))
        rejected_low_price_count += _coerce_int(payload.get("rejected_low_price_count"))
        category_price_floor_count += _count_price_anomaly_reasons(
            payload.get("category_gate_blocked_reasons")
        )

    anomaly_count = missing_price_count + rejected_low_price_count + category_price_floor_count
    observed_count = item_count + anomaly_count
    return {
        "item_count": item_count,
        "missing_price_count": missing_price_count,
        "rejected_low_price_count": rejected_low_price_count,
        "category_price_floor_count": category_price_floor_count,
        "anomaly_count": anomaly_count,
        "observed_count": observed_count,
        "anomaly_rate": (anomaly_count / observed_count) if observed_count else 0.0,
    }


def _count_price_anomaly_reasons(raw_reasons: Any) -> int:
    if not isinstance(raw_reasons, dict):
        return 0
    count = 0
    for raw_reason, raw_count in raw_reasons.items():
        reason = str(raw_reason or "").strip().lower()
        if reason in PRICE_ANOMALY_REASON_EXACT or reason.startswith(PRICE_ANOMALY_REASON_PREFIXES):
            count += _coerce_int(raw_count)
    return count


def _coerce_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _decimal_to_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _normalize_category_id(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _find_existing_metric(
    *,
    session,
    metric_date: date,
    metric_hour: int,
    metric_key: str,
    category_id: UUID | None,
    task_key: str | None,
) -> DataQualityMetric | None:
    query = select(DataQualityMetric).where(
        DataQualityMetric.metric_date == metric_date,
        DataQualityMetric.metric_hour == metric_hour,
        DataQualityMetric.metric_key == metric_key,
    )
    if category_id is None:
        query = query.where(DataQualityMetric.category_id.is_(None))
    else:
        query = query.where(DataQualityMetric.category_id == category_id)
    if task_key is None:
        query = query.where(DataQualityMetric.task_key.is_(None))
    else:
        query = query.where(DataQualityMetric.task_key == task_key)
    return session.execute(query.limit(1)).scalar_one_or_none()
