"""GET /p/{slug}/evolutions — list of agent _context/ overrides."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/p/{slug}/evolutions")
async def evolutions_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    # Default: {working_dir}/.claude/agents/_context/
    default_dir = str(Path(project.working_dir) / ".claude" / "agents" / "_context")
    evolutions_dir = await resolver.get(project, "evolutions_dir", "") or \
                     await resolver.get(project, "context_overrides_dir", "") or default_dir
    items: list = []
    error: str | None = None
    if Path(evolutions_dir).exists():
        try:
            from dreaming.services.evolutions import list_evolutions
            raw = list_evolutions(evolutions_dir)
            items = [it.__dict__ if hasattr(it, "__dict__") else it for it in raw]
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_evolutions.html",
        {"project": project, "items": items, "evolutions_dir": evolutions_dir,
         "exists": Path(evolutions_dir).exists(), "error": error,
         "projects": projects, "locale": locale},
    )
