"""GET /p/{slug}/loops — reflex-loop dashboard."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/p/{slug}/loops")
async def loops_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    obs_vault = await resolver.get(project, "obsidian_vault", "")
    default_dir = str(Path(obs_vault) / "03-Team" / "loops") if obs_vault else ""
    loops_dir = await resolver.get(project, "loops_dir", default_dir)
    items: list = []
    error: str | None = None
    if loops_dir and Path(loops_dir).exists():
        try:
            from dreaming.services.loops import list_loops
            raw = list_loops(loops_dir)
            items = [it.__dict__ for it in raw]
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_loops.html",
        {"project": project, "items": items, "loops_dir": loops_dir,
         "loops_dir_set": bool(loops_dir),
         "exists": bool(loops_dir) and Path(loops_dir).exists(),
         "error": error, "projects": projects, "locale": locale},
    )
