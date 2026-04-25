from __future__ import annotations

import re
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...category_compat import resolve_category_code
from ...models import (
    Category,
    OutboxEvent,
    ProductAttrAuditLog,
    ProductSpu,
    ProductStatus,
)

APPLE_COMPUTER_POSITIVE_RE = re.compile(
    r"(macbook|mac\s*book|mac\s*mini|macmini|mac\s*studio|macstudio|\bimac\b|\bm[1-5]\s*(pro|max|ultra)?\b|笔记本|电脑)",
    re.IGNORECASE,
)
APPLE_COMPUTER_WRONG_CATEGORY_TOKENS = (
    "apple watch",
    "watch series",
    "iwatch",
    "iphone",
    "ipad",
    "airpods",
    "airtag",
    "手表",
    "手机",
    "平板",
    "耳机",
)

GARMIN_WATCH_POSITIVE_RE = re.compile(
    r"(garmin|佳明|fenix|forerunner|instinct|epix|marq|venu|approach|tactix|enduro|descent|vivoactive|vivomove|quatix|lily)",
    re.IGNORECASE,
)
GARMIN_WATCH_WRONG_CATEGORY_TOKENS = (
    "apple watch",
    "iwatch",
    "macbook",
    "mac mini",
    "macmini",
    "mac studio",
    "macstudio",
    "imac",
    "iphone",
    "ipad",
    "airpods",
    "rtx",
    "显卡",
    "镜头",
    "相机",
    "手机",
    "电脑",
    "笔记本",
)

PHONE_POSITIVE_RE = re.compile(
    r"(iphone|手机|华为|huawei|mate|pura|小米|xiaomi|红米|redmi|oppo|vivo|荣耀|honor|三星|samsung|pixel|oneplus|一加)",
    re.IGNORECASE,
)
PHONE_WRONG_CATEGORY_TOKENS = (
    "macbook",
    "mac mini",
    "macmini",
    "mac studio",
    "macstudio",
    "imac",
    "garmin",
    "佳明",
    "fenix",
    "forerunner",
    "instinct",
    "apple watch",
    "rtx",
    "显卡",
    "镜头",
    "相机",
)

AUDITABLE_CATEGORY_CODES: tuple[str, ...] = (
    "apple_computer",
    "garmin_watch",
    "phone",
    "graphics_card",
    "camera_interchangeable_lens",
    "camera_body",
)

CROSS_CATEGORY_MATCH_ORDER: tuple[str, ...] = (
    "apple_computer",
    "phone",
    "garmin_watch",
    "graphics_card",
    "camera_interchangeable_lens",
    "camera_body",
)


def catalog_scope_mismatch_reason(
    category_code: str | None,
    *,
    title: str | None = None,
    spu_snapshot: Any | None = None,
    sku_snapshots: list[Any] | tuple[Any, ...] | None = None,
) -> str | None:
    canonical_code = resolve_category_code(category_code)
    haystack = _catalog_scope_haystack(
        title=title,
        spu_snapshot=spu_snapshot,
        sku_snapshots=sku_snapshots,
    )
    if not haystack:
        return None
    if canonical_code == "apple_computer":
        return _apple_computer_mismatch_reason(haystack)
    if canonical_code == "garmin_watch":
        return _garmin_watch_mismatch_reason(haystack)
    if canonical_code == "phone":
        return _phone_mismatch_reason(haystack)
    return _cross_category_mismatch_reason(canonical_code, haystack)


def build_catalog_category_scope_audit(
    session: Session,
    *,
    category_code: str | None = None,
    active_only: bool = True,
) -> dict[str, Any]:
    findings = find_catalog_category_scope_mismatches(
        session,
        category_code=category_code,
        active_only=active_only,
    )
    category_counts = Counter(str(row["categoryCode"]) for row in findings)
    reason_counts = Counter(str(row["reason"]) for row in findings)
    return {
        "categoryCode": resolve_category_code(category_code) or None,
        "activeOnly": active_only,
        "mismatchCount": len(findings),
        "categoryCounts": dict(sorted(category_counts.items())),
        "reasonCounts": dict(sorted(reason_counts.items())),
        "items": findings,
    }


