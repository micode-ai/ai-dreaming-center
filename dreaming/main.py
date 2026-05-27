"""ai-dreaming-center FastAPI entry point."""
from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dreaming.config import settings as load_settings
from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService
from dreaming.services.config_resolver import ConfigResolver
from dreaming.services.i18n import I18n
from dreaming.services.process_manager import ProcessManager
from dreaming.services.orchestration_hub import OrchestrationHub
from dreaming.services.harness_client import HarnessClientCache
from dreaming.services.scheduler import build_scheduler, register_project_jobs, unregister_project_jobs
from dreaming.middleware.setup_gate import setup_gate_middleware
from dreaming.middleware.project_resolver import project_resolver_middleware
from dreaming.routes.root import router as root_router
from dreaming.routes.setup import router as setup_router
from dreaming.routes.projects import router as projects_router
from dreaming.routes.settings import router as settings_router
from dreaming.routes.api import router as api_router
from dreaming.routes.ai_radar import router as ai_radar_router
from dreaming.routes.project_router import router as project_router

log = logging.getLogger(__name__)


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
    app.state.process_manager = ProcessManager(
        app.state.settings, app.state.db, app.state.projects)
    app.state.orchestration_hub = OrchestrationHub(app.state.db, app.state.projects)
    app.state.harness_clients = HarnessClientCache()
    app.state.scheduler = build_scheduler(app.state)
    app.state.scheduler.start()
    # Register per-project jobs for every enabled project
    for proj in await app.state.projects.list_all(only_enabled=True):
        await register_project_jobs(app.state.scheduler, app.state, proj)
    # One-time backfill of skill/agent breakdown for pre-existing history.
    # Runs in the background so startup isn't blocked; guarded so it only fires
    # while ai_skill_invocations is still empty. Idempotent if it re-fires.
    try:
        row = await app.state.db.fetch_one(
            "SELECT COUNT(*) AS c FROM ai_skill_invocations"
        )
        has_events = await app.state.db.fetch_one(
            "SELECT 1 FROM ai_usage_events LIMIT 1"
        )
        if row is not None and int(row["c"]) == 0 and has_events is not None:
            from dreaming.services.ai_usage_parser import backfill_skill_agent_stats
            # Keep a reference so the event loop doesn't GC the task mid-run.
            app.state.skill_backfill_task = asyncio.create_task(
                backfill_skill_agent_stats(app.state.db, app.state.projects)
            )
    except Exception as e:
        log.warning("skill/agent backfill kickoff failed: %s", e)
    app.state.resolver_factory = get_resolver
    try:
        yield
    finally:
        # Cleanup runs even on exception during the yield body.
        app.state.scheduler.shutdown(wait=False)
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


app.include_router(root_router)
app.include_router(setup_router)
app.include_router(projects_router)
app.include_router(settings_router)
app.include_router(api_router)
app.include_router(ai_radar_router)
app.include_router(project_router)
app.mount("/static", StaticFiles(directory="dreaming/static"), name="static")
