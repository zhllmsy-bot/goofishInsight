from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from ....application.services.dashboard_sections import (
    DashboardSectionOptions,
    build_dashboard_calibration_section_data,
    build_dashboard_focus_section_data,
    build_dashboard_filters_section_data,
    build_dashboard_hero_section_data,
    build_dashboard_insights_section_data,
    build_dashboard_items_section_data,
    build_dashboard_llm_traces_section_data,
    build_dashboard_ops_section_data,
    build_dashboard_pricing_section_data,
)
from ....application.services.llm_prompt_traces import load_dashboard_llm_trace_detail
from ....application.services.dashboard_page import build_dashboard_page_data
from ....application.services.dashboard_queries import build_item_detail
from ....application.services.listing_preferences import upsert_user_listing_preference
from ....application.services.runtime_controls import (
    RuntimeControlError,
    build_runtime_control_panel_data,
    run_runtime_action,
)
from ....category_compat import resolve_category_code
from ....db import SessionLocal
from ....models import RawResponse
from ....presentation.react_shell import react_shell_response

router = APIRouter()


class RuntimeActionRequest(BaseModel):
    target: Literal[
        "market_collectors",
        "home_feed",
        "batch_collect",
        "analyzer_runtime",
        "buy_jobs",
        "local_model",
        "vlm_runtime",
        "review_runtime",
        "review_v3_direct",
        "template_smoke",
    ]
    action: Literal[
        "start",
        "restart",
        "stop",
        "enable_message_mode",
        "enable_dry_run",
        "switch_to_qwen3_30b",
        "switch_to_qwen25_32b",
        "start_vlm",
        "stop_vlm",
        "restart_vlm",
        "run_smoke",
        "run_now",
        "start_second_pass",
        "build-buy-baselines",
        "refresh-buy-opportunities",
        "emit-buy-alerts",
    ]
    categoryCode: str | None = None


class ListingPreferenceRequest(BaseModel):
    item_id: str
    preference: Literal["interested", "not_interested"]
    reason: str | None = None


def dashboard_section_options(
    business_domain: str | None = Query(default=None),
    category_code: str | None = Query(default=None),
    limit: int = Query(default=36, ge=12, le=120),
    pricing_view: str = Query(default="product"),
    pricing_scope: str = Query(default="actionable"),
    pricing_limit: int = Query(default=12, ge=6, le=60),
    pricing_freshness_days: int = Query(default=30, ge=7, le=180),
    heartbeat_days: int = Query(default=3, ge=1, le=30),
    pricing_min_samples: int = Query(default=4, ge=2, le=20),
    product_label: str | None = Query(default=None),
    spec_label: str | None = Query(default=None),
    display_type: str | None = Query(default=None),
    case_size_mm: str | None = Query(default=None),
    is_solar: str | None = Query(default=None),
    chip_family: str | None = Query(default=None),
    screen_size_in: str | None = Query(default=None),
    memory_gb: str | None = Query(default=None),
    storage_gb: str | None = Query(default=None),
) -> DashboardSectionOptions:
    return DashboardSectionOptions(
        business_domain=business_domain,
        limit=limit,
        pricing_view=pricing_view,
        pricing_scope=pricing_scope,
        pricing_limit=pricing_limit,
        pricing_freshness_days=pricing_freshness_days,
        heartbeat_days=heartbeat_days,
        pricing_min_samples=pricing_min_samples,
        raw_filters={
            "product_label": product_label,
            "spec_label": spec_label,
            "display_type": display_type,
            "case_size_mm": case_size_mm,
            "is_solar": is_solar,
            "chip_family": chip_family,
            "screen_size_in": screen_size_in,
            "memory_gb": memory_gb,
            "storage_gb": storage_gb,
        },
        category_code=resolve_category_code(category_code or business_domain) or None,
    )


@router.get("/")
def dashboard() -> FileResponse:
    return react_shell_response()


@router.get("/llm-ops")
@router.get("/llm-devops")
@router.get("/runtime")
@router.get("/agent-harness")
def dashboard_react_shell() -> FileResponse:
    return react_shell_response()


@router.get("/favicon.svg")
@router.get("/icons.svg")
def dashboard_react_asset(request: Request) -> FileResponse:
    return react_shell_response(path=request.url.path)


