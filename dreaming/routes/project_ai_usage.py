"""GET /p/{slug}/ai-usage — per-project token/cost analytics."""
from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/p/{slug}/ai-usage")
async def project_ai_usage(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    from dreaming.services.ai_usage_stats import project_summary
    try:
        summary = await project_summary(db, project.id)
    except Exception as e:
        summary = {"error": f"{type(e).__name__}: {e}"}
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request,
        "project_ai_usage.html",
        {
            "project": project,
            "summary": summary,
            "projects": projects,
            "locale": locale,
        },
    )
