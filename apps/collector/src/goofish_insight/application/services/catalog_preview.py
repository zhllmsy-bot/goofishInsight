from __future__ import annotations

from typing import Any

from ...domain.catalog.contracts import build_product_snapshot, build_sales_signature


def preview_catalog_signature(payload: dict[str, Any]) -> dict[str, str]:
    return build_sales_signature(
        template_items=list(payload.get("templateItems") or []),
        attributes=list(payload.get("attributes") or []),
        selections=list(payload.get("selections") or []),
    )


def preview_catalog_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return build_product_snapshot(
        spu=dict(payload.get("spu") or {}),
        template_items=list(payload.get("templateItems") or []),
        attributes=list(payload.get("attributes") or []),
        spu_attributes=list(payload.get("spuAttributes") or []),
        skus=list(payload.get("skus") or []),
    )
