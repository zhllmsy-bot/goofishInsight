from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from goofish_analyzer.adapters import (
    resolve_category_code,
    normalize_opportunity_status,
    serialize_pricing_record,
    BuyAlertEvent,
    BuyDecisionFeedback,
    BuyOpportunity,
    BuyOpportunityRisk,
    BuyPriceBaseline,
    BuyWatchTarget,
    Category,
    Item,
)
from goofish_analyzer.services.buy_alerts import (
    serialize_buy_alert_event,
    summarize_buy_alert_hit_rate_with_session,
    link_buy_feedback_to_alert_candidate_with_session,
)
from goofish_analyzer.services.buy_feedback import (
    apply_buy_feedback_calibration,
    apply_buy_feedback_calibration_with_session,
    record_buy_decision_feedback,
    record_buy_decision_feedback_with_session,
    serialize_buy_decision_feedback,
    summarize_buy_feedback_calibration,
    summarize_buy_feedback_calibration_with_session,
    summarize_buy_feedback_quality,
    summarize_buy_feedback_quality_with_session,
)
from goofish_analyzer.services.buy_opportunities import (
    refresh_buy_opportunities,
    refresh_buy_opportunities_with_session,
)
from goofish_analyzer.services.pricing_explanations import (
    build_buy_opportunity_explanation,
    build_buy_price_baseline_explanation,
)
from goofish_analyzer.services.buy_template_monitoring import (
    summarize_template_availability_monitoring,
    summarize_template_availability_monitoring_with_session,
)

CONTACT_OUTCOME_FEEDBACK_LABELS = {
    "contacted",
    "messaged",
    "已联系",
}

OPEN_OUTCOME_FEEDBACK_LABELS = {
    "detail_opened",
    "listing_opened",
}

PURCHASE_OUTCOME_FEEDBACK_LABELS = {
    "purchased",
    "bought",
    "成交",
    "已买",
}

VALUE_OPEN_FEEDBACK_LABELS = tuple(sorted(OPEN_OUTCOME_FEEDBACK_LABELS))
VALUE_CONTACT_FEEDBACK_LABELS = tuple(sorted(CONTACT_OUTCOME_FEEDBACK_LABELS))
VALUE_PURCHASE_FEEDBACK_LABELS = tuple(sorted(PURCHASE_OUTCOME_FEEDBACK_LABELS))

DAILY_OPPORTUNITY_TARGET_COUNT = 20
DAILY_OPPORTUNITY_GROUP_SPECS = (
    (
        "act_now",
        "立即看",
        "今天先打开原始商品，确认实物、卖家和可交易性，再标记已联系或不值得。",
    ),
    (
        "negotiate",
        "可砍价",
        "用公平价和买入线上限做议价锚点，优先验证卖家是否接受目标买入价。",
    ),
    (
        "needs_review",
        "需复核",
        "机会分可能很高，但标题、风险分或基线状态需要先人工排雷。",
    ),
)
DAILY_REVIEW_KEYWORDS = (
    ("mdm", "MDM/监管风险"),
    ("监管", "监管/企业机风险"),
    ("企业机", "监管/企业机风险"),
    ("资源机", "资源机风险"),
    ("id锁", "账号锁风险"),
    ("有锁", "账号锁风险"),
    ("网络锁", "账号锁风险"),
    ("丢失模式", "账号锁风险"),
    ("扩容", "改装/扩容风险"),
    ("改码", "改装/改码风险"),
    ("维修", "维修史风险"),
    ("进水", "进水风险"),
    ("换屏", "维修/换屏风险"),
    ("官换", "官换/翻新需核验"),
    ("翻新", "翻新需核验"),
    ("展示机", "展示机需核验"),
    ("样机", "样机需核验"),
    ("置换", "置换交易需核验"),
    ("单主板", "非整机/配件风险"),
    ("仅配件", "非整机/配件风险"),
)


