"""Smoke check for Wave A orchestration SSE plumbing.

Exercises the hub helpers and (where possible) the SSE generator without
spinning up a full HTTP server. Run with:

    python scripts/smoke_orchestration_stream.py

Exits 0 on success, non-zero on failure. Prints a short summary line.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import uuid
from pathlib import Path

# Make the package importable when run from repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dreaming.services.db import SqliteDB
from dreaming.services.orchestration_hub import OrchestrationHub


async def _setup():
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_sse_")) / "test.db"
    db = SqliteDB(str(tmp))
    await db.connect()
    # Seed a project row so the FK on orchestrator_runs.project_id resolves.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO projects (id, slug, label, working_dir, enabled, is_default, sort_order, color, created_at, updated_at) "
        "VALUES (1, 'smoke', 'Smoke', ?, 1, 0, 0, NULL, ?, ?)",
        (str(tmp.parent), now, now),
    )
    hub = OrchestrationHub(db, projects=None)
    return db, hub


async def smoke_list_events_since():
    db, hub = await _setup()
    project_id = 1
    run_id = await hub.create_run(project_id, goal="smoke")
    # Append three events
    await hub.append_event(run_id, "a", {"i": 1})
    await hub.append_event(run_id, "b", {"i": 2})
    await hub.append_event(run_id, "c", {"i": 3})
    all_events = await hub.list_events(run_id)
    assert len(all_events) == 3, f"expected 3 events, got {len(all_events)}"
    cursor_ts = all_events[0]["ts"]
    cursor_id = all_events[0]["id"]
    newer = await hub.list_events_since(run_id, after_ts=cursor_ts, after_id=cursor_id)
    assert len(newer) == 2, f"expected 2 newer events, got {len(newer)}"
    assert newer[0]["event_type"] == "b"
    assert newer[1]["event_type"] == "c"
    # Also assert tied-ts behaviour: insert two events from inside the same tick
    # and confirm both come back when we cursor past only the first.
    await hub.append_event(run_id, "tie1", {})
    await hub.append_event(run_id, "tie2", {})
    after_b = await hub.list_events_since(run_id, after_ts=all_events[1]["ts"], after_id=all_events[1]["id"])
    types = [e["event_type"] for e in after_b]
    assert "c" in types and "tie1" in types and "tie2" in types, f"missed events: {types}"
    print("  [OK] list_events_since (composite cursor)")


async def main():
    await smoke_list_events_since()
    print("smoke_orchestration_stream OK")


if __name__ == "__main__":
    asyncio.run(main())
