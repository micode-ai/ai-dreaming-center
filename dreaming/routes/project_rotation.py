"""GET /p/{slug}/rotation — agent roster + tier/enabled inline edit + Start button."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse

from dreaming.services.agents import list_agent_names


router = APIRouter()


@router.get("/p/{slug}/rotation")
async def rotation_page(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    fs_agents = list_agent_names(project.working_dir)
    db_rotation = await db.list_rotation(project.id)
    db_names = {r["agent_name"] for r in db_rotation}
    for name in fs_agents:
        if name not in db_names:
            await db.upsert_agent_rotation(project.id, name, tier=2)
    rotation = await db.list_rotation(project.id)
    pm = request.app.state.process_manager
    pfx = f"{project.slug}:"
    running_keys = {k for k in pm.list_running() if k.startswith(pfx)}
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_rotation.html",
        {"project": project, "rotation": [dict(r) for r in rotation],
         "running_keys": running_keys, "fs_count": len(fs_agents),
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/rotation/tier")
async def rotation_set_tier(request: Request, slug: str, agent_name: str = Form(...), tier: int = Form(...)):
    project = request.state.project
    if tier not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="tier must be 1|2|3")
    await request.app.state.db.set_agent_tier(project.id, agent_name, tier)
    return RedirectResponse(f"/p/{project.slug}/rotation", status_code=303)


@router.post("/p/{slug}/rotation/toggle")
async def rotation_toggle(request: Request, slug: str, agent_name: str = Form(...)):
    project = request.state.project
    db = request.app.state.db
    rows = await db.list_rotation(project.id)
    cur = next((r for r in rows if r["agent_name"] == agent_name), None)
    if cur is None:
        raise HTTPException(status_code=404)
    await db.set_agent_enabled(project.id, agent_name, not bool(cur["enabled"]))
    return RedirectResponse(f"/p/{project.slug}/rotation", status_code=303)


@router.post("/p/{slug}/rotation/start/{agent}")
async def rotation_start(request: Request, slug: str, agent: str):
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    try:
        await pm.start_session(
            project,
            agent_name=agent,
            claude_path=getattr(settings, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=getattr(settings, "model", "sonnet"),
            max_turns=getattr(settings, "max_turns", 25),
            timeout_minutes=getattr(settings, "timeout_minutes", 20),
            self_study_command=getattr(settings, "self_study_command", "/self-study"),
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return RedirectResponse(f"/p/{project.slug}/live", status_code=303)