def build_buy_opportunity_workbench(
    session: Session,
    *,
    category_code: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    category = _resolve_optional_category(session, category_code=category_code)
    opportunity_stmt = (
        select(BuyOpportunity)
        .order_by(BuyOpportunity.opportunity_score.desc(), BuyOpportunity.last_detected_at.desc())
        .limit(max(int(limit), 1))
    )
    baseline_stmt = select(BuyPriceBaseline).order_by(
        BuyPriceBaseline.baseline_date.desc(),
        BuyPriceBaseline.baseline_key.asc(),
    ).limit(30)
    target_stmt = select(BuyWatchTarget).order_by(BuyWatchTarget.target_name.asc()).limit(30)
    if category is not None:
        category_id = str(category.id)
        opportunity_stmt = opportunity_stmt.where(BuyOpportunity.category_id == category_id)
        baseline_stmt = baseline_stmt.where(BuyPriceBaseline.category_id == category_id)
        target_stmt = target_stmt.where(BuyWatchTarget.category_id == category_id)

    opportunities = list(session.execute(opportunity_stmt).scalars().all())
    baselines = list(session.execute(baseline_stmt).scalars().all())
    targets = list(session.execute(target_stmt).scalars().all())
    serialized_opportunities = [serialize_buy_workbench_opportunity(row) for row in opportunities]
    serialized_baselines = [serialize_buy_workbench_baseline(row) for row in baselines]
    hit_rate = summarize_buy_alert_hit_rate_with_session(
        session,
        category_code=category.code if category is not None else None,
    )
    feedback_quality = summarize_buy_feedback_quality_with_session(
        session,
        category_code=category.code if category is not None else None,
        window_days=30,
    )
    feedback_calibration = summarize_buy_feedback_calibration_with_session(
        session,
        category_code=category.code if category is not None else None,
        window_days=30,
    )
    outcome_funnel = summarize_buy_outcome_funnel_with_session(
        session,
        category=category,
    )
    recommendation_count = int(
        dict(feedback_calibration.get("recommendations") or {}).get("totalRecommendationCount") or 0
    )
    category_id = str(category.id) if category is not None else None
    today_opportunity_count = _count_buy_opportunities_opened_since(
        session=session,
        category_id=category_id,
        since_seconds=_today_opportunity_window_seconds(),
    )
    data_value = build_buy_data_value_report_with_session(
        session,
        category_code=category.code if category is not None else None,
    )
    return {
        "categoryCode": category.code if category is not None else None,
        "summary": {
            "opportunityCount": len(opportunities),
            "baselineCount": len(baselines),
            "watchTargetCount": len(targets),
            "todayOpportunityCount": today_opportunity_count,
            "alertHitRate": hit_rate.get("hitRate", 0.0),
            "alertCount": hit_rate.get("alertCount", 0),
            "alertHitCount": hit_rate.get("hitCount", 0),
            "feedbackCount": feedback_quality.get("feedbackCount", 0),
            "acceptCount": feedback_quality.get("acceptCount", 0),
            "rejectCount": feedback_quality.get("rejectCount", 0),
            "calibrationRecommendationCount": recommendation_count,
        },
        "dataValue": data_value,
        "dailyOpportunityPack": build_daily_opportunity_pack(
            opportunities=serialized_opportunities,
            baselines=serialized_baselines,
            data_value=data_value,
            target_count=DAILY_OPPORTUNITY_TARGET_COUNT,
        ),
        "outcomeFunnel": outcome_funnel,
        "feedbackQuality": feedback_quality,
        "feedbackCalibration": feedback_calibration,
        "opportunities": serialized_opportunities,
        "baselines": serialized_baselines,
        "watchTargets": [serialize_buy_workbench_target(row) for row in targets],
    }


def build_buy_data_value_report_with_session(
    session: Session,
    *,
    category_code: str | None = None,
) -> dict[str, Any]:
    """Summarize whether collected market data is converting into business proof."""

    normalized_category_code = resolve_category_code(category_code) if _normalize_optional_string(category_code) else None
    params = {
        "category_code": normalized_category_code,
        "open_labels": list(VALUE_OPEN_FEEDBACK_LABELS),
        "contact_labels": list(VALUE_CONTACT_FEEDBACK_LABELS),
        "purchase_labels": list(VALUE_PURCHASE_FEEDBACK_LABELS),
    }
    overall = _one_mapping(
        session,
        """
        select
          (
            select count(*) from items i
            where (cast(:category_code as text) is null or i.business_domain = :category_code)
          ) as item_count,
          (
            select count(*) from items i
            where (cast(:category_code as text) is null or i.business_domain = :category_code) and i.is_active
          ) as active_item_count,
          (
            select count(*) from items i
            where (cast(:category_code as text) is null or i.business_domain = :category_code) and i.current_price is not null
          ) as priced_item_count,
          (
            select count(*) from item_snapshots s
            join items i on i.id = s.item_id_ref
            where (cast(:category_code as text) is null or i.business_domain = :category_code)
          ) as snapshot_count,
          (
            select count(*) from item_ingest_rejection r
            where (cast(:category_code as text) is null or r.business_domain = :category_code)
          ) as rejection_count,
          (
            select count(distinct e.item_id_ref) from item_spec_enrichments e
            where (cast(:category_code as text) is null or e.business_domain = :category_code)
          ) as spec_item_count,
          (
            select count(distinct e.item_id_ref) from item_spec_enrichments e
            where (cast(:category_code as text) is null or e.business_domain = :category_code)
              and e.status = 'complete'
          ) as complete_spec_item_count,
          (
            select count(*) from buy_price_baseline b
            left join category c on c.id = b.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
          ) as baseline_count,
          (
            select max(b.baseline_date) from buy_price_baseline b
            left join category c on c.id = b.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
          ) as latest_baseline_date,
          (
            select count(*) from buy_price_baseline b
            left join category c on c.id = b.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
              and b.baseline_date = (
                select max(b2.baseline_date)
                from buy_price_baseline b2
                left join category c2 on c2.id = b2.category_id
                where (cast(:category_code as text) is null or c2.code = :category_code)
              )
          ) as latest_baseline_count,
          (
            select count(*) from buy_opportunity o
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
          ) as opportunity_count,
          (
            select count(*) from buy_opportunity o
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
              and o.status = 'OPEN'
          ) as open_opportunity_count,
          (
            select count(*) from buy_opportunity o
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
              and coalesce(o.payload->>'templateAvailabilityTier', 'unknown') = 'guidance_ready'
          ) as guidance_ready_opportunity_count,
          (
            select count(*) from buy_opportunity o
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
              and coalesce(o.payload->>'templateAvailabilityTier', 'unknown') in ('blocked', 'reference_only')
          ) as reference_limited_opportunity_count,
          (
            select count(*) from buy_alert_event a
            join buy_opportunity o on o.id = a.opportunity_id
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
          ) as alert_event_count,
          (
            select count(distinct a.opportunity_id) from buy_alert_event a
            join buy_opportunity o on o.id = a.opportunity_id
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
          ) as alerted_opportunity_count,
          (
            select count(*) from buy_decision_feedback f
            join buy_opportunity o on o.id = f.opportunity_id
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
          ) as feedback_count,
          (
            select count(distinct f.opportunity_id) from buy_decision_feedback f
            join buy_opportunity o on o.id = f.opportunity_id
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
              and lower(replace(replace(f.feedback_label, '-', '_'), ' ', '_')) = any(:open_labels)
          ) as opened_opportunity_count,
          (
            select count(distinct f.opportunity_id) from buy_decision_feedback f
            join buy_opportunity o on o.id = f.opportunity_id
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
              and lower(replace(replace(f.feedback_label, '-', '_'), ' ', '_')) = any(:contact_labels)
          ) as contacted_opportunity_count,
          (
            select count(distinct f.opportunity_id) from buy_decision_feedback f
            join buy_opportunity o on o.id = f.opportunity_id
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
              and lower(replace(replace(f.feedback_label, '-', '_'), ' ', '_')) = any(:purchase_labels)
          ) as purchased_opportunity_count,
          (
            select count(distinct f.opportunity_id) from buy_decision_feedback f
            join buy_opportunity o on o.id = f.opportunity_id
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
              and lower(replace(replace(f.feedback_label, '-', '_'), ' ', '_')) = any(:purchase_labels)
              and f.purchase_price is not null
              and f.expected_resale_price is not null
              and f.purchase_price > 0
          ) as roi_evidence_count,
          (
            select max(i.last_seen_at) from items i
            where (cast(:category_code as text) is null or i.business_domain = :category_code)
          ) as latest_item_seen_at,
          (
            select max(s.snapshot_at) from item_snapshots s
            join items i on i.id = s.item_id_ref
            where (cast(:category_code as text) is null or i.business_domain = :category_code)
          ) as latest_snapshot_at,
          (
            select max(o.last_detected_at) from buy_opportunity o
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
          ) as latest_opportunity_detected_at,
          (
            select max(f.created_at) from buy_decision_feedback f
            join buy_opportunity o on o.id = f.opportunity_id
            left join category c on c.id = o.category_id
            where (cast(:category_code as text) is null or c.code = :category_code)
          ) as latest_feedback_at
        """,
        params,
    )
    category_breakdown = _build_data_value_category_breakdown(session, category_code=normalized_category_code)
    summary = _build_data_value_summary(overall)
    diagnosis = _build_data_value_diagnosis(summary)
    stages = _build_data_value_stages(summary)
    return {
        "categoryCode": normalized_category_code,
        "generatedAt": datetime.now(UTC).isoformat(),
        "summary": summary,
        "diagnosis": diagnosis,
        "stages": stages,
        "categoryBreakdown": category_breakdown,
        "recommendations": _build_data_value_recommendations(summary, diagnosis),
    }


def build_daily_opportunity_pack(
    *,
    opportunities: list[Mapping[str, Any]],
    baselines: list[Mapping[str, Any]],
    data_value: Mapping[str, Any] | None = None,
    target_count: int = DAILY_OPPORTUNITY_TARGET_COUNT,
) -> dict[str, Any]:
    """Turn the OPEN backlog into a small daily operating queue."""

    summary = dict((data_value or {}).get("summary") or {})
    open_backlog_count = _to_int(summary.get("openOpportunityCount")) or len(
        [row for row in opportunities if _is_open_opportunity(row)]
    )
    normalized_target_count = max(int(target_count), 1)
    selected_ids: set[str] = set()
    groups = []
    for key, label, recommended_action in DAILY_OPPORTUNITY_GROUP_SPECS:
        tasks = _select_daily_opportunity_tasks(
            opportunities=opportunities,
            selected_ids=selected_ids,
            group_key=key,
            group_label=label,
            recommended_action=recommended_action,
            remaining_limit=max(normalized_target_count - len(selected_ids), 0),
        )
        selected_ids.update(str(task["opportunity"]["id"]) for task in tasks)
        groups.append(
            {
                "key": key,
                "label": label,
                "recommendedAction": recommended_action,
                "count": len(tasks),
                "tasks": tasks,
            }
        )

    market_intel = _build_daily_market_intel(baselines)
    pack_count = len(selected_ids)
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "summary": {
            "targetProcessingCount": min(normalized_target_count, open_backlog_count),
            "packOpportunityCount": pack_count,
            "openBacklogCount": open_backlog_count,
            "ungroupedOpenCount": max(open_backlog_count - pack_count, 0),
            "feedbackCount": _to_int(summary.get("feedbackCount")),
            "contactedOpportunityCount": _to_int(summary.get("contactedOpportunityCount")),
            "purchasedOpportunityCount": _to_int(summary.get("purchasedOpportunityCount")),
            "roiEvidenceCount": _to_int(summary.get("roiEvidenceCount")),
            "feedbackCoverageRate": _to_float(summary.get("feedbackCoverageRate")),
            "operatingMode": "opportunity_digest_first",
            "northStar": "把 OPEN 机会消化成反馈、联系、成交和 ROI 证据",
        },
        "groups": groups,
        "marketIntel": market_intel,
    }


