"""GET /p/{slug}/articles — предложения статей проекта по статусам.

Согласование и публикация живут в отдельных роутах (Task 8 и Task 9);
здесь — список, отклонение и возврат в очередь.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.services import articles


router = APIRouter()

_ORDER = ["proposed", "approved", "writing", "drafted", "published",
          "failed", "rejected"]


def _enrich(row: dict, *, verify_cmd: str, publish_mode: str) -> dict:
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        d["tags"] = []
    allowed, reason = articles.can_publish(d, verify_cmd, publish_mode)
    d["can_publish"] = allowed
    d["gate_reason"] = reason
    d["verify_label"] = articles.publish_label(bool(d.get("verify_ok")), verify_cmd)
    return d


@router.get("/p/{slug}/articles")
async def articles_page(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    resolver = request.app.state.resolver_factory(request)
    verify_cmd = await resolver.get(project, "article_verify_cmd", "")
    publish_mode = await resolver.get(project, "article_publish_mode", "off")
    blog_dir = await resolver.get(project, "article_blog_dir", "")
    configured_writer = await resolver.get(project, "article_writer_agent", "")
    rows = await db.list_article_proposals(project_id=project.id)
    enriched = [_enrich(r, verify_cmd=verify_cmd, publish_mode=publish_mode)
                for r in rows]
    groups = [(st, [r for r in enriched if r["status"] == st]) for st in _ORDER]
    counts = {r["status"]: r["n"] for r in await db.article_status_counts(project.id)}
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale,
    )
    projects = await request.app.state.projects.list_all(only_enabled=True)
    pm = request.app.state.process_manager
    return request.app.state.templates.TemplateResponse(
        request, "project_articles.html",
        {"project": project,
         "groups": [(st, items) for st, items in groups if items],
         "counts": counts, "total": len(enriched),
         "blog_dir": blog_dir,
         "writer": articles.resolve_writer(project.working_dir, configured_writer),
         "scan_running": f"cmd:{project.slug}:article-ideas-scan" in pm.list_running(),
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/articles/{proposal_id}/reject")
async def articles_reject(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    ok = await request.app.state.db.set_article_proposal_status(
        proposal_id, "rejected",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)


@router.post("/p/{slug}/articles/{proposal_id}/restore")
async def articles_restore(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    ok = await request.app.state.db.set_article_proposal_status(
        proposal_id, "proposed",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)
