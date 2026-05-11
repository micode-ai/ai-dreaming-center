"""GET /p/{slug}/contracts — module/page contracts list."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request

from dreaming.services import autoconfig


router = APIRouter()


@router.get("/p/{slug}/contracts")
async def contracts_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    obs_vault = await resolver.get(project, "obsidian_vault", "")
    default_dir = str(Path(obs_vault) / "03-Team" / "specs" / "contracts") if obs_vault else ""
    contracts_dir = await resolver.get(project, "contracts_dir", default_dir)
    items: list = []
    error: str | None = None
    if contracts_dir and Path(contracts_dir).exists():
        try:
            from dreaming.services.contracts import list_contracts
            raw = list_contracts(contracts_dir)
            items = [it.__dict__ for it in raw]
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_contracts.html",
        {"project": project, "items": items, "contracts_dir": contracts_dir,
         "contracts_dir_set": bool(contracts_dir),
         "exists": bool(contracts_dir) and Path(contracts_dir).exists(),
         "autoconfig_default": autoconfig.default_abs(project, "contracts_dir"),
         "error": error, "projects": projects, "locale": locale},
    )
