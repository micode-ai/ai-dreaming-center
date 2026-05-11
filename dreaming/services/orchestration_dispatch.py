"""Shared launcher for an orchestration run.

The Roman-spawning logic was originally inlined in
`POST /p/{slug}/orchestration/start` (orchestration_start_form). It's now
shared with the "Send to orchestration" buttons on Findings / Ideas pages,
so the spawn / watcher / tail bookkeeping lives here.
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from pathlib import Path

log = logging.getLogger(__name__)


class OrchestrationDispatchResult(dict):
    """{'run_id': str, 'started': bool, 'reason': str | None}"""


async def start_orchestration_run(
    app_state, project, goal: str, *, enforce_single: bool = True,
) -> OrchestrationDispatchResult:
    """Create a new orchestrator run + spawn Roman via PM. Best-effort: any
    optional pieces (ClaudeSessionTail, SubagentWatcher) that fail to spawn
    are logged and skipped — the run still proceeds.

    Returns a dict with `run_id` (always populated, even on failure) and
    `started` (True when claude actually launched).
    """
    hub = app_state.orchestration_hub
    pm = app_state.process_manager
    settings = app_state.settings
    db = app_state.db

    if enforce_single:
        existing = await hub.has_running_run(project.id)
        if existing:
            return OrchestrationDispatchResult({
                "run_id": existing, "started": False,
                "reason": "another orchestration run is already running",
            })

    claude_session_id = str(uuid.uuid4())
    run_id = await hub.create_run(project.id, goal.strip(), external_id=claude_session_id)
    root_node = await hub.create_node(
        run_id, project.id, agent_name="roman", role="orchestrator",
        external_id=claude_session_id,
    )
    await hub.append_event(
        run_id, "run_started",
        {"project_slug": project.slug, "goal": goal.strip()},
    )

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
        await hub.finish_run(run_id, status="failed", error_message=str(e))
        await hub.append_event(run_id, "run_failed", {"error": str(e)})
        log.warning("start_orchestration_run: spawn failed: %s", e)
        return OrchestrationDispatchResult({
            "run_id": run_id, "started": False, "reason": str(e),
        })

    claude_projects_dir = (
        getattr(settings, "claude_projects_dir", "")
        or str(Path.home() / ".claude" / "projects")
    )
    try:
        from dreaming.services.claude_session_tail import (
            ClaudeSessionTail, find_session_file_by_id,
        )
        jsonl_path = find_session_file_by_id(claude_session_id, claude_projects_dir)
        if jsonl_path:
            tail = ClaudeSessionTail(run_id, str(jsonl_path), hub, db)
            tasks = getattr(app_state, "orchestration_tails", None)
            if tasks is None:
                tasks = {}
                app_state.orchestration_tails = tasks
            tasks[run_id] = asyncio.create_task(
                tail.start(), name=f"orch-tail-{run_id[:8]}",
            )
        else:
            log.info(
                "start_orchestration_run: jsonl not yet visible for %s; "
                "backfill will recover", claude_session_id,
            )
    except Exception as e:
        log.warning("tail spawn failed: %s", e)

    try:
        from dreaming.services.subagent_watcher import SubagentWatcher
        watcher = SubagentWatcher(
            run_id, root_node, hub, db, claude_projects_dir=claude_projects_dir,
        )
        watchers = getattr(app_state, "orchestration_watchers", None)
        if watchers is None:
            watchers = {}
            app_state.orchestration_watchers = watchers
        watchers[run_id] = asyncio.create_task(
            watcher.start(), name=f"orch-watch-{run_id[:8]}",
        )
    except Exception as e:
        log.warning("watcher spawn failed: %s", e)

    return OrchestrationDispatchResult({
        "run_id": run_id, "started": True, "reason": None,
    })
