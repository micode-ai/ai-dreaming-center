"""GET/POST /p/{slug}/settings — full per-project overrides for ~80 keys."""
from __future__ import annotations
from urllib.parse import urlparse
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.config import SETTINGS_GROUPS
from dreaming.services import autoconfig


router = APIRouter()


@router.post("/p/{slug}/settings/autoconfig")
async def project_settings_autoconfig(
    request: Request, slug: str,
    key: str = Form(...),
    redirect_to: str | None = Form(default=None),
):
    """Create the default directory for `key` and save the setting. Returns to
    referer (or the explicit redirect_to) so the user lands back on the page
    that triggered the action."""
    project = request.state.project
    if key not in autoconfig.DEFAULTS:
        raise HTTPException(status_code=400, detail=f"unknown autoconfig key '{key}'")
    await autoconfig.apply(request.app.state.projects, project, key)
    raw = redirect_to or request.headers.get("referer") or ""
    path = urlparse(raw).path if raw else ""
    if not path.startswith(f"/p/{project.slug}"):
        path = f"/p/{project.slug}/"
    return RedirectResponse(path, status_code=303)


def _coerce(raw: str, default_value):
    if isinstance(default_value, bool):
        return raw.lower() in ("true", "1", "yes", "on")
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        try:
            return int(raw)
        except ValueError:
            return default_value
    if isinstance(default_value, float):
        try:
            return float(raw)
        except ValueError:
            return default_value
    return raw


@router.get("/p/{slug}/settings")
async def project_settings_page(request: Request, slug: str):
    project = request.state.project
    overrides = await request.app.state.projects.all_settings(project.id)
    global_settings = request.app.state.settings

    rows = []
    for group_name, keys in SETTINGS_GROUPS:
        group_rows = []
        for k in keys:
            global_v = getattr(global_settings, k, None)
            override_v = overrides.get(k)
            group_rows.append({
                "key": k,
                "global": global_v,
                "override": override_v,
                "is_overridden": k in overrides,
                "is_bool": isinstance(global_v, bool),
            })
        rows.append((group_name, group_rows))

    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_settings.html",
        {"project": project, "groups": rows,
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/settings")
async def project_settings_save(request: Request, slug: str):
    project = request.state.project
    form = await request.form()
    svc = request.app.state.projects
    settings = request.app.state.settings

    for group_name, keys in SETTINGS_GROUPS:
        for k in keys:
            action = form.get(f"action_{k}")
            if action == "inherit":
                await svc.unset_setting(project.id, k)
            elif action == "override":
                # Bool keys: checkbox value or absent = treat absence as False
                global_v = getattr(settings, k, "")
                if isinstance(global_v, bool):
                    raw = form.get(f"value_{k}", "")
                    val = raw.lower() in ("true", "on", "1", "yes")
                    await svc.set_setting(project.id, k, val)
                else:
                    raw = (form.get(f"value_{k}") or "").strip()
                    if raw:
                        val = _coerce(raw, global_v)
                        await svc.set_setting(project.id, k, val)
                    else:
                        # empty override → treat as unset
                        await svc.unset_setting(project.id, k)
    return RedirectResponse(f"/p/{project.slug}/settings", status_code=303)
