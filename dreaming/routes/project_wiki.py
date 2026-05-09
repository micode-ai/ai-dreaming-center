"""GET /p/{slug}/wiki — wiki bootstrap status (Wave 2 lean — Wave 4 adds full health)."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/p/{slug}/wiki")
async def wiki_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    wiki_dir = await resolver.get(project, "wiki_dir", "")
    status_info = None
    if wiki_dir:
        from dreaming.services.wiki_data import get_wiki_status
        status_info = get_wiki_status(wiki_dir)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_wiki.html",
        {"project": project, "wiki_dir": wiki_dir, "wiki_dir_set": bool(wiki_dir),
         "status": status_info,
         "projects": projects, "locale": locale},
    )
