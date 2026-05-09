"""Wave 0: only the global reconcile_stale_sessions interval runs.
Per-project crons land in Wave 1+."""
from __future__ import annotations
from apscheduler.schedulers.asyncio import AsyncIOScheduler


def build_scheduler(app_state) -> AsyncIOScheduler:
    sched = AsyncIOScheduler()

    async def reconcile_job():
        # Wave 1+ supplies real reconcile logic via ProcessManager
        pm = app_state.process_manager
        active = list(pm.running.keys())  # in W0 always empty
        return await pm.reconcile_stale_sessions([])

    sched.add_job(reconcile_job, "interval", minutes=5, id="reconcile_stale_sessions")
    return sched
