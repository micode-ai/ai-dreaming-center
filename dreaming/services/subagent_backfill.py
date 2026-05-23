"""Backfill orchestrator nodes/messages for a run from on-disk Claude jsonl files.

Scenario: a run was created (we know its external_id, which equals Claude's
session UUID) but the orchestration tables are empty for it — either the run
predates the watcher or the watcher was offline. This module scans:

    1. The main session jsonl `<external_id>.jsonl` (replayed into the
       orchestrator node, creating one if needed).
    2. Any subagents at `<external_id>/subagents/agent-*.jsonl` plus their
       sibling `*.meta.json` (each replayed into a worker node).

Idempotent by Claude's per-line `uuid` — repeated invocations don't double-write
within a single call since `_ingest_line` dedupes against the `seen` set, but
DB-level dedup is not enforced (the orchestrator_messages table has no UNIQUE
on the source uuid). Running backfill twice on the same run produces duplicate
rows; callers that re-run should clear messages for the run first or use the
smoke-harness pattern of recreating the DB.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from dreaming.services import claude_session_tail as session_tail
from dreaming.services.claude_session_tail import _ingest_line
from dreaming.services.db import SqliteDB
from dreaming.services.orchestration_hub import OrchestrationHub
from dreaming.services.subagent_watcher import _resolve_node_for_subagent

log = logging.getLogger(__name__)


async def _ensure_main_node(
    hub: OrchestrationHub,
    run_id: str,
    project_id: int,
    fallback_name: str,
) -> str:
    """Return the orchestrator node id for `run_id`, creating one if absent."""
    nodes = await hub.list_nodes(run_id)
    for n in nodes:
        try:
            role = n["role"]
        except (KeyError, TypeError):
            role = None
        if (role or "").lower() == "orchestrator":
            return n["id"]
    return await hub.create_node(
        run_id, project_id, agent_name=fallback_name, role="orchestrator",
    )


async def _load_seen_uuids(db: SqliteDB, run_id: str) -> set[str]:
    """Pre-fill `seen` with client_message_ids already in DB for this run, so
    re-running backfill doesn't duplicate rows previously written by the live
    tail or a prior backfill. Pre-2026-05-21 messages may have NULL — those
    won't dedup, but they also won't drive new dups (the jsonl uuid would have
    no match in `seen` and we'd re-insert; this is the known limitation called
    out in the module docstring)."""
    rows = await db.fetch_all(
        "SELECT client_message_id FROM orchestrator_messages "
        "WHERE run_id=? AND client_message_id IS NOT NULL",
        (run_id,),
    )
    seen: set[str] = set()
    for r in rows:
        try:
            cmid = r["client_message_id"]
        except (KeyError, IndexError, TypeError):
            cmid = None
        if cmid:
            seen.add(cmid)
    return seen


async def _replay_jsonl(
    hub: OrchestrationHub,
    db: SqliteDB,
    run_id: str,
    node_id: str,
    project_id: int,
    path: Path,
    seen: set[str] | None = None,
) -> int:
    """Replay every line of `path` through `_ingest_line`. Returns the count of
    appended messages. Pass a shared `seen` set across files for one run so the
    main session and subagent jsonls don't redundantly re-ingest each other's
    UUIDs (subagent jsonl may share uuids with the parent in tool_use/result
    chains)."""
    appended = 0
    if seen is None:
        seen = set()
    with path.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            appended += await _ingest_line(
                hub, db, run_id, node_id, project_id, line, seen,
            )
    return appended


async def backfill_run(
    run_id: str,
    db: SqliteDB,
    hub: OrchestrationHub,
    claude_projects_dir: str | None = None,
) -> int:
    """Replay all jsonl files belonging to `run_id` into the orchestration tables.

    Returns the total number of messages appended (main session + subagents).
    Returns 0 if no jsonl can be located for the run.
    """
    run = await hub.get_run(run_id)
    if run is None:
        log.warning("backfill_run: run %s not found", run_id)
        return 0
    project_id = run["project_id"]
    external_id = run["external_id"]
    if not external_id:
        log.warning("backfill_run: run %s has no external_id, nothing to find", run_id)
        return 0

    main_jsonl = session_tail.find_session_file_by_id(
        external_id, claude_projects_dir=claude_projects_dir,
    )
    if main_jsonl is None:
        log.warning(
            "backfill_run: no jsonl for session_id=%s under %s",
            external_id, claude_projects_dir or "~/.claude/projects",
        )
        return 0

    total = 0
    seen = await _load_seen_uuids(db, run_id)
    # When backfilling a finished run, any node we ingest is also done — leaving
    # workers in 'running' makes the swimlane chip pulse blue forever.
    run_finished = (run["status"] in ("completed", "failed", "cancelled"))

    # 1) Main session — orchestrator node.
    main_node = await _ensure_main_node(
        hub, run_id, project_id, fallback_name=main_jsonl.stem or "claude",
    )
    try:
        added = await _replay_jsonl(
            hub, db, run_id, main_node, project_id, main_jsonl, seen=seen,
        )
    except OSError as e:
        log.warning("backfill_run: main replay failed for %s: %s", main_jsonl, e)
        added = 0
    total += added
    log.info("backfill_run: main session %s → %s messages", main_jsonl.name, added)

    # 2) Subagents — one worker node per agent_hash.
    subagents = main_jsonl.parent / external_id / "subagents"
    if subagents.exists():
        for meta_path in sorted(subagents.glob("agent-*.meta.json")):
            agent_hash = meta_path.stem.replace("agent-", "").replace(".meta", "")
            jsonl_path = subagents / f"agent-{agent_hash}.jsonl"
            if not jsonl_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                log.warning("backfill_run: meta read failed %s: %s", meta_path, e)
                continue
            agent_type = (meta.get("agentType") or "").strip()
            description = (meta.get("description") or "").strip()
            if not agent_type:
                continue
            node_id = await _resolve_node_for_subagent(
                hub=hub, db=db, run_id=run_id, project_id=project_id,
                parent_node_id=main_node,
                agent_type=agent_type, description=description,
                agent_hash=agent_hash,
            )
            if not node_id:
                continue
            try:
                added_sa = await _replay_jsonl(
                    hub, db, run_id, node_id, project_id, jsonl_path,
                    seen=seen,
                )
            except OSError as e:
                log.warning(
                    "backfill_run: subagent replay failed for %s: %s",
                    jsonl_path, e,
                )
                continue
            total += added_sa
            log.info(
                "backfill_run: subagent %s (%s) → %s messages",
                agent_type, agent_hash, added_sa,
            )
            if run_finished:
                try:
                    await hub.update_node_status(node_id, "completed")
                except Exception as e:
                    log.warning(
                        "backfill_run: update_node_status(%s) failed: %s",
                        node_id, e,
                    )

    return total
