"""AI Radar — глобальный раздел.

GET  /ai-radar                       — лента всех findings (фильтры)
POST /ai-radar/{id}/status           — `seen` | `dismissed` | `new`
POST /ai-radar/{id}/apply            — Wave R1: только kind=note (стаб)
POST /ai-radar/{id}/pin              — закрепить за проектом (slug)
"""
from __future__ import annotations
import json
import logging
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from dreaming.lib.flash import set_flash
from dreaming.services import ai_radar

log = logging.getLogger(__name__)


router = APIRouter()


_ALLOWED_STATUSES = {"new", "seen", "dismissed"}


def _decode_tags(row: dict) -> list[str]:
    try:
        tags = json.loads(row.get("tags_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(t) for t in tags if t]


def _enrich(rows: list) -> list[dict]:
    """Декодируем tags_json + рассыпаем pinned_projects/relevance_hint в списки."""
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        d["tags"] = _decode_tags(d)
        d["relevance_list"] = [
            s for s in (d.get("relevance_hint") or "").split(",") if s
        ]
        d["pinned_list"] = [
            s for s in (d.get("pinned_projects") or "").split(",") if s
        ]
        out.append(d)
    return out


@router.get("/ai-radar")
async def ai_radar_index(
    request: Request,
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    since_days: int | None = Query(default=None),
):
    db = request.app.state.db
    rows = await db.list_radar_findings(
        status=status or None,
        source_key=source or None,
        since_days=since_days,
        # table-tools filters client-side over this capped set (default limit=200 in list_radar_findings); see docs/superpowers/plans re: table-tools
    )
    source_counts = await db.radar_source_counts(since_days=7)
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale,
    )
    projects = await request.app.state.projects.list_all(only_enabled=True)
    sources_path = str(ai_radar.DEFAULT_SOURCES_PATH)
    watchlist = ai_radar.load_sources(sources_path)
    return request.app.state.templates.TemplateResponse(
        request, "ai_radar.html",
        {
            "findings": _enrich(rows),
            "source_counts": [dict(r) for r in source_counts],
            "projects": projects,
            "watchlist": watchlist,
            "sources_path": sources_path,
            "filter_status": status or "",
            "filter_source": source or "",
            "filter_since_days": since_days,
            "locale": locale,
        },
    )


@router.post("/ai-radar/{finding_id}/status")
async def ai_radar_set_status(
    request: Request, finding_id: int, status: str = Form(...),
):
    if status not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"bad status: {status}")
    ok = await request.app.state.db.set_radar_finding_status(finding_id, status)
    if not ok:
        raise HTTPException(status_code=404, detail="finding not found")
    return RedirectResponse(_back_to(request), status_code=303)


@router.post("/ai-radar/{finding_id}/apply")
async def ai_radar_apply(
    request: Request,
    finding_id: int,
    kind: str = Form(...),
    target_project: str = Form(...),
):
    if kind in ai_radar.SUPPORTED_APPLY_KINDS_R3:
        raise HTTPException(
            status_code=501,
            detail=f"apply kind '{kind}' lands in Wave R3 — use 'note' for now",
        )
    if kind not in ai_radar.SUPPORTED_APPLY_KINDS_R1:
        raise HTTPException(status_code=400, detail=f"unknown apply kind: {kind}")
    project = await request.app.state.projects.get_by_slug(target_project)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project {target_project} not found")
    try:
        await ai_radar.apply_as_note(
            request.app.state.db, finding_id, project.slug,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return RedirectResponse(_back_to(request), status_code=303)


@router.post("/ai-radar/{finding_id}/pin")
async def ai_radar_pin(
    request: Request, finding_id: int, target_project: str = Form(...),
):
    project = await request.app.state.projects.get_by_slug(target_project)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project {target_project} not found")
    ok = await request.app.state.db.pin_radar_finding_to_project(
        finding_id, project.slug,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="finding not found")
    return RedirectResponse(_back_to(request), status_code=303)


@router.post("/ai-radar/scan-now")
async def ai_radar_scan_now(request: Request):
    """Run the live RSS/Atom scanner against the watchlist and merge new
    findings. Synchronous — the scan is bounded (concurrency-limited, per-source
    timeout) and usually finishes in a few seconds."""
    from dreaming.services.ai_radar_scan import scan_now
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    resp = RedirectResponse(_back_to(request), status_code=303)
    try:
        res = await scan_now(request.app.state.db)
        msg = request.app.state.i18n.t(
            "radar.scan.done", locale=locale,
            inserted=res["inserted"], sources=res["sources_with_feed"],
        )
        set_flash(resp, msg, level="success")
    except Exception as e:
        log.warning("ai-radar scan-now failed: %s", e)
        set_flash(resp, request.app.state.i18n.t("radar.scan.failed", locale=locale, err=str(e)[:200]), level="error")
    return resp


def _back_to(request: Request) -> str:
    referer = request.headers.get("referer") or ""
    # Защита от open-redirect: принимаем только относительные пути из своего же
    # хоста (берём только path).
    if referer.startswith("/"):
        return referer
    host = f"{request.url.scheme}://{request.url.netloc}"
    if referer.startswith(host):
        return referer[len(host):] or "/ai-radar"
    return "/ai-radar"
