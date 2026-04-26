from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...models import ConditionAdjuster, MsrpAnchor, SkuFingerprint, SkuNeighbor


def load_condition_adjusters_by_scope_with_session(
    session: Session,
    *,
    scope_key: str | None,
) -> list[ConditionAdjuster]:
    normalized_scope = str(scope_key or "").strip()
    execute = getattr(session, "execute", None)
    if not normalized_scope or not callable(execute):
        return []
    return list(
        execute(
            select(ConditionAdjuster)
            .where(ConditionAdjuster.scope_key == normalized_scope)
            .where(ConditionAdjuster.status == "ACTIVE")
            .order_by(ConditionAdjuster.priority.asc(), ConditionAdjuster.id.asc())
        )
        .scalars()
        .all()
    )


def resolve_condition_adjuster_from_tags(
    *,
    tags: list[str],
    adjusters: list[ConditionAdjuster],
) -> dict[str, Any] | None:
    normalized_tags = [str(tag).strip().lower() for tag in tags if str(tag).strip()]
    if not normalized_tags:
        return None
    joined = " ".join(normalized_tags)
    for row in adjusters:
        tokens = [str(token).strip().lower() for token in (row.match_tokens or []) if str(token).strip()]
        if not tokens:
            continue
        if any(token in joined for token in tokens):
            return {
                "conditionCode": str(row.condition_code),
                "conditionLabel": str(row.condition_label or row.condition_code),
                "multiplier": Decimal(str(row.multiplier)),
                "source": "configured",
                "matchTokens": tokens,
            }
    return None


def refresh_sku_neighbors_with_session(
    session: Session,
    *,
    schema_id: int,
    top_k: int = 3,
    min_similarity: float = 0.35,
) -> dict[str, Any]:
    fingerprints = list(
        session.execute(
            select(SkuFingerprint)
            .where(SkuFingerprint.schema_id == int(schema_id))
            .order_by(SkuFingerprint.sample_count.desc(), SkuFingerprint.id.asc())
        )
        .scalars()
        .all()
    )
    session.execute(delete(SkuNeighbor).where(SkuNeighbor.schema_id == int(schema_id)))
    created = 0
    if len(fingerprints) < 2:
        return {"schemaId": int(schema_id), "fingerprintCount": len(fingerprints), "neighborCount": 0}

    for source in fingerprints:
        ranked: list[tuple[SkuFingerprint, float]] = []
        for candidate in fingerprints:
            if candidate.id == source.id:
                continue
            similarity = _fingerprint_similarity(source, candidate)
            if similarity < min_similarity:
                continue
            ranked.append((candidate, similarity))
        ranked.sort(key=lambda item: (-item[1], -(item[0].sample_count or 0), item[0].id))
        for neighbor_rank, (candidate, similarity) in enumerate(ranked[: max(int(top_k), 1)], start=1):
            session.add(
                SkuNeighbor(
                    schema_id=int(schema_id),
                    sku_fingerprint_id=int(source.id),
                    neighbor_fingerprint_id=int(candidate.id),
                    neighbor_rank=neighbor_rank,
                    similarity_score=Decimal(str(round(similarity, 4))),
                    payload={
                        "sourceFingerprintHash": str(source.fingerprint_hash),
                        "neighborFingerprintHash": str(candidate.fingerprint_hash),
                        "sourceSampleCount": int(source.sample_count or 0),
                        "neighborSampleCount": int(candidate.sample_count or 0),
                    },
                )
            )
            created += 1
    return {"schemaId": int(schema_id), "fingerprintCount": len(fingerprints), "neighborCount": created}


