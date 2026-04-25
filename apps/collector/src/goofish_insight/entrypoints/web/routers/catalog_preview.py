from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ....application.services.catalog_preview import (
    preview_catalog_signature as preview_catalog_signature_service,
    preview_catalog_snapshot as preview_catalog_snapshot_service,
)
from ....application.services.catalog_persistence import (
    CatalogPersistenceError,
    persist_catalog_payload,
    replace_catalog_payload,
)
from ....application.services.catalog_queries import (
    CatalogQueryError,
    build_catalog_category_templates,
    build_catalog_sku_page,
    build_catalog_spu_page,
    build_catalog_sku_list,
    build_catalog_spu_detail,
    build_catalog_template_detail,
)
from ....application.services.catalog_template import (
    CatalogTemplatePersistenceError,
    persist_catalog_template_payload,
)
from ....application.services.catalog_template_version import (
    CatalogTemplateVersionError,
    persist_catalog_template_version_payload,
)
from ....application.services.catalog_upgrade import (
    CatalogTemplateUpgradeApplyError,
    CatalogTemplateReplaceApplyError,
    CatalogTemplateReplacePlanError,
    CatalogTemplateUpgradePreviewError,
    apply_catalog_template_upgrade,
    apply_catalog_template_replace_plan,
    preview_catalog_template_replace_plan,
    preview_catalog_template_upgrade,
)
from ....application.services.catalog_write import prepare_catalog_persist_plan
from ....db import SessionLocal

router = APIRouter()


class TemplateItemModel(BaseModel):
    attributeCode: str
    attributeId: str | None = None
    isSale: bool = False
    sortNo: int = 0


class AttributeDefinitionModel(BaseModel):
    code: str
    name: str
    dataType: Literal["TEXT", "NUMBER", "BOOLEAN", "ENUM", "JSON"]
    isMulti: bool = False


class AttributeValueModel(BaseModel):
    attributeCode: str
    textValue: str | None = None
    numberValue: float | None = None
    normalizedNumberValue: float | None = None
    boolValue: bool | None = None
    optionId: str | None = None
    optionCode: str | None = None
    optionName: str | None = None
    jsonValue: dict[str, Any] | list[Any] | None = None
    unit: str | None = None


class SpuModel(BaseModel):
    id: str | None = None
    categoryId: str
    templateId: str
    merchantId: str | None = None
    brandId: str | None = None
    title: str
    status: str = "DRAFT"


class SkuPreviewModel(BaseModel):
    skuCode: str
    price: float
    stock: int
    barcode: str | None = None
    status: str = "DRAFT"
    saleAttributes: list[AttributeValueModel] = Field(default_factory=list)
    attributes: list[AttributeValueModel] = Field(default_factory=list)


class SignaturePreviewRequest(BaseModel):
    templateItems: list[TemplateItemModel]
    attributes: list[AttributeDefinitionModel]
    selections: list[AttributeValueModel]


class SnapshotPreviewRequest(BaseModel):
    requestId: str | None = None
    spu: SpuModel
    templateItems: list[TemplateItemModel]
    attributes: list[AttributeDefinitionModel]
    spuAttributes: list[AttributeValueModel] = Field(default_factory=list)
    skus: list[SkuPreviewModel] = Field(default_factory=list)


class PersistCatalogRequest(BaseModel):
    requestId: str | None = None
    operatorId: str = "admin"
    dryRun: bool = True
    spu: SpuModel
    spuAttributes: list[AttributeValueModel] = Field(default_factory=list)
    skus: list[SkuPreviewModel] = Field(default_factory=list)


class AttributeOptionModel(BaseModel):
    id: str | None = None
    optionCode: str
    optionName: str
    sortNo: int = 0
    status: str = "ACTIVE"


class TemplateAttributeDefinitionModel(BaseModel):
    id: str | None = None
    scopeType: str = "PLATFORM"
    scopeId: str = "platform"
    code: str
    name: str
    dataType: Literal["TEXT", "NUMBER", "BOOLEAN", "ENUM", "JSON"]
    valueScope: str
    isMulti: bool = False
    unit: str | None = None
    validationSchema: dict[str, Any] | None = None
    status: str = "ACTIVE"
    options: list[AttributeOptionModel] = Field(default_factory=list)


class CategoryPersistModel(BaseModel):
    id: str | None = None
    code: str
    name: str
    path: str
    level: int
    status: str = "ACTIVE"


class TemplatePersistItemModel(BaseModel):
    attributeCode: str
    isRequired: bool = False
    isSale: bool = False
    isFilter: bool = False
    isSearch: bool = False
    isDisplay: bool = True
    sortNo: int = 0


