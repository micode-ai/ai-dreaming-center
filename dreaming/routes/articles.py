"""GET /articles — кросс-проектная очередь предложений в статусе proposed.

Ради этого экрана предложения лежат в БД центра, а не в файлах проектов:
один запрос вместо обхода одиннадцати рабочих каталогов.
"""
from __future__ import annotations
from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/articles")
async def articles_queue(request: Request):
    db = request.app.state.db
    rows = await db.list_article_proposals(status="proposed")
    projects = await request.app.state.projects.list_all(only_enabled=True)
    by_id = {p.id: p for p in projects}
    enabled_project_ids = [p.id for p in projects]
    items = []
    for r in rows:
        d = dict(r)
        project = by_id.get(d["project_id"])
        if project is None:
            continue  # проект отключён или удалён — в очереди не показываем
        d["project_slug"] = project.slug
        d["project_label"] = project.label
        items.append(d)
    # Get the true count of proposed articles in enabled projects only
    true_total = await db.count_article_proposals(
        status="proposed", project_ids=enabled_project_ids,
    )
    shown = len(items)
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale,
    )
    return request.app.state.templates.TemplateResponse(
        request, "articles.html",
        {
            "items": items, "projects": projects, "locale": locale,
            "total": true_total, "shown": shown, "capped": shown < true_total,
        },
    )
