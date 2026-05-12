"""GET /p/{slug}/ideas — product ideas board (read-only flat list).

POST /p/{slug}/ideas/{item_id}/jira — create Jira Task for a specific idea
and persist the resulting key back to the markdown file's frontmatter.
"""
from __future__ import annotations
import re
from pathlib import Path
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.services import autoconfig
from dreaming.services.frontmatter_io import set_frontmatter_field, find_md_file


router = APIRouter()


def _find_idea_file(ideas_dir: str, item_id: str) -> Path | None:
    return find_md_file(ideas_dir, item_id)


@router.get("/p/{slug}/ideas")
async def ideas_page(request: Request, slug: str, status: str | None = None):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    ideas_dir = await resolver.get(project, "product_ideas_dir", "")
    items = []
    error = None
    statuses: list[str] = []
    if ideas_dir and Path(ideas_dir).exists():
        try:
            from dreaming.services.product_ideas import list_product_ideas
            raw = list_product_ideas(ideas_dir)
            for it in raw:
                if hasattr(it, "__dict__"):
                    items.append(dict(it.__dict__))
                elif isinstance(it, dict):
                    items.append(it)
                else:
                    items.append({"raw": str(it)})
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        # Build status filter list
        statuses = sorted({(it.get("status") or "unknown") for it in items if isinstance(it, dict)})
    # Apply status filter
    if status:
        items = [it for it in items if (it.get("status") if isinstance(it, dict) else None) == status]
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_ideas.html",
        {"project": project, "items": items, "ideas_dir": ideas_dir,
         "ideas_dir_set": bool(ideas_dir),
         "ideas_dir_exists": bool(ideas_dir) and Path(ideas_dir).exists(),
         "autoconfig_default": autoconfig.default_abs(project, "product_ideas_dir"),
         "error": error, "statuses": statuses, "selected_status": status or "",
         "projects": projects, "locale": locale},
    )