def _select_daily_opportunity_tasks(
    *,
    opportunities: list[Mapping[str, Any]],
    selected_ids: set[str],
    group_key: str,
    group_label: str,
    recommended_action: str,
    remaining_limit: int,
) -> list[dict[str, Any]]:
    if remaining_limit <= 0:
        return []
    candidates = [
        row
        for row in opportunities
        if _is_open_opportunity(row)
        and _normalize_optional_string(row.get("id")) not in selected_ids
        and _daily_group_matches(row, group_key=group_key)
    ]
    tasks = []
    for index, opportunity in enumerate(sorted(candidates, key=_daily_opportunity_sort_key)[:remaining_limit], start=1):
        tasks.append(
            {
                "rank": index,
                "groupKey": group_key,
                "groupLabel": group_label,
                "recommendedAction": recommended_action,
                "reason": _build_daily_task_reason(opportunity, group_key=group_key),
                "slaLabel": _build_daily_task_sla_label(group_key),
                "riskFlags": _daily_risk_flags(opportunity),
                "valueSignals": _daily_value_signals(opportunity),
                "opportunity": dict(opportunity),
            }
        )
    return tasks


def _daily_group_matches(row: Mapping[str, Any], *, group_key: str) -> bool:
    risk_flags = _daily_risk_flags(row)
    risk_score = _to_float(row.get("riskScore"))
    opportunity_score = _to_float(row.get("opportunityScore"))
    if group_key == "act_now":
        return (
            opportunity_score >= 60
            and risk_score <= 20
            and not risk_flags
            and _is_guidance_ready_opportunity(row)
        )
    if group_key == "negotiate":
        return (
            opportunity_score >= 50
            and risk_score <= 35
            and not risk_flags
            and _has_negotiation_signal(row)
        )
    if group_key == "needs_review":
        return bool(risk_flags) or risk_score > 35 or (
            opportunity_score >= 70 and not _is_guidance_ready_opportunity(row)
        )
    return False


def _build_daily_task_reason(row: Mapping[str, Any], *, group_key: str) -> str:
    signals = _daily_value_signals(row)
    risk_flags = _daily_risk_flags(row)
    if group_key == "needs_review" and risk_flags:
        return f"先复核：{'、'.join(risk_flags[:3])}。"
    if group_key == "negotiate":
        return "有低于买入线或折扣信号，适合用价格基线做议价锚点。"
    if signals:
        return " · ".join(signals[:3])
    return "OPEN 机会尚未形成反馈证据，今天应完成一次明确判断。"


def _build_daily_task_sla_label(group_key: str) -> str:
    if group_key == "act_now":
        return "今日必须给出联系/跳过判断"
    if group_key == "negotiate":
        return "今日至少完成一次议价判断"
    if group_key == "needs_review":
        return "先人工排雷，再决定是否联系"
    return "今日处理"


def _daily_opportunity_sort_key(row: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        -_to_float(row.get("opportunityScore")),
        _to_float(row.get("riskScore")),
        -_to_float(row.get("discountRate")),
    )


def _is_open_opportunity(row: Mapping[str, Any]) -> bool:
    return str(row.get("status") or "").upper() == "OPEN"


def _is_guidance_ready_opportunity(row: Mapping[str, Any]) -> bool:
    tier = _normalize_optional_string(row.get("templateAvailabilityTier"))
    if tier == "guidance_ready":
        return True
    if bool(row.get("exactSpecReady")):
        return True
    baseline_level = _normalize_optional_string(row.get("baselineMatchLevel"))
    if baseline_level in {"spec", "template", "product"}:
        return True
    spec_contract = dict(row.get("specContract") or {})
    return _normalize_optional_string(spec_contract.get("status")) == "complete"


def _has_negotiation_signal(row: Mapping[str, Any]) -> bool:
    current_price = _to_float(row.get("currentPrice"))
    buy_ceiling = _to_float(row.get("buyCeiling"))
    discount_rate = _to_float(row.get("discountRate"))
    if current_price > 0 and buy_ceiling > 0 and current_price <= buy_ceiling:
        return True
    return discount_rate >= 0.08


def _daily_risk_flags(row: Mapping[str, Any]) -> list[str]:
    flags = []
    title = str(row.get("title") or "").lower()
    for keyword, label in DAILY_REVIEW_KEYWORDS:
        if keyword.lower() in title and label not in flags:
            flags.append(label)
    risk_score = _to_float(row.get("riskScore"))
    if risk_score > 35:
        flags.append("风险分偏高")
    if not _is_guidance_ready_opportunity(row) and _to_float(row.get("opportunityScore")) >= 70:
        flags.append("基线不够细但机会分较高")
    return flags


def _daily_value_signals(row: Mapping[str, Any]) -> list[str]:
    signals = []
    opportunity_score = _to_float(row.get("opportunityScore"))
    risk_score = _to_float(row.get("riskScore"))
    current_price = _to_float(row.get("currentPrice"))
    fair_price = _to_float(row.get("fairPrice"))
    buy_ceiling = _to_float(row.get("buyCeiling"))
    discount_rate = _to_float(row.get("discountRate"))
    if opportunity_score > 0:
        signals.append(f"机会分 {opportunity_score:.1f}")
    if fair_price > 0 and current_price > 0 and current_price < fair_price:
        signals.append(f"低于公平价 {_format_money(fair_price - current_price)}")
    if buy_ceiling > 0 and current_price > 0 and current_price <= buy_ceiling:
        signals.append(f"低于买入线 {_format_money(buy_ceiling - current_price)}")
    if discount_rate > 0:
        signals.append(f"折扣 {discount_rate * 100:.1f}%")
    if risk_score > 0:
        signals.append(f"风险 {risk_score:.1f}")
    baseline_level = _normalize_optional_string(row.get("baselineMatchLevel"))
    if baseline_level:
        signals.append(f"基线 {baseline_level}")
    return signals


