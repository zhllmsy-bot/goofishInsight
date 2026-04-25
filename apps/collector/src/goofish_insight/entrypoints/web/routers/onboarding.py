from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ....application.services.xianyu_onboarding_discovery import (
    XianyuOnboardingDiscoveryError,
    run_xianyu_onboarding_discovery,
)
from ....application.services.xianyu_category_mapping import (
    XianyuCategoryMappingError,
    build_xianyu_category_onboarding_draft,
    build_xianyu_raw_category_coverage_report,
    list_xianyu_category_onboarding_queue,
    persist_xianyu_category_onboarding,
    sync_xianyu_category_onboarding_queue,
    update_xianyu_category_onboarding_queue_status,
)
from ....presentation.react_shell import react_shell_response

router = APIRouter()


class OnboardingQueueSyncRequest(BaseModel):
    operatorId: str
    sourceKeyword: str | None = None
    taskId: int | None = None
    businessDomain: str | None = None
    itemScanLimit: int = 2000
    apply: bool = False


class OnboardingQueueStatusRequest(BaseModel):
    operatorId: str
    status: str
    queueId: str | None = None
    matchKey: str | None = None
    ownerOperatorId: str | None = None
    statusNote: str | None = None
    apply: bool = False


class OnboardingDraftRequest(BaseModel):
    sourceKeyword: str | None = None
    taskId: int | None = None
    businessDomain: str | None = None
    xianyuCatId: str | None = None
    xianyuTbCatId: str | None = None
    xianyuCCatId: str | None = None
    sampleLimit: int = 25
    preferUnmapped: bool = True


class OnboardingPersistRequest(BaseModel):
    operatorId: str
    payload: dict[str, Any]
    apply: bool = False


class OnboardingDiscoveryRequest(BaseModel):
    sourceKeyword: str
    taskKey: str | None = None
    businessDomain: str | None = None
    pages: int = 1
    profileKey: str = "default"
    loginWaitSeconds: int = 180


@router.get("/onboarding/xianyu", response_class=HTMLResponse)
def xianyu_onboarding_page() -> HTMLResponse:
    return react_shell_response()


@router.get("/api/onboarding/xianyu/coverage", response_class=JSONResponse)
def xianyu_onboarding_coverage(
    source_keyword: str | None = Query(default=None),
    task_id: int | None = Query(default=None),
    business_domain: str | None = Query(default=None),
    unmapped_limit: int = Query(default=20, ge=1, le=200),
    item_scan_limit: int = Query(default=2000, ge=1, le=5000),
) -> JSONResponse:
    detail = build_xianyu_raw_category_coverage_report(
        source_keyword=source_keyword,
        task_id=task_id,
        business_domain=business_domain,
        unmapped_limit=unmapped_limit,
        item_scan_limit=item_scan_limit,
    )
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/onboarding/xianyu/queue", response_class=JSONResponse)
def xianyu_onboarding_queue(
    status: str | None = Query(default=None),
    include_closed: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
) -> JSONResponse:
    try:
        detail = list_xianyu_category_onboarding_queue(
            status=status,
            include_closed=include_closed,
            limit=limit,
        )
    except XianyuCategoryMappingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/onboarding/xianyu/queue/sync", response_class=JSONResponse)
def xianyu_onboarding_queue_sync(payload: OnboardingQueueSyncRequest) -> JSONResponse:
    try:
        detail = sync_xianyu_category_onboarding_queue(
            operator_id=payload.operatorId,
            source_keyword=payload.sourceKeyword,
            task_id=payload.taskId,
            business_domain=payload.businessDomain,
            item_scan_limit=payload.itemScanLimit,
            dry_run=not payload.apply,
        )
    except XianyuCategoryMappingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/onboarding/xianyu/queue/status", response_class=JSONResponse)
def xianyu_onboarding_queue_status(payload: OnboardingQueueStatusRequest) -> JSONResponse:
    try:
        detail = update_xianyu_category_onboarding_queue_status(
            operator_id=payload.operatorId,
            status=payload.status,
            queue_id=payload.queueId,
            match_key=payload.matchKey,
            owner_operator_id=payload.ownerOperatorId,
            status_note=payload.statusNote,
            dry_run=not payload.apply,
        )
    except XianyuCategoryMappingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/onboarding/xianyu/discovery", response_class=JSONResponse)
def xianyu_onboarding_discovery(payload: OnboardingDiscoveryRequest) -> JSONResponse:
    try:
        detail = run_xianyu_onboarding_discovery(
            source_keyword=payload.sourceKeyword,
            task_key=payload.taskKey,
            business_domain=payload.businessDomain,
            pages=payload.pages,
            profile_key=payload.profileKey,
            login_wait_seconds=payload.loginWaitSeconds,
        )
    except XianyuOnboardingDiscoveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/onboarding/xianyu/draft", response_class=JSONResponse)
def xianyu_onboarding_draft(payload: OnboardingDraftRequest) -> JSONResponse:
    try:
        detail = build_xianyu_category_onboarding_draft(
            source_keyword=payload.sourceKeyword,
            task_id=payload.taskId,
            business_domain=payload.businessDomain,
            xianyu_cat_id=payload.xianyuCatId,
            xianyu_tb_cat_id=payload.xianyuTbCatId,
            xianyu_c_cat_id=payload.xianyuCCatId,
            sample_limit=payload.sampleLimit,
            prefer_unmapped=payload.preferUnmapped,
        )
    except XianyuCategoryMappingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/onboarding/xianyu/persist", response_class=JSONResponse)
def xianyu_onboarding_persist(payload: OnboardingPersistRequest) -> JSONResponse:
    try:
        detail = persist_xianyu_category_onboarding(
            payload=payload.payload,
            operator_id=payload.operatorId,
            dry_run=not payload.apply,
        )
    except XianyuCategoryMappingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(detail))
