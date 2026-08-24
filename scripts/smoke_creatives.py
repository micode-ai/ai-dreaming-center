"""Smoke-тест creative pipeline.

Покрывает: правило доказательства, дедуп, предусловия статусов, загрузку
вложений (traversal, тип, размер, нормализация имени), роут выдачи медиа,
проверки размеров рендеров и группировку предпросмотра по формату и локали.

Спек: docs/superpowers/specs/2026-08-22-creative-pipeline-design.md
Выход 0 — всё ок; ненулевой код + диагностика в stderr — что упало.
"""
from __future__ import annotations
import asyncio
import io
import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# cp1250 console: an unencodable char in print() aborts the run mid-way.
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

from dreaming.services import creatives  # noqa: E402
from dreaming.services.db import SqliteDB  # noqa: E402
from dreaming.services.projects import ProjectsService  # noqa: E402


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def png_bytes(w: int, h: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(ihdr)) + chunk
            + struct.pack(">I", zlib.crc32(chunk)))


async def main() -> int:  # noqa: C901
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_creatives_"))
    db = SqliteDB(str(tmp / "test.db"))
    await db.connect()
    try:
        project = await ProjectsService(db).create(
            slug="demo-cr", label="Demo creatives", working_dir=str(tmp))
        pid = project.id

        # ---- evidence + dedup --------------------------------------------
        try:
            await db.add_creative_proposal(
                pid, source="manual", source_ref="", evidence="   ",
                title="x", angle="", slug_hint="blank-evidence")
            fail("blank evidence was accepted — the rule the whole queue "
                 "rests on has to hold in the DB method, not only at the "
                 "HTTP boundary")
            return 1
        except ValueError:
            pass
        print("ok: add_creative_proposal refuses blank evidence")

        first = await db.add_creative_proposal(
            pid, source="project_scan", source_ref="a1b2c3d",
            evidence="voice entry shipped in a1b2c3d",
            title="Voice entry", angle="one take", slug_hint="voice-entry",
            formats="post-4x5,story", locales="pl")
        if not first:
            fail("first insert returned no id")
            return 1
        dup = await db.add_creative_proposal(
            pid, source="manual", source_ref="", evidence="something else",
            title="Voice entry again", angle="", slug_hint="voice-entry")
        if dup is not None:
            fail(f"a second proposal with the same slug got id {dup} — three "
                 f"feeders on one subject must make one row, not three")
            return 1
        found = await db.find_creative_proposal_by_slug(pid, "voice-entry")
        if not found or found["id"] != first:
            fail("find_creative_proposal_by_slug did not return the row a "
                 "duplicate collided with")
            return 1
        print("ok: dedup on (project_id, slug_hint), and the collision is "
              "reportable by id")

        # ---- status machine ----------------------------------------------
        if await db.set_creative_revision_notes(first, "n"):
            fail("a 'proposed' row accepted revision notes")
            return 1
        if await db.mark_creative_published(first, commit_ref="x"):
            fail("a 'proposed' row was published without ever being made")
            return 1
        if not await db.start_creative_attempt(first, session_id="s1"):
            fail("a 'proposed' row could not be dispatched")
            return 1
        if await db.set_creative_revision_notes(first, "n"):
            fail("a 'making' row accepted revision notes — it would race the "
                 "attempt already in flight")
            return 1
        if await db.mark_creative_published(first, commit_ref="x"):
            fail("a 'making' row was published")
            return 1
        if not await db.mark_creative_made(
                first, draft_ref="renders/a.png", verify_output="ok",
                maker_agent="self", verify_ok=True, verify_label="verified"):
            fail("mark_creative_made refused a 'making' row")
            return 1
        if not await db.set_creative_revision_notes(first, "add a reel"):
            fail("a 'drafted' row refused revision notes")
            return 1
        if not await db.start_creative_attempt(first, session_id="s2"):
            fail("a revision could not be dispatched from 'drafted'")
            return 1
        row = await db.get_creative_proposal(first)
        if row["revision_notes"] != "add a reel":
            fail("revision notes were lost when the revision attempt started, "
                 "so the session would never see them")
            return 1
        await db.mark_creative_made(
            first, draft_ref="renders/a.png", verify_output="",
            maker_agent="self", verify_ok=True)
        row = await db.get_creative_proposal(first)
        if row["revision_notes"] != "":
            fail(f"revision notes survived the write-back as "
                 f"{row['revision_notes']!r}; a later plain retry would "
                 f"resend an instruction the maker already carried out")
            return 1
        if not await db.mark_creative_published(first, commit_ref="deadbeef"):
            fail("a drafted row could not be published")
            return 1
        if await db.mark_creative_published(first, commit_ref="second"):
            fail("published is not terminal — a second publish succeeded")
            return 1
        if await db.set_creative_proposal_venue(first, 999):
            fail("the venue changed after publishing, which would leave the "
                 "files in one repository and the row claiming another")
            return 1
        print("ok: every status precondition holds — notes only while "
              "drafted, cleared by the write-back, publish once, venue frozen "
              "after a session ran")

        # ---- reconcile ----------------------------------------------------
        stranded = await db.add_creative_proposal(
            pid, source="manual", source_ref="", evidence="checked",
            title="Stranded", angle="", slug_hint="stranded")
        await db.start_creative_attempt(stranded, session_id="ghost")
        n = await db.reconcile_stranded_creative_proposals(set())
        row = await db.get_creative_proposal(stranded)
        # No agent_learning_sessions row exists for 'ghost', so the method
        # logs it and leaves it rather than guessing — the same choice the
        # article reconcile makes, and the reason it returns 0 here.
        if n != 0 or row["status"] != "making":
            fail(f"a 'making' row whose session has no session row at all was "
                 f"auto-failed (n={n}, status={row['status']}) — that is the "
                 f"case the article reconcile deliberately leaves alone")
            return 1
        sid = await db.create_session(pid, "cmd:demo-cr:make-creative", "sonnet")
        live = await db.add_creative_proposal(
            pid, source="manual", source_ref="", evidence="checked",
            title="Live", angle="", slug_hint="live-one")
        await db.start_creative_attempt(live, session_id=sid)
        if await db.reconcile_stranded_creative_proposals({sid}) != 0:
            fail("a row whose session is in the live process set was failed")
            return 1
        await db.finish_session(sid, status="success")
        if await db.reconcile_stranded_creative_proposals(set()) != 1:
            fail("a row whose session finished without reporting was not "
                 "failed, so the card would claim work still in progress")
            return 1
        row = await db.get_creative_proposal(live)
        if row["status"] != "failed" or "without reporting" not in (
                row["error_message"] or ""):
            fail(f"the stranded row's message does not say what happened: "
                 f"{row['error_message']!r}")
            return 1
        print("ok: reconcile trusts only the live process set, and says what "
              "happened")

        # ---- pure helpers -------------------------------------------------
        cases = [
            ("Photo 1.JPG", "photo-1.jpg"),
            ("../../etc/passwd", ""),
            ("C:\\evil\\shot.png", "shot.png"),
            (".env", ""),
            ("..", ""),
            ("no-extension", ""),
            ("--weird--.gif", "weird.gif"),
        ]
        for raw, want in cases:
            got = creatives.safe_upload_name(raw)
            if got != want:
                fail(f"safe_upload_name({raw!r}) = {got!r}, want {want!r}")
                return 1
        if creatives.upload_allowed("shot.tar.gz"):
            fail("an archive passed the upload allow-list")
            return 1
        if not creatives.upload_allowed("clip.mp4"):
            fail("mp4 was refused, so no reel footage could ever be attached")
            return 1
        print(f"ok: safe_upload_name neutralises {len(cases)} hostile or messy "
              f"names, and the allow-list keeps archives out")

        sizes = tmp / "sizes"
        sizes.mkdir()
        (sizes / "a.png").write_bytes(png_bytes(1080, 1350))
        (sizes / "b.png").write_bytes(png_bytes(800, 600))
        (sizes / "c.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
        if creatives.image_size(sizes / "a.png") != (1080, 1350):
            fail("PNG dimensions were misread from the header")
            return 1
        if creatives.image_size(sizes / "c.mp4") is not None:
            fail("a video reported a measurable size — a dimension that "
                 "cannot be measured must never be guessed")
            return 1
        print("ok: image_size reads PNG headers and refuses to guess a video's")

        fmts = ["post-4x5", "story", "reel-4x5", "reel"]
        locs = ["pl", "en"]
        if creatives.classify_render("x-reel-4x5-pl.mp4", fmts, locs) != (
                "reel-4x5", "pl"):
            fail("reel-4x5 was classified as 'reel' with a locale of '4x5'")
            return 1
        if creatives.classify_render("thumb.png", fmts, locs) != ("", ""):
            fail("an unrelated filename invented a format")
            return 1
        print("ok: classify_render prefers the longest format id and invents "
              "nothing")

        # A campaign slug is the directory attachments land in, before any
        # session runs, and it never changes — so unlike an article's slug_hint
        # (a seed the writer replaces) it must never be empty and should be
        # readable. articles.slugify drops Cyrillic by documented design, which
        # for an all-Russian campaign title would have put a human's footage in
        # the shared creatives root and made the next such title collide with
        # it on the unique index.
        slug_cases = [
            ("Дашборды в  eKsiegowyAI", "dashbordy-v-eksiegowyai"),
            ("Дашборды и отчёты", "dashbordy-i-otchety"),
            ("Щупальця і їжак", "shchupaltsia-i-izhak"),
            ("Wykresy i raporty", "wykresy-i-raporty"),
        ]
        for title, want in slug_cases:
            got = creatives.campaign_slug(title)
            if got != want:
                fail(f"campaign_slug({title!r}) = {got!r}, want {want!r}")
                return 1
        for title in ("...", "🎬", "", "   "):
            got = creatives.campaign_slug(title)
            if not got or "/" in got or got.startswith("-"):
                fail(f"campaign_slug({title!r}) = {got!r} — a campaign slug is "
                     f"a directory name and can never be empty")
                return 1
            if not got.startswith("campaign-"):
                fail(f"campaign_slug({title!r}) = {got!r}; an unusable title "
                     f"should fall back to a digest, not to a bare fragment")
                return 1
        if creatives.campaign_slug("...") == creatives.campaign_slug("🎬"):
            fail("two different unusable titles produced the same slug, so the "
                 "second campaign would swallow the first as a duplicate")
            return 1
        if creatives.campaign_slug("Отчёты") != creatives.campaign_slug("отчёты"):
            fail("the same title in different case produced different slugs, "
                 "so dedup would stop working")
            return 1
        long_slug = creatives.campaign_slug(
            "Voice entry: an expense in three seconds flat, no typing at all")
        if len(long_slug.split("-")) != 7:
            fail(f"a long title should truncate to six words plus a digest, "
                 f"got {long_slug!r}")
            return 1
        print(f"ok: campaign_slug transliterates Cyrillic ({len(slug_cases)} "
              f"cases), never returns empty, keeps distinct titles apart and "
              f"case-folds the same one together")

        camp = tmp / "camp"
        camp.mkdir()
        (camp / "x-post-4x5-pl.png").write_bytes(png_bytes(1080, 1350))
        (camp / "x-story-pl.png").write_bytes(png_bytes(800, 600))
        found = creatives.draft_findings(
            camp, ["x-post-4x5-pl.png", "x-story-pl.png"],
            formats=["post-4x5", "story"], locales=["pl", "en"])
        kinds = sorted(f["kind"] for f in found)
        want_kinds = ["copy_missing", "locale_missing", "wrong_size"]
        if kinds != want_kinds:
            fail(f"draft_findings returned {kinds}, want {want_kinds}")
            return 1
        # With no formats and no locales declared there is nothing to check
        # about them — but "renders with no post copy" is not a venue rule, it
        # is what half a campaign looks like, so that one still fires.
        bare = creatives.draft_findings(
            camp, ["x-post-4x5-pl.png"], formats=[], locales=[])
        if [f["kind"] for f in bare] != ["copy_missing"]:
            fail(f"with no venue rules the only finding may be copy_missing, "
                 f"got {[f['kind'] for f in bare]}")
            return 1
        (camp / "copy-pl.md").write_text("text", encoding="utf-8")
        if creatives.draft_findings(
                camp, ["x-post-4x5-pl.png", "copy-pl.md"],
                formats=[], locales=[]) != []:
            fail("draft_findings complained about a campaign with a render, "
                 "copy, and no venue rules to break")
            return 1
        print("ok: draft_findings reports a wrong size, a missing locale and "
              "missing copy; with no venue rules and copy present it says "
              "nothing")

        # ---- routes: upload, media, preview -------------------------------
        from starlette.testclient import TestClient
        from dreaming.main import app

        prior = os.environ.get("DC_DB_PATH")
        page_db = Path(tempfile.mkdtemp(prefix="dc_smoke_cr_page_"))
        repo = Path(tempfile.mkdtemp(prefix="dc_smoke_cr_repo_"))
        (repo / "docs" / "marketing" / "creatives").mkdir(parents=True)
        os.environ["DC_DB_PATH"] = str(page_db / "t.db")
        try:
            with TestClient(app) as client:
                svc = ProjectsService(app.state.db)
                proj = await svc.create(
                    slug="cr-page", label="CR page", working_dir=str(repo))
                await svc.set_setting(
                    proj.id, "creative_dir", "docs/marketing/creatives")
                await svc.set_setting(proj.id, "creative_formats",
                                      "post-4x5,story")
                await svc.set_setting(proj.id, "creative_locales", "pl")

                r = client.get("/p/cr-page/creatives")
                if r.status_code != 200:
                    fail(f"creatives page: {r.status_code}")
                    return 1

                cid = await app.state.db.add_creative_proposal(
                    proj.id, source="manual", source_ref="", evidence="checked",
                    title="Voice", angle="", slug_hint="voice",
                    formats="post-4x5,story", locales="pl")

                # attach: the happy path, then every refusal
                r = client.post(
                    f"/p/cr-page/creatives/{cid}/attach",
                    files=[("files", ("Shot 1.PNG", png_bytes(10, 10),
                                      "image/png"))])
                if r.status_code not in (200, 303):
                    fail(f"attach refused a valid png: {r.status_code} {r.text[:200]}")
                    return 1
                landed = repo / "docs" / "marketing" / "creatives" / "voice" / "src"
                if not (landed / "shot-1.png").is_file():
                    fail(f"the attachment did not land normalised in "
                         f"{landed} (contents: "
                         f"{[p.name for p in landed.glob('*')] if landed.exists() else 'no dir'})")
                    return 1
                # A traversal filename is neutralised, not refused: only the
                # basename ever survives, and refusing would also reject the
                # ordinary case of a browser sending a path. What must hold is
                # that nothing lands outside the campaign's src/.
                r = client.post(
                    f"/p/cr-page/creatives/{cid}/attach",
                    files=[("files", ("../../escape.png", png_bytes(10, 10),
                                      "image/png"))])
                if r.status_code not in (200, 303):
                    fail(f"a path-shaped filename was refused outright "
                         f"({r.status_code}); it should be reduced to its "
                         f"basename instead")
                    return 1
                if not (landed / "escape.png").is_file():
                    fail("the path-shaped filename did not land as a plain "
                         "basename inside src/")
                    return 1
                for outside in (repo.parent / "escape.png",
                                repo / "escape.png",
                                repo / "docs" / "escape.png"):
                    if outside.exists():
                        fail(f"a traversal filename wrote outside the campaign "
                             f"directory: {outside}")
                        return 1
                r = client.post(
                    f"/p/cr-page/creatives/{cid}/attach",
                    files=[("files", ("payload.zip", b"PK\x03\x04",
                                      "application/zip"))])
                if r.status_code != 400:
                    fail(f"a zip was accepted as attachable: {r.status_code}")
                    return 1
                if list(landed.glob("*.zip")):
                    fail("a refused type was written anyway")
                    return 1
                big = io.BytesIO(b"\x00" * (65 * 1024 * 1024))
                r = client.post(
                    f"/p/cr-page/creatives/{cid}/attach",
                    files=[("files", ("huge.mp4", big, "video/mp4"))])
                if r.status_code != 400:
                    fail(f"an oversized upload was accepted: {r.status_code}")
                    return 1
                if (landed / "huge.mp4").exists():
                    fail("an oversized upload was left on disk after refusal")
                    return 1
                print("ok: attach normalises a name (a path-shaped one down to "
                      "its basename, inside src/), and refuses a bad type and "
                      "an oversized file without leaving anything behind")

                # attach is refused once a maker is running
                await app.state.db.start_creative_attempt(cid, session_id="live")
                r = client.post(
                    f"/p/cr-page/creatives/{cid}/attach",
                    files=[("files", ("late.png", png_bytes(10, 10),
                                      "image/png"))])
                if r.status_code != 409:
                    fail(f"attaching to a 'making' campaign returned "
                         f"{r.status_code}, want 409 — the session has already "
                         f"listed the directory")
                    return 1
                print("ok: attach is refused while a maker session is running")

                # a made campaign: preview groups by format x locale, media
                # serves only what the row reported
                cdir = repo / "docs" / "marketing" / "creatives" / "voice"
                (cdir / "renders").mkdir(parents=True, exist_ok=True)
                (cdir / "renders" / "voice-post-4x5-pl.png").write_bytes(
                    png_bytes(1080, 1350))
                (cdir / "renders" / "voice-story-pl.png").write_bytes(
                    png_bytes(1080, 1920))
                (cdir / "copy-pl.md").write_text("# Post\n\ntext",
                                                 encoding="utf-8")
                (repo / "secret.txt").write_text("classified", encoding="utf-8")
                base = "docs/marketing/creatives/voice"
                await app.state.db.mark_creative_made(
                    cid,
                    draft_ref=(f"{base}/renders/voice-post-4x5-pl.png, "
                               f"{base}/renders/voice-story-pl.png, "
                               f"{base}/copy-pl.md"),
                    verify_output="", maker_agent="self", verify_ok=True)

                r = client.get(f"/p/cr-page/creatives/{cid}/preview")
                if r.status_code != 200:
                    fail(f"preview: {r.status_code} {r.text[:200]}")
                    return 1
                for tab in ("fmt=post-4x5", "fmt=story"):
                    if tab not in r.text:
                        fail(f"preview is missing the {tab} tab")
                        return 1
                if "copy-pl.md" not in r.text:
                    fail("preview did not show the post copy")
                    return 1
                print("ok: preview groups renders by format and locale and "
                      "shows the copy beside them")

                url = f"/p/cr-page/creatives/{cid}/media"
                r = client.get(url, params={
                    "path": f"{base}/renders/voice-post-4x5-pl.png"})
                if r.status_code != 200 or r.headers["content-type"] != "image/png":
                    fail(f"media route refused a reported render: "
                         f"{r.status_code} {r.headers.get('content-type')}")
                    return 1
                r = client.get(url, params={"path": "secret.txt"})
                if r.status_code == 200:
                    fail("the media route served a file this campaign never "
                         "reported — the parameter must select, never open")
                    return 1
                r = client.get(url, params={"path": f"{base}/copy-pl.md"})
                if r.status_code == 200:
                    fail("the media route served a non-media file")
                    return 1
                r = client.get(url, params={"path": "../../../etc/passwd"})
                if r.status_code == 200:
                    fail("the media route served a traversal path")
                    return 1
                # An SVG is a script container and this route answers from the
                # center's own origin with the operator's cookies. draft_ref is
                # self-reported by a session, so a reported .svg must not be
                # servable even though it is nominally an image.
                if creatives.media_type("evil.svg") is not None:
                    fail("svg is servable as media — a session that wrote one "
                         "could get script executed in the center's origin")
                    return 1
                (cdir / "renders" / "evil.svg").write_text(
                    "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                    encoding="utf-8")
                await app.state.db.set_creative_proposal_status(
                    cid, "making", expect_statuses=("drafted",))
                await app.state.db.mark_creative_made(
                    cid,
                    draft_ref=(f"{base}/renders/voice-post-4x5-pl.png, "
                               f"{base}/renders/evil.svg, {base}/copy-pl.md"),
                    verify_output="", maker_agent="self", verify_ok=True)
                r = client.get(url, params={
                    "path": f"{base}/renders/evil.svg"})
                if r.status_code == 200:
                    fail("the media route served a reported .svg")
                    return 1
                print("ok: the media route serves only reported media, and "
                      "refuses an unreported path, a non-media type and "
                      "traversal")

                # revise
                r = client.post(f"/p/cr-page/creatives/{cid}/revise",
                                data={"notes": ""})
                if r.status_code != 400:
                    fail(f"an empty revision was accepted: {r.status_code}")
                    return 1
                print("ok: an empty revision is refused rather than spending a "
                      "session to change nothing")

                # ---- adding a campaign with its material in one step -------
                # The whole point of attaching on the add form: an operator's
                # campaign usually exists BECAUSE they have footage, and a
                # second step to hand it over is the step that gets skipped.
                r = client.post(
                    "/p/cr-page/creatives/add",
                    data={"title": "Receipt scan in one tap", "angle": "one take"},
                    files=[("files", ("Clip 1.MP4", b"\x00" * 64, "video/mp4")),
                           ("files", ("frame.png", png_bytes(8, 8), "image/png"))],
                )
                if r.status_code not in (200, 303):
                    fail(f"add with files: {r.status_code} {r.text[:200]}")
                    return 1
                added = await app.state.db.find_creative_proposal_by_slug(
                    proj.id, "receipt-scan-in-one-tap")
                if added is None:
                    fail("adding with files did not create the campaign")
                    return 1
                src = (repo / "docs" / "marketing" / "creatives"
                       / "receipt-scan-in-one-tap" / "src")
                landed_names = sorted(p.name for p in src.glob("*")) \
                    if src.exists() else []
                if landed_names != ["clip-1.mp4", "frame.png"]:
                    fail(f"the add form's files did not land normalised in "
                         f"{src}: {landed_names}")
                    return 1
                print("ok: adding a campaign attaches its material in the same "
                      "step, with the same normalisation")

                # A refused file must not leave the operator guessing whether
                # the campaign was created: it is, and the flash says why the
                # files were not.
                r = client.post(
                    "/p/cr-page/creatives/add",
                    data={"title": "Archive attempt"},
                    files=[("files", ("payload.zip", b"PK\x03\x04",
                                      "application/zip"))],
                )
                if r.status_code not in (200, 303):
                    fail(f"add with a refused file returned {r.status_code}; it "
                         f"should redirect and explain, since the campaign was "
                         f"created either way")
                    return 1
                bad = await app.state.db.find_creative_proposal_by_slug(
                    proj.id, "archive-attempt")
                if bad is None:
                    fail("a refused attachment also lost the campaign")
                    return 1
                zsrc = (repo / "docs" / "marketing" / "creatives"
                        / "archive-attempt" / "src")
                if zsrc.exists() and list(zsrc.glob("*")):
                    fail(f"a refused type was written anyway: "
                         f"{[p.name for p in zsrc.glob('*')]}")
                    return 1
                print("ok: a refused attachment on the add form keeps the "
                      "campaign and writes nothing")

                # No file chosen is a form, not an error.
                r = client.post(
                    "/p/cr-page/creatives/add",
                    data={"title": "No files here"},
                    files=[("files", ("", b"", "application/octet-stream"))],
                )
                if r.status_code not in (200, 303):
                    fail(f"add with an empty file input: {r.status_code}")
                    return 1
                if await app.state.db.find_creative_proposal_by_slug(
                        proj.id, "no-files-here") is None:
                    fail("an empty file input lost the campaign")
                    return 1
                print("ok: an empty file input is a form with nothing chosen, "
                      "not a refusal")

                # ---- the card says what is attached -----------------------
                # A campaign whose footage is on disk and whose card says
                # nothing about it reads as a campaign with nothing to work
                # from — which is exactly how it read before this.
                r = client.get("/p/cr-page/creatives")
                if "clip-1.mp4" not in r.text or "frame.png" not in r.text:
                    fail("the card does not name the files attached to the "
                         "campaign, so nothing in the UI says they arrived")
                    return 1
                added_id = added["id"]
                thumb = (f"/p/cr-page/creatives/{added_id}/media?path="
                         f"docs%2Fmarketing%2Fcreatives%2Freceipt-scan-in-one-tap"
                         f"%2Fsrc%2Fframe.png")
                if thumb.split("?")[0] not in r.text:
                    fail("the card has no thumbnail URL for an attached image")
                    return 1
                # An attachment is servable even though it is not in draft_ref:
                # it is an input, not an output, and the allow-list is the
                # campaign's own src/ listing.
                r = client.get(
                    f"/p/cr-page/creatives/{added_id}/media",
                    params={"path": "docs/marketing/creatives/"
                                    "receipt-scan-in-one-tap/src/frame.png"})
                if r.status_code != 200:
                    fail(f"the media route refused an attachment: "
                         f"{r.status_code} — the card's thumbnails would all "
                         f"be broken images")
                    return 1
                # ...but only one that is really there, and only inside src/.
                for bogus in ("docs/marketing/creatives/receipt-scan-in-one-tap/"
                              "src/absent.png",
                              "docs/marketing/creatives/receipt-scan-in-one-tap/"
                              "src/../../../../secret.txt"):
                    r = client.get(
                        f"/p/cr-page/creatives/{added_id}/media",
                        params={"path": bogus})
                    if r.status_code == 200:
                        fail(f"the media route served {bogus!r} — the "
                             f"attachment allow-list must be a directory "
                             f"listing, not path arithmetic")
                        return 1
                print("ok: the card names and thumbnails what is attached, the "
                      "media route serves an attachment but only one its own "
                      "listing contains")
        finally:
            if prior is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior

        # ---- the waiting indicator is per campaign, not per project -----
        # A question lights up the card whose id it names, and no other. The
        # bug this guards against is a project-wide "is anything pending"
        # check: orchestrator_questions is shared by every session on a
        # project, so that version lights up every 'making' card, including
        # ones that never asked.
        prior2 = os.environ.get("DC_DB_PATH")
        page_db2 = Path(tempfile.mkdtemp(prefix="dc_smoke_cr_q_"))
        repo2 = Path(tempfile.mkdtemp(prefix="dc_smoke_cr_qrepo_"))
        (repo2 / "docs" / "marketing" / "creatives").mkdir(parents=True)
        os.environ["DC_DB_PATH"] = str(page_db2 / "t.db")
        try:
            from starlette.testclient import TestClient as TC2
            with TC2(app) as client:
                svc = ProjectsService(app.state.db)
                proj = await svc.create(
                    slug="cr-q", label="CR q", working_dir=str(repo2))
                await svc.set_setting(
                    proj.id, "creative_dir", "docs/marketing/creatives")
                asker = await app.state.db.add_creative_proposal(
                    proj.id, source="manual", source_ref="", evidence="checked",
                    title="Asks", angle="", slug_hint="asks")
                quiet = await app.state.db.add_creative_proposal(
                    proj.id, source="manual", source_ref="", evidence="checked",
                    title="Quiet", angle="", slug_hint="quiet")
                for cid_ in (asker, quiet):
                    await app.state.db.start_creative_attempt(
                        cid_, session_id=f"sess-{cid_}")

                marker = app.state.i18n.t("creative.waiting_answer", locale="ru")
                body = client.get("/p/cr-q/creatives").text
                if marker in body:
                    fail("the waiting line showed with no pending question")
                    return 1

                client.post("/api/questions/create", json={
                    "project_slug": "cr-q", "run_id": str(asker),
                    "tool_use_id": "smoke-cr-q1",
                    "question": "real figure?", "options": []})
                body = client.get("/p/cr-q/creatives").text
                if body.count(marker) != 1:
                    fail(f"one campaign asked, {body.count(marker)} cards show "
                         f"the waiting line -- it must be matched by run_id, "
                         f"not by 'does this project have any pending question'")
                    return 1

                # A question with an unrelated run_id belongs to no card.
                client.post("/api/questions/create", json={
                    "project_slug": "cr-q", "run_id": "not-a-campaign",
                    "tool_use_id": "smoke-cr-q2",
                    "question": "stray", "options": []})
                body = client.get("/p/cr-q/creatives").text
                if body.count(marker) != 1:
                    fail(f"an unrelated run_id changed the count to "
                         f"{body.count(marker)}; it must light up nothing")
                    return 1
                print("ok: the waiting line marks the campaign that asked, and "
                      "only it")
        finally:
            if prior2 is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior2

        # ---- "already made" is a decision, not a rejection ---------------
        # Closing a proposal you have already produced by hand must be its own
        # terminal state: rejected says the idea was wrong, done says it was
        # right and the work exists. Reversible, and refused from any state
        # where it would contradict work in flight.
        prior3 = os.environ.get("DC_DB_PATH")
        page_db3 = Path(tempfile.mkdtemp(prefix="dc_smoke_cr_done_"))
        repo3 = Path(tempfile.mkdtemp(prefix="dc_smoke_cr_donerepo_"))
        (repo3 / "docs" / "marketing" / "creatives").mkdir(parents=True)
        os.environ["DC_DB_PATH"] = str(page_db3 / "t.db")
        try:
            from starlette.testclient import TestClient as TC3
            with TC3(app) as client:
                svc = ProjectsService(app.state.db)
                proj = await svc.create(
                    slug="cr-done", label="CR done", working_dir=str(repo3))
                await svc.set_setting(
                    proj.id, "creative_dir", "docs/marketing/creatives")
                d = app.state.db
                cid_ = await d.add_creative_proposal(
                    proj.id, source="manual", source_ref="", evidence="checked",
                    title="Voice", angle="", slug_hint="voice")

                if client.post(f"/p/cr-done/creatives/{cid_}/done",
                               follow_redirects=False).status_code != 303:
                    fail("marking a proposed campaign as already made was refused")
                    return 1
                if (await d.get_creative_proposal(cid_))["status"] != "done":
                    fail("the campaign did not reach 'done'")
                    return 1

                # It must not be the same thing as rejected.
                if (await d.get_creative_proposal(cid_))["status"] == "rejected":
                    fail("'already made' collapsed into 'rejected'")
                    return 1

                # A re-scan cannot resurrect it: the unique (project_id,
                # slug_hint) index is what stops the queue refilling with work
                # that is done.
                if await d.add_creative_proposal(
                        proj.id, source="project_scan", source_ref="x",
                        evidence="again", title="Voice", angle="",
                        slug_hint="voice") is not None:
                    fail("a scan re-proposed a campaign already marked done")
                    return 1

                # Reversible through the same restore the rejected ones use.
                if client.post(f"/p/cr-done/creatives/{cid_}/restore",
                               follow_redirects=False).status_code != 303:
                    fail("an already-made campaign could not be restored")
                    return 1
                if (await d.get_creative_proposal(cid_))["status"] != "proposed":
                    fail("restore did not return the campaign to the queue")
                    return 1

                # Refused mid-assembly: a session is running against it.
                busy = await d.add_creative_proposal(
                    proj.id, source="manual", source_ref="", evidence="checked",
                    title="Two", angle="", slug_hint="two")
                await d.start_creative_attempt(busy, session_id="s")
                if client.post(f"/p/cr-done/creatives/{busy}/done",
                               follow_redirects=False).status_code != 409:
                    fail("a campaign being assembled was marked done -- the "
                         "maker is still writing to its directory")
                    return 1
                print("ok: 'already made' closes a proposal without rejecting "
                      "it, survives a re-scan, reverses, and is refused "
                      "mid-assembly")
        finally:
            if prior3 is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior3

        # ---- a hand-written campaign is buildable at all -----------------
        # The form used to record evidence as "proposed by the operator", a
        # note about who asked rather than a claim. make-creative.md reads
        # evidence as the fact the creative must be true to and refuses to
        # state anything it does not carry, so every manual campaign was
        # unbuildable by construction. Observed in production: proposal 20
        # ("Реклама фирмы") came back failed without a render.
        prior4 = os.environ.get("DC_DB_PATH")
        page_db4 = Path(tempfile.mkdtemp(prefix="dc_smoke_cr_ev_"))
        repo4 = Path(tempfile.mkdtemp(prefix="dc_smoke_cr_evrepo_"))
        (repo4 / "docs" / "marketing" / "creatives").mkdir(parents=True)
        os.environ["DC_DB_PATH"] = str(page_db4 / "t.db")
        try:
            from starlette.testclient import TestClient as TC4
            with TC4(app) as client:
                svc = ProjectsService(app.state.db)
                proj = await svc.create(
                    slug="cr-ev", label="CR ev", working_dir=str(repo4))
                await svc.set_setting(
                    proj.id, "creative_dir", "docs/marketing/creatives")

                client.post("/p/cr-ev/creatives/add",
                            data={"title": "Company intro", "angle": "a reel"},
                            follow_redirects=False)
                row = await app.state.db.find_creative_proposal_by_slug(
                    proj.id, "company-intro")
                ev = (row["evidence"] or "") if row else ""
                if "proposed by the operator" in ev:
                    fail("a hand-written campaign still records who asked as "
                         "its evidence -- the maker reads that as carrying no "
                         "claim and cannot build anything from it")
                    return 1
                if "repository" not in ev:
                    fail(f"blank evidence should point at checkable material; "
                         f"got {ev!r}")
                    return 1

                # An operator who names the fact keeps it verbatim.
                client.post("/p/cr-ev/creatives/add",
                            data={"title": "Second", "angle": "x",
                                  "evidence": "products.json lists 4 shipped tools"},
                            follow_redirects=False)
                row2 = await app.state.db.find_creative_proposal_by_slug(
                    proj.id, "second")
                if row2["evidence"] != "products.json lists 4 shipped tools":
                    fail(f"the operator's own evidence was not kept: "
                         f"{row2['evidence']!r}")
                    return 1
                print("ok: a hand-written campaign records what it rests on, "
                      "not who asked")
        finally:
            if prior4 is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior4

        # ---- the maker can ask at all ------------------------------------
        cmd = (ROOT / "templates" / "starter-kit" / "commands"
               / "make-creative.md").read_text(encoding="utf-8")
        for needle in ("/api/questions/create", "poll", "tool_use_id", "run_id"):
            if needle not in cmd:
                fail(f"make-creative.md lost {needle!r} -- without the ask "
                     f"channel the maker's only answer to an unverifiable "
                     f"claim is to fail the campaign")
                return 1
        print("ok: make-creative.md carries the question channel")

        print("PASS")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
