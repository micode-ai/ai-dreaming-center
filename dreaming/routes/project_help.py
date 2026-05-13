"""GET /p/{slug}/help — per-project help / reference page."""
from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/p/{slug}/help")
async def project_help(request: Request, slug: str):
    project = request.state.project
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request,
        "project_help.html",
        {"project": project, "projects": projects, "locale": locale},
    )
