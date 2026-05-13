"""GET/POST /p/{slug}/kanban — 5-day rotation board + custom topics CRUD."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse


router = APIRouter()


WEEKDAY_NAMES_RU = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
_DT_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _parse_dt(s: str | None) -> datetime:
    if not s:
        return _DT_MIN
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return _DT_MIN
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/p/{slug}/kanban")
async def kanban_page(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    resolver = request.app.state.resolver_factory(request)

    rotation_rows = await db.list_rotation(project.id)
    rotation = [dict(r) for r in rotation_rows]

    # Total sessions per agent (per-project) for the agent meta line
    counts = await db.fetch_all(
        "SELECT agent_name, COUNT(*) AS c FROM agent_learning_sessions "
        "WHERE project_id=? GROUP BY agent_name",
        (project.id,),
    )
    totals = {r["agent_name"]: int(r["c"]) for r in counts}

    per_night = int(await resolver.get(project, "agents_per_night", 5))

    # Same ordering as scheduler: oldest last_studied_at first (NULL=∞ past), then tier ASC.
    enabled = [a for a in rotation if a.get("enabled")]
    enabled.sort(key=lambda a: (_parse_dt(a.get("last_studied_at")), int(a.get("tier") or 2)))

    today = date.today()
    columns: list[dict] = []
    idx = 0
    for day_offset in range(5):
        d = today + timedelta(days=day_offset)
        day_agents = []
        for _ in range(per_night):
            if idx >= len(enabled):
                break
            a = enabled[idx]
            day_agents.append({
                "name": a["agent_name"],
                "tier": int(a.get("tier") or 2),
                "total_sessions": totals.get(a["agent_name"], 0),
                "last_studied_at": a.get("last_studied_at"),
            })
            idx += 1
        columns.append({
            "date_iso": d.isoformat(),
            "date_str": d.strftime("%d.%m"),
            "weekday": WEEKDAY_NAMES_RU[d.weekday()],
            "is_today": day_offset == 0,
            "agents": day_agents,
        })
    remaining = max(0, len(enabled) - idx)

    topics = await db.list_custom_topics(project.id, active_only=False)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_kanban.html",
        {
            "project": project,
            "columns": columns,
            "per_night": per_night,
            "total_enabled": len(enabled),
            "remaining": remaining,
            "topics": [dict(t) for t in topics],
            "projects": projects,
            "locale": locale,
        },
    )


@router.post("/p/{slug}/kanban/add")
async def kanban_add(
    request: Request, slug: str,
    title: str = Form(...), module: str = Form(""),
    target_agents: str = Form(""), question: str = Form(""),
    why_important: str = Form(""),
):
    project = request.state.project
    if not title.strip():
        raise HTTPException(status_code=400, detail="title required")
    await request.app.state.db.add_custom_topic(
        project.id, title.strip(), module.strip(),
        target_agents.strip(), question.strip(), why_important.strip(),
    )
    return RedirectResponse(f"/p/{project.slug}/kanban", status_code=303)


@router.post("/p/{slug}/kanban/{topic_id}/delete")
async def kanban_delete(request: Request, slug: str, topic_id: str):
    project = request.state.project
    await request.app.state.db.delete_custom_topic(project.id, topic_id)
    return RedirectResponse(f"/p/{project.slug}/kanban", status_code=303)