def _build_daily_market_intel(baselines: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        dict(row)
        for row in baselines
        if _to_int(row.get("sampleSize")) >= 10 and _to_float(row.get("confidence")) >= 0.7
    ]
    candidates.sort(key=lambda row: (-_to_float(row.get("confidence")), -_to_int(row.get("sampleSize"))))
    return [
        {
            "baselineKey": row.get("baselineKey"),
            "sampleSize": _to_int(row.get("sampleSize")),
            "fairPrice": _to_float(row.get("fairPrice")) or None,
            "buyCeiling": _to_float(row.get("buyCeiling")) or None,
            "confidence": _to_float(row.get("confidence")) or None,
            "reason": "可作为今日联系和议价的价格锚点。",
        }
        for row in candidates[:6]
    ]


def _format_money(value: float) -> str:
    if not value:
        return "¥0"
    return f"¥{value:,.0f}"


def _build_data_value_category_breakdown(
    session: Session,
    *,
    category_code: str | None,
) -> list[dict[str, Any]]:
    item_rows = _many_mappings(
        session,
        """
        select i.business_domain as category_code,
               count(*) as item_count,
               count(*) filter (where i.is_active) as active_item_count,
               count(*) filter (where i.current_price is not null) as priced_item_count,
               max(i.last_seen_at) as latest_item_seen_at
        from items i
        where (cast(:category_code as text) is null or i.business_domain = :category_code)
        group by i.business_domain
        """,
        {"category_code": category_code},
    )
    spec_rows = _many_mappings(
        session,
        """
        select e.business_domain as category_code,
               count(distinct e.item_id_ref) as spec_item_count,
               count(distinct e.item_id_ref) filter (where e.status = 'complete') as complete_spec_item_count
        from item_spec_enrichments e
        where (cast(:category_code as text) is null or e.business_domain = :category_code)
        group by e.business_domain
        """,
        {"category_code": category_code},
    )
    baseline_rows = _many_mappings(
        session,
        """
        select c.code as category_code,
               count(*) as baseline_count,
               max(b.baseline_date) as latest_baseline_date
        from buy_price_baseline b
        join category c on c.id = b.category_id
        where (cast(:category_code as text) is null or c.code = :category_code)
        group by c.code
        """,
        {"category_code": category_code},
    )
    opportunity_rows = _many_mappings(
        session,
        """
        select c.code as category_code,
               count(*) as opportunity_count,
               count(*) filter (where o.status = 'OPEN') as open_opportunity_count,
               count(*) filter (where coalesce(o.payload->>'templateAvailabilityTier', 'unknown') = 'guidance_ready') as guidance_ready_opportunity_count,
               max(o.last_detected_at) as latest_opportunity_detected_at
        from buy_opportunity o
        join category c on c.id = o.category_id
        where (cast(:category_code as text) is null or c.code = :category_code)
        group by c.code
        """,
        {"category_code": category_code},
    )
    alert_rows = _many_mappings(
        session,
        """
        select c.code as category_code,
               count(a.*) as alert_event_count,
               count(distinct a.opportunity_id) as alerted_opportunity_count
        from buy_alert_event a
        join buy_opportunity o on o.id = a.opportunity_id
        join category c on c.id = o.category_id
        where (cast(:category_code as text) is null or c.code = :category_code)
        group by c.code
        """,
        {"category_code": category_code},
    )
    feedback_rows = _many_mappings(
        session,
        """
        select c.code as category_code,
               count(*) as feedback_count,
               count(distinct f.opportunity_id) filter (
                 where lower(replace(replace(f.feedback_label, '-', '_'), ' ', '_')) = any(:purchase_labels)
               ) as purchased_opportunity_count,
               count(distinct f.opportunity_id) filter (
                 where lower(replace(replace(f.feedback_label, '-', '_'), ' ', '_')) = any(:purchase_labels)
                   and f.purchase_price is not null
                   and f.expected_resale_price is not null
                   and f.purchase_price > 0
               ) as roi_evidence_count
        from buy_decision_feedback f
        join buy_opportunity o on o.id = f.opportunity_id
        join category c on c.id = o.category_id
        where (cast(:category_code as text) is null or c.code = :category_code)
        group by c.code
        """,
        {
            "category_code": category_code,
            "purchase_labels": list(VALUE_PURCHASE_FEEDBACK_LABELS),
        },
    )
    by_code: dict[str, dict[str, Any]] = {}
    for row_set in (item_rows, spec_rows, baseline_rows, opportunity_rows, alert_rows, feedback_rows):
        for row in row_set:
            code = _normalize_optional_string(row.get("category_code"))
            if not code:
                continue
            target = by_code.setdefault(code, {"categoryCode": code})
            target.update(_camelize_mapping(row, exclude={"category_code"}))

    breakdown = []
    for payload in by_code.values():
        item_count = _to_int(payload.get("itemCount"))
        opportunity_count = _to_int(payload.get("opportunityCount"))
        feedback_count = _to_int(payload.get("feedbackCount"))
        payload["specCoverageRate"] = _safe_rate_float(_to_int(payload.get("specItemCount")), item_count)
        payload["completeSpecCoverageRate"] = _safe_rate_float(_to_int(payload.get("completeSpecItemCount")), item_count)
        payload["opportunityYieldRate"] = _safe_rate_float(opportunity_count, item_count)
        payload["feedbackCoverageRate"] = _safe_rate_float(feedback_count, opportunity_count)
        payload["purchaseProofRate"] = _safe_rate_float(_to_int(payload.get("purchasedOpportunityCount")), opportunity_count)
        payload["roiProofRate"] = _safe_rate_float(_to_int(payload.get("roiEvidenceCount")), _to_int(payload.get("purchasedOpportunityCount")))
        payload["utilizationScore"] = _data_value_score(
            spec_coverage=payload["specCoverageRate"],
            opportunity_yield=payload["opportunityYieldRate"],
            feedback_coverage=payload["feedbackCoverageRate"],
            purchase_proof=payload["purchaseProofRate"],
            roi_proof=payload["roiProofRate"],
        )
        breakdown.append(payload)
    return sorted(
        breakdown,
        key=lambda row: (_to_int(row.get("itemCount")), _to_int(row.get("opportunityCount"))),
        reverse=True,
    )


def _build_data_value_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    item_count = _to_int(row.get("item_count"))
    spec_item_count = _to_int(row.get("spec_item_count"))
    complete_spec_item_count = _to_int(row.get("complete_spec_item_count"))
    opportunity_count = _to_int(row.get("opportunity_count"))
    open_opportunity_count = _to_int(row.get("open_opportunity_count"))
    guidance_ready_count = _to_int(row.get("guidance_ready_opportunity_count"))
    alert_event_count = _to_int(row.get("alert_event_count"))
    alerted_opportunity_count = _to_int(row.get("alerted_opportunity_count"))
    feedback_count = _to_int(row.get("feedback_count"))
    purchased_count = _to_int(row.get("purchased_opportunity_count"))
    roi_count = _to_int(row.get("roi_evidence_count"))
    summary = _camelize_mapping(row)
    summary.update(
        {
            "itemCount": item_count,
            "specItemCount": spec_item_count,
            "completeSpecItemCount": complete_spec_item_count,
            "opportunityCount": opportunity_count,
            "openOpportunityCount": open_opportunity_count,
            "guidanceReadyOpportunityCount": guidance_ready_count,
            "alertEventCount": alert_event_count,
            "alertedOpportunityCount": alerted_opportunity_count,
            "feedbackCount": feedback_count,
            "purchasedOpportunityCount": purchased_count,
            "roiEvidenceCount": roi_count,
            "specCoverageRate": _safe_rate_float(spec_item_count, item_count),
            "completeSpecCoverageRate": _safe_rate_float(complete_spec_item_count, item_count),
            "opportunityYieldRate": _safe_rate_float(opportunity_count, item_count),
            "openOpportunityRate": _safe_rate_float(open_opportunity_count, opportunity_count),
            "guidanceReadyRate": _safe_rate_float(guidance_ready_count, opportunity_count),
            "alertCoverageRate": _safe_rate_float(alerted_opportunity_count, max(open_opportunity_count, 1)),
            "feedbackCoverageRate": _safe_rate_float(feedback_count, opportunity_count),
            "purchaseProofRate": _safe_rate_float(purchased_count, opportunity_count),
            "roiProofRate": _safe_rate_float(roi_count, purchased_count),
            "dataValueScore": _data_value_score(
                spec_coverage=_safe_rate_float(spec_item_count, item_count),
                opportunity_yield=_safe_rate_float(opportunity_count, item_count),
                feedback_coverage=_safe_rate_float(feedback_count, opportunity_count),
                purchase_proof=_safe_rate_float(purchased_count, opportunity_count),
                roi_proof=_safe_rate_float(roi_count, purchased_count),
            ),
        }
    )
    return summary


