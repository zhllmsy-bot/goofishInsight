from __future__ import annotations

import json
import re
import statistics
from datetime import datetime
from ...compat import UTC
from decimal import Decimal
from pathlib import Path
from typing import Any

from ...presentation.web import domain_label, format_currency
from ...settings import get_settings

MOBILE_MARKET_REPORTS_DIR = get_settings().base_dir / "reports" / "mobile-market-bulk"


def load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def normalize_model_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())


def parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def resolve_report_path(raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    candidates = [
        Path(raw_path),
        MOBILE_MARKET_REPORTS_DIR / Path(raw_path).name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def find_latest_mobile_queue_state() -> Path | None:
    if not MOBILE_MARKET_REPORTS_DIR.exists():
        return None
    for path in sorted(
        MOBILE_MARKET_REPORTS_DIR.glob("queue-state*.json"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    ):
        payload = load_json_object(path)
        tasks = payload.get("tasks") if payload else None
        if not isinstance(tasks, list):
            continue
        if any(
            isinstance(task, dict)
            and task.get("status") == "done"
            and task.get("last_output_path")
            for task in tasks
        ):
            return path
    return None


def format_signed_currency(value: float) -> str:
    if value > 0:
        return f"+{format_currency(value)}"
    if value < 0:
        return f"-{format_currency(abs(value))}"
    return format_currency(value)


def derive_anchor_price(
    *,
    visible_records: list[dict[str, Any]],
    sold_price_range_low: float | None,
    sold_price_range_high: float | None,
    recent_avg_price_7d: float | None,
) -> tuple[float | None, str]:
    sold_prices = [
        float(price)
        for price in (to_float(record.get("sold_price")) for record in visible_records)
        if price is not None
    ]
    if sold_prices:
        return statistics.median(sold_prices), "真实成交中位价"
    if sold_price_range_low is not None and sold_price_range_high is not None:
        return (sold_price_range_low + sold_price_range_high) / 2, "成交区间中位价"
    if recent_avg_price_7d is not None:
        return recent_avg_price_7d, "近7日成交均价"
    return None, "待补充成交锚点"


def build_calibration_payload(
    *,
    listed_avg_price: float | None,
    sold_anchor_price: float | None,
) -> dict[str, Any]:
    if listed_avg_price is None or sold_anchor_price is None or sold_anchor_price <= 0:
        return {
            "calibration_label": "等待比对",
            "calibration_class": "warm",
            "calibration_detail": "缺少挂牌均价或真实成交锚点，暂时无法校准。",
            "gap_value": None,
            "gap_pct": None,
        }

    gap_value = listed_avg_price - sold_anchor_price
    gap_pct = gap_value / sold_anchor_price * 100

    if gap_pct > 18:
        label = "挂牌偏高"
        class_name = "alert"
    elif gap_pct > 8:
        label = "挂牌略高"
        class_name = "warm"
    elif gap_pct < -8:
        label = "成交更强"
        class_name = "healthy"
    else:
        label = "挂牌贴盘"
        class_name = "healthy"

    return {
        "calibration_label": label,
        "calibration_class": class_name,
        "calibration_detail": f"较真实成交 {gap_pct:+.1f}% / {format_signed_currency(gap_value)}",
        "gap_value": round(gap_value, 2),
        "gap_pct": round(gap_pct, 1),
    }


def build_evidence_label(
    *,
    visible_record_count: int,
    sold_price_range_low: float | None,
    sold_price_range_high: float | None,
    recent_avg_price_7d: float | None,
) -> str:
    if visible_record_count > 0:
        return f"真实成交 {visible_record_count} 条"
    if sold_price_range_low is not None and sold_price_range_high is not None:
        return "已拿到成交区间"
    if recent_avg_price_7d is not None:
        return "已拿到7日均价"
    return "移动端已抓取"


def build_mobile_market_calibration_panel(
    *,
    business_domain: str | None,
    top_models: list[dict[str, Any]],
) -> dict[str, Any]:
    panel = {
        "available": False,
        "queue_name": None,
        "queue_updated_at": None,
        "latest_captured_at": None,
        "captured_model_count": 0,
        "domain_count": 0,
        "comparison_ready_count": 0,
        "with_visible_records_count": 0,
        "with_range_count": 0,
        "with_recent_avg_count": 0,
        "visible_record_total": 0,
        "rows": [],
    }

    state_path = find_latest_mobile_queue_state()
    if state_path is None:
        return panel

    state = load_json_object(state_path)
    tasks = state.get("tasks") if state else None
    if not isinstance(tasks, list):
        return panel

    top_model_lookup = {
        (str(row["business_domain"]), normalize_model_key(str(row["model_name"]))): row
        for row in top_models
    }
    top_model_order = {
        (str(row["business_domain"]), normalize_model_key(str(row["model_name"]))): index
        for index, row in enumerate(top_models)
    }

    rows: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict) or task.get("status") != "done":
            continue

        task_domain = str(task.get("business_domain") or "").strip()
        task_model_name = str(task.get("model_name") or "").strip()
        if not task_domain or not task_model_name:
            continue
        if business_domain and task_domain != business_domain:
            continue

        report_path = resolve_report_path(task.get("last_output_path"))
        report = load_json_object(report_path) if report_path else None
        if report is None:
            continue

        visible_records = [record for record in report.get("visible_records", []) if isinstance(record, dict)]
        sold_price_range_low = to_float(report.get("sold_price_range_low"))
        sold_price_range_high = to_float(report.get("sold_price_range_high"))
        recent_avg_price_7d = to_float(report.get("recent_avg_price_7d"))
        sold_anchor_price, anchor_source_label = derive_anchor_price(
            visible_records=visible_records,
            sold_price_range_low=sold_price_range_low,
            sold_price_range_high=sold_price_range_high,
            recent_avg_price_7d=recent_avg_price_7d,
        )

        top_model = top_model_lookup.get((task_domain, normalize_model_key(task_model_name)))
        listed_avg_price = (
            float(top_model["avg_price"])
            if top_model and top_model.get("avg_price") is not None
            else None
        )
        calibration = build_calibration_payload(
            listed_avg_price=listed_avg_price,
            sold_anchor_price=sold_anchor_price,
        )
        first_record_title = next(
            (
                str(record.get("title") or "").strip()
                for record in visible_records
                if str(record.get("title") or "").strip()
            ),
            None,
        )

        rows.append(
            {
                "business_domain": task_domain,
                "domain_label": domain_label(task_domain),
                "model_name": task_model_name,
                "task_id": str(task.get("task_id") or ""),
                "query": report.get("query"),
                "captured_at": parse_iso_datetime(report.get("captured_at")),
                "report_path": str(report_path),
                "listed_avg_price": listed_avg_price,
                "listed_listing_count": int(top_model.get("listing_count") or 0) if top_model else None,
                "listed_seller_count": int(top_model.get("seller_count") or 0) if top_model else None,
                "sold_anchor_price": sold_anchor_price,
                "anchor_source_label": anchor_source_label,
                "recent_avg_price_7d": recent_avg_price_7d,
                "sold_price_range_low": sold_price_range_low,
                "sold_price_range_high": sold_price_range_high,
                "visible_record_count": len(visible_records),
                "visible_records": visible_records[:3],
                "first_record_title": first_record_title,
                "evidence_label": build_evidence_label(
                    visible_record_count=len(visible_records),
                    sold_price_range_low=sold_price_range_low,
                    sold_price_range_high=sold_price_range_high,
                    recent_avg_price_7d=recent_avg_price_7d,
                ),
                **calibration,
            }
        )

    if not rows:
        return panel

    rows.sort(
        key=lambda row: (
            top_model_order.get(
                (row["business_domain"], normalize_model_key(row["model_name"])),
                10**6,
            ),
            row["business_domain"],
            row["model_name"],
        )
    )

    panel.update(
        {
            "available": True,
            "queue_name": state_path.name,
            "queue_updated_at": datetime.fromtimestamp(state_path.stat().st_mtime, tz=UTC),
            "latest_captured_at": max(
                (row["captured_at"] for row in rows if row["captured_at"] is not None),
                default=None,
            ),
            "captured_model_count": len(rows),
            "domain_count": len({row["business_domain"] for row in rows}),
            "comparison_ready_count": sum(
                1
                for row in rows
                if row["listed_avg_price"] is not None and row["sold_anchor_price"] is not None
            ),
            "with_visible_records_count": sum(1 for row in rows if row["visible_record_count"] > 0),
            "with_range_count": sum(
                1
                for row in rows
                if row["sold_price_range_low"] is not None and row["sold_price_range_high"] is not None
            ),
            "with_recent_avg_count": sum(1 for row in rows if row["recent_avg_price_7d"] is not None),
            "visible_record_total": sum(row["visible_record_count"] for row in rows),
            "rows": rows,
        }
    )
    return panel


def merge_mobile_market_into_top_models(
    top_models: list[dict[str, Any]],
    mobile_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mobile_lookup = {
        (str(row["business_domain"]), normalize_model_key(str(row["model_name"]))): row
        for row in mobile_rows
    }
    return [
        {
            **row,
            "mobile_calibration": mobile_lookup.get(
                (str(row["business_domain"]), normalize_model_key(str(row["model_name"])))
            ),
        }
        for row in top_models
    ]
