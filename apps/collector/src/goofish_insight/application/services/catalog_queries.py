from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from ...models import (
    Category,
    CategoryAttrTemplate,
    ProductSku,
    ProductSkuAttrValue,
    ProductSpu,
    ProductSpuAttrValue,
    ProductStatus,
)


class CatalogQueryError(RuntimeError):
    pass


def build_catalog_spu_detail(session, spu_id: str) -> dict[str, Any] | None:
    spu = session.get(ProductSpu, spu_id)
    if spu is None:
        return None

    return {
        "spu": {
            "id": spu.id,
            "categoryId": spu.category_id,
            "templateId": spu.template_id,
            "merchantId": spu.merchant_id,
            "brandId": spu.brand_id,
            "title": spu.title,
            "status": spu.status.value,
            "attrSnapshotJson": spu.attr_snapshot_json,
            "createdAt": spu.created_at,
            "updatedAt": spu.updated_at,
        },
        "spuAttributes": [
            _serialize_attr_value(value)
            for value in sorted(
                spu.attributes,
                key=lambda row: (row.attribute.code, row.value_seq),
            )
        ],
        "skus": [
            _serialize_sku(sku)
            for sku in sorted(
                spu.skus,
                key=lambda row: row.sku_code,
            )
        ],
    }


def build_catalog_template_detail(session, template_id: str) -> dict[str, Any] | None:
    template = session.get(CategoryAttrTemplate, template_id)
    if template is None:
        return None

    items = sorted(template.items, key=lambda row: (row.sort_no, row.attribute.code))
    return {
        "category": {
            "id": template.category.id,
            "code": template.category.code,
            "name": template.category.name,
            "path": template.category.path,
            "level": template.category.level,
            "status": template.category.status,
        },
        "template": {
            "id": template.id,
            "categoryId": template.category_id,
            "version": template.version,
            "status": template.status.value,
            "effectiveAt": template.effective_at,
            "publishedBy": template.published_by,
            "createdAt": template.created_at,
            "updatedAt": template.updated_at,
        },
        "items": [
            {
                "attributeCode": item.attribute.code,
                "attributeId": item.attribute.id,
                "attributeName": item.attribute.name,
                "dataType": item.attribute.data_type.value,
                "valueScope": item.attribute.value_scope,
                "isMulti": item.attribute.is_multi,
                "isRequired": item.is_required,
                "isSale": item.is_sale,
                "isFilter": item.is_filter,
                "isSearch": item.is_search,
                "isDisplay": item.is_display,
                "role": item.role,
                "required": item.is_required,
                "weight": float(item.weight) if item.weight is not None else None,
                "normalization": item.normalization,
                "enumValues": item.enum_values,
                "sortNo": item.sort_no,
                "options": [
                    {
                        "optionId": option.id,
                        "optionCode": option.option_code,
                        "optionName": option.option_name,
                        "sortNo": option.sort_no,
                        "status": option.status.value,
                    }
                    for option in sorted(item.attribute.options, key=lambda row: (row.sort_no, row.option_code))
                ],
            }
            for item in items
        ],
    }


def build_catalog_category_templates(session, category_id: str) -> dict[str, Any] | None:
    category = session.get(Category, category_id)
    if category is None:
        return None

    templates = sorted(
        category.templates,
        key=lambda row: (-row.version, row.created_at),
    )
    return {
        "category": {
            "id": category.id,
            "code": category.code,
            "name": category.name,
            "path": category.path,
            "level": category.level,
            "status": category.status,
        },
        "templateCount": len(templates),
        "latestTemplateId": templates[0].id if templates else None,
        "templates": [
            {
                "id": template.id,
                "version": template.version,
                "status": template.status.value,
                "effectiveAt": template.effective_at,
                "publishedBy": template.published_by,
                "itemCount": len(template.items),
                "createdAt": template.created_at,
                "updatedAt": template.updated_at,
            }
            for template in templates
        ],
    }


