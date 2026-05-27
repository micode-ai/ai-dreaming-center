"""Smoke: skills/agents breakdown — ingest a fixture session tree, verify
agent_name stamping, skill invocation recording, the stats aggregators, and
backfill idempotency. Function-level (no server needed)."""
import asyncio
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService
from dreaming.services.ai_usage_parser import (
    ingest_ai_usage,
    backfill_skill_agent_stats,
)
from dreaming.services import ai_usage_stats as stats


def _line(**kw) -> str:
    return json.dumps(kw)


async def run() -> int:
    tmp = Path(tempfile.mkdtemp())
    workdir = tmp / "proj"
    workdir.mkdir()
    cwd = str(workdir)

    root = tmp / "claude_projects"
    slug_dir = root / "proj-slug"
    slug_dir.mkdir(parents=True)
    sess = "session-uuid-1"

    main = slug_dir / f"{sess}.jsonl"
    main.write_text("\n".join([
        _line(type="assistant", timestamp="2026-05-27T10:00:00Z", sessionId=sess,
              cwd=cwd, isSidechain=False,
              message={"id": "m1", "model": "claude-opus-4-7",
                       "usage": {"input_tokens": 100, "output_tokens": 50},
                       "content": [{"type": "tool_use", "name": "Skill",
                                    "input": {"skill": "brainstorming"}}]}),
        _line(type="assistant", timestamp="2026-05-27T10:01:00Z", sessionId=sess,
              cwd=cwd, isSidechain=False,
              message={"id": "m2", "model": "claude-opus-4-7",
                       "usage": {"input_tokens": 200, "output_tokens": 20},
                       "content": [{"type": "text", "text": "hi"}]}),
    ]) + "\n", encoding="utf-8")

    sub = slug_dir / sess / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-abc.meta.json").write_text(
        json.dumps({"agentType": "Explore", "description": "d"}), encoding="utf-8")
    (sub / "agent-abc.jsonl").write_text(
        _line(type="assistant", timestamp="2026-05-27T10:02:00Z", sessionId=sess,
              cwd=cwd, isSidechain=True,
              message={"id": "m3", "model": "claude-opus-4-7",
                       "usage": {"input_tokens": 300, "output_tokens": 30},
                       "content": [{"type": "text", "text": "sub"}]}) + "\n",
        encoding="utf-8")

    db = SqliteDB(str(tmp / "t.db"))
    await db.connect()
    now = dt.datetime.utcnow().isoformat()
    await db.execute(
        "INSERT INTO projects (slug,label,working_dir,created_at,updated_at) "
        "VALUES (?,?,?,?,?)",
        ("proj-slug", "Proj", cwd, now, now),
    )
    projects = ProjectsService(db)

    res = await ingest_ai_usage(db, projects, claude_projects_dir=str(root))
    print("ingest:", res)
    assert res["skills_inserted"] == 1, res

    sk = await stats._by_skill(db, start="2026-05-01", end="2026-05-31")
    assert any(r["skill_name"] == "brainstorming" and r["calls"] == 1 for r in sk), sk

    ag = await stats._by_agent(db, start="2026-05-01", end="2026-05-31")
    assert any(r["agent_name"] == "Explore" and r["total_tokens"] == 330
               and r["runs"] == 1 for r in ag), ag

    summ = await stats.project_summary(db, 1, preset="all")
    assert "by_skill" in summ and "by_agent" in summ, list(summ)

    bf = await backfill_skill_agent_stats(db, projects, claude_projects_dir=str(root))
    print("backfill:", bf)
    sk2 = await stats._by_skill(db, start="2026-05-01", end="2026-05-31")
    assert sk2 == sk, (sk, sk2)

    print("OK smoke_skill_agent_stats")
    await db.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
