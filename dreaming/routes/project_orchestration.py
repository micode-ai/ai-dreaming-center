"""GET /p/{slug}/orchestration — list runs + per-run detail."""
from __future__ import annotations
import logging

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse


router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/p/{slug}/orchestration")
async def orchestration_list(request: Request, slug: str):
    project = request.state.project
    hub = request.app.state.orchestration_hub
    pm = request.app.state.process_manager
    runs = await hub.list_runs(project.id, limit=50)
    # Mark each running row "stale" if no live claude process matches its
    # external_id — this is what the auto-reconcile checks too.
    live_session_ids = {
        getattr(sess, "session_id", "") or ""
        for key, sess in pm.list_running().items()
        if key.startswith(f"cmd:{slug}:roman-")
    }
    stale_running = sum(
        1 for r in runs
        if r["status"] == "running" and (r.get("external_id") or "") not in live_session_ids
    )
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_orchestration_list.html",
        {"project": project, "runs": [dict(r) for r in runs],
         "stale_running": stale_running,
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/orchestration/force-close-stale")
async def orchestration_force_close_stale(request: Request, slug: str):
    """Force-close every running orchestration run for this project — used to
    clear orphans that the auto-reconcile hasn't gotten to yet."""
    project = request.state.project
    await request.app.state.db.cancel_stale_orchestration_runs_for_project(project.id)
    return RedirectResponse(f"/p/{project.slug}/orchestration", status_code=303)


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
    """Form-based start: pre-creates run+root_node, spawns claude subprocess,
    starts ClaudeSessionTail + SubagentWatcher to populate the detail page live."""
    project = request.state.project
    if not goal.strip():
        raise HTTPException(status_code=400, detail="goal cannot be empty")
    from dreaming.services.orchestration_dispatch import start_orchestration_run
    result = await start_orchestration_run(request.app.state, project, goal)
    return RedirectResponse(
        f"/p/{project.slug}/orchestration/{result['run_id']}", status_code=303,
    )


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


@router.get("/p/{slug}/orchestration/{run_id}/refresh")
async def orchestration_refresh(request: Request, slug: str, run_id: str):
    """Lightweight JSON for polling — returns counts + latest items."""
    project = request.state.project
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404)
    nodes = await hub.list_nodes(run_id)
    messages = await hub.list_messages(run_id)
    return JSONResponse({
        "status": run["status"],
        "finished_at": run["finished_at"],
        "node_count": len(nodes),
        "message_count": len(messages),
        "nodes": [
            {"id": n["id"], "agent_name": n["agent_name"],
             "status": n["status"], "role": n["role"]}
            for n in nodes
        ],
        "messages": [
            {"id": m["id"], "ts": m["ts"], "author": m["author"],
             "kind": m["kind"], "text": m["text"]}
            for m in messages[-100:]
        ],
    })


@router.post("/p/{slug}/orchestration/{run_id}/resume")
async def orchestration_resume(
    request: Request, slug: str, run_id: str, prompt: str = Form(""),
):
    """Resume a finished run — spawns claude --resume <session_id> with new prompt."""
    project = request.state.project
    hub = request.app.state.orchestration_hub
    pm = request.app.state.process_manager
    settings = request.app.state.settings

    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404)
    if not run["external_id"]:
        raise HTTPException(status_code=400, detail="run has no claude_session_id; cannot resume")

    # Reactivate the run.
    await request.app.state.db.execute(
        "UPDATE orchestrator_runs SET status='running', finished_at=NULL, error_message=NULL "
        "WHERE id=?",
        (run_id,),
    )
    await hub.append_event(run_id, "run_resumed", {"prompt": prompt})

    try:
        await pm.start_command(
            project,
            command_name=f"resume-{run_id[:8]}",
            prompt=(prompt.strip() or "продолжай"),
            claude_path=getattr(settings, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=getattr(settings, "model", "sonnet"),
            max_turns=getattr(settings, "max_turns", 50),
            timeout_minutes=getattr(settings, "timeout_minutes", 60),
            resume_session_id=run["external_id"],
            interactive_stdin=True,
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
                "DREAMING_RUN_ID": run_id,
            },
        )
    except RuntimeError as e:
        await hub.finish_run(run_id, status="failed", error_message=str(e))
        await hub.append_event(run_id, "run_resume_failed", {"error": str(e)})
        raise HTTPException(status_code=409, detail=str(e))

    return RedirectResponse(f"/p/{project.slug}/orchestration/{run_id}", status_code=303)
