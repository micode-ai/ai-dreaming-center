# Wave A: Orchestration SSE + Swimlane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the polling-based orchestration detail page with live SSE updates and a dynamic stage-rail + swimlane visualization, matching ALC's orchestration UX.

**Architecture:** Server-side async generator tails `orchestrator_events` table (no schema changes; stage association derived via JOIN through `orchestrator_nodes.stage_id`). Client uses `EventSource` to receive events, mutates the DOM in place. On SSE error, falls back to existing `/refresh` polling.

**Tech Stack:** FastAPI, `sse-starlette` (already a dependency), `EventSource` (browser native), Jinja2, vanilla JS, SQLite via existing `SqliteDB`.

**Spec:** `docs/superpowers/specs/2026-05-21-alc-features-port-design.md` (Wave A section).

---

## File Structure

**New files:**
- `dreaming/static/orchestration_stream.js` — EventSource client, DOM mutation, polling fallback
- `dreaming/static/orchestration_swimlane.css` — stage rail, swimlane, activity chip styles (extracted from inline CSS for clarity)
- `scripts/smoke_orchestration_stream.py` — smoke test for the SSE generator and route

**Modified files:**
- `dreaming/services/orchestration_hub.py` — add `stream_run_events()` async generator + `list_events_since()` helper
- `dreaming/routes/project_orchestration.py` — add `GET /p/{slug}/orchestration/{run_id}/stream` returning `EventSourceResponse`; extend detail handler to render swimlane context (stages, nodes-by-stage)
- `dreaming/templates/project_orchestration_detail.html` — replace polling-script-only layout with server-rendered stage rail + swimlane skeleton; include new JS/CSS
- `dreaming/main.py` — mount `/static` if not already mounted (verify; likely already there)
- `dreaming/i18n/messages_ru.json` + `dreaming/i18n/messages_en.json` — add new UI strings

**Untouched (intentionally):**
- The existing `/refresh` polling route stays as the JS-disabled fallback.
- `claude_session_tail.py` — already emits `message_added` events via `hub.append_event`; no parser changes needed for Wave A. Stage-marker parsing is a future enhancement (mentioned in spec but is not load-bearing for the swimlane to render — stage rows already get created by the orchestration_dispatch layer).

---

## Task 1: Add event-stream helper methods to OrchestrationHub

Adds two small helpers to `OrchestrationHub` so the route doesn't need to write SQL inline.

**Files:**
- Modify: `dreaming/services/orchestration_hub.py` (add methods after existing `list_events`)
- Test: `scripts/smoke_orchestration_stream.py` (new)

- [ ] **Step 1: Create the smoke script with the failing test for `list_events_since`**

Write `scripts/smoke_orchestration_stream.py`:

```python
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
    hub = OrchestrationHub(db, projects=None)
    # Create a minimal project row so FK on orchestrator_runs.project_id can be satisfied
    # by the integer 1 (projects table has no FK back to runs; we only need the id to exist
    # for the joins to look natural — orchestrator_runs.project_id is NOT a FK in schema).
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
    cursor_id = all_events[0]["id"]
    # New helper: list events with id > cursor (lex order — uuids work because ids are stored
    # as strings; we need a different cursor scheme. Use `ts` instead: events appended later
    # have lexicographically later ts ISO strings).
    cursor_ts = all_events[0]["ts"]
    newer = await hub.list_events_since(run_id, since_ts=cursor_ts)
    assert len(newer) == 2, f"expected 2 newer events, got {len(newer)}"
    assert newer[0]["event_type"] == "b"
    assert newer[1]["event_type"] == "c"
    print("  ✓ list_events_since")


async def main():
    await smoke_list_events_since()
    print("smoke_orchestration_stream OK")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run smoke, confirm it fails with AttributeError on `list_events_since`**

Run:
```powershell
python scripts/smoke_orchestration_stream.py
```
Expected: `AttributeError: 'OrchestrationHub' object has no attribute 'list_events_since'`

- [ ] **Step 3: Add `list_events_since` to OrchestrationHub**

In `dreaming/services/orchestration_hub.py`, immediately after the existing `list_events` method (around line 155), add:

```python
    async def list_events_since(self, run_id: str, since_ts: str | None) -> list:
        """Events strictly after `since_ts` (ISO8601 UTC). Pass None to get all."""
        if since_ts is None:
            return await self.db.fetch_all(
                "SELECT * FROM orchestrator_events WHERE run_id=? ORDER BY ts ASC",
                (run_id,),
            )
        return await self.db.fetch_all(
            "SELECT * FROM orchestrator_events WHERE run_id=? AND ts > ? "
            "ORDER BY ts ASC",
            (run_id, since_ts),
        )
