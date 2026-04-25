from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ....application.services.attribute_config import (
    AttributeConfigError,
    list_attribute_configs,
    upsert_attribute_config,
)
from ....application.services.category_config import (
    CategoryConfigError,
    list_category_configs,
    upsert_category_config,
)
from ....application.services.category_ai_config import (
    CategoryAIConfigError,
    apply_category_ai_draft,
    generate_category_ai_draft,
)
from ....application.services.task_config import (
    TaskConfigError,
    list_task_configs,
    upsert_task_config,
)
from ....application.services.template_config import (
    TemplateConfigError,
    get_template_config,
    list_template_configs,
    preview_template_config_diff,
    upsert_template_config,
)
from ....application.services.model_config import (
    ModelConfigError,
    export_model_configs,
    import_model_configs,
    list_model_configs,
    upsert_model_config,
)
from ....application.services.raw_cate_policy_config import (
    RawCatePolicyConfigError,
    list_raw_cate_policy_configs,
    upsert_raw_cate_policy_config,
)
from ....presentation.react_shell import react_shell_response

router = APIRouter()

# Legacy admin-only template pages.
# These pages use server-side Jinja templates and are reserved for admin/support operations.
# All main operations work should use the React frontend instead.


class CategoryConfigUpsertRequest(BaseModel):
    operatorId: str
    payload: dict[str, Any]
    apply: bool = False


class CategoryAIDraftRequest(BaseModel):
    description: str
    categoryCodeHint: str | None = None


class CategoryAIApplyRequest(BaseModel):
    operatorId: str
    draft: dict[str, Any]
    apply: bool = True
    allowExistingCategoryUpdate: bool = False
    allowActiveTemplateRebind: bool = False


class AttributeConfigUpsertRequest(BaseModel):
    operatorId: str
    payload: dict[str, Any]
    apply: bool = False


class TaskConfigUpsertRequest(BaseModel):
    operatorId: str
    payload: dict[str, Any]
    apply: bool = False


class TemplateConfigUpsertRequest(BaseModel):
    operatorId: str
    payload: dict[str, Any]
    apply: bool = False


class TemplateConfigDiffPreviewRequest(BaseModel):
    payload: dict[str, Any]


class ModelConfigUpsertRequest(BaseModel):
    operatorId: str
    payload: dict[str, Any]
    apply: bool = False


class ModelConfigImportRequest(BaseModel):
    operatorId: str
    payload: dict[str, Any]
    apply: bool = False


class RawCatePolicyConfigUpsertRequest(BaseModel):
    operatorId: str
    payload: dict[str, Any]
    apply: bool = False


@router.get("/config/categories", response_class=HTMLResponse)
@router.get("/config", response_class=HTMLResponse)
def category_config_page(request: Request) -> HTMLResponse:
    _ = request
    return react_shell_response()


@router.get("/config/attributes", response_class=HTMLResponse)
def attribute_config_page(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "config_attributes.html",
        {
            "request": request,
            "page_title": "Attribute Config",
        },
    )


@router.get("/config/tasks", response_class=HTMLResponse)
def task_config_page(request: Request) -> HTMLResponse:
    _ = request
    return react_shell_response()


@router.get("/config/templates", response_class=HTMLResponse)
def template_config_page(request: Request) -> HTMLResponse:
    _ = request
    return react_shell_response()


@router.get("/config/models", response_class=HTMLResponse)
def model_config_page(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "config_models.html",
        {
            "request": request,
            "page_title": "Model Config",
        },
    )


@router.get("/config/raw-cate-policy", response_class=HTMLResponse)
def raw_cate_policy_config_page(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "config_raw_cate_policy.html",
        {
            "request": request,
            "page_title": "Raw Cate Policy Config",
        },
    )


@router.get("/api/config/categories", response_class=JSONResponse)
def category_config_list(
    status: str | None = Query(default=None),
) -> JSONResponse:
    try:
        detail = list_category_configs(status=status)
    except CategoryConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/config/attributes", response_class=JSONResponse)
def attribute_config_list(
    status: str | None = Query(default=None),
    scope_type: str | None = Query(default=None),
) -> JSONResponse:
    try:
        detail = list_attribute_configs(status=status, scope_type=scope_type)
    except AttributeConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/config/tasks", response_class=JSONResponse)
def task_config_list(
    status: str | None = Query(default=None),
    category_code: str | None = Query(default=None),
) -> JSONResponse:
    try:
        detail = list_task_configs(status=status, category_code=category_code)
    except TaskConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/config/templates", response_class=JSONResponse)
def template_config_list(
    status: str | None = Query(default=None),
    category_code: str | None = Query(default=None),
) -> JSONResponse:
    try:
        detail = list_template_configs(status=status, category_code=category_code)
    except TemplateConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/config/templates/{template_id}", response_class=JSONResponse)
