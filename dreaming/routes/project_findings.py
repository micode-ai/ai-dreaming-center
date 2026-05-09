"""GET /p/{slug}/findings — flat tech-debt list (Wave 2 lean: no bulk actions, no detail page)."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request


router = APIRouter()


def _default_td_dir(project) -> str:
    # Default fallback: project's own .claude/agents/findings or empty
    return ""


@router.get("/p/{slug}/findings")
async def findings_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", _default_td_dir(project))
    items = []
    error = None
    if td_dir and Path(td_dir).exists():
        try:
            from dreaming.services.tech_debt import list_tech_debt
            raw = list_tech_debt(td_dir)
            # Normalize to list of dicts so template doesn't depend on dataclass
            items = []
            for it in raw:
                if hasattr(it, "__dict__"):
                    items.append(dict(it.__dict__))
                elif isinstance(it, dict):
                    items.append(it)
                else:
                    items.append({"raw": str(it)})
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_findings.html",
        {"project": project, "items": items, "td_dir": td_dir,
         "td_dir_set": bool(td_dir), "td_dir_exists": bool(td_dir) and Path(td_dir).exists(),
         "error": error,
         "projects": projects, "locale": locale},
    )
