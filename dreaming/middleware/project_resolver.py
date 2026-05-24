"""Parses /p/{slug}/ prefix; sets request.state.project; 404 on unknown slug."""
from __future__ import annotations
from fastapi import Request
from fastapi.templating import Jinja2Templates


async def project_resolver_middleware(request: Request, call_next):
    request.state.project = None
    path = request.url.path
    if not path.startswith("/p/"):
        return await call_next(request)

    parts = path.split("/", 3)  # ['', 'p', slug, rest_or_empty]
    if len(parts) < 3 or not parts[2]:
        return await call_next(request)

    slug = parts[2]
    project = await request.app.state.projects.get_by_slug(slug)
    if project is None or not project.enabled:
        templates: Jinja2Templates = request.app.state.templates
        locale = request.cookies.get(
            "dc_locale", request.app.state.settings.default_locale)
        return templates.TemplateResponse(
            request,
            "project_not_found.html",
            {"slug": slug,
             "is_disabled": project is not None and not project.enabled,
             "locale": locale},
            status_code=404,
        )
    request.state.project = project
    return await call_next(request)
