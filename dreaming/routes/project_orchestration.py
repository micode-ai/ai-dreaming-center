"""GET /p/{slug}/orchestration — list runs + per-run detail."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse


router = APIRouter()


@router.get("/p/{slug}/orchestration")
async def orchestration_list(request: Request, slug: str):
    project = request.state.project
    hub = request.app.state.orchestration_hub
    runs = await hub.list_runs(project.id, limit=50)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_orchestration_list.html",
        {"project": project, "runs": [dict(r) for r in runs],
         "projects": projects, "locale": locale},
    )


@router.get("/p/{slug}/orchestration/{run_id}")
async def orchestration_detail(request: Request, slug: str, run_id: str):
    project = request.state.project
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="run not found in this project")
    nodes = await hub.list_nodes(run_id)
    messages = await hub.list_messages(run_id)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_orchestration_detail.html",
        {"project": project, "run": dict(run),
         "nodes": [dict(n) for n in nodes],
         "messages": [dict(m) for m in messages],
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/orchestration/start")
async def orchestration_start_form(request: Request, slug: str, goal: str = Form(...)):
    """Form-based start. Redirects to the new run's detail page."""
    project = request.state.project
    hub = request.app.state.orchestration_hub
    if not goal.strip():
        raise HTTPException(status_code=400, detail="goal cannot be empty")
    existing = await hub.has_running_run(project.id)
    if existing:
        return RedirectResponse(
            f"/p/{project.slug}/orchestration/{existing}",
            status_code=303,
        )
    run_id = await hub.create_run(project.id, goal.strip())
    await hub.create_node(run_id, project.id, agent_name="roman", role="orchestrator")
    await hub.append_event(run_id, "run_started",
                           {"project_slug": project.slug, "goal": goal.strip()})
    return RedirectResponse(f"/p/{project.slug}/orchestration/{run_id}", status_code=303)


@router.post("/p/{slug}/orchestration/{run_id}/finish")
async def orchestration_finish_form(request: Request, slug: str, run_id: str):
    project = request.state.project
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404)
    await hub.finish_run(run_id, status="completed")
    await hub.append_event(run_id, "run_finished", {"status": "completed"})
    return RedirectResponse(f"/p/{project.slug}/orchestration", status_code=303)
