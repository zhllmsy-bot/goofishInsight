from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from ...db import session_scope
from ...models import Item, ItemSpecEnrichment
from ...specs import SpecEnrichmentCandidate, extract_item_specs
from .spec_candidate_queue import load_items_for_enrichment as load_items_for_enrichment_from_queue


def load_items_for_enrichment(
    *,
    business_domain: str | None,
    item_id: str | None,
    limit: int,
    force: bool,
    session_factory: Callable = session_scope,
) -> list[int]:
    return load_items_for_enrichment_from_queue(
        business_domain=business_domain,
        item_id=item_id,
        limit=limit,
        force=force,
        session_factory=session_factory,
    )


def enrich_single_item(
    *,
    db_item_id: int,
    allow_llm: bool,
    session_factory: Callable = session_scope,
) -> dict[str, Any]:
    with session_factory() as session:
        item = session.get(Item, db_item_id)
        if item is None:
            raise RuntimeError(f"Item {db_item_id} not found.")

        candidate = upsert_item_spec_enrichment_for_item(
            session=session,
            item_id_ref=db_item_id,
            allow_llm=allow_llm,
        )
        if candidate is None:
            raise RuntimeError(f"Item {db_item_id} disappeared during enrichment.")

        confidence = float(candidate.confidence) if candidate.confidence is not None else None
        return {
            "item_id": item.item_id,
            "status": candidate.status,
            "confidence": confidence,
            "model_name": candidate.model_name,
            "extractor_type": candidate.extractor_type,
        }


def run_spec_enrichment_batch_with_session(
    session,
    *,
    business_domain: str | None = None,
    item_id: str | None = None,
    limit: int = 50,
    force: bool = False,
    allow_llm: bool = True,
) -> dict[str, Any]:
    item_ids = load_items_for_enrichment(
        business_domain=business_domain,
        item_id=item_id,
        limit=limit,
        force=force,
    )
    summary = {
        "processed": 0,
        "complete": 0,
        "partial": 0,
        "unresolved": 0,
        "failed": 0,
        "llm_used": 0,
        "items": [],
    }
    for db_item_id in item_ids:
        summary["processed"] += 1
        try:
            candidate = upsert_item_spec_enrichment_for_item(
                session=session,
                item_id_ref=int(db_item_id),
                allow_llm=allow_llm,
            )
            if candidate is None:
                raise RuntimeError(f"Item {db_item_id} disappeared during enrichment.")
            item = session.get(Item, int(db_item_id))
            status_key = candidate.status if candidate.status in summary else "failed"
            summary[status_key] += 1
            if candidate.extractor_type in {"llm", "hybrid"}:
                summary["llm_used"] += 1
            summary["items"].append(
                {
                    "itemIdRef": int(db_item_id),
                    "itemId": getattr(item, "item_id", None),
                    "status": candidate.status,
                    "confidence": float(candidate.confidence) if candidate.confidence is not None else None,
                    "modelName": candidate.model_name,
                    "extractorType": candidate.extractor_type,
                }
            )
        except Exception as exc:
            summary["failed"] += 1
            summary["items"].append({"itemIdRef": int(db_item_id), "error": str(exc)})
    return summary


def upsert_item_spec_enrichment_for_item(
    *,
    session,
    item_id_ref: int,
    allow_llm: bool,
) -> SpecEnrichmentCandidate | None:
    item = session.get(Item, item_id_ref)
    if item is None:
        return None

    candidate = extract_item_specs(item, allow_llm=allow_llm)
    upsert_item_spec_enrichment_candidate_for_item(
        session=session,
        item_id_ref=item_id_ref,
        candidate=candidate,
    )
    return candidate


