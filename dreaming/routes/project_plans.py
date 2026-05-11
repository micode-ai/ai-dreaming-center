"""GET /p/{slug}/plans — Roman's plan files dashboard.

POST /p/{slug}/plans/extract — run /plans-extract slash-command via Claude CLI.
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.services import autoconfig


router = APIRouter()


@router.post("/p/{slug}/plans/extract")
async def plans_extract(request: Request, slug: str):
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    try:
        await pm.start_command(
            project,
            command_name="plans-extract",
            prompt="/plans-extract",
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
         "autoconfig_default": autoconfig.default_abs(project, "plans_dir"),
         "error": error, "projects": projects, "locale": locale},
    )