def _build_data_value_diagnosis(summary: Mapping[str, Any]) -> dict[str, Any]:
    if _to_int(summary.get("feedbackCount")) == 0:
        return {
            "stage": "value_unproven",
            "severity": "critical",
            "statusLabel": "资源消耗态",
            "summary": "数据已经能生成价格资产和机会资产，但没有任何人工反馈、成交或 ROI 证据，业务价值尚未被证明。",
            "nextBestAction": "暂停扩品类采集，把 OPEN 机会转成人工判断、联系、成交与 ROI 证据。",
        }
    if _to_int(summary.get("purchasedOpportunityCount")) == 0:
        return {
            "stage": "decision_loop_unproven",
            "severity": "high",
            "statusLabel": "决策未兑现",
            "summary": "系统已经获得反馈，但还没有成交证明，暂时只能证明有人看过机会，不能证明机会能赚钱。",
            "nextBestAction": "围绕最高分 OPEN 机会建立每日成交实验，并记录买入价与预期转售价。",
        }
    if _to_int(summary.get("roiEvidenceCount")) == 0:
        return {
            "stage": "roi_missing",
            "severity": "high",
            "statusLabel": "ROI 缺证据",
            "summary": "已有成交信号，但缺少买入价/转售价字段，无法计算收益质量。",
            "nextBestAction": "成交反馈必须强制记录 purchasePrice 与 expectedResalePrice。",
        }
    return {
        "stage": "value_loop_learning",
        "severity": "medium",
        "statusLabel": "价值闭环学习中",
        "summary": "系统已经具备从数据到成交/ROI 的证据链，下一步应把反馈反哺到基线和机会排序。",
        "nextBestAction": "用成交 ROI 和拒绝原因校准买入线、风险权重和提醒阈值。",
    }


def _build_data_value_stages(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    stage_specs = [
        ("inventory", "有效商品库存", "pricedItemCount", "itemCount"),
        ("structured", "结构化规格", "specItemCount", "pricedItemCount"),
        ("baseline", "价格基线", "latestBaselineCount", "specItemCount"),
        ("opportunity", "机会池", "opportunityCount", "pricedItemCount"),
        ("open", "可行动机会", "openOpportunityCount", "opportunityCount"),
        ("alert", "已提醒机会", "alertedOpportunityCount", "openOpportunityCount"),
        ("feedback", "人工反馈", "feedbackCount", "opportunityCount"),
        ("purchase", "成交证明", "purchasedOpportunityCount", "opportunityCount"),
        ("roi", "ROI 证据", "roiEvidenceCount", "purchasedOpportunityCount"),
    ]
    stages = []
    for key, label, count_key, denominator_key in stage_specs:
        count = _to_int(summary.get(count_key))
        denominator = _to_int(summary.get(denominator_key))
        stages.append(
            {
                "key": key,
                "label": label,
                "count": count,
                "denominator": denominator,
                "conversionRate": _safe_rate_float(count, denominator),
                "leakageCount": max(denominator - count, 0),
            }
        )
    return stages


def _build_data_value_recommendations(
    summary: Mapping[str, Any],
    diagnosis: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "P0",
            "title": "从采集优先切换到机会消化优先",
            "reason": f"当前 OPEN 机会有 {_to_int(summary.get('openOpportunityCount'))} 条，但反馈数是 {_to_int(summary.get('feedbackCount'))}。",
            "action": "每天先处理 TOP 20 OPEN 机会，并把打开、联系、不值得、已成交全部回写。",
        },
        {
            "priority": "P0",
            "title": "把成交/ROI 当作唯一北极星证据",
            "reason": f"成交证明 {_to_int(summary.get('purchasedOpportunityCount'))} 条，ROI 证据 {_to_int(summary.get('roiEvidenceCount'))} 条。",
            "action": "所有已成交反馈必须记录买入价和预期转售价，否则不计入产品价值闭环。",
        },
    ]
    if _to_float(summary.get("specCoverageRate")) < 0.2:
        recommendations.append(
            {
                "priority": "P1",
                "title": "只补高价值机会相关规格",
                "reason": f"结构化规格覆盖率只有 {_to_float(summary.get('specCoverageRate')) * 100:.1f}%。",
                "action": "不要全量补规格，优先补 OPEN 和 guidance_ready 机会缺失的定价字段。",
            }
        )
    if _to_int(summary.get("alertedOpportunityCount")) == 0 or _to_int(summary.get("alertedOpportunityCount")) < _to_int(summary.get("openOpportunityCount")):
        recommendations.append(
            {
                "priority": "P1",
                "title": "刷新提醒候选而不是继续爬更多商品",
                "reason": f"OPEN 机会 {_to_int(summary.get('openOpportunityCount'))} 条，已提醒机会 {_to_int(summary.get('alertedOpportunityCount'))} 条。",
                "action": "基线和机会刷新后，先发出 dashboard alert candidate，再让操作者反馈命中质量。",
            }
        )
    recommendations.append(
        {
            "priority": "P2",
            "title": f"当前诊断：{diagnosis.get('statusLabel')}",
            "reason": str(diagnosis.get("summary") or ""),
            "action": str(diagnosis.get("nextBestAction") or ""),
        }
    )
    return recommendations


