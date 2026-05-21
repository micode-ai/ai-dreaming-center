"""Per-project dashboard tile data builders (Wave E MVP).

Each builder returns a small dict consumed by the corresponding partial template.
Builders are intentionally tolerant — if a data source is missing or raises,
they return an `error: <message>` dict so the partial can render a degraded card
without breaking the page."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


async def build_orchestration_tile(db, hub, project) -> dict[str, Any]:
    """Active orchestration runs + last completed run."""
    try:
        runs = await hub.list_runs(project.id, limit=10)
        running = [r for r in runs if r["status"] == "running"]
        last_completed = next(
            (r for r in runs if r["status"] in ("completed", "failed", "cancelled")),
            None,
        )
        return {
            "running_count": len(running),
            "running_ids": [r["id"][:8] for r in running[:3]],
            "last_completed": {
                "id": last_completed["id"][:8] if last_completed else None,
                "status": last_completed["status"] if last_completed else None,
                "finished_at": (last_completed["finished_at"] or "")[:19] if last_completed else None,
                "goal": (last_completed["goal"] or "")[:60] if last_completed else None,
            } if last_completed else None,
        }
    except Exception as e:
        log.warning("orchestration tile failed: %s", e)
        return {"error": str(e)}


async def build_evolutions_tile(db, projects_svc, project) -> dict[str, Any]:
    """Count evolution files by status."""
    try:
        from dreaming.services.evolutions import list_evolutions
        from dreaming.services import autoconfig
        overrides = await projects_svc.all_settings(project.id)
        evolutions_dir = (
            overrides.get("evolutions_dir")
            or autoconfig.default_abs(project, "evolutions_dir")
        )
        if not evolutions_dir or not Path(evolutions_dir).exists():
            return {"missing": True, "dir": evolutions_dir or ""}
        items = list_evolutions(evolutions_dir)
        buckets: dict[str, int] = {}
        for it in items:
            status = (getattr(it, "status", "") or "proposed").lower()
            buckets[status] = buckets.get(status, 0) + 1
        return {
            "total": len(items),
            "buckets": buckets,
            "dir": evolutions_dir,
        }
    except Exception as e:
        log.warning("evolutions tile failed: %s", e)
        return {"error": str(e)}


async def build_loops_tile(db, project) -> dict[str, Any]:
    """Recent loop runs from the loop_runs table (if present in the DB)."""
    try:
        # The loops table may not exist on all installations. Probe and degrade.
        row = await db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='loop_runs'",
        )
        if row is None:
            return {"missing_table": True}
        rows = await db.fetch_all(
            "SELECT id, slug, status, started_at, finished_at FROM loop_runs "
            "WHERE project_id=? ORDER BY started_at DESC LIMIT 5",
            (project.id,),
        )
        items = [dict(r) for r in rows]
        running = sum(1 for it in items if it["status"] == "running")
        last = items[0] if items else None
        return {
            "total": len(items),
            "running_count": running,
            "last": {
                "slug": (last["slug"] or "")[:30] if last else None,
                "status": last["status"] if last else None,
                "started_at": (last["started_at"] or "")[:19] if last else None,
            } if last else None,
        }
    except Exception as e:
        log.warning("loops tile failed: %s", e)
        return {"error": str(e)}