@router.get("/p/{slug}/ideas/{item_id}")
async def ideas_detail(request: Request, slug: str, item_id: str):
    """Detail page for a single product idea: frontmatter meta + rendered markdown."""
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    ideas_dir = await resolver.get(project, "product_ideas_dir", "")
    item_dict: dict | None = None
    body_md = ""
    if ideas_dir and Path(ideas_dir).exists():
        from dreaming.services.product_ideas import list_product_ideas, read_product_idea
        try:
            for it in list_product_ideas(ideas_dir):
                obj = it.__dict__ if hasattr(it, "__dict__") else (it if isinstance(it, dict) else {})
                if obj.get("id") == item_id or obj.get("slug") == item_id:
                    item_dict = dict(obj)
                    break
        except Exception:
            item_dict = None
        if item_dict and item_dict.get("file_path"):
            try:
                _, body_md = read_product_idea(item_dict["file_path"])
            except Exception:
                body_md = ""
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_ideas_detail.html",
        {"project": project, "item_id": item_id, "item": item_dict,
         "body_md": body_md, "ideas_dir": ideas_dir,
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/ideas/scan")
async def ideas_scan(request: Request, slug: str):
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    try:
        await pm.start_command(
            project,
            command_name="product-idea-scan",
            prompt="/product-idea-scan",
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


@router.post("/p/{slug}/ideas/{item_id}/jira")
async def ideas_create_jira(request: Request, slug: str, item_id: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    ideas_dir = await resolver.get(project, "product_ideas_dir", "")
    if not ideas_dir:
        raise HTTPException(status_code=400, detail="product_ideas_dir not set")

    from dreaming.services.product_ideas import list_product_ideas
    items = list_product_ideas(ideas_dir)
    target = None
    for it in items:
        obj = it.__dict__ if hasattr(it, "__dict__") else (it if isinstance(it, dict) else {})
        if obj.get("id") == item_id or obj.get("slug") == item_id:
            target = obj
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"idea {item_id} not found")

    # Per-project jira_project_key override (or fall back to global)
    jira_pk_override = await resolver.get(project, "jira_project_key", None)
    if jira_pk_override == "":
        jira_pk_override = None

    summary = target.get("title", item_id)
    description = (target.get("body") or target.get("value_hypothesis") or "")[:3000]
    item_url = f"http://localhost:{request.app.state.settings.port}/p/{project.slug}/ideas"

    from dreaming.services.jira import create_task, JiraError
    try:
        result = await create_task(
            request.app.state.settings,
            summary=f"[{project.slug}] {summary}",
            item_id=item_id,
            item_url=item_url,
            description=description,
            project_key_override=jira_pk_override,
            kind="идея",
        )
        # Persist the resulting Jira key back to the markdown file frontmatter.
        for cand in [Path(ideas_dir) / f"{item_id}.md", Path(ideas_dir) / "items" / f"{item_id}.md"]:
            if cand.exists():
                text = cand.read_text(encoding="utf-8")
                new_text, n = re.subn(
                    r"(?m)^jira_ticket:\s*.*$", f"jira_ticket: {result['key']}", text, count=1
                )
                if n == 0 and text.startswith("---\n"):
                    end = text.find("\n---", 4)
                    if end > 0:
                        new_text = text[:end] + f"\njira_ticket: {result['key']}" + text[end:]
                cand.write_text(new_text, encoding="utf-8")
                break
    except JiraError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RedirectResponse(f"/p/{project.slug}/ideas", status_code=303)


@router.post("/p/{slug}/ideas/{item_id}/status")
async def ideas_set_status(
    request: Request, slug: str, item_id: str, status: str = Form(...),
):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    ideas_dir = await resolver.get(project, "product_ideas_dir", "")
    value = status.strip()
    if ideas_dir and value:
        path = _find_idea_file(ideas_dir, item_id)
        if path is not None:
            set_frontmatter_field(path, "status", value)
    return RedirectResponse(f"/p/{project.slug}/ideas", status_code=303)


@router.post("/p/{slug}/ideas/{item_id}/github")
async def ideas_create_github(request: Request, slug: str, item_id: str):
    """Create a GitHub issue from this idea + persist URL into frontmatter."""
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    ideas_dir = await resolver.get(project, "product_ideas_dir", "")
    if not ideas_dir:
        raise HTTPException(status_code=400, detail="product_ideas_dir not set")
    from dreaming.services.product_ideas import list_product_ideas, read_product_idea
    target = None
    for it in list_product_ideas(ideas_dir):
        obj = it.__dict__ if hasattr(it, "__dict__") else (it if isinstance(it, dict) else {})
        if obj.get("id") == item_id or obj.get("slug") == item_id:
            target = obj
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"idea {item_id} not found")
    path = _find_idea_file(ideas_dir, item_id)
    body_md = ""
    if path is not None:
        try:
            _, body_md = read_product_idea(str(path))
        except Exception:
            body_md = ""
    title = target.get("title") or item_id
    dc_url = f"http://localhost:{request.app.state.settings.port}/p/{project.slug}/ideas"
    issue_body = (
        f"From AI Dreaming Center product idea `{item_id}` — {dc_url}\n\n"
        f"{body_md[:5000]}"
    )
    labels = ["product-idea"]
    if target.get("priority"):
        labels.append(f"priority:{target['priority']}".lower())
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
    if path is not None:
        set_frontmatter_field(path, "github_issue", result["url"])
    return RedirectResponse(f"/p/{project.slug}/ideas", status_code=303)


@router.post("/p/{slug}/ideas/{item_id}/orchestrate")
async def ideas_send_to_orchestration(request: Request, slug: str, item_id: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    ideas_dir = await resolver.get(project, "product_ideas_dir", "")
    if not ideas_dir:
        raise HTTPException(status_code=400, detail="product_ideas_dir not set")
    from dreaming.services.product_ideas import list_product_ideas, read_product_idea
    target = None
    for it in list_product_ideas(ideas_dir):
        obj = it.__dict__ if hasattr(it, "__dict__") else (it if isinstance(it, dict) else {})
        if obj.get("id") == item_id or obj.get("slug") == item_id:
            target = obj
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"idea {item_id} not found")
    path = _find_idea_file(ideas_dir, item_id)
    body_md = ""
    if path is not None:
        try:
            _, body_md = read_product_idea(str(path))
        except Exception:
            body_md = ""
    title = target.get("title") or item_id
    goal = (
        f"Спроектируй и реализуй продуктовую идею: «{title}» (id `{item_id}`).\n\n"
        f"{body_md[:4000]}\n\n"
        f"Шаги: (1) разнеси задачи в `docs/plans/{item_id}-plan.md` с "
        f"чек-листом, (2) сформулируй контракты модулей в `docs/contracts/`, "
        f"(3) реализуй основной путь, (4) обнови frontmatter `status:` "
        f"в `{path}` на `building` (или `dropped`, если решил, что идея не годится)."
    )
    from dreaming.services.orchestration_dispatch import start_orchestration_run
    result = await start_orchestration_run(request.app.state, project, goal)
    if path is not None:
        set_frontmatter_field(path, "orchestration_run", result["run_id"])
    return RedirectResponse(
        f"/p/{project.slug}/orchestration/{result['run_id']}", status_code=303,
    )
