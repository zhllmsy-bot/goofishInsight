from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .entrypoints.web.routers.agent_harness import router as agent_harness_router
from .entrypoints.web.routers.catalog_preview import router as catalog_preview_router
from .entrypoints.web.routers.buy import router as buy_router
from .entrypoints.web.routers.config import router as config_router
from .entrypoints.web.routers.dashboard import router as dashboard_router
from .entrypoints.web.routers.mobile_overlay import router as mobile_overlay_router
from .entrypoints.web.routers.onboarding import router as onboarding_router
from .entrypoints.web.routers.progress import router as progress_router
from .logging import configure_logging
from .presentation.react_shell import react_dist_dir
from .presentation.web import register_template_filters
from .settings import get_settings

SETTINGS = get_settings()
TEMPLATE_DIR = SETTINGS.base_dir / "apps" / "web" / "templates"
STATIC_DIR = SETTINGS.base_dir / "apps" / "web" / "static"
REACT_DIST_DIR = react_dist_dir()


def _static_asset_version(static_dir: Path) -> str:
    latest_mtime_ns = 0
    for path in static_dir.rglob("*"):
        if path.is_file():
            latest_mtime_ns = max(latest_mtime_ns, path.stat().st_mtime_ns)
    return str(latest_mtime_ns or 1)


def _cors_origins(raw_origins: str) -> list[str]:
    return [origin.strip() for origin in str(raw_origins or "").split(",") if origin.strip()]


def create_app() -> FastAPI:
    configure_logging()
    application = FastAPI(title="Goofish Insight Dashboard")
    cors_origins = _cors_origins(SETTINGS.dashboard_cors_origins)
    if cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    react_assets_dir = REACT_DIST_DIR / "assets"
    if react_assets_dir.exists():
        application.mount("/assets", StaticFiles(directory=str(react_assets_dir)), name="dashboard-assets")

    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    register_template_filters(templates)

    application.state.templates = templates
    application.state.current_ai_provider = SETTINGS.ai_provider
    application.state.current_ai_model = SETTINGS.ai_model
    application.state.asset_version = _static_asset_version(STATIC_DIR)

    application.include_router(agent_harness_router)
    application.include_router(dashboard_router)
    application.include_router(buy_router)
    application.include_router(config_router)
    application.include_router(onboarding_router)
    application.include_router(catalog_preview_router)
    application.include_router(mobile_overlay_router)
    application.include_router(progress_router)
    return application


app = create_app()
