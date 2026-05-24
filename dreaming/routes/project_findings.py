"""GET /p/{slug}/findings — flat tech-debt list + detail page + bulk close/delete.

POST /p/{slug}/findings/{id}/status   — change status (open|in-progress|closed|...)
POST /p/{slug}/findings/{id}/github   — create GitHub issue + persist URL
POST /p/{slug}/findings/{id}/orchestrate — send to Orchestrator as goal
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.services import autoconfig
from dreaming.services.frontmatter_io import set_frontmatter_field, find_md_file


router = APIRouter()


def _default_td_dir(project) -> str:
    # Default fallback: project's own .claude/agents/findings or empty
    return ""


@router.get("/p/{slug}/findings")
async def findings_page(
    request: Request, slug: str,
    status: str | None = None, module: str | None = None,
):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", _default_td_dir(project))
    items = []
    error = None
    statuses: list[str] = []
    modules: list[str] = []
    if td_dir and Path(td_dir).exists():
        try:
            from dreaming.services.tech_debt import list_tech_debt
            raw = list_tech_debt(td_dir)
            for it in raw:
                if hasattr(it, "__dict__"):
                    items.append(dict(it.__dict__))
                elif isinstance(it, dict):
                    items.append(it)
                else:
                    items.append({"raw": str(it)})
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        statuses = sorted({(it.get("status") or "open") for it in items if isinstance(it, dict)})
        modules = sorted({(it.get("module") or "") for it in items if isinstance(it, dict) and it.get("module")})
    if status:
        items = [it for it in items if (it.get("status") or "open") == status]
    if module:
        items = [it for it in items if (it.get("module") or "") == module]
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    pm = request.app.state.process_manager
    scan_running = f"cmd:{project.slug}:tech-debt-scan" in pm.list_running()
    return request.app.state.templates.TemplateResponse(
        request, "project_findings.html",
        {"project": project, "items": items, "td_dir": td_dir,
         "td_dir_set": bool(td_dir), "td_dir_exists": bool(td_dir) and Path(td_dir).exists(),
         "autoconfig_default": autoconfig.default_abs(project, "tech_debt_dir"),
         "statuses": statuses, "modules": modules,
         "selected_status": status or "", "selected_module": module or "",
         "error": error, "scan_running": scan_running,
         "projects": projects, "locale": locale},
    )


@router.get("/p/{slug}/findings/{item_id}")
async def findings_detail(request: Request, slug: str, item_id: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    item = None
    body_md = ""
    item_dict: dict | None = None
    if td_dir and Path(td_dir).exists():
        try:
            from dreaming.services.tech_debt import read_tech_debt_item, read_td
            item = read_tech_debt_item(td_dir, item_id)
            if item is not None:
                item_dict = dict(item.__dict__) if hasattr(item, "__dict__") else (item if isinstance(item, dict) else None)
                # Pull body via read_td using the file_path from the parsed item.
                fp = item_dict.get("file_path") if item_dict else None
                if fp:
                    try:
                        _, body_md = read_td(fp)
                    except Exception:
                        body_md = ""
        except Exception:
            item = None
            item_dict = None
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_findings_detail.html",
        {"project": project, "item_id": item_id,
         "item": item_dict,
         "body_md": body_md, "td_dir": td_dir,
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/findings/{item_id}/close")
async def findings_close(request: Request, slug: str, item_id: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    if td_dir:
        from dreaming.services.tech_debt import close_tech_debt_item
        close_tech_debt_item(td_dir, item_id)
    return RedirectResponse(f"/p/{project.slug}/findings", status_code=303)


@router.post("/p/{slug}/findings/{item_id}/delete")
async def findings_delete(request: Request, slug: str, item_id: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    if td_dir:
        from dreaming.services.tech_debt import delete_tech_debt_item
        delete_tech_debt_item(td_dir, item_id)
    return RedirectResponse(f"/p/{project.slug}/findings", status_code=303)


@router.post("/p/{slug}/findings/{item_id}/status")
async def findings_set_status(
    request: Request, slug: str, item_id: str, status: str = Form(...),
):
    """Rewrite frontmatter `status:` line. Accepts any value — open / in-progress
    / closed / dropped / blocked / ... — caller's responsibility to pick sane values."""
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    value = status.strip()
    if td_dir and value:
        from dreaming.services.tech_debt import read_tech_debt_item
        item = read_tech_debt_item(td_dir, item_id)
        fp = getattr(item, "file_path", None) if item else None
        path = find_md_file(td_dir, item_id, fallback_paths=[fp] if fp else None)
        if path is not None:
            set_frontmatter_field(path, "status", value)
    return RedirectResponse(f"/p/{project.slug}/findings", status_code=303)