def build_buy_opportunity_detail_with_session(
    session: Session,
    *,
    opportunity_id: str,
    category_code: str | None = None,
) -> dict[str, Any] | None:
    normalized_opportunity_id = _normalize_optional_string(opportunity_id)
    if not normalized_opportunity_id:
        return None

    category = _resolve_optional_category(session, category_code=category_code)
    opportunity_stmt = select(BuyOpportunity).where(BuyOpportunity.id == normalized_opportunity_id)
    if category is not None:
        opportunity_stmt = opportunity_stmt.where(BuyOpportunity.category_id == str(category.id))

    opportunity = session.execute(opportunity_stmt).scalar_one_or_none()
    if opportunity is None:
        return None

    resolved_category = category
    if resolved_category is None and opportunity.category_id is not None:
        resolved_category = session.get(Category, str(opportunity.category_id))

    baseline = session.get(BuyPriceBaseline, str(opportunity.baseline_id)) if opportunity.baseline_id else None
    watch_target = session.get(BuyWatchTarget, str(opportunity.watch_target_id)) if opportunity.watch_target_id else None
    risk_rows = list(
        session.execute(
            select(BuyOpportunityRisk)
            .where(BuyOpportunityRisk.opportunity_id == normalized_opportunity_id)
            .order_by(BuyOpportunityRisk.risk_code.asc())
        )
        .scalars()
        .all()
    )
    alert_rows = list(
        session.execute(
            select(BuyAlertEvent)
            .where(BuyAlertEvent.opportunity_id == normalized_opportunity_id)
            .order_by(BuyAlertEvent.sent_at.desc(), BuyAlertEvent.created_at.desc())
        )
        .scalars()
        .all()
    )
    feedback_rows = list(
        session.execute(
            select(BuyDecisionFeedback)
            .where(BuyDecisionFeedback.opportunity_id == normalized_opportunity_id)
            .order_by(BuyDecisionFeedback.created_at.desc())
        )
        .scalars()
        .all()
    )

    detail_opportunity = {
        **serialize_buy_workbench_opportunity(opportunity),
        "firstDetectedAt": opportunity.first_detected_at.isoformat() if opportunity.first_detected_at else None,
        "decisionNote": opportunity.decision_note,
        "feedbackSummary": dict((opportunity.payload or {}).get("feedbackSummary") or {}),
        "matchedTemplateKey": (opportunity.payload or {}).get("matchedTemplateKey"),
        "matchedTemplateLabel": (opportunity.payload or {}).get("matchedTemplateLabel"),
        "matchedFieldValues": dict((opportunity.payload or {}).get("matchedFieldValues") or {}),
        "templateAvailabilityTier": (opportunity.payload or {}).get("templateAvailabilityTier"),
        "metrics": dict((opportunity.payload or {}).get("metrics") or {}),
    }
    item_id = _resolve_opportunity_item_id(session, opportunity)
    if item_id:
        detail_opportunity["itemId"] = item_id

    sorted_risks = sorted(
        risk_rows,
        key=lambda row: (_risk_level_sort_key(row.risk_level), str(row.risk_code or "")),
    )
    return {
        "categoryCode": resolved_category.code if resolved_category is not None else None,
        "opportunity": detail_opportunity,
        "baseline": serialize_buy_workbench_baseline(baseline) if baseline is not None else None,
        "watchTarget": serialize_buy_workbench_target(watch_target) if watch_target is not None else None,
        "outcomeProof": summarize_buy_opportunity_outcome_proof(
            alert_rows=alert_rows,
            feedback_rows=feedback_rows,
        ),
        "risks": [serialize_buy_opportunity_risk(row) for row in sorted_risks],
        "alertEvents": [serialize_buy_alert_event(row) for row in alert_rows],
        "feedbackEntries": [serialize_buy_decision_feedback(row) for row in feedback_rows],
    }


def build_buy_watch_targets_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    category = _resolve_optional_category(session, category_code=category_code)
    stmt = select(BuyWatchTarget).order_by(
        BuyWatchTarget.target_name.asc(),
        BuyWatchTarget.created_at.desc(),
    )
    if category is not None:
        stmt = stmt.where(BuyWatchTarget.category_id == str(category.id))
    if status:
        stmt = stmt.where(BuyWatchTarget.status == status)
    if limit > 0:
        stmt = stmt.limit(int(limit))

    rows = list(session.execute(stmt).scalars().all())
    active_count = _count_buy_targets(
        session=session,
        category=category,
        status="ACTIVE",
    )
    return {
        "categoryCode": category.code if category is not None else None,
        "summary": {
            "watchTargetCount": len(rows),
            "activeWatchTargetCount": active_count,
        },
        "watchTargets": [serialize_buy_workbench_target(row) for row in rows],
    }


def build_buy_price_baselines_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    baseline_date: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    category = _resolve_optional_category(session, category_code=category_code)
    stmt = select(BuyPriceBaseline).order_by(
        BuyPriceBaseline.baseline_date.desc(),
        BuyPriceBaseline.baseline_key.asc(),
    )
    if category is not None:
        stmt = stmt.where(BuyPriceBaseline.category_id == str(category.id))
    if baseline_date:
        stmt = stmt.where(BuyPriceBaseline.baseline_date == baseline_date)
    if limit > 0:
        stmt = stmt.limit(int(limit))

    rows = list(session.execute(stmt).scalars().all())
    return {
        "categoryCode": category.code if category is not None else None,
        "summary": {
            "baselineCount": len(rows),
            "baselineDateFrom": rows[-1].baseline_date.isoformat() if rows else None,
            "baselineDateTo": rows[0].baseline_date.isoformat() if rows else None,
        },
        "baselines": [serialize_buy_workbench_baseline(row) for row in rows],
    }


def serialize_buy_workbench_opportunity(row: BuyOpportunity) -> dict[str, Any]:
    pricing_record = dict((row.payload or {}).get("pricing_record") or {})
    pricing_eligibility = dict(
        pricing_record.get("pricing_eligibility")
        or (row.payload or {}).get("pricingEligibility")
        or {}
    )
    spec_contract = dict(
        pricing_record.get("spec_contract")
        or (row.payload or {}).get("specContract")
        or {}
    )
    spec_source = dict(
        pricing_record.get("spec_source")
        or pricing_eligibility.get("specSource")
        or (row.payload or {}).get("specSource")
        or {}
    )
    normalized_status = normalize_opportunity_status(row.status)
    explanation = build_buy_opportunity_explanation(
        opportunity_status=normalized_status,
        pricing_eligibility=pricing_eligibility,
        spec_contract=spec_contract,
        template_guidance_ready=_coerce_template_guidance_ready(
            normalized_status,
            (row.payload or {}).get("templateGuidanceReady"),
        ),
    )
    serialized_record = serialize_pricing_record(pricing_record)
    return {
        "id": row.id,
        "itemIdRef": str(row.item_id_ref) if row.item_id_ref is not None else None,
        "title": serialized_record.get("title"),
        "itemId": serialized_record.get("itemId"),
        "listingUrl": serialized_record.get("listingUrl"),
        "region": serialized_record.get("region"),
        "status": normalized_status,
        "decision": row.decision,
        "currentPrice": _decimal_to_float(row.current_price),
        "fairPrice": _decimal_to_float(row.fair_price),
        "buyCeiling": _decimal_to_float(row.buy_ceiling),
        "discountRate": _decimal_to_float(row.discount_rate),
        "opportunityScore": _decimal_to_float(row.opportunity_score),
        "riskScore": _decimal_to_float(row.risk_score),
        "exactSpecReady": serialized_record.get("exactSpecReady"),
        "specConfidence": serialized_record.get("specConfidence"),
        "pricingEligibility": pricing_eligibility,
        "specContract": spec_contract,
        "specSource": spec_source,
        "explanation": explanation,
        "baselineMatchLevel": (row.payload or {}).get("baseline_match_level"),
        "baselineMatchKey": (row.payload or {}).get("baseline_match_key"),
        "templateAvailabilityTier": (row.payload or {}).get("templateAvailabilityTier"),
        "lastDetectedAt": row.last_detected_at.isoformat() if row.last_detected_at else None,
    }