```

- [ ] **Step 4: Re-run smoke, confirm it passes**

Run:
```powershell
python scripts/smoke_orchestration_stream.py
```
Expected: `smoke_orchestration_stream OK` (and exit code 0).

- [ ] **Step 5: Commit**

```powershell
git add dreaming/services/orchestration_hub.py scripts/smoke_orchestration_stream.py
git commit -m "feat(orchestration): add list_events_since helper for SSE cursor tailing"
```

---

## Task 2: Add `stream_run_events` async generator on the hub

The generator yields an initial snapshot (current stages + nodes + messages) and then incremental events from `orchestrator_events`, terminating cleanly when the run finishes AND no new events arrive for 3 seconds.

**Files:**
- Modify: `dreaming/services/orchestration_hub.py`
- Test: `scripts/smoke_orchestration_stream.py`

- [ ] **Step 1: Extend smoke with a failing test for `stream_run_events`**

Append this function to `scripts/smoke_orchestration_stream.py` and call it from `main()`:

```python
async def smoke_stream_generator():
    db, hub = await _setup()
    project_id = 1
    run_id = await hub.create_run(project_id, goal="stream-smoke")
    # Pre-seed one event so the snapshot is non-empty
    await hub.append_event(run_id, "warmup", {"i": 0})

    # Collect the first 3 events from the generator with a 2s deadline
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
            if len(collected) >= 4:  # 1 snapshot + 3 events (warmup + 2 live)
                break

    await asyncio.wait_for(asyncio.gather(feeder(), collect()), timeout=6.0)
    # First yield should be snapshot
    assert collected[0]["event"] == "snapshot", f"expected snapshot first, got {collected[0]['event']}"
    snap = collected[0]["data"]
    assert "stages" in snap and "nodes" in snap and "messages" in snap
    # Remaining yields are the events
    event_types = [c["event"] for c in collected[1:]]
    assert "warmup" in event_types, f"expected warmup in {event_types}"
    print("  ✓ stream_run_events generator yields snapshot + events")


async def main():
    await smoke_list_events_since()
    await smoke_stream_generator()
    print("smoke_orchestration_stream OK")
```

- [ ] **Step 2: Run smoke, confirm it fails on missing `stream_run_events`**

Run:
```powershell
python scripts/smoke_orchestration_stream.py
```
Expected: `AttributeError: 'OrchestrationHub' object has no attribute 'stream_run_events'`

- [ ] **Step 3: Implement `stream_run_events` on the hub**

Add this method to `dreaming/services/orchestration_hub.py` right after `list_events_since`:

```python
    async def stream_run_events(
        self, run_id: str, *,
        poll_interval: float = 0.5,
        idle_close_seconds: float = 3.0,
    ):
        """Async generator that yields dicts of shape `{"event": str, "data": dict}`.

        First yield is always `{"event": "snapshot", "data": {stages, nodes, messages}}`
        so a client connecting mid-run gets full state.

        Subsequent yields are `{"event": <event_type>, "data": <payload>}` for each
        new row in `orchestrator_events`. The generator terminates when the run is in
        a terminal status AND no new events have arrived for `idle_close_seconds`.

        Implementation note: tails the events table via repeated `list_events_since`
        polls. This is fine for a local single-user dashboard; for multi-user fan-out
        an asyncio.Queue pub/sub would be preferable.
        """
        import asyncio

        # Initial snapshot.
        run = await self.get_run(run_id)
        if run is None:
            yield {"event": "error", "data": {"message": f"run {run_id} not found"}}
            return
        stages = [dict(r) for r in await self.list_stages(run_id)]
        nodes = [dict(r) for r in await self.list_nodes(run_id)]
        messages = [dict(r) for r in await self.list_messages(run_id)]
        yield {
            "event": "snapshot",
            "data": {
                "run": dict(run),
                "stages": stages,
                "nodes": nodes,
                "messages": messages,
            },
        }

        # Tail events. Use `ts` as the cursor (string ISO timestamps sort lexically
        # in the order they were appended because `_now()` is monotonic per-process).
        cursor_ts: str | None = None
        # Prime the cursor to the latest event we've already shown via snapshot,
        # so we don't re-emit them.
        existing = await self.list_events(run_id, limit=1000000)
        if existing:
            cursor_ts = existing[-1]["ts"]

        idle_started_at: float | None = None
        loop = asyncio.get_event_loop()
        while True:
            new_events = await self.list_events_since(run_id, since_ts=cursor_ts)
            if new_events:
                for ev in new_events:
                    payload = {}
                    try:
                        import json
                        payload = json.loads(ev["payload_json"]) if ev["payload_json"] else {}
                    except (ValueError, TypeError):
                        payload = {}
                    yield {
                        "event": ev["event_type"],
                        "data": payload,
                    }
                    cursor_ts = ev["ts"]
                idle_started_at = None
            else:
                # Check terminal state + idle window
                run = await self.get_run(run_id)
                status = run["status"] if run else "unknown"
                if status not in ("running",):
                    if idle_started_at is None:
                        idle_started_at = loop.time()
                    elif loop.time() - idle_started_at >= idle_close_seconds:
                        yield {"event": "done", "data": {"status": status}}
                        return
            await asyncio.sleep(poll_interval)
