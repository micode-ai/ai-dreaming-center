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


async def smoke_stream_generator():
    db, hub = await _setup()
    project_id = 1
    run_id = await hub.create_run(project_id, goal="stream-smoke")
    # Pre-seed one event so the snapshot is non-empty
    await hub.append_event(run_id, "warmup", {"i": 0})

    # Collect events from the generator with a 6s deadline
    collected: list[dict] = []

    async def feeder():
        await asyncio.sleep(0.1)
        await hub.append_event(run_id, "live", {"i": 1})
        await asyncio.sleep(0.1)
        await hub.append_event(run_id, "live", {"i": 2})
        # End the run so the generator terminates after idle window
        await hub.finish_run(run_id, status="completed")

    async def collect():
        async for ev in hub.stream_run_events(run_id, idle_close_seconds=1.0):
            collected.append(ev)
            if len(collected) >= 4:  # snapshot + 2 live + done (warmup is in snapshot only, not re-emitted)
                break

    await asyncio.wait_for(asyncio.gather(feeder(), collect()), timeout=6.0)
    # First yield should be snapshot
    assert collected[0]["event"] == "snapshot", f"expected snapshot first, got {collected[0]['event']}"
    snap = collected[0]["data"]
    assert "stages" in snap and "nodes" in snap and "messages" in snap, f"snapshot missing keys: {list(snap.keys())}"
    # Remaining yields are the 'live' events; 'warmup' was already there before stream started so it won't be re-emitted
    event_types = [c["event"] for c in collected[1:]]
    assert "live" in event_types, f"expected live events in {event_types}"
    print("  [OK] stream_run_events generator yields snapshot + events")


def smoke_route_endpoint():
    """Verify the SSE stream route is registered on the FastAPI app.

    We could TestClient-roundtrip, but `setup_gate_middleware` returns
    303 -> /setup before the router runs when the projects table is empty,
    making a roundtrip indistinguishable between "route exists" and "route
    doesn't exist". Inspecting `app.routes` directly proves the registration.
    """
    import os
    # Use an isolated DB so settings load with no clobber.
    os.environ["DC_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="dc_smoke_app_")) / "test.db")
    from dreaming.main import app  # noqa: E402

    target_path = "/p/{slug}/orchestration/{run_id}/stream"
    registered = [r.path for r in app.routes if hasattr(r, "path")]
    assert target_path in registered, (
        f"expected route {target_path!r} to be registered. "
        f"Found {len(registered)} routes; first 10: {registered[:10]!r}"
    )
    # Also confirm it's specifically a GET on that path.
    target_methods = None
    for r in app.routes:
        if getattr(r, "path", None) == target_path:
            target_methods = getattr(r, "methods", None)
            break
    assert target_methods and "GET" in target_methods, (
        f"expected GET on {target_path}, got methods={target_methods}"
    )
    print("  [OK] /stream route registered (GET on /p/{slug}/orchestration/{run_id}/stream)")


async def smoke_dispatch_seeds_stage():
    """A fresh run started via start_orchestration_run should have at least
    one stage row, and its root node should be tagged with that stage_id."""
    from unittest.mock import AsyncMock, MagicMock
    db, hub = await _setup()
    pm = MagicMock()
    pm.start_command = AsyncMock(side_effect=RuntimeError("no claude binary in smoke"))
    settings = MagicMock(port=8086, claude_path="claude", model="sonnet",
                         orchestration_max_turns=150, orchestration_timeout_minutes=120,
                         claude_projects_dir="")
    app_state = MagicMock(
        orchestration_hub=hub, process_manager=pm, settings=settings, db=db,
    )
    project = MagicMock(id=1, slug="smoke", working_dir="/tmp")

    from dreaming.services.orchestration_dispatch import start_orchestration_run
    result = await start_orchestration_run(app_state, project, "test goal")
    run_id = result["run_id"]
    stages = await hub.list_stages(run_id)
    assert len(stages) >= 1, "expected at least one stage to be created"
    nodes = await hub.list_nodes(run_id)
    root = [n for n in nodes if (n["role"] or "").lower() == "orchestrator"]
    assert root, "expected an orchestrator root node"
    assert root[0]["stage_id"] == stages[0]["id"], (
        f"root node stage_id {root[0]['stage_id']!r} != stage {stages[0]['id']!r}")
    print("  [OK] dispatch seeds initial stage and tags root node")


async def main():
    await smoke_list_events_since()
    await smoke_stream_generator()
    await smoke_dispatch_seeds_stage()
    print("smoke_orchestration_stream OK (async smokes)")


def main_entry():
    """Sync entry: runs async smokes first, then sync TestClient smoke."""
    asyncio.run(main())
    smoke_route_endpoint()
    print("smoke_orchestration_stream OK (with route)")


if __name__ == "__main__":
    main_entry()
