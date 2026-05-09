"""ai-dreaming-center FastAPI entry point."""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from dreaming.config import settings as load_settings
from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService
from dreaming.services.config_resolver import ConfigResolver
from dreaming.services.i18n import I18n
from dreaming.middleware.setup_gate import setup_gate_middleware
from dreaming.middleware.project_resolver import project_resolver_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = load_settings()
    app.state.db = SqliteDB(app.state.settings.db_path)
    await app.state.db.connect()
    app.state.projects = ProjectsService(app.state.db)
    app.state.templates = Jinja2Templates(directory="dreaming/templates")
    app.state.i18n = I18n(Path("dreaming/i18n"))

    def _t(key: str, locale: str | None = None, **fmt) -> str:
        return app.state.i18n.t(key, locale=locale, **fmt)

    app.state.templates.env.filters["t"] = _t
    try:
        yield
    finally:
        await app.state.db.close()


app = FastAPI(title="AI Dreaming Center", lifespan=lifespan)


# Middleware order matters: Starlette runs registered-LAST FIRST on the way in.
# We want setup_gate as the OUTER (runs first; redirects to /setup when DB empty),
# and project_resolver as INNER (sets request.state.project for /p/{slug}/).
app.middleware("http")(project_resolver_middleware)
app.middleware("http")(setup_gate_middleware)


def get_resolver(request) -> ConfigResolver:
    """Per-request factory; fresh resolver per request — caches project_settings."""
    return ConfigResolver(request.app.state.projects, request.app.state.settings)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})