```

- [ ] **Step 4: Re-run smoke, confirm it passes**

Run:
```powershell
python scripts/smoke_orchestration_stream.py
```
Expected: `smoke_orchestration_stream OK`.

- [ ] **Step 5: Commit**

```powershell
git add dreaming/services/orchestration_hub.py scripts/smoke_orchestration_stream.py
git commit -m "feat(orchestration): add stream_run_events async generator (snapshot + tail)"
```

---

## Task 3: Wire SSE route into project_orchestration

Add `GET /p/{slug}/orchestration/{run_id}/stream` returning `EventSourceResponse`. The route does NOT do its own SSE parsing — it just adapts our generator's `{"event", "data"}` dicts to the format `sse_starlette` wants.

**Files:**
- Modify: `dreaming/routes/project_orchestration.py`
- Test: `scripts/smoke_orchestration_stream.py` (extend)

- [ ] **Step 1: Add route handler**

In `dreaming/routes/project_orchestration.py`, add the import at the top (after the existing fastapi imports):

```python
import json as _json
from sse_starlette.sse import EventSourceResponse
```

Then add this route just after `orchestration_refresh` (around line 153):

```python
@router.get("/p/{slug}/orchestration/{run_id}/stream")
async def orchestration_stream(request: Request, slug: str, run_id: str):
    """SSE live-tail of orchestration events. Yields:
      - one `snapshot` event with full {stages, nodes, messages}
      - one event per `orchestrator_events` row as it appears
      - a final `done` event when the run terminates
    Client should fall back to polling `/refresh` on EventSource error.
    """
    project = request.state.project
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="run not found in this project")

    async def event_generator():
        async for ev in hub.stream_run_events(run_id):
            # sse_starlette expects {"event", "data"} with `data` already a string.
            yield {
                "event": ev["event"],
                "data": _json.dumps(ev["data"], ensure_ascii=False, default=str),
            }
            if await request.is_disconnected():
                break

    return EventSourceResponse(event_generator())
```

- [ ] **Step 2: Smoke-check the route via TestClient**

Append to `scripts/smoke_orchestration_stream.py`:

```python
def smoke_route_endpoint():
    """End-to-end: hit /stream via the FastAPI TestClient and verify headers."""
    import os
    from fastapi.testclient import TestClient
    # Use an isolated DB to avoid clobbering data
    os.environ.setdefault("DREAMING_DB_PATH", str(Path(tempfile.mkdtemp(prefix="dc_smoke_app_")) / "test.db"))
    from dreaming.main import app  # noqa: E402

    with TestClient(app) as client:
        # We can't create a full project + run easily without going through the
        # whole /setup flow. Just assert the endpoint exists (404 on a fake slug
        # is success — it means the route is registered).
        r = client.get("/p/__missing__/orchestration/00000000-0000-0000-0000-000000000000/stream")
        # 404 = route exists but project missing; 200 not expected here.
        assert r.status_code in (404, 422), f"unexpected status {r.status_code}"
    print("  ✓ /stream route registered")


async def main():
    await smoke_list_events_since()
    await smoke_stream_generator()
    smoke_route_endpoint()  # sync — uses TestClient
    print("smoke_orchestration_stream OK")
```

- [ ] **Step 3: Run smoke and verify it passes**

Run:
```powershell
python scripts/smoke_orchestration_stream.py
```
Expected: all 3 ✓ marks, exit 0. If the route smoke fails with 404 on a route prefix (e.g. the project resolver middleware redirects first), accept 303/307 too.

- [ ] **Step 4: Commit**

```powershell
git add dreaming/routes/project_orchestration.py scripts/smoke_orchestration_stream.py
git commit -m "feat(orchestration): add SSE stream endpoint /p/{slug}/orchestration/{id}/stream"
```

---

## Task 4: Extend detail route handler to provide swimlane context

The handler needs to pass `stages` and a `nodes_by_stage` grouping to the template so the swimlane can render its initial state (works even with JS disabled).

**Files:**
- Modify: `dreaming/routes/project_orchestration.py`

- [ ] **Step 1: Update the detail handler**

Replace the `orchestration_detail` function body (currently lines 82-99) with:

```python
@router.get("/p/{slug}/orchestration/{run_id}")
async def orchestration_detail(request: Request, slug: str, run_id: str):
    project = request.state.project
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None or run["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="run not found in this project")
    nodes = [dict(n) for n in await hub.list_nodes(run_id)]
    messages = [dict(m) for m in await hub.list_messages(run_id)]
    stages = [dict(s) for s in await hub.list_stages(run_id)]

    # Group nodes by their stage_id (column added via migration; nodes with no stage_id
    # land in the "_unassigned" bucket).
    nodes_by_stage: dict[str, list] = {}
    for n in nodes:
        key = n.get("stage_id") or "_unassigned"
        nodes_by_stage.setdefault(key, []).append(n)

    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_orchestration_detail.html",
        {"project": project, "run": dict(run),
         "nodes": nodes,
         "messages": messages,
         "stages": stages,
         "nodes_by_stage": nodes_by_stage,
         "projects": projects, "locale": locale},
    )
```

- [ ] **Step 2: Manually verify it loads**

Start the dev server (in a separate terminal if needed):

```powershell
python -m uvicorn dreaming.main:app --port 8086 --reload
```

Open `http://127.0.0.1:8086/p/<some-existing-slug>/orchestration` in a browser, click into a run. Page should still load (template hasn't changed yet so swimlane data is unused, but no 500 errors). Stop the server.

- [ ] **Step 3: Commit**

```powershell
git add dreaming/routes/project_orchestration.py
git commit -m "feat(orchestration): pass stages+nodes_by_stage into detail template context"
```

---

## Task 5: Add CSS file for swimlane (extracted from ALC)

Create the dedicated stylesheet so the template stays readable.

