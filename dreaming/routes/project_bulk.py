"""POST /p/{slug}/bulk/orchestrate — enqueue many findings/ideas/evolutions
for sequential Orchestrator dispatch.

The Orchestrator only accepts one run per project at a time, so we can't just
hammer it with N concurrent dispatches. This endpoint queues them and a
per-project background task feeds them in one by one (see
`dreaming.services.bulk_orchestration`).

Form fields:
- `kind`     : "finding" | "idea" | "evolution"
- `selected` : repeated form field — finding/idea ids, or evolution relative paths
- `force`    : "1" to bypass the evolution conflict gate (optional)
- `redirect` : where to send the user after enqueue (optional; defaults to
               the source list page for the given kind)
"""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse

from dreaming.lib.flash import set_flash
from dreaming.services.bulk_orchestration import (
    ensure_dispatcher, get_queue, _KINDS,
)

router = APIRouter()


_DEFAULT_REDIRECT = {
    "finding":   "/p/{slug}/findings",
    "idea":      "/p/{slug}/ideas",
    "evolution": "/p/{slug}/evolutions",
}


@router.post("/p/{slug}/bulk/orchestrate")
async def bulk_orchestrate(
    request: Request, slug: str,
    kind: str = Form(...),
    force: str | None = Form(default=None),
    redirect: str | None = Form(default=None),
):
    project = request.state.project
    if kind not in _KINDS:
        raise HTTPException(status_code=400, detail=f"unknown kind: {kind}")
    form = await request.form()
    selected = [v for v in form.getlist("selected") if v]
    if not selected:
        raise HTTPException(status_code=400, detail="no items selected")
    queue = get_queue(request.app.state, project.id)
    force_flag = bool(force)
    for ident in selected:
        queue.add(kind, ident, force=force_flag)
    ensure_dispatcher(request.app.state, project)
    target = redirect or _DEFAULT_REDIRECT[kind].format(slug=project.slug)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    msg = request.app.state.i18n.t("bulk.queued_flash", locale=locale, n=len(selected))
    resp = RedirectResponse(target, status_code=303)
    set_flash(resp, msg, level="success")
    return resp


@router.get("/p/{slug}/bulk/queue")
async def bulk_queue_status(request: Request, slug: str):
    """JSON snapshot of the project's bulk queue — used by the UI to show
    pending counts and per-item status without a full page refresh."""
    project = request.state.project
    queue = get_queue(request.app.state, project.id)
    return JSONResponse({
        "dispatching": queue.dispatching,
        "pending": queue.pending_count(),
        "items": queue.snapshot(),
    })


@router.post("/p/{slug}/bulk/kick")
async def bulk_queue_kick(request: Request, slug: str):
    """Force-restart the dispatcher task. Useful when the dispatcher crashed
    silently or when the user wants to retry the slot check after manually
    closing a stale Orchestrator run."""
    from urllib.parse import urlparse
    project = request.state.project
    ensure_dispatcher(request.app.state, project)
    raw = request.headers.get("referer") or ""
    path = urlparse(raw).path if raw else ""
    if not path.startswith(f"/p/{project.slug}"):
        path = f"/p/{project.slug}/orchestration"
    return RedirectResponse(path, status_code=303)


@router.post("/p/{slug}/bulk/retry-failed")
async def bulk_queue_retry_failed(
    request: Request, slug: str,
    force: str | None = Form(default=None),
):
    """Flip any failed items back to pending and kick the dispatcher.

    Optional `force=1` flips the per-item force flag too — useful for evolution
    items whose original failure was the conflict gate (multiple proposals
    targeting the same agent), where the user has decided to apply anyway.
    """
    from urllib.parse import urlparse
    project = request.state.project
    queue = get_queue(request.app.state, project.id)
    flipped = 0
    for it in queue.items:
        if it.status == "failed":
            it.status = "pending"
            it.error = None
            if force:
                it.force = True
            flipped += 1
    if flipped:
        ensure_dispatcher(request.app.state, project)
    raw = request.headers.get("referer") or ""
    path = urlparse(raw).path if raw else ""
    if not path.startswith(f"/p/{project.slug}"):
        path = f"/p/{project.slug}/orchestration"
    return RedirectResponse(path, status_code=303)


@router.post("/p/{slug}/bulk/clear")
async def bulk_queue_clear(
    request: Request, slug: str,
    only: str | None = Form(default=None),
):
    """Drop items from the queue display.

    Default: wipe everything (pending + dispatched + failed). The queue is a
    work-list, not history — already-dispatched runs live in the DB
    independently and are not affected; this only clears the UI panel.

    `only=done` keeps pending items and clears just dispatched/failed —
    useful when the user wants to dismiss completed noise while waiting for
    pending ones to flow.
    """
    from urllib.parse import urlparse
    project = request.state.project
    queue = get_queue(request.app.state, project.id)
    if only == "done":
        queue.items = [it for it in queue.items if it.status == "pending"]
    else:
        queue.items = []
    raw = request.headers.get("referer") or ""
    path = urlparse(raw).path if raw else ""
    if not path.startswith(f"/p/{project.slug}"):
        path = f"/p/{project.slug}/orchestration"
    return RedirectResponse(path, status_code=303)
