from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from goofish_analyzer.adapters import (
    resolve_category_code,
    UTC,
    normalize_alert_status,
    normalize_availability_tier,
    normalize_opportunity_status,
    serialize_alert_event,
    BuyAlertEvent,
    BuyDecisionFeedback,
    BuyOpportunity,
    BuyWatchTarget,
    Category,
    session_scope,
    create_notification_delivery_for_alert,
    is_price_template_alert_strict_mode_enabled,
)


class BuyAlertError(RuntimeError):
    pass


def summarize_buy_alert_hit_rate(
    *,
    category_code: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return summarize_buy_alert_hit_rate_with_session(
            session,
            category_code=category_code,
        )


def summarize_buy_alert_hit_rate_with_session(
    session: Session,
    *,
    category_code: str | None = None,
) -> dict[str, Any]:
    category = _resolve_optional_category(session, category_code=category_code)
    alert_stmt = select(BuyAlertEvent)
    if category is not None:
        opportunity_ids = list(
            session.execute(
                select(BuyOpportunity.id).where(BuyOpportunity.category_id == str(category.id))
            )
            .scalars()
            .all()
        )
        if not opportunity_ids:
            return {
                "categoryCode": category.code,
                "alertCount": 0,
                "hitCount": 0,
                "hitRate": 0.0,
            }
        alert_stmt = alert_stmt.where(BuyAlertEvent.opportunity_id.in_([str(value) for value in opportunity_ids]))

    alerts = list(session.execute(alert_stmt).scalars().all())
    alerted_opportunity_ids = {str(alert.opportunity_id) for alert in alerts}
    if not alerted_opportunity_ids:
        return {
            "categoryCode": category.code if category is not None else None,
            "alertCount": 0,
            "hitCount": 0,
            "hitRate": 0.0,
        }

    feedback_rows = list(
        session.execute(
            select(BuyDecisionFeedback).where(BuyDecisionFeedback.opportunity_id.in_(alerted_opportunity_ids))
        )
        .scalars()
        .all()
    )
    hit_opportunity_ids = {
        str(row.opportunity_id)
        for row in feedback_rows
        if is_positive_alert_feedback_label(str(row.feedback_label or ""))
    }
    return {
        "categoryCode": category.code if category is not None else None,
        "alertCount": len(alerts),
        "alertedOpportunityCount": len(alerted_opportunity_ids),
        "hitCount": len(hit_opportunity_ids),
        "hitRate": round(len(hit_opportunity_ids) / len(alerted_opportunity_ids), 4),
    }


def is_positive_alert_feedback_label(feedback_label: str) -> bool:
    normalized = feedback_label.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in {"contacted", "messaged", "purchased", "bought", "成交", "已买", "已联系"}


def is_alert_eligible_opportunity(opportunity: BuyOpportunity) -> bool:
    return _is_alert_eligible_payload(
        payload=dict(opportunity.payload or {}),
        status_override=None,
        current_status=opportunity.status,
    )


def has_active_alert_event(
    *,
    session: Session,
    opportunity: BuyOpportunity,
    watch_target: BuyWatchTarget | None = None,
    now: datetime | None = None,
) -> bool:
    existing_rows = list(
        session.execute(
            select(BuyAlertEvent)
            .where(BuyAlertEvent.opportunity_id == str(opportunity.id))
            .where(BuyAlertEvent.watch_target_id == str(opportunity.watch_target_id))
            .where(BuyAlertEvent.status.in_(("PENDING", "SENT")))
        )
        .scalars()
        .all()
    )
    if any(row.status == "PENDING" for row in existing_rows):
        return True
    cooldown_minutes = int(getattr(watch_target, "notify_cooldown_minutes", None) or 60)
    cutoff = (now or datetime.now(UTC)) - timedelta(minutes=max(cooldown_minutes, 1))
    for row in existing_rows:
        if row.status != "SENT":
            continue
        created_at = row.created_at
        if created_at is None or created_at >= cutoff:
            return True
    return False


def build_alert_reason(opportunity: BuyOpportunity) -> str:
    discount_pct = (
        f"{float(opportunity.discount_rate) * 100:.1f}%"
        if opportunity.discount_rate is not None
        else "unknown"
    )
    score = (
        f"{float(opportunity.opportunity_score):.1f}"
        if opportunity.opportunity_score is not None
        else "unknown"
    )
    return f"buy opportunity score={score}, discount={discount_pct}"


def build_alert_payload(opportunity: BuyOpportunity) -> dict[str, Any]:
    pricing_record = dict((opportunity.payload or {}).get("pricing_record") or {})
    return {
        "source": "buy_alerts.emit_buy_alert_events",
        "opportunity": {
            "id": opportunity.id,
            "item_id_ref": opportunity.item_id_ref,
            "current_price": _decimal_to_float(opportunity.current_price),
            "fair_price": _decimal_to_float(opportunity.fair_price),
            "buy_ceiling": _decimal_to_float(opportunity.buy_ceiling),
            "discount_rate": _decimal_to_float(opportunity.discount_rate),
            "opportunity_score": _decimal_to_float(opportunity.opportunity_score),
            "risk_score": _decimal_to_float(opportunity.risk_score),
        },
        "listing": {
            "item_id": pricing_record.get("item_id"),
            "title": pricing_record.get("title"),
            "listing_url": pricing_record.get("listing_url"),
            "region": pricing_record.get("region"),
        },
    }


def serialize_buy_alert_event(row: BuyAlertEvent) -> dict[str, Any]:
    internal_alert = {
        "id": row.id,
        "opportunity_id": row.opportunity_id,
        "watch_target_id": row.watch_target_id,
        "alert_channel": row.alert_channel,
        "alert_reason": row.alert_reason,
        "status": row.status,
        "sent_at": row.sent_at,
        "payload": dict(row.payload or {}),
    }
    return serialize_alert_event(internal_alert)


def emit_buy_alert_events(
    *,
    category_code: str | None = None,
    min_opportunity_score: float = 55.0,
    channel: str = "dashboard",
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        result = emit_buy_alert_events_with_session(
            session,
            category_code=category_code,
            min_opportunity_score=min_opportunity_score,
            channel=channel,
            limit=limit,
        )
        if dry_run:
            session.rollback()
            result["dryRun"] = True
        return result


def emit_buy_alert_events_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    min_opportunity_score: float = 55.0,
    channel: str = "dashboard",
    limit: int | None = None,
) -> dict[str, Any]:
    category = _resolve_optional_category(session, category_code=category_code)
    stmt = (
        select(BuyOpportunity)
        .where(BuyOpportunity.status == "OPEN")
        .where(BuyOpportunity.opportunity_score >= Decimal(str(min_opportunity_score)))
        .order_by(BuyOpportunity.opportunity_score.desc(), BuyOpportunity.last_detected_at.desc())
    )
    if category is not None:
        stmt = stmt.where(BuyOpportunity.category_id == str(category.id))
    opportunities = list(session.execute(stmt).scalars().all())
    if limit is not None:
        opportunities = opportunities[: max(int(limit), 0)]

    skipped = {"duplicate_alert": 0}
    created: list[BuyAlertEvent] = []
    for opportunity in opportunities:
        if not is_alert_eligible_opportunity(opportunity):
            skipped["ineligible_opportunity"] = skipped.get("ineligible_opportunity", 0) + 1
            continue
        watch_target = session.get(BuyWatchTarget, str(opportunity.watch_target_id))
        if has_active_alert_event(
            session=session,
            opportunity=opportunity,
            watch_target=watch_target,
        ):
            skipped["duplicate_alert"] += 1
            continue
        alert = BuyAlertEvent(
            opportunity_id=str(opportunity.id),
            watch_target_id=str(opportunity.watch_target_id),
            alert_channel=channel,
            alert_reason=build_alert_reason(opportunity),
            status="PENDING",
            payload=build_alert_payload(opportunity),
        )
        session.add(alert)
        _flush(session)
        session.add(create_notification_delivery_for_alert(alert, channel=channel))
        created.append(alert)

    _flush(session)
    return {
        "dryRun": False,
        "categoryCode": category.code if category is not None else None,
        "candidateOpportunityCount": len(opportunities),
        "alertCount": len(created),
        "skipped": skipped,
        "items": [serialize_buy_alert_event(row) for row in created],
    }


def link_buy_feedback_to_alert_candidate_with_session(
    session: Session,
    *,
    opportunity: BuyOpportunity,
    channel: str = "dashboard",
    status_at_feedback: str | None = None,
    linkage_source: str = "buy_feedback_interest",
) -> dict[str, Any]:
    watch_target = session.get(BuyWatchTarget, str(opportunity.watch_target_id))
    if watch_target is None:
        return {
            "status": "skipped",
            "reason": "watch_target_missing",
            "channel": channel,
            "alertEventId": None,
        }

    if not _is_alert_eligible_payload(
        payload=dict(opportunity.payload or {}),
        status_override=status_at_feedback,
        current_status=opportunity.status,
    ):
        return {
            "status": "skipped",
            "reason": "opportunity_not_eligible",
            "channel": channel,
            "alertEventId": None,
        }

    if has_active_alert_event(
        session=session,
        opportunity=opportunity,
        watch_target=watch_target,
    ):
        return {
            "status": "duplicate",
            "reason": "active_alert_exists",
            "channel": channel,
            "alertEventId": None,
        }

    payload = build_alert_payload(opportunity)
    payload["source"] = "buy_alerts.link_buy_feedback_to_alert_candidate"
    payload["feedbackLinkage"] = {
        "source": linkage_source,
        "statusAtFeedback": str(status_at_feedback or opportunity.status or "").strip().upper() or None,
        "linkedAt": datetime.now(UTC).isoformat(),
    }
    alert = BuyAlertEvent(
        opportunity_id=str(opportunity.id),
        watch_target_id=str(opportunity.watch_target_id),
        alert_channel=channel,
        alert_reason=f"{build_alert_reason(opportunity)} [linked_from_buy_feedback]",
        status="PENDING",
        payload=payload,
    )
    session.add(alert)
    _flush(session)
    session.add(create_notification_delivery_for_alert(alert, channel=channel))
    return {
        "status": "created",
        "reason": "candidate_created",
        "channel": channel,
        "alertEventId": str(alert.id),
    }


def _resolve_optional_category(session: Session, *, category_code: str | None) -> Category | None:
    normalized = _normalize_optional_string(category_code)
    if not normalized:
        return None
    resolved = resolve_category_code(normalized)
    row = session.execute(select(Category).where(Category.code == resolved)).scalar_one_or_none()
    if row is None:
        raise BuyAlertError(f"Category not found: {resolved}")
    return row


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _flush(session: Session) -> None:
    flush = getattr(session, "flush", None)
    if callable(flush):
        flush()


def _is_alert_eligible_payload(
    *,
    payload: dict[str, Any],
    status_override: str | None,
    current_status: str | None,
) -> bool:
    normalized_status = normalize_opportunity_status(status_override or current_status)
    if normalized_status != "OPEN":
        return False
    if not is_price_template_alert_strict_mode_enabled():
        return True
    if normalize_availability_tier(payload.get("templateAvailabilityTier")) != "guidance_ready":
        return False
    if not payload.get("matchedTemplateKey"):
        return False
    if payload.get("baseline_match_level") in {"degraded_product", "degraded_brand"}:
        return False
    return True


__all__ = [
    "BuyAlertError",
    "build_alert_payload",
    "build_alert_reason",
    "emit_buy_alert_events",
    "emit_buy_alert_events_with_session",
    "has_active_alert_event",
    "is_alert_eligible_opportunity",
    "is_positive_alert_feedback_label",
    "link_buy_feedback_to_alert_candidate_with_session",
    "serialize_buy_alert_event",
    "summarize_buy_alert_hit_rate",
    "summarize_buy_alert_hit_rate_with_session",
]
