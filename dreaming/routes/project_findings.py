"""GET /p/{slug}/findings — flat tech-debt list + detail page + bulk close/delete."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.services import autoconfig


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
         "autoconfig_default": autoconfig.default_abs(project, "tech_debt_dir"),
         "error": error,
         "projects": projects, "locale": locale},
    )


@router.get("/p/{slug}/findings/{item_id}")
async def findings_detail(request: Request, slug: str, item_id: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    item = None
    body_md = ""
    item_dict: dict | None = None
    if td_dir and Path(td_dir).exists():
        try:
            from dreaming.services.tech_debt import read_tech_debt_item, read_td
            item = read_tech_debt_item(td_dir, item_id)
            if item is not None:
                item_dict = dict(item.__dict__) if hasattr(item, "__dict__") else (item if isinstance(item, dict) else None)
                # Pull body via read_td using the file_path from the parsed item.
                fp = item_dict.get("file_path") if item_dict else None
                if fp:
                    try:
                        _, body_md = read_td(fp)
                    except Exception:
                        body_md = ""
        except Exception:
            item = None
            item_dict = None
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_findings_detail.html",
        {"project": project, "item_id": item_id,
         "item": item_dict,
         "body_md": body_md, "td_dir": td_dir,
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/findings/{item_id}/close")
async def findings_close(request: Request, slug: str, item_id: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    if td_dir:
        from dreaming.services.tech_debt import close_tech_debt_item
        close_tech_debt_item(td_dir, item_id)
    return RedirectResponse(f"/p/{project.slug}/findings", status_code=303)


@router.post("/p/{slug}/findings/{item_id}/delete")
async def findings_delete(request: Request, slug: str, item_id: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    if td_dir:
        from dreaming.services.tech_debt import delete_tech_debt_item
        delete_tech_debt_item(td_dir, item_id)
    return RedirectResponse(f"/p/{project.slug}/findings", status_code=303)
