"""Aggregate AI usage events into dashboard payloads.

Public surface:
- `project_summary(db, project_id)` — per-project totals, by_model breakdown,
  daily series, main vs sidechain split, top sessions, learning-week roll-up.
- `global_summary(db)` — same shape across all projects.

Private helpers (`_by_model`, `_daily_series`, `_main_vs_sidechain`,
`_top_sessions`) feed both summaries. They were ported from ALC's original
layout in commit 8d11671.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from dreaming.services.db import SqliteDB


# ── helpers ───────────────────────────────────────────────────────

def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _date_window(days: int) -> tuple[str, str]:
    today = _today_utc()
    start = (today - timedelta(days=max(days - 1, 0))).isoformat()
    end = today.isoformat()
    return start, end


def resolve_preset(preset: str | None) -> tuple[str, str, str]:
    """Map a preset name to (start_date, end_date, normalized_preset).
    Unknown presets fall back to '7d'. 'all' uses a very early start."""
    p = (preset or "7d").lower()
    if p == "today":
        s, e = _date_window(1)
    elif p == "7d":
        s, e = _date_window(7)
    elif p == "30d":
        s, e = _date_window(30)
    elif p == "all":
        s, e = "1970-01-01", _today_utc().isoformat()
    else:
        p = "7d"
        s, e = _date_window(7)
    return s, e, p


async def _totals(
    db: SqliteDB,
    *,
    start: str,
    end: str,
    project_id: int | None = None,
    model: str | None = None,
) -> dict[str, int]:
    sql = (
        "SELECT "
        "COALESCE(SUM(input_tokens), 0)          AS input_tokens, "
        "COALESCE(SUM(output_tokens), 0)         AS output_tokens, "
        "COALESCE(SUM(cache_read_tokens), 0)     AS cache_read_tokens, "
        "COALESCE(SUM(cache_creation_tokens), 0) AS cache_creation_tokens, "
        "COALESCE(SUM(input_tokens+output_tokens+cache_read_tokens+cache_creation_tokens), 0) "
        "  AS total_tokens, "
        "COUNT(*) AS events "
        "FROM ai_usage_events "
        "WHERE ts_date BETWEEN ? AND ? "
    )
    params: list[Any] = [start, end]
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    if model:
        sql += "AND model=? "
        params.append(model)
    row = await db.fetch_one(sql, tuple(params))
    return dict(row) if row else {
        "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
        "cache_creation_tokens": 0, "total_tokens": 0, "events": 0,
    }


async def _by_model(
    db: SqliteDB,
    *,
    start: str,
    end: str,
    project_id: int | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT model, COUNT(*) AS events, "
        "COALESCE(SUM(input_tokens), 0)          AS input_tokens, "
        "COALESCE(SUM(output_tokens), 0)         AS output_tokens, "
        "COALESCE(SUM(cache_read_tokens), 0)     AS cache_read_tokens, "
        "COALESCE(SUM(cache_creation_tokens), 0) AS cache_creation_tokens, "
        "COALESCE(SUM(input_tokens+output_tokens+cache_read_tokens+cache_creation_tokens), 0) "
        "  AS total_tokens "
        "FROM ai_usage_events "
        "WHERE ts_date BETWEEN ? AND ? "
    )
    params: list[Any] = [start, end]
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    if model:
        sql += "AND model=? "
        params.append(model)
    sql += "GROUP BY model ORDER BY total_tokens DESC"
    rows = await db.fetch_all(sql, tuple(params))
    return [dict(r) for r in rows]


async def _by_project(
    db: SqliteDB, *, start: str, end: str,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT e.project_id, p.slug AS slug, p.label AS label, "
        "COUNT(*) AS events, "
        "COALESCE(SUM(e.input_tokens), 0)          AS input_tokens, "
        "COALESCE(SUM(e.output_tokens), 0)         AS output_tokens, "
        "COALESCE(SUM(e.cache_read_tokens), 0)     AS cache_read_tokens, "
        "COALESCE(SUM(e.cache_creation_tokens), 0) AS cache_creation_tokens, "
        "COALESCE(SUM(e.input_tokens+e.output_tokens+e.cache_read_tokens+e.cache_creation_tokens), 0) "
        "  AS total_tokens "
        "FROM ai_usage_events e "
        "LEFT JOIN projects p ON p.id = e.project_id "
        "WHERE e.ts_date BETWEEN ? AND ? "
        "GROUP BY e.project_id "
        "ORDER BY total_tokens DESC"
    )
    rows = await db.fetch_all(sql, (start, end))
    return [dict(r) for r in rows]


async def _by_skill(
    db: SqliteDB,
    *,
    start: str,
    end: str,
    project_id: int | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Skill invocation counts in the window, ordered by calls desc."""
    sql = (
        "SELECT skill_name, COUNT(*) AS calls, "
        "COUNT(DISTINCT session_id) AS sessions "
        "FROM ai_skill_invocations "
        "WHERE ts_date BETWEEN ? AND ? "
    )
    params: list[Any] = [start, end]
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    if model:
        sql += "AND model=? "
        params.append(model)
    sql += "GROUP BY skill_name ORDER BY calls DESC, skill_name ASC"
    rows = await db.fetch_all(sql, tuple(params))
    return [dict(r) for r in rows]


