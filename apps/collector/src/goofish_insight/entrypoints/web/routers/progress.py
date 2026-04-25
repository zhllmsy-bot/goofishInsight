from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse

from ....application.services.progress_sections import (
    ProgressSectionOptions,
    build_progress_audits_section_data,
    build_progress_header_section_data,
    build_progress_overview_section_data,
    build_progress_usage_workers_section_data,
)
from ....db import SessionLocal
from ....presentation.react_shell import react_shell_response

router = APIRouter()


def progress_section_options(
    business_domain: str | None = Query(default=None),
    category_code: str | None = Query(default=None),
) -> ProgressSectionOptions:
    return ProgressSectionOptions(business_domain=category_code or business_domain)


@router.get("/progress")
def review_progress(
) -> FileResponse:
    return react_shell_response()


@router.get("/api/progress/sections/header", response_class=JSONResponse)
def review_progress_header_section(
    request: Request,
    options: ProgressSectionOptions = Depends(progress_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_progress_header_section_data(
            session,
            options=options,
            current_ai_provider=request.app.state.current_ai_provider,
            current_ai_model=request.app.state.current_ai_model,
        )
    return JSONResponse(jsonable_encoder(section_data))


@router.get("/api/progress/sections/overview", response_class=JSONResponse)
def review_progress_overview_section(
    options: ProgressSectionOptions = Depends(progress_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_progress_overview_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))


@router.get("/api/progress/sections/usage-workers", response_class=JSONResponse)
def review_progress_usage_workers_section(
    options: ProgressSectionOptions = Depends(progress_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_progress_usage_workers_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))


@router.get("/api/progress/sections/audits", response_class=JSONResponse)
def review_progress_audits_section(
    options: ProgressSectionOptions = Depends(progress_section_options),
) -> JSONResponse:
    with SessionLocal() as session:
        section_data = build_progress_audits_section_data(session, options=options)
    return JSONResponse(jsonable_encoder(section_data))