@router.post("/p/{slug}/findings/{item_id}/github")
async def findings_create_github(request: Request, slug: str, item_id: str):
    """Create a GitHub issue from this finding and persist its URL into frontmatter."""
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    if not td_dir:
        raise HTTPException(status_code=400, detail="tech_debt_dir not set")
    from dreaming.services.tech_debt import read_tech_debt_item, read_td
    item = read_tech_debt_item(td_dir, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"finding {item_id} not found")
    item_dict = dict(item.__dict__) if hasattr(item, "__dict__") else (item if isinstance(item, dict) else {})
    title = item_dict.get("title") or item_id
    fp = item_dict.get("file_path")
    body_md = ""
    if fp:
        try:
            _, body_md = read_td(fp)
        except Exception:
            body_md = ""
    dc_url = f"http://localhost:{request.app.state.settings.port}/p/{project.slug}/findings/{item_id}"
    issue_body = (
        f"From AI Dreaming Center finding `{item_id}` — {dc_url}\n\n"
        f"{body_md[:5000]}"
    )
    labels = ["tech-debt"]
    if item_dict.get("priority"):
        labels.append(f"priority:{item_dict['priority']}".lower())
    repo_override = await resolver.get(project, "github_repo", None) or None
    from dreaming.services.github_issues import create_issue, GitHubIssueError
    try:
        result = await create_issue(
            working_dir=project.working_dir,
            repo_override=repo_override,
            title=f"[{project.slug}] {title}",
            body=issue_body,
            labels=labels,
        )
    except GitHubIssueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    path = find_md_file(td_dir, item_id, fallback_paths=[fp] if fp else None)
    if path is not None:
        set_frontmatter_field(path, "github_issue", result["url"])
    return RedirectResponse(f"/p/{project.slug}/findings", status_code=303)


@router.post("/p/{slug}/findings/{item_id}/orchestrate")
async def findings_send_to_orchestration(request: Request, slug: str, item_id: str):
    """Spawn the Orchestrator with this finding as the goal."""
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    if not td_dir:
        raise HTTPException(status_code=400, detail="tech_debt_dir not set")
    from dreaming.services.tech_debt import read_tech_debt_item, read_td
    item = read_tech_debt_item(td_dir, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"finding {item_id} not found")
    item_dict = dict(item.__dict__) if hasattr(item, "__dict__") else {}
    title = item_dict.get("title") or item_id
    fp = item_dict.get("file_path")

    # Idempotency: reuse the previously linked run instead of starting a duplicate
    # (handles double-click and re-click on the same finding).
    existing_run_id = (item_dict.get("orchestration_run") or "").strip()
    if existing_run_id:
        hub = request.app.state.orchestration_hub
        existing_row = await hub.get_run(existing_run_id)
        if existing_row is not None and existing_row["project_id"] == project.id:
            return RedirectResponse(
                f"/p/{project.slug}/orchestration?run_id={existing_run_id}",
                status_code=303,
            )

    body_md = ""
    if fp:
        try:
            _, body_md = read_td(fp)
        except Exception:
            body_md = ""
    goal = (
        f"Реши tech-debt: «{title}» (id `{item_id}`).\n\n"
        f"{body_md[:4000]}\n\n"
        f"Когда закончишь, обнови frontmatter `status:` в "
        f"`{fp or (td_dir + '/' + item_id + '.md')}` на `closed` "
        f"(или `dropped`, если решил, что это не баг)."
    )
    from dreaming.services.orchestration_dispatch import start_orchestration_run
    result = await start_orchestration_run(request.app.state, project, goal)
    # Persist a backlink so the finding remembers which run took it on.
    path = find_md_file(td_dir, item_id, fallback_paths=[fp] if fp else None)
    if path is not None:
        set_frontmatter_field(path, "orchestration_run", result["run_id"])
    return RedirectResponse(
        f"/p/{project.slug}/orchestration?run_id={result['run_id']}", status_code=303,
    )
