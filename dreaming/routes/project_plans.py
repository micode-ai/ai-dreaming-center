"""GET /p/{slug}/plans — Roman's plan files dashboard."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/p/{slug}/plans")
async def plans_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    obs_vault = await resolver.get(project, "obsidian_vault", "")
    default_dir = str(Path(obs_vault) / "03-Team" / "plans") if obs_vault else ""
    plans_dir = await resolver.get(project, "plans_dir", default_dir)
    items: list = []
    error: str | None = None
    if plans_dir and Path(plans_dir).exists():
        try:
            from dreaming.services.plans import list_plans
            raw = list_plans(plans_dir)
            items = [it.__dict__ for it in raw]
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_plans.html",
        {"project": project, "items": items, "plans_dir": plans_dir,
         "plans_dir_set": bool(plans_dir),
         "exists": bool(plans_dir) and Path(plans_dir).exists(),
         "error": error, "projects": projects, "locale": locale},
    )
