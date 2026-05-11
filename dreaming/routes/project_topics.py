"""GET /p/{slug}/topics — weekly learning checklist (read-only)."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request

from dreaming.services import starter_kit


router = APIRouter()


CHECKLIST_REL = "agents/lessons/_weekly-learning-checklist.md"


@router.get("/p/{slug}/topics")
async def topics_page(request: Request, slug: str):
    project = request.state.project
    candidates = [
        Path(project.working_dir) / ".claude" / "agents" / "lessons" / "_weekly-learning-checklist.md",
        Path(project.working_dir) / ".claude" / "agents" / "_weekly-learning-checklist.md",
    ]
    found_path = next((c for c in candidates if c.exists()), None)
    items = []
    if found_path is not None:
        try:
            from dreaming.services.checklist import parse_weekly_checklist
            items = parse_weekly_checklist(found_path.read_text(encoding="utf-8"))
        except (ImportError, AttributeError):
            text = found_path.read_text(encoding="utf-8")
            items = [{"raw": ln.strip()} for ln in text.splitlines() if ln.strip().startswith("- [")]
        except Exception:
            items = []
    kit_status = starter_kit.status(project.working_dir)
    can_install = CHECKLIST_REL in kit_status.template_files
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_topics.html",
        {"project": project, "items": items,
         "checklist_path": str(found_path) if found_path else "",
         "found": found_path is not None,
         "can_install_checklist": can_install,
         "projects": projects, "locale": locale},
    )
