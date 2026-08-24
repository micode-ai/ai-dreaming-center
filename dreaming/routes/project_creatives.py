"""GET /p/{slug}/creatives — promotional creatives through the article loop.

The center proposes or the operator does, a human attaches source material,
the venue's own agent makes the formats, a human looks at the renders and
either sends them back with notes or publishes them.

One thing works differently from articles on purpose: **the campaign slug is
fixed when the proposal is created**, not chosen by the maker. Attachments land
in `<creative_dir>/<slug>/src/` before any session runs, so the directory name
has to exist before the maker does.

Spec: docs/superpowers/specs/2026-08-22-creative-pipeline-design.md
"""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from dreaming.lib.flash import set_flash
from dreaming.services import articles, creatives, starter_kit


log = logging.getLogger(__name__)
router = APIRouter()

_ORDER = ["proposed", "approved", "making", "drafted", "published",
          "done", "failed", "rejected"]

# Mirrors SqliteDB._CREATIVE_DISPATCHABLE / _CREATIVE_ATTACHABLE, which are
# the preconditions that actually enforce these at the write. Checked here too
# so a stale click is refused before a paid session is dispatched.
# What a hand-written campaign rests on when the operator names nothing.
# Not "proposed by the operator": the maker reads evidence as the claim the
# creative must be true to, and a note about who asked carries no claim, so
# every manual campaign was unbuildable by construction. This points at
# material that can actually be checked.
_MANUAL_EVIDENCE = (
    "hand-written brief, no external fact supplied: build only from what the "
    "venue's repository and the subject's own product demonstrably show, and "
    "ask (step 4a) for anything neither establishes"
)

_DISPATCHABLE_STATUSES = ("proposed", "approved", "failed", "drafted")
_ATTACHABLE_STATUSES = ("proposed", "approved", "failed", "drafted")

# A screen recording is the biggest thing anyone should be attaching here. Big
# enough for a minute of 1080p, small enough that a mistake is not a disk.
_UPLOAD_MAX_BYTES = 64 * 1024 * 1024
_UPLOAD_CHUNK = 1024 * 1024
# Post copy is prose; a file larger than this is not post copy and the preview
# says so rather than rendering a megabyte.
_COPY_MAX_CHARS = 40_000


def _enrich(row: dict, *, verify_cmd: str, publish_mode: str) -> dict:
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        d["tags"] = []
    allowed, reason = creatives.can_publish(d, verify_cmd, publish_mode)
    d["can_publish"] = allowed
    d["gate_reason"] = reason
    d["verify_label"] = d.get("verify_label") or creatives.publish_label(
        bool(d.get("verify_ok")), verify_cmd,
    )
    d["status_known"] = d.get("status") in _ORDER
    d["can_attach"] = d.get("status") in _ATTACHABLE_STATUSES
    return d


async def _venue_for(request: Request, project, row: dict | None):
    """(venue, creative_dir) for a proposal — the venue owns the repository."""
    resolver = request.app.state.resolver_factory(request)
    enabled = await request.app.state.projects.list_all(only_enabled=True)
    configured = await resolver.get(project, "creative_venue_project", "")
    venue_id = creatives.resolve_venue_id(
        project.id, row.get("target_project_id") if row else None,
        configured, enabled,
    )
    venue = next((p for p in enabled if p.id == venue_id), project)
    creative_dir = await resolver.get(venue, "creative_dir", "")
    return venue, creative_dir


async def _campaign(request: Request, project, row: dict | None):
    """(venue, repo_root, campaign_rel_dir).

    `repo_root` is the git repository that owns the creatives directory, which
    is not always the venue's working dir — the landing page lives in a nested
    repository with its own remote, exactly as it does for articles. Everything
    downstream (the maker's cwd, the publish commit, the media route's
    containment check) is relative to this one root, so they cannot disagree.
    """
    venue, creative_dir = await _venue_for(request, project, row)
    root = await creatives.resolve_repo_root(venue.working_dir, creative_dir)
    rel_dir = articles.session_blog_dir(venue.working_dir, creative_dir, root)
    slug = (row or {}).get("slug_hint") or ""
    return venue, Path(root), creatives.campaign_dir(rel_dir, slug) if slug else rel_dir


