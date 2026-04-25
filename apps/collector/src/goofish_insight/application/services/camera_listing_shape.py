from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ...category_compat import resolve_category_code
from ...models import Category, CategoryRuntimeProfile, Item, ItemIngestRejection
from ...pricing import (
    CAMERA_BODY_ALWAYS_EXPLICIT_TOKENS,
    CAMERA_BODY_BUNDLE_TOKENS,
    CAMERA_BODY_COMPACT_SAFE_SIGNATURES,
    CAMERA_BODY_CONTEXTUAL_TOKENS,
    CAMERA_BODY_MODEL_PATTERNS,
    CAMERA_BODY_NON_TARGET_PACKAGING_PATTERNS,
    CAMERA_BODY_NON_TARGET_PART_TOKENS,
    CAMERA_BRAND_TOKENS,
    CAMERA_LENS_COMPACT_PATTERNS,
    CAMERA_LENS_COMPACT_SIGNATURES,
    CAMERA_LENS_DESCRIPTOR_TOKENS,
    CAMERA_LENS_KEYWORD_TOKENS,
    CAMERA_LENS_MOUNT_PATTERNS,
    CAMERA_LENS_NORMALIZED_PATTERNS,
    CAMERA_LENS_PRIME_SIGNATURE_PATTERNS,
    CAMERA_LENS_TIGHT_SIGNATURE_PATTERNS,
    CAMERA_LENS_ZOOM_SIGNATURE_PATTERNS,
    CAMERA_NON_TARGET_LIGHTING_TOKENS,
)

CAMERA_CATEGORY_CODES: tuple[str, str] = ("camera_body", "camera_interchangeable_lens")

BODY_SHAPES: tuple[str, ...] = ("body_only", "body_bundle")
LENS_SHAPES: tuple[str, ...] = ("lens_only", "lens_bundle")
BLOCK_SHAPES: tuple[str, ...] = ("rental_or_service", "commercial_menu", "accessory_or_part")

CAMERA_RENTAL_SERVICE_TOKENS: tuple[str, ...] = (
    "出租",
    "租赁",
    "租机",
    "租用",
    "免押",
    "押金",
    "租期",
    "日租",
)
CAMERA_COMMERCIAL_MENU_TOKENS: tuple[str, ...] = (
    "搭配",
    "套机",
    "套装",
    "套餐",
    "单机",
    "单机身",
    "可选",
    "另配",
    "咨询客服",
    "联系客服",
    "型号齐全",
    "现货",
)
CAMERA_ACCESSORY_CONTEXT_TOKENS: tuple[str, ...] = (
    "适用",
    "适配",
    "专用",
    "配件",
    "维修",
    "拆机",
    "更换",
)
CAMERA_COMPATIBILITY_PREFIX_TOKENS: tuple[str, ...] = (
    "适合",
    "适配",
    "适用于",
    "支持",
    "转接",
    "可转接",
    "兼容",
)
CAMERA_BODY_META_TOKENS: tuple[str, ...] = (
    "机身号",
    "机身编号",
    "机身序列号",
)
CAMERA_LENS_ABSENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:不含|不带|没有|无)\s*(?:原装|套装|套头|标配|附带)?镜头", re.IGNORECASE),
    re.compile(r"(?:镜头|套头)(?:另售|另出|不出|已出)", re.IGNORECASE),
    re.compile(r"(?:镜头|套头).{0,2}(?:单出|另卖)", re.IGNORECASE),
)
CAMERA_BODY_EXTRA_MODEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![a-z0-9])d(?:3|4|5|6|7|8)\d{2,3}(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:5d|6d|7d|70d|80d|90d|1dx)(?:\s*(?:mark\s*)?(?:ii|iii|iv|2|3|4))?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])(?:xt|x-t)\s*20(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])z\s*r(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])z(?:5|6|7|8|9|30|50)(?:ll|iii|ii|2|3|二代|三代)?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])s5m2xk?(?![a-z0-9])", re.IGNORECASE),
)
CAMERA_BODY_EXTRA_COMPACT_SIGNATURES: tuple[str, ...] = (
    "d750",
    "d780",
    "d850",
    "d7500",
    "5dmarkii",
    "5dmarkiii",
    "5dmarkiv",
    "5d2",
    "5d3",
    "5d4",
    "6d2",
    "xt20",
    "z50ll",
    "z6ll",
    "z7ll",
    "s5m2xk",
)
CAMERA_KIT_ZOOM_PATTERN = re.compile(
    r"(?<!\d)(?:1[2-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])\s*[-~至到/]\s*(?:[2-9]\d|1\d{2})(?:\s*mm)?(?!\d)",
    re.IGNORECASE,
)
CAMERA_EXPLICIT_LENS_PRESENT_PATTERN = re.compile(
    r"(?:带|含|配|搭配|套装|套机|送).{0,18}(?:镜头|(?:1[2-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])\s*[-~至到/]\s*(?:[2-9]\d|1\d{2}))",
    re.IGNORECASE,
)
CAMERA_COMMERCIAL_MENU_PATTERN = re.compile(
    r"(?:单机身?|机身).{0,16}(?:[:：]|售价|价格|报价|\d{4,5}).{0,40}(?:搭配|套机|套装|套餐)",
    re.IGNORECASE,
)
CAMERA_LENS_SLANG_TOKENS: tuple[str, ...] = (
    "g大师",
    "大三元",
    "小痰盂",
    "天涯镜",
    "狗头",
)
CAMERA_LENS_NICKNAME_SIGNATURES: tuple[str, ...] = (
    "1770",
    "2470",
    "247028",
    "1024",
    "5018",
    "5014",
    "8518",
    "8514",
)


