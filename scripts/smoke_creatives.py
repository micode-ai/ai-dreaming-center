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
        finally:
            if prior is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior

        print("PASS")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
