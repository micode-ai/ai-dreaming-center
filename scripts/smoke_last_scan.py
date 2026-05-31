"""Smoke: db.get_last_command_session returns the most-recent scan row, or None."""
from __future__ import annotations
import asyncio, sys, tempfile, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dreaming.services.db import SqliteDB


async def amain() -> int:
    tmp = tempfile.mkdtemp()
    db = SqliteDB(os.path.join(tmp, "t.db"))
    await db.connect()
    # agent_learning_sessions.project_id has an FK to projects(id) and connect()
    # turns foreign_keys ON — disable it for this isolated helper test so we can
    # insert sessions without first seeding a projects row.
    await db.execute("PRAGMA foreign_keys=OFF")
    pid = 1
    agent = "cmd:acct:tech-debt-scan"
    assert await db.get_last_command_session(pid, agent) is None, "expected None when no rows"
    s1 = await db.create_session(pid, agent, "sonnet")
    s2 = await db.create_session(pid, agent, "sonnet")
    row = await db.get_last_command_session(pid, agent)
    assert row is not None, "expected a row"
    assert row["status"] == "running", f"unexpected status {row['status']!r}"
    assert "started_at" in row and "finished_at" in row, "missing columns"
    assert await db.get_last_command_session(pid, "cmd:acct:product-idea-scan") is None
    print("OK get_last_command_session")
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
