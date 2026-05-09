"""Root-level routes: /, /health, /locale."""
from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse


router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@router.get("/")
async def index(request: Request):
    db = request.app.state.db
    projects = await request.app.state.projects.list_all(only_enabled=True)
    pm = request.app.state.process_manager

    # Build per-project stats
    cards = []
    for proj in projects:
        try:
            stats = await db.week_stats(proj.id) or {}
        except Exception:
            stats = {}
        running = sum(
            1 for k in pm.list_running()
            if k.startswith(f"{proj.slug}:") or k.startswith(f"cmd:{proj.slug}:")
        )

        td_count = 0
        ideas_count = 0
        wiki_present = False
        try:
            from dreaming.services.config_resolver import ConfigResolver
            resolver = ConfigResolver(request.app.state.projects, request.app.state.settings)
            td_dir = await resolver.get(proj, "tech_debt_dir", "")
            if td_dir:
                from dreaming.services.tech_debt import list_tech_debt
                if Path(td_dir).exists():
                    try:
                        td_count = len(list_tech_debt(td_dir))
                    except Exception:
                        td_count = 0
            ideas_dir = await resolver.get(proj, "product_ideas_dir", "")
            if ideas_dir:
                from dreaming.services.product_ideas import list_product_ideas
                if Path(ideas_dir).exists():
                    try:
                        ideas_count = len(list_product_ideas(ideas_dir))
                    except Exception:
                        ideas_count = 0
            wiki_dir = await resolver.get(proj, "wiki_dir", "")
            if wiki_dir:
                wiki_present = Path(wiki_dir).exists()
        except Exception:
            pass

        cards.append({
            "project": proj,
            "stats": stats,
            "running": running,
            "td_count": td_count,
            "ideas_count": ideas_count,
            "wiki_present": wiki_present,
        })

    # Top-line totals
    total_success = sum((c["stats"] or {}).get("success", 0) for c in cards)
    total_failed = sum((c["stats"] or {}).get("failed", 0) for c in cards)
    total_timeout = sum((c["stats"] or {}).get("timeout", 0) for c in cards)
    total_running = sum(c["running"] for c in cards)
    total_td = sum(c["td_count"] for c in cards)
    total_ideas = sum(c["ideas_count"] for c in cards)

    # Active runs flat list (slug + agent) for the right rail
    pfx_runs = []
    for k in pm.list_running().keys():
        if k.startswith("cmd:"):
            parts = k.split(":", 2)
            if len(parts) == 3:
                pfx_runs.append({"slug": parts[1], "agent": f"cmd:{parts[2]}"})
        else:
            slug, _, agent = k.partition(":")
            pfx_runs.append({"slug": slug, "agent": agent})

    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    return request.app.state.templates.TemplateResponse(
        request,
        "index_dashboard.html",
        {
            "projects": projects,
            "cards": cards,
            "active_runs": pfx_runs,
            "totals": {
                "success": total_success, "failed": total_failed,
                "timeout": total_timeout, "running": total_running,
                "td": total_td, "ideas": total_ideas,
            },
            "locale": locale,
        },
    )


@router.post("/locale")
async def set_locale(request: Request, locale: str = Form(...), next: str = Form("/")):
    if locale not in ("ru", "en"):
        locale = "ru"
    resp = RedirectResponse(url=next or "/", status_code=303)
    resp.set_cookie("dc_locale", locale, max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax")
    return resp
