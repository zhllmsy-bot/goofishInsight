from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select

from goofish_analyzer.adapters import session_scope, AnalysisReport, DailyMetric, ModelScore

REPORT_TYPE_MARKET_DAILY_SUMMARY = "market_daily_summary"


@dataclass(slots=True)
class AnalysisReportPayload:
    business_domain: str | None
    category_id: str | None
    title: str
    summary: str
    payload: dict[str, Any]


def _decimal_to_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    return str(value)


def _score_to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _scope_key(domain: str | None, category_id: str | None) -> tuple[str | None, str | None]:
    return (str(domain or "").strip() or None, str(category_id or "").strip() or None)


def _build_analysis_report_payloads(
    *,
    report_date: date,
    daily_metrics: list[Any],
    model_scores: list[Any],
) -> list[AnalysisReportPayload]:
    buckets: dict[tuple[str | None, str | None], dict[str, list[Any]]] = defaultdict(
        lambda: {"daily_metrics": [], "model_scores": []}
    )

    for metric in daily_metrics:
        buckets[_scope_key(getattr(metric, "business_domain", None), getattr(metric, "category_id", None))][
            "daily_metrics"
        ].append(metric)
    for score in model_scores:
        buckets[_scope_key(getattr(score, "business_domain", None), getattr(score, "category_id", None))][
            "model_scores"
        ].append(score)

    reports: list[AnalysisReportPayload] = []
    for (business_domain, category_id), bucket in sorted(
        buckets.items(),
        key=lambda item: (str(item[0][0] or ""), str(item[0][1] or "")),
    ):
        metric_rows = bucket["daily_metrics"]
        score_rows = sorted(
            bucket["model_scores"],
            key=lambda row: _score_to_decimal(getattr(row, "selection_score", None)),
            reverse=True,
        )
        total_listing_count = sum(int(getattr(row, "listing_count", 0) or 0) for row in metric_rows)
        total_seller_count = sum(int(getattr(row, "unique_seller_count", 0) or 0) for row in metric_rows)
        top_models = [
            {
                "normalized_model": getattr(row, "normalized_model", None),
                "normalized_model_family": getattr(row, "normalized_model_family", None),
                "model_catalog_id": getattr(row, "model_catalog_id", None),
                "selection_score": _decimal_to_text(getattr(row, "selection_score", None)),
                "liquidity_score": _decimal_to_text(getattr(row, "liquidity_score", None)),
                "profit_potential_score": _decimal_to_text(getattr(row, "profit_potential_score", None)),
                "score_reason": getattr(row, "score_reason", {}) or {},
            }
            for row in score_rows[:5]
        ]
        top_model_name = top_models[0]["normalized_model"] if top_models else "暂无"
        scope_label = business_domain or "全域"
        if category_id:
            scope_label = f"{scope_label}/{category_id}"
        title = f"{report_date.isoformat()} {scope_label} 市场日报"
        summary = (
            f"{scope_label} 当日活跃商品 {total_listing_count} 个，"
            f"卖家样本 {total_seller_count} 个，Top 机会型号：{top_model_name}。"
        )
        reports.append(
            AnalysisReportPayload(
                business_domain=business_domain,
                category_id=category_id,
                title=title,
                summary=summary,
                payload={
                    "report_date": report_date.isoformat(),
                    "report_type": REPORT_TYPE_MARKET_DAILY_SUMMARY,
                    "business_domain": business_domain,
                    "category_id": category_id,
                    "daily_metric_count": len(metric_rows),
                    "model_score_count": len(score_rows),
                    "total_listing_count": total_listing_count,
                    "total_unique_seller_count": total_seller_count,
                    "top_models": top_models,
                    "source_path": "daily_metrics+model_scores",
                    "generated_at": datetime.now(UTC).isoformat(),
                },
            )
        )
    return reports


def build_analysis_reports(
    *,
    report_date: date,
    business_domain: str | None = None,
    category_id: str | None = None,
    source_mode: str = "legacy_items",
    replace_existing: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        metric_query = select(DailyMetric).where(DailyMetric.metric_date == report_date)
        score_query = select(ModelScore).where(ModelScore.score_date == report_date)
        if business_domain:
            metric_query = metric_query.where(DailyMetric.business_domain == business_domain)
            score_query = score_query.where(ModelScore.business_domain == business_domain)
        if category_id:
            metric_query = metric_query.where(DailyMetric.category_id == category_id)
            score_query = score_query.where(ModelScore.category_id == category_id)

        daily_metrics = list(session.execute(metric_query).scalars().all())
        model_scores = list(session.execute(score_query).scalars().all())
        reports = _build_analysis_report_payloads(
            report_date=report_date,
            daily_metrics=daily_metrics,
            model_scores=model_scores,
        )

        deleted_count = 0
        if replace_existing and not dry_run:
            delete_stmt = delete(AnalysisReport).where(
                AnalysisReport.report_date == report_date,
                AnalysisReport.report_type == REPORT_TYPE_MARKET_DAILY_SUMMARY,
            )
            if business_domain:
                delete_stmt = delete_stmt.where(AnalysisReport.business_domain == business_domain)
            if category_id:
                delete_stmt = delete_stmt.where(AnalysisReport.category_id == category_id)
            deleted_count = int(session.execute(delete_stmt).rowcount or 0)

        if not dry_run:
            for report in reports:
                session.add(
                    AnalysisReport(
                        report_type=REPORT_TYPE_MARKET_DAILY_SUMMARY,
                        business_domain=report.business_domain,
                        category_id=report.category_id,
                        template_id=None,
                        report_date=report_date,
                        title=report.title,
                        summary=report.summary,
                        payload=report.payload,
                    )
                )

    return {
        "report_date": report_date.isoformat(),
        "report_type": REPORT_TYPE_MARKET_DAILY_SUMMARY,
        "report_count": len(reports),
        "deleted_count": deleted_count,
        "business_domain": business_domain,
        "category_id": category_id,
        "dry_run": dry_run,
        "source_path": "daily_metrics+model_scores",
        "source_mode": source_mode,
    }
