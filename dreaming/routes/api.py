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


class QuestionCreateIn(BaseModel):
    project_slug: str | None = None
    run_id: str | None = None
    node_id: str | None = None
    tool_use_id: str
    question: str
    options: list[str] | None = None


@router.post("/questions/create")
async def question_create(request: Request, payload: QuestionCreateIn):
    """Claude (via slash-command Bash) POSTs here when it wants to ask the user
    a question. Body has `tool_use_id` (unique per claude tool call), `question`
    text, and optional `options`. Stores a pending row in
    `orchestrator_questions`; ProcessManager watchdog detects it and refrains
    from killing the session for silence."""
    project = await _resolve_project(request, payload.project_slug)
    import json
    qjson = json.dumps({
        "question": payload.question,
        "options": payload.options or [],
    }, ensure_ascii=False)
    qid = await request.app.state.db.create_question(
        project_id=project.id,
        run_id=payload.run_id,
        node_id=payload.node_id,
        tool_use_id=payload.tool_use_id,
        questions_json=qjson,
    )
    return JSONResponse({"id": qid, "status": "pending"})


@router.get("/questions/{question_id}/poll")
async def question_poll(request: Request, question_id: str):
    """Claude polls this until status != pending; then reads answer_text.
    Returns {status, answer_text} or 404 if no such question."""
    row = await request.app.state.db.get_question(question_id)
    if row is None:
        raise HTTPException(status_code=404, detail="question not found")
    return JSONResponse({
        "id": row["id"],
        "status": row["status"],
        "answer_text": row.get("answer_text") or "",
        "answered_at": row.get("answered_at"),
    })


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
    # Auto-create the orchestrator root node
    node_id = await hub.create_node(
        run_id, project.id, agent_name="orchestrator", role="orchestrator",
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


# ── Cascade API (Wave 3.8) ──────────────────────────

class CascadeStartIn(BaseModel):
    project_slug: str | None = None
    goal: str
    external_id: str | None = None
    stages: list[dict] | None = None  # [{"key": "contract", "label": "..."}]


class CascadeStageStartIn(BaseModel):
    stage_key: str
    label: str | None = None
    iteration: int = 1


class CascadeStageFinishIn(BaseModel):
    stage_key: str
    status: str = "completed"


class CascadeGateIn(BaseModel):
    stage_key: str
    verdict: str  # "approve" | "return-to-stage" | "reject"
    returned_to_stage_key: str | None = None
    iteration: int = 1
    comment: str | None = None
    decided_by_node_id: str | None = None


class CascadeArtifactIn(BaseModel):
    kind: str          # "module" | "page" | "doc" | etc.
    title: str
    stage_key: str | None = None
    node_id: str | None = None
    url: str | None = None
    content_preview: str | None = None
    dedup_hash: str | None = None


class CascadeMessageIn(BaseModel):
    node_id: str | None = None
    author: str = "agent"
    kind: str = "text"
    text: str
    stage_key: str | None = None  # if set and node_id is None, server picks any node tied to that stage


@router.post("/cascade/init")
async def cascade_init(request: Request, payload: CascadeStartIn):
    project = await _resolve_project(request, payload.project_slug)
    hub = request.app.state.orchestration_hub
    existing = await hub.has_running_run(project.id)
    if existing:
        raise HTTPException(status_code=409, detail={"error": "another run already running",
                                                     "run_id": existing})
    run_id = await hub.create_run(project.id, payload.goal, external_id=payload.external_id)
    root_node_id = await hub.create_node(run_id, project.id, agent_name="orchestrator", role="orchestrator",
                                         external_id=payload.external_id)
    stages = payload.stages or [
        {"key": "contract", "label": "Contract"},
        {"key": "design", "label": "Design"},
        {"key": "implementation", "label": "Implementation"},
        {"key": "review", "label": "Review"},
        {"key": "qa", "label": "QA"},
    ]
    stage_ids = []
    for i, s in enumerate(stages):
        sid = await hub.ensure_stage(run_id, i, s["key"], s.get("label", s["key"].title()))
        stage_ids.append({"key": s["key"], "id": sid})
    await hub.append_event(run_id, "cascade_init",
                           {"goal": payload.goal, "stages": [s["key"] for s in stages]})
    return JSONResponse({"run_id": run_id, "root_node_id": root_node_id, "stages": stage_ids})


async def _resolve_stage(hub, run_id: str, stage_key: str) -> str:
    rows = await hub.list_stages(run_id)
    for r in rows:
        if r["stage_key"] == stage_key:
            return r["id"]
    raise HTTPException(status_code=404, detail=f"stage '{stage_key}' not found in run {run_id}")


@router.post("/cascade/{run_id}/stage/start")
async def cascade_stage_start(request: Request, run_id: str, payload: CascadeStageStartIn):
    hub = request.app.state.orchestration_hub
    sid = await _resolve_stage(hub, run_id, payload.stage_key)
    await hub.start_stage(sid)
    await hub.append_event(run_id, "cascade_stage_started",
                           {"stage_key": payload.stage_key, "iteration": payload.iteration})
    return JSONResponse({"stage_id": sid})


@router.post("/cascade/{run_id}/stage/finish")
async def cascade_stage_finish(request: Request, run_id: str, payload: CascadeStageFinishIn):
    hub = request.app.state.orchestration_hub
    sid = await _resolve_stage(hub, run_id, payload.stage_key)
    await hub.finish_stage(sid, status=payload.status)
    await hub.append_event(run_id, "cascade_stage_finished",
                           {"stage_key": payload.stage_key, "status": payload.status})
    return JSONResponse({"ok": True})


@router.post("/cascade/{run_id}/gate")
async def cascade_gate(request: Request, run_id: str, payload: CascadeGateIn):
    hub = request.app.state.orchestration_hub
    sid = await _resolve_stage(hub, run_id, payload.stage_key)
    return_to_sid = None
    if payload.returned_to_stage_key:
        return_to_sid = await _resolve_stage(hub, run_id, payload.returned_to_stage_key)
    v_id = await hub.record_gate_verdict(
        run_id=run_id, stage_id=sid, verdict=payload.verdict,
        returned_to_stage_id=return_to_sid, iteration=payload.iteration,
        comment=payload.comment, decided_by_node_id=payload.decided_by_node_id,
    )
    await hub.append_event(run_id, "cascade_gate",
                           {"stage_key": payload.stage_key, "verdict": payload.verdict,
                            "returned_to": payload.returned_to_stage_key})
    return JSONResponse({"verdict_id": v_id})


@router.post("/cascade/{run_id}/artifact")
async def cascade_artifact(request: Request, run_id: str, payload: CascadeArtifactIn):
    hub = request.app.state.orchestration_hub
    stage_id = None
    if payload.stage_key:
        stage_id = await _resolve_stage(hub, run_id, payload.stage_key)
    a_id = await hub.append_artifact(
        run_id=run_id, kind=payload.kind, title=payload.title,
        stage_id=stage_id, node_id=payload.node_id, url=payload.url,
        content_preview=payload.content_preview, dedup_hash=payload.dedup_hash,
    )
    if a_id is None:
        return JSONResponse({"id": None, "deduped": True})
    return JSONResponse({"id": a_id, "deduped": False})


@router.post("/cascade/{run_id}/message")
async def cascade_message(request: Request, run_id: str, payload: CascadeMessageIn):
    hub = request.app.state.orchestration_hub
    run = await hub.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404)
    node_id = payload.node_id
    if node_id is None:
        # No explicit node — use the root_node (first node of the run)
        nodes = await hub.list_nodes(run_id)
        if not nodes:
            raise HTTPException(status_code=400, detail="no nodes in run; pass node_id")
        node_id = nodes[0]["id"]
    msg_id = await hub.append_message(
        run_id=run_id, node_id=node_id, project_id=run["project_id"],
        author=payload.author, kind=payload.kind, text=payload.text,
    )
    return JSONResponse({"id": msg_id})


