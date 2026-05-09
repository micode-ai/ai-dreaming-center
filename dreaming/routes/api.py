"""REST API for slash-command callbacks. Multi-tenant via project_slug body."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class SessionStartIn(BaseModel):
    project_slug: str | None = None
    agent_name: str
    model: str = "sonnet"


class SessionFinishIn(BaseModel):
    session_id: str
    status: str
    topic: str | None = None
    confidence: float | None = None
    note_path: str | None = None
    error_message: str | None = None
    entity_page: str | None = None
    tokens_total: int | None = None


async def _resolve_project(request: Request, slug: str | None):
    if slug:
        proj = await request.app.state.projects.get_by_slug(slug)
        if proj is None:
            raise HTTPException(status_code=404, detail=f"project '{slug}' not found")
        return proj
    default = await request.app.state.projects.get_default()
    if default is None:
        raise HTTPException(status_code=400, detail="no default project; pass project_slug")
    log.warning("session API call without project_slug; using default '%s'", default.slug)
    return default


@router.post("/session/start")
async def session_start(request: Request, payload: SessionStartIn):
    project = await _resolve_project(request, payload.project_slug)
    sid = await request.app.state.db.create_session(
        project.id, payload.agent_name, payload.model
    )
    return JSONResponse({"id": sid})


@router.post("/session/finish")
async def session_finish(request: Request, payload: SessionFinishIn):
    db = request.app.state.db
    ok = await db.finish_session(
        payload.session_id,
        status=payload.status,
        topic=payload.topic,
        confidence=payload.confidence,
        note_path=payload.note_path,
        error_message=payload.error_message,
        entity_page=payload.entity_page,
        tokens_total=payload.tokens_total,
    )
    return JSONResponse({"ok": True, "found": ok})
