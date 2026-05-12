"""GET /p/{slug}/sessions/{session_id}/log
GET /p/{slug}/orchestration/{run_id}/log

Both endpoints read the per-session stdout file that ProcessManager wrote
while the claude subprocess was running. File path:
    {settings.session_logs_dir}/{YYYY-MM-DD}/{session_id}.log

For orchestration runs the lookup key is `run.external_id` (= the claude
session_id passed via `--session-id`). For agent_learning_sessions
(self-study + cmd:*) the key is the row's `id`.
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request


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
                  run_id: str | None = None):
    settings = request.app.state.settings
    base = getattr(settings, "session_logs_dir", "data/session_logs")
    p = _find_log(base, session_id)
    body = ""
    if p is not None:
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            body = f"(error reading log: {e})"
    locale = request.cookies.get("dc_locale", settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "session_log.html",
        {"project": project, "session_id": session_id, "label": label,
         "log_path": str(p) if p else "", "body": body,
         "run_id": run_id, "projects": projects, "locale": locale},
    )


@router.get("/p/{slug}/sessions/{session_id}/log")
async def session_log(request: Request, slug: str, session_id: str):
    project = request.state.project
    db = request.app.state.db
    row = await db.fetch_one(
        "SELECT id, agent_name FROM agent_learning_sessions WHERE id=? AND project_id=?",
        (session_id, project.id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="session not found for this project")
    return await _render(request, project, session_id,
                         f"Session {row['agent_name'][:60]}")


@router.get("/p/{slug}/orchestration/{run_id}/log")
async def orchestration_log(request: Request, slug: str, run_id: str):
    project = request.state.project
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="run not found for this project")
    sid = run["external_id"] or run_id
    return await _render(request, project, sid,
                         f"Orchestration run {run_id[:8]}…", run_id=run_id)
