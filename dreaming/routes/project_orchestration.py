"""GET /p/{slug}/orchestration — list runs + per-run detail."""
from __future__ import annotations
import json
import logging

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse


router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/p/{slug}/orchestration")
async def orchestration_list(request: Request, slug: str, run_id: str | None = None):
    project = request.state.project
    hub = request.app.state.orchestration_hub
    pm = request.app.state.process_manager
    runs = await hub.list_runs(project.id, limit=50)
    # Mark each running row "stale" if no live claude process matches its
    # external_id — this is what the auto-reconcile checks too.
    # Both prefixes are recognised — `orchestrator-` for new runs,
    # `roman-` for runs created before the 2026-05-12 rename.
    live_session_ids = {
        getattr(sess, "session_id", "") or ""
        for key, sess in pm.list_running().items()
        if key.startswith(f"cmd:{slug}:orchestrator-")
        or key.startswith(f"cmd:{slug}:roman-")
    }
    def _ext(r):
        try:
            return r["external_id"] or ""
        except (IndexError, KeyError):
            return ""
    stale_running = sum(
        1 for r in runs
        if r["status"] == "running" and _ext(r) not in live_session_ids
    )

    # Optional inline detail — when ?run_id=... is set and the run belongs to
    # this project, load the swimlane data so the centre column can render it
    # without an extra page navigation.
    selected_run = None
    selected_nodes: list = []
    selected_messages: list = []
    selected_stages: list = []
    nodes_by_stage: dict[str, list] = {}
    skills_by_node: dict[str, list] = {}
    if run_id:
        run_row = await hub.get_run(run_id)
        if run_row is not None and run_row["project_id"] == project.id:
            selected_run = dict(run_row)
            selected_nodes = [dict(n) for n in await hub.list_nodes(run_id)]
            selected_messages = [dict(m) for m in await hub.list_messages(run_id)]
            selected_stages = [dict(s) for s in await hub.list_stages(run_id)]
            for n in selected_nodes:
                key = n.get("stage_id") or "_unassigned"
                nodes_by_stage.setdefault(key, []).append(n)
            # Skills each node invoked → swimlane chip badges.
            for sk in await request.app.state.db.list_node_skills_for_run(run_id):
                skills_by_node.setdefault(sk["node_id"], []).append(sk["skill_name"])

    from dreaming.services.bulk_orchestration import get_queue
    _bq = get_queue(request.app.state, project.id)
    bulk_queue_snap = _bq.snapshot()
    bulk_diag = _bq.diag()
    bulk_pending = sum(1 for it in bulk_queue_snap if it["status"] == "pending")
    bulk_failed = sum(1 for it in bulk_queue_snap if it["status"] == "failed")
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_orchestration_list.html",
        {
            "project": project, "runs": [dict(r) for r in runs],
            "stale_running": stale_running,
            "selected_run": selected_run,
            "selected_run_id": run_id,
            "selected_nodes": selected_nodes,
            "selected_messages": selected_messages,
            "selected_stages": selected_stages,
            "nodes_by_stage": nodes_by_stage,
            "skills_by_node": skills_by_node,
            "bulk_queue": bulk_queue_snap,
            "bulk_diag": bulk_diag,
            "bulk_pending": bulk_pending,
            "bulk_failed": bulk_failed,
            "projects": projects, "locale": locale,
        },
    )


@router.post("/p/{slug}/orchestration/force-close-stale")
async def orchestration_force_close_stale(request: Request, slug: str):
    """Force-close every running orchestration run for this project — used to
    clear orphans that the auto-reconcile hasn't gotten to yet."""
    project = request.state.project
    await request.app.state.db.cancel_stale_orchestration_runs_for_project(project.id)
    return RedirectResponse(f"/p/{project.slug}/orchestration", status_code=303)


