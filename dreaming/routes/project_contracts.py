"""GET  /p/{slug}/contracts                    — list of contract files.
GET  /p/{slug}/contracts/raw?path=X         — plain text of one contract.
GET  /p/{slug}/contracts/view?path=X        — detail page with rendered markdown.
POST /p/{slug}/contracts/scan               — run /contracts-scan slash-command.
POST /p/{slug}/contracts/status?path=X      — rewrite frontmatter `status:`.
POST /p/{slug}/contracts/delete?path=X      — unlink the markdown file.
POST /p/{slug}/contracts/orchestrate?path=X — audit contract via Orchestrator.
POST /p/{slug}/contracts/github?path=X      — create a GitHub issue from the contract.

Notes use the `path` query param (relative to contracts_dir) rather than a
`{name}` URL segment because contract files may be nested arbitrarily under
contracts_dir (the parser uses `rglob`).
"""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from dreaming.services import autoconfig
from dreaming.services.frontmatter_io import set_frontmatter_field


router = APIRouter()


def _resolve_contract(contracts_dir: str, relative_path: str) -> Path | None:
    if not contracts_dir or not relative_path:
        return None
    base = Path(contracts_dir).resolve()
    if not base.exists():
        return None
    target = (base / relative_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target if target.exists() and target.is_file() else None


@router.get("/p/{slug}/contracts")
async def contracts_page(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    obs_vault = await resolver.get(project, "obsidian_vault", "")
    default_dir = str(Path(obs_vault) / "03-Team" / "specs" / "contracts") if obs_vault else ""
    contracts_dir = await resolver.get(project, "contracts_dir", default_dir)
    items: list = []
    error: str | None = None
    if contracts_dir and Path(contracts_dir).exists():
        try:
            from dreaming.services.contracts import list_contracts
            raw = list_contracts(contracts_dir)
            items = [it.__dict__ for it in raw]
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_contracts.html",
        {"project": project, "items": items, "contracts_dir": contracts_dir,
         "contracts_dir_set": bool(contracts_dir),
         "exists": bool(contracts_dir) and Path(contracts_dir).exists(),
         "autoconfig_default": autoconfig.default_abs(project, "contracts_dir"),
         "error": error, "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/contracts/scan")
async def contracts_scan(request: Request, slug: str):
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    try:
        await pm.start_command(
            project,
            command_name="contracts-scan",
            prompt="/contracts-scan",
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


@router.get("/p/{slug}/contracts/raw")
async def contracts_raw(request: Request, slug: str, path: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    contracts_dir = await resolver.get(project, "contracts_dir", "")
    target = _resolve_contract(contracts_dir, path)
    if target is None:
        raise HTTPException(status_code=404, detail="contract not found")
    try:
        return PlainTextResponse(target.read_text(encoding="utf-8"))
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"read failed: {e}")


@router.get("/p/{slug}/contracts/view")
async def contracts_detail(request: Request, slug: str, path: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    contracts_dir = await resolver.get(project, "contracts_dir", "")
    item: dict | None = None
    body_md = ""
    if contracts_dir and Path(contracts_dir).exists():
        try:
            from dreaming.services.contracts import list_contracts, read_contract
            for it in list_contracts(contracts_dir):
                if it.relative_path == path:
                    item = dict(it.__dict__)
                    break
            result = read_contract(contracts_dir, path)
            if result is not None:
                _, body_md = result
        except Exception:
            pass
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_contracts_detail.html",
        {"project": project, "path": path, "item": item,
         "body_md": body_md, "contracts_dir": contracts_dir,
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/contracts/status")
async def contracts_set_status(
    request: Request, slug: str,
    path: str = Form(...), status: str = Form(...),
):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    contracts_dir = await resolver.get(project, "contracts_dir", "")
    target = _resolve_contract(contracts_dir, path)
    value = status.strip()
    if target and value:
        set_frontmatter_field(target, "status", value)
    return RedirectResponse(f"/p/{project.slug}/contracts", status_code=303)


@router.post("/p/{slug}/contracts/delete")
async def contracts_delete(request: Request, slug: str, path: str = Form(...)):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    contracts_dir = await resolver.get(project, "contracts_dir", "")
    target = _resolve_contract(contracts_dir, path)
    if target is not None:
        try:
            target.unlink()
        except OSError:
            pass
    return RedirectResponse(f"/p/{project.slug}/contracts", status_code=303)


@router.post("/p/{slug}/contracts/orchestrate")
async def contracts_orchestrate(request: Request, slug: str, path: str = Form(...)):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    contracts_dir = await resolver.get(project, "contracts_dir", "")
    target = _resolve_contract(contracts_dir, path)
    if target is None:
        raise HTTPException(status_code=404, detail=f"contract {path} not found")
    from dreaming.services.contracts import read_contract
    res = read_contract(contracts_dir, path)
    fm, body = res if res else ({}, "")
    title = fm.get("module") or fm.get("page") or path
    goal = (
        f"Аудит контракта `{path}` (module/page: {title}).\n\n"
        f"{body[:5000]}\n\n"
        f"Шаги:\n"
        f"1. Прочитай реальный код модуля/страницы.\n"
        f"2. Сверь с контрактом — что устарело, что отсутствует, что лишнее.\n"
        f"3. Обнови файл `{target}`. Сохрани frontmatter, обнови `last_review_at`, "
        f"при необходимости `status` (draft / active / deprecated).\n"
        f"4. Если найдены архитектурные противоречия, не описанные в контракте — "
        f"   добавь раздел «## Invariants» или «## Open questions»."
    )
    from dreaming.services.orchestration_dispatch import start_orchestration_run
    result = await start_orchestration_run(request.app.state, project, goal)
    set_frontmatter_field(target, "orchestration_run", result["run_id"])
    return RedirectResponse(
        f"/p/{project.slug}/orchestration/{result['run_id']}", status_code=303,
    )


@router.post("/p/{slug}/contracts/github")
async def contracts_create_github(request: Request, slug: str, path: str = Form(...)):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    contracts_dir = await resolver.get(project, "contracts_dir", "")
    target = _resolve_contract(contracts_dir, path)
    if target is None:
        raise HTTPException(status_code=404, detail=f"contract {path} not found")
    from dreaming.services.contracts import read_contract
    res = read_contract(contracts_dir, path)
    fm, body = res if res else ({}, "")
    title = fm.get("module") or fm.get("page") or path
    dc_url = f"http://localhost:{request.app.state.settings.port}/p/{project.slug}/contracts/view?path={path}"
    issue_body = (
        f"From AI Dreaming Center contract `{path}` — {dc_url}\n\n{body[:5000]}"
    )
    repo_override = await resolver.get(project, "github_repo", None) or None
    from dreaming.services.github_issues import create_issue, GitHubIssueError
    try:
        result = await create_issue(
            working_dir=project.working_dir,
            repo_override=repo_override,
            title=f"[{project.slug}] contract: {title}",
            body=issue_body,
            labels=["contract"],
        )
    except GitHubIssueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    set_frontmatter_field(target, "github_issue", result["url"])
    return RedirectResponse(f"/p/{project.slug}/contracts", status_code=303)