def load_sku_neighbor_hashes_by_source_with_session(
    session: Session,
    *,
    schema_ids: set[int] | None = None,
) -> dict[str, list[str]]:
    stmt = (
        select(
            SkuNeighbor,
            SkuFingerprint.fingerprint_hash,
            SkuFingerprint.id,
        )
        .join(SkuFingerprint, SkuFingerprint.id == SkuNeighbor.neighbor_fingerprint_id)
        .order_by(SkuNeighbor.sku_fingerprint_id.asc(), SkuNeighbor.neighbor_rank.asc())
    )
    if schema_ids:
        stmt = stmt.where(SkuNeighbor.schema_id.in_(tuple(sorted(int(value) for value in schema_ids))))
    rows = list(session.execute(stmt).all())
    if not rows:
        return {}
    source_rows = list(
        session.execute(
            select(SkuFingerprint.id, SkuFingerprint.fingerprint_hash).where(
                SkuFingerprint.id.in_(tuple({int(row[0].sku_fingerprint_id) for row in rows}))
            )
        ).all()
    )
    source_hash_by_id = {int(row_id): str(fingerprint_hash) for row_id, fingerprint_hash in source_rows}
    neighbor_hashes: dict[str, list[str]] = defaultdict(list)
    for neighbor_row, neighbor_hash, _neighbor_id in rows:
        source_hash = source_hash_by_id.get(int(neighbor_row.sku_fingerprint_id))
        if not source_hash or not neighbor_hash:
            continue
        neighbor_hashes[source_hash].append(str(neighbor_hash))
    return dict(neighbor_hashes)


def load_msrp_anchors_by_key_with_session(
    session: Session,
    *,
    scope_key: str | None,
    as_of: date | None = None,
) -> dict[tuple[str | None, str], MsrpAnchor]:
    normalized_scope = str(scope_key or "").strip()
    if not normalized_scope:
        return {}
    target_date = as_of or date.today()
    rows = list(
        session.execute(
            select(MsrpAnchor)
            .where(MsrpAnchor.scope_key == normalized_scope)
            .where(MsrpAnchor.status == "ACTIVE")
            .order_by(MsrpAnchor.effective_from.desc().nullslast(), MsrpAnchor.updated_at.desc())
        )
        .scalars()
        .all()
    )
    indexed: dict[tuple[str | None, str], MsrpAnchor] = {}
    for row in rows:
        if row.effective_from is not None and row.effective_from > target_date:
            continue
        key = (_normalize_optional_string(row.model_catalog_id), str(row.anchor_key))
        if key not in indexed:
            indexed[key] = row
    return indexed


def _fingerprint_similarity(left: SkuFingerprint, right: SkuFingerprint) -> float:
    left_projection = dict((left.raw_signature or {}).get("projection") or {})
    right_projection = dict((right.raw_signature or {}).get("projection") or {})
    if left_projection or right_projection:
        keys = sorted(set(left_projection) | set(right_projection))
        matched = 0
        comparable = 0
        for key in keys:
            left_value = left_projection.get(key)
            right_value = right_projection.get(key)
            if left_value is None or right_value is None:
                continue
            comparable += 1
            if _stable_value(left_value) == _stable_value(right_value):
                matched += 1
        score = (matched / comparable) if comparable else 0.0
    else:
        left_signature = dict(left.lock_signature or {})
        left_signature.update(dict(left.variant_signature or {}))
        right_signature = dict(right.lock_signature or {})
        right_signature.update(dict(right.variant_signature or {}))
        keys = sorted(set(left_signature) | set(right_signature))
        matched = 0
        comparable = 0
        for key in keys:
            left_value = left_signature.get(key)
            right_value = right_signature.get(key)
            if left_value is None or right_value is None:
                continue
            comparable += 1
            if _stable_value(left_value) == _stable_value(right_value):
                matched += 1
        score = (matched / comparable) if comparable else 0.0
    if dict(left.lock_signature or {}) == dict(right.lock_signature or {}) and score > 0:
        score = min(score + 0.15, 0.99)
    return round(score, 4)


def _stable_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "load_condition_adjusters_by_scope_with_session",
    "load_msrp_anchors_by_key_with_session",
    "load_sku_neighbor_hashes_by_source_with_session",
    "refresh_sku_neighbors_with_session",
    "resolve_condition_adjuster_from_tags",
]
