"""Stub for Wave 1+. Public API mirrors ALC's ProcessManager but raises NotImplementedError
for spawn-related calls. Allows downstream imports in Wave 0.

NOTE for Wave 1 implementer:
- Add per-project FIFO queue (dict[project_id, list[QueuedTask]]) and global semaphore
  for `max_concurrent`; per-project semaphore for `max_concurrent_per_project`.
- Add `keep_awake: KeepAwake` attribute (Windows Modern Standby suppressor) — owned
  by ProcessManager, not app.state, per spec singleton inventory.
- See spec § "Process Manager" and "Concurrency".
"""
from __future__ import annotations


class ProcessManager:
    def __init__(self, settings, db, projects):
        self.settings = settings
        self.db = db
        self.projects = projects
        self.running: dict[str, dict] = {}
        # Wave 1: queue, semaphores, keep_awake go here.

    async def start_session(self, project, agent_name: str, **kwargs) -> str:
        raise NotImplementedError("ProcessManager.start_session implemented in Wave 1")

    async def start_command(self, project, command_name: str, prompt: str, **kwargs) -> str:
        raise NotImplementedError("ProcessManager.start_command implemented in Wave 1")

    async def kill(self, key: str) -> bool:
        return False

    async def reconcile_stale_sessions(self, active_pairs: list[tuple[int, str]]) -> int:
        """active_pairs: list of (project_id, agent_name) tuples — see spec.
        Wave 0 stub: noop."""
        return 0
