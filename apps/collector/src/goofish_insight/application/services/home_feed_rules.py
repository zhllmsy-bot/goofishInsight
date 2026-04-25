from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ...category_compat import compatible_scope_keys, display_label_for_scope, resolve_category_code, token_aliases_for_scope
from ...models import CrawlTask, Item, SellerProfile
from ...pricing import decimal_to_float, title_matches_domain
from ...application.services.pricing_eligibility import float_to_decimal
from ...application.services.seller_classification import COMMERCIAL_NAME_TOKENS


@dataclass(slots=True)
class FeedCardCandidate:
    item_id: str
    category_id: str | None
    tb_cat_id: str | None
    c_cat_id: str | None
    listing_url: str | None
    title: str
    raw_text: str
    price: Decimal | None
    position: int


@dataclass(slots=True)
class FeedTargetMatch:
    business_domain: str
    task: CrawlTask
    view: str
    label: str
    product_label: str | None
    spec_label: str | None
    target_buy_ceiling: Decimal | None
    fair_price: Decimal | None
    expected_profit_floor: Decimal | None
    is_actionable: bool
    pricing_row: dict[str, Any] | None


@dataclass(slots=True)
class FeedDetailSellerSnapshot:
    seller_id: str | None
    seller_name: str | None
    region: str | None
    last_active_label: str | None
    sold_count: int | None
    years_on_platform: int | None
    review_rate_pct: int | None
    level_token_count: int | None
    level_texts: tuple[str, ...]
    badge_texts: tuple[str, ...]
    profile_url: str | None


FEED_COMMERCIAL_BADGE_TOKENS: tuple[str, ...] = (
    "鱼小铺",
    "官方",
    "专营",
    "严选",
)

CATEGORY_SCOPE_PRIORITY = (
    "camera_interchangeable_lens",
    "camera_body",
    "graphics_card",
    "phone",
    "garmin_watch",
    "apple_airpods",
    "apple_computer",
)


def resolve_feed_seller_type(
    *,
    card: FeedCardCandidate,
    existing_item: Item | None,
    seller_profiles: dict[int, SellerProfile],
) -> str | None:
    if existing_item is not None and existing_item.seller_profile_id is not None:
        seller_profile = seller_profiles.get(int(existing_item.seller_profile_id))
        seller_type = normalize_feed_seller_type(
            (seller_profile.metadata_json or {}).get("sellerType") if seller_profile is not None else None
        )
        if seller_type is not None:
            return seller_type
    lowered_text = card.raw_text.lower()
    if any(token.lower() in lowered_text for token in FEED_COMMERCIAL_BADGE_TOKENS):
        return "commercial_like"
    return "unknown"


def classify_feed_detail_seller_snapshot(
    *,
    snapshot: FeedDetailSellerSnapshot,
) -> tuple[str | None, list[str]]:
    if snapshot.level_token_count is not None:
        if snapshot.level_token_count >= 2:
            return "commercial_like", [f"detail_level_token_count={snapshot.level_token_count}"]
        if snapshot.level_token_count == 1:
            return "private_like", ["detail_level_token_count=1"]

    seller_name = str(snapshot.seller_name or "")
    commercial_name_hits = [token for token in COMMERCIAL_NAME_TOKENS if token in seller_name]
    if commercial_name_hits:
        return "commercial_like", [f"detail_name:{'/'.join(commercial_name_hits[:3])}"]

    badge_hits = [
        token
        for token in FEED_COMMERCIAL_BADGE_TOKENS
        if any(token in value for value in (*snapshot.badge_texts, *snapshot.level_texts))
    ]
    if badge_hits:
        return "commercial_like", [f"detail_badge:{'/'.join(badge_hits[:3])}"]

    if snapshot.sold_count is not None and snapshot.sold_count >= 100:
        return "commercial_like", [f"detail_sold_count={snapshot.sold_count}"]

    if snapshot.seller_name:
        return "private_like", ["detail_seller_name_present"]
    return None, []


def normalize_feed_seller_type(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"commercial_like", "private_like", "unknown"}:
        return normalized
    return None


