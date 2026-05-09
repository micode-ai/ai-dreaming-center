"""ai-dreaming-center FastAPI entry point."""
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from dreaming.config import settings as load_settings
from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService
from dreaming.services.config_resolver import ConfigResolver


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = load_settings()
    app.state.db = SqliteDB(app.state.settings.db_path)
    await app.state.db.connect()
    app.state.projects = ProjectsService(app.state.db)
    try:
        yield
    finally:
        await app.state.db.close()


app = FastAPI(title="AI Dreaming Center", lifespan=lifespan)


def get_resolver(request) -> ConfigResolver:
    """Per-request factory; fresh resolver per request — caches project_settings."""
    return ConfigResolver(request.app.state.projects, request.app.state.settings)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})
