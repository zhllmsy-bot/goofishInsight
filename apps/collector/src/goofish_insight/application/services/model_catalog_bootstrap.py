from __future__ import annotations

from collections import defaultdict
import re
from hashlib import sha1
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ...category_compat import compatible_scope_keys, resolve_category_code
from ...db import session_scope
from ...models import Category, Item
from .model_config import import_model_configs

BOOTSTRAP_BRAND_BY_CATEGORY = {
    'apple_computer': 'Apple',
    'garmin_watch': 'Garmin',
}

REJECT_MODEL_SUBSTRINGS = {
    '包邮', '私聊', '顺丰', '自提', '国行全新', '特价活动', '图片为实拍图', '欲购从速', '货源紧俏', '未拆封', '可小刀', '不要直接拍'
}
APPLE_ALLOWED_MEMORY_GB = {8, 16, 18, 24, 32, 36, 48, 64, 96, 128, 192, 256, 512}
APPLE_ALLOWED_STORAGE_GB = {128, 256, 512, 1024, 2048, 4096, 8192, 16384}


class ModelCatalogBootstrapError(RuntimeError):
    pass


def preview_model_catalog_bootstrap(
    *,
    business_domain: str,
    min_sample_count: int = 20,
    limit: int = 0,
    active_only: bool = True,
    name_query: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return preview_model_catalog_bootstrap_with_session(
            session,
            business_domain=business_domain,
            min_sample_count=min_sample_count,
            limit=limit,
            active_only=active_only,
            name_query=name_query,
        )


def apply_model_catalog_bootstrap(
    *,
    business_domain: str,
    operator_id: str,
    min_sample_count: int = 20,
    limit: int = 0,
    active_only: bool = True,
    name_query: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    preview = preview_model_catalog_bootstrap(
        business_domain=business_domain,
        min_sample_count=min_sample_count,
        limit=limit,
        active_only=active_only,
        name_query=name_query,
    )
    result = import_model_configs(
        payload={'items': preview['items']},
        operator_id=operator_id,
        dry_run=dry_run,
    )
    return {
        'businessDomain': preview['businessDomain'],
        'canonicalCategoryCode': preview['canonicalCategoryCode'],
        'dryRun': dry_run,
        'minSampleCount': preview['minSampleCount'],
        'activeOnly': preview['activeOnly'],
        'nameQuery': preview['nameQuery'],
        'candidateCount': preview['candidateCount'],
        'acceptedCount': preview['acceptedCount'],
        'rejectedCount': preview['rejectedCount'],
        'import': result,
        'items': preview['items'],
        'rejections': preview['rejections'],
    }


def preview_model_catalog_bootstrap_with_session(
    session: Session,
    *,
    business_domain: str,
    min_sample_count: int = 20,
    limit: int = 0,
    active_only: bool = True,
    name_query: str | None = None,
) -> dict[str, Any]:
    canonical = resolve_category_code(business_domain)
    category = session.execute(select(Category).where(Category.code == canonical)).scalar_one_or_none()
    if category is None:
        raise ModelCatalogBootstrapError(f'Category not found for bootstrap: {business_domain}')
    brand_name = BOOTSTRAP_BRAND_BY_CATEGORY.get(canonical)
    if brand_name is None:
        raise ModelCatalogBootstrapError(f'Unsupported business_domain for model bootstrap: {business_domain}')

    rows = _load_bootstrap_rows(
        session,
        canonical_category_code=canonical,
        min_sample_count=max(int(min_sample_count), 1),
        active_only=active_only,
    )
    rows = _collapse_bootstrap_rows(rows)
    rows = [row for row in rows if _matches_name_query(row=row, name_query=name_query)]

    accepted: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    used_codes: set[str] = set()
    for row in rows:
        reason = _reject_reason(canonical, row['modelName'])
        if reason is not None:
            rejections.append({**row, 'reason': reason})
            continue
        payload = _build_model_payload(
            canonical_category_code=canonical,
            brand_name=brand_name,
            row=row,
            used_codes=used_codes,
        )
        accepted.append(payload)
        if limit > 0 and len(accepted) >= limit:
            break

    return {
        'businessDomain': business_domain,
        'canonicalCategoryCode': canonical,
        'categoryId': category.id,
        'categoryName': category.name,
        'minSampleCount': max(int(min_sample_count), 1),
        'activeOnly': bool(active_only),
        'nameQuery': str(name_query or '').strip() or None,
        'candidateCount': len(rows),
        'acceptedCount': len(accepted),
        'rejectedCount': len(rejections),
        'items': accepted,
        'rejections': rejections[:50],
    }


def _load_bootstrap_rows(
    session: Session,
    *,
    canonical_category_code: str,
    min_sample_count: int,
    active_only: bool,
) -> list[dict[str, Any]]:
    scope_keys = compatible_scope_keys(canonical_category_code)
    stmt = (
        select(
            Item.normalized_model.label('normalized_model'),
            Item.normalized_model_family.label('normalized_model_family'),
            Item.normalized_chip.label('normalized_chip'),
            Item.normalized_memory_gb.label('normalized_memory_gb'),
            Item.normalized_storage_gb.label('normalized_storage_gb'),
            func.count(Item.id).label('sample_count'),
            func.max(Item.last_seen_at).label('last_seen_at'),
        )
        .where(Item.business_domain.in_(scope_keys), Item.normalized_model.is_not(None))
        .group_by(
            Item.normalized_model,
            Item.normalized_model_family,
            Item.normalized_chip,
            Item.normalized_memory_gb,
            Item.normalized_storage_gb,
        )
        .having(func.count(Item.id) >= min_sample_count)
        .order_by(desc('sample_count'), Item.normalized_model)
    )
    if active_only:
        stmt = stmt.where(Item.is_active.is_(True))
    rows = session.execute(stmt).all()
    bootstrap_rows = [
        _normalize_bootstrap_row(
            canonical_category_code=canonical_category_code,
            row={
                'modelName': str(row.normalized_model or '').strip(),
                'seriesName': str(row.normalized_model_family or '').strip() or None,
                'chipFamily': str(row.normalized_chip or '').strip() or None,
                'memoryGb': int(row.normalized_memory_gb) if row.normalized_memory_gb is not None else None,
                'storageGb': int(row.normalized_storage_gb) if row.normalized_storage_gb is not None else None,
                'sampleCount': int(row.sample_count or 0),
                'lastSeenAt': row.last_seen_at.isoformat() if row.last_seen_at is not None else None,
                'source': 'bootstrap_from_items_v1',
            },
        )
        for row in rows
    ]
    if canonical_category_code == 'apple_computer':
        bootstrap_rows.extend(
            _load_apple_title_bootstrap_rows(
                session,
                scope_keys=scope_keys,
                min_sample_count=min_sample_count,
                active_only=active_only,
            )
        )
    return bootstrap_rows


def _collapse_bootstrap_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: (-int(item.get('sampleCount') or 0), str(item.get('modelName') or ''))):
        model_name = str(row.get('modelName') or '').strip()
        if not model_name:
            continue
        key = model_name.lower()
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = dict(row)
            continue
        existing['sampleCount'] = int(existing.get('sampleCount') or 0) + int(row.get('sampleCount') or 0)
        existing['lastSeenAt'] = max(str(existing.get('lastSeenAt') or ''), str(row.get('lastSeenAt') or '')) or None
        for field in ('seriesName', 'chipFamily', 'memoryGb', 'storageGb'):
            if existing.get(field) in (None, '') and row.get(field) not in (None, ''):
                existing[field] = row.get(field)
    return sorted(
        grouped.values(),
        key=lambda item: (-int(item.get('sampleCount') or 0), str(item.get('modelName') or '')),
    )


def _normalize_bootstrap_row(*, canonical_category_code: str, row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    model_name = str(normalized.get('modelName') or '').strip()
    if not model_name:
        return normalized
    if canonical_category_code == 'apple_computer':
        canonical_name = _canonicalize_apple_model_name(
            model_name=model_name,
            series_name=normalized.get('seriesName'),
            chip_family=normalized.get('chipFamily'),
            memory_gb=normalized.get('memoryGb'),
            storage_gb=normalized.get('storageGb'),
        )
        if canonical_name:
            normalized['modelName'] = canonical_name
            if not normalized.get('seriesName'):
                normalized['seriesName'] = _extract_apple_product_line(canonical_name)
    if canonical_category_code == 'garmin_watch':
        canonical_name = _canonicalize_garmin_model_name(model_name)
        if canonical_name:
            normalized['modelName'] = canonical_name
            if not normalized.get('seriesName'):
                normalized['seriesName'] = canonical_name.split()[0]
    return normalized


def _load_apple_title_bootstrap_rows(
    session: Session,
    *,
    scope_keys: tuple[str, ...],
    min_sample_count: int,
    active_only: bool,
) -> list[dict[str, Any]]:
    lowered_title = func.lower(Item.title)
    stmt = (
        select(Item.title, Item.last_seen_at)
        .where(Item.business_domain.in_(scope_keys), Item.title.is_not(None))
        .where(
            or_(
                lowered_title.like('%m1 pro%'),
                lowered_title.like('%m2 pro%'),
                lowered_title.like('%m3 pro%'),
                lowered_title.like('%m4 pro%'),
                lowered_title.like('%m1 max%'),
                lowered_title.like('%m2 max%'),
                lowered_title.like('%m3 max%'),
                lowered_title.like('%m4 max%'),
                lowered_title.like('%m1 ultra%'),
                lowered_title.like('%m2 ultra%'),
                lowered_title.like('%m3 ultra%'),
                lowered_title.like('%m4 ultra%'),
                lowered_title.like('%m1pro%'),
                lowered_title.like('%m2pro%'),
                lowered_title.like('%m3pro%'),
                lowered_title.like('%m4pro%'),
                lowered_title.like('%m1max%'),
                lowered_title.like('%m2max%'),
                lowered_title.like('%m3max%'),
                lowered_title.like('%m4max%'),
                lowered_title.like('%m1ultra%'),
                lowered_title.like('%m2ultra%'),
                lowered_title.like('%m3ultra%'),
                lowered_title.like('%m4ultra%'),
            )
        )
    )
    if active_only:
        stmt = stmt.where(Item.is_active.is_(True))
    rows = session.execute(stmt).all()
    aggregated: dict[tuple[str, str | None, str | None, int | None, int | None], dict[str, Any]] = {}
    for row in rows:
        parsed = _parse_apple_title_bootstrap_row(str(row.title or '').strip())
        if parsed is None:
            continue
        key = (
            parsed['modelName'],
            parsed.get('seriesName'),
            parsed.get('chipFamily'),
            parsed.get('memoryGb'),
            parsed.get('storageGb'),
        )
        existing = aggregated.get(key)
        if existing is None:
            aggregated[key] = {
                **parsed,
                'sampleCount': 1,
                'lastSeenAt': row.last_seen_at.isoformat() if row.last_seen_at is not None else None,
                'source': 'bootstrap_from_titles_v1',
            }
            continue
        existing['sampleCount'] = int(existing.get('sampleCount') or 0) + 1
        existing['lastSeenAt'] = max(str(existing.get('lastSeenAt') or ''), row.last_seen_at.isoformat() if row.last_seen_at is not None else '') or None
    return [
        row
        for row in aggregated.values()
        if int(row.get('sampleCount') or 0) >= min_sample_count
    ]


def _parse_apple_title_bootstrap_row(title: str) -> dict[str, Any] | None:
    text = str(title or '').strip()
    lowered = text.lower()
    if not text or 'apple watch' in lowered:
        return None
    product_line = _extract_apple_product_line(text)
    chip_family = _extract_apple_chip_family(text)
    if not product_line or not chip_family:
        return None
    memory_gb = _extract_apple_memory_gb(text)
    storage_gb = _extract_apple_storage_gb(text)
    screen_size = _extract_apple_screen_size(text)
    model_name = _canonicalize_apple_model_name(
        model_name=f'{product_line} {chip_family}',
        series_name=product_line,
        chip_family=chip_family,
        memory_gb=memory_gb,
        storage_gb=storage_gb,
        screen_size=screen_size,
    )
    return {
        'modelName': model_name,
        'seriesName': product_line,
        'chipFamily': chip_family,
        'memoryGb': memory_gb,
        'storageGb': storage_gb,
    }


def _extract_apple_product_line(text: str) -> str | None:
    lowered = str(text or '').lower()
    if re.search(r'macbook\s*pro', lowered):
        return 'MacBook Pro'
    if re.search(r'macbook\s*air', lowered):
        return 'MacBook Air'
    if re.search(r'mac\s*studio', lowered):
        return 'Mac Studio'
    if re.search(r'mac\s*mini|macmini', lowered):
        return 'Mac mini'
    if re.search(r'\bimac\b', lowered):
        return 'iMac'
    return None


def _extract_apple_chip_family(text: str) -> str | None:
    match = re.search(r'\bm([1-4])\s*(pro|max|ultra)\b', str(text or ''), re.IGNORECASE)
    if match is None:
        compact = re.search(r'\bm([1-4])(pro|max|ultra)\b', str(text or ''), re.IGNORECASE)
        match = compact
    if match is None:
        return None
    return f"M{match.group(1)} {match.group(2).title()}"


def _extract_apple_memory_gb(text: str) -> int | None:
    raw = str(text or '')
    patterns = (
        r'(\d{1,3})\s*g(?:b)?\s*(?:内存|统一内存|运存|ram|运行内存)',
        r'(?:内存|统一内存|运存|ram|运行内存)\s*(\d{1,3})\s*g(?:b)?',
    )
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match is not None:
            value = int(match.group(1))
            if value in APPLE_ALLOWED_MEMORY_GB:
                return value
    values = [int(value) for value in re.findall(r'(\d{1,3})\s*g(?:b)?', raw, re.IGNORECASE)]
    for value in values:
        if value in APPLE_ALLOWED_MEMORY_GB:
            return value
    return None


def _extract_apple_storage_gb(text: str) -> int | None:
    raw = str(text or '')
    match_tb = re.search(r'(\d{1,2})\s*t(?:b)?', raw, re.IGNORECASE)
    if match_tb is not None:
        value = int(match_tb.group(1)) * 1024
        if value in APPLE_ALLOWED_STORAGE_GB:
            return value
    patterns = (
        r'(\d{3,5})\s*g(?:b)?\s*(?:ssd|闪存|硬盘|固态|存储)',
        r'(?:ssd|闪存|硬盘|固态|存储)\s*(\d{3,5})\s*g(?:b)?',
    )
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match is not None:
            value = int(match.group(1))
            if value in APPLE_ALLOWED_STORAGE_GB:
                return value
    values = [int(value) for value in re.findall(r'(\d{3,5})\s*g(?:b)?', raw, re.IGNORECASE)]
    for value in values:
        if value in APPLE_ALLOWED_STORAGE_GB:
            return value
    return None


def _extract_apple_screen_size(text: str) -> str | None:
    raw = str(text or '')
    match = re.search(r'\b(13|14|15|16|24)(?:\.\d)?\s*寸', raw)
    if match is None:
        match = re.search(r'\b(13|14|15|16|24)(?:\.\d)?\s*(?:in|inch)\b', raw, re.IGNORECASE)
    if match is None:
        return None
    return match.group(1)


def _canonicalize_apple_model_name(
    *,
    model_name: str,
    series_name: Any,
    chip_family: Any,
    memory_gb: Any,
    storage_gb: Any,
    screen_size: str | None = None,
) -> str | None:
    product_line = _extract_apple_product_line(series_name or model_name or '')
    chip = _extract_apple_chip_family(chip_family or model_name or '')
    if not product_line or not chip:
        return None
    parts: list[str] = [product_line]
    if product_line.startswith('MacBook') and screen_size:
        parts.append(f'{screen_size}in')
    parts.append(chip)
    if memory_gb not in (None, ''):
        parts.append(f'{int(memory_gb)}G')
    if storage_gb not in (None, ''):
        parts.append(f'{int(storage_gb)}G')
    return ' '.join(parts)


def _canonicalize_garmin_model_name(model_name: str) -> str | None:
    text = str(model_name or '').strip()
    lowered = text.lower()
    compact = re.sub(r'[^a-z0-9]+', '', lowered)
    if 'instinct2x' in compact:
        if 'solar' in compact or '太阳能' in text or 'mip' in compact:
            return 'Instinct 2X Solar'
        return 'Instinct 2X'
    if 'instinctcrossover' in compact:
        return 'Instinct Crossover'
    if 'instinct2' in compact:
        return 'Instinct 2'
    if 'instinctsolar' in compact:
        return 'Instinct Solar'
    if 'instinct' == compact or compact.startswith('instinct'):
        return 'Instinct'
    if 'tactix8' in compact:
        if 'amoled' in compact or '炫彩' in text:
            return 'Tactix 8 AMOLED'
        if 'solar' in compact or '太阳能' in text or 'mip' in compact:
            return 'Tactix 8 Solar'
        return 'Tactix 8'
    if 'tactix7' in compact:
        if 'amoled' in compact or '炫彩' in text or 'oled' in compact:
            return 'Tactix 7 AMOLED'
        if 'solar' in compact or '太阳能' in text or 'mip' in compact:
            return 'Tactix 7 Solar'
        return 'Tactix 7'
    if 'tactix' in compact:
        return 'Tactix'
    return None


def _matches_name_query(*, row: dict[str, Any], name_query: str | None) -> bool:
    query = str(name_query or '').strip().lower()
    if not query:
        return True
    haystack = ' '.join(
        str(value or '').strip().lower()
        for value in (row.get('modelName'), row.get('seriesName'), row.get('chipFamily'))
        if str(value or '').strip()
    )
    return query in haystack


def _reject_reason(canonical_category_code: str, model_name: str) -> str | None:
    text = str(model_name or '').strip()
    if not text:
        return 'empty_model_name'
    if len(text) < 3:
        return 'too_short'
    if len(text) > 80:
        return 'too_long'
    lowered = text.lower()
    if any(token.lower() in lowered for token in REJECT_MODEL_SUBSTRINGS):
        return 'contains_listing_copy'
    if canonical_category_code == 'garmin_watch' and not re.search(r'(fenix|forerunner|instinct|epix|marq|venu|approach|tactix)', lowered):
        return 'missing_known_product_line'
    if canonical_category_code == 'apple_computer' and not re.search(r'(macbook|mac mini|macmini|mac studio|macstudio|imac)', lowered):
        return 'missing_known_product_line'
    return None


def _build_model_payload(
    *,
    canonical_category_code: str,
    brand_name: str,
    row: dict[str, Any],
    used_codes: set[str],
) -> dict[str, Any]:
    model_name = str(row['modelName']).strip()
    source_name = str(row.get('source') or 'bootstrap_from_items_v1')
    base_code = _slugify_model_code(canonical_category_code, model_name)
    model_code = base_code
    if model_code in used_codes:
        model_code = f"{base_code}-{sha1(model_name.encode('utf-8')).hexdigest()[:6]}"
    used_codes.add(model_code)

    alias_texts: list[str] = []
    for alias in [model_name, row.get('seriesName')]:
        alias_clean = str(alias or '').strip()
        if alias_clean and alias_clean not in alias_texts:
            alias_texts.append(alias_clean)

    metadata = {
        'source': source_name,
        'canonicalCategoryCode': canonical_category_code,
        'sampleCount': int(row.get('sampleCount') or 0),
        'lastSeenAt': row.get('lastSeenAt'),
        'chipFamily': row.get('chipFamily'),
        'memoryGb': row.get('memoryGb'),
        'storageGb': row.get('storageGb'),
    }
    return {
        'categoryCode': canonical_category_code,
        'brandName': brand_name,
        'seriesName': row.get('seriesName'),
        'modelCode': model_code,
        'modelName': model_name,
        'status': 'ACTIVE',
        'metadata': metadata,
        'aliases': [
            {
                'aliasText': alias_text,
                'aliasType': 'BOOTSTRAP',
                'status': 'ACTIVE',
                'metadata': {'source': source_name},
            }
            for alias_text in alias_texts
        ],
    }


def _slugify_model_code(canonical_category_code: str, model_name: str) -> str:
    normalized = str(model_name or '').strip().lower()
    normalized = normalized.replace('+', ' plus ')
    normalized = normalized.replace('/', ' ')
    normalized = re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '_', normalized)
    normalized = re.sub(r'_+', '_', normalized).strip('_')
    if not normalized:
        normalized = sha1(model_name.encode('utf-8')).hexdigest()[:12]
    return f'{canonical_category_code}_{normalized}'[:128]