@dataclass(frozen=True, slots=True)
class CameraListingShapeDecision:
    current_category_code: str | None
    shape: str
    recommended_action: str
    target_category_code: str | None
    reason: str
    confidence: float
    signals: dict[str, bool | int | str | None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_category_code": self.current_category_code,
            "shape": self.shape,
            "recommended_action": self.recommended_action,
            "target_category_code": self.target_category_code,
            "reason": self.reason,
            "confidence": round(float(self.confidence), 4),
            "signals": dict(self.signals),
        }


def evaluate_camera_listing_shape(
    *,
    current_category_code: str | None,
    title: str | None,
) -> CameraListingShapeDecision:
    resolved_category_code = resolve_category_code(current_category_code)
    normalized, compact, slug = _normalize_camera_title(title)
    if not normalized:
        return _decision(
            current_category_code=resolved_category_code,
            shape="unknown",
            recommended_action="review",
            target_category_code=None,
            reason="empty_title",
            confidence=0.5,
            signals={},
        )

    body_signal = _camera_shape_has_body_signal(normalized, compact, slug)
    lens_signal = _camera_shape_has_lens_signal(normalized, compact, slug)
    body_primary = _camera_shape_has_body_primary_signal(normalized, compact, slug)
    lens_primary = _camera_shape_has_lens_primary_signal(normalized, compact, slug)
    rental_or_service = _camera_shape_is_rental_or_service(normalized)
    commercial_menu = _camera_shape_is_commercial_menu(normalized)
    accessory_or_part = _camera_shape_is_accessory_or_part(
        normalized=normalized,
        body_signal=body_signal,
        lens_signal=lens_signal,
    )

    signals: dict[str, bool | int | str | None] = {
        "body_signal": body_signal,
        "lens_signal": lens_signal,
        "body_primary": body_primary,
        "lens_primary": lens_primary,
        "rental_or_service": rental_or_service,
        "commercial_menu": commercial_menu,
        "accessory_or_part": accessory_or_part,
        "body_first_index": _camera_body_first_index(normalized, compact, slug),
        "lens_first_index": _camera_lens_first_index(normalized, compact),
    }

    if rental_or_service:
        shape = "rental_or_service"
        reason = "camera_rental_or_service"
        confidence = 0.97
    elif commercial_menu:
        shape = "commercial_menu"
        reason = "camera_commercial_multi_option_menu"
        confidence = 0.94
    elif accessory_or_part:
        shape = "accessory_or_part"
        reason = "camera_accessory_or_part_only"
        confidence = 0.95
    elif body_signal and lens_signal:
        if lens_primary and not body_primary:
            shape = "lens_bundle"
            reason = "lens_primary_with_body_context"
            confidence = 0.9
        else:
            shape = "body_bundle"
            reason = "body_primary_with_lens_context"
            confidence = 0.94
    elif body_signal:
        shape = "body_only"
        reason = "camera_body_signal"
        confidence = 0.94
    elif lens_signal:
        shape = "lens_only"
        reason = "camera_lens_signal"
        confidence = 0.94
    else:
        shape = "unknown"
        reason = "no_camera_body_or_lens_signal"
        confidence = 0.5

    recommended_action, target_category_code = recommend_camera_listing_shape_action(
        current_category_code=resolved_category_code,
        shape=shape,
    )
    return _decision(
        current_category_code=resolved_category_code,
        shape=shape,
        recommended_action=recommended_action,
        target_category_code=target_category_code,
        reason=reason,
        confidence=confidence,
        signals=signals,
    )


