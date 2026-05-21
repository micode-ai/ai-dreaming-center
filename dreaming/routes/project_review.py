"""GET /p/{slug}/review — triage page aggregating items needing attention.

Pure aggregation. No new data layer. Reads from:
  - dreaming.services.evolutions.list_evolutions
  - dreaming.services.tech_debt.parse_tech_debt
  - dreaming.services.sidecar_findings.list_sidecar_findings

Each item links back to its canonical detail page.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request

from dreaming.services import autoconfig

router = APIRouter()
log = logging.getLogger(__name__)


_HIGH_PRIORITIES = {"high", "urgent", "critical"}


async def _resolve_dir(request, project, key: str) -> str:
    """Resolve a project dir setting with autoconfig fallback."""
    resolver = request.app.state.resolver_factory(request)
    default = autoconfig.default_abs(project, key) or ""
    return await resolver.get(project, key, default)


@router.get("/p/{slug}/review")
async def project_review(request: Request, slug: str):
    project = request.state.project

    # 1. Proposed evolutions
    proposed_evolutions: list = []
    try:
        from dreaming.services.evolutions import list_evolutions
        evolutions_dir = await _resolve_dir(request, project, "evolutions_dir")
        if evolutions_dir and Path(evolutions_dir).exists():
            for it in list_evolutions(evolutions_dir):
                status = (it.status or "").lower()
                # An empty status is treated as "proposed" — that's how
                # /evolve-agent writes new items.
                if status in ("", "proposed"):
                    proposed_evolutions.append({
                        "agent_name": it.agent_name,
                        "title": it.title or it.name,
                        "relative_path": it.relative_path,
                        "has_conflict": it.has_conflict,
                    })
    except Exception as e:
        log.warning("review: evolutions read failed: %s", e)

    # 2. Open + high-priority tech-debt
    urgent_findings: list = []
    try:
        from dreaming.services.tech_debt import parse_tech_debt
        tech_debt_dir = await _resolve_dir(request, project, "tech_debt_dir")
        if tech_debt_dir and Path(tech_debt_dir).exists():
            for it in parse_tech_debt(tech_debt_dir):
                if (it.status or "").lower() == "open" and (it.priority or "").lower() in _HIGH_PRIORITIES:
                    urgent_findings.append({
                        "id": it.id,
                        "title": it.title,
                        "priority": it.priority,
                        "module": it.module,
                        "created": (it.created or "")[:10],
                    })
    except Exception as e:
        log.warning("review: tech_debt read failed: %s", e)

    # 3. Recent sidecar findings (top 10)
    recent_sidecar: list = []
    try:
        from dreaming.services.sidecar_findings import list_sidecar_findings
        sidecar_dir = await _resolve_dir(request, project, "sidecar_findings_dir")
        if sidecar_dir and Path(sidecar_dir).exists():
            items = list_sidecar_findings(sidecar_dir)
            # Sort by source_file mtime descending if path exists.
            def _mtime(it):
                try:
                    return Path(it.source_file).stat().st_mtime
                except OSError:
                    return 0.0
            items.sort(key=_mtime, reverse=True)
            for it in items[:10]:
                recent_sidecar.append({
                    "id": it.id,
                    "title": it.title,
                    "severity": it.severity,
                    "module": it.module,
                    "reviewer": it.reviewer,
                    "file": it.file,
                })
    except Exception as e:
        log.warning("review: sidecar_findings read failed: %s", e)

    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_review.html",
        {
            "project": project,
            "proposed_evolutions": proposed_evolutions,
            "urgent_findings": urgent_findings,
            "recent_sidecar": recent_sidecar,
            "projects": projects,
            "locale": locale,
        },
    )
