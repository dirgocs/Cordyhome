from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .adapters.base import Adapter, AdapterError
from .adapters.simulator import SimulatorAdapter
from .adapters.tuya.cloud import TuyaCloud
from .adapters.tuya.local import TuyaLocalAdapter
from .api import auth_routes, routes
from .api.deps import Services
from .auth import AuthService
from .clock import Clock
from .config import Config
from .db import Database
from .events import EventBus
from .services.demo import seed_demo
from .services.hub import DeviceNotFound, Hub
from .services.tuya_link import TuyaLinkService
from .settings import SettingsStore

log = logging.getLogger("cordyhome")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def build_services(
    config: Config,
    *,
    adapters: dict[str, Adapter] | None = None,
    clock: Clock | None = None,
    tuya_cloud: TuyaCloud | None = None,
) -> Services:
    db = Database(":memory:" if config.data_dir == Path(":memory:") else config.db_path)
    settings = SettingsStore(db)
    bus = EventBus()
    hub = Hub(
        db,
        settings,
        bus,
        adapters or {"tuya": TuyaLocalAdapter(), "simulator": SimulatorAdapter()},
        clock,
    )
    tuya = TuyaLinkService(db, settings, hub, tuya_cloud or TuyaCloud())
    hub.lan_rescan = tuya.rescan
    if config.demo:
        seed_demo(db, settings.get().timezone)
    return Services(
        config=config, db=db, settings=settings, bus=bus, auth=AuthService(db), hub=hub, tuya=tuya
    )


def create_app(
    config: Config | None = None, svc: Services | None = None, *, background: bool = True
) -> FastAPI:
    config = config or Config.from_env()
    svc = svc or build_services(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if background:
            await svc.hub.start()
        yield
        if background:
            await svc.hub.stop()
        else:
            svc.hub.meter.flush()

    app = FastAPI(
        title="Cordyhome", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.services = svc

    @app.middleware("http")
    async def same_origin_guard(request: Request, call_next):
        # Proteção CSRF: requisições que alteram estado precisam vir da própria interface.
        origin = request.headers.get("origin")
        host = request.headers.get("host")
        if request.method in UNSAFE_METHODS and origin and urlparse(origin).netloc != host:
            return JSONResponse({"detail": "Origem não permitida."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(AdapterError)
    async def adapter_error(_: Request, exc: AdapterError):
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.exception_handler(DeviceNotFound)
    async def not_found(_: Request, exc: DeviceNotFound):
        return JSONResponse({"detail": "Dispositivo não encontrado."}, status_code=404)

    @app.get("/api/health", include_in_schema=False)
    def health():
        return {"ok": True}

    app.include_router(auth_routes.router)
    app.include_router(routes.router)
    app.include_router(routes.ws_router)

    if config.web_dir is not None:
        _mount_spa(app, config.web_dir)
    return app


def _mount_spa(app: FastAPI, web_dir: Path) -> None:
    index = web_dir / "index.html"
    app.mount("/_app", StaticFiles(directory=web_dir / "_app"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Não encontrado."}, status_code=404)
        candidate = (web_dir / path).resolve()
        if path and candidate.is_file() and web_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