class TemplatePersistModel(BaseModel):
    id: str | None = None
    version: int
    status: str = "DRAFT"
    effectiveAt: str | None = None
    publishedBy: str | None = None
    items: list[TemplatePersistItemModel] = Field(default_factory=list)


class PersistCatalogTemplateRequest(BaseModel):
    requestId: str | None = None
    operatorId: str = "admin"
    dryRun: bool = True
    category: CategoryPersistModel
    attributes: list[TemplateAttributeDefinitionModel]
    template: TemplatePersistModel


class PersistCatalogTemplateVersionRequest(BaseModel):
    requestId: str | None = None
    operatorId: str = "admin"
    dryRun: bool = True
    categoryId: str
    template: TemplatePersistModel


class TemplateUpgradePreviewRequest(BaseModel):
    targetTemplateId: str


class TemplateUpgradeApplyRequest(BaseModel):
    requestId: str | None = None
    operatorId: str = "admin"
    dryRun: bool = True
    targetTemplateId: str


def _snapshot_request_payload(payload: SnapshotPreviewRequest) -> dict[str, Any]:
    return {
        "requestId": payload.requestId,
        "spu": payload.spu.model_dump(),
        "templateItems": [item.model_dump() for item in payload.templateItems],
        "attributes": [item.model_dump() for item in payload.attributes],
        "spuAttributes": [item.model_dump() for item in payload.spuAttributes],
        "skus": [item.model_dump() for item in payload.skus],
    }


def _persist_request_payload(payload: PersistCatalogRequest) -> dict[str, Any]:
    return {
        "requestId": payload.requestId,
        "spu": payload.spu.model_dump(),
        "spuAttributes": [item.model_dump() for item in payload.spuAttributes],
        "skus": [item.model_dump() for item in payload.skus],
    }


@router.post("/api/catalog/tools/signature/preview", response_class=JSONResponse)
def preview_catalog_signature_route(payload: SignaturePreviewRequest) -> JSONResponse:
    result = preview_catalog_signature_service(
        {
            "templateItems": [item.model_dump() for item in payload.templateItems],
            "attributes": [item.model_dump() for item in payload.attributes],
            "selections": [item.model_dump() for item in payload.selections],
        }
    )
    return JSONResponse(result)


@router.post("/api/catalog/tools/snapshot/preview", response_class=JSONResponse)
def preview_catalog_snapshot_route(payload: SnapshotPreviewRequest) -> JSONResponse:
    result = preview_catalog_snapshot_service(_snapshot_request_payload(payload))
    return JSONResponse(result)


@router.post("/api/catalog/tools/persist-plan/preview", response_class=JSONResponse)
def preview_catalog_persist_plan_route(payload: SnapshotPreviewRequest) -> JSONResponse:
    result = prepare_catalog_persist_plan(_snapshot_request_payload(payload))
    return JSONResponse(result)


@router.post("/api/catalog/tools/persist", response_class=JSONResponse)
def persist_catalog_route(payload: PersistCatalogRequest) -> JSONResponse:
    try:
        result = persist_catalog_payload(
            payload=_persist_request_payload(payload),
            operator_id=payload.operatorId,
            dry_run=payload.dryRun,
        )
    except CatalogPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@router.post("/api/catalog/tools/replace", response_class=JSONResponse)
def replace_catalog_route(payload: PersistCatalogRequest) -> JSONResponse:
    try:
        result = replace_catalog_payload(
            payload=_persist_request_payload(payload),
            operator_id=payload.operatorId,
            dry_run=payload.dryRun,
        )
    except CatalogPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@router.post("/api/catalog/tools/template/persist", response_class=JSONResponse)
def persist_catalog_template_route(payload: PersistCatalogTemplateRequest) -> JSONResponse:
    try:
        result = persist_catalog_template_payload(
            payload={
                "requestId": payload.requestId,
                "category": payload.category.model_dump(),
                "attributes": [item.model_dump() for item in payload.attributes],
                "template": payload.template.model_dump(),
            },
            operator_id=payload.operatorId,
            dry_run=payload.dryRun,
        )
    except CatalogTemplatePersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@router.post("/api/catalog/tools/template-version/persist", response_class=JSONResponse)
def persist_catalog_template_version_route(payload: PersistCatalogTemplateVersionRequest) -> JSONResponse:
    try:
        result = persist_catalog_template_version_payload(
            payload={
                "requestId": payload.requestId,
                "categoryId": payload.categoryId,
                "template": payload.template.model_dump(),
            },
            operator_id=payload.operatorId,
            dry_run=payload.dryRun,
        )
    except CatalogTemplateVersionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@router.get("/api/catalog/spus", response_class=JSONResponse)
