"""GET /p/{slug}/notes and /p/{slug}/notes/raw."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse

from dreaming.services.notes import list_notes, read_note


router = APIRouter()


def _default_notes_dir(project) -> str:
    return str(Path(project.working_dir) / ".claude" / "agents" / "learning-notes")


@router.get("/p/{slug}/notes")
async def notes_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    notes_dir = await resolver.get(project, "learning_notes_dir", _default_notes_dir(project))
    files = list_notes(notes_dir)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_notes.html",
        {"project": project, "files": files, "notes_dir": notes_dir,
         "exists": Path(notes_dir).exists(),
         "projects": projects, "locale": locale},
    )


@router.get("/p/{slug}/notes/raw")
async def notes_raw(request: Request, slug: str, path: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    notes_dir = await resolver.get(project, "learning_notes_dir", _default_notes_dir(project))
    text = read_note(notes_dir, path)
    if text is None:
        raise HTTPException(status_code=404, detail="not found or path traversal")
    return PlainTextResponse(text)
