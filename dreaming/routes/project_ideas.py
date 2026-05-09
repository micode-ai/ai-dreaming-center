"""GET /p/{slug}/ideas — product ideas board (read-only flat list).

POST /p/{slug}/ideas/{item_id}/jira — create Jira Task for a specific idea
and persist the resulting key back to the markdown file's frontmatter.
"""
from __future__ import annotations
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse


router = APIRouter()


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
         "error": error, "statuses": statuses, "selected_status": status or "",
         "projects": projects, "locale": locale},
    )


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
