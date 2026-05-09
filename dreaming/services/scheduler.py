"""Wave 1 scheduler: global reconcile + per-project nightly_learning jobs.

Global jobs:
- `reconcile_stale_sessions` (interval, every 5 minutes) — closes orphan
  sessions whose process has vanished.

Per-project jobs:
- `nightly_learning_{slug}` (cron) — picks top-N agents and runs self-study.
  Lifecycle: register on project enable / import / settings change;
  unregister on project disable / delete.
"""
from __future__ import annotations
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from dreaming.services.config_resolver import ConfigResolver

log = logging.getLogger(__name__)


def _job_id(kind: str, slug: str) -> str:
    return f"{kind}_{slug}"


async def _reconcile_job(app_state):
    """Build (project_id, agent_name) pairs from currently-running keys, then
    ask ProcessManager to close orphans."""
    pm = app_state.process_manager
    pairs: list[tuple[int, str]] = []
    for key, sess in pm.list_running().items():
        if key.startswith("cmd:"):
            continue
        slug, _, agent = key.partition(":")
        proj = await app_state.projects.get_by_slug(slug)
        if proj:
            pairs.append((proj.id, agent))
    try:
        return await pm.reconcile_stale_sessions(pairs)
    except Exception as e:
        log.warning("reconcile_job error: %s", e)
        return 0


async def _nightly_learning(app_state, project_id: int):
    """Pick top-N agents from this project's rotation and start self-study sessions."""
    proj = await app_state.projects.get_by_id(project_id)
    if proj is None or not proj.enabled:
        log.info("nightly_learning skipped: project %d missing or disabled", project_id)
        return
    db = app_state.db
    pm = app_state.process_manager
    settings = app_state.settings
    resolver = ConfigResolver(app_state.projects, settings)
    n = int(await resolver.get(proj, "agents_per_night", 5))
    pause = int(await resolver.get(proj, "wait_between_sec", 5))
    candidates = await db.next_agents_for_nightly(proj.id, n)
    log.info("nightly_learning [%s]: %d candidates", proj.slug, len(candidates))
    for row in candidates:
        try:
            await pm.start_session(
                proj,
                agent_name=row["agent_name"],
                claude_path=await resolver.get(proj, "claude_path", "claude"),
                working_dir=proj.working_dir,
                model=await resolver.get(proj, "model", "sonnet"),
                max_turns=int(await resolver.get(proj, "max_turns", 25)),
                timeout_minutes=int(await resolver.get(proj, "timeout_minutes", 20)),
                self_study_command=await resolver.get(proj, "self_study_command", "/self-study"),
                env_overrides={
                    "DREAMING_PROJECT_SLUG": proj.slug,
                    "DREAMING_API_URL": f"http://localhost:{settings.port}",
                },
            )
        except RuntimeError as e:
            log.warning("nightly_learning [%s] %s: %s", proj.slug, row["agent_name"], e)
        await asyncio.sleep(pause)


async def register_project_jobs(scheduler: AsyncIOScheduler, app_state, project) -> None:
    """Register all per-project jobs for a single project. Idempotent
    (replace_existing=True). Skips if project disabled or cron disabled."""
    if not project.enabled:
        return
    resolver = ConfigResolver(app_state.projects, app_state.settings)
    cron_expr = await resolver.get(project, "cron_expression", "0 2 * * *")
    enabled = await resolver.get(project, "cron_enabled", True)
    if not enabled:
        return
    job_id = _job_id("nightly_learning", project.slug)
    try:
        scheduler.add_job(
            _nightly_learning,
            CronTrigger.from_crontab(cron_expr),
            args=[app_state, project.id],
            id=job_id,
            replace_existing=True,
        )
    except Exception as e:
        log.warning("Failed to register %s: %s", job_id, e)


async def unregister_project_jobs(scheduler: AsyncIOScheduler, project) -> None:
    """Remove all per-project jobs for a single project. Safe if not registered."""
    for kind in ("nightly_learning",):
        try:
            scheduler.remove_job(_job_id(kind, project.slug))
        except Exception:
            pass


def build_scheduler(app_state) -> AsyncIOScheduler:
    """Build scheduler with the global reconcile job. Per-project jobs are
    registered separately by main.py after lifespan startup completes."""
    sched = AsyncIOScheduler()
    sched.add_job(
        _reconcile_job, "interval", minutes=5, args=[app_state],
        id="reconcile_stale_sessions",
    )
    return sched
