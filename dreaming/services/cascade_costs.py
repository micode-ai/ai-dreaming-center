"""Cascade costs aggregation.

Per-project roll-up of orchestrator runs:
  - cost_usd: parsed from orchestrator_events.payload_json (whatever key the
    underlying pipeline used — cost_usd / total_cost_usd are both accepted)
  - tokens: joined from ai_usage_events on session_id == orchestrator_runs.external_id

Roman/cascade pipelines aren't fully wired until Wave 3, so cost values are
usually 0 in current builds; the page still renders the runs list and tokens
attribution so people can spot heavy sessions.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


@dataclass
class CascadeRunCost:
    run_id: str
    project_id: int
    goal: str
    status: str
    started_at: str
    finished_at: str | None
    external_id: str | None
    total_cost_usd: float
    event_count: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def resolve_preset(preset: str | None) -> tuple[str | None, str | None, str]:
    """Map a preset name to (start_iso, end_iso, normalized_preset).

    `start`/`end` are ISO timestamps suitable for comparison against
    `orchestrator_runs.started_at`. `all` returns (None, None) so the SQL
    skips the date filter entirely. Unknown presets fall back to '7d'."""
    p = (preset or "7d").lower()
    today = _today_utc()
    if p == "today":
        start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        end = None
    elif p == "7d":
        start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        end = None
    elif p == "30d":
        start = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        end = None
    elif p == "all":
        start = None
        end = None
    else:
        p = "7d"
        start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        end = None
    return start, end, p


async def list_cascade_costs(
    db,
    project_id: int,
    *,
    start: str | None = None,
    end: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[CascadeRunCost]:
    sql = (
        "SELECT id, project_id, goal, status, started_at, finished_at, external_id "
        "FROM orchestrator_runs WHERE project_id=? "
    )
    params: list = [project_id]
    if start:
        sql += "AND started_at >= ? "
        params.append(start)
    if end:
        sql += "AND started_at <= ? "
        params.append(end)
    if status:
        sql += "AND status = ? "
        params.append(status)
    sql += "ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    rows = await db.fetch_all(sql, tuple(params))
    out: list[CascadeRunCost] = []
    for r in rows:
        events = await db.fetch_all(
            "SELECT payload_json FROM orchestrator_events WHERE run_id=?",
            (r["id"],),
        )
        cost_total = 0.0
        for e in events:
            try:
                payload = json.loads(e["payload_json"])
            except (TypeError, ValueError):
                continue
            cost = payload.get("cost_usd") or payload.get("total_cost_usd") or 0
            try:
                cost_total += float(cost)
            except (TypeError, ValueError):
                pass

        # Token attribution via session_id match
        in_tok = out_tok = cr_tok = cc_tok = 0
        ext = r["external_id"] or ""
        if ext:
            tok = await db.fetch_one(
                "SELECT "
                "COALESCE(SUM(input_tokens),0) AS i, "
                "COALESCE(SUM(output_tokens),0) AS o, "
                "COALESCE(SUM(cache_read_tokens),0) AS cr, "
                "COALESCE(SUM(cache_creation_tokens),0) AS cc "
                "FROM ai_usage_events WHERE session_id=?",
                (ext,),
            )
            if tok:
                in_tok = int(tok["i"] or 0)
                out_tok = int(tok["o"] or 0)
                cr_tok = int(tok["cr"] or 0)
                cc_tok = int(tok["cc"] or 0)

        out.append(CascadeRunCost(
            run_id=r["id"],
            project_id=r["project_id"],
            goal=r["goal"] or "",
            status=r["status"] or "",
            started_at=r["started_at"] or "",
            finished_at=r["finished_at"],
            external_id=ext or None,
            total_cost_usd=cost_total,
            event_count=len(events),
            total_tokens=in_tok + out_tok + cr_tok + cc_tok,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cache_read_tokens=cr_tok,
            cache_creation_tokens=cc_tok,
        ))
    return out


def kpi_from_rows(rows: list[CascadeRunCost]) -> dict:
    n = len(rows)
    total_cost = sum(r.total_cost_usd for r in rows)
    total_tokens = sum(r.total_tokens for r in rows)
    total_events = sum(r.event_count for r in rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    avg_cost = (total_cost / n) if n else 0
    avg_tokens = (total_tokens // n) if n else 0
    return {
        "runs": n,
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
        "total_events": total_events,
        "status_counts": counts,
        "avg_cost_usd": avg_cost,
        "avg_tokens": avg_tokens,
    }
