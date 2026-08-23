"""Parses /p/{slug}/ prefix; sets request.state.project; 404 on unknown slug.

Also loads the project's hidden-nav list onto `request.state.nav_hidden`. The
sidebar is rendered from `base.html` on every project page, so the alternative
was threading the same value through thirty route handlers -- one small query
here instead.
"""
from __future__ import annotations
from fastapi import Request
from fastapi.templating import Jinja2Templates

from dreaming.services.nav_sections import NAV_HIDDEN_KEY


async def project_resolver_middleware(request: Request, call_next):
    request.state.project = None
    request.state.nav_hidden = ()
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
    # A malformed stored value must not take the page down; the nav simply
    # falls back to showing everything.
    try:
        stored = await request.app.state.projects.get_setting(
            project.id, NAV_HIDDEN_KEY,
        )
        request.state.nav_hidden = tuple(stored) if isinstance(stored, list) else ()
    except Exception:
        request.state.nav_hidden = ()
    return await call_next(request)
