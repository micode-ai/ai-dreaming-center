"""Smoke check for per-node skill invocation tracking (pipeline badges).

Exercises the tail's skill detection (`_ingest_line` → `orchestrator_node_skills`)
and the route helper that feeds swimlane badges. Run with:

    python scripts/smoke_node_skills.py

Exits 0 on success, non-zero on failure. Prints a short summary line.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Make the package importable when run from repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dreaming.services.db import SqliteDB
from dreaming.services.orchestration_hub import OrchestrationHub
from dreaming.services.claude_session_tail import _ingest_line, _extract_skill_names


async def _setup():
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_skills_")) / "test.db"
    db = SqliteDB(str(tmp))
    await db.connect()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO projects (id, slug, label, working_dir, enabled, is_default, sort_order, color, created_at, updated_at) "
        "VALUES (1, 'smoke', 'Smoke', ?, 1, 0, 0, NULL, ?, ?)",
        (str(tmp.parent), now, now),
    )
    hub = OrchestrationHub(db, projects=None)
    return db, hub


def _assistant_line(uuid_: str, skills: list[str], *, with_text: bool = True) -> str:
    content: list[dict] = [
        {"type": "tool_use", "name": "Skill", "input": {"skill": s}} for s in skills
    ]
    if with_text:
        content.append({"type": "text", "text": "working"})
    return json.dumps({
        "type": "assistant",
        "uuid": uuid_,
        "timestamp": "2026-05-27T10:00:00Z",
        "message": {"id": "m_" + uuid_, "content": content},
    })


def smoke_extract():
    msg = {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": "tdd"}},
        {"type": "tool_use", "name": "Skill", "input": {"skill": "tdd"}},      # dup in turn
        {"type": "tool_use", "name": "Skill", "input": {"skill": "debugging"}},
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},      # not a skill
        {"type": "text", "text": "hi"},
    ]}
    names = _extract_skill_names(msg)
    assert names == ["tdd", "debugging"], f"expected [tdd, debugging], got {names}"
    assert _extract_skill_names({}) == []
    assert _extract_skill_names({"content": "str-not-list"}) == []
    print("  [OK] _extract_skill_names: distinct, ordered, skill-only")


async def smoke_ingest_records_and_emits():
    db, hub = await _setup()
    run_id = await hub.create_run(1, goal="skills")
    node_id = await hub.create_node(run_id, 1, agent_name="backend-dev", role="worker")

    seen: set[str] = set()
    await _ingest_line(hub, db, run_id, node_id, 1, _assistant_line("u1", ["tdd"]), seen)

    rows = await db.list_node_skills_for_run(run_id)
    got = [(r["node_id"], r["skill_name"]) for r in rows]
    assert (node_id, "tdd") in got, f"skill row not recorded: {got}"

    events = [e["event_type"] for e in await hub.list_events(run_id)]
    assert "node_skill_used" in events, f"no node_skill_used event: {events}"
    print("  [OK] _ingest_line records skill row + emits node_skill_used")


async def smoke_idempotent_retail():
    db, hub = await _setup()
    run_id = await hub.create_run(1, goal="idem")
    node_id = await hub.create_node(run_id, 1, agent_name="planner", role="worker")

    line = _assistant_line("u1", ["brainstorming"])
    await _ingest_line(hub, db, run_id, node_id, 1, line, set())
    events_after_first = sum(
        1 for e in await hub.list_events(run_id) if e["event_type"] == "node_skill_used"
    )
    # Re-tail with a FRESH seen set (simulates server restart catchup).
    await _ingest_line(hub, db, run_id, node_id, 1, line, set())

    rows = [r for r in await db.list_node_skills_for_run(run_id) if r["skill_name"] == "brainstorming"]
    assert len(rows) == 1, f"re-tail duplicated skill row: {len(rows)}"
    events_after_second = sum(
        1 for e in await hub.list_events(run_id) if e["event_type"] == "node_skill_used"
    )
    assert events_after_first == 1 and events_after_second == 1, (
        f"re-tail re-emitted event: {events_after_first} -> {events_after_second}")
    print("  [OK] re-tail is idempotent (no dup row, no dup event)")


async def smoke_multi_skill_grouping():
    db, hub = await _setup()
    run_id = await hub.create_run(1, goal="multi")
    n1 = await hub.create_node(run_id, 1, agent_name="dev", role="worker")
    n2 = await hub.create_node(run_id, 1, agent_name="reviewer", role="worker")

    await _ingest_line(hub, db, run_id, n1, 1, _assistant_line("a", ["tdd", "debugging"]), set())
    await _ingest_line(hub, db, run_id, n2, 1, _assistant_line("b", ["receiving-code-review"]), set())
    # Same skill, different message on n1 → still one badge after grouping.
    await _ingest_line(hub, db, run_id, n1, 1, _assistant_line("c", ["tdd"]), set())

    by_node: dict[str, list[str]] = {}
    for r in await db.list_node_skills_for_run(run_id):
        by_node.setdefault(r["node_id"], []).append(r["skill_name"])
    assert sorted(by_node.get(n1, [])) == ["debugging", "tdd"], f"n1 skills wrong: {by_node.get(n1)}"
    assert by_node.get(n2) == ["receiving-code-review"], f"n2 skills wrong: {by_node.get(n2)}"
    print("  [OK] grouping per node de-dups repeated skill, splits by node")


async def main():
    smoke_extract()
    await smoke_ingest_records_and_emits()
    await smoke_idempotent_retail()
    await smoke_multi_skill_grouping()
    print("smoke_node_skills OK")


if __name__ == "__main__":
    asyncio.run(main())
