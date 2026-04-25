from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from ...category_compat import resolve_category_code
from ...compat import UTC
from ...db import session_scope
from ...models import CrawlTask, Item, ItemIngestRejection, ItemSnapshot
from ...normalizers import ExtractedItem, extract_items_from_response
from ...pricing import (
    decimal_to_float,
    resolve_domain_redirect_scope,
    title_domain_mismatch_reason,
    title_is_non_comparable_listing,
    title_matches_domain,
)
from ...settings import get_settings
from .review_ingest import contains_suspicious_listing_keyword, screen_suspicious_intake_candidates


def should_insert_snapshot(
    *,
    session,
    item_id_ref: int,
    extracted: Any,
) -> bool:
    latest_snapshot = session.execute(
        select(ItemSnapshot)
        .where(ItemSnapshot.item_id_ref == item_id_ref)
        .order_by(ItemSnapshot.snapshot_at.desc(), ItemSnapshot.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest_snapshot is None:
        return True

    return not (
        latest_snapshot.price == extracted.price
        and latest_snapshot.region == extracted.area
        and latest_snapshot.condition_tags == extracted.tags
        and latest_snapshot.publish_time == extracted.publish_time
    )


def mark_item_snapshot_timestamp(*, session, item_id_ref: int, snapshot_time: datetime | None = None) -> None:
    session.execute(
        update(Item)
        .where(Item.id == item_id_ref)
        .values(last_snapshot_at=snapshot_time or datetime.now(UTC))
    )


@dataclass(slots=True)
class PreparedListing:
    extracted: ExtractedItem
    page_number: int


@dataclass(frozen=True, slots=True)
class RejectedPreparedListing:
    listing: PreparedListing
    stage: str
    reason: str
    is_permanent: bool = True


@dataclass(slots=True)
class ListingCleanupResult:
    kept: list[PreparedListing]
    duplicate_item_count: int
    rejected_missing_price_count: int
    rejected_low_price_count: int
    price_reference: Decimal | None
    low_price_floor: Decimal | None


@dataclass(slots=True)
class CategoryIngestGateProfile:
    hard_block_keywords: tuple[str, ...] = ()
    accessory_block_keywords: tuple[str, ...] = ()
    accessory_price_ceiling: Decimal | None = None
    minimum_listing_price: Decimal | None = None
    minimum_listing_price_inclusive: bool = False
    require_numeric_signature: bool = False


MAX_CLEAN_TITLE_LENGTH = 500


CATEGORY_INGEST_GATE_PROFILES: dict[str, CategoryIngestGateProfile] = {
    "apple_computer": CategoryIngestGateProfile(
        hard_block_keywords=(
            "高价回收",
            "现金回收",
            "回收芯片",
            "回收ic",
            "回收电子元器件",
            "求购",
            "收个",
            "慢收",
            "代拍",
            "代购",
            "主板",
            "屏幕总成",
            "硬盘颗粒",
        ),
        accessory_block_keywords=(
            "空盒",
            "包装盒",
            "充电器",
            "电源线",
            "键帽",
            "保护壳",
            "保护膜",
            "贴膜",
            "支架",
            "扩展坞",
            "转接头",
            "转接器",
        ),
        accessory_price_ceiling=Decimal("800"),
        minimum_listing_price=Decimal("800"),
    ),
    "garmin_watch": CategoryIngestGateProfile(
        hard_block_keywords=(
            "高价回收",
            "现金回收",
            "回收佳明",
            "回收garmin",
            "求购",
            "收个",
            "代拍",
            "代购",
        ),
        accessory_block_keywords=(),
        accessory_price_ceiling=None,
        minimum_listing_price=Decimal("400"),
        minimum_listing_price_inclusive=True,
    ),
    "camera_body": CategoryIngestGateProfile(
        hard_block_keywords=("出租", "租赁", "租机", "租用", "回收", "置换", "代拍", "代购", "维修", "套机", "套装"),
        accessory_block_keywords=(
            "硅胶套",
            "相机套",
            "保护套",
            "转接环",
            "转接器",
            "机身盖",
            "镜头盖",
            "镜头后盖",
            "镜头前盖",
            "后盖",
            "前盖",
            "电池盖",
            "电池仓盖",
            "充电器",
            "防尘盖",
            "兔笼",
            "快门线",
            "遮光罩",
            "腕带",
            "肩带",
        ),
        accessory_price_ceiling=Decimal("800"),
        minimum_listing_price=Decimal("1000"),
    ),
    "camera_interchangeable_lens": CategoryIngestGateProfile(
        hard_block_keywords=("出租", "租赁", "租机", "租用", "回收", "置换", "代拍", "代购", "维修"),
        accessory_block_keywords=(
            "镜头盖",
            "镜头后盖",
            "镜头前盖",
            "后盖",
            "前盖",
            "遮光罩",
            "滤镜",
            "uv镜",
            "保护镜",
            "转接环",
            "接圈",
            "增倍镜",
            "脚架环",
            "三脚架环",
            "镜头包",
            "收纳包",
            "硅胶套",
            "保护套",
            "防尘盖",
        ),
        accessory_price_ceiling=Decimal("600"),
        minimum_listing_price=Decimal("800"),
        require_numeric_signature=True,
    ),
}


def prepare_listings_for_persistence(captures: list[Any]) -> ListingCleanupResult:
    seen_item_ids: set[str] = set()
    prepared: list[PreparedListing] = []
    duplicate_item_count = 0

    for capture in captures:
        for extracted in extract_items_from_response(capture.payload):
            if extracted.item_id in seen_item_ids:
                duplicate_item_count += 1
                continue
            seen_item_ids.add(extracted.item_id)
            prepared.append(PreparedListing(extracted=extracted, page_number=capture.page_number))

    priced_listings: list[PreparedListing] = []
    rejected_missing_price_count = 0
    for listing in prepared:
        price = listing.extracted.price
        if price is None or price <= 0:
            rejected_missing_price_count += 1
            continue
        priced_listings.append(listing)

    price_reference: Decimal | None = None
    low_price_floor: Decimal | None = None
    rejected_low_price_count = 0

    settings = get_settings()
    if len(priced_listings) >= settings.low_price_filter_min_samples:
        numeric_prices = [float(listing.extracted.price) for listing in priced_listings if listing.extracted.price is not None]
        mean_price = Decimal(str(round(statistics.mean(numeric_prices), 2)))
        median_price = Decimal(str(round(statistics.median(numeric_prices), 2)))
        price_reference = max(mean_price, median_price)
        low_price_floor = (price_reference * Decimal(str(settings.low_price_filter_ratio))).quantize(Decimal("0.01"))

        filtered = [listing for listing in priced_listings if listing.extracted.price is not None and listing.extracted.price >= low_price_floor]
        if filtered:
            rejected_low_price_count = len(priced_listings) - len(filtered)
            priced_listings = filtered
        else:
            low_price_floor = None
            price_reference = None

    return ListingCleanupResult(
        kept=priced_listings,
        duplicate_item_count=duplicate_item_count,
        rejected_missing_price_count=rejected_missing_price_count,
        rejected_low_price_count=rejected_low_price_count,
        price_reference=price_reference,
        low_price_floor=low_price_floor,
    )


def build_intake_review_candidate(
    *,
    business_domain: str,
    source_keyword: str,
    extracted: ExtractedItem,
) -> dict[str, Any]:
    return {
        "item_id": extracted.item_id,
        "business_domain": business_domain,
        "source_keyword": source_keyword,
        "title": extracted.title,
        "current_price": decimal_to_float(extracted.price),
        "condition_tags": extracted.tags or [],
        "region": extracted.area,
    }


def filter_suspicious_prepared_listings_for_ingest(
    *,
    task: CrawlTask,
    source_keyword: str,
    listings: list[PreparedListing],
) -> tuple[list[PreparedListing], dict[str, Any], list[RejectedPreparedListing]]:
    suspicious_candidates: list[dict[str, Any]] = []
    suspicious_item_ids: set[str] = set()
    blocked_reasons: defaultdict[str, int] = defaultdict(int)
    decisions_by_item_id: dict[str, dict[str, Any]] = {}

    for listing in listings:
        if not contains_suspicious_listing_keyword(
            title=listing.extracted.title,
        ):
            continue
        suspicious_item_ids.add(listing.extracted.item_id)
        suspicious_candidates.append(
            build_intake_review_candidate(
                business_domain=task.business_domain,
                source_keyword=source_keyword,
                extracted=listing.extracted,
            )
        )

    if suspicious_candidates:
        decisions_by_item_id = {
            decision["item_id"]: decision
            for decision in screen_suspicious_intake_candidates(candidates=suspicious_candidates)
        }

    kept: list[PreparedListing] = []
    rejected: list[RejectedPreparedListing] = []
    valid_count = 0
    blocked_count = 0
    for listing in listings:
        item_id = listing.extracted.item_id
        if item_id not in suspicious_item_ids:
            kept.append(listing)
            continue
        decision = decisions_by_item_id.get(item_id)
        if decision is not None and decision.get("is_valid") is True:
            kept.append(listing)
            valid_count += 1
            continue
        blocked_count += 1
        reason = None
        if decision is not None and decision.get("invalid_reason") is not None:
            reason = str(decision["invalid_reason"]).strip() or None
        resolved_reason = reason or "review_failed"
        blocked_reasons[resolved_reason] += 1
        rejected.append(
            RejectedPreparedListing(
                listing=listing,
                stage="suspicious_intake",
                reason=resolved_reason,
            )
        )

    return kept, {
        "candidate_count": len(suspicious_candidates),
        "valid_count": valid_count,
        "blocked_count": blocked_count,
        "blocked_reasons": dict(sorted(blocked_reasons.items())),
    }, rejected


def filter_title_length_prepared_listings_for_ingest(
    *,
    listings: list[PreparedListing],
) -> tuple[list[PreparedListing], dict[str, Any], list[RejectedPreparedListing]]:
    kept: list[PreparedListing] = []
    rejected: list[RejectedPreparedListing] = []
    blocked_reasons: defaultdict[str, int] = defaultdict(int)
    for listing in listings:
        reason = classify_title_length_ingest_block_reason(title=listing.extracted.title)
        if reason is None:
            kept.append(listing)
            continue
        blocked_reasons[reason] += 1
        rejected.append(
            RejectedPreparedListing(
                listing=listing,
                stage="title_length_gate",
                reason=reason,
            )
        )

    return kept, {
        "candidate_count": len(listings),
        "blocked_count": len(rejected),
        "blocked_reasons": dict(sorted(blocked_reasons.items())),
    }, rejected


def filter_category_profile_prepared_listings_for_ingest(
    *,
    task: CrawlTask,
    source_keyword: str,
    listings: list[PreparedListing],
) -> tuple[list[PreparedListing], dict[str, Any], list[RejectedPreparedListing]]:
    profile = CATEGORY_INGEST_GATE_PROFILES.get(resolve_category_code(task.business_domain))
    if profile is None or not listings:
        return listings, {
            "candidate_count": len(listings),
            "blocked_count": 0,
            "blocked_reasons": {},
        }, []

    kept: list[PreparedListing] = []
    rejected: list[RejectedPreparedListing] = []
    blocked_reasons: defaultdict[str, int] = defaultdict(int)
    for listing in listings:
        reason = classify_category_ingest_block_reason(
            category_code=resolve_category_code(task.business_domain),
            title=listing.extracted.title,
            price=listing.extracted.price,
            source_keyword=source_keyword,
            profile=profile,
        )
        if reason is None:
            kept.append(listing)
            continue
        blocked_reasons[reason] += 1
        rejected.append(
            RejectedPreparedListing(
                listing=listing,
                stage="category_gate",
                reason=reason,
                is_permanent=is_permanent_category_gate_reason(
                    category_code=resolve_category_code(task.business_domain),
                    reason=reason,
                ),
            )
        )

    return kept, {
        "candidate_count": len(listings),
        "blocked_count": len(listings) - len(kept),
        "blocked_reasons": dict(sorted(blocked_reasons.items())),
    }, rejected


def classify_category_ingest_block_reason(
    *,
    category_code: str | None = None,
    title: str,
    price: Decimal | None,
    source_keyword: str,
    profile: CategoryIngestGateProfile,
) -> str | None:
    normalized_title = normalize_ingest_gate_text(title)
    for keyword in profile.hard_block_keywords:
        if normalize_ingest_gate_text(keyword) in normalized_title:
            return f"hard_block:{keyword}"

    if category_code and title_is_non_comparable_listing(
        business_domain=category_code,
        title=title,
        price=price,
    ):
        return "non_comparable_title"

    if category_code and not title_matches_domain(category_code, title):
        redirect_scope = resolve_domain_redirect_scope(category_code, title)
        if redirect_scope:
            return f"domain_redirect:{redirect_scope}"
        mismatch_reason = title_domain_mismatch_reason(category_code, title)
        if mismatch_reason:
            return f"domain_mismatch:{mismatch_reason}"
        return "domain_mismatch"

    if price is not None and profile.minimum_listing_price is not None:
        if profile.minimum_listing_price_inclusive:
            if price <= profile.minimum_listing_price:
                return "price_floor"
        elif price < profile.minimum_listing_price:
            return "price_floor"

    if (
        price is not None
        and profile.accessory_price_ceiling is not None
        and price <= profile.accessory_price_ceiling
    ):
        for keyword in profile.accessory_block_keywords:
            if normalize_ingest_gate_text(keyword) in normalized_title:
                return f"accessory:{keyword}"

    if profile.require_numeric_signature and not title_matches_source_numeric_signature(
        title=title,
        source_keyword=source_keyword,
    ):
        return "signature_mismatch"

    return None


def is_permanent_category_gate_reason(*, category_code: str | None, reason: str | None) -> bool:
    normalized_reason = str(reason or "").strip().lower()
    resolved_category_code = resolve_category_code(category_code)
    if not normalized_reason:
        return True
    if normalized_reason.startswith("domain_redirect:"):
        return False
    if resolved_category_code == "camera_body" and normalized_reason.startswith("domain_mismatch"):
        return False
    if resolved_category_code == "camera_interchangeable_lens" and normalized_reason.startswith("domain_mismatch"):
        return False
    return True


def classify_title_length_ingest_block_reason(*, title: str | None) -> str | None:
    if len(str(title or "")) > MAX_CLEAN_TITLE_LENGTH:
        return f"title_length_gt_{MAX_CLEAN_TITLE_LENGTH}"
    return None


def classify_ingest_block_reason(
    *,
    task: CrawlTask,
    source_keyword: str,
    extracted: ExtractedItem,
) -> tuple[str | None, str | None]:
    title_length_reason = classify_title_length_ingest_block_reason(title=extracted.title)
    if title_length_reason is not None:
        return "title_length_gate", title_length_reason

    profile = CATEGORY_INGEST_GATE_PROFILES.get(resolve_category_code(task.business_domain))
    if profile is None:
        return None, None
    category_reason = classify_category_ingest_block_reason(
        category_code=resolve_category_code(task.business_domain),
        title=extracted.title,
        price=extracted.price,
        source_keyword=source_keyword,
        profile=profile,
    )
    if category_reason is None:
        return None, None
    return "category_gate", category_reason


def normalize_ingest_gate_text(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def title_matches_source_numeric_signature(*, title: str, source_keyword: str) -> bool:
    signature_tokens = extract_source_numeric_signature_tokens(source_keyword)
    if not signature_tokens:
        return True
    title_signature = canonical_signature_text(title)
    return all(token in title_signature for token in signature_tokens)


def extract_source_numeric_signature_tokens(source_keyword: str) -> list[str]:
    raw_tokens = re.findall(r"\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?", str(source_keyword or "").lower())
    canonical_tokens: list[str] = []
    for token in raw_tokens:
        canonical = canonical_signature_text(token)
        if canonical and canonical not in canonical_tokens:
            canonical_tokens.append(canonical)
    if len(canonical_tokens) >= 2:
        return [canonical_tokens[0], canonical_tokens[-1]]
    return canonical_tokens[:1]


def canonical_signature_text(value: str | None) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(value or "").lower())


def should_allow_suspicious_listing_ingest(
    *,
    business_domain: str,
    source_keyword: str,
    extracted: ExtractedItem,
) -> tuple[bool, str | None]:
    if not contains_suspicious_listing_keyword(
        title=extracted.title,
    ):
        return True, None

    decisions = screen_suspicious_intake_candidates(
        candidates=[
            build_intake_review_candidate(
                business_domain=business_domain,
                source_keyword=source_keyword,
                extracted=extracted,
            )
        ]
    )
    if decisions and decisions[0].get("is_valid") is True:
        return True, None
    reason = None
    if decisions and decisions[0].get("invalid_reason") is not None:
        reason = str(decisions[0]["invalid_reason"]).strip() or None
    return False, reason or "review_failed"


def load_ingest_rejection_item_ids(
    *,
    source_platform: str,
    item_ids: list[str],
) -> set[str]:
    unique_item_ids = sorted({item_id for item_id in item_ids if item_id})
    if not unique_item_ids:
        return set()
    with session_scope() as session:
        return load_ingest_rejection_item_ids_with_session(
            session=session,
            source_platform=source_platform,
            item_ids=unique_item_ids,
        )


def load_ingest_rejection_item_ids_with_session(
    *,
    session,
    source_platform: str,
    item_ids: list[str],
) -> set[str]:
    unique_item_ids = sorted({item_id for item_id in item_ids if item_id})
    if not unique_item_ids:
        return set()
    rows = session.execute(
        select(ItemIngestRejection.item_id).where(
            ItemIngestRejection.source_platform == source_platform,
            ItemIngestRejection.item_id.in_(unique_item_ids),
            ItemIngestRejection.rejection_stage.not_like("transient:%"),
        )
    ).scalars()
    return set(rows)


def split_permanently_rejected_prepared_listings(
    *,
    source_platform: str,
    listings: list[PreparedListing],
) -> tuple[list[PreparedListing], list[str]]:
    rejected_item_ids = load_ingest_rejection_item_ids(
        source_platform=source_platform,
        item_ids=[listing.extracted.item_id for listing in listings],
    )
    if not rejected_item_ids:
        return listings, []
    kept = [listing for listing in listings if listing.extracted.item_id not in rejected_item_ids]
    return kept, sorted(rejected_item_ids)


def touch_item_ingest_rejections(
    *,
    session,
    source_platform: str,
    item_ids: list[str],
) -> int:
    unique_item_ids = sorted({item_id for item_id in item_ids if item_id})
    if not unique_item_ids:
        return 0
    result = session.execute(
        update(ItemIngestRejection)
        .where(ItemIngestRejection.source_platform == source_platform)
        .where(ItemIngestRejection.item_id.in_(unique_item_ids))
        .values(
            hit_count=ItemIngestRejection.hit_count + 1,
            last_rejected_at=func.now(),
            updated_at=func.now(),
        )
    )
    return int(result.rowcount or 0)


def upsert_item_ingest_rejection(
    *,
    session,
    source_platform: str,
    item_id: str,
    business_domain: str | None,
    category_id: str | None,
    rejection_stage: str,
    rejection_reason: str,
) -> None:
    stmt = insert(ItemIngestRejection).values(
        source_platform=source_platform,
        item_id=item_id,
        business_domain=business_domain,
        category_id=category_id,
        rejection_stage=rejection_stage,
        rejection_reason=rejection_reason,
        hit_count=1,
        first_rejected_at=func.now(),
        last_rejected_at=func.now(),
        created_at=func.now(),
        updated_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            ItemIngestRejection.source_platform,
            ItemIngestRejection.item_id,
        ],
        set_={
            "business_domain": stmt.excluded.business_domain,
            "category_id": stmt.excluded.category_id,
            "rejection_stage": stmt.excluded.rejection_stage,
            "rejection_reason": stmt.excluded.rejection_reason,
            "hit_count": ItemIngestRejection.hit_count + 1,
            "last_rejected_at": func.now(),
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)


def upsert_item_ingest_rejections(
    *,
    session,
    task: CrawlTask,
    rejected: list[RejectedPreparedListing],
) -> int:
    recorded = 0
    for rejection in rejected:
        rejection_stage = rejection.stage
        if not rejection.is_permanent:
            rejection_stage = f"transient:{rejection.stage}"
        upsert_item_ingest_rejection(
            session=session,
            source_platform=task.source_platform,
            item_id=rejection.listing.extracted.item_id,
            business_domain=task.business_domain,
            category_id=task.category_id,
            rejection_stage=rejection_stage,
            rejection_reason=rejection.reason,
        )
        recorded += 1
    return recorded
