"""Cascade costs aggregation. Wave 4 lite — sums cost_usd from orchestrator_events
payload_json keyed by run. Roman/cascade pipelines aren't fully wired until Wave 3,
so the data is mostly empty in current builds."""
from __future__ import annotations
import json
from dataclasses import dataclass


@dataclass
class CascadeRunCost:
    run_id: str
    project_id: int
    goal: str
    status: str
    started_at: str
    finished_at: str | None
    total_cost_usd: float
    event_count: int


async def list_cascade_costs(db, project_id: int, limit: int = 50) -> list[CascadeRunCost]:
    rows = await db.fetch_all(
        """
        SELECT id, project_id, goal, status, started_at, finished_at
        FROM orchestrator_runs
        WHERE project_id=?
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (project_id, limit),
    )
    out: list[CascadeRunCost] = []
    for r in rows:
        events = await db.fetch_all(
            "SELECT payload_json FROM orchestrator_events WHERE run_id=?",
            (r["id"],),
        )
        total = 0.0
        for e in events:
            try:
                p = json.loads(e["payload_json"])
            except Exception:
                continue
            cost = p.get("cost_usd") or p.get("total_cost_usd") or 0
            try:
                total += float(cost)
            except (TypeError, ValueError):
                pass
        out.append(CascadeRunCost(
            run_id=r["id"],
            project_id=r["project_id"],
            goal=r["goal"] or "",
            status=r["status"] or "",
            started_at=r["started_at"] or "",
            finished_at=r["finished_at"],
            total_cost_usd=total,
            event_count=len(events),
        ))
    return out
