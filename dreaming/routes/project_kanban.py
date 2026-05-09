"""GET/POST /p/{slug}/kanban — custom topics CRUD."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse


router = APIRouter()


@router.get("/p/{slug}/kanban")
async def kanban_page(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    topics = await db.list_custom_topics(project.id, active_only=False)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_kanban.html",
        {"project": project, "topics": [dict(t) for t in topics],
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/kanban/add")
async def kanban_add(
    request: Request, slug: str,
    title: str = Form(...), module: str = Form(""),
    target_agents: str = Form(""), question: str = Form(""),
    why_important: str = Form(""),
):
    project = request.state.project
    if not title.strip():
        raise HTTPException(status_code=400, detail="title required")
    await request.app.state.db.add_custom_topic(
        project.id, title.strip(), module.strip(),
        target_agents.strip(), question.strip(), why_important.strip(),
    )
    return RedirectResponse(f"/p/{project.slug}/kanban", status_code=303)


@router.post("/p/{slug}/kanban/{topic_id}/delete")
async def kanban_delete(request: Request, slug: str, topic_id: str):
    project = request.state.project
    await request.app.state.db.delete_custom_topic(project.id, topic_id)
    return RedirectResponse(f"/p/{project.slug}/kanban", status_code=303)
