"""GET  /p/{slug}/plans                          — list of plan files.
GET  /p/{slug}/plans/{name}                   — detail page with rendered markdown.
GET  /p/{slug}/plans/raw?name=X               — plain-text content of one plan.
POST /p/{slug}/plans/extract                  — run /plans-extract slash-command.
POST /p/{slug}/plans/{name}/status            — rewrite frontmatter `status:` line.
POST /p/{slug}/plans/{name}/delete            — unlink the markdown file.
POST /p/{slug}/plans/{name}/orchestrate       — send the plan to the Orchestrator.
POST /p/{slug}/plans/{name}/github            — create a GitHub issue from the plan.
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from dreaming.services import autoconfig
from dreaming.services.frontmatter_io import set_frontmatter_field


router = APIRouter()


def _resolve_plan_file(plans_dir: str, name: str) -> Path | None:
    if not plans_dir or not name:
        return None
    base = Path(plans_dir).resolve()
    if not base.exists():
        return None
    if name.endswith(".md"):
        name = name[:-3]
    target = (base / f"{name}.md").resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target if target.exists() and target.is_file() else None


@router.get("/p/{slug}/plans")
async def plans_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    obs_vault = await resolver.get(project, "obsidian_vault", "")
    default_dir = str(Path(obs_vault) / "03-Team" / "plans") if obs_vault else ""
    plans_dir = await resolver.get(project, "plans_dir", default_dir)
    items: list = []
    error: str | None = None
    if plans_dir and Path(plans_dir).exists():
        try:
            from dreaming.services.plans import list_plans
            raw = list_plans(plans_dir)
            items = [it.__dict__ for it in raw]
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_plans.html",
        {"project": project, "items": items, "plans_dir": plans_dir,
         "plans_dir_set": bool(plans_dir),
         "exists": bool(plans_dir) and Path(plans_dir).exists(),
         "autoconfig_default": autoconfig.default_abs(project, "plans_dir"),
         "error": error, "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/plans/extract")
async def plans_extract(request: Request, slug: str):
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    try:
        await pm.start_command(
            project,
            command_name="plans-extract",
            prompt="/plans-extract",
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


@router.get("/p/{slug}/plans/raw")
async def plans_raw(request: Request, slug: str, name: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    plans_dir = await resolver.get(project, "plans_dir", "")
    target = _resolve_plan_file(plans_dir, name)
    if target is None:
        raise HTTPException(status_code=404, detail="plan not found")
    try:
        return PlainTextResponse(target.read_text(encoding="utf-8"))
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"read failed: {e}")


@router.get("/p/{slug}/plans/{name}")
async def plans_detail(request: Request, slug: str, name: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    plans_dir = await resolver.get(project, "plans_dir", "")
    item: dict | None = None
    body_md = ""
    if plans_dir and Path(plans_dir).exists():
        try:
            from dreaming.services.plans import list_plans, read_plan
            for it in list_plans(plans_dir):
                if it.name == name:
                    item = dict(it.__dict__)
                    break
            result = read_plan(plans_dir, name)
            if result is not None:
                _, body_md = result
        except Exception:
            pass
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_plans_detail.html",
        {"project": project, "name": name, "item": item,
         "body_md": body_md, "plans_dir": plans_dir,
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/plans/{name}/status")
async def plans_set_status(
    request: Request, slug: str, name: str, status: str = Form(...),
):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    plans_dir = await resolver.get(project, "plans_dir", "")
    target = _resolve_plan_file(plans_dir, name)
    value = status.strip()
    if target and value:
        set_frontmatter_field(target, "status", value)
    return RedirectResponse(f"/p/{project.slug}/plans", status_code=303)


@router.post("/p/{slug}/plans/{name}/delete")
async def plans_delete(request: Request, slug: str, name: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    plans_dir = await resolver.get(project, "plans_dir", "")
    target = _resolve_plan_file(plans_dir, name)
    if target is not None:
        try:
            target.unlink()
        except OSError:
            pass
    return RedirectResponse(f"/p/{project.slug}/plans", status_code=303)


@router.post("/p/{slug}/plans/{name}/orchestrate")
async def plans_send_to_orchestration(request: Request, slug: str, name: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    plans_dir = await resolver.get(project, "plans_dir", "")
    target = _resolve_plan_file(plans_dir, name)
    if target is None:
        raise HTTPException(status_code=404, detail=f"plan {name} not found")
    from dreaming.services.plans import read_plan
    res = read_plan(plans_dir, name)
    fm, body = res if res else ({}, "")
    title = fm.get("title") or name
    goal = (
        f"Продолжай выполнение плана: «{title}» (`{name}.md`).\n\n"
        f"{body[:5000]}\n\n"
        f"Закрой как можно больше открытых `- [ ]` пунктов. После каждой "
        f"завершённой задачи обнови чек-бокс в `{target}` на `- [x]`. "
        f"Когда все пункты закрыты — обнови frontmatter `status:` на `done` "
        f"и заверши run через POST /api/orchestration/$DREAMING_RUN_ID/finish."
    )
    from dreaming.services.orchestration_dispatch import start_orchestration_run
    result = await start_orchestration_run(request.app.state, project, goal)
    set_frontmatter_field(target, "orchestration_run", result["run_id"])
    return RedirectResponse(
        f"/p/{project.slug}/orchestration/{result['run_id']}", status_code=303,
    )


@router.post("/p/{slug}/plans/{name}/github")
async def plans_create_github(request: Request, slug: str, name: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    plans_dir = await resolver.get(project, "plans_dir", "")
    target = _resolve_plan_file(plans_dir, name)
    if target is None:
        raise HTTPException(status_code=404, detail=f"plan {name} not found")
    from dreaming.services.plans import read_plan
    res = read_plan(plans_dir, name)
    fm, body = res if res else ({}, "")
    title = fm.get("title") or name
    dc_url = f"http://localhost:{request.app.state.settings.port}/p/{project.slug}/plans/{name}"
    issue_body = (
        f"From AI Dreaming Center plan `{name}` — {dc_url}\n\n{body[:5000]}"
    )
    repo_override = await resolver.get(project, "github_repo", None) or None
    from dreaming.services.github_issues import create_issue, GitHubIssueError
    try:
        result = await create_issue(
            working_dir=project.working_dir,
            repo_override=repo_override,
            title=f"[{project.slug}] {title}",
            body=issue_body,
            labels=["plan"],
        )
    except GitHubIssueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    set_frontmatter_field(target, "github_issue", result["url"])
    return RedirectResponse(f"/p/{project.slug}/plans", status_code=303)
