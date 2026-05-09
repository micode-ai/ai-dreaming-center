"""Global settings UI (Wave 0 minimal — Wave 1 expands to full ~80-key form)."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import yaml


router = APIRouter()


def _settings_to_dict(settings) -> dict:
    out = {}
    for f in settings.model_fields:
        out[f] = getattr(settings, f)
    return out


def _save_yaml(values: dict) -> None:
    p = Path("config.yaml")
    cur = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    cur = cur or {}
    cur.update(values)
    p.write_text(yaml.safe_dump(cur, allow_unicode=True), encoding="utf-8")


@router.get("/settings")
async def settings_get(request: Request):
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    return request.app.state.templates.TemplateResponse(
        request,
        "settings.html",
        {"current": _settings_to_dict(request.app.state.settings),
         "locale": locale, "projects": []},
    )


@router.post("/settings")
async def settings_post(request: Request):
    form = await request.form()
    new_values = {}
    for k in request.app.state.settings.model_fields:
        if k in form:
            new_values[k] = form[k]
    _save_yaml(new_values)
    request.app.state.settings = type(request.app.state.settings).load()
    return RedirectResponse("/settings", status_code=303)
