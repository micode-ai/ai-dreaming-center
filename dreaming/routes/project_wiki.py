"""GET /p/{slug}/wiki — wiki bootstrap status (Wave 2 lean — Wave 4 adds full health).

POST /p/{slug}/wiki/bootstrap — run /wiki-bootstrap via Claude CLI for the project.
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.services import autoconfig


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
         "autoconfig_default": autoconfig.default_abs(project, "wiki_dir"),
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/wiki/bootstrap")
async def wiki_bootstrap_run(request: Request, slug: str):
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    try:
        await pm.start_command(
            project,
            command_name="wiki-bootstrap",
            prompt="/wiki-bootstrap",
            claude_path=getattr(settings, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=getattr(settings, "model", "sonnet"),
            max_turns=getattr(settings, "max_turns", 50),
            timeout_minutes=getattr(settings, "timeout_minutes", 60),
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return RedirectResponse(f"/p/{project.slug}/live", status_code=303)
