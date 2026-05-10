"""Backfill orchestrator nodes/messages for a run from on-disk Claude jsonl files.

Scenario: a run was created (we know its external_id, which equals Claude's
session UUID) but the orchestration tables are empty for it — either the run
predates the watcher or the watcher was offline. This module scans:

    1. The main session jsonl `<external_id>.jsonl` (replayed into the
       orchestrator node, creating one if needed).
    2. Any subagents at `<external_id>/subagents/agent-*.jsonl` plus their
       sibling `*.meta.json` (each replayed into a worker node).

Idempotent by Claude's per-line `uuid` — repeated invocations don't double-write
since `_ingest_line` dedupes against the `seen` set, but DB-level dedup is
not enforced here (Wave 3 lean has no message-level dedup column). Run twice
on a run that already has messages and you'll get duplicates; the smoke harness
recreates the DB before invoking, which avoids that case.
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


async def _replay_jsonl(
    hub: OrchestrationHub,
    db: SqliteDB,
    run_id: str,
    node_id: str,
    project_id: int,
    path: Path,
) -> int:
    """Replay every line of `path` through `_ingest_line`. Returns the count of
    appended messages."""
    appended = 0
    seen: set[str] = set()
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

    # 1) Main session — orchestrator node.
    main_node = await _ensure_main_node(
        hub, run_id, project_id, fallback_name=main_jsonl.stem or "claude",
    )
    try:
        added = await _replay_jsonl(hub, db, run_id, main_node, project_id, main_jsonl)
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

    return total