def find_catalog_category_scope_mismatches(
    session: Session,
    *,
    category_code: str | None = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    stmt = (
        select(Category, ProductSpu)
        .join(ProductSpu, ProductSpu.category_id == Category.id)
        .options(selectinload(ProductSpu.skus))
        .order_by(Category.code.asc(), ProductSpu.title.asc())
    )
    if active_only:
        stmt = stmt.where(ProductSpu.status == ProductStatus.ACTIVE)
    resolved_category_code = resolve_category_code(category_code)
    if resolved_category_code:
        stmt = stmt.where(Category.code == resolved_category_code)

    findings: list[dict[str, Any]] = []
    for category, spu in session.execute(stmt).all():
        candidate_skus = [
            sku
            for sku in list(spu.skus or [])
            if not active_only or sku.status == ProductStatus.ACTIVE
        ]
        if not candidate_skus:
            continue
        reason = catalog_scope_mismatch_reason(
            category.code,
            title=spu.title,
            spu_snapshot=spu.attr_snapshot_json,
            sku_snapshots=[sku.attr_snapshot_json for sku in candidate_skus],
        )
        if reason is None:
            continue
        findings.append(
            {
                "categoryCode": category.code,
                "categoryName": category.name,
                "spuId": str(spu.id),
                "title": spu.title,
                "reason": reason,
                "spuStatus": getattr(spu.status, "value", str(spu.status)),
                "activeSkuCount": len(candidate_skus),
                "skuCodes": [sku.sku_code for sku in candidate_skus],
            }
        )
    return findings


def quarantine_catalog_category_scope_mismatches(
    session: Session,
    *,
    category_code: str | None = None,
    operator_id: str = "catalog-scope-cleanup",
    dry_run: bool = True,
) -> dict[str, Any]:
    findings = find_catalog_category_scope_mismatches(
        session,
        category_code=category_code,
        active_only=True,
    )
    if dry_run or not findings:
        return _cleanup_summary(findings=findings, dry_run=dry_run)

    finding_by_spu_id = {str(row["spuId"]): row for row in findings}
    rows = session.execute(
        select(ProductSpu)
        .where(ProductSpu.id.in_(tuple(finding_by_spu_id.keys())))
        .options(selectinload(ProductSpu.skus))
    ).scalars()
    for spu in rows:
        finding = finding_by_spu_id.get(str(spu.id))
        if finding is None:
            continue
        before = {
            "spuStatus": getattr(spu.status, "value", str(spu.status)),
            "skuStatuses": {
                sku.sku_code: getattr(sku.status, "value", str(sku.status))
                for sku in list(spu.skus or [])
            },
        }
        spu.status = ProductStatus.INACTIVE
        changed_sku_codes: list[str] = []
        for sku in list(spu.skus or []):
            if sku.status == ProductStatus.ACTIVE:
                sku.status = ProductStatus.INACTIVE
                changed_sku_codes.append(sku.sku_code)
        session.add(
            ProductAttrAuditLog(
                operator_id=operator_id,
                resource_type="product_spu",
                resource_id=str(spu.id),
                action="CATEGORY_SCOPE_QUARANTINE",
                before_json=before,
                after_json={
                    "spuStatus": ProductStatus.INACTIVE.value,
                    "reason": finding["reason"],
                    "categoryCode": finding["categoryCode"],
                    "skuCodes": changed_sku_codes,
                },
            )
        )
        session.add(
            OutboxEvent(
                event_type="catalog.product_spu_changed",
                aggregate_type="product_spu",
                aggregate_id=str(spu.id),
                payload={
                    "reason": "category_scope_quarantine",
                    "categoryCode": finding["categoryCode"],
                    "mismatchReason": finding["reason"],
                    "skuCodes": changed_sku_codes,
                },
            )
        )
    session.flush()
    return _cleanup_summary(findings=findings, dry_run=False)


def _cleanup_summary(*, findings: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    category_counts = Counter(str(row["categoryCode"]) for row in findings)
    reason_counts = Counter(str(row["reason"]) for row in findings)
    matched_sku_count = sum(int(row.get("activeSkuCount") or 0) for row in findings)
    return {
        "dryRun": dry_run,
        "matchedSpuCount": len(findings),
        "matchedSkuCount": matched_sku_count,
        "quarantinedSpuCount": 0 if dry_run else len(findings),
        "quarantinedSkuCount": 0 if dry_run else matched_sku_count,
        "categoryCounts": dict(sorted(category_counts.items())),
        "reasonCounts": dict(sorted(reason_counts.items())),
        "items": findings,
    }


def _catalog_scope_haystack(
    *,
    title: str | None,
    spu_snapshot: Any | None,
    sku_snapshots: list[Any] | tuple[Any, ...] | None,
) -> str:
    parts: list[str] = []
    _append_flattened_text(parts, title)
    _append_flattened_text(parts, spu_snapshot)
    for snapshot in list(sku_snapshots or []):
        _append_flattened_text(parts, snapshot)
    return " ".join(part for part in parts if part).lower()


def _append_flattened_text(parts: list[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for nested in value.values():
            _append_flattened_text(parts, nested)
        return
    if isinstance(value, (list, tuple, set)):
        for nested in value:
            _append_flattened_text(parts, nested)
        return
    text = str(value).strip()
    if text:
        parts.append(text)


def _apple_computer_mismatch_reason(haystack: str) -> str | None:
    positive = bool(APPLE_COMPUTER_POSITIVE_RE.search(haystack))
    wrong_hits = _token_hits(haystack, APPLE_COMPUTER_WRONG_CATEGORY_TOKENS)
    if wrong_hits and not positive:
        return f"apple_computer_contains_{_reason_token(wrong_hits[0])}"
    if "apple watch" in haystack or "watch series" in haystack or "iwatch" in haystack:
        return "apple_computer_contains_apple_watch"
    return None


def _garmin_watch_mismatch_reason(haystack: str) -> str | None:
    positive = bool(GARMIN_WATCH_POSITIVE_RE.search(haystack))
    wrong_hits = _token_hits(haystack, GARMIN_WATCH_WRONG_CATEGORY_TOKENS)
    if wrong_hits and not positive:
        return f"garmin_watch_contains_{_reason_token(wrong_hits[0])}"
    return None


def _phone_mismatch_reason(haystack: str) -> str | None:
    positive = bool(PHONE_POSITIVE_RE.search(haystack))
    wrong_hits = _token_hits(haystack, PHONE_WRONG_CATEGORY_TOKENS)
    if wrong_hits and not positive:
        return f"phone_contains_{_reason_token(wrong_hits[0])}"
    return _cross_category_mismatch_reason("phone", haystack)


def _cross_category_mismatch_reason(category_code: str | None, haystack: str) -> str | None:
    canonical_code = resolve_category_code(category_code)
    if canonical_code not in AUDITABLE_CATEGORY_CODES:
        return None
    if _title_matches_scope(canonical_code, haystack):
        return None
    for other_code in CROSS_CATEGORY_MATCH_ORDER:
        if other_code == canonical_code:
            continue
        if _cross_scope_matches(other_code, haystack):
            return f"{canonical_code}_contains_{other_code}"
    return None


def _title_matches_scope(category_code: str, haystack: str) -> bool:
    normalized = str(haystack or "").strip()
    if not normalized:
        return False
    from ...pricing import title_matches_domain

    return title_matches_domain(category_code, normalized)


def _cross_scope_matches(category_code: str, haystack: str) -> bool:
    normalized = str(haystack or "").strip().lower()
    if not normalized:
        return False
    if category_code == "phone":
        return bool(PHONE_POSITIVE_RE.search(normalized))
    if category_code == "garmin_watch":
        return bool(GARMIN_WATCH_POSITIVE_RE.search(normalized))
    if category_code == "graphics_card":
        return _strong_graphics_card_signal(normalized)
    if category_code == "camera_interchangeable_lens":
        return _strong_lens_signal(normalized)
    return _title_matches_scope(category_code, normalized)


def _token_hits(haystack: str, tokens: tuple[str, ...]) -> list[str]:
    return [token for token in tokens if token in haystack]


def _reason_token(token: str) -> str:
    return re.sub(r"\s+", "_", str(token or "").strip().lower()).replace("/", "_")


def _strong_graphics_card_signal(normalized: str) -> bool:
    compact = re.sub(r"[\s\-_+/（）()]+", "", normalized)
    if "显卡" in normalized:
        return True
    if re.search(r"\b(?:rtx|gtx)\s*\d{3,4}\b", normalized, re.IGNORECASE):
        return True
    if re.search(r"\brx\s*\d{3,4}\b", normalized, re.IGNORECASE):
        return True
    if re.search(r"\b(?:quadro|radeon)\b", normalized, re.IGNORECASE):
        return True
    if re.search(r"\barc\s*a\d+\b", normalized, re.IGNORECASE):
        return True
    return bool(re.search(r"(?:rtx|gtx|rx)\d{3,4}", compact, re.IGNORECASE))


def _strong_lens_signal(normalized: str) -> bool:
    compact = re.sub(r"[\s\-_+/（）()]+", "", normalized)
    if "镜头" in normalized or "nikkor" in normalized:
        return True
    focal_match = re.search(r"\b\d{1,3}(?:\s*-\s*\d{1,3})?\s*mm\b", normalized, re.IGNORECASE)
    aperture_match = re.search(r"\bf\s*/?\s*\d(?:\.\d)?\b", normalized, re.IGNORECASE)
    if focal_match and aperture_match:
        return True
    normalized_pattern = re.compile(
        r"\b(?:rf|ef|fe|xf|xcd|gf)\s*\d{1,3}(?:\s*-\s*\d{1,3})?(?:\s*mm)?\s*(?:f\s*/?\s*)?\d(?:\.\d)?\b",
        re.IGNORECASE,
    )
    compact_pattern = re.compile(
        r"(?:rf|ef|fe|xf|xcd|gf|nikkorz)\d{1,3}(?:-\d{1,3})?(?:mm)?f?\d(?:\.\d)?(?:s|gm|art|pro|vr|dgdn|dn)?",
        re.IGNORECASE,
    )
    z_mount_pattern = re.compile(
        r"\bz\s*\d{1,3}(?:\s*-\s*\d{1,3})?(?:\s*mm)?\s*(?:f\s*/?\s*)\d(?:\.\d)?\b",
        re.IGNORECASE,
    )
    return bool(
        normalized_pattern.search(normalized)
        or compact_pattern.search(compact)
        or z_mount_pattern.search(normalized)
    )