@router.get("/api/dashboard/sections/hero", response_class=JSONResponse)
def dashboard_hero_section(
    options: DashboardSectionOptions = Depends(dashboard_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_dashboard_hero_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))


@router.get("/api/dashboard/sections/filters", response_class=JSONResponse)
def dashboard_filters_section(
    options: DashboardSectionOptions = Depends(dashboard_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_dashboard_filters_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))


@router.get("/api/dashboard/sections/focus", response_class=JSONResponse)
def dashboard_focus_section(
    options: DashboardSectionOptions = Depends(dashboard_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_dashboard_focus_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))


@router.get("/api/dashboard/sections/insights", response_class=JSONResponse)
def dashboard_insights_section(
    options: DashboardSectionOptions = Depends(dashboard_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_dashboard_insights_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))


@router.get("/api/dashboard/sections/pricing", response_class=JSONResponse)
def dashboard_pricing_section(
    options: DashboardSectionOptions = Depends(dashboard_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_dashboard_pricing_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))


@router.get("/api/dashboard/sections/ops", response_class=JSONResponse)
def dashboard_ops_section(
    options: DashboardSectionOptions = Depends(dashboard_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_dashboard_ops_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))


@router.get("/api/dashboard/sections/llm-traces", response_class=JSONResponse)
def dashboard_llm_traces_section() -> JSONResponse:
    return JSONResponse(jsonable_encoder(build_dashboard_llm_traces_section_data()))


@router.get("/api/dashboard/llm-traces/{trace_key}", response_class=JSONResponse)
def dashboard_llm_trace_detail(trace_key: str) -> JSONResponse:
    trace = load_dashboard_llm_trace_detail(trace_key)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return JSONResponse(jsonable_encoder({"trace": trace}))


@router.get("/api/dashboard/runtime/status", response_class=JSONResponse)
def dashboard_runtime_status(
    category_code: str | None = Query(default=None),
) -> JSONResponse:
    return JSONResponse(
        jsonable_encoder(
            build_runtime_control_panel_data(
                category_code=resolve_category_code(category_code) or None,
            )
        )
    )


@router.post("/api/dashboard/runtime/actions", response_class=JSONResponse)
def dashboard_runtime_action(payload: RuntimeActionRequest) -> JSONResponse:
    try:
        result = run_runtime_action(
            target=payload.target,
            action=payload.action,
            category_code=resolve_category_code(payload.categoryCode) or None,
        )
    except RuntimeControlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder(result))


@router.get("/api/dashboard/sections/calibration", response_class=JSONResponse)
def dashboard_calibration_section(
    options: DashboardSectionOptions = Depends(dashboard_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_dashboard_calibration_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))


@router.get("/api/dashboard/sections/items", response_class=JSONResponse)
def dashboard_items_section(
    options: DashboardSectionOptions = Depends(dashboard_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_dashboard_items_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))


@router.post("/api/dashboard/listing-preferences", response_class=JSONResponse)
def dashboard_listing_preference(payload: ListingPreferenceRequest) -> JSONResponse:
    try:
        with SessionLocal() as session:
            preference = upsert_user_listing_preference(
                session,
                item_id=payload.item_id,
                preference=payload.preference,
                reason=payload.reason,
                metadata={"entrypoint": "dashboard_listing_card"},
            )
            session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder({"preference": preference}))


@router.get("/items/{item_id}")
def item_detail(item_id: str) -> FileResponse:
    with SessionLocal() as session:
        detail = build_item_detail(session, item_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Item not found")
    return react_shell_response()


@router.get("/api/dashboard/items/{item_id}", response_class=JSONResponse)
def item_detail_api(item_id: str) -> JSONResponse:
    with SessionLocal() as session:
        detail = build_item_detail(session, item_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Item not found")
    return JSONResponse(jsonable_encoder(detail))


@router.get("/api/raw-responses/{raw_response_id}", response_class=JSONResponse)
def raw_response_detail(raw_response_id: str) -> JSONResponse:
    with SessionLocal() as session:
        raw_response = session.get(RawResponse, raw_response_id)
        if raw_response is None:
            raise HTTPException(status_code=404, detail="Raw response not found")
        return JSONResponse(raw_response.response_body)


@router.get("/healthz", response_class=JSONResponse)
def health() -> JSONResponse:
    return JSONResponse({"ok": True})