def build_catalog_spu_page(
    session,
    *,
    page: int = 1,
    page_size: int = 20,
    category_id: str | None = None,
    template_id: str | None = None,
    merchant_id: str | None = None,
    status: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    normalized_page = int(page)
    normalized_page_size = int(page_size)
    if normalized_page <= 0:
        raise CatalogQueryError("page must be greater than 0.")
    if normalized_page_size <= 0:
        raise CatalogQueryError("page_size must be greater than 0.")
    normalized_page_size = min(normalized_page_size, 100)

    row_stmt = select(ProductSpu)
    count_stmt = select(func.count()).select_from(ProductSpu)
    row_stmt = _apply_spu_filters(
        row_stmt,
        category_id=category_id,
        template_id=template_id,
        merchant_id=merchant_id,
        status=status,
        title=title,
    )
    count_stmt = _apply_spu_filters(
        count_stmt,
        category_id=category_id,
        template_id=template_id,
        merchant_id=merchant_id,
        status=status,
        title=title,
    )

    total = int(session.execute(count_stmt).scalar_one() or 0)
    rows = session.execute(
        row_stmt
        .order_by(ProductSpu.updated_at.desc(), ProductSpu.created_at.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    ).scalars()
    spus = list(rows)

    return {
        "page": normalized_page,
        "pageSize": normalized_page_size,
        "total": total,
        "items": [_serialize_spu_summary(spu) for spu in spus],
    }


def build_catalog_sku_page(
    session,
    *,
    page: int = 1,
    page_size: int = 20,
    spu_id: str | None = None,
    category_id: str | None = None,
    template_id: str | None = None,
    merchant_id: str | None = None,
    status: str | None = None,
    sku_code: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    normalized_page = int(page)
    normalized_page_size = int(page_size)
    if normalized_page <= 0:
        raise CatalogQueryError("page must be greater than 0.")
    if normalized_page_size <= 0:
        raise CatalogQueryError("page_size must be greater than 0.")
    normalized_page_size = min(normalized_page_size, 100)

    row_stmt = select(ProductSku, ProductSpu).join(ProductSpu, ProductSku.spu_id == ProductSpu.id)
    count_stmt = select(func.count()).select_from(ProductSku).join(ProductSpu, ProductSku.spu_id == ProductSpu.id)
    row_stmt = _apply_sku_filters(
        row_stmt,
        spu_id=spu_id,
        category_id=category_id,
        template_id=template_id,
        merchant_id=merchant_id,
        status=status,
        sku_code=sku_code,
        title=title,
    )
    count_stmt = _apply_sku_filters(
        count_stmt,
        spu_id=spu_id,
        category_id=category_id,
        template_id=template_id,
        merchant_id=merchant_id,
        status=status,
        sku_code=sku_code,
        title=title,
    )

    total = int(session.execute(count_stmt).scalar_one() or 0)
    rows = session.execute(
        row_stmt
        .order_by(ProductSku.updated_at.desc(), ProductSku.created_at.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    ).all()

    return {
        "page": normalized_page,
        "pageSize": normalized_page_size,
        "total": total,
        "items": [_serialize_sku_summary(sku, spu) for sku, spu in rows],
    }


def build_catalog_sku_list(session, spu_id: str) -> list[dict[str, Any]]:
    spu = session.get(ProductSpu, spu_id)
    if spu is None:
        return []
    return [_serialize_sku(sku) for sku in sorted(spu.skus, key=lambda row: row.sku_code)]


def build_catalog_pricing_contract_row(
    *,
    business_domain: str | None,
    item_id: str | None,
    spu: ProductSpu | None,
    sku: ProductSku | None,
    fallback_spu_id: str | None = None,
    fallback_sku_code: str | None = None,
    title: str | None = None,
    price: Decimal | int | float | None = None,
) -> dict[str, Any]:
    resolved_spu_id = str(spu.id) if spu is not None else str(fallback_spu_id or "")
    resolved_sku_code = str(sku.sku_code) if sku is not None else str(fallback_sku_code or "")
    resolved_title = title
    if not resolved_title and spu is not None:
        resolved_title = spu.title
    resolved_price = _to_number(sku.price) if sku is not None else _to_number(price)
    return {
        "businessDomain": str(business_domain or ""),
        "itemId": str(item_id or ""),
        "spuId": resolved_spu_id,
        "skuCode": resolved_sku_code,
        "title": str(resolved_title or ""),
        "price": resolved_price,
    }


def _apply_spu_filters(
    stmt,
    *,
    category_id: str | None,
    template_id: str | None,
    merchant_id: str | None,
    status: str | None,
    title: str | None,
):
    if category_id:
        stmt = stmt.where(ProductSpu.category_id == category_id)
    if template_id:
        stmt = stmt.where(ProductSpu.template_id == template_id)
    if merchant_id:
        stmt = stmt.where(ProductSpu.merchant_id == merchant_id)
    if status:
        try:
            normalized_status = ProductStatus(str(status).upper())
        except ValueError as exc:
            raise CatalogQueryError(f"Invalid product status: {status}") from exc
        stmt = stmt.where(ProductSpu.status == normalized_status)
    if title:
        stmt = stmt.where(ProductSpu.title.ilike(f"%{title.strip()}%"))
    return stmt


def _apply_sku_filters(
    stmt,
    *,
    spu_id: str | None,
    category_id: str | None,
    template_id: str | None,
    merchant_id: str | None,
    status: str | None,
    sku_code: str | None,
    title: str | None,
):
    if spu_id:
        stmt = stmt.where(ProductSku.spu_id == spu_id)
    if category_id:
        stmt = stmt.where(ProductSpu.category_id == category_id)
    if template_id:
        stmt = stmt.where(ProductSpu.template_id == template_id)
    if merchant_id:
        stmt = stmt.where(ProductSpu.merchant_id == merchant_id)
    if status:
        try:
            normalized_status = ProductStatus(str(status).upper())
        except ValueError as exc:
            raise CatalogQueryError(f"Invalid product status: {status}") from exc
        stmt = stmt.where(ProductSku.status == normalized_status)
    if sku_code:
        stmt = stmt.where(ProductSku.sku_code.ilike(f"%{sku_code.strip()}%"))
    if title:
        stmt = stmt.where(ProductSpu.title.ilike(f"%{title.strip()}%"))
    return stmt


def _serialize_spu_summary(spu: ProductSpu) -> dict[str, Any]:
    snapshot = dict(spu.attr_snapshot_json or {})
    return {
        "id": spu.id,
        "categoryId": spu.category_id,
        "templateId": spu.template_id,
        "merchantId": spu.merchant_id,
        "brandId": spu.brand_id,
        "title": spu.title,
        "status": spu.status.value,
        "skuCount": len(list(snapshot.get("skus") or [])),
        "saleAttributeCodes": list(snapshot.get("saleAttributeCodes") or []),
        "createdAt": spu.created_at,
        "updatedAt": spu.updated_at,
    }


def _serialize_sku_summary(sku: ProductSku, spu: ProductSpu) -> dict[str, Any]:
    snapshot = dict(sku.attr_snapshot_json or {})
    return {
        "id": sku.id,
        "spuId": sku.spu_id,
        "categoryId": spu.category_id,
        "templateId": spu.template_id,
        "merchantId": spu.merchant_id,
        "title": spu.title,
        "skuCode": sku.sku_code,
        "salesSignatureRaw": sku.sales_signature_raw,
        "salesSignatureHash": sku.sales_signature_hash,
        "price": _to_number(sku.price),
        "stock": sku.stock,
        "barcode": sku.barcode,
        "status": sku.status.value,
        "saleAttributeCodes": [
            value.get("attributeCode")
            for value in list(snapshot.get("saleAttributes") or [])
            if value.get("attributeCode") is not None
        ],
        "createdAt": sku.created_at,
        "updatedAt": sku.updated_at,
    }


def _serialize_sku(sku: ProductSku) -> dict[str, Any]:
    return {
        "id": sku.id,
        "spuId": sku.spu_id,
        "skuCode": sku.sku_code,
        "salesSignatureRaw": sku.sales_signature_raw,
        "salesSignatureHash": sku.sales_signature_hash,
        "price": _to_number(sku.price),
        "stock": sku.stock,
        "barcode": sku.barcode,
        "status": sku.status.value,
        "attrSnapshotJson": sku.attr_snapshot_json,
        "createdAt": sku.created_at,
        "updatedAt": sku.updated_at,
        "attributes": [
            _serialize_attr_value(value)
            for value in sorted(
                sku.attributes,
                key=lambda row: (row.attribute.code, row.value_seq),
            )
        ],
    }


def _serialize_attr_value(value: ProductSpuAttrValue | ProductSkuAttrValue) -> dict[str, Any]:
    return {
        "attributeId": value.attribute_id,
        "attributeCode": value.attribute.code,
        "attributeName": value.attribute.name,
        "valueSeq": value.value_seq,
        "textValue": value.text_value,
        "numberValue": _to_number(value.number_value),
        "normalizedNumberValue": _to_number(value.normalized_number_value),
        "boolValue": value.bool_value,
        "optionId": value.option_id,
        "optionCode": value.option.option_code if value.option is not None else None,
        "optionName": value.option.option_name if value.option is not None else None,
        "jsonValue": value.json_value,
    }


def _to_number(value: Decimal | int | float | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if value == value.to_integral_value():
        return int(value)
    return float(value)