def catalog_spu_page_route(
    category_id: str | None = Query(None, alias="categoryId"),
    template_id: str | None = Query(None, alias="templateId"),
    merchant_id: str | None = Query(None, alias="merchantId"),
    status: str | None = Query(None),
    title: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
) -> JSONResponse:
    with SessionLocal() as session:
        try:
            detail = build_catalog_spu_page(
                session,
                page=page,
                page_size=page_size,
                category_id=category_id,
                template_id=template_id,
                merchant_id=merchant_id,
                status=status,
                title=title,
            )
        except CatalogQueryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/catalog/skus", response_class=JSONResponse)
def catalog_sku_page_route(
    spu_id: str | None = Query(None, alias="spuId"),
    category_id: str | None = Query(None, alias="categoryId"),
    template_id: str | None = Query(None, alias="templateId"),
    merchant_id: str | None = Query(None, alias="merchantId"),
    status: str | None = Query(None),
    sku_code: str | None = Query(None, alias="skuCode"),
    title: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
) -> JSONResponse:
    with SessionLocal() as session:
        try:
            detail = build_catalog_sku_page(
                session,
                page=page,
                page_size=page_size,
                spu_id=spu_id,
                category_id=category_id,
                template_id=template_id,
                merchant_id=merchant_id,
                status=status,
                sku_code=sku_code,
                title=title,
            )
        except CatalogQueryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/catalog/spus/{spu_id}", response_class=JSONResponse)
def catalog_spu_detail_route(spu_id: str) -> JSONResponse:
    with SessionLocal() as session:
        detail = build_catalog_spu_detail(session, spu_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="SPU not found")
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/catalog/spus/{spu_id}/skus", response_class=JSONResponse)
def catalog_spu_skus_route(spu_id: str) -> JSONResponse:
    with SessionLocal() as session:
        detail = build_catalog_spu_detail(session, spu_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="SPU not found")
        rows = build_catalog_sku_list(session, spu_id)
    return JSONResponse(jsonable_encoder({"spuId": spu_id, "skus": rows}))


@router.get("/api/catalog/templates/{template_id}", response_class=JSONResponse)
def catalog_template_detail_route(template_id: str) -> JSONResponse:
    with SessionLocal() as session:
        detail = build_catalog_template_detail(session, template_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/catalog/categories/{category_id}/templates", response_class=JSONResponse)
def catalog_category_templates_route(category_id: str) -> JSONResponse:
    with SessionLocal() as session:
        detail = build_catalog_category_templates(session, category_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/catalog/spus/{spu_id}/template-upgrades/preview", response_class=JSONResponse)
def catalog_template_upgrade_preview_route(
    spu_id: str,
    payload: TemplateUpgradePreviewRequest,
) -> JSONResponse:
    try:
        result = preview_catalog_template_upgrade(
            spu_id=spu_id,
            target_template_id=payload.targetTemplateId,
        )
    except CatalogTemplateUpgradePreviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@router.post("/api/catalog/spus/{spu_id}/template-upgrades/replace-plan/preview", response_class=JSONResponse)
def catalog_template_replace_plan_preview_route(
    spu_id: str,
    payload: TemplateUpgradePreviewRequest,
) -> JSONResponse:
    try:
        result = preview_catalog_template_replace_plan(
            spu_id=spu_id,
            target_template_id=payload.targetTemplateId,
        )
    except CatalogTemplateReplacePlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@router.post("/api/catalog/spus/{spu_id}/template-upgrades/apply", response_class=JSONResponse)
def catalog_template_upgrade_apply_route(
    spu_id: str,
    payload: TemplateUpgradeApplyRequest,
) -> JSONResponse:
    try:
        result = apply_catalog_template_upgrade(
            spu_id=spu_id,
            target_template_id=payload.targetTemplateId,
            operator_id=payload.operatorId,
            request_id=payload.requestId,
            dry_run=payload.dryRun,
        )
    except CatalogTemplateUpgradeApplyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@router.post("/api/catalog/spus/{spu_id}/template-upgrades/replace-plan/apply", response_class=JSONResponse)
def catalog_template_replace_plan_apply_route(
    spu_id: str,
    payload: TemplateUpgradeApplyRequest,
) -> JSONResponse:
    try:
        result = apply_catalog_template_replace_plan(
            spu_id=spu_id,
            target_template_id=payload.targetTemplateId,
            operator_id=payload.operatorId,
            request_id=payload.requestId,
            dry_run=payload.dryRun,
        )
    except CatalogTemplateReplaceApplyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)
