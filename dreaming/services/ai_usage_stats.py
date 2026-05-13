"""Aggregate AI usage events into dashboard payloads.

Wave 4 lite surface:
- `project_summary(db, project_id)` — totals (last 7d / 30d), by_model breakdown.
- `global_summary(db)` — totals across all projects + by_project breakdown.

All other ALC aggregations (daily series, sidechain split, top sessions, ...)
are intentionally not ported here — Wave 4 lite only needs the two above.
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
    daily = await _daily_series(db, start=fs, end=fe, project_id=project_id, model=model)
    main_sub = await _main_vs_sidechain(
        db, start=fs, end=fe, project_id=project_id, model=model,
    )
    models = await _models_catalog(db, project_id=project_id)

    return {
        "project_id": project_id,
        "filters": {
            "preset": preset, "model": model or "",
            "start": fs, "end": fe,
        },
        "models_catalog": models,
        "filtered": filtered,
        "last_7d": last_7d,
        "last_30d": last_30d,
        "by_model": by_model,
        "daily": daily,
        "main_sub": main_sub,
    }


async def global_summary(db: SqliteDB) -> dict[str, Any]:
    """Totals across all projects + by_project breakdown (last 30d)."""
    s7, e7 = _date_window(7)
    s30, e30 = _date_window(30)

    last_7d = await _totals(db, start=s7, end=e7, project_id=None)
    last_30d = await _totals(db, start=s30, end=e30, project_id=None)
    by_project = await _by_project(db, start=s30, end=e30)
    events_total = await _events_total_all_time(db)

    return {
        "last_7d": last_7d,
        "last_30d": last_30d,
        "by_project": by_project,
        "events_total": events_total,
    }
