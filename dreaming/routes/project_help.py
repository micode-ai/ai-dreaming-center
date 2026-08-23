"""Help / reference pages.

`/help` is the canonical one: what this tool is and what each section does is
the same answer whichever project you happen to have selected, so it must not
require picking one first. `/p/{slug}/help` renders the same page with the
project in context, which lets the agents card name that project's real
`.claude/agents/` path instead of a placeholder — and keeps older links and
the per-project nav working.
"""
from __future__ import annotations
from fastapi import APIRouter, Request

from dreaming.services import help_content
from dreaming.services.nav_sections import (
    GLOBAL_SECTIONS, NAV_HIDDEN_KEY, PROJECT_SECTIONS,
)

router = APIRouter()


async def _render(request: Request, project=None):
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    # Help lists every section, including the ones this project hid from its
    # sidebar. This is where you decide whether you need a section at all, so
    # filtering it the way the nav is filtered would make what you switched off
    # undiscoverable. They are marked instead.
    hidden: set[str] = set()
    if project is not None:
        stored = await request.app.state.projects.get_setting(
            project.id, NAV_HIDDEN_KEY,
        )
        if isinstance(stored, list):
            hidden = set(stored)
    return request.app.state.templates.TemplateResponse(
        request,
        "help.html",
        {
            "project": project,
            "projects": projects,
            "locale": locale,
            "global_sections": GLOBAL_SECTIONS,
            # key -> markdown. A section with nothing written yet simply has
            # no entry, and the template renders it as a plain card.
            "bodies": {
                s.key: body
                for s in (*GLOBAL_SECTIONS, *PROJECT_SECTIONS)
                if (body := help_content.get(s.key, locale)) is not None
            },
            # Without a project there is nowhere for these to point, so the
            # template renders them as plain cards next to the pick-a-project
            # hint rather than as dead links.
            "project_sections": PROJECT_SECTIONS,
            "project_base": f"/p/{project.slug}" if project else "",
            "hidden_sections": hidden,
        },
    )


@router.get("/help")
async def global_help(request: Request):
    return await _render(request)


@router.get("/p/{slug}/help")
async def project_help(request: Request, slug: str):
    return await _render(request, project=request.state.project)
