"""Projects CRUD."""
from __future__ import annotations
import re

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse

from dreaming.services.projects import ProjectsService


router = APIRouter()


# Slug = lowercase letters, digits, hyphens; must start and end with alphanumeric.
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


@router.get("/projects")
async def projects_list(request: Request):
    projects = await request.app.state.projects.list_all()
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    return request.app.state.templates.TemplateResponse(
        request,
        "projects.html",
        {"projects": projects, "settings": request.app.state.settings, "locale": locale},
    )


@router.post("/projects/{project_id}/toggle")
async def projects_toggle(request: Request, project_id: int):
    p = await request.app.state.projects.get_by_id(project_id)
    if not p:
        raise HTTPException(404)
    new_enabled = not p.enabled
    await request.app.state.projects.update(project_id, enabled=new_enabled)
    refreshed = await request.app.state.projects.get_by_id(project_id)
    if refreshed:
        from dreaming.services.scheduler import register_project_jobs, unregister_project_jobs
        if new_enabled:
            await register_project_jobs(request.app.state.scheduler, request.app.state, refreshed)
        else:
            await unregister_project_jobs(request.app.state.scheduler, refreshed)
    return RedirectResponse("/projects", status_code=303)


@router.post("/projects/{project_id}/delete")
async def projects_delete(request: Request, project_id: int):
    p = await request.app.state.projects.get_by_id(project_id)
    if p:
        from dreaming.services.scheduler import unregister_project_jobs
        await unregister_project_jobs(request.app.state.scheduler, p)
    await request.app.state.projects.delete(project_id)
    return RedirectResponse("/projects", status_code=303)


@router.post("/projects/{project_id}/rename")
async def projects_rename(
    request: Request, project_id: int,
    slug: str | None = Form(default=None),
    label: str | None = Form(default=None),
):
    """Rename a project's label and/or slug.

    Slug rename is supported but rewires scheduler jobs (job IDs use slug)
    and breaks bookmarked /p/<old-slug>/... URLs — the template warns. Per-
    project settings and sessions are keyed on project_id so they survive
    unchanged."""
    svc = request.app.state.projects
    p = await svc.get_by_id(project_id)
    if not p:
        raise HTTPException(404)

    new_label = (label or "").strip() or None
    new_slug = (slug or "").strip().lower() or None
    updates: dict = {}

    if new_label is not None and new_label != p.label:
        updates["label"] = new_label

    slug_changed = new_slug is not None and new_slug != p.slug
    if slug_changed:
        if not _SLUG_RE.match(new_slug):
            raise HTTPException(
                400,
                detail=(
                    "Slug может содержать только латиницу (a-z), цифры и дефис, "
                    "начинаться и заканчиваться буквой/цифрой, длина 1–64."
                ),
            )
        # Check uniqueness — get_by_slug returns the OTHER project if collision.
        clash = await svc.get_by_slug(new_slug)
        if clash and clash.id != project_id:
            raise HTTPException(
                409,
                detail=f"Slug '{new_slug}' уже занят проектом id={clash.id}.",
            )
        updates["slug"] = new_slug

    if not updates:
        return RedirectResponse("/projects", status_code=303)

    # If we're touching slug, unregister old scheduler jobs first so the
    # renamed project doesn't leave orphans keyed by the old slug.
    from dreaming.services.scheduler import register_project_jobs, unregister_project_jobs
    if slug_changed and p.enabled:
        await unregister_project_jobs(request.app.state.scheduler, p)

    await svc.update(project_id, **updates)
    refreshed = await svc.get_by_id(project_id)

    if slug_changed and refreshed and refreshed.enabled:
        await register_project_jobs(
            request.app.state.scheduler, request.app.state, refreshed,
        )

    return RedirectResponse("/projects", status_code=303)


@router.post("/projects/import")
async def projects_import(request: Request, root: str = Form(...)):
    items_meta = ProjectsService.scan_projects_root(root)
    if not items_meta:
        return RedirectResponse("/projects", status_code=303)
    items = [
        {"slug": m["suggested_slug"], "label": m["suggested_label"],
         "working_dir": m["path"], "enabled": True}
        for m in items_meta
    ]
    created = await request.app.state.projects.import_from_scan(items)
    if created:
        from dreaming.services.scheduler import register_project_jobs
        for proj in created:
            await register_project_jobs(request.app.state.scheduler, request.app.state, proj)
    return RedirectResponse("/projects", status_code=303)
