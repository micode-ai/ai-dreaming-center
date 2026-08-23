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

router = APIRouter()


async def _render(request: Request, project=None):
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request,
        "help.html",
        {"project": project, "projects": projects, "locale": locale},
    )


@router.get("/help")
async def global_help(request: Request):
    return await _render(request)


@router.get("/p/{slug}/help")
async def project_help(request: Request, slug: str):
    return await _render(request, project=request.state.project)
