from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import ControlPlaneConfig, load_config
from .routes import STATIC_DIR, router as http_router
from .state import ConductorManager
from .ws import router as ws_router


def create_app(config: ControlPlaneConfig | None = None) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title="DBOS Control Plane")
    app.state.control_plane_config = config
    app.state.conductor_manager = ConductorManager(
        app_name=config.app_name,
        conductor_key=config.conductor_key,
        request_timeout_seconds=config.request_timeout_seconds,
        system_database_url=config.system_database_url,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(http_router)
    app.include_router(ws_router)
    return app