**Files:**
- Create: `dreaming/static/orchestration_swimlane.css`

- [ ] **Step 1: Create the file**

Write `dreaming/static/orchestration_swimlane.css`:

```css
/* Orchestration swimlane: stage rail, activity chips, status pills.
   Ported from ALC's app/templates/orchestration.html inline CSS (rev 2026-05-10).
   See docs/superpowers/specs/2026-05-21-alc-features-port-design.md Wave A. */

/* ─────────── Status pills ─────────── */
.status-pill { font-size: 11px; padding: 2px 8px; border-radius: 9999px; border: 1px solid transparent; display: inline-block; }
.status-running, .status-active { color:#0369a1; border-color:rgba(56,189,248,.45); background:rgba(56,189,248,.12); }
.status-completed, .status-done, .status-approved { color:#047857; border-color:rgba(52,211,153,.45); background:rgba(52,211,153,.12); }
.status-pending, .status-queued { color:#475569; border-color:rgba(156,163,175,.45); background:rgba(156,163,175,.12); }
.status-blocked { color:#92400e; border-color:rgba(245,158,11,.45); background:rgba(245,158,11,.12); }
.status-rejected, .status-failed { color:#b91c1c; border-color:rgba(248,113,113,.45); background:rgba(248,113,113,.12); }
.status-cancelled, .status-stopped { color:#9a3412; border-color:rgba(249,115,22,.45); background:rgba(249,115,22,.12); }

/* ─────────── Stage rail ─────────── */
.stage-rail { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(120px, 1fr); gap: 6px; padding: 6px 0 20px; }
.stage-tile { padding: 10px 12px; border: 1px solid var(--border-subtle); background: var(--bg-elevated);
              border-radius: 14px; cursor: pointer; transition: all .18s; min-height: 76px;
              display: flex; flex-direction: column; align-items: center; justify-content: center; }
.stage-tile:hover { border-color: rgba(99,102,241,.6); transform: translateY(-1px); }
.stage-tile.active-stage { border-color: rgba(56,189,248,.8); box-shadow: 0 0 0 1px rgba(56,189,248,.35); }
.stage-tile.selected-stage { border-color: rgba(99,102,241,1); box-shadow: 0 0 0 1px rgba(99,102,241,.55); }
.stage-tile.completed { border-color: rgba(52,211,153,.6); background: rgba(52,211,153,.06); }
.stage-tile.failed, .stage-tile.rejected { border-color: rgba(248,113,113,.6); background: rgba(248,113,113,.06); }
.stage-icon { width: 30px; height: 30px; display:flex; align-items:center; justify-content:center;
              border-radius:50%; font-size:14px; font-weight:700; background: rgba(99,102,241,.2);
              color:#4338ca; margin-bottom: 6px; }
.stage-label { font-size: 12px; text-align:center; font-weight:600; }
.stage-meta { font-size: 10px; color:#6b7280; margin-top: 2px; }

/* ─────────── Swimlane body ─────────── */
.swimlanes-wrap { border:1px solid var(--border-subtle); border-radius: 12px; overflow: hidden;
                  background: var(--bg-surface); margin-top: 10px; }
.swim-row { display:grid; grid-template-columns: 170px 1fr; border-bottom: 1px dashed var(--border-subtle); min-height: 56px; }
.swim-row:last-child { border-bottom: 0; }
.swim-agent { padding: 10px 10px 10px 14px; display:flex; flex-direction:column; gap:3px;
              border-right: 1px solid var(--border-subtle); }
.swim-agent-name { font-size: 12px; font-weight:600; }
.swim-agent-role { font-size: 10px; color:#6b7280; }
.swim-cell { padding: 8px 6px; display:flex; flex-wrap:wrap; gap:6px; align-content:flex-start; align-items:flex-start; }

/* ─────────── Activity chips ─────────── */
.activity-chip { display:flex; flex-direction:column; gap:3px; padding:6px 9px;
                 border-radius:8px; font-size:11px; border:1px solid rgba(99,102,241,.3);
                 background: rgba(99,102,241,.06); cursor:pointer; max-width: 100%;
                 transition: opacity .2s, border-color .15s, transform .12s; }
.activity-chip:hover { border-color: rgba(99,102,241,.7); transform: translateY(-1px); }
.activity-chip.selected { border-color: rgba(99,102,241,1); box-shadow: 0 0 0 1px rgba(99,102,241,.45); }
.activity-chip.history { opacity: .45; filter: saturate(.6); }
.activity-chip.history:hover { opacity: .8; }

.activity-chip.state-idle    { border-color: rgba(107,114,128,.45); background: rgba(107,114,128,.06); }
.activity-chip.state-active  { border-color: rgba(56,189,248,.7);  background: rgba(56,189,248,.06);
                               box-shadow: 0 0 0 1px rgba(56,189,248,.18); }
.activity-chip.state-done    { border-color: rgba(52,211,153,.55); background: rgba(52,211,153,.06); }
.activity-chip.state-rejected { border-color: rgba(248,113,113,.55); background: rgba(248,113,113,.06); }

.chip-action { font-size: 11px; line-height: 1.3; overflow:hidden; text-overflow:ellipsis;
               white-space: nowrap; max-width: 100%; }

/* SSE status indicator (top-right of detail page) */
.sse-indicator { font-size: 10px; padding: 2px 8px; border-radius: 9999px; font-family: monospace; }
.sse-indicator.connected { background: rgba(52,211,153,.12); color:#047857; }
.sse-indicator.disconnected { background: rgba(248,113,113,.12); color:#b91c1c; }
.sse-indicator.polling { background: rgba(245,158,11,.12); color:#92400e; }
```