def recommend_camera_listing_shape_action(
    *,
    current_category_code: str | None,
    shape: str,
) -> tuple[str, str | None]:
    resolved_category_code = resolve_category_code(current_category_code)
    if resolved_category_code not in CAMERA_CATEGORY_CODES:
        return "review", None
    if shape in BLOCK_SHAPES:
        return "block", resolved_category_code
    if resolved_category_code == "camera_body":
        if shape in BODY_SHAPES:
            return "keep", "camera_body"
        if shape in LENS_SHAPES:
            return "redirect", "camera_interchangeable_lens"
        return "review", None
    if resolved_category_code == "camera_interchangeable_lens":
        if shape in LENS_SHAPES:
            return "keep", "camera_interchangeable_lens"
        if shape in BODY_SHAPES:
            return "redirect", "camera_body"
        return "review", None
    return "review", None


def audit_camera_listing_shapes(
    session: Session,
    *,
    category_code: str | None = None,
    active_only: bool = True,
    limit: int | None = None,
    sample_limit: int = 20,
) -> dict[str, Any]:
    resolved_category_code = _resolve_optional_camera_category(category_code)
    items = _load_camera_items(
        session,
        category_code=resolved_category_code,
        active_only=active_only,
        limit=limit,
    )

    shape_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    domain_shape_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    domain_action_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[dict[str, Any]]] = {"redirect": [], "block": [], "review": []}

    for item in items:
        current_category_code = resolve_category_code(getattr(item, "business_domain", None))
        decision = evaluate_camera_listing_shape(
            current_category_code=current_category_code,
            title=str(getattr(item, "title", "") or ""),
        )
        shape_counts[decision.shape] += 1
        action_counts[decision.recommended_action] += 1
        domain_key = current_category_code or str(getattr(item, "business_domain", "") or "unknown")
        domain_shape_counts[domain_key][decision.shape] += 1
        domain_action_counts[domain_key][decision.recommended_action] += 1

        if decision.recommended_action in samples and len(samples[decision.recommended_action]) < sample_limit:
            samples[decision.recommended_action].append(_item_decision_sample(item, decision))

    return {
        "category_code": resolved_category_code,
        "active_only": bool(active_only),
        "scanned": len(items),
        "shape_counts": dict(sorted(shape_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "domain_shape_counts": {
            domain: dict(sorted(counter.items())) for domain, counter in sorted(domain_shape_counts.items())
        },
        "domain_action_counts": {
            domain: dict(sorted(counter.items())) for domain, counter in sorted(domain_action_counts.items())
        },
        "samples": samples,
    }


def repair_camera_listing_shapes(
    session: Session,
    *,
    category_code: str | None = None,
    active_only: bool = True,
    limit: int | None = None,
    sample_limit: int = 50,
    min_confidence: float = 0.9,
    dry_run: bool = True,
) -> dict[str, Any]:
    resolved_category_code = _resolve_optional_camera_category(category_code)
    items = _load_camera_items(
        session,
        category_code=resolved_category_code,
        active_only=active_only,
        limit=limit,
    )
    category_id_by_code = _load_category_id_by_code(session)
    active_template_id_by_code = _load_active_template_id_by_code(session)

    redirected_item_ids: set[str] = set()
    blocked_item_ids: set[str] = set()
    skipped_low_confidence_count = 0
    review_count = 0
    keep_count = 0
    unchanged_count = 0
    updates: list[dict[str, Any]] = []

    for item in items:
        current_category_code = resolve_category_code(getattr(item, "business_domain", None))
        decision = evaluate_camera_listing_shape(
            current_category_code=current_category_code,
            title=str(getattr(item, "title", "") or ""),
        )
        action = decision.recommended_action
        if action == "keep":
            keep_count += 1
            continue
        if action == "review":
            review_count += 1
            continue
        if decision.confidence < min_confidence:
            skipped_low_confidence_count += 1
            continue

        if action == "redirect":
            target_category_code = decision.target_category_code
            if target_category_code not in CAMERA_CATEGORY_CODES or target_category_code == current_category_code:
                unchanged_count += 1
                continue
            redirected_category_id = category_id_by_code.get(target_category_code)
            redirected_template_id = active_template_id_by_code.get(target_category_code)
            updates.append(_item_decision_sample(item, decision))
            redirected_item_ids.add(str(item.item_id))
            if dry_run:
                continue
            item.business_domain = target_category_code
            item.is_active = True
            item.resolved_category_id = redirected_category_id
            item.resolved_template_id = redirected_template_id
            item.category_validation_status = "OVERRIDE_CATEGORY"
            item.category_validation_reason = (
                f"camera_shape_redirect:{current_category_code}_to_{target_category_code}:{decision.shape}"
            )
            item.category_validation_confidence = Decimal(str(round(decision.confidence, 4)))
            continue

        if action == "block":
            expected_reason = f"camera_shape_blocked:{decision.shape}"
            already_blocked = (
                not bool(getattr(item, "is_active", True))
                and str(getattr(item, "category_validation_status", "") or "") == "BLOCKED"
                and str(getattr(item, "category_validation_reason", "") or "") == expected_reason
            )
            if already_blocked:
                unchanged_count += 1
                continue
            updates.append(_item_decision_sample(item, decision))
            blocked_item_ids.add(str(item.item_id))
            if dry_run:
                continue
            item.is_active = False
            item.resolved_category_id = None
            item.resolved_template_id = None
            item.category_validation_status = "BLOCKED"
            item.category_validation_reason = expected_reason
            item.category_validation_confidence = Decimal(str(round(decision.confidence, 4)))

    cleared_rejection_count = 0
    removable_item_ids = redirected_item_ids | blocked_item_ids
    if removable_item_ids and not dry_run:
        result = session.execute(
            delete(ItemIngestRejection).where(
                ItemIngestRejection.source_platform == "xianyu",
                ItemIngestRejection.item_id.in_(tuple(sorted(removable_item_ids))),
                or_(
                    ItemIngestRejection.rejection_stage.like("%category_gate%"),
                    ItemIngestRejection.rejection_stage.like("transient:%"),
                    ItemIngestRejection.rejection_reason.like("domain_%"),
                    ItemIngestRejection.rejection_reason == "non_comparable_title",
                ),
            )
        )
        cleared_rejection_count = int(result.rowcount or 0)

    return {
        "category_code": resolved_category_code,
        "active_only": bool(active_only),
        "dry_run": bool(dry_run),
        "scanned": len(items),
        "keep_count": keep_count,
        "review_count": review_count,
        "redirected_count": len(redirected_item_ids),
        "blocked_count": len(blocked_item_ids),
        "unchanged_count": unchanged_count,
        "skipped_low_confidence_count": skipped_low_confidence_count,
        "cleared_rejection_count": cleared_rejection_count,
        "sample": updates[:sample_limit],
    }


def _decision(
    *,
    current_category_code: str | None,
    shape: str,
    recommended_action: str,
    target_category_code: str | None,
    reason: str,
    confidence: float,
    signals: dict[str, bool | int | str | None],
) -> CameraListingShapeDecision:
    return CameraListingShapeDecision(
        current_category_code=current_category_code,
        shape=shape,
        recommended_action=recommended_action,
        target_category_code=target_category_code,
        reason=reason,
        confidence=confidence,
        signals=signals,
    )


def _resolve_optional_camera_category(category_code: str | None) -> str | None:
    if category_code is None:
        return None
    resolved_category_code = resolve_category_code(category_code)
    if resolved_category_code not in CAMERA_CATEGORY_CODES:
        raise ValueError("category_code must be camera_body or camera_interchangeable_lens")
    return resolved_category_code


def _load_camera_items(
    session: Session,
    *,
    category_code: str | None,
    active_only: bool,
    limit: int | None,
) -> list[Item]:
    domains = (category_code,) if category_code else CAMERA_CATEGORY_CODES
    stmt = select(Item).where(Item.business_domain.in_(domains)).order_by(Item.id.asc())
    if active_only:
        stmt = stmt.where(Item.is_active.is_(True))
    if limit is not None and limit > 0:
        stmt = stmt.limit(int(limit))
    return list(session.execute(stmt).scalars().all())


def _load_category_id_by_code(session: Session) -> dict[str, str]:
    rows = session.execute(select(Category.id, Category.code)).all()
    return {str(code): str(category_id) for category_id, code in rows if code}


def _load_active_template_id_by_code(session: Session) -> dict[str, str]:
    rows = session.execute(
        select(Category.code, CategoryRuntimeProfile.active_template_id)
        .join(CategoryRuntimeProfile, CategoryRuntimeProfile.category_id == Category.id)
        .where(CategoryRuntimeProfile.status == "ACTIVE")
    ).all()
    return {str(code): str(template_id) for code, template_id in rows if code and template_id}


def _item_decision_sample(item: Item, decision: CameraListingShapeDecision) -> dict[str, Any]:
    return {
        "item_id": getattr(item, "item_id", None),
        "action": decision.recommended_action,
        "from_domain": resolve_category_code(getattr(item, "business_domain", None))
        or getattr(item, "business_domain", None),
        "to_domain": decision.target_category_code,
        "shape": decision.shape,
        "reason": decision.reason,
        "confidence": round(float(decision.confidence), 4),
        "price": float(getattr(item, "current_price", 0) or 0) or None,
        "title": getattr(item, "title", None),
    }


def _normalize_camera_title(title: str | None) -> tuple[str, str, str]:
    normalized = (
        str(title or "")
        .strip()
        .lower()
        .replace("α", "a")
        .replace("—", "-")
        .replace("–", "-")
        .replace("－", "-")
        .replace("／", "/")
        .replace("．", ".")
        .replace(" ", " ")
    )
    normalized = re.sub(r"\s+", " ", normalized)
    compact = re.sub(r"[\s\-_+/（）()【】\[\]{}:：,，.。;；!！？?]+", "", normalized)
    slug = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized, compact, slug


def _camera_shape_has_body_signal(normalized: str, compact: str, slug: str) -> bool:
    return _camera_shape_has_body_model_signal(normalized, compact, slug) or _camera_shape_has_body_primary_signal(
        normalized,
        compact,
        slug,
    )


def _camera_shape_has_body_model_signal(normalized: str, compact: str, slug: str) -> bool:
    for pattern in (*CAMERA_BODY_MODEL_PATTERNS, *CAMERA_BODY_EXTRA_MODEL_PATTERNS):
        match = pattern.search(normalized)
        if match and not _camera_match_has_compatibility_prefix(normalized, match.start()):
            return True
    return any(signature in compact or signature in slug for signature in CAMERA_BODY_COMPACT_SAFE_SIGNATURES) or any(
        signature in compact or signature in slug for signature in CAMERA_BODY_EXTRA_COMPACT_SIGNATURES
    )


def _camera_shape_has_body_primary_signal(normalized: str, compact: str, slug: str) -> bool:
    body_model_present = _camera_shape_has_body_model_signal(normalized, compact, slug)
    brand_present = any(token in normalized for token in CAMERA_BRAND_TOKENS)
    prefix = _camera_leading_clause(normalized, max_length=48)
    lens_signal = _camera_shape_has_lens_signal(normalized, compact, slug, guard_body_primary=False)
    if any(token in normalized for token in CAMERA_BODY_ALWAYS_EXPLICIT_TOKENS):
        return True
    if any(token in normalized for token in CAMERA_BODY_BUNDLE_TOKENS) and (body_model_present or brand_present):
        return True
    if _camera_body_context_token_present(prefix) and (body_model_present or brand_present):
        if lens_signal and not body_model_present:
            return False
        return True
    if any(token in normalized for token in ("相机", "微单", "单反")) and body_model_present:
        return True
    if any(token in normalized for token in CAMERA_BODY_META_TOKENS):
        return bool(body_model_present and not lens_signal)
    if _camera_shape_has_body_model_signal(prefix, *(_normalize_camera_title(prefix)[1:])):
        return True
    return False


def _camera_shape_has_lens_signal(
    normalized: str,
    compact: str,
    slug: str,
    *,
    guard_body_primary: bool = True,
) -> bool:
    if _camera_lens_absent_only(normalized):
        return False
    if CAMERA_EXPLICIT_LENS_PRESENT_PATTERN.search(normalized):
        return True
    if any(token in normalized for token in CAMERA_LENS_DESCRIPTOR_TOKENS):
        return True
    if any(token in normalized for token in CAMERA_LENS_KEYWORD_TOKENS if token != "镜头"):
        return True
    if any(token in normalized for token in CAMERA_LENS_SLANG_TOKENS):
        return True
    if "尼克尔" in normalized:
        return True
    if "镜头" in normalized and not _camera_lens_absent_only(normalized):
        if CAMERA_KIT_ZOOM_PATTERN.search(normalized):
            return True
        if any(pattern.search(normalized) for pattern in CAMERA_LENS_PRIME_SIGNATURE_PATTERNS):
            return True
        if not guard_body_primary:
            return True
        if not _camera_shape_has_body_primary_signal(normalized, compact, slug):
            return True
    if CAMERA_KIT_ZOOM_PATTERN.search(normalized):
        return True
    if any(pattern.search(normalized) for pattern in CAMERA_LENS_ZOOM_SIGNATURE_PATTERNS):
        return True
    if any(pattern.search(normalized) for pattern in CAMERA_LENS_PRIME_SIGNATURE_PATTERNS):
        return True
    if any(pattern.search(normalized) for pattern in CAMERA_LENS_NORMALIZED_PATTERNS):
        return True
    if any(pattern.search(compact) or pattern.search(slug) for pattern in CAMERA_LENS_TIGHT_SIGNATURE_PATTERNS):
        return True
    if any(pattern.search(compact) for pattern in CAMERA_LENS_COMPACT_PATTERNS):
        return True
    if any(signature in compact or signature in slug for signature in CAMERA_LENS_COMPACT_SIGNATURES):
        return True
    if any(signature in compact or signature in slug for signature in CAMERA_LENS_NICKNAME_SIGNATURES):
        return True
    if any(pattern.search(normalized) for pattern in CAMERA_LENS_MOUNT_PATTERNS) and re.search(
        r"\d{1,3}(?:\s*[-~至到/]\s*\d{1,3})?(?:\s*mm)?",
        normalized,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"(?<!\d)\d{2,3}\s+(?:1\.\d|2\.\d|2\.8|4)(?!\d)", normalized, re.IGNORECASE):
        return True
    if re.search(r"(?<![a-z0-9])z\s*\d{2,3}\s*(?:f\s*/?\s*)?\d(?:\.\d)?", normalized, re.IGNORECASE):
        return True
    return False


def _camera_shape_has_lens_primary_signal(normalized: str, compact: str, slug: str) -> bool:
    prefix = _camera_leading_clause(normalized, max_length=48)
    prefix_normalized, prefix_compact, prefix_slug = _normalize_camera_title(prefix)
    if _camera_shape_has_body_primary_signal(prefix_normalized, prefix_compact, prefix_slug):
        return False
    if _camera_shape_has_lens_signal(prefix_normalized, prefix_compact, prefix_slug):
        return True
    lens_index = _camera_lens_first_index(normalized, compact)
    body_index = _camera_body_first_index(normalized, compact, slug)
    return lens_index >= 0 and (body_index < 0 or lens_index + 8 < body_index)


def _camera_shape_is_rental_or_service(normalized: str) -> bool:
    return any(token in normalized for token in CAMERA_RENTAL_SERVICE_TOKENS)


def _camera_shape_is_commercial_menu(normalized: str) -> bool:
    price_points = re.findall(r"(?<!\d)\d{4,5}(?!\d)", normalized)
    menu_hits = sum(1 for token in CAMERA_COMMERCIAL_MENU_TOKENS if token in normalized)
    if CAMERA_COMMERCIAL_MENU_PATTERN.search(normalized):
        return True
    if len(price_points) >= 3 and menu_hits >= 1:
        return True
    if len(price_points) >= 2 and menu_hits >= 2:
        return True
    return "型号齐全" in normalized and ("联系客服" in normalized or "咨询客服" in normalized)


def _camera_shape_is_accessory_or_part(
    *,
    normalized: str,
    body_signal: bool,
    lens_signal: bool,
) -> bool:
    if any(pattern.search(normalized) for pattern in CAMERA_BODY_NON_TARGET_PACKAGING_PATTERNS):
        return True
    if body_signal or lens_signal:
        return False
    if any(token in normalized for token in CAMERA_NON_TARGET_LIGHTING_TOKENS):
        return True
    part_hit = any(token in normalized for token in CAMERA_BODY_NON_TARGET_PART_TOKENS)
    context_hit = any(token in normalized for token in CAMERA_ACCESSORY_CONTEXT_TOKENS)
    return part_hit and context_hit


def _camera_lens_absent_only(normalized: str) -> bool:
    if not any(pattern.search(normalized) for pattern in CAMERA_LENS_ABSENT_PATTERNS):
        return False
    non_absent_lens_context = (
        CAMERA_EXPLICIT_LENS_PRESENT_PATTERN.search(normalized)
        or CAMERA_KIT_ZOOM_PATTERN.search(normalized)
        or any(token in normalized for token in CAMERA_LENS_KEYWORD_TOKENS if token != "镜头")
    )
    return not bool(non_absent_lens_context)


def _camera_leading_clause(normalized: str, *, max_length: int) -> str:
    return re.split(r"[，,。；;!！?？]", normalized, maxsplit=1)[0][:max_length]


def _camera_match_has_compatibility_prefix(normalized: str, start: int) -> bool:
    prefix = normalized[max(0, start - 8):start]
    return any(token in prefix for token in CAMERA_COMPATIBILITY_PREFIX_TOKENS)


def _camera_body_context_token_present(prefix: str) -> bool:
    return bool(re.search(r"(?:机身(?!号|编号|序列号)|单机|微单|单反|body)", prefix, re.IGNORECASE))


def _camera_body_first_index(normalized: str, compact: str, slug: str) -> int:
    indexes: list[int] = []
    for token in (*CAMERA_BODY_ALWAYS_EXPLICIT_TOKENS, *CAMERA_BODY_CONTEXTUAL_TOKENS):
        index = normalized.find(token)
        if index >= 0:
            indexes.append(index)
    for pattern in (*CAMERA_BODY_MODEL_PATTERNS, *CAMERA_BODY_EXTRA_MODEL_PATTERNS):
        match = pattern.search(normalized)
        if match:
            indexes.append(match.start())
    for signature in (*CAMERA_BODY_COMPACT_SAFE_SIGNATURES, *CAMERA_BODY_EXTRA_COMPACT_SIGNATURES):
        index = compact.find(signature)
        if index >= 0:
            indexes.append(index)
        slug_index = slug.find(signature)
        if slug_index >= 0:
            indexes.append(slug_index)
    return min(indexes) if indexes else -1


def _camera_lens_first_index(normalized: str, compact: str) -> int:
    indexes: list[int] = []
    for token in (*CAMERA_LENS_KEYWORD_TOKENS, *CAMERA_LENS_DESCRIPTOR_TOKENS):
        index = normalized.find(token)
        if index >= 0:
            indexes.append(index)
    for pattern in (
        *CAMERA_LENS_ZOOM_SIGNATURE_PATTERNS,
        *CAMERA_LENS_PRIME_SIGNATURE_PATTERNS,
        *CAMERA_LENS_NORMALIZED_PATTERNS,
        CAMERA_KIT_ZOOM_PATTERN,
    ):
        match = pattern.search(normalized)
        if match:
            indexes.append(match.start())
    for pattern in (*CAMERA_LENS_TIGHT_SIGNATURE_PATTERNS, *CAMERA_LENS_COMPACT_PATTERNS):
        match = pattern.search(compact)
        if match:
            indexes.append(match.start())
    return min(indexes) if indexes else -1
