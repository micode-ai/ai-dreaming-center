"""Watcher over the subagents/ folder of an active orchestration run.

When the main Claude CLI delegates via the Task tool (Agent), it spawns a child
Claude process and writes its stream into:
    ~/.claude/projects/<workdir>/<session_id>/subagents/agent-<hash>.jsonl
plus a sibling agent-<hash>.meta.json containing {agentType, description}.

This module polls the subagents/ folder for an active run: for each new
`*.meta.json` it (1) ensures a worker `orchestrator_nodes` row exists for
this agent_hash (idempotent — same hash always maps to the same node), and
(2) launches a `tail_session_file` task on the matching jsonl. From that point
on subagent messages stream into their own node in real time.

Ported from agent-learning-center's subagent_watcher. The ALC original also
reused pre-created placeholder nodes per stage; here we always create a fresh
worker node per subagent jsonl. Stage tables now exist (orchestrator_stages),
but stage→node attachment is left for callers that need it — the default
case (one orchestrator + N workers) does not require stage binding.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from dreaming.services import claude_session_tail as session_tail
from dreaming.services.db import SqliteDB
from dreaming.services.orchestration_hub import OrchestrationHub

log = logging.getLogger(__name__)


def _node_external_id(row) -> str | None:
    """Pull external_id from a sqlite Row or dict, returning None if absent/missing."""
    try:
        return row["external_id"]
    except (KeyError, TypeError, IndexError):
        return None


def _node_field(row, key: str):
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return None


async def _resolve_node_for_subagent(
    *,
    hub: OrchestrationHub,
    db: SqliteDB,
    run_id: str,
    project_id: int,
    parent_node_id: str | None,
    agent_type: str,
    description: str,
    agent_hash: str,
) -> str | None:
    """One subagent_hash = one task = one node in DB.

    Lookup order:
      1) If a node with `external_id == agent_hash` already exists, reuse it.
      2) Otherwise create a fresh worker node parented at `parent_node_id`.
    """
    nodes = await hub.list_nodes(run_id)
    for n in nodes:
        if _node_external_id(n) == agent_hash:
            return _node_field(n, "id")

    # Look up the parent's stage_id so sub-agents appear in the same swimlane
    # row as the orchestrator that spawned them. Pass it into create_node so
    # the node_created SSE event carries it from the start.
    parent_stage_id: str | None = None
    if parent_node_id:
        for n in nodes:
            if _node_field(n, "id") == parent_node_id:
                parent_stage_id = _node_field(n, "stage_id")
                break

    node_id = await hub.create_node(
        run_id, project_id,
        agent_name=agent_type, role="worker",
        parent_node_id=parent_node_id, external_id=agent_hash,
        stage_id=parent_stage_id,
    )
    return node_id


async def watch_subagents_for_run(
    *,
    run_id: str,
    parent_node_id: str,
    folder: Path,
    hub: OrchestrationHub,
    db: SqliteDB,
    poll_interval: float = 1.0,
    stop_event: asyncio.Event | None = None,
    tails: dict[str, asyncio.Task] | None = None,
) -> dict[str, asyncio.Task]:
    """Background coroutine: poll `folder` and attach a tail-task per new subagent.

    The optional `tails` dict is mutated in place — caller can hold onto it for
    later cleanup via `stop_subagent_tails`. Returns the same dict.
    """
    run = await hub.get_run(run_id)
    if run is None:
        log.warning("watch_subagents_for_run: run %s not found", run_id)
        return tails or {}
    project_id = run["project_id"]
    if tails is None:
        tails = {}

    while True:
        if stop_event is not None and stop_event.is_set():
            return tails
        try:
            if folder.exists():
                for meta_path in folder.glob("agent-*.meta.json"):
                    agent_hash = meta_path.stem.replace("agent-", "").replace(".meta", "")
                    if agent_hash in tails:
                        continue
                    jsonl_path = folder / f"agent-{agent_hash}.jsonl"
                    if not jsonl_path.exists():
                        continue
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError) as e:
                        log.warning("subagent meta read failed %s: %s", meta_path, e)
                        continue
                    agent_type = (meta.get("agentType") or "").strip()
                    description = (meta.get("description") or "").strip()
                    if not agent_type:
                        log.warning("subagent meta without agentType: %s", meta_path)
                        continue
                    node_id = await _resolve_node_for_subagent(
                        hub=hub, db=db, run_id=run_id, project_id=project_id,
                        parent_node_id=parent_node_id,
                        agent_type=agent_type, description=description,
                        agent_hash=agent_hash,
                    )
                    if not node_id:
                        continue
                    seen: set[str] = set()
                    task = asyncio.create_task(
                        session_tail.tail_session_file(
                            run_id=run_id, node_id=node_id, project_id=project_id,
                            path=jsonl_path, hub=hub, db=db,
                            seen_uuids=seen,
                            idle_finalize_after=30.0,
                        )
                    )
                    tails[agent_hash] = task
                    log.info(
                        "subagent attached: run=%s agent=%s hash=%s -> node=%s",
                        run_id, agent_type, agent_hash, node_id,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("subagent watcher iteration error for run %s: %s", run_id, e)
        await asyncio.sleep(poll_interval)


async def stop_subagent_tails(tails: dict[str, asyncio.Task]) -> None:
    """Cancel all tail tasks in `tails` and await their termination. Idempotent."""
    for task in list(tails.values()):
        task.cancel()
    for task in list(tails.values()):
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    tails.clear()


class SubagentWatcher:
    """Object wrapper around `watch_subagents_for_run` matching the Wave 3 spec.

    Resolves the subagents/ folder lazily on `start()`. Pass `claude_projects_dir`
    to override `~/.claude/projects` (e.g. for tests).
    """

    def __init__(
        self,
        run_id: str,
        parent_node_id: str,
        hub: OrchestrationHub,
        db: SqliteDB,
        claude_projects_dir: str | None = None,
        working_dir: str | None = None,
    ):
        self.run_id = run_id
        self.parent_node_id = parent_node_id
        self.hub = hub
        self.db = db
        self.claude_projects_dir = claude_projects_dir
        self.working_dir = working_dir
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._tails: dict[str, asyncio.Task] = {}

    async def _resolve_folder(self) -> Path | None:
        """Compute this run's subagents/ folder path.

        When `working_dir` is known (the common case — dispatcher passes it),
        derive the path directly from `(claude_projects_dir, working_dir,
        external_id)` so we can return the EXPECTED path even before Claude
        has created it. The polling loop in `watch_subagents_for_run` tolerates
        a not-yet-existing folder and picks it up the moment Claude writes the
        first subagent meta file.

        Fallback (legacy callers without working_dir): rglob the projects root
        for `<external_id>.jsonl`. Returns None if external_id is missing or
        the legacy lookup finds nothing.
        """
        run = await self.hub.get_run(self.run_id)
        if run is None:
            return None
        external_id = run["external_id"]
        if not external_id:
            return None
        root = Path(self.claude_projects_dir) if self.claude_projects_dir \
            else session_tail.claude_projects_root()
        if self.working_dir:
            return root / session_tail.encode_workdir(self.working_dir) / external_id / "subagents"
        if not root.exists():
            return None
        for path in root.rglob(f"{external_id}.jsonl"):
            if path.is_file():
                return path.parent / external_id / "subagents"
        return None

    async def start(self) -> None:
        if self._task is not None:
            return
        folder = await self._resolve_folder()
        if folder is None:
            log.info(
                "SubagentWatcher.start: no subagents folder for run=%s — watcher idle",
                self.run_id,
            )
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            watch_subagents_for_run(
                run_id=self.run_id,
                parent_node_id=self.parent_node_id,
                folder=folder,
                hub=self.hub,
                db=self.db,
                stop_event=self._stop,
                tails=self._tails,
            )
        )

    async def stop(self) -> None:
        self._stop.set()
        task, self._task = self._task, None
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception as e:
                log.warning("watcher task ended with error: %s", e)
        await stop_subagent_tails(self._tails)
