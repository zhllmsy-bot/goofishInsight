from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ....application.services.mobile_overlay_analysis import build_mobile_overlay_analysis
from ....application.services.mobile_overlay_vlm import build_overlay_vlm_runtime_status
from ....db import SessionLocal

router = APIRouter()


class OverlayOcrLinePayload(BaseModel):
    text: str
    left: int | None = None
    top: int | None = None
    right: int | None = None
    bottom: int | None = None


class OverlayAnalyzeRequest(BaseModel):
    source_package: str | None = None
    screen_width: int | None = Field(default=None, ge=1)
    screen_height: int | None = Field(default=None, ge=1)
    captured_at: str | None = None
    screenshot_base64: str | None = None
    ocr_lines: list[OverlayOcrLinePayload] = Field(default_factory=list)


@router.post("/api/mobile-overlay/analyze", response_class=JSONResponse)
def analyze_overlay(payload: OverlayAnalyzeRequest) -> JSONResponse:
    with SessionLocal() as session:
        result = build_mobile_overlay_analysis(
            session,
            source_package=payload.source_package,
            screen_width=payload.screen_width,
            screen_height=payload.screen_height,
            captured_at=payload.captured_at,
            screenshot_base64=payload.screenshot_base64,
            ocr_lines=[line.model_dump() for line in payload.ocr_lines],
        )
    return JSONResponse(result)


@router.get("/api/mobile-overlay/healthz", response_class=JSONResponse)
def overlay_health() -> JSONResponse:
    return JSONResponse({"ok": True, "vlm": build_overlay_vlm_runtime_status()})
