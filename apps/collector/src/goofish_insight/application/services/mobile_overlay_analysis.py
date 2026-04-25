from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from ...compat import UTC
from ...models import CrawlTask, Item, ItemSnapshot
from ...normalizers import ExtractedItem, normalize_market_price, normalize_title
from ...presentation.web import domain_label, format_currency
from ...pricing import aggregate_pricing_view, load_pricing_records, resolve_pricing_record, title_matches_domain
from ...settings import get_settings
from .dashboard_queries import build_domain_trend_chart, freshness_cutoff, summarize_daily_snapshots, summarize_trend_quality
from .mobile_overlay_vlm import analyze_mobile_overlay_screenshot

OVERLAY_DOMAIN_TOKENS = {
    "garmin": (
        "garmin",
        "佳明",
        "fenix",
        "epix",
        "forerunner",
        "instinct",
        "marq",
        "tactix",
        "venu",
        "approach",
        "enduro",
    ),
    "apple_m_series": (
        "apple",
        "苹果",
        "macbook",
        "mac mini",
        "mac studio",
        "imac",
        "m1",
        "m2",
        "m3",
        "m4",
    ),
}
OVERLAY_TITLE_EXCLUDE_TOKENS = (
    "闲鱼",
    "首页",
    "鱼塘",
    "发布",
    "消息",
    "我的",
    "分享",
    "收藏",
    "想要",
    "浏览",
    "信用",
    "卖家",
    "联系",
    "留言",
    "客服",
    "保障",
    "包邮",
    "运费",
    "邮费",
    "退换",
    "已售",
    "已出",
    "付款",
)
OVERLAY_PRICE_EXCLUDE_TOKENS = (
    "浏览",
    "想要",
    "信用",
    "粉丝",
    "鱼力",
    "邮费",
    "运费",
    "包邮",
    "月付",
    "分期",
    "%",
)
OVERLAY_PRICE_MARKERS = ("¥", "￥", "价格", "售价", "现价", "到手", "仅售", "只要")
OVERLAY_PRICE_PATTERN = re.compile(
    r"(?<!\d)(\d{2,6}(?:[.,]\d{1,2})?|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?)(万|w)?(?!\d)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class OverlayOcrLine:
    text: str
    left: int | None = None
    top: int | None = None
    right: int | None = None
    bottom: int | None = None
    index: int = 0

    @property
    def height(self) -> int:
        if self.top is None or self.bottom is None:
            return 0
        return max(self.bottom - self.top, 0)


def build_mobile_overlay_analysis(
    session,
    *,
    ocr_lines: list[dict[str, Any]],
    source_package: str | None = None,
    screen_width: int | None = None,
    screen_height: int | None = None,
    captured_at: str | None = None,
    screenshot_base64: str | None = None,
) -> dict[str, Any]:
    normalized_lines = normalize_ocr_lines(ocr_lines)
    ocr_text = "\n".join(line.text for line in normalized_lines)
    price_payload = extract_listing_price(normalized_lines, screen_height=screen_height)
    ocr_title_candidate = extract_title_candidate(
        normalized_lines,
        screen_height=screen_height,
        price_anchor=price_payload["source_line"],
    )
    vlm_payload = None
    if screenshot_base64:
        vlm_payload = build_overlay_vlm_payload(
            screenshot_base64=screenshot_base64,
            normalized_lines=normalized_lines,
            screen_width=screen_width,
            screen_height=screen_height,
            source_package=source_package,
        )
    title_candidate, title_candidate_source = choose_overlay_title_candidate(
        ocr_title_candidate=ocr_title_candidate,
        vlm_title_candidate=(vlm_payload or {}).get("title_candidate"),
        vlm_confidence=(vlm_payload or {}).get("confidence"),
    )

    tasks_by_domain = load_active_tasks_by_domain(session)
    candidate_domains = determine_candidate_domains(
        title_candidate=title_candidate,
        ocr_text=build_overlay_matching_text(ocr_text=ocr_text, vlm_payload=vlm_payload),
        tasks_by_domain=tasks_by_domain,
        preferred_domain=(vlm_payload or {}).get("business_domain_hint"),
    )

    domain_analyses: list[dict[str, Any]] = []
    for domain in candidate_domains:
        task = tasks_by_domain.get(domain)
        if task is None:
            continue
        analysis = analyze_domain_candidate(
            session,
            task=task,
            title_candidate=title_candidate,
            ocr_text=ocr_text,
            listing_price=price_payload["price_decimal"],
        )
        if analysis is not None:
            domain_analyses.append(analysis)

    best_match = max(domain_analyses, key=overlay_analysis_rank, default=None)
    decision = build_overlay_decision(
        listing_price=price_payload["price_decimal"],
        best_match=best_match,
    )

    return {
        "ok": True,
        "source_package": source_package,
        "captured_at": captured_at,
        "ocr_summary": {
            "line_count": len(normalized_lines),
            "title_candidate": title_candidate,
            "ocr_title_candidate": ocr_title_candidate,
            "title_candidate_source": title_candidate_source,
            "listing_price": decimal_to_float(price_payload["price_decimal"]),
            "price_source_text": price_payload["source_text"],
            "text_excerpt": build_text_excerpt(ocr_text),
            "screenshot_supplied": bool(screenshot_base64),
        },
        "vlm_summary": vlm_payload,
        "match": best_match,
        "alternatives": domain_analyses[:3],
        "decision": decision,
    }


def normalize_ocr_lines(raw_lines: list[dict[str, Any]]) -> list[OverlayOcrLine]:
    normalized: list[OverlayOcrLine] = []
    for index, raw in enumerate(raw_lines):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        normalized.append(
            OverlayOcrLine(
                text=text,
                left=to_int(raw.get("left")),
                top=to_int(raw.get("top")),
                right=to_int(raw.get("right")),
                bottom=to_int(raw.get("bottom")),
                index=index,
            )
        )
    return sorted(
        normalized,
        key=lambda line: (
            line.top if line.top is not None else 10**9,
            line.left if line.left is not None else 10**9,
            line.index,
        ),
    )


def load_active_tasks_by_domain(session) -> dict[str, CrawlTask]:
    rows = session.execute(
        select(CrawlTask)
        .where(CrawlTask.status == "active")
        .order_by(CrawlTask.id.desc())
    ).scalars()
    tasks: dict[str, CrawlTask] = {}
    for task in rows:
        tasks.setdefault(task.business_domain, task)
    return tasks


def determine_candidate_domains(
    *,
    title_candidate: str | None,
    ocr_text: str,
    tasks_by_domain: dict[str, CrawlTask],
    preferred_domain: str | None = None,
) -> list[str]:
    ranked: list[str] = []
    haystacks = [value for value in (title_candidate, ocr_text) if value]
    normalized = normalize_title(title_candidate or ocr_text or "")
    if preferred_domain and preferred_domain in tasks_by_domain:
        ranked.append(preferred_domain)
    for domain in tasks_by_domain:
        if domain in ranked:
            continue
        if any(title_matches_domain(domain, value) for value in haystacks):
            ranked.append(domain)
    if not ranked and normalized["brand"] == "Garmin" and "garmin" in tasks_by_domain:
        ranked.append("garmin")
    if not ranked and normalized["brand"] == "Apple" and "apple_m_series" in tasks_by_domain:
        ranked.append("apple_m_series")
    return ranked


def extract_title_candidate(
    lines: list[OverlayOcrLine],
    *,
    screen_height: int | None,
    price_anchor: OverlayOcrLine | None = None,
) -> str | None:
    if not lines:
        return None

    if price_anchor is not None:
        anchored = extract_title_candidate_near_price(
            lines,
            price_anchor=price_anchor,
            screen_height=screen_height,
        )
        if anchored:
            return anchored

    scored: list[tuple[float, int, OverlayOcrLine]] = []
    for index, line in enumerate(lines):
        score = score_title_line(
            line,
            screen_height=screen_height,
        )
        if score > 0:
            scored.append((score, index, line))

    if not scored:
        fallback = [
            line.text
            for line in lines[:4]
            if not looks_like_price_line(line.text)
        ]
        return " ".join(fallback).strip() or None

    scored.sort(key=lambda entry: (entry[0], -entry[1]), reverse=True)
    _, best_index, best_line = scored[0]
    parts = [best_line.text]
    base_top = best_line.top if best_line.top is not None else 0
    last_bottom = best_line.bottom if best_line.bottom is not None else base_top

    for candidate in lines[best_index + 1 :]:
        if len(" ".join(parts)) >= 48:
            break
        if score_title_line(candidate, screen_height=screen_height) <= 0:
            break
        if candidate.top is not None and candidate.top - last_bottom > 120:
            break
        if candidate.top is not None and candidate.top - base_top > 220:
            break
        parts.append(candidate.text)
        last_bottom = candidate.bottom if candidate.bottom is not None else last_bottom
        if len(parts) >= 3:
            break

    return " ".join(dict.fromkeys(part.strip() for part in parts if part.strip())) or None


def extract_title_candidate_near_price(
    lines: list[OverlayOcrLine],
    *,
    price_anchor: OverlayOcrLine,
    screen_height: int | None,
) -> str | None:
    if price_anchor.top is None:
        return None

    anchored: list[tuple[float, int, OverlayOcrLine]] = []
    for index, line in enumerate(lines):
        if line is price_anchor:
            continue
        if line.bottom is None:
            continue
        vertical_gap = price_anchor.top - line.bottom
        if vertical_gap < -12 or vertical_gap > 280:
            continue
        if line.left is not None and price_anchor.left is not None and line.left - price_anchor.left > 220:
            continue
        score = score_title_line(line, screen_height=screen_height) + max(80 - max(vertical_gap, 0) * 0.4, 0)
        if score > 0:
            anchored.append((score, index, line))

    if not anchored:
        return None

    anchored.sort(key=lambda entry: (entry[0], -entry[1]), reverse=True)
    _, best_index, best_line = anchored[0]
    parts = [best_line.text]
    last_bottom = best_line.bottom if best_line.bottom is not None else 0

    for candidate in lines[best_index + 1 :]:
        if candidate is price_anchor:
            break
        if len(" ".join(parts)) >= 64:
            break
        if candidate.bottom is None or candidate.top is None:
            break
        if candidate.top - last_bottom > 48:
            break
        if looks_like_price_line(candidate.text):
            break
        if score_title_line(candidate, screen_height=screen_height) <= 0:
            break
        parts.append(candidate.text)
        last_bottom = candidate.bottom
        if len(parts) >= 3:
            break

    return " ".join(dict.fromkeys(part.strip() for part in parts if part.strip())) or None


def score_title_line(line: OverlayOcrLine, *, screen_height: int | None) -> float:
    text = line.text.strip()
    lowered = text.lower()
    if len(text) < 4:
        return -10
    if any(token in text for token in OVERLAY_TITLE_EXCLUDE_TOKENS):
        return -30
    if looks_like_price_line(text):
        return -40

    score = 0.0
    if 4 <= len(text) <= 40:
        score += 20
    if any(token in lowered or token in text for tokens in OVERLAY_DOMAIN_TOKENS.values() for token in tokens):
        score += 65
    if any(character.isdigit() for character in text):
        score += 12
    if screen_height and line.top is not None:
        vertical_ratio = line.top / max(screen_height, 1)
        if 0.08 <= vertical_ratio <= 0.72:
            score += 18
        elif vertical_ratio < 0.04 or vertical_ratio > 0.85:
            score -= 10
    if line.height >= 48:
        score += 8
    return score


def extract_listing_price(
    lines: list[OverlayOcrLine],
    *,
    screen_height: int | None,
) -> dict[str, Any]:
    best_value: Decimal | None = None
    best_text: str | None = None
    best_line: OverlayOcrLine | None = None
    best_score = float("-inf")

    for line in lines:
        text = line.text.strip()
        lowered = text.lower()
        if any(token in text for token in OVERLAY_PRICE_EXCLUDE_TOKENS):
            continue
        for match in OVERLAY_PRICE_PATTERN.finditer(text):
            value = parse_price_token(match.group(1), match.group(2))
            if value is None or value <= 0:
                continue
            score = 0.0
            if any(marker in text for marker in OVERLAY_PRICE_MARKERS):
                score += 80
            if len(text) <= 18:
                score += 15
            if screen_height and line.top is not None:
                vertical_ratio = line.top / max(screen_height, 1)
                if vertical_ratio <= 0.6:
                    score += 25
                elif vertical_ratio >= 0.85:
                    score -= 15
            if "到手" in text or "现价" in text or "售价" in text:
                score += 20
            if "原价" in text or "券后" in text:
                score -= 20
            if "%" in lowered:
                score -= 20
            if score > best_score:
                best_value = value
                best_text = text
                best_line = line
                best_score = score

    return {
        "price_decimal": best_value,
        "source_text": best_text,
        "source_line": best_line,
    }


def looks_like_price_line(text: str) -> bool:
    lowered = text.lower()
    if any(marker in text for marker in OVERLAY_PRICE_MARKERS):
        return True
    if "万" in text and any(character.isdigit() for character in text):
        return True
    if re.fullmatch(r"[¥￥]?\s*\d{2,6}(?:\.\d{1,2})?", lowered):
        return True
    return False


def parse_price_token(value: str, unit: str | None) -> Decimal | None:
    cleaned = value.replace(",", "").strip()
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        return None
    if unit and unit.lower() in {"w", "万"}:
        parsed *= Decimal("10000")
    return normalize_market_price(parsed)


def analyze_domain_candidate(
    session,
    *,
    task: CrawlTask,
    title_candidate: str | None,
    ocr_text: str,
    listing_price: Decimal | None,
) -> dict[str, Any] | None:
    title = title_candidate or ocr_text.strip()
    if not title:
        return None

    candidate_record = build_candidate_record(
        task=task,
        title=title,
        listing_price=listing_price,
    )
    pricing_records = load_pricing_records(
        session=session,
        business_domain=task.business_domain,
        freshness_days=30,
        heartbeat_days=3,
    )
    if not pricing_records:
        return None

    matched = match_pricing_row(
        pricing_records=pricing_records,
        task=task,
        title=title,
        candidate_record=candidate_record,
    )
    if matched is None:
        return None

    trend = build_overlay_trend_summary(
        session,
        pricing_records=pricing_records,
        business_domain=task.business_domain,
        product_label=str(matched["row"].get("product_label") or matched["row"].get("label")),
    )

    listing_price_float = decimal_to_float(listing_price)
    fair_price = matched["row"].get("fair_price")
    target_buy_ceiling = matched["row"].get("target_buy_ceiling")
    safe_buy_price = matched["row"].get("safe_buy_price")
    expected_profit_margin_pct = None
    if listing_price is not None and fair_price is not None and listing_price > 0:
        expected_profit_margin_pct = round(((Decimal(str(fair_price)) - listing_price) / listing_price) * Decimal("100"), 2)

    return {
        "business_domain": task.business_domain,
        "domain_label": domain_label(task.business_domain),
        "task_key": task.task_key,
        "task_display_name": task.display_name,
        "title_candidate": title,
        "candidate_record": serialize_candidate_record(candidate_record),
        "matched_view": matched["view"],
        "score": round(matched["score"], 2),
        "pricing": {
            "label": matched["row"].get("label"),
            "product_label": matched["row"].get("product_label"),
            "spec_label": matched["row"].get("spec_label"),
            "seller_sample_count": matched["row"].get("seller_sample_count"),
            "listing_count": matched["row"].get("listing_count"),
            "reliability_score": matched["row"].get("reliability_score"),
            "reliability_tier": matched["row"].get("reliability_tier"),
            "is_actionable": matched["row"].get("is_actionable"),
            "sample_confident": matched["row"].get("sample_confident"),
            "safe_buy_price": matched["row"].get("safe_buy_price"),
            "target_buy_ceiling": target_buy_ceiling,
            "fair_price": fair_price,
            "market_mid_price": matched["row"].get("market_mid_price"),
            "estimated_profit_floor": matched["row"].get("estimated_profit_floor"),
            "estimated_profit_ceiling": matched["row"].get("estimated_profit_ceiling"),
            "required_profit_amount": matched["row"].get("required_profit_amount"),
            "normal_margin_pct": matched["row"].get("normal_margin_pct"),
            "safe_margin_pct": matched["row"].get("safe_margin_pct"),
            "listing_price": listing_price_float,
            "expected_profit_margin_pct": float(expected_profit_margin_pct) if expected_profit_margin_pct is not None else None,
            "price_position": classify_price_position(
                listing_price=listing_price_float,
                safe_buy_price=safe_buy_price,
                target_buy_ceiling=target_buy_ceiling,
                fair_price=fair_price,
            ),
        },
        "trend": trend,
    }


def serialize_candidate_record(candidate_record: dict[str, Any] | None) -> dict[str, Any] | None:
    if candidate_record is None:
        return None
    return {
        "brand": candidate_record.get("brand"),
        "product_line": candidate_record.get("product_line"),
        "model_name": candidate_record.get("model_name"),
        "product_label": candidate_record.get("product_label"),
        "spec_label": candidate_record.get("spec_label"),
        "display_type": candidate_record.get("display_type"),
        "case_size_mm": candidate_record.get("case_size_mm"),
        "is_solar": candidate_record.get("is_solar"),
        "screen_size_in": candidate_record.get("screen_size_in"),
        "chip_family": candidate_record.get("chip_family"),
        "memory_gb": candidate_record.get("memory_gb"),
        "storage_gb": candidate_record.get("storage_gb"),
        "spec_status": candidate_record.get("spec_status"),
        "spec_confidence": candidate_record.get("spec_confidence"),
    }


def build_candidate_record(
    *,
    task: CrawlTask,
    title: str,
    listing_price: Decimal | None,
) -> dict[str, Any] | None:
    normalized = normalize_title(title)
    transient_item = Item(
        item_id=f"overlay:{task.business_domain}:{int(datetime.now(UTC).timestamp())}",
        task_id=task.id,
        source_platform=task.source_platform,
        business_domain=task.business_domain,
        source_keyword="mobile_overlay",
        title=title,
        normalized_brand=normalized["brand"],
        normalized_model_family=normalized["model_family"],
        normalized_model=normalized["model"],
        normalized_chip=normalized["chip"],
        normalized_memory_gb=normalized["memory_gb"],
        normalized_storage_gb=normalized["storage_gb"],
        condition_tags=[],
        region=None,
        listing_url=None,
        image_urls=[],
        is_auction=False,
        is_ad=False,
        has_video=False,
        current_price=listing_price,
        publish_time=None,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        last_snapshot_at=None,
        is_active=True,
    )
    return resolve_pricing_record(transient_item, None)


def match_pricing_row(
    *,
    pricing_records: list[dict[str, Any]],
    task: CrawlTask,
    title: str,
    candidate_record: dict[str, Any] | None,
) -> dict[str, Any] | None:
    product_rows = aggregate_pricing_view(
        records=pricing_records,
        view="product",
        min_sample_points=4,
    )
    spec_rows = aggregate_pricing_view(
        records=pricing_records,
        view="spec",
        min_sample_points=4,
    )
    ranked_rows: list[tuple[float, str, dict[str, Any]]] = []
    for view_name, rows in (("spec", spec_rows), ("product", product_rows)):
        for row in rows:
            score = pricing_row_match_score(
                row=row,
                view=view_name,
                title=title,
                candidate_record=candidate_record,
            )
            if score > 0:
                ranked_rows.append((score, view_name, row))

    if not ranked_rows:
        return None
    ranked_rows.sort(
        key=lambda entry: (
            entry[0],
            1 if entry[2].get("is_actionable") else 0,
            entry[2].get("reliability_score") or 0,
            entry[2].get("seller_sample_count") or 0,
        ),
        reverse=True,
    )
    score, view_name, row = ranked_rows[0]
    return {
        "score": score,
        "view": view_name,
        "row": row,
    }


def pricing_row_match_score(
    *,
    row: dict[str, Any],
    view: str,
    title: str,
    candidate_record: dict[str, Any] | None,
) -> float:
    title_key = normalize_overlay_key(title)
    row_label_key = normalize_overlay_key(str(row.get("label") or ""))
    product_key = normalize_overlay_key(str(row.get("product_label") or ""))
    spec_key = normalize_overlay_key(str(row.get("spec_label") or ""))
    candidate_product_key = normalize_overlay_key(str(candidate_record.get("product_label") or "")) if candidate_record else ""
    candidate_spec_key = normalize_overlay_key(str(candidate_record.get("spec_label") or "")) if candidate_record else ""
    normalized_title = normalize_title(title)
    family_key = normalize_overlay_key(str(normalized_title.get("model_family") or ""))
    model_key = normalize_overlay_key(str(normalized_title.get("model") or ""))
    screen_size_clue = extract_screen_size_clue(title)

    signal_score = 0.0
    if candidate_record:
        if candidate_spec_key and spec_key and candidate_spec_key == spec_key:
            signal_score += 180
        if candidate_product_key and product_key and candidate_product_key == product_key:
            signal_score += 120
        candidate_model_key = normalize_overlay_key(str(candidate_record.get("model_name") or ""))
        if candidate_model_key and candidate_model_key in row_label_key:
            signal_score += 36

    if row_label_key and row_label_key in title_key:
        signal_score += 84
    if product_key and product_key in title_key:
        signal_score += 72
    if spec_key and spec_key in title_key:
        signal_score += 60
    if family_key and family_key in title_key and family_key in (product_key or row_label_key):
        signal_score += 70
    if model_key and model_key in row_label_key:
        signal_score += 40
    if screen_size_clue and screen_size_clue in product_key:
        signal_score += 36
    if signal_score <= 0:
        return 0.0

    score = signal_score
    if view == "spec":
        score += 18
    if row.get("is_actionable"):
        score += 12
    score += float(row.get("reliability_score") or 0) / 12
    score += min(int(row.get("seller_sample_count") or 0), 30) / 6
    return score


def build_overlay_trend_summary(
    session,
    *,
    pricing_records: list[dict[str, Any]],
    business_domain: str,
    product_label: str,
) -> dict[str, Any] | None:
    tracked_items = {
        record["item_id"]: record
        for record in pricing_records
        if record.get("product_label") == product_label
    }
    if not tracked_items:
        return None

    window_limit = freshness_cutoff(window_days=30)
    stmt = (
        select(
            Item.item_id.label("item_id"),
            ItemSnapshot.snapshot_at.label("snapshot_at"),
            ItemSnapshot.price.label("price"),
        )
        .join(Item, Item.id == ItemSnapshot.item_id_ref)
        .where(
            Item.item_id.in_(tuple(tracked_items)),
            ItemSnapshot.snapshot_at >= window_limit,
            ItemSnapshot.price.is_not(None),
            ItemSnapshot.price > 0,
        )
        .order_by(ItemSnapshot.snapshot_at.asc(), ItemSnapshot.id.asc())
    )

    snapshots: list[dict[str, Any]] = []
    for row in session.execute(stmt).all():
        record = tracked_items.get(row.item_id)
        if record is None:
            continue
        normalized_price = normalize_market_price(
            row.price,
            business_domain=business_domain,
            model_family=record.get("product_line"),
        )
        if normalized_price is None or normalized_price <= 0:
            continue
        snapshots.append(
            {
                "item_id": row.item_id,
                "title": record.get("title"),
                "snapshot_at": row.snapshot_at,
                "price": float(normalized_price),
            }
        )

    candles = summarize_daily_snapshots(snapshots=snapshots, max_points=30)
    if not candles:
        return None
    chart = build_domain_trend_chart(
        domain_name=product_label,
        candles=candles,
    )
    if chart is None:
        return None
    quality = summarize_trend_quality(candles)
    return {
        "latest_close": chart["latest_close"],
        "latest_range_label": chart["latest_range_label"],
        "change_label": chart["change_label"],
        "volatility_label": chart["volatility_label"],
        "day_count": chart["day_count"],
        "trend_quality_ok": quality["trend_quality_ok"],
        "latest_sample_count": quality["latest_sample_count"],
        "recent_average_sample_count": quality["recent_average_sample_count"],
    }


def build_overlay_decision(
    *,
    listing_price: Decimal | None,
    best_match: dict[str, Any] | None,
) -> dict[str, Any]:
    if best_match is None:
        return {
            "status": "needs_review",
            "quick_flip_ok": False,
            "summary": "当前截图还没匹配到有效行情分组，建议回到控制页查看 OCR 文本或重截一张。",
            "risk_flags": ["未识别出可匹配的品类或型号"],
        }

    pricing = best_match["pricing"]
    trend = best_match.get("trend") or {}
    risk_flags: list[str] = []

    if listing_price is None:
        risk_flags.append("没有从截图里稳定识别到标价")
    if not pricing.get("sample_confident"):
        risk_flags.append("行情样本量不足，暂时只适合观察")
    if trend and not trend.get("trend_quality_ok"):
        risk_flags.append("近 30 天趋势样本偏少，趋势结论可信度一般")

    safe_buy_price = pricing.get("safe_buy_price")
    target_buy_ceiling = pricing.get("target_buy_ceiling")
    fair_price = pricing.get("fair_price")
    expected_profit_margin_pct = pricing.get("expected_profit_margin_pct")

    if listing_price is None or fair_price is None or target_buy_ceiling is None:
        return {
            "status": "needs_review",
            "quick_flip_ok": False,
            "summary": "已识别到品类，但缺少足够的标价或价格带信息，还不能直接判断是否适合快速收货。",
            "risk_flags": risk_flags or ["价格带信息不足"],
        }

    listing_price_float = float(listing_price)
    quick_flip_ok = bool(
        pricing.get("is_actionable")
        and pricing.get("sample_confident")
        and listing_price_float <= float(target_buy_ceiling)
    )

    if safe_buy_price is not None and listing_price_float <= float(safe_buy_price):
        status = "strong_yes" if quick_flip_ok else "watch"
        summary = (
            f"当前标价 {format_currency(listing_price_float)} 已落进安全收货价 "
            f"{format_currency(safe_buy_price)} 以内，属于优先关注区间。"
        )
    elif quick_flip_ok:
        status = "yes"
        summary = (
            f"当前标价 {format_currency(listing_price_float)} 落在目标收货上限 "
            f"{format_currency(target_buy_ceiling)} 内，可尝试快速收货。"
        )
    elif listing_price_float <= float(fair_price):
        status = "watch"
        summary = (
            f"当前标价 {format_currency(listing_price_float)} 低于市场中位价 "
            f"{format_currency(fair_price)}，但还没进入理想收货区，建议继续观察。"
        )
        risk_flags.append("当前价格没有进入目标收货上限")
    else:
        status = "no"
        summary = (
            f"当前标价 {format_currency(listing_price_float)} 高于目标收货上限 "
            f"{format_currency(target_buy_ceiling)}，不建议现在快速收货。"
        )
        risk_flags.append("当前价格高于目标收货上限")

    if expected_profit_margin_pct is not None and expected_profit_margin_pct < 10:
        risk_flags.append(f"按当前标价推算利润率约 {expected_profit_margin_pct:.2f}%")

    return {
        "status": status,
        "quick_flip_ok": quick_flip_ok,
        "summary": summary,
        "risk_flags": list(dict.fromkeys(risk_flags)),
    }


def build_overlay_vlm_payload(
    *,
    screenshot_base64: str,
    normalized_lines: list[OverlayOcrLine],
    screen_width: int | None,
    screen_height: int | None,
    source_package: str | None,
) -> dict[str, Any]:
    if not get_settings().mobile_overlay_vlm_enabled:
        return {
            "enabled": False,
            "used": False,
        }
    try:
        result = analyze_mobile_overlay_screenshot(
            screenshot_base64=screenshot_base64,
            ocr_lines=[
                {
                    "text": line.text,
                    "left": line.left,
                    "top": line.top,
                    "right": line.right,
                    "bottom": line.bottom,
                }
                for line in normalized_lines
            ],
            screen_width=screen_width,
            screen_height=screen_height,
            source_package=source_package,
        )
    except Exception as exc:
        return {
            "enabled": True,
            "used": False,
            "error": str(exc),
        }
    payload = result.to_payload()
    payload["enabled"] = True
    payload["used"] = True
    return payload


def choose_overlay_title_candidate(
    *,
    ocr_title_candidate: str | None,
    vlm_title_candidate: str | None,
    vlm_confidence: float | None,
) -> tuple[str | None, str]:
    if should_prefer_vlm_title(
        ocr_title_candidate=ocr_title_candidate,
        vlm_title_candidate=vlm_title_candidate,
        vlm_confidence=vlm_confidence,
    ):
        return vlm_title_candidate, "vlm"
    if ocr_title_candidate:
        return ocr_title_candidate, "ocr"
    if vlm_title_candidate:
        return vlm_title_candidate, "vlm"
    return None, "none"


def should_prefer_vlm_title(
    *,
    ocr_title_candidate: str | None,
    vlm_title_candidate: str | None,
    vlm_confidence: float | None,
) -> bool:
    if not vlm_title_candidate:
        return False
    if not ocr_title_candidate:
        return True
    ocr_normalized = normalize_title(ocr_title_candidate)
    vlm_normalized = normalize_title(vlm_title_candidate)
    if (vlm_confidence or 0.0) >= 0.8:
        return True
    if not ocr_normalized.get("brand") and vlm_normalized.get("brand"):
        return True
    if not ocr_normalized.get("model") and vlm_normalized.get("model"):
        return True
    if len(vlm_title_candidate) >= len(ocr_title_candidate) + 6 and (vlm_confidence or 0.0) >= 0.6:
        return True
    return False


def build_overlay_matching_text(
    *,
    ocr_text: str,
    vlm_payload: dict[str, Any] | None,
) -> str:
    parts = [ocr_text.strip()]
    if vlm_payload and not vlm_payload.get("error"):
        parts.extend(
            str(vlm_payload.get(key) or "").strip()
            for key in ("title_candidate", "brand_hint", "model_hint", "spec_hint", "price_hint", "reason")
        )
    return "\n".join(part for part in parts if part)


def overlay_analysis_rank(analysis: dict[str, Any]) -> tuple[float, float, float]:
    pricing = analysis.get("pricing") or {}
    trend = analysis.get("trend") or {}
    return (
        float(analysis.get("score") or 0),
        float(pricing.get("reliability_score") or 0),
        1.0 if trend.get("trend_quality_ok") else 0.0,
    )


def classify_price_position(
    *,
    listing_price: float | None,
    safe_buy_price: float | None,
    target_buy_ceiling: float | None,
    fair_price: float | None,
) -> str | None:
    if listing_price is None:
        return None
    if safe_buy_price is not None and listing_price <= safe_buy_price:
        return "safe"
    if target_buy_ceiling is not None and listing_price <= target_buy_ceiling:
        return "target"
    if fair_price is not None and listing_price <= fair_price:
        return "watch"
    return "expensive"


def build_text_excerpt(text: str, *, limit: int = 280) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def normalize_overlay_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())


def extract_screen_size_clue(title: str) -> str:
    match = re.search(r"(\d{2})\s*(?:寸|in|英寸)", title, flags=re.IGNORECASE)
    if not match:
        return ""
    return f"{match.group(1)}in"


def to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