@router.post("/cascade/{run_id}/finish")
async def cascade_finish(request: Request, run_id: str):
    hub = request.app.state.orchestration_hub
    ok = await hub.finish_run(run_id, status="completed")
    if ok:
        await hub.append_event(run_id, "cascade_finished", {})
    return JSONResponse({"ok": ok})


# -- Topics ingest (slash-command callback) ----------------------

class TopicIngestIn(BaseModel):
    title: str
    module: str = ""
    target_agents: str = ""
    question: str = ""
    why_important: str = ""


@router.post("/p/{slug}/topics/ingest")
async def topics_ingest(request: Request, slug: str, payload: TopicIngestIn):
    """Called by /topics-scan slash-command running inside the project. One POST
    per topic. We don't dedupe at this layer — the slash-command is responsible
    for not proposing duplicates (it can GET /topics/list first)."""
    project = await _resolve_project(request, slug)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title required")
    tid = await request.app.state.db.add_custom_topic(
        project.id, title, payload.module.strip(),
        payload.target_agents.strip(), payload.question.strip(),
        payload.why_important.strip(),
    )
    return JSONResponse({"id": tid}, status_code=201)


@router.get("/p/{slug}/topics/list")
async def topics_list(request: Request, slug: str):
    """Called by /topics-scan to see what already exists so it can skip
    duplicates. Returns active topics only."""
    project = await _resolve_project(request, slug)
    rows = await request.app.state.db.list_custom_topics(project.id, active_only=True)
    return JSONResponse([
        {"id": r["id"], "title": r["title"], "module": r["module"],
         "target_agents": r["target_agents"]}
        for r in rows
    ])