async def _by_agent(
    db: SqliteDB,
    *,
    start: str,
    end: str,
    project_id: int | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Token totals + run count per Task subagent (agentType), tokens desc."""
    sql = (
        "SELECT agent_name, "
        "COUNT(*) AS events, "
        "COUNT(DISTINCT session_id) AS runs, "
        "COALESCE(SUM(input_tokens+output_tokens+cache_read_tokens+cache_creation_tokens), 0) "
        "  AS total_tokens "
        "FROM ai_usage_events "
        "WHERE ts_date BETWEEN ? AND ? "
        "AND agent_name IS NOT NULL AND agent_name <> '' "
    )
    params: list[Any] = [start, end]
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    if model:
        sql += "AND model=? "
        params.append(model)
    sql += "GROUP BY agent_name ORDER BY total_tokens DESC, agent_name ASC"
    rows = await db.fetch_all(sql, tuple(params))
    return [dict(r) for r in rows]


async def _events_total_all_time(db: SqliteDB) -> int:
    row = await db.fetch_one("SELECT COUNT(*) AS c FROM ai_usage_events")
    return int(row["c"]) if row else 0


async def _daily_series(
    db: SqliteDB,
    *,
    start: str,
    end: str,
    project_id: int | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT ts_date, "
        "COALESCE(SUM(input_tokens), 0)          AS input_tokens, "
        "COALESCE(SUM(output_tokens), 0)         AS output_tokens, "
        "COALESCE(SUM(cache_read_tokens), 0)     AS cache_read_tokens, "
        "COALESCE(SUM(cache_creation_tokens), 0) AS cache_creation_tokens "
        "FROM ai_usage_events "
        "WHERE ts_date BETWEEN ? AND ? "
    )
    params: list[Any] = [start, end]
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    if model:
        sql += "AND model=? "
        params.append(model)
    sql += "GROUP BY ts_date ORDER BY ts_date ASC"
    rows = await db.fetch_all(sql, tuple(params))
    return [dict(r) for r in rows]


async def _main_vs_sidechain(
    db: SqliteDB,
    *,
    start: str,
    end: str,
    project_id: int | None = None,
    model: str | None = None,
) -> dict[str, int]:
    sql = (
        "SELECT is_sidechain, "
        "COALESCE(SUM(input_tokens+output_tokens+cache_read_tokens+cache_creation_tokens), 0) "
        "  AS total_tokens "
        "FROM ai_usage_events "
        "WHERE ts_date BETWEEN ? AND ? "
    )
    params: list[Any] = [start, end]
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    if model:
        sql += "AND model=? "
        params.append(model)
    sql += "GROUP BY is_sidechain"
    rows = await db.fetch_all(sql, tuple(params))
    out = {"main": 0, "sub": 0}
    for r in rows:
        key = "sub" if int(r["is_sidechain"] or 0) else "main"
        out[key] = int(r["total_tokens"] or 0)
    return out


async def _models_catalog(
    db: SqliteDB, *, project_id: int | None = None,
) -> list[str]:
    """All distinct models seen for this project, ordered by total usage desc."""
    sql = (
        "SELECT model, SUM(input_tokens+output_tokens+cache_read_tokens+cache_creation_tokens) AS t "
        "FROM ai_usage_events WHERE model IS NOT NULL "
    )
    params: list[Any] = []
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    sql += "GROUP BY model ORDER BY t DESC"
    rows = await db.fetch_all(sql, tuple(params))
    return [r["model"] for r in rows if r["model"]]


async def _distinct_sessions(
    db: SqliteDB, *, start: str, end: str,
    project_id: int | None = None, model: str | None = None,
) -> int:
    sql = (
        "SELECT COUNT(DISTINCT session_id) AS n FROM ai_usage_events "
        "WHERE ts_date BETWEEN ? AND ? "
    )
    params: list[Any] = [start, end]
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    if model:
        sql += "AND model=? "
        params.append(model)
    row = await db.fetch_one(sql, tuple(params))
    return int(row["n"]) if row else 0


async def _top_sessions(
    db: SqliteDB, *, start: str, end: str,
    project_id: int | None = None, model: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Top-N sessions by total tokens. Model picked as the most-used per session."""
    sql = (
        "SELECT session_id, MIN(ts) AS started_at, MAX(ts) AS last_at, "
        "COUNT(*) AS events, "
        "SUM(input_tokens+output_tokens+cache_read_tokens+cache_creation_tokens) AS total_tokens, "
        "(SELECT model FROM ai_usage_events e2 "
        " WHERE e2.session_id=e1.session_id GROUP BY model ORDER BY COUNT(*) DESC LIMIT 1) AS model "
        "FROM ai_usage_events e1 "
        "WHERE ts_date BETWEEN ? AND ? "
    )
    params: list[Any] = [start, end]
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    if model:
        sql += "AND model=? "
        params.append(model)
    sql += "GROUP BY session_id ORDER BY total_tokens DESC LIMIT ?"
    params.append(limit)
    rows = await db.fetch_all(sql, tuple(params))
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["duration_minutes"] = _duration_min(d.get("started_at") or "", d.get("last_at") or "")
        out.append(d)
    return out


def _duration_min(start_iso: str, end_iso: str) -> int:
    """Minutes between two ISO timestamps; safe on empty/malformed input."""
    def _parse(s: str) -> datetime | None:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    a, b = _parse(start_iso), _parse(end_iso)
    if not a or not b:
        return 0
    return max(0, int((b - a).total_seconds() // 60))


def _fill_daily_gaps(
    rows: list[dict[str, Any]], start: str, end: str,
) -> list[dict[str, Any]]:
    """Fill missing dates in [start..end] with zeros so the chart is contiguous."""
    by_date = {r["ts_date"]: r for r in rows}
    try:
        d0 = date.fromisoformat(start)
        d1 = date.fromisoformat(end)
    except ValueError:
        return rows
    if d1 < d0:
        return rows
    out: list[dict[str, Any]] = []
    cur = d0
    while cur <= d1:
        key = cur.isoformat()
        if key in by_date:
            out.append(by_date[key])
        else:
            out.append({
                "ts_date": key,
                "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_creation_tokens": 0,
            })
        cur += timedelta(days=1)
    return out


async def _week_stats_project(db: SqliteDB, project_id: int) -> dict[str, int]:
    """Same shape as db.week_stats(project_id) but available for direct use here."""
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    row = await db.fetch_one(
        """
        SELECT
            COALESCE(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END), 0) AS success,
            COALESCE(SUM(CASE WHEN status='no_gap' THEN 1 ELSE 0 END), 0) AS no_gap,
            COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END), 0) AS failed,
            COALESCE(SUM(CASE WHEN status='timeout' THEN 1 ELSE 0 END), 0) AS timeout,
            COALESCE(SUM(CASE WHEN status='running' OR (status IS NULL AND finished_at IS NULL) THEN 1 ELSE 0 END), 0) AS running,
            COUNT(*) AS total
        FROM agent_learning_sessions
        WHERE project_id=? AND started_at >= ?
        """,
        (project_id, monday.isoformat()),
    )
    return dict(row) if row else {
        "success": 0, "no_gap": 0, "failed": 0, "timeout": 0, "running": 0, "total": 0,
    }


async def _recent_learning_sessions(
    db: SqliteDB, project_id: int, limit: int = 10,
) -> list[dict[str, Any]]:
    rows = await db.fetch_all(
        "SELECT id, agent_name, topic, status, started_at, finished_at "
        "FROM agent_learning_sessions WHERE project_id=? "
        "ORDER BY started_at DESC LIMIT ?",
        (project_id, limit),
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        dur = _duration_min(d.get("started_at") or "", d.get("finished_at") or "")
        d["duration_minutes"] = dur if dur else None
        out.append(d)
    return out


def _kpi(
    filtered: dict, main_sub: dict, sessions: int,
) -> dict[str, Any]:
    inp = int(filtered.get("input_tokens") or 0)
    out = int(filtered.get("output_tokens") or 0)
    cr  = int(filtered.get("cache_read_tokens") or 0)
    cc  = int(filtered.get("cache_creation_tokens") or 0)
    total = int(filtered.get("total_tokens") or 0)
    events = int(filtered.get("events") or 0)
    side = int(main_sub.get("sub") or 0)
    return {
        "input": inp, "output": out,
        "cache_read": cr, "cache_creation": cc,
        "events": events, "sessions": sessions,
        "grand_total": total,
        "sidechain_total": side,
        "avg_per_session": int(total // sessions) if sessions else 0,
        "cache_hit_pct": round(cr / (cr + inp) * 100, 1) if (cr + inp) else 0.0,
        "sidechain_share_pct": round(side / total * 100, 1) if total else 0.0,
    }


# ── public API ────────────────────────────────────────────────────

async def project_summary(
    db: SqliteDB,
    project_id: int,
    *,
    preset: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Per-project AI usage summary.

    `preset` selects the date window (today / 7d / 30d / all). `model` narrows
    every aggregate to a single model. The unfiltered "Last 7d" / "Last 30d"
    KPI tiles are always returned alongside the filtered view so the page
    keeps stable reference numbers when the user is exploring filters."""
    fs, fe, preset = resolve_preset(preset)
    s7, e7 = _date_window(7)
    s30, e30 = _date_window(30)

    filtered = await _totals(db, start=fs, end=fe, project_id=project_id, model=model)
    last_7d = await _totals(db, start=s7, end=e7, project_id=project_id)
    last_30d = await _totals(db, start=s30, end=e30, project_id=project_id)
    by_model = await _by_model(db, start=fs, end=fe, project_id=project_id, model=model)
    daily_rows = await _daily_series(db, start=fs, end=fe, project_id=project_id, model=model)
    daily = _fill_daily_gaps(daily_rows, fs, fe)
    main_sub = await _main_vs_sidechain(
        db, start=fs, end=fe, project_id=project_id, model=model,
    )
    models = await _models_catalog(db, project_id=project_id)
    sessions = await _distinct_sessions(
        db, start=fs, end=fe, project_id=project_id, model=model,
    )
    top_sessions = await _top_sessions(
        db, start=fs, end=fe, project_id=project_id, model=model, limit=5,
    )
    by_skill = await _by_skill(db, start=fs, end=fe, project_id=project_id, model=model)
    by_agent = await _by_agent(db, start=fs, end=fe, project_id=project_id, model=model)
    kpi = _kpi(filtered, main_sub, sessions)
    week = await _week_stats_project(db, project_id)
    recent = await _recent_learning_sessions(db, project_id, limit=10)

    return {
        "project_id": project_id,
        "filters": {
            "preset": preset, "model": model or "",
            "start": fs, "end": fe,
        },
        "models_catalog": models,
        "filtered": filtered,
        "kpi": kpi,
        "last_7d": last_7d,
        "last_30d": last_30d,
        "by_model": by_model,
        "by_skill": by_skill,
        "by_agent": by_agent,
        "daily": daily,
        "main_sub": main_sub,
        "top_sessions": top_sessions,
        "learning": {"week": week, "recent": recent},
    }


async def global_summary(
    db: SqliteDB,
    *,
    preset: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """All-project AI usage summary — same shape as project_summary() so the
    same template can render both, plus a `by_project` table that doesn't
    exist on the per-project view."""
    fs, fe, preset = resolve_preset(preset)
    s7, e7 = _date_window(7)
    s30, e30 = _date_window(30)

    filtered = await _totals(db, start=fs, end=fe, project_id=None, model=model)
    last_7d = await _totals(db, start=s7, end=e7, project_id=None)
    last_30d = await _totals(db, start=s30, end=e30, project_id=None)
    by_model = await _by_model(db, start=fs, end=fe, project_id=None, model=model)
    daily_rows = await _daily_series(db, start=fs, end=fe, project_id=None, model=model)
    daily = _fill_daily_gaps(daily_rows, fs, fe)
    main_sub = await _main_vs_sidechain(db, start=fs, end=fe, project_id=None, model=model)
    models = await _models_catalog(db, project_id=None)
    sessions = await _distinct_sessions(db, start=fs, end=fe, project_id=None, model=model)
    top_sessions = await _top_sessions(
        db, start=fs, end=fe, project_id=None, model=model, limit=5,
    )
    by_skill = await _by_skill(db, start=fs, end=fe, project_id=None, model=model)
    by_agent = await _by_agent(db, start=fs, end=fe, project_id=None, model=model)
    by_project = await _by_project(db, start=fs, end=fe)
    events_total = await _events_total_all_time(db)
    kpi = _kpi(filtered, main_sub, sessions)

    return {
        "filters": {
            "preset": preset, "model": model or "",
            "start": fs, "end": fe,
        },
        "models_catalog": models,
        "filtered": filtered,
        "kpi": kpi,
        "last_7d": last_7d,
        "last_30d": last_30d,
        "by_model": by_model,
        "by_skill": by_skill,
        "by_agent": by_agent,
        "by_project": by_project,
        "daily": daily,
        "main_sub": main_sub,
        "top_sessions": top_sessions,
        "events_total": events_total,
    }
