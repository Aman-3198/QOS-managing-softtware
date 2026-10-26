"""FastAPI application factory.

The backend is unprivileged and binds to 127.0.0.1 by default. It reads system
state directly; all privileged work is delegated to the helper (Phase 5+).
Auth is enforced only once a password is configured (Phase 9) — dev stays open
otherwise, with a visible banner in the UI.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import analytics as analytics_api
from .api import auth as auth_api
from .api import devices as devices_api
from .api import diagnostics as diagnostics_api
from .api import health as health_api
from .api import hotspot as hotspot_api
from .api import network as network_api
from .api import policies as policies_api
from .api import qos as qos_api
from .api import settings as settings_api
from .api import system as system_api
from .api import ws as ws_api
from .config import settings
from .core.exceptions import SmartQoSError
from .database import init_db
from .logging_config import setup_logging
from .schemas import ErrorResponse
from .services.analytics_service import AnalyticsService
from .services.auth_service import AuthService
from .services.connectivity import ConnectivityProbe
from .services.device_service import DeviceService
from .services.diagnostics_service import DiagnosticsService
from .services.hotspot_service import HotspotService
from .services.monitor import Monitor, MonitorHub
from .services.network_info import NetworkContext
from .services.policy_service import PolicyService
from .services.qos_service import QoSService
from .services.settings_service import SettingsService

# Paths that never require auth (liveness, auth itself, docs, SPA shell, websocket).
PUBLIC_API_PATHS = {"/api/health", "/api/auth/login", "/api/auth/me", "/api/auth/logout",
                    "/api/openapi.json", "/api/docs", "/docs", "/openapi.json"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log = setup_logging(settings.log_level, settings.log_dir)
    log.info("starting %s v%s", settings.app_name, __version__)
    app.state.started_at = time.time()
    app.state.logger = log
    app.state.network_ctx = NetworkContext()
    app.state.connectivity_probe = ConnectivityProbe(
        host=settings.connectivity_host,
        fallback_hosts=settings.connectivity_fallbacks,
        port=settings.connectivity_port,
        timeout_s=settings.connectivity_timeout_s,
        ttl_s=settings.connectivity_ttl_s,
    )
    app.state.device_service = DeviceService(app.state.network_ctx)
    app.state.qos_service = QoSService(app.state.device_service, app.state.network_ctx)
    app.state.hotspot_service = HotspotService(app.state.network_ctx, app.state.device_service)
    app.state.policy_service = PolicyService(app.state.qos_service)
    app.state.analytics_service = AnalyticsService()
    app.state.diagnostics_service = DiagnosticsService(
        app.state.network_ctx, app.state.connectivity_probe, app.state.device_service)
    app.state.settings_service = SettingsService()
    app.state.auth_service = AuthService()
    app.state.monitor_hub = MonitorHub()
    monitor = Monitor(
        hub=app.state.monitor_hub,
        interval_s=settings.monitor_interval_s,
        network_ctx=app.state.network_ctx,
        probe=app.state.connectivity_probe,
        persist_interval_s=settings.history_sample_interval_s,
        persist_enabled=True,
        device_service=app.state.device_service,
    )
    app.state.monitor = monitor
    try:
        init_db()
        log.info("database ready: %s", settings.database_url)
    except Exception:
        log.exception("database init failed; continuing with degraded DB state")
    await monitor.start()
    try:
        yield
    finally:
        await monitor.stop()
        log.info("shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(SmartQoSError)
    async def smartqos_error_handler(request: Request, exc: SmartQoSError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorResponse.ErrorDetail(code=exc.code, message=str(exc))
            ).model_dump(),
        )

    @app.middleware("http")
    async def require_auth(request: Request, call_next):
        auth = getattr(request.app.state, "auth_service", None)
        path = request.url.path
        if auth is not None and auth.has_password() and path.startswith("/api"):
            if path not in PUBLIC_API_PATHS and not path.startswith("/api/auth/"):
                token = request.cookies.get("sqm_session")
                if not auth.verify_session(token):
                    return JSONResponse(status_code=401, content={"ok": False, "error": {"code": "unauthorized", "message": "authentication required"}})
        return await call_next(request)

    app.include_router(health_api.router, prefix="/api")
    app.include_router(system_api.router, prefix="/api")
    app.include_router(network_api.router, prefix="/api")
    app.include_router(devices_api.router, prefix="/api")
    app.include_router(qos_api.router, prefix="/api")
    app.include_router(hotspot_api.router, prefix="/api")
    app.include_router(policies_api.router, prefix="/api")
    app.include_router(analytics_api.router, prefix="/api")
    app.include_router(diagnostics_api.router, prefix="/api")
    app.include_router(settings_api.router, prefix="/api")
    app.include_router(auth_api.router, prefix="/api")
    app.include_router(ws_api.router)

    @app.get("/api")
    def api_root() -> dict:
        return {"name": settings.app_name, "version": __version__, "ok": True}

    dist = Path(settings.frontend_dist)
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    else:
        @app.get("/")
        def root() -> dict:
            return {
                "name": settings.app_name, "version": __version__,
                "frontend": "run via Vite dev server (http://127.0.0.1:5173)",
                "api_docs": "/api/docs",
            }

    return app


app = create_app()
