"""GET /p/{slug}/ai-radar — лента findings, релевантных конкретному проекту.

Фильтр: relevance_hint содержит slug ИЛИ pinned_projects содержит slug.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, Query, Request


router = APIRouter()


def _decode_tags(row: dict) -> list[str]:
    try:
        return [str(t) for t in (json.loads(row.get("tags_json") or "[]") or [])]
    except (TypeError, json.JSONDecodeError):
        return []


@router.get("/p/{slug}/ai-radar")
async def project_ai_radar(
    request: Request, slug: str,
    status: str | None = Query(default=None),
    since_days: int | None = Query(default=None),
):
    project = request.state.project
    db = request.app.state.db
    rows = await db.list_radar_findings(
        status=status or None, since_days=since_days, project_slug=project.slug,
    )
    findings = []
    for r in rows:
        d = dict(r)
        d["tags"] = _decode_tags(d)
        d["pinned_list"] = [
            s for s in (d.get("pinned_projects") or "").split(",") if s
        ]
        findings.append(d)
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale,
    )
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_ai_radar.html",
        {"project": project, "findings": findings,
         "filter_status": status or "", "filter_since_days": since_days,
         "projects": projects, "locale": locale},
    )
