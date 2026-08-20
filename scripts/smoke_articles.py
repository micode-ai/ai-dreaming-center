"""Smoke-тест article pipeline.

Покрывает: вставку предложения, дедуп по (project_id, slug_hint), переходы
статусов, фиксацию черновика с выводом верификации и публикацию.

Выход 0 — всё ок; ненулевой код + диагностика в stderr — что упало.
"""
from __future__ import annotations
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Windows console here is cp1250: an unencodable char in print() aborts the
# run mid-way. Force UTF-8 on both streams (fail() writes to stderr).
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

from dreaming.services.db import SqliteDB  # noqa: E402
from dreaming.services.projects import ProjectsService  # noqa: E402


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_articles_"))
    db = SqliteDB(str(tmp / "test.db"))
    await db.connect()
    try:
        project = await ProjectsService(db).create(
            slug="demo", label="Demo", working_dir=str(tmp),
        )
        pid = project.id

        # ── insert + dedup ─────────────────────────────────────────
        first = await db.add_article_proposal(
            pid, source="radar", source_ref="178",
            evidence="GLM-5.3 release, 2026-08-19, source: latent_space",
            title="What GLM-5.3 changes for our agents",
            angle="Compare the new context window against our routing costs",
            slug_hint="glm-53-agent-routing",
            funnel_level="top", locales="pl,en,ru", tags_json='["AI","agents"]',
        )
        if not first:
            fail("add_article_proposal returned no id")
            return 1
        dup = await db.add_article_proposal(
            pid, source="project_scan", source_ref="abc123",
            evidence="same subject from another feeder",
            title="GLM-5.3 again", angle="…",
            slug_hint="glm-53-agent-routing",
        )
        if dup is not None:
            fail(f"dedup broken: second insert returned {dup}, want None")
            return 1
        print("ok: insert + dedup on (project_id, slug_hint)")

        # ── status transitions ─────────────────────────────────────
        row = await db.get_article_proposal(first)
        if row["status"] != "proposed":
            fail(f"initial status = {row['status']}, want 'proposed'")
            return 1
        await db.set_article_proposal_status(first, "approved")
        await db.set_article_proposal_status(first, "writing")
        row = await db.get_article_proposal(first)
        if row["status"] != "writing" or not row["decided_at"]:
            fail(f"after approve/writing: status={row['status']}, "
                 f"decided_at={row['decided_at']}")
            return 1
        print("ok: proposed -> approved -> writing, decided_at stamped")

        # ── draft with verification ────────────────────────────────
        await db.mark_article_written(
            first, draft_ref="src/data/blog-posts.json",
            verify_output="dist/blog/glm-53-agent-routing/index.html written",
            writer_agent="blog-writer", verify_ok=True,
        )
        row = await db.get_article_proposal(first)
        if row["status"] != "drafted" or row["verify_ok"] != 1:
            fail(f"after write: status={row['status']}, verify_ok={row['verify_ok']}")
            return 1
        if not row["written_at"] or "dist/blog" not in row["verify_output"]:
            fail("written_at or verify_output not persisted")
            return 1
        print("ok: drafted with verify_output + verify_ok")

        # ── retry clears the previous attempt's stale results ───────
        # A plain status flip to 'writing' would leave the old draft_ref /
        # verify_output / verify_ok / writer_agent sitting next to a fresh
        # attempt's error -- two contradictory truths about the same draft.
        await db.start_article_attempt(first, session_id="retry-session")
        row = await db.get_article_proposal(first)
        if row["status"] != "writing":
            fail(f"start_article_attempt: status={row['status']}, want 'writing'")
            return 1
        if (row["draft_ref"] or row["verify_output"] or row["writer_agent"]
                or row["error_message"]):
            fail("start_article_attempt left stale fields: "
                 f"draft_ref={row['draft_ref']!r}, "
                 f"verify_output={row['verify_output']!r}, "
                 f"writer_agent={row['writer_agent']!r}, "
                 f"error_message={row['error_message']!r}")
            return 1
        if row["verify_ok"] != 0:
            fail(f"start_article_attempt: verify_ok={row['verify_ok']}, want 0")
            return 1
        if row["session_id"] != "retry-session":
            fail(f"start_article_attempt: session_id={row['session_id']!r}, "
                 "want 'retry-session'")
            return 1
        print("ok: start_article_attempt clears draft_ref/verify_output/"
              "writer_agent/error_message and resets verify_ok")

        # ── failure path ───────────────────────────────────────────
        second = await db.add_article_proposal(
            pid, source="center", source_ref="idea-42",
            evidence="product idea 42 has no article yet",
            title="Second", angle="…", slug_hint="second-piece",
        )
        await db.set_article_proposal_status(
            second, "failed", error_message="npm run build exited 1",
        )
        row = await db.get_article_proposal(second)
        if row["status"] != "failed" or "exited 1" not in row["error_message"]:
            fail(f"failure path: status={row['status']}, err={row['error_message']}")
            return 1
        print("ok: failed carries error_message")

        # ── publish ────────────────────────────────────────────────
        await db.mark_article_published(first, commit_ref="deadbeef")
        row = await db.get_article_proposal(first)
        if row["status"] != "published" or row["commit_ref"] != "deadbeef":
            fail(f"publish: status={row['status']}, ref={row['commit_ref']}")
            return 1
        print("ok: published with commit_ref")

        # ── listing + counts ───────────────────────────────────────
        proposed = await db.list_article_proposals(project_id=pid, status="failed")
        if len(proposed) != 1 or proposed[0]["id"] != second:
            fail(f"status filter returned {len(proposed)} rows")
            return 1
        counts = {r["status"]: r["n"] for r in await db.article_status_counts(pid)}
        if counts.get("published") != 1 or counts.get("failed") != 1:
            fail(f"counts wrong: {counts}")
            return 1
        print("ok: list filter + status counts")

        # ── API: ingest / dedupe / write-back ──────────────────────
        from starlette.testclient import TestClient
        from dreaming.main import app
        from dreaming.config import settings as load_app_settings

        # This section talks to the real configured db (not the tmp one above),
        # so wipe this script's own rows first — otherwise from the second run
        # onward the "fresh insert" assertion below would silently degrade into
        # re-testing the dedupe branch instead.
        real_db = SqliteDB(load_app_settings().db_path)
        await real_db.connect()
        try:
            await real_db.execute(
                "DELETE FROM article_proposals WHERE slug_hint LIKE 'smoke-%'"
            )
            with TestClient(app) as client:
                base = "/api/p/ai-dreaming-center/articles"
                blank = client.post(f"{base}/ingest", json={
                    "title": "No evidence here", "angle": "…",
                    "slug_hint": "smoke-no-evidence", "evidence": "   ",
                    "source": "project_scan",
                })
                if blank.status_code != 400:
                    fail(f"blank evidence: got {blank.status_code}, want 400")
                    return 1
                good = client.post(f"{base}/ingest", json={
                    "title": "Smoke article", "angle": "…",
                    "slug_hint": "smoke-pipeline-check",
                    "evidence": "commit 503ed08 shipped the density fix",
                    "source": "project_scan", "source_ref": "503ed08",
                })
                if good.status_code != 201 or good.json().get("duplicate") is not False:
                    fail(f"fresh ingest: got {good.status_code} {good.text[:200]}")
                    return 1
                api_id = good.json()["id"]
                again = client.post(f"{base}/ingest", json={
                    "title": "Smoke article dup", "angle": "…",
                    "slug_hint": "smoke-pipeline-check",
                    "evidence": "same subject", "source": "radar",
                })
                if again.status_code != 200 or again.json().get("duplicate") is not True:
                    fail(f"dedupe: got {again.status_code} {again.text[:200]}")
                    return 1
                detail = client.get(f"/api/articles/{api_id}")
                if detail.status_code != 200 or detail.json()["slug_hint"] != "smoke-pipeline-check":
                    fail(f"detail GET wrong: {detail.status_code} {detail.text[:200]}")
                    return 1
                # write-back is gated on 'writing'; nudge the row there directly
                # since Task 2 doesn't add an approval endpoint.
                await real_db.set_article_proposal_status(api_id, "writing")
                write_payload = {
                    "draft_ref": "content/blog/ru/smoke.md",
                    "verify_output": "no verify command configured",
                    "writer_agent": "self", "verify_ok": False,
                }
                back = client.post(f"/api/articles/{api_id}/written", json=write_payload)
                if back.status_code != 200:
                    fail(f"write-back failed: {back.status_code} {back.text[:200]}")
                    return 1
                # row is now 'drafted' -> a repeat write-back must be refused
                again_back = client.post(f"/api/articles/{api_id}/written", json=write_payload)
                if again_back.status_code != 409:
                    fail(f"write-back guard: got {again_back.status_code}, want 409")
                    return 1

                page = client.get("/p/ai-dreaming-center/articles")
                if page.status_code != 200:
                    fail(f"/articles page: {page.status_code}")
                    return 1
                if "smoke-pipeline-check" not in page.text:
                    fail("the ingested proposal is not rendered on the page")
                    return 1
                print("ok: /p/{slug}/articles renders the proposal")

                queue = client.get("/articles")
                if queue.status_code != 200:
                    fail(f"/articles queue: {queue.status_code}")
                    return 1
                print("ok: cross-project /articles queue renders")

                # Test count_article_proposals with project filter
                smoke_p1 = await ProjectsService(real_db).create(
                    slug="smoke-count-p1", label="Smoke Count P1", working_dir=str(tmp),
                )
                smoke_p2 = await ProjectsService(real_db).create(
                    slug="smoke-count-p2", label="Smoke Count P2", working_dir=str(tmp),
                )
                await real_db.add_article_proposal(
                    smoke_p1.id, source="smoke", source_ref="1",
                    evidence="test", title="Smoke count 1", angle="…",
                    slug_hint="smoke-count-1",
                )
                await real_db.add_article_proposal(
                    smoke_p2.id, source="smoke", source_ref="2",
                    evidence="test", title="Smoke count 2", angle="…",
                    slug_hint="smoke-count-2",
                )
                count_p1 = await real_db.count_article_proposals(
                    status="proposed", project_ids=[smoke_p1.id],
                )
                if count_p1 != 1:
                    fail(f"count_article_proposals for p1: got {count_p1}, want 1")
                    return 1
                count_both = await real_db.count_article_proposals(
                    status="proposed", project_ids=[smoke_p1.id, smoke_p2.id],
                )
                if count_both != 2:
                    fail(f"count_article_proposals for both: got {count_both}, want 2")
                    return 1
                count_empty = await real_db.count_article_proposals(
                    status="proposed", project_ids=[],
                )
                if count_empty != 0:
                    fail(f"count_article_proposals for empty list: got {count_empty}, want 0")
                    return 1
                try:
                    await real_db.execute(
                        "DELETE FROM projects WHERE id IN (?, ?)",
                        (smoke_p1.id, smoke_p2.id),
                    )
                    await real_db.execute(
                        "DELETE FROM article_proposals WHERE project_id IN (?, ?)",
                        (smoke_p1.id, smoke_p2.id),
                    )
                finally:
                    pass
                print("ok: count_article_proposals counts correctly per project")

                # A status outside the seven the page groups by must still
                # show up (in the catch-all "other" group) instead of
                # silently vanishing -- status has no CHECK constraint.
                ai_dc_project = await ProjectsService(real_db).get_by_slug(
                    "ai-dreaming-center",
                )
                weird_id = await real_db.add_article_proposal(
                    ai_dc_project.id, source="project_scan",
                    source_ref="weird-status",
                    evidence="smoke: a status outside _ORDER must not vanish",
                    title="Smoke weird-status row", angle="…",
                    slug_hint="smoke-weird-status",
                )
                if weird_id is None:
                    fail("weird-status smoke row failed to insert")
                    return 1
                try:
                    await real_db.set_article_proposal_status(weird_id, "weird")
                    weird_page = client.get("/p/ai-dreaming-center/articles")
                    if weird_page.status_code != 200:
                        fail(f"/articles page (weird status): {weird_page.status_code}")
                        return 1
                    if "smoke-weird-status" not in weird_page.text:
                        fail("a row with a status outside _ORDER vanished from the page")
                        return 1
                finally:
                    await real_db.execute(
                        "DELETE FROM article_proposals WHERE id=?", (weird_id,),
                    )
                print("ok: a status outside _ORDER lands in the catch-all group")
        finally:
            await real_db.close()
        print("ok: API ingest (201 fresh / 200 dedupe), detail, write-back, "
              "write-back guard (409 once drafted)")

        # ── writer resolution + publish gate ───────────────────────
        from dreaming.services import articles
        agents_dir = tmp / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        if articles.resolve_writer(str(tmp)) != "self":
            fail("resolve_writer: empty agents dir must give 'self'")
            return 1
        (agents_dir / "blog-writer.md").write_text("---\nname: blog-writer\n---\n",
                                                   encoding="utf-8")
        (agents_dir / "backend-developer.md").write_text("---\nname: x\n---\n",
                                                         encoding="utf-8")
        got = articles.resolve_writer(str(tmp))
        if got != "blog-writer":
            fail(f"autodetect picked {got!r}, want 'blog-writer'")
            return 1
        if articles.resolve_writer(str(tmp), configured="kb-page-author") != "kb-page-author":
            fail("configured agent must win over autodetect")
            return 1
        print("ok: resolve_writer — configured > autodetect > self")

        gate_cases = [
            ({"verify_ok": 1, "status": "drafted"}, "npm run build", "commit", True),
            ({"verify_ok": 0, "status": "drafted"}, "npm run build", "commit", False),
            ({"verify_ok": 0, "status": "drafted"}, "", "commit", True),
            ({"verify_ok": 1, "status": "drafted"}, "npm run build", "off", False),
            ({"verify_ok": 1, "status": "proposed"}, "npm run build", "commit", False),
        ]
        for row_in, cmd, mode, want in gate_cases:
            allowed, reason = articles.can_publish(row_in, cmd, mode)
            if allowed is not want:
                fail(f"can_publish({row_in}, {cmd!r}, {mode!r}) = {allowed} "
                     f"({reason}), want {want}")
                return 1
        if articles.publish_label(False, "") != "unverified":
            fail("publish_label: empty verify cmd must read 'unverified'")
            return 1
        print("ok: publish gate — verified / failed / unverified / off")

        cases = [
            ("What GLM-5.3 changes for our agents", "what-glm-5-3-changes-for-our"),
            ("Автозаполнение по NIP", "nip"),
            ("   ", ""),
        ]
        for raw, want_prefix in cases:
            got = articles.slugify(raw)
            if want_prefix and not got.startswith(want_prefix.split("-")[0]):
                fail(f"slugify({raw!r}) = {got!r}, expected to start like {want_prefix!r}")
                return 1
            if " " in got or got != got.lower():
                fail(f"slugify({raw!r}) = {got!r}: spaces or uppercase left")
                return 1
        print("ok: slugify produces hyphenated lowercase slugs")

        # Truncation must never let two distinct titles collide: a shared
        # 6-word prefix must not produce one slug_hint for two proposals.
        title_a = "Improve error handling in the parser today"
        title_b = "Improve error handling in the parser tomorrow"
        slug_a = articles.slugify(title_a)
        slug_b = articles.slugify(title_b)
        if slug_a == slug_b:
            fail(f"slugify collision: {title_a!r} and {title_b!r} both gave {slug_a!r}")
            return 1
        prefix = "improve-error-handling-in-the-parser-"
        if not slug_a.startswith(prefix) or not slug_b.startswith(prefix):
            fail(f"slugify truncation prefix wrong: {slug_a!r}, {slug_b!r}")
            return 1
        short = articles.slugify("Ship it")
        if short != "ship-it":
            fail(f"slugify short title must have no suffix: got {short!r}")
            return 1
        print("ok: slugify appends a hash suffix only when truncation would collide")

        # ── starter-kit template present and self-consistent ───────
        kit = ROOT / "templates" / "starter-kit" / "commands" / "article-ideas-scan.md"
        if not kit.exists():
            fail("article-ideas-scan.md missing from the starter kit")
            return 1
        body = kit.read_text(encoding="utf-8")
        for needle in ("/api/p/", "articles/ingest", "evidence", "DREAMING_API_URL"):
            if needle not in body:
                fail(f"article-ideas-scan.md does not mention {needle!r}")
                return 1
        print("ok: article-ideas-scan command shipped in the starter kit")

        kit2 = ROOT / "templates" / "starter-kit" / "commands" / "write-article.md"
        if not kit2.exists():
            fail("write-article.md missing from the starter kit")
            return 1
        body2 = kit2.read_text(encoding="utf-8")
        for needle in ("/api/articles/", "/written", "verify_ok", "draft_ref"):
            if needle not in body2:
                fail(f"write-article.md does not mention {needle!r}")
                return 1
        print("ok: write-article command shipped in the starter kit")

        # ── publish: real git repo in a temp dir ───────────────────
        import re
        import subprocess
        from dreaming.services import article_publish

        repo = tmp / "repo"
        (repo / "content").mkdir(parents=True)
        def git(*args, cwd=repo):
            return subprocess.run(["git", *args], cwd=str(cwd),
                                  capture_output=True, text=True)
        git("init", "-q")
        git("config", "user.email", "smoke@example.test")
        git("config", "user.name", "Smoke")
        (repo / "README.md").write_text("seed\n", encoding="utf-8")
        git("add", "README.md")
        git("commit", "-q", "-m", "seed")

        article = repo / "content" / "piece.md"
        article.write_text("# Piece\n", encoding="utf-8")
        noise = repo / "unrelated.txt"
        noise.write_text("do not commit me\n", encoding="utf-8")

        sha = await article_publish.publish(
            str(repo), ["content/piece.md"],
            message="publish: piece (unverified)", push=False,
        )
        if not re.fullmatch(r"[0-9a-f]{40}", sha or ""):
            fail(f"publish returned a malformed sha: {sha!r}")
            return 1
        listed = git("show", "--name-only", "--pretty=format:", sha).stdout.split()
        if listed != ["content/piece.md"]:
            fail(f"commit contains {listed}, want only content/piece.md")
            return 1
        if not noise.exists() or "do not commit me" not in noise.read_text(encoding="utf-8"):
            fail("publish touched the unrelated working-tree file")
            return 1
        status_after = git("status", "--porcelain").stdout
        if "unrelated.txt" not in status_after:
            fail("the unrelated file left the working tree — stash or add -A happened")
            return 1
        print("ok: publish commits only draft paths, leaves the rest alone")

        # ── split_paths: whole-string-first, then comma/newline fallback ──
        (repo / "content" / "multi-a.md").write_text("a\n", encoding="utf-8")
        (repo / "content" / "multi-b.md").write_text("b\n", encoding="utf-8")
        got = article_publish.split_paths(
            "content/multi-a.md\ncontent/multi-b.md", str(repo),
        )
        if got != ["content/multi-a.md", "content/multi-b.md"]:
            fail(f"split_paths (newline-separated): got {got}")
            return 1
        got = article_publish.split_paths(
            "content/multi-a.md,content/multi-b.md", str(repo),
        )
        if got != ["content/multi-a.md", "content/multi-b.md"]:
            fail(f"split_paths (comma-separated): got {got}")
            return 1
        # A comma inside a real filename must not be chopped into fragments:
        # the whole string wins when it resolves to an existing file.
        (repo / "content" / "notes, v2.md").write_text(
            "comma in the filename\n", encoding="utf-8",
        )
        got = article_publish.split_paths("content/notes, v2.md", str(repo))
        if got != ["content/notes, v2.md"]:
            fail(f"split_paths must not chop a real filename's own comma: got {got}")
            return 1
        print("ok: split_paths — newline/comma split, whole string wins when it's a real file")

        # ── build_message: title + the verification claim it may make ─────
        row_for_msg = {"title": "My Piece", "slug_hint": "my-piece"}
        msg = article_publish.build_message(row_for_msg, "unverified")
        if "My Piece" not in msg or "verification: unverified" not in msg:
            fail(f"build_message (unverified) missing title/label: {msg!r}")
            return 1
        msg = article_publish.build_message(row_for_msg, "verified")
        if "My Piece" not in msg or "verification: verified" not in msg:
            fail(f"build_message (verified) missing title/label: {msg!r}")
            return 1
        print("ok: build_message carries the title and the verification label")

        # ── path validation: reject anything that isn't a plain in-repo file ──
        before_cached = git("diff", "--cached", "--name-only").stdout
        for bad, why in [
            ("content/../.env", "a '..' segment"),
            ("content/*.md", "a glob character"),
            ("content", "a directory, not a file"),
        ]:
            try:
                await article_publish.publish(
                    str(repo), [bad], message="should never commit", push=False,
                )
            except article_publish.PublishError:
                pass
            else:
                fail(f"publish accepted an invalid path ({why}): {bad!r}")
                return 1
        after_cached = git("diff", "--cached", "--name-only").stdout
        if after_cached != before_cached:
            fail("a rejected path still touched the index: "
                 f"before={before_cached!r} after={after_cached!r}")
            return 1
        print("ok: publish rejects '..' segments, glob pathspecs, and directory paths, "
              "index untouched")

        # A target path that someone else has already STAGED must refuse
        # rather than sweep their index entry into our commit.
        article.write_text("# Piece edited by hand\n", encoding="utf-8")
        git("add", "content/piece.md")
        try:
            await article_publish.publish(
                str(repo), ["content/piece.md"], message="second", push=False,
            )
        except article_publish.PublishError:
            print("ok: dirty article path refuses to publish")
        else:
            fail("dirty article path published anyway")
            return 1

        print("PASS")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
