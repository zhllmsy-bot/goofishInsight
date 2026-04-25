from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from ..settings import get_settings

SETTINGS = get_settings()
REACT_DIST_DIR = SETTINGS.base_dir / "apps" / "dashboard-react" / "dist"
REACT_INDEX_PATH = REACT_DIST_DIR / "index.html"
REACT_ENTRYPOINT_PATHS = (
    "/",
    "/llm-ops",
    "/llm-devops",
    "/runtime",
    "/buy/opportunities",
    "/agent-harness",
    "/progress",
    "/onboarding/xianyu",
    "/mobile-overlay",
    "/config",
    "/config/categories",
    "/config/templates",
    "/config/tasks",
)
REACT_ITEM_DETAIL_PREFIX = "/items/"
REACT_PUBLIC_ASSET_PATHS = (
    "/favicon.svg",
    "/icons.svg",
)


def react_dist_dir() -> Path:
    return REACT_DIST_DIR


def react_shell_response(*, path: str | None = None) -> FileResponse:
    candidate_path = _resolve_react_asset_path(path)
    if candidate_path is None:
        raise HTTPException(status_code=404, detail="React asset not found")
    if not candidate_path.exists():
        raise HTTPException(
            status_code=503,
            detail='React build missing. Run "npm run build -w @goofish/dashboard-react" first.',
        )
    return FileResponse(candidate_path)


def _resolve_react_asset_path(path: str | None) -> Path | None:
    normalized = _normalize_request_path(path)
    if normalized in REACT_ENTRYPOINT_PATHS:
        return REACT_INDEX_PATH
    if normalized.startswith(REACT_ITEM_DETAIL_PREFIX):
        return REACT_INDEX_PATH
    if normalized in REACT_PUBLIC_ASSET_PATHS:
        return REACT_DIST_DIR / normalized.lstrip("/")
    if not normalized.startswith("/assets/"):
        return None

    asset_path = (REACT_DIST_DIR / normalized.lstrip("/")).resolve()
    try:
        asset_path.relative_to(REACT_DIST_DIR.resolve())
    except ValueError:
        return None
    return asset_path


def _normalize_request_path(path: str | None) -> str:
    candidate = str(path or "/").strip() or "/"
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    return candidate
