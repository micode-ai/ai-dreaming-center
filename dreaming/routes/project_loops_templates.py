"""Loop templates CRUD: per-project catalog of markdown templates with YAML frontmatter.

Directory resolved from project setting `loops_templates_dir`, falling back to
`<working_dir>/.claude/loops/templates`. Initial 16 templates are seeded by
autoconfig on project bootstrap; the user can add/edit/delete additional ones here.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.services import loop_templates as svc

router = APIRouter()
log = logging.getLogger(__name__)


def _resolve_dir(project, settings_overrides: dict) -> str:
    """Per-project templates dir, with fallback to .claude/loops/templates."""
    override = settings_overrides.get("loops_templates_dir")
    if override:
        return override
    if not project.working_dir:
        return ""
    return str(Path(project.working_dir) / ".claude" / "loops" / "templates")


@router.get("/p/{slug}/loops/templates")
async def project_loops_templates_list(request: Request, slug: str):
    project = request.state.project
    overrides = await request.app.state.projects.all_settings(project.id)
    templates_dir = _resolve_dir(project, overrides)
    items = svc.list_templates(templates_dir) if templates_dir else []
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_loops_templates.html",
        {
            "project": project,
            "items": items,
            "templates_dir": templates_dir or "",
            "templates_dir_exists": bool(templates_dir and Path(templates_dir).exists()),
            "projects": projects,
            "locale": locale,
        },
    )


@router.get("/p/{slug}/loops/templates/new")
async def project_loops_templates_new(request: Request, slug: str):
    project = request.state.project
    overrides = await request.app.state.projects.all_settings(project.id)
    templates_dir = _resolve_dir(project, overrides)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    blank = svc.LoopTemplate(slug="", name="")
    return request.app.state.templates.TemplateResponse(
        request, "project_loops_template_view.html",
        {
            "project": project,
            "tpl": blank,
            "is_new": True,
            "templates_dir": templates_dir,
            "projects": projects,
            "locale": locale,
        },
    )


@router.get("/p/{slug}/loops/templates/{tpl_slug}")
async def project_loops_templates_edit(request: Request, slug: str, tpl_slug: str):
    project = request.state.project
    overrides = await request.app.state.projects.all_settings(project.id)
    templates_dir = _resolve_dir(project, overrides)
    if not templates_dir:
        raise HTTPException(status_code=404, detail="loops_templates_dir not configured")
    tpl = svc.read_template(templates_dir, tpl_slug)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"template {tpl_slug} not found")
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_loops_template_view.html",
        {
            "project": project,
            "tpl": tpl,
            "is_new": False,
            "templates_dir": templates_dir,
            "projects": projects,
            "locale": locale,
        },
    )


@router.post("/p/{slug}/loops/templates")
async def project_loops_templates_save(
    request: Request, slug: str,
    tpl_slug: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    engine: str = Form("loop"),
    preset: str = Form(""),
    max_iterations: str = Form(""),
    tags: str = Form(""),
    team: str = Form("auto"),
    body: str = Form(""),
):
    project = request.state.project
    overrides = await request.app.state.projects.all_settings(project.id)
    templates_dir = _resolve_dir(project, overrides)
    if not templates_dir:
        raise HTTPException(status_code=400, detail="loops_templates_dir not configured")
    tpl_slug = tpl_slug.strip()
    if not tpl_slug:
        raise HTTPException(status_code=400, detail="slug is required")
    # Slug shape: a-z, 0-9, hyphen; starts/ends with letter or digit.
    import re
    if not re.fullmatch(r"[a-z0-9]([a-z0-9\-]*[a-z0-9])?", tpl_slug):
        raise HTTPException(status_code=400, detail="slug must match a-z0-9- (lowercase)")
    try:
        max_it = int(max_iterations) if max_iterations.strip() else None
    except ValueError:
        max_it = None
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tpl = svc.LoopTemplate(
        slug=tpl_slug, name=name.strip() or tpl_slug,
        description=description.strip(), engine=engine.strip() or "loop",
        preset=preset.strip(), max_iterations=max_it, tags=tag_list,
        team=team.strip() or "auto", body=body,
    )
    svc.write_template(templates_dir, tpl)
    return RedirectResponse(
        f"/p/{project.slug}/loops/templates/{tpl_slug}", status_code=303,
    )


@router.post("/p/{slug}/loops/templates/{tpl_slug}/delete")
async def project_loops_templates_delete(request: Request, slug: str, tpl_slug: str):
    project = request.state.project
    overrides = await request.app.state.projects.all_settings(project.id)
    templates_dir = _resolve_dir(project, overrides)
    if not templates_dir:
        raise HTTPException(status_code=400, detail="loops_templates_dir not configured")
    svc.delete_template(templates_dir, tpl_slug)
    return RedirectResponse(f"/p/{project.slug}/loops/templates", status_code=303)