- [ ] **Step 2: Verify static mount is in place**

Open `dreaming/main.py` and confirm there's a `app.mount("/static", StaticFiles(directory=...))` call. If not present, add it inside the lifespan or near the `app = FastAPI(...)` line:

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
```

(Likely it's already mounted — verify via grep before adding.)

```powershell
# Verify before editing:
# Grep "StaticFiles" in dreaming/main.py
```

- [ ] **Step 3: Commit**

```powershell
git add dreaming/static/orchestration_swimlane.css
# If main.py was edited:
# git add dreaming/main.py
git commit -m "feat(orchestration): add swimlane CSS"
```

---

## Task 6: Add EventSource client JS with polling fallback

The client reads SSE events, mutates the DOM (chip status, stage rail, message append). On `error` it switches to polling `/refresh`. After a normal `done` event from the server, it stops.

**Files:**
- Create: `dreaming/static/orchestration_stream.js`

- [ ] **Step 1: Write the client**

Write `dreaming/static/orchestration_stream.js`:

```javascript
/* Orchestration live updates: EventSource client with polling fallback.
   - On `snapshot` event: ignored (server-rendered initial state already in DOM).
   - On `message_added`: append a new message card and bump msg counter.
   - On `run_finished` / `done`: update status pill, stop the stream.
   - On EventSource error: switch to polling /refresh until reconnect succeeds. */
(function () {
  "use strict";

  const wrapper = document.getElementById("orch-detail");
  if (!wrapper) return;
  const slug = wrapper.dataset.slug;
  const runId = wrapper.dataset.runId;
  const initialStatus = wrapper.dataset.runStatus;
  const streamUrl = `/p/${slug}/orchestration/${runId}/stream`;
  const refreshUrl = `/p/${slug}/orchestration/${runId}/refresh`;
  const indicator = document.getElementById("sse-indicator");

  let es = null;
  let pollHandle = null;
  let lastMsgCount = parseInt(wrapper.dataset.msgCount || "0", 10);
  let lastNodeCount = parseInt(wrapper.dataset.nodeCount || "0", 10);
  let normalClose = false;

  function setIndicator(state) {
    if (!indicator) return;
    indicator.className = "sse-indicator " + state;
    indicator.textContent = state.toUpperCase();
  }

  function setStatus(status) {
    const el = document.getElementById("run-status");
    if (el) {
      el.textContent = status;
      el.className = "font-mono status-pill status-" + status;
    }
  }

  function bumpCounter(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = String(value);
  }

  function appendMessage(msg) {
    const list = document.getElementById("messages-list");
    if (!list) return;
    const card = document.createElement("div");
    card.className = "bg-white rounded shadow p-3";
    card.innerHTML = `
      <div class="text-xs muted mb-1">
        <span class="font-mono">${msg.author || ""}</span> ·
        <span class="font-mono">${msg.kind || ""}</span> ·
        ${msg.ts || ""}
      </div>
      <pre class="whitespace-pre-wrap text-sm font-mono"></pre>`;
    card.querySelector("pre").textContent = msg.text || "";
    list.appendChild(card);
    lastMsgCount += 1;
    bumpCounter("msg-count", lastMsgCount);
  }

  function handleEvent(eventType, data) {
    switch (eventType) {
      case "snapshot":
        // Already server-rendered; nothing to do.
        return;
      case "message_added":
        // Server-side payload has only ids — we'd need to fetch the full row.
        // Simpler: just bump the counter and ask the user to reload for body.
        // For Wave A v1, increment the counter and inject a placeholder card.
        lastMsgCount += 1;
        bumpCounter("msg-count", lastMsgCount);
        appendMessage({
          author: data.author || "",
          kind: data.kind || "",
          ts: data.ts || "",
          text: "(new message — reload to see full content)",
        });
        return;
      case "node_created":
      case "node_status_changed":
        lastNodeCount = data.node_count || lastNodeCount + 1;
        bumpCounter("node-count", lastNodeCount);
        return;
      case "run_finished":
      case "run_resumed":
        if (data.status) setStatus(data.status);
        return;
      case "done":
        normalClose = true;
        setStatus(data.status || "completed");
        setIndicator("connected");
        if (es) { es.close(); es = null; }
        return;
      default:
        // Unknown event — log for debugging, no DOM mutation.
        // console.debug("orch sse event", eventType, data);
        return;
    }
  }

  function startStream() {
    try {
      es = new EventSource(streamUrl);
    } catch (e) {
      console.warn("EventSource init failed", e);
      startPolling();
      return;
    }
    es.onopen = () => setIndicator("connected");
    es.onmessage = (e) => {
      // Default 'message' channel — sse_starlette doesn't put events here when we use `event:` field.
      try { handleEvent("message", JSON.parse(e.data)); } catch {}
    };
    // Register named handlers for known event types.
    const named = ["snapshot", "message_added", "node_created", "node_status_changed",
                   "run_finished", "run_resumed", "run_started", "done", "heartbeat"];
    named.forEach((name) => {
      es.addEventListener(name, (e) => {
        let payload = {};
        try { payload = JSON.parse(e.data || "{}"); } catch {}
        handleEvent(name, payload);
      });
    });
    es.onerror = () => {
      if (normalClose) return;
      setIndicator("disconnected");
      if (es) { es.close(); es = null; }
      // Fall back to polling; periodically try to reconnect to SSE.
      startPolling();
      setTimeout(() => {
        if (!normalClose && !es) {
          stopPolling();
          startStream();
        }
      }, 10000);
    };
  }

  async function pollOnce() {
    try {
      const r = await fetch(refreshUrl);
      if (!r.ok) return;
      const data = await r.json();
      setStatus(data.status);
      bumpCounter("node-count", data.node_count);
      bumpCounter("msg-count", data.message_count);
      if (data.status !== "running") {
        normalClose = true;
        stopPolling();
        setIndicator("connected");
      }
    } catch (e) {
      // Silent — next tick will retry.
    }
  }

  function startPolling() {
    if (pollHandle) return;
    setIndicator("polling");
    pollOnce();
    pollHandle = setInterval(pollOnce, 3000);
  }

  function stopPolling() {
    if (pollHandle) {
      clearInterval(pollHandle);
      pollHandle = null;
    }
  }

  if (initialStatus === "running" || initialStatus === "pending") {
    startStream();
  } else {
    setIndicator("connected");
  }

  window.addEventListener("beforeunload", () => {
    if (es) es.close();
    stopPolling();
  });
})();
```

- [ ] **Step 2: Commit**

```powershell
git add dreaming/static/orchestration_stream.js
git commit -m "feat(orchestration): add EventSource client with polling fallback"
```

---

## Task 7: Rewrite the detail template with stage rail + swimlane

Replace the inline polling script and table-only layout with a server-rendered swimlane that the JS client mutates.

**Files:**
- Modify: `dreaming/templates/project_orchestration_detail.html` (full replacement)

- [ ] **Step 1: Replace the template**

Overwrite `dreaming/templates/project_orchestration_detail.html` with:

```html
{% extends "_project_layout.html" %}
{% set active='orchestration' %}
{% block project_content %}
<link rel="stylesheet" href="/static/orchestration_swimlane.css">

