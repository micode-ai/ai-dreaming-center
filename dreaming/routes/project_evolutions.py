"""GET /p/{slug}/evolutions — list of agent _context/ overrides.
GET /p/{slug}/evolutions/raw?path=X — raw text of a single evolution file.
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from dreaming.services import autoconfig


router = APIRouter()


async def _resolve_evolutions_dir(request, project) -> str:
    resolver = request.app.state.resolver_factory(request)
    default_dir = str(Path(project.working_dir) / ".claude" / "agents" / "_context")
    return (await resolver.get(project, "evolutions_dir", "")
            or await resolver.get(project, "context_overrides_dir", "")
            or default_dir)


@router.get("/p/{slug}/evolutions")
async def evolutions_page(request: Request, slug: str):
    project = request.state.project
    evolutions_dir = await _resolve_evolutions_dir(request, project)
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
         "autoconfig_default": autoconfig.default_abs(project, "evolutions_dir"),
         "projects": projects, "locale": locale},
    )


@router.get("/p/{slug}/evolutions/raw")
async def evolutions_raw(request: Request, slug: str, path: str):
    """Plain-text content of a single evolution markdown file. `path` is
    relative to evolutions_dir; path traversal is rejected."""
    project = request.state.project
    evolutions_dir = await _resolve_evolutions_dir(request, project)
    base = Path(evolutions_dir).resolve()
    if not base.exists():
        raise HTTPException(status_code=404, detail="evolutions_dir not found")
    target = (base / path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="path traversal blocked")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="evolution not found")
    try:
        return PlainTextResponse(target.read_text(encoding="utf-8"))
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"read failed: {e}")
