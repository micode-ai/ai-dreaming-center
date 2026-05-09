"""GET/POST /p/{slug}/settings — minimal per-project overrides for 5 keys.
Wave 2 will expand to full ~80-key UI."""
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse


router = APIRouter()


WAVE1_KEYS = ["claude_path", "model", "max_turns", "timeout_minutes", "self_study_command"]


@router.get("/p/{slug}/settings")
async def project_settings_page(request: Request, slug: str):
    project = request.state.project
    overrides = await request.app.state.projects.all_settings(project.id)
    global_settings = request.app.state.settings
    rows = []
    for k in WAVE1_KEYS:
        rows.append({
            "key": k,
            "global": getattr(global_settings, k, None),
            "override": overrides.get(k),
            "is_overridden": k in overrides,
        })
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_settings.html",
        {"project": project, "rows": rows, "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/settings")
async def project_settings_save(request: Request, slug: str):
    project = request.state.project
    form = await request.form()
    svc = request.app.state.projects
    for k in WAVE1_KEYS:
        action = form.get(f"action_{k}")
        if action == "inherit":
            await svc.unset_setting(project.id, k)
        elif action == "override":
            v_raw = (form.get(f"value_{k}") or "").strip()
            if v_raw:
                global_v = getattr(request.app.state.settings, k, "")
                try:
                    if isinstance(global_v, bool):
                        v = v_raw.lower() in ("true", "1", "yes", "on")
                    elif isinstance(global_v, int) and not isinstance(global_v, bool):
                        v = int(v_raw)
                    elif isinstance(global_v, float):
                        v = float(v_raw)
                    else:
                        v = v_raw
                except ValueError:
                    v = v_raw
                await svc.set_setting(project.id, k, v)
    return RedirectResponse(f"/p/{project.slug}/settings", status_code=303)
