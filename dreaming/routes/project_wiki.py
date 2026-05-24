"""GET /p/{slug}/wiki — wiki bootstrap status + scan triggers.

POST /p/{slug}/wiki/bootstrap — run /wiki-bootstrap via Claude CLI for the project.
POST /p/{slug}/wiki/lint      — run /wiki-lint to find stale pages and broken refs.
GET  /p/{slug}/wiki/raw?name=X  — read a single wiki page as plain text.
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from dreaming.services import autoconfig


router = APIRouter()


def _resolve_wiki_file(wiki_dir: str, name: str) -> Path | None:
    """Locate `{name}.md` under wiki_dir (in /domains/ if present, else root).
    Returns the file path only if it resolves cleanly inside wiki_dir
    (defence against path traversal)."""
    if not wiki_dir or not name:
        return None
    base = Path(wiki_dir).resolve()
    if not base.exists():
        return None
    name = name.strip()
    if name.endswith(".md"):
        name = name[:-3]
    candidates = [
        base / "domains" / f"{name}.md",
        base / f"{name}.md",
    ]
    for cand in candidates:
        try:
            resolved = cand.resolve()
            # Containment check: resolved must be under base.
            resolved.relative_to(base)
        except (OSError, ValueError):
            continue
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


@router.get("/p/{slug}/wiki")
async def wiki_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    wiki_dir = await resolver.get(project, "wiki_dir", "")
    status_info = None
    if wiki_dir:
        from dreaming.services.wiki_data import get_wiki_status
        status_info = get_wiki_status(wiki_dir)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    pm = request.app.state.process_manager
    bootstrap_running = f"cmd:{project.slug}:wiki-bootstrap" in pm.list_running()
    lint_running = f"cmd:{project.slug}:wiki-lint" in pm.list_running()
    return request.app.state.templates.TemplateResponse(
        request, "project_wiki.html",
        {"project": project, "wiki_dir": wiki_dir, "wiki_dir_set": bool(wiki_dir),
         "status": status_info,
         "autoconfig_default": autoconfig.default_abs(project, "wiki_dir"),
         "bootstrap_running": bootstrap_running, "lint_running": lint_running,
         "projects": projects, "locale": locale},
    )


@router.get("/p/{slug}/wiki/raw")
async def wiki_raw(request: Request, slug: str, name: str):
    """Plain-text content of a single wiki page. Used by the modal on /wiki."""
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    wiki_dir = await resolver.get(project, "wiki_dir", "")
    path = _resolve_wiki_file(wiki_dir, name)
    if path is None:
        raise HTTPException(status_code=404, detail="wiki page not found")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"read failed: {e}")
    return PlainTextResponse(text)


@router.post("/p/{slug}/wiki/bootstrap")
async def wiki_bootstrap_run(request: Request, slug: str):
    return await _spawn_wiki_command(request, "wiki-bootstrap", "/wiki-bootstrap")


@router.post("/p/{slug}/wiki/lint")
async def wiki_lint_run(request: Request, slug: str):
    return await _spawn_wiki_command(request, "wiki-lint", "/wiki-lint")


async def _spawn_wiki_command(request: Request, command_name: str, prompt: str):
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    try:
        await pm.start_command(
            project,
            command_name=command_name,
            prompt=prompt,
            claude_path=getattr(settings, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=getattr(settings, "model", "sonnet"),
            max_turns=getattr(settings, "max_turns", 50),
            timeout_minutes=getattr(settings, "timeout_minutes", 60),
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return RedirectResponse(f"/p/{project.slug}/live", status_code=303)
