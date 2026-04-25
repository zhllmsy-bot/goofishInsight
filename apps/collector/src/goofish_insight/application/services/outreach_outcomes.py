from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...compat import UTC
from ...db import session_scope
from ...models import OutreachRecord

CLOSED_OUTCOME_STATUSES = {"closed", "deal", "purchased", "not_interested", "failed", "成交", "已成交", "放弃"}


class OutreachOutcomeError(RuntimeError):
    pass


def record_outreach_outcome(
    *,
    outreach_id: int | None = None,
    item_id: str | None = None,
    outcome_status: str,
    deal_price: str | Decimal | None = None,
    operator_note: str | None = None,
    closed_at: datetime | str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        row = _load_outreach_record(session, outreach_id=outreach_id, item_id=item_id)
        apply_outreach_outcome(
            row,
            outcome_status=outcome_status,
            deal_price=deal_price,
            operator_note=operator_note,
            closed_at=closed_at,
        )
        result = serialize_outreach_outcome(row)
        if dry_run:
            session.rollback()
            result["dryRun"] = True
        return result


def summarize_outreach_outcomes(
    *,
    window_days: int = 30,
) -> dict[str, Any]:
    with session_scope() as session:
        return summarize_outreach_outcomes_with_session(session, window_days=window_days)


def summarize_outreach_outcomes_with_session(session: Session, *, window_days: int = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=max(int(window_days), 1))
    rows = session.execute(
        select(OutreachRecord.outcome_status, func.count())
        .where(OutreachRecord.updated_at >= since)
        .where(OutreachRecord.outcome_status.is_not(None))
        .group_by(OutreachRecord.outcome_status)
        .order_by(OutreachRecord.outcome_status)
    ).all()
    total = sum(int(count or 0) for _status, count in rows)
    return {
        "windowDays": max(int(window_days), 1),
        "totalOutcomeCount": total,
        "statusCounts": {str(status): int(count or 0) for status, count in rows},
    }


def apply_outreach_outcome(
    row: OutreachRecord,
    *,
    outcome_status: str,
    deal_price: str | Decimal | None = None,
    operator_note: str | None = None,
    closed_at: datetime | str | None = None,
) -> OutreachRecord:
    normalized_status = _normalize_required_string(outcome_status, field_name="outcome_status")
    row.outcome_status = normalized_status
    row.deal_price = _parse_decimal(deal_price)
    row.operator_note = _normalize_optional_string(operator_note)
    parsed_closed_at = _parse_datetime(closed_at)
    if parsed_closed_at is not None:
        row.closed_at = parsed_closed_at
    elif normalized_status.lower() in CLOSED_OUTCOME_STATUSES:
        row.closed_at = datetime.now(UTC)
    return row


def serialize_outreach_outcome(row: OutreachRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "itemId": row.item_id,
        "status": row.status,
        "outcomeStatus": row.outcome_status,
        "dealPrice": str(row.deal_price) if row.deal_price is not None else None,
        "closedAt": row.closed_at.isoformat() if row.closed_at else None,
        "operatorNote": row.operator_note,
    }


def _load_outreach_record(
    session: Session,
    *,
    outreach_id: int | None,
    item_id: str | None,
) -> OutreachRecord:
    if outreach_id is None and not _normalize_optional_string(item_id):
        raise OutreachOutcomeError("Either outreach_id or item_id is required")
    row = session.get(OutreachRecord, outreach_id) if outreach_id is not None else None
    if row is None and item_id:
        row = session.execute(select(OutreachRecord).where(OutreachRecord.item_id == item_id)).scalar_one_or_none()
    if row is None:
        raise OutreachOutcomeError("Outreach record not found")
    return row


def _normalize_required_string(value: Any, *, field_name: str) -> str:
    normalized = _normalize_optional_string(value)
    if not normalized:
        raise OutreachOutcomeError(f"{field_name} is required")
    return normalized


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _parse_decimal(value: str | Decimal | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise OutreachOutcomeError(f"Invalid deal_price: {value}") from exc


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise OutreachOutcomeError(f"Invalid closed_at: {value}") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
