"""GET /p/{slug}/tech-debt — minimal aggregate dashboard (Wave 2 lean)."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/p/{slug}/tech-debt")
async def tech_debt_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    by_status: dict[str, int] = {}
    by_module: dict[str, int] = {}
    total = 0
    error = None
    if td_dir and Path(td_dir).exists():
        try:
            from dreaming.services.tech_debt import list_tech_debt
            items = list_tech_debt(td_dir)
            total = len(items)
            for it in items:
                obj = it.__dict__ if hasattr(it, "__dict__") else (it if isinstance(it, dict) else {})
                by_status[obj.get("status") or "unknown"] = by_status.get(obj.get("status") or "unknown", 0) + 1
                by_module[obj.get("module") or "—"] = by_module.get(obj.get("module") or "—", 0) + 1
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_tech_debt.html",
        {"project": project, "total": total,
         "by_status": sorted(by_status.items(), key=lambda kv: -kv[1]),
         "by_module": sorted(by_module.items(), key=lambda kv: -kv[1])[:10],
         "td_dir": td_dir, "td_dir_set": bool(td_dir),
         "td_dir_exists": bool(td_dir) and Path(td_dir).exists(),
         "error": error,
         "projects": projects, "locale": locale},
    )