def determine_feed_candidate_domains(
    *,
    card: FeedCardCandidate,
    existing_item: Item | None,
    tasks_by_domain: dict[str, CrawlTask],
    business_domain: str | None,
    mapped_domain: str | None = None,
) -> list[str]:
    domains: list[str] = []
    if business_domain:
        requested_scope = resolve_category_code(business_domain)
        return [requested_scope] if requested_scope in tasks_by_domain else []
    if mapped_domain:
        resolved_mapped_domain = resolve_category_code(mapped_domain) or mapped_domain
        if existing_item is None:
            return [resolved_mapped_domain] if resolved_mapped_domain in tasks_by_domain else []
        if resolved_mapped_domain in tasks_by_domain and resolved_mapped_domain not in domains:
            domains.append(resolved_mapped_domain)
    if existing_item is not None:
        for scope_key in compatible_scope_keys(existing_item.business_domain):
            resolved_scope = resolve_category_code(scope_key) or scope_key
            if resolved_scope in tasks_by_domain and resolved_scope not in domains:
                domains.append(resolved_scope)
    for domain in tasks_by_domain:
        if domain in domains:
            continue
        if title_matches_domain(domain, card.title):
            domains.append(domain)
    return domains


def resolve_feed_collection_scope_domain(
    *,
    mapped_domain: str | None,
    tasks_by_domain: dict[str, CrawlTask],
) -> str | None:
    if not mapped_domain:
        return None
    resolved_mapped_domain = resolve_category_code(mapped_domain) or mapped_domain
    if resolved_mapped_domain not in tasks_by_domain:
        return None
    return resolved_mapped_domain


def should_open_feed_detail_for_task(
    *,
    mapped_domain: str | None,
    task: CrawlTask | None,
    tasks_by_domain: dict[str, CrawlTask],
) -> bool:
    collection_scope_domain = resolve_feed_collection_scope_domain(
        mapped_domain=mapped_domain,
        tasks_by_domain=tasks_by_domain,
    )
    if collection_scope_domain is None or task is None:
        return False
    task_scope = resolve_category_code(task.business_domain) or task.business_domain
    return task_scope == collection_scope_domain


def should_open_feed_detail_for_match(
    *,
    mapped_domain: str | None,
    task: CrawlTask | None,
    match: FeedTargetMatch | None,
    tasks_by_domain: dict[str, CrawlTask],
) -> bool:
    if match is None:
        return False
    return should_open_feed_detail_for_task(
        mapped_domain=mapped_domain,
        task=task,
        tasks_by_domain=tasks_by_domain,
    )


def build_feed_target_match(*, task: CrawlTask, view: str, row: dict[str, Any]) -> FeedTargetMatch:
    return FeedTargetMatch(
        business_domain=task.business_domain,
        task=task,
        view=view,
        label=row["label"],
        product_label=row.get("product_label"),
        spec_label=row.get("spec_label"),
        target_buy_ceiling=float_to_decimal(row.get("target_buy_ceiling")),
        fair_price=float_to_decimal(row.get("fair_price")),
        expected_profit_floor=float_to_decimal(row.get("estimated_profit_floor")),
        is_actionable=bool(row.get("is_actionable")),
        pricing_row=row,
    )


def feed_target_priority(view: str, row: dict[str, Any]) -> tuple[int, float, float, int]:
    base = 2 if view == "spec" else 1
    actionable_bonus = 10 if row.get("is_actionable") else 0
    opportunity = float(row.get("opportunity_score") or 0)
    reliability = float(row.get("reliability_score") or 0)
    sample_count = int(row.get("seller_sample_count") or 0)
    return base + actionable_bonus, opportunity, reliability, sample_count