def template_config_detail(
    template_id: str,
    compare_to_template_id: str | None = Query(default=None),
) -> JSONResponse:
    try:
        detail = get_template_config(
            template_id=template_id,
            compare_to_template_id=compare_to_template_id,
        )
    except TemplateConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/config/models", response_class=JSONResponse)
def model_config_list(
    status: str | None = Query(default=None),
    category_code: str | None = Query(default=None),
    brand_name: str | None = Query(default=None),
) -> JSONResponse:
    try:
        detail = list_model_configs(
            status=status,
            category_code=category_code,
            brand_name=brand_name,
        )
    except ModelConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/config/models/export", response_class=JSONResponse)
def model_config_export(
    status: str | None = Query(default=None),
    category_code: str | None = Query(default=None),
    brand_name: str | None = Query(default=None),
) -> JSONResponse:
    try:
        detail = export_model_configs(
            status=status,
            category_code=category_code,
            brand_name=brand_name,
        )
    except ModelConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/config/raw-cate-policy", response_class=JSONResponse)
def raw_cate_policy_config_list(
    status: str | None = Query(default=None),
    policy_mode: str | None = Query(default=None),
) -> JSONResponse:
    try:
        detail = list_raw_cate_policy_configs(status=status, policy_mode=policy_mode)
    except RawCatePolicyConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/config/categories", response_class=JSONResponse)
def category_config_upsert(payload: CategoryConfigUpsertRequest) -> JSONResponse:
    try:
        detail = upsert_category_config(
            payload=payload.payload,
            operator_id=payload.operatorId,
            dry_run=not payload.apply,
        )
    except CategoryConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/config/categories/ai-draft", response_class=JSONResponse)
def category_ai_draft(payload: CategoryAIDraftRequest) -> JSONResponse:
    try:
        detail = generate_category_ai_draft(
            description=payload.description,
            category_code_hint=payload.categoryCodeHint,
        )
    except CategoryAIConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/config/categories/ai-apply", response_class=JSONResponse)
def category_ai_apply(payload: CategoryAIApplyRequest) -> JSONResponse:
    try:
        detail = apply_category_ai_draft(
            operator_id=payload.operatorId,
            draft=payload.draft,
            dry_run=not payload.apply,
            allow_existing_category_update=payload.allowExistingCategoryUpdate,
            allow_active_template_rebind=payload.allowActiveTemplateRebind,
        )
    except CategoryAIConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/config/attributes", response_class=JSONResponse)
def attribute_config_upsert(payload: AttributeConfigUpsertRequest) -> JSONResponse:
    try:
        detail = upsert_attribute_config(
            payload=payload.payload,
            operator_id=payload.operatorId,
            dry_run=not payload.apply,
        )
    except AttributeConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/config/tasks", response_class=JSONResponse)
def task_config_upsert(payload: TaskConfigUpsertRequest) -> JSONResponse:
    try:
        detail = upsert_task_config(
            payload=payload.payload,
            operator_id=payload.operatorId,
            dry_run=not payload.apply,
        )
    except TaskConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/config/templates", response_class=JSONResponse)
def template_config_upsert(payload: TemplateConfigUpsertRequest) -> JSONResponse:
    try:
        detail = upsert_template_config(
            payload=payload.payload,
            operator_id=payload.operatorId,
            dry_run=not payload.apply,
        )
    except TemplateConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/config/templates/diff-preview", response_class=JSONResponse)
def template_config_diff_preview(payload: TemplateConfigDiffPreviewRequest) -> JSONResponse:
    try:
        detail = preview_template_config_diff(payload=payload.payload)
    except TemplateConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/config/models", response_class=JSONResponse)
def model_config_upsert(payload: ModelConfigUpsertRequest) -> JSONResponse:
    try:
        detail = upsert_model_config(
            payload=payload.payload,
            operator_id=payload.operatorId,
            dry_run=not payload.apply,
        )
    except ModelConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/config/models/import", response_class=JSONResponse)
def model_config_import(payload: ModelConfigImportRequest) -> JSONResponse:
    try:
        detail = import_model_configs(
            payload=payload.payload,
            operator_id=payload.operatorId,
            dry_run=not payload.apply,
        )
    except ModelConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/config/raw-cate-policy", response_class=JSONResponse)
def raw_cate_policy_config_upsert(payload: RawCatePolicyConfigUpsertRequest) -> JSONResponse:
    try:
        detail = upsert_raw_cate_policy_config(
            payload=payload.payload,
            operator_id=payload.operatorId,
            dry_run=not payload.apply,
        )
    except RawCatePolicyConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))
