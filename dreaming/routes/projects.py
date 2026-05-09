"""Projects CRUD."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse

from dreaming.services.projects import ProjectsService


router = APIRouter()


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