def upsert_item_spec_enrichment_candidate_for_item(
    *,
    session,
    item_id_ref: int,
    candidate: SpecEnrichmentCandidate,
) -> SpecEnrichmentCandidate | None:
    item = session.get(Item, item_id_ref)
    if item is None:
        return None
    payload = candidate.to_record(item=item)
    upsert_stmt = insert(ItemSpecEnrichment).values(**payload)
    excluded = upsert_stmt.excluded
    session.execute(
        upsert_stmt.on_conflict_do_update(
            constraint="uq_item_spec_enrichments_item_id_ref",
            set_={
                "business_domain": excluded.business_domain,
                "category_id": excluded.category_id,
                "template_id": excluded.template_id,
                "model_catalog_id": excluded.model_catalog_id,
                "extractor_type": excluded.extractor_type,
                "extractor_version": excluded.extractor_version,
                "llm_provider": excluded.llm_provider,
                "llm_model": excluded.llm_model,
                "status": excluded.status,
                "confidence": excluded.confidence,
                "needs_review": excluded.needs_review,
                "brand": excluded.brand,
                "product_line": excluded.product_line,
                "model_family": excluded.model_family,
                "model_name": excluded.model_name,
                "generation": excluded.generation,
                "case_size_mm": excluded.case_size_mm,
                "is_solar": excluded.is_solar,
                "display_type": excluded.display_type,
                "screen_size_in": excluded.screen_size_in,
                "chip_family": excluded.chip_family,
                "cpu_model": excluded.cpu_model,
                "cpu_cores": excluded.cpu_cores,
                "gpu_cores": excluded.gpu_cores,
                "memory_gb": excluded.memory_gb,
                "storage_gb": excluded.storage_gb,
                "edition_tags": excluded.edition_tags,
                "evidence": excluded.evidence,
                "extraction_payload": excluded.extraction_payload,
                "updated_at": func.now(),
            },
        )
    )
    propagate_specs_to_item(item=item, payload=payload)
    return candidate


def backfill_spec_confidence(
    *,
    dry_run: bool = False,
    limit: int | None = None,
    extractor_type: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "extractor_type": extractor_type,
        "scanned": 0,
        "updated": 0,
        "skipped_no_source": 0,
        "sources": {},
    }
    with session_scope() as session:
        stmt = (
            select(ItemSpecEnrichment, Item)
            .join(Item, Item.id == ItemSpecEnrichment.item_id_ref)
            .where(ItemSpecEnrichment.confidence.is_(None))
            .order_by(ItemSpecEnrichment.updated_at.desc(), ItemSpecEnrichment.id.desc())
        )
        if extractor_type:
            stmt = stmt.where(ItemSpecEnrichment.extractor_type == extractor_type)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = list(session.execute(stmt).all())
        summary["scanned"] = len(rows)
        source_counts: dict[str, int] = defaultdict(int)
        for spec, item in rows:
            desired_confidence = _extract_confidence_from_payload(spec.extraction_payload)
            confidence_source = "extraction_payload"
            if desired_confidence is None:
                desired_confidence = _extract_confidence_from_payload(spec.evidence)
                confidence_source = "evidence"
            if desired_confidence is None and (spec.extractor_type or "").strip().lower() == "llm_review":
                desired_confidence = _coerce_backfill_confidence(item.llm_review_confidence)
                confidence_source = "item_llm_review_confidence"
            if desired_confidence is None:
                summary["skipped_no_source"] += 1
                continue
            spec.confidence = desired_confidence
            source_counts[confidence_source] += 1
            summary["updated"] += 1
        summary["sources"] = dict(sorted(source_counts.items()))
        if dry_run:
            session.rollback()
    return summary


def propagate_specs_to_item(*, item: Item, payload: dict[str, Any]) -> None:
    if payload.get("brand"):
        item.normalized_brand = payload["brand"]
    if payload.get("product_line") or payload.get("model_family"):
        item.normalized_model_family = payload.get("model_family") or payload.get("product_line")
    if payload.get("model_name"):
        item.normalized_model = payload["model_name"]
    if payload.get("chip_family"):
        item.normalized_chip = payload["chip_family"]
    if payload.get("memory_gb") is not None:
        item.normalized_memory_gb = payload["memory_gb"]
    if payload.get("storage_gb") is not None:
        item.normalized_storage_gb = payload["storage_gb"]


def _coerce_backfill_confidence(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        numeric = Decimal(str(value))
    except Exception:
        return None
    if numeric > 1:
        numeric /= Decimal("100")
    numeric = max(Decimal("0"), min(numeric, Decimal("1")))
    return numeric.quantize(Decimal("0.01"))


def _extract_confidence_from_payload(payload: dict[str, Any] | None) -> Decimal | None:
    if not isinstance(payload, dict):
        return None
    direct_value = payload.get("confidence")
    if direct_value is None:
        direct_value = payload.get("self_confidence")
    return _coerce_backfill_confidence(direct_value)


__all__ = [
    "backfill_spec_confidence",
    "enrich_single_item",
    "load_items_for_enrichment",
    "propagate_specs_to_item",
    "run_spec_enrichment_batch_with_session",
    "upsert_item_spec_enrichment_candidate_for_item",
    "upsert_item_spec_enrichment_for_item",
]
