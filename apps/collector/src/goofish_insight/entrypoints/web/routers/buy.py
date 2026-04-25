from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from ....analyzer_runtime import ensure_analyzer_src_on_path
from ....application.services.dashboard_queries import build_item_detail
from ....db import SessionLocal
from ....presentation.react_shell import react_shell_response

ensure_analyzer_src_on_path()

from goofish_analyzer.services.buy_decision_hub import (  # noqa: E402
    apply_buy_feedback_calibration_with_session,
    build_buy_data_value_report_with_session,
    build_buy_opportunity_detail_with_session,
    build_buy_opportunity_workbench,
    build_buy_price_baselines_with_session,
    build_buy_watch_targets_with_session,
    record_buy_decision_feedback_with_session,
    summarize_buy_feedback_calibration_with_session,
    summarize_buy_feedback_quality_with_session,
    summarize_template_availability_monitoring_with_session,
)
from goofish_analyzer.services.buy_feedback import BuyFeedbackError  # noqa: E402

router = APIRouter()


class BuyFeedbackRequest(BaseModel):
    opportunityId: str
    feedbackLabel: str
    feedbackType: str = "decision"
    operatorId: str | None = None
    feedbackNote: str | None = None
    purchasePrice: str | None = None
    expectedResalePrice: str | None = None
    linkToAlertCandidate: bool = False


class BuyFeedbackCalibrationApplyRequest(BaseModel):
    categoryCode: str
    windowDays: int = 30
    operatorId: str | None = None
    recommendationIds: list[str] | None = None


@router.get("/buy/opportunities")
def buy_opportunities_page(
    category_code: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> FileResponse:
    return react_shell_response()


@router.get("/buy/opportunities/{opportunity_id}")
def buy_opportunity_detail_page(
    opportunity_id: str,
    category_code: str | None = Query(default=None),
) -> FileResponse:
    return react_shell_response()


@router.get("/buy/targets")
def buy_targets_page(
    category_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> FileResponse:
    return react_shell_response()


@router.get("/buy/baselines")
def buy_baselines_page(
    category_code: str | None = Query(default=None),
) -> FileResponse:
    return react_shell_response()


@router.get("/api/buy/opportunities", response_class=JSONResponse)
def buy_opportunities_api(
    category_code: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> JSONResponse:
    with SessionLocal() as session:
        data = build_buy_opportunity_workbench(
            session,
            category_code=category_code,
            limit=limit,
        )
    return JSONResponse(jsonable_encoder(data))


@router.get("/api/buy/data-value", response_class=JSONResponse)
def buy_data_value_api(
    category_code: str | None = Query(default=None),
) -> JSONResponse:
    with SessionLocal() as session:
        data = build_buy_data_value_report_with_session(
            session,
            category_code=category_code,
        )
    return JSONResponse(jsonable_encoder(data))


@router.get("/api/buy/targets", response_class=JSONResponse)
def buy_targets_api(
    category_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> JSONResponse:
    with SessionLocal() as session:
        data = build_buy_watch_targets_with_session(
            session,
            category_code=category_code,
            status=status,
            limit=limit,
        )
    return JSONResponse(jsonable_encoder(data))


@router.get("/api/buy/baselines", response_class=JSONResponse)
def buy_price_baselines_api(
    category_code: str | None = Query(default=None),
    baseline_date: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> JSONResponse:
    with SessionLocal() as session:
        data = build_buy_price_baselines_with_session(
            session,
            category_code=category_code,
            baseline_date=baseline_date,
            limit=limit,
        )
    return JSONResponse(jsonable_encoder(data))


@router.get("/api/buy/opportunities/{opportunity_id}", response_class=JSONResponse)
def buy_opportunity_detail_api(
    opportunity_id: str,
    category_code: str | None = Query(default=None),
) -> JSONResponse:
    with SessionLocal() as session:
        detail = build_buy_opportunity_detail_with_session(
            session,
            opportunity_id=opportunity_id,
            category_code=category_code,
        )
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Opportunity not found: {opportunity_id}")
        item_id = (
            dict(detail.get("opportunity") or {}).get("itemId")
            or dict(detail.get("opportunity") or {}).get("itemIdRef")
        )
        detail["itemDetail"] = build_item_detail(session, str(item_id)) if item_id else None
    return JSONResponse(jsonable_encoder(detail))


@router.post("/api/buy/feedback", response_class=JSONResponse)
def buy_feedback_api(payload: BuyFeedbackRequest) -> JSONResponse:
    try:
        with SessionLocal() as session:
            result = record_buy_decision_feedback_with_session(
                session,
                opportunity_id=payload.opportunityId,
                feedback_type=payload.feedbackType,
                feedback_label=payload.feedbackLabel,
                operator_id=payload.operatorId,
                feedback_note=payload.feedbackNote,
                purchase_price=payload.purchasePrice,
                expected_resale_price=payload.expectedResalePrice,
                link_to_alert_candidate=payload.linkToAlertCandidate,
            )
            session.commit()
    except BuyFeedbackError as exc:
        message = str(exc)
        status_code = 404 if message.startswith("Opportunity not found:") else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return JSONResponse(jsonable_encoder(result))


@router.get("/api/buy/feedback-quality", response_class=JSONResponse)
def buy_feedback_quality_api(
    category_code: str | None = Query(default=None),
    window_days: int = Query(default=30, ge=1, le=180),
) -> JSONResponse:
    with SessionLocal() as session:
        result = summarize_buy_feedback_quality_with_session(
            session,
            category_code=category_code,
            window_days=window_days,
        )
    return JSONResponse(jsonable_encoder(result))


@router.get("/api/buy/feedback-calibration", response_class=JSONResponse)
def buy_feedback_calibration_api(
    category_code: str | None = Query(default=None),
    window_days: int = Query(default=30, ge=1, le=180),
) -> JSONResponse:
    with SessionLocal() as session:
        result = summarize_buy_feedback_calibration_with_session(
            session,
            category_code=category_code,
            window_days=window_days,
        )
    return JSONResponse(jsonable_encoder(result))


@router.post("/api/buy/feedback-calibration/apply", response_class=JSONResponse)
def buy_feedback_calibration_apply_api(payload: BuyFeedbackCalibrationApplyRequest) -> JSONResponse:
    try:
        with SessionLocal() as session:
            result = apply_buy_feedback_calibration_with_session(
                session,
                category_code=payload.categoryCode,
                window_days=payload.windowDays,
                operator_id=payload.operatorId,
                recommendation_ids=payload.recommendationIds,
            )
            session.commit()
    except BuyFeedbackError as exc:
        message = str(exc)
        status_code = 404 if message.startswith("Category not found:") else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return JSONResponse(jsonable_encoder(result))


@router.get("/api/buy/template-monitoring", response_class=JSONResponse)
def buy_template_monitoring_api(
    category_code: str | None = Query(default=None),
    window_days: int = Query(default=30, ge=1, le=180),
) -> JSONResponse:
    with SessionLocal() as session:
        result = summarize_template_availability_monitoring_with_session(
            session,
            category_code=category_code,
            window_days=window_days,
        )
    return JSONResponse(jsonable_encoder(result))
