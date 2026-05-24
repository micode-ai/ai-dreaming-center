"""GET  /p/{slug}/evolutions                    — list of agent _context/ overrides.
GET  /p/{slug}/evolutions/raw?path=X         — raw text of a single evolution file.
POST /p/{slug}/evolutions/status             — rewrite frontmatter `status:`.
POST /p/{slug}/evolutions/delete             — unlink the evolution file.
POST /p/{slug}/evolutions/apply              — apply the proposal via Orchestrator.
POST /p/{slug}/evolutions/github             — create GitHub issue from the proposal.
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from dreaming.services import autoconfig
from dreaming.services.frontmatter_io import set_frontmatter_field
from dreaming.services.evolution_rubric import collect_stats, ReportRubricStats


router = APIRouter()


async def _resolve_evolutions_dir(request, project) -> str:
    resolver = request.app.state.resolver_factory(request)
    default_dir = str(Path(project.working_dir) / ".claude" / "agents" / "_context")
    return (await resolver.get(project, "evolutions_dir", "")
            or await resolver.get(project, "context_overrides_dir", "")
            or default_dir)


def _resolve_evolution_file(evolutions_dir: str, path: str) -> Path | None:
    """Resolve `path` relative to evolutions_dir with containment check."""
    if not evolutions_dir or not path:
        return None
    base = Path(evolutions_dir).resolve()
    if not base.exists():
        return None
    target = (base / path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target if target.exists() and target.is_file() else None


@router.get("/p/{slug}/evolutions")
async def evolutions_page(request: Request, slug: str):
    project = request.state.project
    evolutions_dir = await _resolve_evolutions_dir(request, project)
    items: list = []
    error: str | None = None
    if Path(evolutions_dir).exists():
        try:
            from dreaming.services.evolutions import list_evolutions
            raw = list_evolutions(evolutions_dir)
            items = [it.__dict__ if hasattr(it, "__dict__") else it for it in raw]
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    # Project-wide rubric aggregation (ALC-style stats panel).
    try:
        rubric_stats = collect_stats(evolutions_dir) if Path(evolutions_dir).exists() else ReportRubricStats()
    except Exception:
        rubric_stats = ReportRubricStats()
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_evolutions.html",
        {"project": project, "items": items, "evolutions_dir": evolutions_dir,
         "exists": Path(evolutions_dir).exists(), "error": error,
         "autoconfig_default": autoconfig.default_abs(project, "evolutions_dir"),
         "projects": projects, "locale": locale,
         "rubric_stats": rubric_stats},
    )


@router.get("/p/{slug}/evolutions/raw")
async def evolutions_raw(request: Request, slug: str, path: str):
    """Plain-text content of a single evolution markdown file. `path` is
    relative to evolutions_dir; path traversal is rejected."""
    project = request.state.project
    evolutions_dir = await _resolve_evolutions_dir(request, project)
    target = _resolve_evolution_file(evolutions_dir, path)
    if target is None:
        raise HTTPException(status_code=404, detail="evolution not found")
    try:
        return PlainTextResponse(target.read_text(encoding="utf-8"))
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"read failed: {e}")


@router.post("/p/{slug}/evolutions/status")
async def evolutions_set_status(
    request: Request, slug: str,
    path: str = Form(...), status: str = Form(...),
):
    project = request.state.project
    evolutions_dir = await _resolve_evolutions_dir(request, project)
    target = _resolve_evolution_file(evolutions_dir, path)
    value = status.strip()
    if target and value:
        set_frontmatter_field(target, "status", value)
    return RedirectResponse(f"/p/{project.slug}/evolutions", status_code=303)


@router.post("/p/{slug}/evolutions/delete")
async def evolutions_delete(request: Request, slug: str, path: str = Form(...)):
    project = request.state.project
    evolutions_dir = await _resolve_evolutions_dir(request, project)
    target = _resolve_evolution_file(evolutions_dir, path)
    if target is not None:
        try:
            target.unlink()
        except OSError:
            pass
    return RedirectResponse(f"/p/{project.slug}/evolutions", status_code=303)


@router.post("/p/{slug}/evolutions/apply")
async def evolutions_apply(
    request: Request, slug: str,
    path: str = Form(...), force: str | None = Form(default=None),
):
    """Spawn the Orchestrator with the evolution's proposed change + the
    current agent file, asking it to merge the change cleanly.

    Conflict-gate: if `list_evolutions` flags this item as conflicting with
    another open evolution targeting the same agent, refuse to apply unless
    the caller passes `force=1`. The check is intentionally on the server
    even though the UI also blocks the button — a stale browser tab or curl
    call must not bypass it.
    """
    project = request.state.project
    evolutions_dir = await _resolve_evolutions_dir(request, project)
    target = _resolve_evolution_file(evolutions_dir, path)
    if target is None:
        raise HTTPException(status_code=404, detail=f"evolution {path} not found")

    if not force:
        from dreaming.services.evolutions import list_evolutions
        items = list_evolutions(evolutions_dir)
        same = next((it for it in items if it.path == str(target)), None)
        if same and same.has_conflict:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Evolution '{same.name}' conflicts with another open evolution "
                    f"targeting agent '{same.agent_name}'. Archive or reject the other one, "
                    f"set 'conflict: false' in this file's frontmatter after manual review, "
                    f"or resubmit with force=1."
                ),
            )

    text = target.read_text(encoding="utf-8")
    # Pull agent name from frontmatter (parser already does this — we re-parse
    # cheaply here to avoid a second list_evolutions pass).
    import re
    m = re.search(r"(?m)^agent\s*:\s*(.+?)\s*$", text)
    agent_name = m.group(1).strip().strip("'\"") if m else target.parent.name
    agent_file = Path(project.working_dir) / ".claude" / "agents" / f"{agent_name}.md"
    goal = (
        f"Применить evolution-предложение к агент-файлу `{agent_file}`.\n\n"
        f"Содержание evolution-файла `{path}`:\n\n"
        f"{text[:5000]}\n\n"
        f"Шаги:\n"
        f"1. Прочитай текущий `{agent_file}` (если существует).\n"
        f"2. Примени правки из раздела «Proposed change» evolution-файла. "
        f"   Сохрани стиль и структуру существующего агент-файла.\n"
        f"3. Если изменение конфликтует с другими разделами — отметь это "
        f"   в конце агент-файла секцией «## Open questions» вместо переписывания.\n"
        f"4. Обнови frontmatter evolution-файла `{target}` на "
        f"   `status: applied` и добавь `applied_at: <today YYYY-MM-DD>`.\n"
        f"5. Заверши run."
    )
    from dreaming.services.orchestration_dispatch import start_orchestration_run
    result = await start_orchestration_run(request.app.state, project, goal)
    set_frontmatter_field(target, "orchestration_run", result["run_id"])
    return RedirectResponse(
        f"/p/{project.slug}/orchestration/{result['run_id']}", status_code=303,
    )


@router.post("/p/{slug}/evolutions/github")
async def evolutions_create_github(request: Request, slug: str, path: str = Form(...)):
    project = request.state.project
    evolutions_dir = await _resolve_evolutions_dir(request, project)
    target = _resolve_evolution_file(evolutions_dir, path)
    if target is None:
        raise HTTPException(status_code=404, detail=f"evolution {path} not found")
    text = target.read_text(encoding="utf-8")
    import re
    title_m = re.search(r"(?m)^title\s*:\s*['\"]?(.+?)['\"]?\s*$", text)
    agent_m = re.search(r"(?m)^agent\s*:\s*(.+?)\s*$", text)
    title = title_m.group(1).strip() if title_m else target.stem
    agent_name = agent_m.group(1).strip().strip("'\"") if agent_m else "?"
    dc_url = f"http://localhost:{request.app.state.settings.port}/p/{project.slug}/evolutions"
    issue_body = (
        f"Evolution proposal for agent `{agent_name}` from AI Dreaming Center — {dc_url}\n\n"
        f"{text[:5000]}"
    )
    resolver = request.app.state.resolver_factory(request)
    repo_override = await resolver.get(project, "github_repo", None) or None
    from dreaming.services.github_issues import create_issue, GitHubIssueError
    try:
        result = await create_issue(
            working_dir=project.working_dir,
            repo_override=repo_override,
            title=f"[{project.slug}] evolution[{agent_name}]: {title}",
            body=issue_body,
            labels=["evolution"],
        )
    except GitHubIssueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    set_frontmatter_field(target, "github_issue", result["url"])
    return RedirectResponse(f"/p/{project.slug}/evolutions", status_code=303)
