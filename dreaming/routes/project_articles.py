"""GET /p/{slug}/articles — предложения статей проекта по статусам.

Согласование и публикация живут в отдельных роутах (Task 8 и Task 9);
здесь — список, отклонение и возврат в очередь.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.services import articles


router = APIRouter()

_ORDER = ["proposed", "approved", "writing", "drafted", "published",
          "failed", "rejected"]


def _enrich(row: dict, *, verify_cmd: str, publish_mode: str) -> dict:
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        d["tags"] = []
    allowed, reason = articles.can_publish(d, verify_cmd, publish_mode)
    d["can_publish"] = allowed
    d["gate_reason"] = reason
    d["verify_label"] = articles.publish_label(bool(d.get("verify_ok")), verify_cmd)
    # `status` has no CHECK constraint; a row this route doesn't recognise
    # must still render (in the "other" catch-all) with its real status text
    # rather than through a missing article.status.<value> i18n key.
    d["status_known"] = d.get("status") in _ORDER
    return d


@router.get("/p/{slug}/articles")
async def articles_page(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    resolver = request.app.state.resolver_factory(request)
    verify_cmd = await resolver.get(project, "article_verify_cmd", "")
    publish_mode = await resolver.get(project, "article_publish_mode", "off")
    blog_dir = await resolver.get(project, "article_blog_dir", "")
    configured_writer = await resolver.get(project, "article_writer_agent", "")
    # `list_article_proposals` caps at 200 rows; `article_status_counts` does
    # not, so it — not len(enriched) — is the source of truth for how many
    # proposals actually exist. Both numbers go to the template pre-computed
    # so nothing about "is this page complete" is decided in Jinja.
    rows = await db.list_article_proposals(project_id=project.id)
    enriched = [_enrich(r, verify_cmd=verify_cmd, publish_mode=publish_mode)
                for r in rows]
    groups = [(st, [r for r in enriched if r["status"] == st]) for st in _ORDER]
    # A status outside _ORDER (no CHECK constraint stops one existing) would
    # otherwise silently vanish from every group above; catch it in one more
    # bucket instead of dropping it.
    other = [r for r in enriched if not r["status_known"]]
    if other:
        groups.append(("other", other))
    counts = {r["status"]: r["n"] for r in await db.article_status_counts(project.id)}
    true_total = sum(counts.values())
    shown = len(enriched)
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale,
    )
    projects = await request.app.state.projects.list_all(only_enabled=True)
    pm = request.app.state.process_manager
    return request.app.state.templates.TemplateResponse(
        request, "project_articles.html",
        {"project": project,
         "groups": [(st, items) for st, items in groups if items],
         "counts": counts, "total": true_total, "shown": shown,
         "capped": shown < true_total,
         "blog_dir": blog_dir,
         "writer": articles.resolve_writer(project.working_dir, configured_writer),
         "scan_running": f"cmd:{project.slug}:article-ideas-scan" in pm.list_running(),
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/articles/{proposal_id}/reject")
async def articles_reject(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    ok = await request.app.state.db.set_article_proposal_status(
        proposal_id, "rejected",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)


@router.post("/p/{slug}/articles/{proposal_id}/restore")
async def articles_restore(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    ok = await request.app.state.db.set_article_proposal_status(
        proposal_id, "proposed",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)


@router.post("/p/{slug}/articles/scan")
async def articles_scan(request: Request, slug: str):
    """Dispatch /article-ideas-scan into the project. Proposes only — this
    session never writes an article and never publishes."""
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    resolver = request.app.state.resolver_factory(request)
    try:
        await pm.start_command(
            project,
            command_name="article-ideas-scan",
            prompt="/article-ideas-scan",
            claude_path=await resolver.get(project, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=await resolver.get(project, "model", "sonnet"),
            max_turns=int(await resolver.get(project, "max_turns", 50)),
            timeout_minutes=int(await resolver.get(project, "timeout_minutes", 30)),
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return RedirectResponse(f"/p/{project.slug}/live", status_code=303)


@router.post("/p/{slug}/articles/{proposal_id}/approve")
async def articles_approve(request: Request, slug: str, proposal_id: int):
    """The first human gate: approve a proposal and dispatch the writer.

    bypassPermissions is required — with --allowedTools the session silently
    loses the ability to write into the repo (settled on self-study)."""
    project = request.state.project
    db = request.app.state.db
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    resolver = request.app.state.resolver_factory(request)
    row = await db.get_article_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    blog_dir = await resolver.get(project, "article_blog_dir", "")
    if not blog_dir:
        raise HTTPException(
            status_code=400,
            detail="article_blog_dir is not set — nowhere to put the article",
        )
    writer = articles.resolve_writer(
        project.working_dir,
        await resolver.get(project, "article_writer_agent", ""),
    )
    verify_cmd = await resolver.get(project, "article_verify_cmd", "")
    locales = await resolver.get(project, "article_locales", "")
    try:
        session_id = await pm.start_command(
            project,
            command_name="write-article",
            prompt=f"/write-article {proposal_id}",
            claude_path=await resolver.get(project, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=await resolver.get(project, "model", "sonnet"),
            max_turns=int(await resolver.get(project, "article_max_turns", 300)),
            timeout_minutes=int(
                await resolver.get(project, "article_timeout_minutes", 120)
            ),
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
                "DC_ARTICLE_WRITER": writer,
                "DC_ARTICLE_BLOG_DIR": blog_dir,
                "DC_ARTICLE_VERIFY_CMD": verify_cmd,
                "DC_ARTICLE_LOCALES": locales or row["locales"],
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await db.start_article_attempt(proposal_id, session_id=session_id or "")
    return RedirectResponse(f"/p/{project.slug}/live", status_code=303)


@router.post("/p/{slug}/articles/{proposal_id}/cancel")
async def articles_cancel(request: Request, slug: str, proposal_id: int):
    """Reconcile a row stuck in 'writing' back to 'failed' from the UI.

    This only rewrites the database row — it does NOT stop the running CLI
    session or kill any OS process. Use it when a write session crashed, was
    killed by the watchdog, or the host restarted before /written arrived, so
    the card is not left with no buttons at all."""
    project = request.state.project
    db = request.app.state.db
    row = await db.get_article_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    if row["status"] != "writing":
        raise HTTPException(
            status_code=409,
            detail=f"proposal is '{row['status']}', not 'writing' — nothing to cancel",
        )
    await db.set_article_proposal_status(
        proposal_id, "failed",
        error_message="cancelled from the UI while writing",
    )
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)


@router.post("/p/{slug}/articles/{proposal_id}/publish")
async def articles_publish(request: Request, slug: str, proposal_id: int):
    """The second human gate. Commits only the article's own files."""
    from dreaming.services import article_publish
    project = request.state.project
    db = request.app.state.db
    resolver = request.app.state.resolver_factory(request)
    row = await db.get_article_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    verify_cmd = await resolver.get(project, "article_verify_cmd", "")
    publish_mode = await resolver.get(project, "article_publish_mode", "off")
    allowed, reason = articles.can_publish(row, verify_cmd, publish_mode)
    if not allowed:
        raise HTTPException(status_code=400, detail=f"publish refused: {reason}")
    label = articles.publish_label(bool(row["verify_ok"]), verify_cmd)
    try:
        commit = await article_publish.publish(
            project.working_dir,
            article_publish.split_paths(row["draft_ref"], project.working_dir),
            message=article_publish.build_message(row, label),
            push=(publish_mode == "commit+push"),
        )
    except article_publish.PushFailed as e:
        # The commit landed locally; only the push failed. Recording the sha
        # keeps a retry from seeing "nothing to publish" forever, and the
        # error_message tells a human the push still needs doing by hand.
        await db.mark_article_published(proposal_id, commit_ref=e.commit)
        await db.set_article_proposal_status(
            proposal_id, "published", error_message=str(e)[:2000],
        )
        raise HTTPException(status_code=409, detail=str(e))
    except article_publish.PublishError as e:
        await db.set_article_proposal_status(
            proposal_id, "drafted", error_message=str(e)[:2000],
        )
        raise HTTPException(status_code=409, detail=str(e))
    await db.mark_article_published(proposal_id, commit_ref=commit)
    # Clear a stale error_message from an earlier failed attempt on this same
    # row (e.g. a prior commit or push failure) -- otherwise a card that just
    # published cleanly would still show the previous failure's text, now
    # that a 'published' row with a non-empty error_message renders it.
    if row.get("error_message"):
        await db.set_article_proposal_status(
            proposal_id, "published", error_message="",
        )
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)
