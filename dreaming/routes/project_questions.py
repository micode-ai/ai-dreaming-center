"""GET /p/{slug}/questions — list pending + recently-answered AskUserQuestion rows.
POST /p/{slug}/questions/{id}/answer — submit an answer (from the UI form).
POST /p/{slug}/questions/{id}/dismiss — close without answering.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse


router = APIRouter()


def _enrich(row) -> dict:
    """Parse questions_json blob into a usable structure."""
    d = dict(row)
    try:
        d["parsed"] = json.loads(d.get("questions_json") or "{}")
    except Exception:
        d["parsed"] = {"question": d.get("questions_json", ""), "options": []}
    return d


@router.get("/p/{slug}/questions")
async def questions_page(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    pending = [_enrich(r) for r in await db.list_questions(project.id, status="pending", limit=50)]
    answered = [_enrich(r) for r in await db.list_questions(project.id, status="answered", limit=20)]
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request, "project_questions.html",
        {"project": project, "pending": pending, "answered": answered,
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/questions/{question_id}/answer")
async def question_answer(
    request: Request, slug: str, question_id: str,
    answer: str = Form(...),
):
    project = request.state.project
    db = request.app.state.db
    row = await db.get_question(question_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="question not found")
    await db.answer_question(question_id, answer_text=answer.strip(), status="answered")
    return RedirectResponse(f"/p/{project.slug}/questions", status_code=303)


@router.post("/p/{slug}/questions/{question_id}/dismiss")
async def question_dismiss(request: Request, slug: str, question_id: str):
    project = request.state.project
    db = request.app.state.db
    row = await db.get_question(question_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="question not found")
    await db.answer_question(question_id, answer_text="", status="dismissed")
    return RedirectResponse(f"/p/{project.slug}/questions", status_code=303)
