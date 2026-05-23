"""GET /p/{slug}/sessions/{session_id}/log
GET /p/{slug}/orchestration/{run_id}/log
GET /p/{slug}/sessions/{session_id}/log/tail?offset=N      (incremental polling)
GET /p/{slug}/orchestration/{run_id}/log/tail?offset=N

Both endpoints read the per-session stdout file that ProcessManager wrote
while the claude subprocess was running. File path:
    {settings.session_logs_dir}/{YYYY-MM-DD}/{session_id}.log

For orchestration runs the lookup key is `run.external_id` (= the claude
session_id passed via `--session-id`). For agent_learning_sessions
(self-study + cmd:*) the key is the row's `id`.

The /tail endpoints serve the JS auto-refresh on session_log.html — they
return the file slice starting at `offset` plus the new total size, so the
page can append-only without re-rendering the whole log.
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse


router = APIRouter()


def _find_log(base_dir: str, session_id: str) -> Path | None:
    if not session_id:
        return None
    base = Path(base_dir)
    if not base.exists():
        return None
    matches = list(base.rglob(f"{session_id}.log"))
    return matches[0] if matches else None


async def _render(request: Request, project, session_id: str, label: str,
                  run_id: str | None = None, tail_url: str | None = None,
                  is_live: bool = True):
    """Render the log page. `tail_url` is where the JS poller hits to
    incrementally append new bytes; `is_live` controls whether polling
    starts at all (set False once the run has terminated to save cycles)."""
    settings = request.app.state.settings
    base = getattr(settings, "session_logs_dir", "data/session_logs")
    p = _find_log(base, session_id)
    body = ""
    initial_size = 0
    if p is not None:
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
            initial_size = p.stat().st_size
        except OSError as e:
            body = f"(error reading log: {e})"
    locale = request.cookies.get("dc_locale", settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "session_log.html",
        {"project": project, "session_id": session_id, "label": label,
         "log_path": str(p) if p else "", "body": body,
         "run_id": run_id, "projects": projects, "locale": locale,
         "tail_url": tail_url, "is_live": is_live,
         "initial_size": initial_size},
    )


def _tail_response(base_dir: str, session_id: str, offset: int) -> JSONResponse:
    p = _find_log(base_dir, session_id)
    if p is None:
        return JSONResponse({"size": 0, "delta": "", "missing": True})
    try:
        size = p.stat().st_size
    except OSError:
        return JSONResponse({"size": 0, "delta": "", "missing": True})
    if offset > size:
        # Log was rotated/truncated — start over from the beginning.
        offset = 0
    delta = ""
    if size > offset:
        try:
            with p.open("rb") as f:
                f.seek(offset)
                delta = f.read(size - offset).decode("utf-8", errors="replace")
        except OSError as e:
            delta = f"(error reading log: {e})"
    return JSONResponse({"size": size, "delta": delta, "missing": False})


@router.get("/p/{slug}/sessions/{session_id}/log")
async def session_log(request: Request, slug: str, session_id: str):
    project = request.state.project
    db = request.app.state.db
    row = await db.fetch_one(
        "SELECT id, agent_name, status FROM agent_learning_sessions WHERE id=? AND project_id=?",
        (session_id, project.id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="session not found for this project")
    is_live = (row["status"] or "running") == "running"
    return await _render(
        request, project, session_id,
        f"Session {row['agent_name'][:60]}",
        tail_url=f"/p/{project.slug}/sessions/{session_id}/log/tail",
        is_live=is_live,
    )


@router.get("/p/{slug}/sessions/{session_id}/log/tail")
async def session_log_tail(request: Request, slug: str, session_id: str, offset: int = 0):
    project = request.state.project
    db = request.app.state.db
    row = await db.fetch_one(
        "SELECT id FROM agent_learning_sessions WHERE id=? AND project_id=?",
        (session_id, project.id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="session not found for this project")
    base = getattr(request.app.state.settings, "session_logs_dir", "data/session_logs")
    return _tail_response(base, session_id, offset)


@router.get("/p/{slug}/orchestration/{run_id}/log")
async def orchestration_log(request: Request, slug: str, run_id: str):
    project = request.state.project
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="run not found for this project")
    sid = run["external_id"] or run_id
    is_live = (run["status"] or "running") == "running"
    return await _render(
        request, project, sid,
        f"Orchestration run {run_id[:8]}…",
        run_id=run_id,
        tail_url=f"/p/{project.slug}/orchestration/{run_id}/log/tail",
        is_live=is_live,
    )


@router.get("/p/{slug}/orchestration/{run_id}/log/tail")
async def orchestration_log_tail(request: Request, slug: str, run_id: str, offset: int = 0):
    project = request.state.project
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="run not found for this project")
    sid = run["external_id"] or run_id
    base = getattr(request.app.state.settings, "session_logs_dir", "data/session_logs")
    return _tail_response(base, sid, offset)
