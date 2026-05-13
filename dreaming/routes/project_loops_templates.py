"""GET /p/{slug}/loops/templates — per-project loop-template catalog.

Reads .md files from `<working_dir>/.claude/loops/templates/` if it exists.
The directory is conventional in ALC; the dreaming center treats this as
opt-in — empty list is the normal state.
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request

router = APIRouter()


def _scan_templates(working_dir: str | None) -> list[dict]:
    if not working_dir:
        return []
    base = Path(working_dir) / ".claude" / "loops" / "templates"
    if not base.exists() or not base.is_dir():
        return []
    items: list[dict] = []
    for md in sorted(base.glob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        first_line = text.splitlines()[0].lstrip("# ").strip() if text else md.stem
        items.append({
            "slug": md.stem,
            "name": first_line or md.stem,
            "path": str(md),
            "size_bytes": md.stat().st_size,
        })
    return items


@router.get("/p/{slug}/loops/templates")
async def project_loops_templates(request: Request, slug: str):
    project = request.state.project
    items = _scan_templates(project.working_dir)
    base = (Path(project.working_dir) / ".claude" / "loops" / "templates") if project.working_dir else None
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request,
        "project_loops_templates.html",
        {
            "project": project,
            "items": items,
            "templates_dir": str(base) if base else "",
            "templates_dir_exists": bool(base and base.exists()),
            "projects": projects,
            "locale": locale,
        },
    )
