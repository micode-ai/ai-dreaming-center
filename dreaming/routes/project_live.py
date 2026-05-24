"""GET /p/{slug}/live — page; GET /p/{slug}/live/stream/{agent} — SSE; POST /p/{slug}/live/kill/{agent} — kill.

Handles both kinds of keys:
- Self-study sessions:  `{slug}:{agent_name}`
- Command sessions:     `cmd:{slug}:{command_name}` (wiki-bootstrap, tech-debt-scan, ...)
URL paths only carry the trailing component (agent_name or command_name); the
handler resolves which kind by probing both forms.
"""
from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from sse_starlette.sse import EventSourceResponse


router = APIRouter()


def _collect_runs_for_project(pm, slug: str) -> list[tuple[str, str, bool]]:
    """Return [(full_key, display_name, is_cmd)] for both self-study + cmd sessions
    belonging to the given project.

    Skips sessions whose child process has already exited — those are zombies
    waiting for _cleanup to finish (or stuck holding a pipe); rendering them on
    /live just leaves a "live"-pulsing card with no incoming stream.
    """
    slug_prefix = f"{slug}:"
    cmd_prefix = f"cmd:{slug}:"
    runs: list[tuple[str, str, bool]] = []
    for k, sess in pm.list_running().items():
        if sess.process.returncode is not None:
            continue
        if k.startswith(cmd_prefix):
            runs.append((k, k[len(cmd_prefix):], True))
        elif k.startswith(slug_prefix):
            runs.append((k, k[len(slug_prefix):], False))
    return runs


def _resolve_key(pm, slug: str, agent_or_cmd: str) -> str | None:
    """Resolve a URL path component to the actual pm.running key."""
    plain = f"{slug}:{agent_or_cmd}"
    cmd = f"cmd:{slug}:{agent_or_cmd}"
    running = pm.list_running()
    if plain in running:
        return plain
    if cmd in running:
        return cmd
    return None


@router.get("/p/{slug}/live")
async def live_page(request: Request, slug: str):
    project = request.state.project
    pm = request.app.state.process_manager
    active_runs = _collect_runs_for_project(pm, project.slug)
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
    key = _resolve_key(pm, project.slug, agent)
    if key is None:
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
    key = _resolve_key(pm, project.slug, agent)
    if key is not None:
        await pm.kill(key)
    return RedirectResponse(f"/p/{project.slug}/live", status_code=303)