@router.post("/p/{slug}/orchestration/{run_id}/delete")
async def orchestration_delete(request: Request, slug: str, run_id: str):
    """Hard-delete a run plus its child rows (messages, nodes, events,
    questions). If the run is still in `pm.running`, kill the claude process
    first so we don't leave a runaway."""
    project = request.state.project
    db = request.app.state.db
    pm = request.app.state.process_manager
    # If the spawn-side cmd key is still alive, kill its process first so we
    # don't leave a runaway. Both initial run and resume use stable key names.
    # `roman-` is the pre-rename prefix, kept for backwards compatibility.
    for cmd_key in (
        f"cmd:{project.slug}:orchestrator-{run_id[:8]}",
        f"cmd:{project.slug}:roman-{run_id[:8]}",
        f"cmd:{project.slug}:resume-{run_id[:8]}",
    ):
        if cmd_key in pm.list_running():
            try:
                await pm.kill(cmd_key)
            except Exception:
                pass
    await db.delete_orchestration_run(run_id, project.id)
    return RedirectResponse(f"/p/{project.slug}/orchestration", status_code=303)


@router.get("/p/{slug}/orchestration/{run_id}")
async def orchestration_detail(request: Request, slug: str, run_id: str):
    """Compatibility redirect: the run detail lives inline in the list view now.
    Old bookmarks and links continue to work via this 303."""
    project = request.state.project
    return RedirectResponse(
        f"/p/{project.slug}/orchestration?run_id={run_id}", status_code=303,
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
    # Finalize any still-running stages and nodes so the swimlane reflects
    # reality. Done BEFORE finish_run so events are written in sensible order.
    for s in await hub.list_stages(run_id):
        if s["status"] == "running":
            await hub.finish_stage(s["id"], "completed")
    for n in await hub.list_nodes(run_id):
        if n["status"] == "running":
            await hub.update_node_status(n["id"], "completed")
    await hub.finish_run(run_id, status="completed")
    await hub.append_event(run_id, "run_finished", {"status": "completed"})
    from dreaming.services.orchestration_dispatch import kill_run_processes
    await kill_run_processes(request.app.state, run_id)
    # Backfill any messages/subagents the live tail missed (race on jsonl
    # creation, mid-run reload, etc.). Idempotent via client_message_id dedup.
    try:
        from dreaming.services.subagent_backfill import backfill_run
        added = await backfill_run(
            run_id,
            request.app.state.db,
            hub,
            claude_projects_dir=getattr(
                request.app.state.settings, "claude_projects_dir", None,
            ) or None,
        )
        if added:
            log.info("orchestration_finish_form: backfilled %s messages", added)
    except Exception as e:
        log.warning("orchestration_finish_form: backfill failed: %s", e)
    return RedirectResponse(f"/p/{project.slug}/orchestration?run_id={run_id}", status_code=303)


@router.post("/p/{slug}/orchestration/{run_id}/backfill")
async def orchestration_backfill(request: Request, slug: str, run_id: str):
    """Replay the claude jsonl for this run into orchestrator_messages /
    orchestrator_nodes. Recovers runs whose live tail missed events (e.g.,
    the dispatcher hit the jsonl-creation race before the fix landed, or the
    server was reloaded mid-run). Idempotent — repeat calls dedup via
    client_message_id."""
    project = request.state.project
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404)
    from dreaming.services.subagent_backfill import backfill_run
    added = await backfill_run(
        run_id,
        request.app.state.db,
        hub,
        claude_projects_dir=getattr(
            request.app.state.settings, "claude_projects_dir", None,
        ) or None,
    )
    log.info("orchestration_backfill: run=%s added=%s", run_id, added)
    return RedirectResponse(f"/p/{project.slug}/orchestration?run_id={run_id}", status_code=303)


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


@router.get("/p/{slug}/orchestration/{run_id}/stream")
async def orchestration_stream(request: Request, slug: str, run_id: str):
    """SSE live-tail of orchestration events. Yields:
      - one `snapshot` event with full {run, stages, nodes, messages}
      - one event per `orchestrator_events` row as it appears
      - a final `done` event when the run terminates
    Client should fall back to polling `/refresh` on EventSource error.
    """
    project = request.state.project
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="run not found in this project")

    async def event_generator():
        async for ev in hub.stream_run_events(run_id):
            # sse_starlette expects {"event", "data"} with `data` already a string.
            yield {
                "event": ev["event"],
                "data": json.dumps(ev["data"], ensure_ascii=False, default=str),
            }
            if await request.is_disconnected():
                break

    return EventSourceResponse(event_generator())


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
            max_turns=getattr(settings, "orchestration_max_turns", 150),
            timeout_minutes=getattr(settings, "orchestration_timeout_minutes", 120),
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