def serialize_buy_opportunity_risk(row: BuyOpportunityRisk) -> dict[str, Any]:
    return {
        "id": row.id,
        "riskCode": row.risk_code,
        "riskLevel": row.risk_level,
        "detail": row.detail,
        "evidence": dict(row.evidence_json or {}),
    }


def serialize_buy_workbench_baseline(row: BuyPriceBaseline) -> dict[str, Any]:
    explanation = build_buy_price_baseline_explanation(row)
    return {
        "id": row.id,
        "baselineKey": row.baseline_key,
        "sampleSize": row.sample_size,
        "fairPrice": _decimal_to_float(row.fair_price),
        "buyCeiling": _decimal_to_float(row.buy_ceiling),
        "confidence": _decimal_to_float(row.confidence),
        "baselineDate": row.baseline_date.isoformat() if row.baseline_date else None,
        "explanation": explanation,
    }


def serialize_buy_workbench_target(row: BuyWatchTarget) -> dict[str, Any]:
    return {
        "id": row.id,
        "targetName": row.target_name,
        "profileKey": row.profile_key,
        "status": row.status,
        "budgetCeiling": _decimal_to_float(row.budget_ceiling),
        "desiredMemoryGb": row.desired_memory_gb,
        "desiredStorageGb": row.desired_storage_gb,
        "desiredRegion": row.desired_region,
        "riskTolerance": row.risk_tolerance,
        "notifyCooldownMinutes": row.notify_cooldown_minutes,
    }


def summarize_buy_outcome_funnel_with_session(
    session: Session,
    *,
    category: Category | None = None,
    category_code: str | None = None,
) -> dict[str, Any]:
    resolved_category = category or _resolve_optional_category(session, category_code=category_code)
    alert_stmt = select(BuyAlertEvent)
    feedback_stmt = select(BuyDecisionFeedback)
    if resolved_category is not None:
        category_id = str(resolved_category.id)
        alert_stmt = (
            alert_stmt.join(BuyOpportunity, BuyAlertEvent.opportunity_id == BuyOpportunity.id)
            .where(BuyOpportunity.category_id == category_id)
        )
        feedback_stmt = (
            feedback_stmt.join(BuyOpportunity, BuyDecisionFeedback.opportunity_id == BuyOpportunity.id)
            .where(BuyOpportunity.category_id == category_id)
        )

    alert_rows = list(session.execute(alert_stmt).scalars().all())
    feedback_rows = list(session.execute(feedback_stmt).scalars().all())
    alerted_opportunity_ids = {
        opportunity_id
        for opportunity_id in (
            _normalize_optional_string(getattr(row, "opportunity_id", None))
            for row in alert_rows
        )
        if opportunity_id
    }
    contacted_opportunity_ids = _feedback_opportunity_ids_by_labels(
        feedback_rows,
        accepted_labels=CONTACT_OUTCOME_FEEDBACK_LABELS,
    )
    opened_opportunity_ids = _feedback_opportunity_ids_by_labels(
        feedback_rows,
        accepted_labels=OPEN_OUTCOME_FEEDBACK_LABELS,
    )
    purchased_opportunity_ids = _feedback_opportunity_ids_by_labels(
        feedback_rows,
        accepted_labels=PURCHASE_OUTCOME_FEEDBACK_LABELS,
    )
    roi_proofs = [
        proof
        for proof in (
            _serialize_purchase_roi_proof(row)
            for row in _latest_feedback_rows_by_labels(
                feedback_rows,
                accepted_labels=PURCHASE_OUTCOME_FEEDBACK_LABELS,
            ).values()
        )
        if proof is not None
    ]
    alerted_opened_count = len(alerted_opportunity_ids & opened_opportunity_ids)
    alerted_contacted_count = len(alerted_opportunity_ids & contacted_opportunity_ids)
    alerted_purchased_count = len(alerted_opportunity_ids & purchased_opportunity_ids)
    contacted_after_open_count = len(opened_opportunity_ids & contacted_opportunity_ids)
    purchased_after_contact_count = len(contacted_opportunity_ids & purchased_opportunity_ids)
    average_expected_profit = None
    average_expected_roi_rate = None
    if roi_proofs:
        average_expected_profit = round(
            sum(float(proof["estimatedProfit"] or 0.0) for proof in roi_proofs) / len(roi_proofs),
            2,
        )
        average_expected_roi_rate = round(
            sum(float(proof["estimatedRoiRate"] or 0.0) for proof in roi_proofs) / len(roi_proofs),
            4,
        )
    return {
        "categoryCode": resolved_category.code if resolved_category is not None else None,
        "alertedOpportunityCount": len(alerted_opportunity_ids),
        "openedOpportunityCount": len(opened_opportunity_ids),
        "contactedOpportunityCount": len(contacted_opportunity_ids),
        "purchasedOpportunityCount": len(purchased_opportunity_ids),
        "purchaseWithoutContactCount": len(purchased_opportunity_ids - contacted_opportunity_ids),
        "roiEvidenceCount": len(roi_proofs),
        "alertToOpenRate": _safe_rate(alerted_opened_count, len(alerted_opportunity_ids)),
        "alertToContactRate": _safe_rate(alerted_contacted_count, len(alerted_opportunity_ids)),
        "alertToPurchaseRate": _safe_rate(alerted_purchased_count, len(alerted_opportunity_ids)),
        "openToContactRate": _safe_rate(contacted_after_open_count, len(opened_opportunity_ids)),
        "contactToPurchaseRate": _safe_rate(purchased_after_contact_count, len(contacted_opportunity_ids)),
        "roiEvidenceCoverageRate": _safe_rate(len(roi_proofs), len(purchased_opportunity_ids)),
        "averageExpectedProfit": average_expected_profit,
        "averageExpectedRoiRate": average_expected_roi_rate,
    }


def summarize_buy_opportunity_outcome_proof(
    *,
    alert_rows: list[BuyAlertEvent],
    feedback_rows: list[BuyDecisionFeedback],
) -> dict[str, Any]:
    open_rows = _feedback_rows_for_labels(
        feedback_rows,
        accepted_labels=OPEN_OUTCOME_FEEDBACK_LABELS,
    )
    contact_rows = _feedback_rows_for_labels(
        feedback_rows,
        accepted_labels=CONTACT_OUTCOME_FEEDBACK_LABELS,
    )
    purchase_rows = _feedback_rows_for_labels(
        feedback_rows,
        accepted_labels=PURCHASE_OUTCOME_FEEDBACK_LABELS,
    )
    latest_feedback = max(
        feedback_rows,
        key=_feedback_sort_key,
        default=None,
    )
    latest_purchase = max(
        purchase_rows,
        key=_feedback_sort_key,
        default=None,
    )
    roi_proof = _serialize_purchase_roi_proof(latest_purchase)
    return {
        "alertEventCount": len(alert_rows),
        "openFeedbackCount": len(open_rows),
        "contactFeedbackCount": len(contact_rows),
        "purchaseFeedbackCount": len(purchase_rows),
        "hasAlertEvidence": bool(alert_rows),
        "hasOpenEvidence": bool(open_rows),
        "hasContactEvidence": bool(contact_rows),
        "hasPurchaseEvidence": bool(purchase_rows),
        "hasRoiEvidence": roi_proof is not None,
        "latestFeedbackLabel": _normalize_optional_string(getattr(latest_feedback, "feedback_label", None)),
        "purchasePrice": roi_proof["purchasePrice"] if roi_proof is not None else None,
        "expectedResalePrice": roi_proof["expectedResalePrice"] if roi_proof is not None else None,
        "estimatedProfit": roi_proof["estimatedProfit"] if roi_proof is not None else None,
        "estimatedRoiRate": roi_proof["estimatedRoiRate"] if roi_proof is not None else None,
    }


