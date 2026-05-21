"""Smoke check for Wave E MVP dashboard tiles."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def smoke_tiles_basic():
    from dreaming.services.db import SqliteDB
    from dreaming.services.orchestration_hub import OrchestrationHub
    from dreaming.services.dashboard_tiles import (
        build_orchestration_tile, build_evolutions_tile, build_loops_tile,
    )

    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_tiles_")) / "test.db"
    db = SqliteDB(str(tmp))
    await db.connect()
    # Seed a project row so create_run's FK resolves.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO projects (id, slug, label, working_dir, enabled, is_default, sort_order, color, created_at, updated_at) "
        "VALUES (1, 'smoke', 'Smoke', '/tmp/smoke', 1, 0, 0, NULL, ?, ?)",
        (now, now),
    )
    hub = OrchestrationHub(db, projects=None)
    project = MagicMock(id=1, slug="smoke", working_dir="/tmp/smoke")

    # Orchestration tile with empty data
    t1 = await build_orchestration_tile(db, hub, project)
    assert "running_count" in t1, f"orch tile missing running_count: {t1}"
    assert t1["running_count"] == 0
    print("  [OK] build_orchestration_tile (empty)")

    # Add a run, then non-empty
    run_id = await hub.create_run(project.id, goal="smoke goal")
    t2 = await build_orchestration_tile(db, hub, project)
    assert t2["running_count"] == 1, f"expected 1 running, got {t2}"
    print("  [OK] build_orchestration_tile (1 running)")

    # Evolutions tile — missing dir is OK
    projects_svc = MagicMock()
    projects_svc.all_settings = AsyncMock(return_value={})
    t3 = await build_evolutions_tile(db, projects_svc, project)
    assert "missing" in t3 or "total" in t3, f"evolutions tile unexpected: {t3}"
    print("  [OK] build_evolutions_tile (no dir)")

    # Loops tile — missing table is OK (DB has no loop_runs table by default in fresh schema)
    t4 = await build_loops_tile(db, project)
    assert "missing_table" in t4 or "total" in t4, f"loops tile unexpected: {t4}"
    print("  [OK] build_loops_tile (degrades gracefully)")


def smoke_templates_parse():
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("dreaming/templates"))
    env.filters["t"] = lambda k, **kw: k
    env.get_template("partials/dashboard/_tile_orchestration.html")
    env.get_template("partials/dashboard/_tile_evolutions.html")
    env.get_template("partials/dashboard/_tile_loops.html")
    env.get_template("project_dashboard.html")
    print("  [OK] partials + parent template parse")


def main():
    asyncio.run(smoke_tiles_basic())
    smoke_templates_parse()
    print("smoke_dashboard_tiles OK")


if __name__ == "__main__":
    main()
