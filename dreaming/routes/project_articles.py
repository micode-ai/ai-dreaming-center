"""GET /p/{slug}/articles — предложения статей проекта по статусам.

Согласование и публикация живут в отдельных роутах (Task 8 и Task 9);
здесь — список, отклонение и возврат в очередь.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.lib.flash import set_flash
from dreaming.services import articles, starter_kit


log = logging.getLogger(__name__)
router = APIRouter()

_ORDER = ["proposed", "approved", "writing", "drafted", "published",
          "failed", "rejected"]

# Statuses from which (re)dispatching a writer is legal — mirrors
# SqliteDB._DISPATCHABLE_STATUSES, which is the precondition that actually
# enforces this at the write. Checked here too, and *before* start_command,
# so a stale Approve/Retry click against an already-'published' row (C1) is
# refused before a paid session is dispatched, not just before its result is
# recorded.
_DISPATCHABLE_STATUSES = ("proposed", "approved", "failed", "drafted")


def _enrich(row: dict, *, verify_cmd: str, publish_mode: str) -> dict:
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        d["tags"] = []
    allowed, reason = articles.can_publish(d, verify_cmd, publish_mode)
    d["can_publish"] = allowed
    d["gate_reason"] = reason
    # I5: what the card claims is what was actually observed at write-back
    # time (persisted in verify_label), not article_verify_cmd re-read live —
    # clearing or setting the setting later must not repaint an old row's
    # claim. Rows written before this column existed have '' stored; for
    # those only, fall back to the old live computation.
    d["verify_label"] = d.get("verify_label") or articles.publish_label(
        bool(d.get("verify_ok")), verify_cmd,
    )
    # `status` has no CHECK constraint; a row this route doesn't recognise
    # must still render (in the "other" catch-all) with its real status text
    # rather than through a missing article.status.<value> i18n key.
    d["status_known"] = d.get("status") in _ORDER
    return d


async def _venue_for(request: Request, project, row: dict | None) -> tuple[object, str]:
    """Resolve a proposal's venue project and that venue's blog dir.

    The subject owns the card, the queue row and the questions; the venue owns
    the repository the article lands in, so every article setting from here on
    is read against the venue. With no override and no `article_venue_project`
    this returns the subject itself, which is exactly wave A's behaviour.
    """
    resolver = request.app.state.resolver_factory(request)
    enabled = await request.app.state.projects.list_all(only_enabled=True)
    configured = await resolver.get(project, "article_venue_project", "")
    venue_id = articles.resolve_venue_id(
        project.id, row.get("target_project_id") if row else None,
        configured, enabled,
    )
    venue = next((p for p in enabled if p.id == venue_id), project)
    blog_dir = await resolver.get(venue, "article_blog_dir", "")
    return venue, blog_dir


@router.get("/p/{slug}/articles")
async def articles_page(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    resolver = request.app.state.resolver_factory(request)
    # The page banner and the writer label use the project's *default* venue
    # (no per-proposal override) — a project with no proposals yet still has
    # to show something truthful about what an /approve would resolve to.
    default_venue, blog_dir = await _venue_for(request, project, None)
    configured_writer = await resolver.get(default_venue, "article_writer_agent", "")
    # The writer label is a claim about what articles_approve will actually
    # dispatch, not decoration — it must be resolved from the same root
    # (resolve_article_root falls back to the venue's working_dir when
    # blog_dir is unset/nested-escaping/missing/non-git, so this renders fine
    # for projects with no article_blog_dir configured at all).
    article_root = await articles.resolve_article_root(
        default_venue.working_dir, blog_dir,
    )
    # `list_article_proposals` caps at 200 rows; `count_article_proposals`
    # does not, so it — not len(enriched) — is the source of truth for how
    # many proposals actually exist. Both numbers go to the template
    # pre-computed so nothing about "is this page complete" is decided in
    # Jinja.
    rows = await db.list_article_proposals(project_id=project.id)
    enriched = []
    for r in rows:
        # list_article_proposals returns raw sqlite3.Row objects — dict()
        # them once so _venue_for's row.get("target_project_id") works (Row
        # has no .get) and so the same dict feeds _enrich below.
        row_dict = dict(r)
        # Each row may name its own venue (target_project_id override, or
        # the subject's article_venue_project setting) — the gate a card
        # shows must reflect *that* row's venue, not the page's default one.
        row_venue, _row_blog_dir = await _venue_for(request, project, row_dict)
        row_verify_cmd = await resolver.get(row_venue, "article_verify_cmd", "")
        row_publish_mode = await resolver.get(row_venue, "article_publish_mode", "off")
        d = _enrich(row_dict, verify_cmd=row_verify_cmd, publish_mode=row_publish_mode)
        d["venue_slug"] = row_venue.slug
        enriched.append(d)
    groups = [(st, [r for r in enriched if r["status"] == st]) for st in _ORDER]
    # A status outside _ORDER (no CHECK constraint stops one existing) would
    # otherwise silently vanish from every group above; catch it in one more
    # bucket instead of dropping it.
    other = [r for r in enriched if not r["status_known"]]
    if other:
        groups.append(("other", other))
    true_total = await db.count_article_proposals(project_ids=[project.id])
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
         "total": true_total, "shown": shown,
         "capped": shown < true_total,
         "blog_dir": blog_dir,
         "writer": articles.resolve_writer(article_root, configured_writer),
         "scan_running": f"cmd:{project.slug}:article-ideas-scan" in pm.list_running(),
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/articles/add")
async def articles_add(
    request: Request, slug: str,
    title: str = Form(...), angle: str = Form(""), venue: str = Form(""),
):
    """A human states the topic. `source='manual'`, and the evidence says so.

    The API's blank-evidence 400 exists because a queue of unfalsifiable
    suggestions is worse than an empty one. A person asking for an article is
    a checkable fact about why the proposal exists, so we record exactly that
    and never dress it up as a commit or a measurement.
    """
    project = request.state.project
    db = request.app.state.db
    topic = title.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")
    prompt = angle.strip()
    enabled = await request.app.state.projects.list_all(only_enabled=True)
    venue_id = None
    if venue.strip():
        match = next((p for p in enabled if p.slug == venue.strip()), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"project {venue} not found")
        venue_id = match.id
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    evidence = f"requested by hand on {stamp}"
    if prompt:
        evidence += f": {prompt[:300]}"
    slug_hint = articles.slugify(topic) or f"manual-{int(datetime.now(timezone.utc).timestamp())}"
    new_id = await db.add_article_proposal(
        project.id, source="manual", source_ref="", evidence=evidence,
        title=topic[:300], angle=prompt, slug_hint=slug_hint,
        target_project_id=venue_id,
    )
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    resp = RedirectResponse(f"/p/{project.slug}/articles", status_code=303)
    key = "article.flash.duplicate" if new_id is None else "article.flash.proposed"
    set_flash(resp, request.app.state.i18n.t(key, locale=locale),
              level="info" if new_id is None else "success")
    return resp


def _back_to(request: Request, default: str) -> str:
    """Same open-redirect-safe referer bounce ai_radar._back_to uses — reject
    is now reachable both from a project's own /articles page and from the
    cross-project /articles queue, and should return the operator to
    whichever one they clicked from rather than always jumping to the
    per-project page."""
    referer = request.headers.get("referer") or ""
    if referer.startswith("/"):
        return referer
    host = f"{request.url.scheme}://{request.url.netloc}"
    if referer.startswith(host):
        return referer[len(host):] or default
    return default


@router.post("/p/{slug}/articles/{proposal_id}/reject")
async def articles_reject(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    db = request.app.state.db
    row = await db.get_article_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    ok = await db.set_article_proposal_status(proposal_id, "rejected")
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    return RedirectResponse(
        _back_to(request, f"/p/{project.slug}/articles"), status_code=303,
    )


@router.post("/p/{slug}/articles/{proposal_id}/restore")
async def articles_restore(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    db = request.app.state.db
    row = await db.get_article_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    ok = await db.set_article_proposal_status(proposal_id, "proposed")
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)


async def dispatch_article_scan(request: Request, project) -> None:
    """Dispatch /article-ideas-scan into `project`. Proposes only — this
    session never writes an article and never publishes.

    Shared by the per-project scan button (below) and the cross-project
    queue's project-picker scan form (dreaming/routes/articles.py), so an
    operator can kick off a scan without first navigating into that
    project's own /articles page. Raises HTTPException on refusal; the
    caller does its own redirect afterwards.
    """
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    resolver = request.app.state.resolver_factory(request)
    if not starter_kit.command_installed(project.working_dir, "article-ideas-scan"):
        raise HTTPException(
            status_code=400,
            detail="article-ideas-scan is not installed for this project — "
            "re-run the starter-kit install to add "
            ".claude/commands/article-ideas-scan.md",
        )
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


@router.post("/p/{slug}/articles/scan")
async def articles_scan(request: Request, slug: str):
    """Dispatch /article-ideas-scan into the project. Proposes only — this
    session never writes an article and never publishes."""
    project = request.state.project
    await dispatch_article_scan(request, project)
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
    # C1: a stale tab can still be showing 'drafted' (or even 'proposed')
    # after another tab already published this same row. Refuse before
    # dispatching anything — checking only after start_article_attempt
    # would still have burned a real, paid CLI session on an
    # already-published article. The DB-level precondition in
    # start_article_attempt is the actual enforcement (belt); this is the
    # suspenders that keep the belt from being pointless.
    if row["status"] not in _DISPATCHABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"proposal is '{row['status']}' — cannot (re)dispatch a "
                "writer for it. 'published' is terminal (re-editing a "
                "published article is out of scope); a 'writing' row must "
                "be cancelled first."
            ),
        )
    # Wave B: the article lands in the venue's repository, not necessarily
    # the subject's — every setting from here on is read against the venue.
    # With no override and no article_venue_project setting this resolves to
    # `project` itself, which is byte-identical to wave A's behaviour.
    venue, blog_dir = await _venue_for(request, project, row)
    # write-article has to exist where the session will actually run, so the
    # starter-kit check targets the venue's working directory, not the
    # subject's.
    if not starter_kit.command_installed(venue.working_dir, "write-article"):
        raise HTTPException(
            status_code=400,
            detail=f"write-article is not installed for venue '{venue.slug}' — "
            "re-run the starter-kit install to add "
            ".claude/commands/write-article.md",
        )
    if not blog_dir:
        raise HTTPException(
            status_code=400,
            detail=f"article_blog_dir is not set for venue '{venue.slug}' — "
            "nowhere to put the article",
        )
    # The blog does not always live in the venue's own repository (e.g. a
    # nested landing-page repo with its own .git and remote). Deriving the
    # containing repo's root once means the writer autodetect, the session's
    # cwd, and the publish commit (in articles_publish below) all agree on
    # which repository owns the article. For the two projects whose blog is
    # inside their own repo this equals venue.working_dir unchanged.
    root = await articles.resolve_article_root(venue.working_dir, blog_dir)
    writer = articles.resolve_writer(
        root,
        await resolver.get(venue, "article_writer_agent", ""),
    )
    verify_cmd = await resolver.get(venue, "article_verify_cmd", "")
    locales = await resolver.get(venue, "article_locales", "")
    # DC_ARTICLE_BLOG_DIR must be relative to the session's own cwd (`root`),
    # not to venue.working_dir — once the session runs inside a nested repo,
    # "micode-landing-page/blog" from the venue's perspective is just "blog"
    # from the session's. session_blog_dir only re-derives that when root
    # actually moved; every case where resolve_article_root fell back to
    # venue.working_dir unchanged (unset, escaping, non-existent, non-git, or
    # ancestor-escaping blog_dir) leaves blog_dir untouched too.
    blog_dir_for_session = articles.session_blog_dir(
        venue.working_dir, blog_dir, root,
    )
    try:
        session_id = await pm.start_command(
            project,
            command_name="write-article",
            prompt=f"/write-article {proposal_id}",
            claude_path=await resolver.get(venue, "claude_path", "claude"),
            working_dir=root,
            model=await resolver.get(venue, "model", "sonnet"),
            max_turns=int(await resolver.get(venue, "article_max_turns", 300)),
            timeout_minutes=int(
                await resolver.get(venue, "article_timeout_minutes", 120)
            ),
            env_overrides={
                # DREAMING_PROJECT_SLUG stays the subject's slug even though
                # the session's cwd is the venue's article root: the
                # write-back and any question the writer asks must reach the
                # proposal's own project — the page the user is looking at —
                # not the venue's.
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
                "DC_ARTICLE_WRITER": writer,
                "DC_ARTICLE_BLOG_DIR": blog_dir_for_session,
                "DC_ARTICLE_VERIFY_CMD": verify_cmd,
                "DC_ARTICLE_LOCALES": locales or row["locales"],
                "DC_ARTICLE_SUBJECT_DIR": project.working_dir,
                "DC_ARTICLE_SUBJECT_SLUG": project.slug,
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    # Pin the resolved venue only now that a session has actually started —
    # not any earlier. start_command itself can still refuse (RuntimeError
    # above, the one-command-in-flight-per-project lock: two dispatchable
    # proposals approved in quick succession on the same project, or a
    # double-submit racing an in-flight write-article session), and pinning
    # before that point would lock in a decision from an attempt that never
    # ran — sticky, so a later successful retry would silently reuse the
    # stale resolution instead of resolving afresh. Placed here, between a
    # successful dispatch and start_article_attempt, the invariant still
    # holds: a row can never reach 'writing' against an unrecorded venue,
    # because both writes now happen only on the success path.
    if not await db.pin_article_proposal_venue(proposal_id, venue.id):
        # The row vanished, or the update matched nothing. A silent no-op
        # here would leave articles_publish re-resolving the venue from
        # scratch later — the exact drift this was meant to close — so it
        # is worth knowing about even though the dispatch itself already
        # succeeded and should not be blocked on this.
        log.warning(
            "pin_article_proposal_venue no-op for proposal %s (venue %s)",
            proposal_id, venue.id,
        )
    started = await db.start_article_attempt(proposal_id, session_id=session_id or "")
    if not started:
        # The process_manager key ("cmd:{slug}:write-article") is one lock
        # per project, so nothing else could dispatch a second write-article
        # session concurrently with this one — the only way to land here is
        # if this row's status changed by some other route in the narrow
        # window between the precondition check above and this write. A
        # real CLI session is now running with nowhere in the DB pointing
        # at it; say so loudly rather than pretending the dispatch above
        # didn't happen.
        raise HTTPException(
            status_code=409,
            detail=(
                f"a write-article session ({session_id}) started, but the "
                "proposal's status changed before it could be recorded — "
                f"check the session log for {session_id}"
            ),
        )
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
    cancelled = await db.set_article_proposal_status(
        proposal_id, "failed",
        error_message="cancelled from the UI while writing",
        expect_statuses=("writing",),
    )
    if not cancelled:
        # Lost a race with the write-back landing (or another cancel) between
        # the check above and this write; nothing to do — the row already
        # moved on to a real result, cancelling it now would clobber that.
        raise HTTPException(
            status_code=409,
            detail="proposal is no longer 'writing' — it resolved before "
            "the cancel could apply",
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
    # Wave B: publish reads the same venue approve dispatched into — the
    # article landed in the venue's repository, so the verify command, the
    # publish mode and the article root all have to come from there too.
    venue, blog_dir = await _venue_for(request, project, row)
    verify_cmd = await resolver.get(venue, "article_verify_cmd", "")
    publish_mode = await resolver.get(venue, "article_publish_mode", "off")
    allowed, reason = articles.can_publish(row, verify_cmd, publish_mode)
    if not allowed:
        raise HTTPException(status_code=400, detail=f"publish refused: {reason}")
    # I5: claim what was actually observed at write-back time, not whatever
    # article_verify_cmd happens to read right now. Rows written before
    # verify_label existed fall back to the live computation once, here.
    label = row.get("verify_label") or articles.publish_label(
        bool(row["verify_ok"]), verify_cmd,
    )
    mode = articles.normalize_publish_mode(publish_mode)  # M4
    articles_url = f"/p/{project.slug}/articles"
    # Same derivation as articles_approve: draft_ref paths are relative to
    # the repository that owns the blog, which is not always
    # venue.working_dir. Publishing against the wrong root would validate
    # and commit paths in a repository that never saw the write.
    root = await articles.resolve_article_root(venue.working_dir, blog_dir)
    try:
        commit = await article_publish.publish(
            root,
            article_publish.split_paths(row["draft_ref"], root),
            message=article_publish.build_message(row, label),
            push=(mode == "commit+push"),
        )
    except article_publish.PushFailed as e:
        # The commit landed locally; only the push failed. Recording the sha
        # keeps a retry from seeing "nothing to publish" forever, and the
        # error_message tells a human the push still needs doing by hand.
        # mark_article_published's own WHERE status='drafted' is what this
        # row was in an instant ago (can_publish just confirmed it), so this
        # should always succeed; if it somehow doesn't, the commit is still
        # real and must not be reported as if it never happened.
        committed = await db.mark_article_published(proposal_id, commit_ref=e.commit)
        if committed:
            await db.set_article_proposal_status(
                proposal_id, "published", error_message=str(e)[:2000],
                expect_statuses=("published",),
            )
            msg = str(e)
        else:
            msg = (
                f"committed {e.commit[:8]} but the push failed, AND the "
                "proposal's status changed before the commit could be "
                "recorded on it — check the project git log and the "
                "proposal by hand"
            )
        resp = RedirectResponse(articles_url, status_code=303)
        set_flash(resp, msg, level="error")  # I3
        return resp
    except article_publish.PublishError as e:
        # C2: only write 'drafted' back if the row is *still* 'drafted'. A
        # concurrent publish (the classic double-click) may have already
        # committed and flipped this same row to 'published' while this
        # request's own git call was in flight (awaiting asyncio.to_thread) —
        # writing 'drafted' unconditionally here is exactly the regression:
        # it would drag a genuinely-published row backwards, forever after
        # showing a stale 'drafted' card next to a real commit_ref.
        reverted = await db.set_article_proposal_status(
            proposal_id, "drafted", error_message=str(e)[:2000],
            expect_statuses=("drafted",),
        )
        if reverted:
            msg = str(e)
        else:
            current = await db.get_article_proposal(proposal_id)
            if current and current["status"] == "published":
                msg = (
                    "this article was already published by another request "
                    "while this publish attempt was in flight"
                )
            else:
                msg = str(e)
        resp = RedirectResponse(articles_url, status_code=303)
        set_flash(resp, msg, level="error")  # I3
        return resp
    committed = await db.mark_article_published(proposal_id, commit_ref=commit)
    if not committed:
        # The commit is real (sha above) but the row moved out of 'drafted'
        # before we could record it -- e.g. a concurrent Retry re-dispatched
        # this same row mid-publish. There is no safe automatic repair here:
        # the repository now holds a commit this row doesn't know about.
        # Surface it loudly rather than silently discarding the sha.
        resp = RedirectResponse(articles_url, status_code=303)
        set_flash(
            resp,
            f"published commit {commit[:8]} landed in the repository, but "
            "the proposal is no longer 'drafted' (a concurrent retry?) — "
            "check the project git log and the proposal by hand",
            level="error",
        )
        return resp
    # Clear a stale error_message from an earlier failed attempt on this same
    # row (e.g. a prior commit or push failure) -- otherwise a card that just
    # published cleanly would still show the previous failure's text, now
    # that a 'published' row with a non-empty error_message renders it.
    if row.get("error_message"):
        await db.set_article_proposal_status(
            proposal_id, "published", error_message="",
            expect_statuses=("published",),
        )
    return RedirectResponse(articles_url, status_code=303)
