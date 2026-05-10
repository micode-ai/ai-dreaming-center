"""Global settings UI — full ~80-key form grouped by category."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import yaml

from dreaming.config import SETTINGS_GROUPS


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


def _coerce(raw: str, default_value):
    """Coerce form string back to default's type."""
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


@router.get("/settings")
async def settings_get(request: Request):
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    current = _settings_to_dict(request.app.state.settings)
    return request.app.state.templates.TemplateResponse(
        request, "settings.html",
        {"current": current, "groups": SETTINGS_GROUPS,
         "locale": locale, "projects": []},
    )


@router.post("/settings")
async def settings_post(request: Request):
    form = await request.form()
    new_values = {}
    settings = request.app.state.settings
    for k in settings.model_fields:
        if k in form:
            current_val = getattr(settings, k)
            # Boolean fields: missing key on form means False (unchecked checkbox)
            # but text fields with empty input mean keep-empty-string.
            new_values[k] = _coerce(form[k] or "", current_val)
        elif isinstance(getattr(settings, k), bool):
            # Unchecked checkbox — explicit False
            new_values[k] = False
    _save_yaml(new_values)
    request.app.state.settings = type(settings).load()
    return RedirectResponse("/settings", status_code=303)
