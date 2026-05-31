"""GET /p/{slug}/cascade-costs — per-run cost roll-up."""
from __future__ import annotations
from fastapi import APIRouter, Query, Request


router = APIRouter()


@router.get("/p/{slug}/cascade-costs")
async def cascade_costs_page(
    request: Request, slug: str,
    preset: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    project = request.state.project
    db = request.app.state.db
    from dreaming.services.cascade_costs import list_cascade_costs, kpi_from_rows, resolve_preset
    start, end, preset = resolve_preset(preset)
    rows: list = []
    error: str | None = None
    try:
        raw = await list_cascade_costs(
            db, project.id, start=start, end=end, status=status, limit=200,  # table-tools filters client-side over this capped set (most-recent 200 in window); see docs/superpowers/plans re: table-tools
        )
        rows = [r.__dict__ for r in raw]
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    kpi = kpi_from_rows([type("R", (), r) for r in rows]) if rows else {
        "runs": 0, "total_cost_usd": 0.0, "total_tokens": 0,
        "total_events": 0, "status_counts": {}, "avg_cost_usd": 0.0, "avg_tokens": 0,
    }
    # rows have token totals already, but our kpi shim above wraps dicts; recompute cleanly:
    kpi["runs"] = len(rows)
    kpi["total_cost_usd"] = sum(r["total_cost_usd"] for r in rows)
    kpi["total_tokens"] = sum(r["total_tokens"] for r in rows)
    kpi["total_events"] = sum(r["event_count"] for r in rows)
    sc: dict[str, int] = {}
    for r in rows:
        sc[r["status"]] = sc.get(r["status"], 0) + 1
    kpi["status_counts"] = sc
    kpi["avg_cost_usd"] = (kpi["total_cost_usd"] / kpi["runs"]) if kpi["runs"] else 0
    kpi["avg_tokens"] = (kpi["total_tokens"] // kpi["runs"]) if kpi["runs"] else 0

    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_cascade_costs.html",
        {
            "project": project, "rows": rows, "kpi": kpi, "error": error,
            "filters": {"preset": preset, "status": status or "", "start": start, "end": end},
            "projects": projects, "locale": locale,
        },
    )
