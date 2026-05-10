"""GET /p/{slug}/cascade-costs — per-run cost roll-up."""
from __future__ import annotations
from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/p/{slug}/cascade-costs")
async def cascade_costs_page(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    error: str | None = None
    rows: list = []
    try:
        from dreaming.services.cascade_costs import list_cascade_costs
        raw = await list_cascade_costs(db, project.id, limit=50)
        rows = [r.__dict__ for r in raw]
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    total_cost = sum(r["total_cost_usd"] for r in rows)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_cascade_costs.html",
        {"project": project, "rows": rows, "total_cost": total_cost, "error": error,
         "projects": projects, "locale": locale},
    )
