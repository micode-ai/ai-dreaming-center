"""GET /p/{slug}/ — project dashboard."""
from __future__ import annotations
from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/p/{slug}/")
async def dashboard(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    pm = request.app.state.process_manager
    stats = await db.week_stats(project.id)
    sessions = await db.list_sessions(project.id, limit=20)
    pfx = f"{project.slug}:"
    active_keys = [k for k in pm.list_running().keys() if k.startswith(pfx)]
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request,
        "project_dashboard.html",
        {"project": project, "stats": stats,
         "sessions": [dict(s) for s in sessions],
         "active_keys": active_keys,
         "projects": projects, "locale": locale},
    )
