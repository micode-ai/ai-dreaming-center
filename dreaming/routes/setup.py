"""Multi-step (single page, two phases) setup wizard."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import yaml

from dreaming.services.projects import ProjectsService


router = APIRouter()


def _save_global_yaml(values: dict) -> None:
    """Merge values into config.yaml (create if missing)."""
    p = Path("config.yaml")
    cur = {}
    if p.exists():
        cur = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cur.update(values)
    p.write_text(yaml.safe_dump(cur, allow_unicode=True), encoding="utf-8")


@router.get("/setup")
async def setup_get(request: Request):
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    s = request.app.state.settings
    defaults = type("D", (), dict(
        claude_path=getattr(s, "claude_path", "") or "claude",
        projects_root=getattr(s, "projects_root", "") or r"D:\Work\micode",
        default_locale=getattr(s, "default_locale", "ru") or "ru",
    ))()
    return request.app.state.templates.TemplateResponse(
        request,
        "setup.html",
        {
            "defaults": defaults,
            "scan": None,
            "scan_root": None,
            "locale": locale,
            "scan_error": None,
        },
    )


@router.post("/setup")
async def setup_post(request: Request):
    form = await request.form()
    action = form.get("action")
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)

    if action == "scan":
        root = (form.get("projects_root") or "").strip()
        scan = ProjectsService.scan_projects_root(root) if root else []
        scan_error = None
        if not root:
            scan_error = "projects_root не указан — впиши абсолютный путь, например D:\\Work\\micode"
        elif not scan:
            scan_error = f"В каталоге {root} не найдено подпапок (или каталог не существует)"
        defaults = type("D", (), dict(
            claude_path=form.get("claude_path", request.app.state.settings.claude_path),
            projects_root=root or request.app.state.settings.projects_root,
            default_locale=form.get("default_locale", request.app.state.settings.default_locale),
        ))()
        return request.app.state.templates.TemplateResponse(
            request,
            "setup.html",
            {
                "defaults": defaults,
                "scan": scan if scan else None,
                "scan_root": root,
                "scan_error": scan_error,
                "locale": locale,
            },
        )

    globals_to_save = {
        "claude_path": form.get("claude_path", "").strip() or "claude",
        "projects_root": form.get("projects_root", "").strip(),
        "default_locale": form.get("default_locale", "ru"),
    }
    _save_global_yaml(globals_to_save)
    request.app.state.settings = type(request.app.state.settings).load()

    n = int(form.get("scan_count", 0))
    default_idx = form.get("default_idx")
    items = []
    for i in range(n):
        if not form.get(f"enabled_{i}"):
            continue
        items.append({
            "slug": form.get(f"slug_{i}", "").strip(),
            "label": form.get(f"label_{i}", "").strip(),
            "working_dir": form.get(f"path_{i}", "").strip(),
            "enabled": True,
        })

    if items:
        default_slug = None
        if default_idx is not None:
            try:
                idx = int(default_idx)
                if form.get(f"enabled_{idx}"):
                    default_slug = form.get(f"slug_{idx}", "").strip()
            except ValueError:
                pass
        created = await request.app.state.projects.import_from_scan(items, default_slug=default_slug)
        if created:
            from dreaming.services.scheduler import register_project_jobs
            for proj in created:
                await register_project_jobs(request.app.state.scheduler, request.app.state, proj)

    return RedirectResponse(url="/", status_code=303)
