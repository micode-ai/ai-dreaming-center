"""GET /p/{slug}/ — project dashboard; POST stop/delete actions on sessions;
POST /p/{slug}/bootstrap-all — one-button starter-kit + autoconfig."""
from __future__ import annotations
from urllib.parse import urlparse
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from dreaming.services import autoconfig, starter_kit


router = APIRouter()


@router.get("/p/{slug}/")
async def dashboard(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    pm = request.app.state.process_manager
    stats = await db.week_stats(project.id)
    sessions = await db.list_sessions(project.id, limit=20)
    pfx = f"{project.slug}:"
    active_keys = [k for k in pm.list_running().keys() if k.startswith(pfx)]
    active_key_set = set(active_keys)

    # Bootstrap health: starter-kit + autoconfig
    kit_status = starter_kit.status(project.working_dir)
    overrides = await request.app.state.projects.all_settings(project.id)
    missing_dirs = [k for k in autoconfig.DEFAULTS if not (k in overrides and overrides[k])]
    bootstrap_needed = (not kit_status.all_present) or bool(missing_dirs)

    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request,
        "project_dashboard.html",
        {"project": project, "stats": stats,
         "sessions": [dict(s) for s in sessions],
         "active_keys": active_keys,
         "active_key_set": active_key_set,
         "kit_status": kit_status,
         "missing_dirs": missing_dirs,
         "bootstrap_needed": bootstrap_needed,
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/bootstrap-all")
async def bootstrap_all(request: Request, slug: str):
    """One-button: install full starter-kit + autoconfig every directory that
    doesn't already have an override. Idempotent: skip-if-exists everywhere."""
    project = request.state.project
    try:
        starter_kit.install(project.working_dir, force=False)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await autoconfig.apply_all_defaults(
        request.app.state.projects, project, skip_existing=True,
    )
    raw = request.headers.get("referer") or ""
    path = urlparse(raw).path if raw else ""
    if not path.startswith(f"/p/{project.slug}"):
        path = f"/p/{project.slug}/"
    return RedirectResponse(path, status_code=303)


async def _stop_one(request: Request, project, session_id: str) -> None:
    db = request.app.state.db
    pm = request.app.state.process_manager
    row = await db.fetch_one(
        "SELECT agent_name FROM agent_learning_sessions WHERE id=? AND project_id=?",
        (session_id, project.id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="session not found for this project")
    key = f"{project.slug}:{row['agent_name']}"
    if key in pm.list_running():
        await pm.kill(key)  # _cleanup() will mark the DB row
    else:
        await db.cancel_session(session_id)  # orphan: process is gone, just close the row


@router.post("/p/{slug}/sessions/{session_id}/stop")
async def session_stop(request: Request, slug: str, session_id: str):
    await _stop_one(request, request.state.project, session_id)
    return RedirectResponse(f"/p/{request.state.project.slug}/", status_code=303)


@router.post("/p/{slug}/sessions/{session_id}/delete")
async def session_delete(request: Request, slug: str, session_id: str):
    project = request.state.project
    db = request.app.state.db
    pm = request.app.state.process_manager
    row = await db.fetch_one(
        "SELECT agent_name FROM agent_learning_sessions WHERE id=? AND project_id=?",
        (session_id, project.id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="session not found for this project")
    key = f"{project.slug}:{row['agent_name']}"
    if key in pm.list_running():
        await pm.kill(key)  # never delete a row while its process is still alive
    await db.delete_session(session_id)
    return RedirectResponse(f"/p/{project.slug}/", status_code=303)


@router.post("/p/{slug}/sessions/force-close-stale")
async def sessions_force_close_stale(request: Request, slug: str):
    """Mark every 'running' row for this project as cancelled. For orphan cleanup."""
    project = request.state.project
    await request.app.state.db.cancel_stale_running(project.id)
    return RedirectResponse(f"/p/{project.slug}/", status_code=303)
