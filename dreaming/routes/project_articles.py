"""GET /p/{slug}/articles — предложения статей проекта по статусам.

Согласование и публикация живут в отдельных роутах (Task 8 и Task 9);
здесь — список, отклонение и возврат в очередь.
"""
from __future__ import annotations
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.lib.flash import set_flash
from dreaming.services import articles, starter_kit


log = logging.getLogger(__name__)
router = APIRouter()

_ORDER = ["proposed", "approved", "writing", "drafted", "published",
          "failed", "rejected"]

# A draft_ref can name a generated registry or a whole editorial plan
# alongside the article — accounting-ai-agent's includes a content.ts, and
# ai-budget-assistant's a content-plan.md — and those have no size the writer
# promised to respect. The preview truncates rather than streaming an
# unbounded file into a page, and says so when it does.
_PREVIEW_MAX_CHARS = 200_000

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
    # Needed both for the venue <select>'s own options and, below, to look
    # up a row's raw override by id without a second query per row.
    projects = await request.app.state.projects.list_all(only_enabled=True)
    # Review fix round 1: a project-wide "is anything pending" boolean was
    # wrong -- orchestrator_questions is shared by every kind of session on
    # this project (self-study, rotation, ...), and two proposals can be
    # 'writing' at once. write-article.md passes the proposal id as run_id
    # when it asks, so a row's own pending question is the one whose run_id
    # matches that row's id; a question with an empty or unrelated run_id
    # (self-study, rotation, a different proposal) must not light up any
    # card. Same accessor project_questions.py uses, fetched once here
    # rather than per row.
    pending_qs = await db.list_questions(project.id, status="pending", limit=50)
    # list_questions returns raw sqlite3.Row objects (no .get()) -- index
    # directly; the column defaults to '' (create_question coalesces a
    # missing run_id to '' rather than storing NULL), so `or ""` covers the
    # unlikely NULL case too without raising.
    pending_run_ids = {q["run_id"] for q in pending_qs if (q["run_id"] or "")}
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
        # Review fix round 1: the resolved venue_slug above is *always* some
        # real enabled project (override -> article_venue_project -> the
        # subject itself), so it always equals one of the <select>'s own
        # options -- most often the subject's own, when there is in fact no
        # override at all. Using it to decide the <select>'s preselection
        # made the "no override" default option unreachable, and let an
        # operator who submits the form untouched silently pin a previously
        # unpinned row. venue_override_slug instead carries the RAW
        # per-row override (None when there is none), so the template can
        # tell "tracks the default, whatever that resolves to" apart from
        # "explicitly pinned to this same project". A stale/disabled
        # override (naming no enabled project) has no matching <option> to
        # begin with, so it falls back to showing the default selected --
        # there being nothing else it could honestly point to on this list.
        override_id = row_dict.get("target_project_id")
        override_project = (
            next((p for p in projects if p.id == override_id), None)
            if override_id is not None else None
        )
        d["venue_override_slug"] = override_project.slug if override_project else None
        d["has_pending_question"] = str(row_dict["id"]) in pending_run_ids
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
    pm = request.app.state.process_manager
    # The center could always see a starter-kit command *missing* but never
    # one gone stale, so an installed copy aged silently as the templates
    # moved on. That is not hypothetical: a project ran a wave-A
    # write-article.md for a day after the question channel shipped, and its
    # writer simply could not ask a question — a requested feature absent
    # with no error anywhere to say so, and a paid session to discover it.
    # Checked at the two roots the two sessions actually start in, which are
    # not always the same directory: the scan runs in the subject's own
    # working_dir (articles_scan below), the writer in the repository that
    # owns the blog (articles_approve below).
    stale_commands = []
    for command_name, root in (
        ("article-ideas-scan", project.working_dir),
        ("write-article", article_root),
    ):
        if not starter_kit.command_stale(root, command_name):
            continue
        stale_commands.append({
            "command": command_name,
            "root": str(root),
            # The install route writes into the project's own working_dir, so
            # its button can only reach a command living there. A venue that
            # nests its blog in a second repository has to be updated by
            # hand — offering a button that cannot reach it would be worse
            # than saying plainly that it cannot. Compared as resolved paths
            # rather than strings: on Windows the same directory reaches here
            # spelled several ways (trailing separator, drive-letter case),
            # and a string mismatch would tell the operator to go edit by
            # hand while the button beside it would have worked.
            "fixable_here": (
                Path(root).resolve() == Path(project.working_dir).resolve()
            ),
        })
    return request.app.state.templates.TemplateResponse(
        request, "project_articles.html",
        {"project": project,
         "stale_commands": stale_commands,
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
    # slugify drops non-ASCII rather than transliterating, so an all-Cyrillic
    # topic — the default case for this user, not an edge case — yields an
    # empty slug. The fallback must be derived from the topic's own text, not
    # the clock: a timestamp fallback makes two different topics submitted in
    # the same UTC second collide (falsely reported as a duplicate) while the
    # same topic submitted twice, seconds apart, does not collide (silently
    # duplicated) — exactly backwards from what (project_id, slug_hint)
    # dedup exists for. A digest of the normalised topic makes identical
    # topics collide deterministically and distinct topics not.
    slug_hint = articles.slugify(topic) or (
        "manual-" + hashlib.sha1(topic.strip().lower().encode("utf-8")).hexdigest()[:10]
    )
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


@router.post("/p/{slug}/articles/{proposal_id}/venue")
async def articles_set_venue(
    request: Request, slug: str, proposal_id: int, venue: str = Form(""),
):
    """Change a proposal's venue before it is approved. An empty `venue`
    clears the override (falls back to the subject's `article_venue_project`
    setting, then the subject itself) -- that is not an error.

    Mirrors articles_reject's guard shape: 404 when the row is missing or
    belongs to another project.
    """
    project = request.state.project
    db = request.app.state.db
    row = await db.get_article_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    venue_id = None
    if venue.strip():
        enabled = await request.app.state.projects.list_all(only_enabled=True)
        match = next((p for p in enabled if p.slug == venue.strip()), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"project {venue} not found")
        venue_id = match.id
    # set_article_proposal_venue's WHERE status='proposed' means its
    # rowcount==0 is ambiguous between "no such row" and "wrong status" --
    # but the 404 check above already established this row exists, so by the
    # time we get here a False can only mean the row is no longer 'proposed'.
    if not await db.set_article_proposal_venue(proposal_id, venue_id):
        raise HTTPException(
            status_code=409,
            detail=(
                f"proposal is '{row['status']}' — its venue was decided at "
                "dispatch and is no longer the user's to change"
            ),
        )
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
    if not blog_dir:
        raise HTTPException(
            status_code=400,
            detail=f"article_blog_dir is not set for venue '{venue.slug}' — "
            "nowhere to put the article",
        )
    # The blog does not always live in the venue's own repository (e.g. a
    # nested landing-page repo with its own .git and remote). Deriving the
    # containing repo's root here — before the starter-kit check right below
    # — means that check, the writer autodetect, the session's cwd, and the
    # publish commit (in articles_publish below) all agree on which
    # repository owns the article. For the two projects whose blog is inside
    # their own repo this equals venue.working_dir unchanged.
    root = await articles.resolve_article_root(venue.working_dir, blog_dir)
    # write-article has to exist where the session's cwd will actually be —
    # the repository that owns the blog directory — which is NOT always
    # venue.working_dir: a venue can nest its blog inside a second repository
    # with its own .git and its own remote (e.g. a landing-page repo checked
    # out inside the parent). Claude CLI resolves project-level slash
    # commands from its own cwd, not from a parent, so checking
    # venue.working_dir here missed exactly that case: the check could pass
    # against the venue's own .claude/commands/ while the session actually
    # runs inside the nested repo, which has none — burning a real paid
    # session for nothing, precisely what this check exists to prevent.
    if not starter_kit.command_installed(root, "write-article"):
        raise HTTPException(
            status_code=400,
            detail=f"write-article is not installed for venue '{venue.slug}' — "
            "re-run the starter-kit install to add "
            ".claude/commands/write-article.md",
        )
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
                # Set only when a human sent this draft back. The writer keys
                # off it to improve the files already named in DRAFT_REF
                # rather than starting a second article on the same subject.
                "DC_ARTICLE_REVISION_NOTES": row.get("revision_notes") or "",
                "DC_ARTICLE_DRAFT_REF": row.get("draft_ref") or "",
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
    # FIX 3: a retry re-dispatches from 'failed' or 'drafted', either of
    # which may still carry a pending question from a prior, abandoned
    # attempt (one that was never cancelled through the UI, e.g. the host
    # restarted before /written arrived). A fresh attempt starts clean —
    # that stale question must not keep the watchdog treating this
    # project's silence as excused, nor keep an old "waiting for your
    # answer" line on a row that has already moved on to a new session.
    await db.dismiss_article_proposal_questions(proposal_id)
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
    # FIX 3: this row is leaving 'writing' without a human ever answering
    # whatever it may have asked — an abandoned question of its own must
    # not stay 'pending' forever.
    await db.dismiss_article_proposal_questions(proposal_id)
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)


@router.post("/p/{slug}/articles/{proposal_id}/revise")
async def articles_revise(
    request: Request, slug: str, proposal_id: int,
    notes: str = Form(""), finding: list[str] | None = Form(None),
):
    """Send a drafted article back to its writer with what to fix.

    The checked findings and the free-text box are one instruction set: the
    findings are this venue's checkable rules stated in the writer's own terms,
    the box is everything a person can see and a check cannot. Both land in
    `revision_notes`, which the dispatch passes to the session next to the
    draft it already produced.

    Refuses an empty request. A revision that says nothing would spend a real
    session to re-read its own output and change nothing.
    """
    db = request.app.state.db
    project = request.state.project
    # Checked before the write, not only inside the dispatch below: the id
    # space is global, and notes must not land on another project's row even
    # if the dispatch would refuse to act on it a moment later.
    row = await db.get_article_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    combined = "\n".join(
        [*(finding or []), (notes or "").strip()],
    ).strip()
    if not combined:
        raise HTTPException(
            status_code=400,
            detail="a revision needs at least one note — tick a finding or "
                   "write what to change",
        )
    if not await db.set_article_revision_notes(proposal_id, combined):
        raise HTTPException(
            status_code=409,
            detail="only a drafted article can be sent back for revision — "
                   "this one is no longer drafted",
        )
    # Same dispatch as the first write, on purpose: one code path decides the
    # venue, the writer, the session's cwd and its limits, so a revision can
    # never resolve any of those differently than the write it revises.
    return await articles_approve(request, slug, proposal_id)


@router.get("/p/{slug}/articles/{proposal_id}/preview")
async def articles_preview(
    request: Request, slug: str, proposal_id: int, lang: str = "",
    file: str = "",
):
    """Read-only look at what the writer actually produced, per language.

    Shows the working tree, not the commit: for a published row this is the
    file as it stands now, which may have moved on since it was committed.
    That is the useful reading before pressing Publish, and the honest one
    after — but it is not a view of history.

    Files are read from the *venue's* article root — the same resolution the
    publish route uses — because a draft written into a nested landing-page
    repository is not reachable from the subject's own working_dir, and a
    preview that quietly read a different tree than publish commits would be
    worse than none.

    Every path goes through the publish validator before it is opened.
    `draft_ref` is self-reported by a Claude session over unauthenticated
    localhost HTTP, so without that this route would be an arbitrary-file
    reader wearing a preview's clothes. A path that fails is listed with its
    reason instead of aborting the page: one deleted file must not hide the
    other eight languages.
    """
    from dreaming.services import article_publish

    project = request.state.project
    db = request.app.state.db
    row = await db.get_article_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        # Scoped to the project in the URL: the id space is global, and this
        # page must not become a way to read another project's drafts.
        raise HTTPException(status_code=404, detail="proposal not found")
    venue, blog_dir = await _venue_for(request, project, row)
    root = Path(await articles.resolve_article_root(venue.working_dir, blog_dir))
    locales = [p.strip() for p in (row.get("locales") or "").split(",") if p.strip()]

    variants: list[dict] = []
    others: list[dict] = []
    problems: list[dict] = []
    draft_paths = article_publish.split_paths(row.get("draft_ref") or "")
    # A venue that keeps prose as data has all its languages inside one entry
    # of one file, so no path can name a language. The entry is found by slug:
    # the proposal's own hint, plus every path segment of its draft, because
    # the writer is free to pick a slug other than the hint.
    candidate_slugs = [row.get("slug_hint") or ""]
    for rel in draft_paths:
        candidate_slugs.extend(re.split(r"[\\/]+", rel))

    for rel in draft_paths:
        try:
            article_publish._validate_paths([rel], root)
        except article_publish.PublishError as e:
            problems.append({"path": rel, "reason": str(e)})
            continue
        target = (root / rel).resolve()
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            problems.append({"path": rel, "reason": f"read failed: {e}"})
            continue
        # A generated registry or a whole content plan can be far larger than
        # any article; truncate rather than shipping megabytes into a page.
        truncated = len(text) > _PREVIEW_MAX_CHARS
        entry = {
            "path": rel,
            "text": text[:_PREVIEW_MAX_CHARS],
            "truncated": truncated,
            "lang": (
                articles.frontmatter_language(text)
                or articles.locale_from_path(rel, locales)
            ),
        }
        if not entry["lang"] and rel.lower().endswith(".json"):
            # Before treating a data file as an unreadable blob: if it holds
            # this article as an entry, its `body<Lang>` fields ARE the
            # languages, and rendering them is the whole point of the page.
            # Without this, the venue whose blog is a 780 KB JSON array showed
            # a truncated dump and no language tabs at all.
            data_variants, _matched = articles.data_entry_variants(
                text, candidate_slugs,
            )
            if data_variants:
                for v in data_variants:
                    variants.append({
                        "path": f"{rel} — {v['lang']}",
                        "text": v["text"][:_PREVIEW_MAX_CHARS],
                        "truncated": len(v["text"]) > _PREVIEW_MAX_CHARS,
                        "lang": v["lang"],
                    })
                # The file itself stays reachable: the entry is what a reader
                # wants, but the raw data is what a debugger wants.
                others.append(entry)
                continue
        (variants if entry["lang"] else others).append(entry)

    # Ordered by the row's own locales so the tabs read the way the article was
    # commissioned, with anything the row never declared trailing behind.
    order = {loc.lower(): i for i, loc in enumerate(locales)}
    variants.sort(key=lambda v: (order.get(v["lang"], len(order)), v["lang"]))
    # `lang` picks a language tab; `file` picks one of the non-article files a
    # draft_ref can carry (a registry, an editorial plan), which have no
    # language to be picked by. `file` is matched against the paths this row
    # itself reported — never used to open anything — so it cannot widen what
    # the validator above already allowed.
    wanted = (lang or "").strip().lower()
    wanted_file = (file or "").strip()
    selected = next(
        (e for e in variants + others if e["path"] == wanted_file), None,
    ) if wanted_file else None
    if selected is None and wanted:
        selected = next((v for v in variants if v["lang"] == wanted), None)
    if selected is None:
        selected = variants[0] if variants else (others[0] if others else None)
    # Proposed revisions, computed from what the page just rendered rather
    # than from the files again. Only for a drafted row: `revise` refuses any
    # other status, and offering a form that will be refused is worse than
    # showing none.
    findings: list[dict] = []
    if row["status"] == "drafted":
        resolver = request.app.state.resolver_factory(request)
        try:
            min_chars = int(
                await resolver.get(venue, "article_min_chars", 0) or 0)
        except (TypeError, ValueError):
            min_chars = 0
        raw_markers = await resolver.get(venue, "article_required_markers", "")
        markers = [m.strip() for m in re.split(r"[,\n]+", raw_markers or "")
                   if m.strip()]
        findings = articles.draft_findings(
            variants, min_chars=min_chars, required_markers=markers,
        )
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale,
    )
    return request.app.state.templates.TemplateResponse(
        request, "project_article_preview.html",
        {"project": project, "row": row, "variants": variants,
         "others": others, "problems": problems, "selected": selected,
         "venue_slug": venue.slug, "article_root": str(root),
         "findings": findings, "locale": locale},
    )


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
    # FIX 2: by publish time the row already carries a PINNED venue
    # (pin_article_proposal_venue records one at dispatch, even when the
    # resolved venue was the subject itself) — the pin exists precisely to
    # reproduce approve's decision, not to be re-resolved. _venue_for's
    # fallback-to-subject is correct for resolving a proposal *before*
    # dispatch (resolve_venue_id's own contract), but applying that same
    # fallback here, to an already-pinned row, would silently redirect
    # publish at the SUBJECT's repository if the venue was disabled or
    # deleted between approve and publish — reading the subject's verify
    # command and publish mode, and committing a venue-written draft into
    # the wrong repo. Refuse instead, naming the venue, before any of that
    # is read. Checked directly against the enabled-projects id set rather
    # than through resolve_venue_id, which exists for the different,
    # fallback-is-correct case and must stay untouched.
    pinned_target_id = row.get("target_project_id")
    if pinned_target_id is not None:
        enabled_projects = await request.app.state.projects.list_all(only_enabled=True)
        if pinned_target_id not in {p.id for p in enabled_projects}:
            pinned_project = await request.app.state.projects.get_by_id(pinned_target_id)
            pinned_label = pinned_project.slug if pinned_project else f"project #{pinned_target_id}"
            raise HTTPException(
                status_code=409,
                detail=(
                    f"this proposal's venue ('{pinned_label}') is no longer "
                    "enabled — publish refuses rather than falling back to "
                    "the subject's repository"
                ),
            )
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
    # Wave C: article_publish_extra_paths stages a build's output (e.g. a
    # committed generated site) alongside draft_ref. Read from the venue,
    # like every other article setting on this route — the build runs in
    # the same article root the venue owns. Empty (the default) means
    # split_paths returns [] and publish() behaves exactly as before.
    extra_paths_setting = await resolver.get(venue, "article_publish_extra_paths", "")
    try:
        commit = await article_publish.publish(
            root,
            article_publish.split_paths(row["draft_ref"], root),
            message=article_publish.build_message(row, label),
            push=(mode == "commit+push"),
            extra_paths=article_publish.split_paths(extra_paths_setting, root),
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