def _resolve_optional_category(session: Session, *, category_code: str | None) -> Category | None:
    normalized = _normalize_optional_string(category_code)
    if not normalized:
        return None
    return session.execute(select(Category).where(Category.code == resolve_category_code(normalized))).scalar_one_or_none()


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _feedback_rows_for_labels(
    feedback_rows: list[BuyDecisionFeedback],
    *,
    accepted_labels: set[str],
) -> list[BuyDecisionFeedback]:
    return [
        row
        for row in feedback_rows
        if _normalize_feedback_label(getattr(row, "feedback_label", None)) in accepted_labels
    ]


def _feedback_opportunity_ids_by_labels(
    feedback_rows: list[BuyDecisionFeedback],
    *,
    accepted_labels: set[str],
) -> set[str]:
    return {
        opportunity_id
        for opportunity_id in (
            _normalize_optional_string(getattr(row, "opportunity_id", None))
            for row in _feedback_rows_for_labels(feedback_rows, accepted_labels=accepted_labels)
        )
        if opportunity_id
    }


def _latest_feedback_rows_by_labels(
    feedback_rows: list[BuyDecisionFeedback],
    *,
    accepted_labels: set[str],
) -> dict[str, BuyDecisionFeedback]:
    latest_rows: dict[str, BuyDecisionFeedback] = {}
    for row in _feedback_rows_for_labels(feedback_rows, accepted_labels=accepted_labels):
        opportunity_id = _normalize_optional_string(getattr(row, "opportunity_id", None))
        if not opportunity_id:
            continue
        existing = latest_rows.get(opportunity_id)
        if existing is None or _feedback_sort_key(row) >= _feedback_sort_key(existing):
            latest_rows[opportunity_id] = row
    return latest_rows


def _serialize_purchase_roi_proof(row: BuyDecisionFeedback | None) -> dict[str, float] | None:
    if row is None:
        return None
    purchase_price = getattr(row, "purchase_price", None)
    expected_resale_price = getattr(row, "expected_resale_price", None)
    if purchase_price is None or expected_resale_price is None or purchase_price <= 0:
        return None
    estimated_profit = expected_resale_price - purchase_price
    estimated_roi_rate = estimated_profit / purchase_price
    return {
        "purchasePrice": _decimal_to_float(purchase_price),
        "expectedResalePrice": _decimal_to_float(expected_resale_price),
        "estimatedProfit": _decimal_to_float(estimated_profit),
        "estimatedRoiRate": round(float(estimated_roi_rate), 4),
    }


def _feedback_sort_key(row: BuyDecisionFeedback) -> datetime:
    return getattr(row, "created_at", None) or datetime.min.replace(tzinfo=UTC)


def _normalize_feedback_label(value: Any) -> str:
    normalized = _normalize_optional_string(value)
    if not normalized:
        return ""
    return normalized.lower().replace("-", "_").replace(" ", "_")


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _one_mapping(session: Session, sql: str, params: Mapping[str, Any]) -> dict[str, Any]:
    row = session.execute(text(sql), dict(params)).mappings().one()
    return dict(row)


def _many_mappings(session: Session, sql: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in session.execute(text(sql), dict(params)).mappings().all()]


def _camelize_mapping(row: Mapping[str, Any], *, exclude: set[str] | None = None) -> dict[str, Any]:
    excluded = exclude or set()
    return {
        _to_camel_case(key): _serialize_data_value(row.get(key))
        for key in row
        if key not in excluded
    }


def _to_camel_case(key: str) -> str:
    parts = str(key).split("_")
    if not parts:
        return str(key)
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _serialize_data_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_rate_float(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _data_value_score(
    *,
    spec_coverage: float,
    opportunity_yield: float,
    feedback_coverage: float,
    purchase_proof: float,
    roi_proof: float,
) -> float:
    score = (
        min(spec_coverage, 1.0) * 15
        + min(opportunity_yield * 10, 1.0) * 15
        + min(feedback_coverage * 20, 1.0) * 25
        + min(purchase_proof * 50, 1.0) * 25
        + min(roi_proof, 1.0) * 20
    )
    return round(score, 1)


def _resolve_opportunity_item_id(session: Session, opportunity: BuyOpportunity) -> str | None:
    payload = dict(opportunity.payload or {})
    pricing_record = serialize_pricing_record(dict(payload.get("pricing_record") or {}))
    item_id = _normalize_optional_string(pricing_record.get("itemId"))
    if item_id:
        return item_id
    if opportunity.item_id_ref is None:
        return None
    item = session.get(Item, opportunity.item_id_ref)
    return _normalize_optional_string(getattr(item, "item_id", None))


def _risk_level_sort_key(value: Any) -> int:
    normalized = str(value or "").strip().lower()
    if normalized == "high":
        return 0
    if normalized == "medium":
        return 1
    if normalized == "low":
        return 2
    return 3


def _coerce_template_guidance_ready(status: str | None, payload_value: Any) -> bool:
    if payload_value is None:
        return str(status or "").upper() == "OPEN"
    return bool(payload_value)


def _today_opportunity_window_seconds() -> int:
    return 24 * 60 * 60


def _count_buy_opportunities_opened_since(
    *,
    session: Session,
    category_id: str | None,
    since_seconds: int,
) -> int:
    if since_seconds <= 0:
        return 0
    started_at = datetime.now(UTC) - timedelta(seconds=since_seconds)
    stmt = select(BuyOpportunity).where(BuyOpportunity.first_detected_at >= started_at)
    if category_id:
        stmt = stmt.where(BuyOpportunity.category_id == category_id)
    return len(session.execute(stmt.with_only_columns(BuyOpportunity.id)).all())


def _count_buy_targets(
    *,
    session: Session,
    category: Category | None,
    status: str | None = None,
) -> int:
    stmt = select(BuyWatchTarget)
    if category is not None:
        stmt = stmt.where(BuyWatchTarget.category_id == str(category.id))
    if status:
        stmt = stmt.where(BuyWatchTarget.status == status)
    return len(session.execute(stmt.with_only_columns(BuyWatchTarget.id)).all())


__all__ = [
    "build_daily_opportunity_pack",
    "build_buy_data_value_report_with_session",
    "build_buy_opportunity_detail_with_session",
    "build_buy_opportunity_workbench",
    "summarize_buy_outcome_funnel_with_session",
    "build_buy_price_baselines_with_session",
    "build_buy_watch_targets_with_session",
    "record_buy_decision_feedback",
    "record_buy_decision_feedback_with_session",
    "refresh_buy_opportunities",
    "refresh_buy_opportunities_with_session",
    "serialize_buy_opportunity_risk",
    "serialize_buy_workbench_baseline",
    "serialize_buy_workbench_opportunity",
    "serialize_buy_workbench_target",
    "summarize_buy_feedback_calibration",
    "summarize_buy_feedback_calibration_with_session",
    "summarize_buy_feedback_quality",
    "summarize_buy_feedback_quality_with_session",
    "summarize_template_availability_monitoring",
    "summarize_template_availability_monitoring_with_session",
]
