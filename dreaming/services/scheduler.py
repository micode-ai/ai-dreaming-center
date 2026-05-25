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
from dreaming.services.topics_prompt import build_topics_extra_prompt

log = logging.getLogger(__name__)


def _job_id(kind: str, slug: str) -> str:
    return f"{kind}_{slug}"


async def _ai_usage_ingest_job(app_state):
    """Ingest Claude Code session JSONLs into ai_usage_events.

    `max_files` is raised well above the default (1000) — with a few thousand
    JSONLs accumulated over months, the alphabetically-first 1000 tend to be
    user-terminal sessions (`C:\\Users\\<name>` cwd) that don't match any
    project, so the parser hits the cap before reaching DC-spawned files."""
    from dreaming.services.ai_usage_parser import ingest_ai_usage
    try:
        result = await ingest_ai_usage(
            app_state.db, app_state.projects, max_files=20000,
        )
        log.info("ai_usage_ingest: %s", result)
    except Exception as e:
        log.warning("ai_usage_ingest failed: %s", e)


async def _reconcile_job(app_state):
    """Close orphans across all process-backed tables:
      - agent_learning_sessions (self-study + cmd:* sessions)
      - orchestrator_runs (Roman runs whose claude process is gone)
    """
    pm = app_state.process_manager
    pairs: list[tuple[int, str]] = []
    cmd_session_ids: set[str] = set()
    for key, sess in pm.list_running().items():
        if key.startswith("cmd:"):
            # `cmd:{slug}:{cmd_name}` — RunningSession.session_id holds the
            # claude `--session-id` (= orchestrator_runs.external_id for Roman).
            cmd_session_ids.add(getattr(sess, "session_id", "") or "")
            continue
        slug, _, agent = key.partition(":")
        proj = await app_state.projects.get_by_slug(slug)
        if proj:
            pairs.append((proj.id, agent))
    closed = 0
    try:
        closed += await pm.reconcile_stale_sessions(pairs) or 0
    except Exception as e:
        log.warning("reconcile_job session error: %s", e)
    try:
        closed += await app_state.db.cancel_stale_orchestration_runs(
            cmd_session_ids, grace_minutes=5,
        ) or 0
    except Exception as e:
        log.warning("reconcile_job orchestration error: %s", e)
    return closed


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
            extra_prompt = await build_topics_extra_prompt(
                db, proj.id, row["agent_name"],
            )
        except Exception as e:
            log.warning("nightly_learning [%s] %s: topics helper failed: %s",
                        proj.slug, row["agent_name"], e)
            extra_prompt = ""
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
                extra_prompt=extra_prompt,
                env_overrides={
                    "DREAMING_PROJECT_SLUG": proj.slug,
                    "DREAMING_API_URL": f"http://localhost:{settings.port}",
                },
            )
        except RuntimeError as e:
            log.warning("nightly_learning [%s] %s: %s", proj.slug, row["agent_name"], e)
        await asyncio.sleep(pause)


