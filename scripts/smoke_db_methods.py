"""Smoke check Wave 1 DB methods."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService


async def main() -> int:
    db = SqliteDB("data/dreaming.db")
    await db.connect()
    try:
        svc = ProjectsService(db)
        proj = await svc.get_by_slug("test")
        if not proj:
            proj = await svc.create(slug="test", label="Test", working_dir=r"D:\Work\micode\mi-code-ai")

        sid = await db.create_session(proj.id, "smoke-agent", "sonnet")
        ok = await db.finish_session(sid, status="success", topic="t", confidence=0.5)
        assert ok
        rows = await db.list_sessions(proj.id, limit=5)
        assert any(r["id"] == sid for r in rows), "session not in list"

        stats = await db.week_stats(proj.id)
        print("week_stats:", stats)
        assert stats.get("success", 0) >= 1

        await db.upsert_agent_rotation(proj.id, "smoke-agent", tier=2)
        await db.set_agent_tier(proj.id, "smoke-agent", 1)
        await db.set_agent_enabled(proj.id, "smoke-agent", False)
        rotation = await db.list_rotation(proj.id)
        smoke_row = next((r for r in rotation if r["agent_name"] == "smoke-agent"), None)
        assert smoke_row, "smoke-agent missing from rotation"
        assert smoke_row["tier"] == 1
        assert smoke_row["enabled"] == 0
        await db.set_agent_enabled(proj.id, "smoke-agent", True)
        next_agents = await db.next_agents_for_nightly(proj.id, 5)
        assert any(r["agent_name"] == "smoke-agent" for r in next_agents)

        # Idempotent reuse
        sid2 = await db.get_or_create_session(proj.id, "smoke-agent", "sonnet")
        rows = await db.fetch_all(
            "SELECT id FROM agent_learning_sessions WHERE project_id=? AND agent_name=?",
            (proj.id, "smoke-agent"),
        )
        # We just finished one and created another; both exist.
        assert sid in [r["id"] for r in rows]

        print("ok")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