def match_feed_title_to_task_lexicon(title: str, task: CrawlTask) -> str | None:
    def compact_for_match(value: str) -> str:
        compact = re.sub(r"[\s\-_+/（）()]+", "", value.lower())
        for token in ("eos", "机身", "单机", "微单", "body"):
            compact = compact.replace(token, "")
        return compact

    lowered = title.lower()
    compact_title = compact_for_match(title)
    generic_tokens = {
        str(token).strip().lower()
        for token in (
            *(task.brand_lexicon or []),
            "apple",
            "garmin",
            "苹果",
            "佳明",
        )
        if str(token).strip()
    }
    candidates = list(task.model_lexicon or [])
    candidates.extend(token for token in (task.keywords or []) if token.lower() not in generic_tokens)
    candidates.sort(key=len, reverse=True)
    for token in candidates:
        lowered_token = token.lower()
        compact_token = compact_for_match(token)
        if lowered_token in lowered or (compact_token and compact_token in compact_title):
            return token
    return None


def should_message_feed_target(
    *,
    card: FeedCardCandidate,
    match: FeedTargetMatch | None,
    seller_type: str | None,
    max_messages: int,
    sent_count: int,
    require_actionable_band: bool,
    only_within_target_price: bool,
    min_profit_margin_pct: Decimal,
) -> tuple[bool, str]:
    del card
    del only_within_target_price
    del min_profit_margin_pct
    if sent_count >= max_messages:
        return False, "message_cap_reached"
    normalized_seller_type = normalize_feed_seller_type(seller_type) or "unknown"
    if normalized_seller_type == "commercial_like":
        return False, "seller_commercial_like"
    if normalized_seller_type != "private_like":
        return False, "seller_type_unknown"
    if not require_actionable_band:
        return True, "eligible"
    if match is None:
        return False, "not_target"
    if require_actionable_band and not match.is_actionable:
        return False, "not_actionable"
    if match.target_buy_ceiling is None:
        return False, "missing_safe_price"
    return True, "eligible"


def compute_feed_expected_profit_margin_pct(
    *,
    card: FeedCardCandidate,
    match: FeedTargetMatch | None,
) -> Decimal | None:
    if match is None or card.price is None or match.fair_price is None:
        return None
    if card.price <= 0:
        return None
    margin_pct = ((match.fair_price - card.price) / card.price) * Decimal("100")
    return margin_pct.quantize(Decimal("0.01"))


def build_feed_outreach_message_text(
    *,
    card: FeedCardCandidate,
    match: FeedTargetMatch | None,
    message_template: str,
) -> str:
    safe_price = match.target_buy_ceiling if match is not None else None
    fair_price = match.fair_price if match is not None else None
    substitutions = defaultdict(
        str,
        {
            "safe_price": format_feed_message_price(safe_price),
            "safe_price_raw": decimal_to_float(safe_price) if safe_price is not None else "",
            "fair_price": format_feed_message_price(fair_price),
            "fair_price_raw": decimal_to_float(fair_price) if fair_price is not None else "",
            "category_name": display_label_for_scope(match.business_domain) if match is not None else "目标品类",
            "target_label": match.label if match is not None else "",
            "listing_price": format_feed_message_price(card.price),
            "listing_price_raw": decimal_to_float(card.price) if card.price is not None else "",
        },
    )
    return str(message_template).format_map(substitutions).strip()


def build_feed_detail_url(
    *,
    item_id: str,
    category_id: str | None = None,
    listing_url: str | None = None,
) -> str:
    normalized_listing_url = str(listing_url or "").strip()
    if normalized_listing_url:
        return normalized_listing_url
    normalized_item_id = str(item_id or "").strip()
    if not normalized_item_id:
        raise ValueError("item_id is required to build a Goofish detail URL.")
    normalized_category_id = str(category_id or "").strip()
    if normalized_category_id:
        return f"https://www.goofish.com/item?id={normalized_item_id}&categoryId={normalized_category_id}"
    return f"https://www.goofish.com/item?id={normalized_item_id}"


def infer_scope_from_feed_title(title: str) -> str | None:
    for scope in CATEGORY_SCOPE_PRIORITY:
        if title_matches_domain(scope, title):
            return scope
    return None


def format_feed_message_price(value: Decimal | None) -> str:
    if value is None:
        return "-"
    quantized = value.quantize(Decimal("0.01"))
    if quantized == quantized.quantize(Decimal("1")):
        return f"¥{int(quantized)}"
    text = format(quantized.normalize(), "f")
    return f"¥{text.rstrip('0').rstrip('.')}"
