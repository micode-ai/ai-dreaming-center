"""REST API for slash-command callbacks. Multi-tenant via project_slug body."""
from __future__ import annotations
import logging
import uuid
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


# -- Orchestration API (Wave 3 lean) -----------------------------

class OrchStartIn(BaseModel):
    project_slug: str | None = None
    goal: str
    external_id: str | None = None
    # If true, fail with 409 when another run is already running on this project.
    enforce_single: bool = True


class OrchAppendMessageIn(BaseModel):
    node_id: str | None = None
    author: str = "agent"   # "agent" | "user" | "system"
    kind: str = "text"      # "text" | "tool_use" | "tool_result" | etc.
    text: str
    client_message_id: str | None = None


class OrchFinishIn(BaseModel):
    status: str = "completed"   # "completed" | "failed" | "cancelled"
    error_message: str | None = None


@router.post("/orchestration/start")
async def orchestration_start(request: Request, payload: OrchStartIn):
    project = await _resolve_project(request, payload.project_slug)
    hub = request.app.state.orchestration_hub
    if payload.enforce_single:
        existing = await hub.has_running_run(project.id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"error": "another orchestration run is already running for this project",
                        "run_id": existing},
            )
    # Default external_id to a fresh UUID so the run is resumable later
    # (Wave 3.7 — form-based start always sets one; mirror that here for
    # external API callers too).
    external_id = payload.external_id or str(uuid.uuid4())
    run_id = await hub.create_run(project.id, payload.goal, external_id=external_id)
    # Auto-create the Roman root node
    node_id = await hub.create_node(
        run_id, project.id, agent_name="roman", role="orchestrator",
        external_id=external_id,
    )
    await hub.append_event(run_id, "run_started",
                           {"project_slug": project.slug, "goal": payload.goal})
    return JSONResponse({"run_id": run_id, "root_node_id": node_id})


@router.get("/orchestration/{run_id}")
async def orchestration_get(request: Request, run_id: str):
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    nodes = await hub.list_nodes(run_id)
    messages = await hub.list_messages(run_id)
    return JSONResponse({
        "run": dict(run),
        "nodes": [dict(n) for n in nodes],
        "messages": [dict(m) for m in messages],
    })


@router.post("/orchestration/{run_id}/nodes/{node_id}/message")
async def orchestration_append_message(
    request: Request, run_id: str, node_id: str, payload: OrchAppendMessageIn,
):
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    msg_id = await hub.append_message(
        run_id=run_id, node_id=node_id, project_id=run["project_id"],
        author=payload.author, kind=payload.kind, text=payload.text,
        client_message_id=payload.client_message_id,
    )
    return JSONResponse({"id": msg_id})


@router.post("/orchestration/{run_id}/finish")
async def orchestration_finish(request: Request, run_id: str, payload: OrchFinishIn):
    hub = request.app.state.orchestration_hub
    ok = await hub.finish_run(run_id, status=payload.status, error_message=payload.error_message)
    if ok:
        await hub.append_event(run_id, "run_finished", {"status": payload.status})
    return JSONResponse({"ok": ok})