async def _weekly_tech_debt_scan(app_state, project_id: int):
    """Run the per-project tech-debt scan command via Claude CLI."""
    proj = await app_state.projects.get_by_id(project_id)
    if proj is None or not proj.enabled:
        return
    pm = app_state.process_manager
    settings = app_state.settings
    resolver = ConfigResolver(app_state.projects, settings)
    try:
        await pm.start_command(
            proj,
            command_name="weekly-tech-debt-scan",
            prompt="/tech-debt-scan",
            claude_path=await resolver.get(proj, "claude_path", "claude"),
            working_dir=proj.working_dir,
            model=await resolver.get(proj, "model", "sonnet"),
            max_turns=int(await resolver.get(proj, "max_turns", 50)),
            timeout_minutes=int(await resolver.get(proj, "timeout_minutes", 60)),
            env_overrides={
                "DREAMING_PROJECT_SLUG": proj.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        log.warning("weekly_tech_debt_scan [%s]: %s", proj.slug, e)


async def _weekly_product_ideas_scan(app_state, project_id: int):
    """Run the per-project product-ideas scan command via Claude CLI."""
    proj = await app_state.projects.get_by_id(project_id)
    if proj is None or not proj.enabled:
        return
    pm = app_state.process_manager
    settings = app_state.settings
    resolver = ConfigResolver(app_state.projects, settings)
    try:
        await pm.start_command(
            proj,
            command_name="weekly-product-ideas-scan",
            prompt="/product-idea-scan",
            claude_path=await resolver.get(proj, "claude_path", "claude"),
            working_dir=proj.working_dir,
            model=await resolver.get(proj, "model", "sonnet"),
            max_turns=int(await resolver.get(proj, "max_turns", 50)),
            timeout_minutes=int(await resolver.get(proj, "timeout_minutes", 60)),
            env_overrides={
                "DREAMING_PROJECT_SLUG": proj.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        log.warning("weekly_product_ideas_scan [%s]: %s", proj.slug, e)


async def _weekly_wiki_lint(app_state, project_id: int):
    """Run the per-project wiki-lint command via Claude CLI."""
    proj = await app_state.projects.get_by_id(project_id)
    if proj is None or not proj.enabled:
        return
    pm = app_state.process_manager
    settings = app_state.settings
    resolver = ConfigResolver(app_state.projects, settings)
    try:
        await pm.start_command(
            proj,
            command_name="weekly-wiki-lint",
            prompt="/wiki-lint",
            claude_path=await resolver.get(proj, "claude_path", "claude"),
            working_dir=proj.working_dir,
            model=await resolver.get(proj, "model", "sonnet"),
            max_turns=int(await resolver.get(proj, "max_turns", 50)),
            timeout_minutes=int(await resolver.get(proj, "timeout_minutes", 60)),
            env_overrides={
                "DREAMING_PROJECT_SLUG": proj.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        log.warning("weekly_wiki_lint [%s]: %s", proj.slug, e)


async def _weekly_wiki_health_scan(app_state, project_id: int):
    """Run /wiki-health-scan via Claude CLI to append a fresh wiki-health snapshot."""
    proj = await app_state.projects.get_by_id(project_id)
    if proj is None or not proj.enabled:
        return
    pm = app_state.process_manager
    settings = app_state.settings
    resolver = ConfigResolver(app_state.projects, settings)
    try:
        await pm.start_command(
            proj,
            command_name="weekly-wiki-health-scan",
            prompt="/wiki-health-scan",
            claude_path=await resolver.get(proj, "claude_path", "claude"),
            working_dir=proj.working_dir,
            model=await resolver.get(proj, "model", "sonnet"),
            max_turns=int(await resolver.get(proj, "max_turns", 50)),
            timeout_minutes=int(await resolver.get(proj, "timeout_minutes", 30)),
            env_overrides={
                "DREAMING_PROJECT_SLUG": proj.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        log.warning("weekly_wiki_health_scan [%s]: %s", proj.slug, e)


async def _weekly_topics_scan(app_state, project_id: int):
    """Run /topics-scan via Claude CLI to generate fresh learning topics."""
    proj = await app_state.projects.get_by_id(project_id)
    if proj is None or not proj.enabled:
        return
    pm = app_state.process_manager
    settings = app_state.settings
    resolver = ConfigResolver(app_state.projects, settings)
    try:
        await pm.start_command(
            proj,
            command_name="weekly-topics-scan",
            prompt="/topics-scan",
            claude_path=await resolver.get(proj, "claude_path", "claude"),
            working_dir=proj.working_dir,
            model=await resolver.get(proj, "model", "sonnet"),
            max_turns=int(await resolver.get(proj, "max_turns", 50)),
            timeout_minutes=int(await resolver.get(proj, "timeout_minutes", 30)),
            env_overrides={
                "DREAMING_PROJECT_SLUG": proj.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        log.warning("weekly_topics_scan [%s]: %s", proj.slug, e)


# (kind, cron_setting_key, enabled_setting_key, default_cron, default_enabled, fn)
_PER_PROJECT_JOBS = [
    ("nightly_learning", "cron_expression", "cron_enabled", "0 2 * * *", True, _nightly_learning),
    ("weekly_tech_debt_scan", "weekly_tech_debt_scan_cron", "weekly_tech_debt_scan_enabled", "0 4 * * 1", False, _weekly_tech_debt_scan),
    ("weekly_product_ideas_scan", "weekly_product_ideas_scan_cron", "weekly_product_ideas_scan_enabled", "0 5 * * 1", False, _weekly_product_ideas_scan),
    ("weekly_wiki_lint", "weekly_wiki_lint_cron", "weekly_wiki_lint_enabled", "0 6 * * 6", False, _weekly_wiki_lint),
    ("weekly_topics_scan", "weekly_topics_scan_cron", "weekly_topics_scan_enabled",
     "0 3 * * 1", False, _weekly_topics_scan),
    ("weekly_wiki_health_scan", "weekly_wiki_health_scan_cron", "weekly_wiki_health_scan_enabled",
     "0 7 * * 6", False, _weekly_wiki_health_scan),
]


async def register_project_jobs(scheduler: AsyncIOScheduler, app_state, project) -> None:
    """Register all per-project jobs for a single project. Idempotent
    (replace_existing=True). Skips if project disabled or job kind disabled.
    Removes previously-registered jobs that are now disabled."""
    if not project.enabled:
        return
    resolver = ConfigResolver(app_state.projects, app_state.settings)
    for kind, cron_key, enabled_key, cron_default, default_enabled, fn in _PER_PROJECT_JOBS:
        cron_expr = await resolver.get(project, cron_key, cron_default)
        enabled = await resolver.get(project, enabled_key, default_enabled)
        job_id = _job_id(kind, project.slug)
        if not enabled:
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass
            continue
        try:
            scheduler.add_job(
                fn,
                CronTrigger.from_crontab(cron_expr),
                args=[app_state, project.id],
                id=job_id,
                replace_existing=True,
            )
        except Exception as e:
            log.warning("Failed to register %s: %s", job_id, e)


async def unregister_project_jobs(scheduler: AsyncIOScheduler, project) -> None:
    """Remove all per-project jobs for a single project. Safe if not registered."""
    for kind, _ck, _ek, _cd, _de, _fn in _PER_PROJECT_JOBS:
        try:
            scheduler.remove_job(_job_id(kind, project.slug))
        except Exception:
            pass


async def _radar_scan_job(app_state):
    """Global weekly AI Radar scan — fetch the watchlist's RSS/Atom feeds and
    merge new findings. Gated by `radar_scan_enabled`."""
    try:
        from dreaming.services.ai_radar_scan import scan_now
        res = await scan_now(app_state.db)
        log.info("radar_scan_job: %d new findings from %d feeds",
                 res.get("inserted", 0), res.get("sources_with_feed", 0))
    except Exception as e:
        log.warning("radar_scan_job failed: %s", e)


def build_scheduler(app_state) -> AsyncIOScheduler:
    """Build scheduler with the global reconcile job. Per-project jobs are
    registered separately by main.py after lifespan startup completes."""
    sched = AsyncIOScheduler()
    sched.add_job(
        _reconcile_job, "interval", minutes=5, args=[app_state],
        id="reconcile_stale_sessions",
    )
    sched.add_job(
        _ai_usage_ingest_job, "interval", minutes=5, args=[app_state],
        id="ai_usage_ingest",
    )
    settings = app_state.settings
    if getattr(settings, "radar_scan_enabled", False):
        cron = getattr(settings, "radar_scan_cron", "0 7 * * 1")
        try:
            sched.add_job(
                _radar_scan_job, CronTrigger.from_crontab(cron), args=[app_state],
                id="radar_scan",
            )
        except ValueError as e:
            log.warning("radar_scan: bad cron %r (%s) — job not scheduled", cron, e)
    return sched
