"""GET /p/{slug}/ideas — product ideas board (read-only flat list, Wave 2 lean)."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/p/{slug}/ideas")
async def ideas_page(request: Request, slug: str, status: str | None = None):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    ideas_dir = await resolver.get(project, "product_ideas_dir", "")
    items = []
    error = None
    statuses: list[str] = []
    if ideas_dir and Path(ideas_dir).exists():
        try:
            from dreaming.services.product_ideas import list_product_ideas
            raw = list_product_ideas(ideas_dir)
            for it in raw:
                if hasattr(it, "__dict__"):
                    items.append(dict(it.__dict__))
                elif isinstance(it, dict):
                    items.append(it)
                else:
                    items.append({"raw": str(it)})
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        # Build status filter list
        statuses = sorted({(it.get("status") or "unknown") for it in items if isinstance(it, dict)})
    # Apply status filter
    if status:
        items = [it for it in items if (it.get("status") if isinstance(it, dict) else None) == status]
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_ideas.html",
        {"project": project, "items": items, "ideas_dir": ideas_dir,
         "ideas_dir_set": bool(ideas_dir),
         "ideas_dir_exists": bool(ideas_dir) and Path(ideas_dir).exists(),
         "error": error, "statuses": statuses, "selected_status": status or "",
         "projects": projects, "locale": locale},
    )
