"""Smoke: one server per database, and no sweeping a neighbour's live run.

Covers the two halves of the 2026-09-01 fix:

  * `orchestrator_runs.owner_instance` + an owner-aware
    `cancel_stale_orchestration_runs`, so a second instance stops failing
    runs that another live instance is still driving.
  * `find_conflicting_instance`, so the second instance never starts.

Run manually:  python scripts/smoke_instance_ownership.py
"""
from __future__ import annotations
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.db import SqliteDB              # noqa: E402
from dreaming.services.orchestration_hub import OrchestrationHub  # noqa: E402

DEAD_PID = 999_999   # high enough to be free on every OS we run on
failures: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}: got={got!r} want={want!r}")
    if not ok:
        failures.append(label)


async def backdate(db: SqliteDB, run_id: str, minutes: int) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    await db.execute(
        "UPDATE orchestrator_runs SET started_at=? WHERE id=?", (ts, run_id))


async def status_of(db: SqliteDB, run_id: str) -> str:
    row = await db.fetch_one(
        "SELECT status FROM orchestrator_runs WHERE id=?", (run_id,))
    return row["status"]


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dc-smoke-inst-")) / "dreaming.db"

    # Two handles on one file: 'a' owns the work, 'b' is the second server.
    a = SqliteDB(str(tmp))
    await a.connect()
    b = SqliteDB(str(tmp))
    await b.connect()

    # --- migration landed
    cols = {r[1] for r in await (await a._conn.execute(
        "PRAGMA table_info(orchestrator_runs)")).fetchall()}
    check("orchestrator_runs has owner_instance", "owner_instance" in cols, True)

    await a.register_instance("inst-a", pid=os.getpid(), port=8086)
    await b.register_instance("inst-b", pid=os.getpid(), port=8087)
    await a.execute(
        "INSERT INTO projects (id, slug, label, working_dir, enabled, "
        " created_at, updated_at) VALUES (1, 'p', 'P', '.', 1, ?, ?)",
        (datetime.now(timezone.utc).isoformat(),
         datetime.now(timezone.utc).isoformat()))

    hub_a = OrchestrationHub(a, None)
    hub_b = OrchestrationHub(b, None)

    # --- a run records who started it
    owned = await hub_a.create_run(1, "owned by a")
    row = await a.fetch_one(
        "SELECT owner_instance FROM orchestrator_runs WHERE id=?", (owned,))
    check("create_run stamps the owner", row["owner_instance"], "inst-a")

    # --- b must not sweep a's live run, however old it is
    await backdate(a, owned, 30)
    closed = await b.cancel_stale_orchestration_runs(set())
    check("b closes nothing while a is live", closed, 0)
    check("a's run still running", await status_of(a, owned), "running")

    # --- an ownerless run is swept exactly as before the column existed
    orphan = await hub_b.create_run(1, "ownerless")
    await b.execute(
        "UPDATE orchestrator_runs SET owner_instance='' WHERE id=?", (orphan,))
    await backdate(b, orphan, 30)
    check("ownerless run is swept", await b.cancel_stale_orchestration_runs(set()), 1)
    check("ownerless run failed", await status_of(b, orphan), "failed")

    # --- b's own live process is still protected by the session set
    mine = await hub_b.create_run(1, "b's own", external_id="sess-b")
    await backdate(b, mine, 30)
    check("own run with a live process survives",
          await b.cancel_stale_orchestration_runs({"sess-b"}), 0)
    check("own run with a dead process is swept",
          await b.cancel_stale_orchestration_runs(set()), 1)

    # --- once a is gone, its run becomes sweepable again
    await a.unregister_instance()
    check("a's run swept after a leaves",
          await b.cancel_stale_orchestration_runs(set()), 1)
    check("a's run failed", await status_of(b, owned), "failed")

    # --- startup guard
    fresh = SqliteDB(str(tmp))
    await fresh.connect()
    conflict = await fresh.find_conflicting_instance()
    check("live sibling blocks startup",
          conflict is not None and conflict["id"], "inst-b")

    await b.unregister_instance()
    check("no siblings, no conflict", await fresh.find_conflicting_instance(), None)

    # a hard-killed server must not lock the next start out
    now = datetime.now(timezone.utc).isoformat()
    await fresh.execute(
        "INSERT INTO app_instances (id, pid, port, started_at, last_seen) "
        "VALUES ('inst-dead', ?, 8086, ?, ?)", (DEAD_PID, now, now))
    check("dead pid with a fresh heartbeat does not block",
          await fresh.find_conflicting_instance(), None)
    left = await fresh.fetch_one(
        "SELECT COUNT(*) AS n FROM app_instances WHERE id='inst-dead'")
    check("dead row is pruned", left["n"], 0)

    for h in (a, b, fresh):
        await h.close()
    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
