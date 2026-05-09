"""If `projects` table is empty AND request is not for /setup or /static or /health,
redirect to /setup."""
from __future__ import annotations
from fastapi import Request
from starlette.responses import RedirectResponse


_BYPASS_PREFIXES = ("/setup", "/static", "/health", "/api", "/docs", "/redoc", "/openapi")


async def setup_gate_middleware(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in _BYPASS_PREFIXES):
        return await call_next(request)

    projects = await request.app.state.projects.list_all()
    if not projects:
        return RedirectResponse(url="/setup", status_code=303)
    return await call_next(request)