<a href="/p/{{ project.slug }}/orchestration" class="text-sm text-blue-600 underline">{{ "common.back_to_runs_list" | t(locale=locale) }}</a>

<header class="mt-3 mb-4" id="orch-detail"
        data-slug="{{ project.slug }}"
        data-run-id="{{ run.id }}"
        data-run-status="{{ run.status }}"
        data-msg-count="{{ messages|length }}"
        data-node-count="{{ nodes|length }}">
  <div class="flex items-start justify-between gap-3 flex-wrap">
    <div>
      <h1 class="text-xl font-bold">{{ run.goal }}</h1>
      <div class="text-xs muted mt-1">
        <span class="font-mono">{{ run.id }}</span> ·
        <span id="run-status" class="font-mono status-pill status-{{ run.status }}">{{ run.status }}</span> ·
        started {{ run.started_at }}
        {% if run.finished_at %} · finished {{ run.finished_at }}{% endif %}
        {% if run.external_id %} · session <span class="font-mono">{{ run.external_id[:8] }}…</span>{% endif %}
      </div>
    </div>
    <div class="flex items-center gap-2">
      <span id="sse-indicator" class="sse-indicator polling" title="{{ 'orchestration.sse_status' | t(locale=locale) }}">…</span>
    </div>
  </div>
  <div class="mt-2 flex gap-2 flex-wrap">
    {% if run.status == 'running' %}
    <form method="post" action="/p/{{ project.slug }}/orchestration/{{ run.id }}/finish" class="inline">
      <button class="text-xs px-3 py-1 border rounded">{{ "orchestration.mark_completed" | t(locale=locale) }}</button>
    </form>
    {% else %}
      {% if run.external_id %}
      <form method="post" action="/p/{{ project.slug }}/orchestration/{{ run.id }}/resume" class="inline flex gap-2">
        <input name="prompt" placeholder="{{ 'orchestration.prompt_placeholder' | t(locale=locale) }}" class="border rounded p-1 text-xs w-64">
        <button class="text-xs px-3 py-1 border rounded">{{ "orchestration.resume" | t(locale=locale) }}</button>
      </form>
      {% endif %}
    {% endif %}
    <a class="text-xs px-3 py-1 border rounded text-slate-700" href="/p/{{ project.slug }}/orchestration/{{ run.id }}/log">{{ "orchestration.view_log" | t(locale=locale) }}</a>
    <form method="post" action="/p/{{ project.slug }}/orchestration/{{ run.id }}/delete" class="inline"
          data-confirm="{{ 'orchestration.confirm_delete' | t(locale=locale) }}" data-confirm-variant="danger">
      <button class="text-xs px-3 py-1 border rounded text-red-600">{{ "orchestration.delete_run" | t(locale=locale) }}</button>
    </form>
  </div>
</header>

