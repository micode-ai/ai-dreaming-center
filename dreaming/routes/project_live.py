"""GET /p/{slug}/live — page; GET /p/{slug}/live/stream/{agent} — SSE; POST /p/{slug}/live/kill/{agent} — kill."""
from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from sse_starlette.sse import EventSourceResponse


router = APIRouter()


@router.get("/p/{slug}/live")
async def live_page(request: Request, slug: str):
    project = request.state.project
    pm = request.app.state.process_manager
    pfx = f"{project.slug}:"
    active_runs = [(k, k.split(":", 1)[1]) for k in pm.list_running().keys() if k.startswith(pfx)]
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_live.html",
        {"project": project, "active_runs": active_runs,
         "projects": projects, "locale": locale},
    )


@router.get("/p/{slug}/live/stream/{agent}")
async def live_stream(request: Request, slug: str, agent: str):
    project = request.state.project
    pm = request.app.state.process_manager
    key = f"{project.slug}:{agent}"
    if key not in pm.list_running():
        raise HTTPException(status_code=404, detail=f"no running session for {agent}")

    async def gen():
        sess = pm.list_running()[key]
        for line in sess.output_lines:
            yield {"event": "log", "data": line}
        async for line in pm.stream_subscriber(key):
            if line is None:
                yield {"event": "end", "data": ""}
                break
            yield {"event": "log", "data": line}

    return EventSourceResponse(gen())


@router.post("/p/{slug}/live/kill/{agent}")
async def live_kill(request: Request, slug: str, agent: str):
    project = request.state.project
    pm = request.app.state.process_manager
    key = f"{project.slug}:{agent}"
    await pm.kill(key)
    return RedirectResponse(f"/p/{project.slug}/live", status_code=303)
