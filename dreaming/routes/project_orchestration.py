"""GET /p/{slug}/orchestration — list runs + per-run detail."""
from __future__ import annotations
import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse


router = APIRouter()
log = logging.getLogger(__name__)


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
    """Form-based start: pre-creates run+root_node, spawns claude subprocess,
    starts ClaudeSessionTail + SubagentWatcher to populate the detail page live."""
    project = request.state.project
    hub = request.app.state.orchestration_hub
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    db = request.app.state.db

    if not goal.strip():
        raise HTTPException(status_code=400, detail="goal cannot be empty")

    existing = await hub.has_running_run(project.id)
    if existing:
        return RedirectResponse(
            f"/p/{project.slug}/orchestration/{existing}",
            status_code=303,
        )

    # Generate session_id up-front so it's both --session-id for claude AND
    # external_id on the orchestrator_run (used by backfill/resume).
    claude_session_id = str(uuid.uuid4())

    run_id = await hub.create_run(project.id, goal.strip(), external_id=claude_session_id)
    root_node = await hub.create_node(
        run_id, project.id, agent_name="roman", role="orchestrator",
        external_id=claude_session_id,
    )
    await hub.append_event(run_id, "run_started",
                           {"project_slug": project.slug, "goal": goal.strip()})

    # Spawn claude with the goal as prompt.
    try:
        await pm.start_command(
            project,
            command_name=f"roman-{run_id[:8]}",
            prompt=goal.strip(),
            claude_path=getattr(settings, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=getattr(settings, "model", "sonnet"),
            max_turns=getattr(settings, "max_turns", 50),
            timeout_minutes=getattr(settings, "timeout_minutes", 60),
            session_id=claude_session_id,
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
                "DREAMING_RUN_ID": run_id,
            },
        )
    except RuntimeError as e:
        # Spawn failed — mark run as failed but keep it for inspection.
        await hub.finish_run(run_id, status="failed", error_message=str(e))
        await hub.append_event(run_id, "run_failed", {"error": str(e)})
        log.warning("orchestration_start_form: claude spawn failed: %s", e)
        return RedirectResponse(f"/p/{project.slug}/orchestration/{run_id}", status_code=303)

    # Spawn watchers (best-effort; if they fail the run still continues, just
    # without auto-population — backfill recovers later).
    claude_projects_dir = (
        getattr(settings, "claude_projects_dir", "") or str(Path.home() / ".claude" / "projects")
    )
    try:
        from dreaming.services.claude_session_tail import ClaudeSessionTail, find_session_file_by_id
        # Locate the JSONL once it appears — claude creates it on first stdout.
        jsonl_path = find_session_file_by_id(claude_session_id, claude_projects_dir)
        if jsonl_path:
            tail = ClaudeSessionTail(run_id, str(jsonl_path), hub, db)
            tasks = getattr(request.app.state, "orchestration_tails", None)
            if tasks is None:
                tasks = {}
                request.app.state.orchestration_tails = tasks
            tasks[run_id] = asyncio.create_task(tail.start(), name=f"orch-tail-{run_id[:8]}")
        else:
            log.info(
                "orchestration_start_form: jsonl not yet visible for session %s; "
                "backfill will recover", claude_session_id,
            )
    except Exception as e:
        log.warning("orchestration_start_form: tail spawn failed: %s", e)

    try:
        from dreaming.services.subagent_watcher import SubagentWatcher
        watcher = SubagentWatcher(
            run_id, root_node, hub, db, claude_projects_dir=claude_projects_dir,
        )
        watchers = getattr(request.app.state, "orchestration_watchers", None)
        if watchers is None:
            watchers = {}
            request.app.state.orchestration_watchers = watchers
        watchers[run_id] = asyncio.create_task(watcher.start(), name=f"orch-watch-{run_id[:8]}")
    except Exception as e:
        log.warning("orchestration_start_form: watcher spawn failed: %s", e)

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
