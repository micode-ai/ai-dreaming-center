"""Root-level routes: /, /health, /locale."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse


router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@router.get("/")
async def index(request: Request):
    projects = await request.app.state.projects.list_all(only_enabled=True)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    return request.app.state.templates.TemplateResponse(
        request,
        "index_placeholder.html",
        {"projects": projects, "locale": locale},
    )


@router.post("/locale")
async def set_locale(request: Request, locale: str = Form(...), next: str = Form("/")):
    if locale not in ("ru", "en"):
        locale = "ru"
    resp = RedirectResponse(url=next or "/", status_code=303)
    resp.set_cookie("dc_locale", locale, max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax")
    return resp