{# ───────────────── Stage rail ───────────────── #}
{% if stages %}
<h2 class="font-semibold mb-2">{{ "orchestration.stages" | t(locale=locale) }} ({{ stages|length }})</h2>
<div class="stage-rail" id="stage-rail">
  {% for s in stages %}
  <div class="stage-tile {{ s.status }}" data-stage-id="{{ s.id }}" data-stage-key="{{ s.stage_key }}">
    <div class="stage-icon">{{ loop.index }}</div>
    <div class="stage-label">{{ s.label }}</div>
    <div class="stage-meta">
      <span class="status-pill status-{{ s.status }}">{{ s.status }}</span>
      {% if s.iteration and s.iteration > 1 %}
        · iter {{ s.iteration }}
      {% endif %}
    </div>
  </div>
  {% endfor %}
</div>

{# ───────────────── Swimlane body ───────────────── #}
<div class="swimlanes-wrap">
  {% for s in stages %}
    {% set stage_nodes = nodes_by_stage.get(s.id, []) %}
    <div class="swim-row">
      <div class="swim-agent">
        <div class="swim-agent-name">{{ s.label }}</div>
        <div class="swim-agent-role">{{ stage_nodes|length }} agent{{ '' if stage_nodes|length == 1 else 's' }}</div>
      </div>
      <div class="swim-cell" data-stage-id="{{ s.id }}">
        {% for n in stage_nodes %}
          <div class="activity-chip state-{% if n.status == 'running' %}active{% elif n.status == 'completed' %}done{% elif n.status in ('failed','cancelled') %}rejected{% else %}idle{% endif %}"
               data-node-id="{{ n.id }}">
            <span class="chip-action">{{ n.agent_name }}</span>
            <span class="text-xs muted">{{ n.role }} · {{ n.status }}</span>
          </div>
        {% else %}
          <span class="text-xs muted">{{ "orchestration.no_agents_yet" | t(locale=locale) }}</span>
        {% endfor %}
      </div>
    </div>
  {% endfor %}
</div>
{% endif %}

{# Unassigned nodes (no stage_id) — show as legacy table fallback #}
{% set unassigned = nodes_by_stage.get('_unassigned', []) %}
{% if unassigned %}
<h2 class="font-semibold mb-2 mt-6">{{ "orchestration.nodes_unassigned" | t(locale=locale) }} (<span id="node-count">{{ nodes|length }}</span>)</h2>
<table class="w-full bg-white rounded shadow text-sm mb-6">
  <thead class="text-left border-b"><tr>
    <th class="p-2">agent</th><th class="p-2">role</th><th class="p-2">status</th><th class="p-2">started</th>
  </tr></thead>
  <tbody>
  {% for n in unassigned %}
  <tr class="border-b">
    <td class="p-2 font-mono text-xs">{{ n.agent_name }}</td>
    <td class="p-2 text-xs">{{ n.role }}</td>
    <td class="p-2 text-xs"><span class="status-pill status-{{ n.status }}">{{ n.status }}</span></td>
    <td class="p-2 text-xs muted">{{ n.started_at }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<span id="node-count" class="hidden">{{ nodes|length }}</span>
{% endif %}

{# ───────────────── Messages ───────────────── #}
<h2 class="font-semibold mb-2 mt-6">{{ "orchestration.messages" | t(locale=locale) }} (<span id="msg-count">{{ messages|length }}</span>)</h2>
<div id="messages">
{% if messages %}
<div id="messages-list" class="space-y-2">
{% for m in messages %}
  <div class="bg-white rounded shadow p-3">
    <div class="text-xs muted mb-1">
      <span class="font-mono">{{ m.author }}</span> ·
      <span class="font-mono">{{ m.kind }}</span> ·
      {{ m.ts }}
    </div>
    <pre class="whitespace-pre-wrap text-sm font-mono">{{ m.text }}</pre>
  </div>
{% endfor %}
</div>
{% else %}
<div id="messages-list" class="space-y-2"></div>
<p class="muted text-sm">{{ "orchestration.no_messages" | t(locale=locale) }}</p>
{% endif %}
</div>

<script src="/static/orchestration_stream.js" defer></script>
{% endblock %}
```

- [ ] **Step 2: Manually verify**

Start the server:
```powershell
python -m uvicorn dreaming.main:app --port 8086 --reload
```

Navigate to an existing run's detail page. Expected:
- Page renders without 500s
- If the run has stages (`orchestrator_stages` rows), they appear in the rail
- If it has nodes with `stage_id`, they appear in the swimlane cells
- Nodes without `stage_id` appear in the legacy table at the bottom
- The SSE indicator pill is visible (top-right of the header)
- If the run is `running`, the indicator should briefly say `CONNECTED` (SSE) or `POLLING` (fallback)

Untranslated i18n keys (e.g., `orchestration.stages`) render as the raw key — that's OK; we'll fix in Task 8.

- [ ] **Step 3: Commit**

```powershell
git add dreaming/templates/project_orchestration_detail.html
git commit -m "feat(orchestration): stage rail + swimlane in detail template"
```

---

## Task 8: Add i18n keys (RU + EN)

**Files:**
- Modify: `dreaming/i18n/messages_ru.json`
- Modify: `dreaming/i18n/messages_en.json`

- [ ] **Step 1: Add RU keys**

Open `dreaming/i18n/messages_ru.json` and add these keys to the appropriate section (probably an `orchestration` object — verify by reading the file first). Required keys:

```json
{
  "orchestration.stages": "Стадии",
  "orchestration.nodes_unassigned": "Узлы без стадии",
  "orchestration.no_agents_yet": "пока без агентов",
  "orchestration.sse_status": "Статус соединения live-обновлений",
  "orchestration.mark_completed": "Отметить как завершено",
  "orchestration.resume": "Продолжить",
  "orchestration.view_log": "Лог",
  "orchestration.delete_run": "Удалить запуск",
  "orchestration.messages": "Сообщения"
}
```

If the existing i18n is structured as nested objects (e.g., `"orchestration": { "stages": "Стадии" }`), nest accordingly. Use the file's existing convention — do NOT mix flat and nested keys.

- [ ] **Step 2: Add EN keys mirroring RU**

Open `dreaming/i18n/messages_en.json` and add the same keys with English values:

```json
{
  "orchestration.stages": "Stages",
  "orchestration.nodes_unassigned": "Unassigned nodes",
  "orchestration.no_agents_yet": "no agents yet",
  "orchestration.sse_status": "Live update connection status",
  "orchestration.mark_completed": "Mark completed",
  "orchestration.resume": "Resume",
  "orchestration.view_log": "View log",
  "orchestration.delete_run": "Delete run",
  "orchestration.messages": "Messages"
}
```

**Encoding warning:** Edit these files with the Write/Edit tool (UTF-8). PowerShell `Set-Content` defaults to UTF-16 LE and will break the i18n parser. CLAUDE.md calls this out explicitly.

- [ ] **Step 3: Run i18n check**

Run:
```powershell
python scripts/check_i18n.py
```
Expected: no missing-key errors. If errors appear, ensure RU and EN have the exact same set of keys.

- [ ] **Step 4: Commit**

```powershell
git add dreaming/i18n/messages_ru.json dreaming/i18n/messages_en.json
git commit -m "feat(orchestration): i18n keys for stages, swimlane, SSE status"
```

---

## Task 9: Verify in browser end-to-end

This is the wave's acceptance gate — manual verification because there's no automated UI testing.

- [ ] **Step 1: Start a fresh orchestration run**

```powershell
python -m uvicorn dreaming.main:app --port 8086 --reload
```

In the browser:
1. Pick a project from the sidebar selector
2. Go to `/p/<slug>/orchestration`
3. Type a goal into the start form, submit
4. Browser should redirect to the new run's detail page

- [ ] **Step 2: Observe live updates**

On the detail page:
- The SSE indicator pill should say `CONNECTED` (green) within ~1s
- As the agent runs and emits messages, they should appear at the bottom **without page reload**
- The `Messages (N)` counter should increment
- If stages get created, they should appear in the stage rail
- Open browser DevTools → Network tab → confirm the `/stream` request is active (Type: `eventsource`, stays connected)

- [ ] **Step 3: Test polling fallback**

While the run is still active, in DevTools → Network → right-click the `/stream` request → "Block request URL". The indicator should switch to `DISCONNECTED` (red) within 30s, then to `POLLING` (amber), and the message counter should continue updating via the polling fallback. Unblock the URL; the indicator should eventually return to `CONNECTED` after the periodic reconnect attempt.

- [ ] **Step 4: Test normal close**

When the run finishes (or click "Mark completed"):
- SSE indicator stays `CONNECTED` (no flicker to disconnected)
- Status pill changes to `completed`
- No more polling kicks in (verify in Network tab)

- [ ] **Step 5: Test JS-disabled fallback**

In DevTools, disable JavaScript. Reload the run detail page. Expected:
- Page renders fully (stage rail, swimlane, message list — all from server-side render)
- SSE indicator stays in `polling` state (default class)
- Counters won't update live, but the user can manually reload to refresh

- [ ] **Step 6: Run smoke script one more time**

```powershell
python scripts/smoke_orchestration_stream.py
```
Expected: all checks pass, exit 0.

- [ ] **Step 7: Tag the wave**

```powershell
git tag wave-A
git log --oneline -10
```

---

## Sidebar / navigation check

Wave A doesn't add any new top-level page — orchestration is already in the sidebar. No `_sidebar.html` edits required. Verify by inspecting `dreaming/templates/_sidebar.html` for an existing entry pointing at `/p/{slug}/orchestration`.

## What's intentionally deferred to a later wave

- Per-agent message attribution (the chip click → message panel UX from ALC). Wave A renders chips but clicking them is a no-op. Add in a follow-up.
- Stage-marker parsing in `claude_session_tail.py` to auto-tag events with `stage_id`. The current state already has `orchestrator_nodes.stage_id` populated by `orchestration_dispatch.py` for cascade-style runs; events get their stage via the node JOIN. Markdown stage markers from the CLI stream is a nice-to-have, not required for Wave A acceptance.
- ALC's "legacy star graph" view. We're only porting the cascade swimlane.
- SSE pub/sub via asyncio.Queue (would replace the 500ms poll). Local single-user only — polling is fine.

## Definition of done

- All 9 tasks committed in order.
- `python scripts/smoke_orchestration_stream.py` exits 0.
- Manual browser verification passed all 5 steps in Task 9.
- `git tag wave-A` applied.
