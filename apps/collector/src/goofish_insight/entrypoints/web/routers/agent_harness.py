from __future__ import annotations

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ....application.services.agent_harness import build_agent_harness_snapshot

router = APIRouter()


@router.get("/api/dashboard/agent-harness/status", response_class=JSONResponse)
def agent_harness_status() -> JSONResponse:
    return JSONResponse(jsonable_encoder(build_agent_harness_snapshot()))
