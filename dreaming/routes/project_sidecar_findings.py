"""GET /p/{slug}/sidecar-findings — sidecar reviewer JSON reports list."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request

from dreaming.services import autoconfig


router = APIRouter()


@router.get("/p/{slug}/sidecar-findings")
async def sidecar_findings_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    obs_vault = await resolver.get(project, "obsidian_vault", "")
    default_dir = str(Path(obs_vault) / "03-Team" / "sidecar-findings") if obs_vault else ""
    sidecar_dir = await resolver.get(project, "sidecar_findings_dir", default_dir)
    items: list = []
    error: str | None = None
    if sidecar_dir and Path(sidecar_dir).exists():
        try:
            from dreaming.services.sidecar_findings import list_sidecar_findings
            raw = list_sidecar_findings(sidecar_dir)
            items = [it.__dict__ for it in raw]
        except Exception as e:
            error = f"{type(e).__name__}: {e}"

    # Filter UI
    severity = request.query_params.get("severity") or ""
    if severity:
        items = [it for it in items if it.get("severity") == severity]
    severities = sorted({it.get("severity", "") for it in items if it.get("severity")})

    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_sidecar_findings.html",
        {"project": project, "items": items, "sidecar_dir": sidecar_dir,
         "sidecar_dir_set": bool(sidecar_dir),
         "exists": bool(sidecar_dir) and Path(sidecar_dir).exists(),
         "autoconfig_default": autoconfig.default_abs(project, "sidecar_findings_dir"),
         "error": error, "severities": severities, "selected_severity": severity,
         "projects": projects, "locale": locale},
    )