def _flash(request: Request, resp, key: str, level: str = "info") -> None:
    """Flash an i18n key as text. The cookie is read by a client script that
    renders it verbatim, so a raw key here would show the operator a raw key."""
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale)
    set_flash(resp, request.app.state.i18n.t(key, locale=locale), level)


class AttachmentRefused(Exception):
    """A file could not be stored. Carries the operator-facing reason."""


async def _store_attachments(
    request: Request, project, row: dict, files,
) -> list[str]:
    """Write attached source material into `<campaign>/src/`, or refuse.

    Shared by the attach route and the add form, on purpose: this is the
    security-critical part of both, and two copies of it would drift. Every
    assumption here is that the caller is careless rather than hostile, and it
    refuses either way — only the basename survives, the name is normalised,
    the extension is allow-listed, the size is capped *while streaming* rather
    than after, the destination is fixed, and the path is then checked by the
    publish validator so this cannot write anywhere publishing could not commit
    from.

    Raises AttachmentRefused with a reason the operator can act on. Nothing
    partially written is left behind: each file that fails is removed before
    the exception leaves.
    """
    from dreaming.services import article_publish

    venue, creative_dir = await _venue_for(request, project, row)
    if not (creative_dir or "").strip():
        raise AttachmentRefused(
            "creative_dir is not set for this venue, so there is nowhere to "
            "put attachments. Set it in the project's settings, under "
            "Creatives."
        )
    _venue, root, camp_rel = await _campaign(request, project, row)
    dest_rel = f"{camp_rel}/src"
    dest = (root / dest_rel).resolve()
    try:
        dest.relative_to(root.resolve())
    except ValueError:
        raise AttachmentRefused(
            f"the campaign directory resolves outside the repository: {dest_rel}"
        )
    dest.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for up in files or []:
        if not getattr(up, "filename", ""):
            # An empty file input posts a part with no filename; that is a
            # form with nothing chosen, not an error.
            continue
        name = creatives.safe_upload_name(up.filename)
        if not name:
            raise AttachmentRefused(
                f"{up.filename!r} leaves no usable filename after normalisation"
            )
        if not creatives.upload_allowed(name):
            raise AttachmentRefused(
                f"{name} is not an attachable type "
                f"({', '.join(creatives.UPLOAD_EXTS)})"
            )
        target = dest / name
        size = 0
        try:
            with target.open("wb") as fh:
                while True:
                    chunk = await up.read(_UPLOAD_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > _UPLOAD_MAX_BYTES:
                        fh.close()
                        target.unlink(missing_ok=True)
                        raise AttachmentRefused(
                            f"{name} exceeds "
                            f"{_UPLOAD_MAX_BYTES // (1024 * 1024)} MB"
                        )
                    fh.write(chunk)
        except OSError as e:
            target.unlink(missing_ok=True)
            raise AttachmentRefused(f"write failed: {e}")
        rel = f"{dest_rel}/{name}"
        try:
            article_publish._validate_paths([rel], root)
        except article_publish.PublishError as e:
            target.unlink(missing_ok=True)
            raise AttachmentRefused(str(e))
        written.append(rel)
    return written


def _require_dir(creative_dir: str) -> None:
    if not (creative_dir or "").strip():
        raise HTTPException(
            status_code=400,
            detail="creative_dir is not set for this venue — the pipeline has "
                   "nowhere to put a campaign. Set it in the project's "
                   "settings, under Creatives.",
        )


@router.get("/p/{slug}/creatives")
async def creatives_page(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    resolver = request.app.state.resolver_factory(request)
    default_venue, creative_dir = await _venue_for(request, project, None)
    root = await creatives.resolve_repo_root(
        default_venue.working_dir, creative_dir)
    rows = await db.list_creative_proposals(project_id=project.id)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    # A campaign's own pending question, matched the way the articles page
    # matches an article's: orchestrator_questions is shared by every kind of
    # session on this project, and two campaigns can be 'making' at once, so a
    # project-wide "is anything pending" boolean would light up the wrong card.
    # make-creative.md passes the proposal id as run_id when it asks; a
    # question with an empty or unrelated run_id must light up nothing.
    # Fetched once here rather than per row.
    pending_qs = await db.list_questions(project.id, status="pending", limit=50)
    pending_run_ids = {q["run_id"] for q in pending_qs if (q["run_id"] or "")}
    enriched = []
    for r in rows:
        row_dict = dict(r)
        row_venue, _ = await _venue_for(request, project, row_dict)
        d = _enrich(
            row_dict,
            verify_cmd=await resolver.get(row_venue, "creative_verify_cmd", ""),
            publish_mode=await resolver.get(
                row_venue, "creative_publish_mode", "off"),
        )
        d["venue_slug"] = row_venue.slug
        d["has_pending_question"] = str(row_dict["id"]) in pending_run_ids
        # What a human already attached, so the card can say so. A campaign
        # whose footage is sitting on disk and whose card says nothing about it
        # reads as a campaign with nothing to work from. One directory listing
        # per row, no file reads.
        try:
            _v, row_root, row_camp = await _campaign(request, project, row_dict)
            d["attachments"] = creatives.list_attachments(row_root, row_camp)
        except Exception as e:  # noqa: BLE001 - a listing must never 500 a page
            log.warning("creative %s: cannot list attachments: %s",
                        row_dict.get("id"), e)
            d["attachments"] = []
        override_id = row_dict.get("target_project_id")
        override = next(
            (p for p in projects if p.id == override_id), None,
        ) if override_id is not None else None
        d["venue_override_slug"] = override.slug if override else None
        enriched.append(d)
    groups = [(st, [r for r in enriched if r["status"] == st]) for st in _ORDER]
    other = [r for r in enriched if not r["status_known"]]
    if other:
        groups.append(("other", other))
    total = await db.count_creative_proposals(project_ids=[project.id])
    # Same drift banner the articles page carries. Without it a project keeps
    # running an installed make-creative.md that predates the question channel
    # and simply fails campaigns it could have asked about, with nothing on
    # this page saying why. The scan runs in the subject's own working_dir,
    # the maker in the repository that owns the creatives.
    stale_commands = []
    for command_name, cmd_root in (
        ("creative-ideas-scan", project.working_dir),
        ("make-creative", str(root)),
    ):
        if not starter_kit.command_stale(cmd_root, command_name):
            continue
        stale_commands.append({
            "command": command_name,
            "root": str(cmd_root),
            # The install route writes into the project's own working_dir, so
            # its button cannot reach a venue nested in a second repository.
            # Resolved-path comparison, not string: on Windows the same
            # directory arrives spelled several ways.
            "fixable_here": (
                Path(cmd_root).resolve() == Path(project.working_dir).resolve()
            ),
        })
    pm = request.app.state.process_manager
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale)
    return request.app.state.templates.TemplateResponse(
        request, "project_creatives.html",
        {"project": project,
         "stale_commands": stale_commands,
         "groups": [(st, items) for st, items in groups if items],
         "total": total, "shown": len(enriched),
         "capped": len(enriched) < total,
         "creative_dir": creative_dir,
         "agent": creatives.resolve_agent(
             root, await resolver.get(default_venue, "creative_agent", "")),
         "formats": creatives.split_list(
             await resolver.get(default_venue, "creative_formats", "")),
         "locales_cfg": creatives.split_list(
             await resolver.get(default_venue, "creative_locales", "")),
         "scan_running":
             f"cmd:{project.slug}:creative-ideas-scan" in pm.list_running(),
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/creatives/scan")
async def creatives_scan(request: Request, slug: str):
    """Ask the project for campaign ideas. Same shape as the article scan."""
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    resolver = request.app.state.resolver_factory(request)
    if not starter_kit.command_installed(
            project.working_dir, "creative-ideas-scan"):
        raise HTTPException(
            status_code=400,
            detail="creative-ideas-scan is not installed for this project — "
                   "re-run the starter-kit install to add "
                   ".claude/commands/creative-ideas-scan.md",
        )
    try:
        await pm.start_command(
            project,
            command_name="creative-ideas-scan",
            prompt="/creative-ideas-scan",
            claude_path=await resolver.get(project, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=await resolver.get(project, "model", "sonnet"),
            max_turns=int(await resolver.get(project, "creative_max_turns", 300)),
            timeout_minutes=int(await resolver.get(
                project, "creative_timeout_minutes", 120)),
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    resp = RedirectResponse(f"/p/{project.slug}/creatives", status_code=303)
    _flash(request, resp, "creative.flash.scan_started", "success")
    return resp


@router.post("/p/{slug}/creatives/add")
async def creatives_add(
    request: Request, slug: str,
    title: str = Form(...), angle: str = Form(""), venue: str = Form(""),
    evidence: str = Form(""),
    formats: str = Form(""), locales: str = Form(""),
):
    """An operator's own campaign idea, with its source material in one step.

    Attaching here rather than afterwards is the point: a campaign the operator
    proposes usually exists *because* they have footage, and making them find
    the card afterwards to hand it over is a step that only ever gets skipped.
    The prompt and the files arrive together, which is what the maker needs.

    `evidence` is what the campaign may claim. The maker treats it as the fact
    the creative must be true to and refuses to state anything it does not
    carry, so a placeholder here is not a neutral default -- it is a campaign
    nobody can build. That is what the old hard-coded "proposed by the
    operator" produced: a brief the maker read as carrying no claim at all,
    and correctly declined to invent one for.

    Left blank, the recorded evidence now says where the facts are instead of
    who asked: the venue's repository and the subject's own product. That is
    checkable material, which is the whole point of the field.
    """
    project = request.state.project
    db = request.app.state.db
    if not title.strip():
        raise HTTPException(status_code=400, detail="a campaign needs a title")
    # Read the file parts off the raw form rather than declaring
    # `list[UploadFile]`: a browser with a `multiple` file input and nothing
    # chosen posts one part with an empty filename, which FastAPI decodes as a
    # str and then 422s against an UploadFile annotation. Choosing no file is
    # the ordinary case for this form, not a validation error.
    form = await request.form()
    files = [
        v for v in form.getlist("files")
        if hasattr(v, "filename") and (v.filename or "").strip()
    ]
    projects = await request.app.state.projects.list_all(only_enabled=True)
    target = next((p.id for p in projects if p.slug == venue.strip()), None) \
        if venue.strip() else None
    # Computed once and reused for both the insert and the duplicate lookup:
    # deriving it twice invites the two from drifting, and then the lookup
    # would miss the very row the insert collided with. campaign_slug rather
    # than articles.slugify — this becomes the campaign's directory name, so it
    # transliterates Cyrillic instead of dropping it, and is never empty.
    slug = creatives.campaign_slug(title)
    new_id = await db.add_creative_proposal(
        project.id, source="manual", source_ref="operator",
        evidence=(evidence.strip() or _MANUAL_EVIDENCE), title=title.strip(),
        angle=angle.strip(), slug_hint=slug,
        formats=formats.strip(), locales=locales.strip(),
        target_project_id=target,
    )
    row = await db.get_creative_proposal(new_id) if new_id else \
        await db.find_creative_proposal_by_slug(project.id, slug)
    has_files = bool(files)
    resp = RedirectResponse(f"/p/{project.slug}/creatives", status_code=303)

    if not has_files:
        _flash(
            request, resp,
            "creative.flash.added" if new_id else "creative.flash.duplicate",
            "success" if new_id else "info",
        )
        return resp

    # Files were chosen, so they must not vanish silently. A duplicate slug is
    # not a reason to drop them — the operator is handing material to the
    # campaign that already exists — but a campaign a maker is already building
    # is, for the same reason the attach route refuses it.
    if row is None:
        _flash(request, resp, "creative.flash.duplicate", "error")
        return resp
    if row["status"] not in _ATTACHABLE_STATUSES:
        locale = request.cookies.get(
            "dc_locale", request.app.state.settings.default_locale)
        set_flash(
            resp,
            request.app.state.i18n.t(
                "creative.flash.attach_busy", locale=locale,
                status=row["status"]),
            "error",
        )
        return resp
    try:
        written = await _store_attachments(request, project, row, files)
    except AttachmentRefused as e:
        # The campaign exists either way; saying only "refused" would leave the
        # operator wondering whether it was created.
        locale = request.cookies.get(
            "dc_locale", request.app.state.settings.default_locale)
        set_flash(
            resp,
            request.app.state.i18n.t(
                "creative.flash.added_no_files", locale=locale, reason=str(e)),
            "error",
        )
        return resp
    log.info("creative %s: added with %d attachment(s)", row["id"], len(written))
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale)
    set_flash(
        resp,
        request.app.state.i18n.t(
            "creative.flash.added_with_files", locale=locale, n=len(written)),
        "success",
    )
    return resp


@router.post("/p/{slug}/creatives/{proposal_id}/attach")
async def creatives_attach(
    request: Request, slug: str, proposal_id: int,
    files: list[UploadFile] = File(...),
):
    """Attach source material — screen captures, clips — for the maker to use.

    Everything about this route assumes the caller is careless rather than
    hostile, and refuses either way: only the basename survives, it is
    normalised to `[a-z0-9._-]`, the extension must be on the upload
    allow-list, the size is capped while streaming rather than after, and the
    destination is fixed at `<campaign>/src/`. The path is then checked by the
    publish validator, so this route cannot write anywhere publishing could not
    commit from.
    """
    from dreaming.services import article_publish

    project = request.state.project
    db = request.app.state.db
    row = await db.get_creative_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    if row["status"] not in _ATTACHABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"cannot attach to a '{row['status']}' campaign — a maker "
                   f"session has already listed the directory, and a file "
                   f"arriving underneath it is a race with no upside",
        )
    try:
        written = await _store_attachments(request, project, row, files)
    except AttachmentRefused as e:
        raise HTTPException(status_code=400, detail=str(e))
    dest_rel = f"{(await _campaign(request, project, row))[2]}/src"
    log.info("creative %d: attached %d file(s) into %s",
             proposal_id, len(written), dest_rel)
    resp = RedirectResponse(f"/p/{project.slug}/creatives", status_code=303)
    _flash(request, resp, "creative.flash.attached", "success")
    return resp


@router.post("/p/{slug}/creatives/{proposal_id}/approve")
async def creatives_approve(request: Request, slug: str, proposal_id: int):
    """Dispatch the maker. bypassPermissions, for the reason self-study settled:
    with --allowedTools the session silently loses the ability to write."""
    project = request.state.project
    db = request.app.state.db
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    resolver = request.app.state.resolver_factory(request)
    row = await db.get_creative_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    if row["status"] not in _DISPATCHABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"a '{row['status']}' campaign cannot be dispatched",
        )
    venue, creative_dir = await _venue_for(request, project, row)
    _require_dir(creative_dir)
    _venue, root, camp_rel = await _campaign(request, project, row)
    if not starter_kit.command_installed(root, "make-creative"):
        raise HTTPException(
            status_code=400,
            detail=f"make-creative is not installed for venue '{venue.slug}' — "
                   f"re-run the starter-kit install to add "
                   f".claude/commands/make-creative.md",
        )
    agent = creatives.resolve_agent(
        root, await resolver.get(venue, "creative_agent", ""))
    try:
        session_id = await pm.start_command(
            project,
            command_name="make-creative",
            prompt=f"/make-creative {proposal_id}",
            claude_path=await resolver.get(venue, "claude_path", "claude"),
            working_dir=str(root),
            model=await resolver.get(venue, "model", "sonnet"),
            max_turns=int(await resolver.get(venue, "creative_max_turns", 300)),
            timeout_minutes=int(await resolver.get(
                venue, "creative_timeout_minutes", 120)),
            env_overrides={
                # The subject's slug, not the venue's: the write-back and any
                # question must reach the page the operator is looking at.
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
                "DC_CREATIVE_AGENT": agent,
                "DC_CREATIVE_DIR": camp_rel,
                "DC_CREATIVE_SLUG": row["slug_hint"],
                "DC_CREATIVE_FORMATS": await resolver.get(
                    venue, "creative_formats", ""),
                "DC_CREATIVE_LOCALES": (
                    await resolver.get(venue, "creative_locales", "")
                    or row["locales"]),
                "DC_CREATIVE_VERIFY_CMD": await resolver.get(
                    venue, "creative_verify_cmd", ""),
                "DC_CREATIVE_SUBJECT_DIR": project.working_dir,
                "DC_CREATIVE_SUBJECT_SLUG": project.slug,
                # Non-empty only when a human sent this back.
                "DC_CREATIVE_REVISION_NOTES": row.get("revision_notes") or "",
                "DC_CREATIVE_DRAFT_REF": row.get("draft_ref") or "",
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not await db.start_creative_attempt(proposal_id, session_id=session_id or ""):
        log.warning(
            "creative %d: a session (%s) started but the row was no longer "
            "dispatchable — check the session log for %s",
            proposal_id, session_id, session_id,
        )
    await db.pin_creative_proposal_venue(proposal_id, venue.id)
    resp = RedirectResponse(f"/p/{project.slug}/creatives", status_code=303)
    _flash(request, resp, "creative.flash.making", "success")
    return resp


@router.post("/p/{slug}/creatives/{proposal_id}/cancel")
async def creatives_cancel(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    db = request.app.state.db
    if not await db.set_creative_proposal_status(
            proposal_id, "failed", expect_statuses=("making",),
            error_message="cancelled by the operator"):
        raise HTTPException(
            status_code=409,
            detail="the campaign is no longer 'making' — it resolved before "
                   "the cancel could apply",
        )
    return RedirectResponse(f"/p/{project.slug}/creatives", status_code=303)


@router.post("/p/{slug}/creatives/{proposal_id}/reject")
async def creatives_reject(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    db = request.app.state.db
    if not await db.set_creative_proposal_status(
            proposal_id, "rejected", expect_statuses=("proposed", "failed")):
        raise HTTPException(
            status_code=409,
            detail="only a proposed or failed campaign can be rejected",
        )
    return RedirectResponse(f"/p/{project.slug}/creatives", status_code=303)


@router.post("/p/{slug}/creatives/{proposal_id}/done")
async def creatives_mark_done(request: Request, slug: str, proposal_id: int):
    """Close a campaign as already made, without making it.

    Distinct from reject on purpose: rejected means the idea was wrong, done
    means it was right and the work already exists. The two read differently
    when you come back to the queue a month later, and a scan that re-proposes
    the same slug is refused either way by the unique (project_id, slug_hint)
    index -- so this costs nothing in dedup and buys an honest record.

    Reversible through the same restore button rejected campaigns use.
    """
    project = request.state.project
    db = request.app.state.db
    if not await db.set_creative_proposal_status(
            proposal_id, "done", expect_statuses=("proposed", "failed")):
        raise HTTPException(
            status_code=409,
            detail="only a proposed or failed campaign can be marked done",
        )
    return RedirectResponse(f"/p/{project.slug}/creatives", status_code=303)


@router.post("/p/{slug}/creatives/{proposal_id}/restore")
async def creatives_restore(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    db = request.app.state.db
    if not await db.set_creative_proposal_status(
            proposal_id, "proposed", expect_statuses=("rejected", "done")):
        raise HTTPException(
            status_code=409,
            detail="only a rejected or already-made campaign can be restored")
    return RedirectResponse(f"/p/{project.slug}/creatives", status_code=303)


@router.post("/p/{slug}/creatives/{proposal_id}/venue")
async def creatives_venue(
    request: Request, slug: str, proposal_id: int, venue: str = Form(""),
):
    project = request.state.project
    db = request.app.state.db
    projects = await request.app.state.projects.list_all(only_enabled=True)
    target = next((p.id for p in projects if p.slug == venue.strip()), None) \
        if venue.strip() else None
    if not await db.set_creative_proposal_venue(proposal_id, target):
        row = await db.get_creative_proposal(proposal_id)
        raise HTTPException(
            status_code=409,
            detail=f"the venue can only be changed while a campaign is "
                   f"proposed or failed (this one is "
                   f"'{(row or {}).get('status', 'gone')}') — moving it after a "
                   f"session ran would leave its files in one repository while "
                   f"the row claimed another",
        )
    return RedirectResponse(f"/p/{project.slug}/creatives", status_code=303)


@router.get("/p/{slug}/creatives/{proposal_id}/preview")
async def creatives_preview(
    request: Request, slug: str, proposal_id: int, fmt: str = "", loc: str = "",
):
    """The renders, grouped by format and locale, with the post copy beside them.

    An advertisement cannot be approved unless it is seen, so this page exists
    before the publish button means anything. Media is not inlined here — each
    render is a URL into the media route below, which is where the path checks
    live.
    """
    from dreaming.services import article_publish

    project = request.state.project
    db = request.app.state.db
    row = await db.get_creative_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    resolver = request.app.state.resolver_factory(request)
    venue, root, camp_rel = await _campaign(request, project, row)
    formats = creatives.split_list(
        await resolver.get(venue, "creative_formats", ""))
    locales = creatives.split_list(
        await resolver.get(venue, "creative_locales", "")) \
        or creatives.split_list(row["locales"])

    media_paths: list[str] = []
    copy_items: list[dict] = []
    problems: list[dict] = []
    for rel in article_publish.split_paths(row.get("draft_ref") or ""):
        try:
            article_publish._validate_paths([rel], root)
        except article_publish.PublishError as e:
            problems.append({"path": rel, "reason": str(e)})
            continue
        if creatives.media_type(rel):
            media_paths.append(rel)
        elif creatives.is_copy(rel):
            try:
                text = (root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                problems.append({"path": rel, "reason": f"read failed: {e}"})
                continue
            copy_items.append({
                "path": rel,
                "text": text[:_COPY_MAX_CHARS],
                "truncated": len(text) > _COPY_MAX_CHARS,
            })
        else:
            problems.append({
                "path": rel,
                "reason": "not a render this pipeline serves and not post copy",
            })

    grouped, ungrouped = creatives.group_renders(media_paths, formats, locales)
    tabs = sorted(grouped.keys())
    want = (fmt.strip().lower(), loc.strip().lower())
    selected = want if want in grouped else (tabs[0] if tabs else None)
    findings: list[dict] = []
    if row["status"] == "drafted":
        findings = creatives.draft_findings(
            root, [*media_paths, *(c["path"] for c in copy_items)],
            formats=formats, locales=locales,
        )
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale)
    return request.app.state.templates.TemplateResponse(
        request, "project_creative_preview.html",
        {"project": project, "row": row, "venue_slug": venue.slug,
         "campaign_dir": camp_rel, "tabs": tabs, "grouped": grouped,
         "selected": selected,
         "selected_paths": grouped.get(selected, []) if selected else [],
         # The maker's inputs beside its outputs: judging an ad means judging
         # it against the material it was given.
         "attachments": creatives.list_attachments(root, camp_rel),
         "ungrouped": ungrouped, "copy_items": copy_items,
         "problems": problems, "findings": findings,
         "has_rules": bool(formats or locales), "locale": locale},
    )


@router.get("/p/{slug}/creatives/{proposal_id}/media")
async def creatives_media(
    request: Request, slug: str, proposal_id: int, path: str = "",
):
    """Serve one render out of the venue's repository.

    Three gates, all of them necessary: the path must be one this row itself
    reported (so the parameter selects, never opens), it must pass the publish
    validator against the campaign's repository root, and its extension must be
    a media type this pipeline produces. Without the first, a proposal id plus
    a crafted path would read any file the validator allows; without the third,
    "preview" would serve whatever happens to sit beside the renders.
    """
    from dreaming.services import article_publish

    project = request.state.project
    db = request.app.state.db
    row = await db.get_creative_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    wanted = (path or "").strip().replace("\\", "/")
    ctype = creatives.media_type(wanted)
    if not ctype:
        raise HTTPException(
            status_code=415, detail="not a media type this pipeline serves")
    _venue, root, camp_rel = await _campaign(request, project, row)
    # Two enumerated sets, never arithmetic on the caller's string: what this
    # row reported as its output, and what a human attached as its input. The
    # attachment set comes from listing the campaign's own src/ directory, so
    # the parameter still only ever selects from a list the server built.
    allowed = set(article_publish.split_paths(row.get("draft_ref") or ""))
    allowed.update(creatives.list_attachments(root, camp_rel))
    if wanted not in allowed:
        raise HTTPException(
            status_code=404,
            detail="that path is neither one this campaign reported nor one of "
                   "its attachments",
        )
    try:
        article_publish._validate_paths([wanted], root)
    except article_publish.PublishError as e:
        raise HTTPException(status_code=400, detail=str(e))
    target = (root / wanted).resolve()
    if not target.is_file():
        raise HTTPException(status_code=404, detail="render is gone from disk")
    return FileResponse(str(target), media_type=ctype)


@router.post("/p/{slug}/creatives/{proposal_id}/revise")
async def creatives_revise(
    request: Request, slug: str, proposal_id: int,
    notes: str = Form(""), finding: list[str] | None = Form(None),
):
    """Send a drafted campaign back with what to fix."""
    project = request.state.project
    db = request.app.state.db
    row = await db.get_creative_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    combined = "\n".join([*(finding or []), (notes or "").strip()]).strip()
    if not combined:
        raise HTTPException(
            status_code=400,
            detail="a revision needs at least one note — tick a finding or "
                   "write what to change",
        )
    if not await db.set_creative_revision_notes(proposal_id, combined):
        raise HTTPException(
            status_code=409,
            detail="only a drafted campaign can be sent back for revision",
        )
    return await creatives_approve(request, slug, proposal_id)


@router.post("/p/{slug}/creatives/{proposal_id}/publish")
async def creatives_publish(request: Request, slug: str, proposal_id: int):
    """The second human gate. Commits the campaign's own files, nothing else."""
    from dreaming.services import article_publish

    project = request.state.project
    db = request.app.state.db
    resolver = request.app.state.resolver_factory(request)
    row = await db.get_creative_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    venue, root, _camp = await _campaign(request, project, row)
    verify_cmd = await resolver.get(venue, "creative_verify_cmd", "")
    publish_mode = await resolver.get(venue, "creative_publish_mode", "off")
    allowed, reason = creatives.can_publish(row, verify_cmd, publish_mode)
    if not allowed:
        raise HTTPException(
            status_code=409, detail=f"publishing refused: {reason}")
    label = row.get("verify_label") or creatives.publish_label(
        bool(row["verify_ok"]), verify_cmd)
    paths = article_publish.split_paths(row.get("draft_ref") or "")
    if not paths:
        raise HTTPException(
            status_code=409,
            detail="the campaign reported no files, so there is nothing to "
                   "commit",
        )
    extra = article_publish.split_paths(
        await resolver.get(venue, "creative_publish_extra_paths", ""))
    message = creatives.build_message(
        row, label,
        formats=creatives.split_list(
            await resolver.get(venue, "creative_formats", "")),
    )
    try:
        sha = await article_publish.publish(
            str(root), paths,
            message=message,
            push=creatives.normalize_publish_mode(publish_mode) == "commit+push",
            extra_paths=extra,
        )
    except article_publish.PushFailed as e:
        await db.mark_creative_published(proposal_id, commit_ref=e.sha)
        resp = RedirectResponse(
            f"/p/{project.slug}/creatives", status_code=303)
        set_flash(resp, f"committed {e.sha[:8]} but the push failed: {e}",
                  "error")
        return resp
    except article_publish.PublishError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not await db.mark_creative_published(proposal_id, commit_ref=sha):
        log.warning(
            "creative %d: committed %s but the row was no longer 'drafted'",
            proposal_id, sha,
        )
    resp = RedirectResponse(f"/p/{project.slug}/creatives", status_code=303)
    _flash(request, resp, "creative.flash.published", "success")
    return resp
