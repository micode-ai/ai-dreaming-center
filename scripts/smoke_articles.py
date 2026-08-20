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
            writer_agent="blog-writer", verify_ok=True, verify_label="verified",
        )
        row = await db.get_article_proposal(first)
        if row["status"] != "drafted" or row["verify_ok"] != 1:
            fail(f"after write: status={row['status']}, verify_ok={row['verify_ok']}")
            return 1
        if not row["written_at"] or "dist/blog" not in row["verify_output"]:
            fail("written_at or verify_output not persisted")
            return 1
        if row["verify_label"] != "verified":
            fail(f"verify_label not persisted: got {row['verify_label']!r}")
            return 1
        print("ok: drafted with verify_output + verify_ok + verify_label")

        # mark_article_written must refuse a row that is not 'writing' (I5's
        # column addition rides on the same precondition C1/C2 rely on) --
        # `first` is already 'drafted' from the call just above.
        refused = await db.mark_article_written(
            first, draft_ref="should-not-land.md", verify_output="",
            writer_agent="blog-writer", verify_ok=True, verify_label="verified",
        )
        if refused:
            fail("mark_article_written applied to a row that was not 'writing'")
            return 1
        print("ok: mark_article_written refuses a non-'writing' row")

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
        # `first` is still 'writing' from the retry test above.
        # mark_article_published must refuse anything that isn't 'drafted' --
        # this is the write-side half of C2 (see the two-publishes pin
        # further below for the full regression it closes).
        refused = await db.mark_article_published(first, commit_ref="deadbeef")
        if refused:
            fail("mark_article_published applied to a 'writing' row")
            return 1
        # Bring `first` back to 'drafted' the normal way (a second write-back
        # completing) before testing the drafted -> published transition.
        await db.mark_article_written(
            first, draft_ref="src/data/blog-posts.json",
            verify_output="dist/blog/glm-53-agent-routing/index.html written",
            writer_agent="blog-writer", verify_ok=True, verify_label="verified",
        )
        await db.mark_article_published(first, commit_ref="deadbeef")
        row = await db.get_article_proposal(first)
        if row["status"] != "published" or row["commit_ref"] != "deadbeef":
            fail(f"publish: status={row['status']}, ref={row['commit_ref']}")
            return 1
        print("ok: published with commit_ref")

        # ── C1 pin: 'published' is terminal ─────────────────────────
        # This is the exact regression from the article-pipeline final-fixes
        # review: two tabs open, one publishes, the other's stale 'drafted'
        # card still offers Retry, and that POST used to sail straight into
        # start_article_attempt, wiping draft_ref/verify_output/verify_ok/
        # writer_agent while keeping commit_ref. A stray (re)dispatch must
        # be refused, and the row must come out exactly as it went in.
        restarted = await db.start_article_attempt(first, session_id="should-not-start")
        if restarted:
            fail("start_article_attempt resurrected a 'published' row into 'writing'")
            return 1
        row = await db.get_article_proposal(first)
        if row["status"] != "published" or row["commit_ref"] != "deadbeef":
            fail("C1: a refused re-dispatch attempt disturbed the published row: "
                 f"status={row['status']!r}, commit_ref={row['commit_ref']!r}")
            return 1
        print("ok: C1 -- start_article_attempt refuses a 'published' row, "
              "leaving status and commit_ref untouched")

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

        # ── count_article_proposals: per-project filtering (M6) ─────
        # This only exercises SQL filtering, so it runs entirely against
        # this script's own throwaway database -- no reason to create (and
        # then have to remember to reliably delete) real rows in the user's
        # live project list just to test a WHERE clause.
        count_p1_project = await ProjectsService(db).create(
            slug="smoke-count-p1", label="Smoke Count P1", working_dir=str(tmp),
        )
        count_p2_project = await ProjectsService(db).create(
            slug="smoke-count-p2", label="Smoke Count P2", working_dir=str(tmp),
        )
        await db.add_article_proposal(
            count_p1_project.id, source="smoke", source_ref="1",
            evidence="test", title="Smoke count 1", angle="…",
            slug_hint="smoke-count-1",
        )
        await db.add_article_proposal(
            count_p2_project.id, source="smoke", source_ref="2",
            evidence="test", title="Smoke count 2", angle="…",
            slug_hint="smoke-count-2",
        )
        count_p1 = await db.count_article_proposals(
            status="proposed", project_ids=[count_p1_project.id],
        )
        if count_p1 != 1:
            fail(f"count_article_proposals for p1: got {count_p1}, want 1")
            return 1
        count_both = await db.count_article_proposals(
            status="proposed",
            project_ids=[count_p1_project.id, count_p2_project.id],
        )
        if count_both != 2:
            fail(f"count_article_proposals for both: got {count_both}, want 2")
            return 1
        count_empty = await db.count_article_proposals(
            status="proposed", project_ids=[],
        )
        if count_empty != 0:
            fail(f"count_article_proposals for empty list: got {count_empty}, want 0")
            return 1
        print("ok: count_article_proposals counts correctly per project")

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

                # ── manual add: blank topic refused, honest evidence recorded ──
                blank = client.post("/p/ai-dreaming-center/articles/add",
                                    data={"title": "   ", "angle": "x"},
                                    follow_redirects=False)
                if blank.status_code != 400:
                    fail(f"manual add with a blank topic: {blank.status_code}, want 400")
                    return 1
                made = client.post("/p/ai-dreaming-center/articles/add",
                                   data={"title": "Smoke manual topic",
                                         "angle": "an intro prompt from the operator",
                                         "venue": ""},
                                   follow_redirects=False)
                if made.status_code != 303:
                    fail(f"manual add: {made.status_code}, want 303")
                    return 1
                # the row must carry honest, non-blank evidence naming the request
                made_row = None
                for r in await real_db.list_article_proposals(status="proposed"):
                    if r["slug_hint"].startswith("smoke-manual") or r["title"] == "Smoke manual topic":
                        made_row = r
                        break
                if made_row is None:
                    fail("manual proposal was not created")
                    return 1
                if made_row["source"] != "manual" or not made_row["evidence"].strip():
                    fail(f"manual row: source={made_row['source']}, evidence={made_row['evidence']!r}")
                    return 1
                if "an intro prompt from the operator" not in made_row["angle"]:
                    fail("the intro prompt did not reach the angle")
                    return 1
                await real_db.execute("DELETE FROM article_proposals WHERE id=?", (made_row["id"],))
                print("ok: manual add -- blank topic refused, row carries honest evidence")

                ai_dc_project = await ProjectsService(real_db).get_by_slug(
                    "ai-dreaming-center",
                )

                # C1, route level: a stale Approve/Retry POST against an
                # already-'published' row must be refused (409) and must not
                # disturb the row -- the same regression pinned at the DB
                # layer above (start_article_attempt), now through the
                # actual HTTP endpoint a browser would hit. The status
                # precondition in articles_approve fires before any other
                # check (blog_dir, starter-kit install, process_manager), so
                # this needs none of that set up.
                c1_id = await real_db.add_article_proposal(
                    ai_dc_project.id, source="project_scan",
                    source_ref="c1-route-check",
                    evidence="smoke: approving a published row must be refused",
                    title="Smoke C1 route check", angle="…",
                    slug_hint="smoke-c1-route-check",
                )
                try:
                    await real_db.set_article_proposal_status(c1_id, "drafted")
                    if not await real_db.mark_article_published(
                        c1_id, commit_ref="smoke-c1-deadbeef",
                    ):
                        fail("C1 setup: mark_article_published on a drafted "
                             "smoke row failed")
                        return 1
                    resp = client.post(
                        f"/p/ai-dreaming-center/articles/{c1_id}/approve"
                    )
                    if resp.status_code != 409:
                        fail(f"C1: approving a published row got "
                             f"{resp.status_code}, want 409")
                        return 1
                    c1_row = await real_db.get_article_proposal(c1_id)
                    if (c1_row["status"] != "published"
                            or c1_row["commit_ref"] != "smoke-c1-deadbeef"):
                        fail("C1: approve route disturbed a published row: "
                             f"status={c1_row['status']!r}, "
                             f"commit_ref={c1_row['commit_ref']!r}")
                        return 1
                finally:
                    await real_db.execute(
                        "DELETE FROM article_proposals WHERE id=?", (c1_id,),
                    )
                print("ok: C1 -- POST .../approve on a published row is "
                      "refused (409), status and commit_ref untouched")

                # A status outside the seven the page groups by must still
                # show up (in the catch-all "other" group) instead of
                # silently vanishing -- status has no CHECK constraint.
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

                # A proposal whose venue has no article_blog_dir must be
                # refused with 400 naming the venue, not silently dispatched.
                # `api_id` has no target_project_id and ai-dreaming-center has
                # no article_venue_project setting, so its venue is itself --
                # this is the NULL-venue regression case, not a new one.
                r = client.post(
                    f"/p/ai-dreaming-center/articles/{api_id}/approve",
                    follow_redirects=False,
                )
                if r.status_code not in (400, 409):
                    fail(f"approve without a venue blog dir: {r.status_code}, "
                         "want 400/409")
                    return 1
                if r.status_code == 400 and "venue" not in r.json().get("detail", ""):
                    fail("400 for a missing blog dir must name the venue: "
                         f"{r.text[:200]}")
                    return 1
                print("ok: approve refuses before dispatch when the venue "
                      "has no blog dir, naming it")
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

        # ── resolve_article_root: nested-repo blog vs in-repo blog ──
        import subprocess as _subprocess
        def _git_init(path: Path) -> None:
            path.mkdir(parents=True, exist_ok=True)
            _subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
            _subprocess.run(["git", "config", "user.email", "smoke@example.test"],
                            cwd=str(path), check=True)
            _subprocess.run(["git", "config", "user.name", "Smoke"],
                            cwd=str(path), check=True)

        # A parent repo containing a nested repo with its own blog dir --
        # this is the mi-code-ai / micode-landing-page shape: the parent is
        # a git repo, and a wholly separate git repo (own .git, own remote
        # in the real case) sits nested inside it with the blog underneath.
        rar_parent = tmp / "rar_parent"
        _git_init(rar_parent)
        rar_nested = rar_parent / "nested"
        _git_init(rar_nested)
        (rar_nested / "blog").mkdir(parents=True)
        got_root = await articles.resolve_article_root(str(rar_parent), "nested/blog")
        if Path(got_root) != rar_nested.resolve():
            fail(f"resolve_article_root (nested repo): got {got_root!r}, "
                 f"want {rar_nested.resolve()!r}")
            return 1
        print("ok: resolve_article_root finds the nested repo's own root")

        # A single repo with the blog inside it -- the regression guard for
        # accounting-ai-agent and ai-budget-assistant, whose blog sits in
        # their own repository. Must equal working_dir exactly, unchanged.
        rar_single = tmp / "rar_single"
        _git_init(rar_single)
        (rar_single / "content" / "blog").mkdir(parents=True)
        got_root = await articles.resolve_article_root(str(rar_single), "content/blog")
        if got_root != str(rar_single):
            fail(f"resolve_article_root (in-repo blog): got {got_root!r}, "
                 f"want unchanged working_dir {str(rar_single)!r}")
            return 1
        print("ok: resolve_article_root — in-repo blog returns working_dir unchanged")

        # Safe-fallback cases: each must return working_dir unchanged.
        fallback_cases = [
            ("", "empty blog_dir"),
            ("../escape", "'..' segment"),
            (str(Path(rar_single.anchor) / "somewhere" / "else"), "absolute blog_dir"),
            ("does/not/exist", "non-existent blog_dir"),
        ]
        for bad_blog, why in fallback_cases:
            got_root = await articles.resolve_article_root(str(rar_single), bad_blog)
            if got_root != str(rar_single):
                fail(f"resolve_article_root fallback ({why}): got {got_root!r}, "
                     f"want unchanged {str(rar_single)!r}")
                return 1
        print("ok: resolve_article_root falls back to working_dir for "
              "empty/'..'/absolute/non-existent blog_dir")

        # A directory that is not a git repository at all.
        rar_nogit = tmp / "rar_nogit"
        (rar_nogit / "content" / "blog").mkdir(parents=True)
        got_root = await articles.resolve_article_root(str(rar_nogit), "content/blog")
        if got_root != str(rar_nogit):
            fail(f"resolve_article_root (not a git repo): got {got_root!r}, "
                 f"want unchanged {str(rar_nogit)!r}")
            return 1
        print("ok: resolve_article_root falls back to working_dir when it "
              "is not inside a git repository")

        # Review finding 2: the containment guarantee is asymmetric if only
        # the lexical '..'/absolute checks exist. A project can be
        # registered on a subdirectory of a larger checkout -- working_dir
        # itself holds no .git -- so `git rev-parse --show-toplevel` from
        # under it returns an ANCESTOR of working_dir, not working_dir or a
        # descendant of it. Reproduced for real: before the fix this
        # returned the outer repo's root, a directory strictly above the
        # project. Must fall back to working_dir instead of following it.
        ancestor_outer = tmp / "ancestor_outer"
        _git_init(ancestor_outer)
        ancestor_project = ancestor_outer / "some" / "project"
        (ancestor_project / "content" / "blog").mkdir(parents=True)
        got_root = await articles.resolve_article_root(
            str(ancestor_project), "content/blog",
        )
        if got_root != str(ancestor_project):
            fail(f"resolve_article_root (ancestor escape): got {got_root!r}, "
                 f"want unchanged working_dir {str(ancestor_project)!r} -- "
                 "the derived root escaped the project into a repository "
                 "above it")
            return 1
        print("ok: resolve_article_root refuses an ancestor repo, staying "
              "inside the project's own working_dir")

        # ── session_blog_dir: only re-derive when the root actually moved ──
        # Review finding 1: the DC_ARTICLE_BLOG_DIR reduction used to
        # recompute unconditionally from the raw blog_dir, which broke on
        # exactly the inputs resolve_article_root is built to tolerate --
        # a cross-drive absolute blog_dir raised ValueError out of the path
        # math (an unhandled 500 from the approve route, which only catches
        # RuntimeError), and a '..'-laden blog_dir got silently handed to
        # the write session anyway even though resolve_article_root had
        # already decided it was unsafe to follow. Pin the reduction
        # function itself, not just resolve_article_root's fallback --
        # that gap is exactly what let this regression through the first
        # round of smoke coverage.
        sbd_wd = str(rar_single)  # a real git repo from the block above
        cross_drive = "E:\\evil\\path" if sbd_wd[:1].upper() != "E" else "D:\\evil\\path"
        for bad_blog, why in [
            (cross_drive, "cross-drive absolute blog_dir"),
            ("../escape", "'..'-laden blog_dir"),
        ]:
            fallback_root = await articles.resolve_article_root(sbd_wd, bad_blog)
            if fallback_root != sbd_wd:
                fail(f"session_blog_dir setup ({why}): resolve_article_root "
                     f"did not fall back, got {fallback_root!r}")
                return 1
            got_session_dir = articles.session_blog_dir(sbd_wd, bad_blog, fallback_root)
            if got_session_dir != bad_blog:
                fail(f"session_blog_dir ({why}): got {got_session_dir!r}, "
                     f"want the raw blog_dir {bad_blog!r} untouched")
                return 1
        print("ok: session_blog_dir leaves a cross-drive-absolute or "
              "'..'-laden blog_dir untouched and raises nothing, when "
              "resolve_article_root did not move the root")

        # And the positive case: when the root DOES move (the nested-repo
        # shape), session_blog_dir must actually reduce the path, not just
        # pass everything through untouched.
        sbd_nested_root = await articles.resolve_article_root(
            str(rar_parent), "nested/blog",
        )
        got_nested_session_dir = articles.session_blog_dir(
            str(rar_parent), "nested/blog", sbd_nested_root,
        )
        if got_nested_session_dir != "blog":
            fail(f"session_blog_dir (nested repo): got {got_nested_session_dir!r}, "
                 "want 'blog' (blog_dir made relative to the moved root)")
            return 1
        print("ok: session_blog_dir reduces blog_dir relative to the root "
              "when the root actually moved")

        # ── articles_page: the writer label must reflect the resolved root ──
        # Regression pin for the exact bug this follow-up fixed: the page's
        # "writer" label used to resolve from project.working_dir even
        # though articles_approve (fixed earlier in this task) now dispatches
        # from the derived article root. A label that names a different
        # agent than the one that will actually be dispatched is not
        # decoration, it's a false claim. Mirrors the real mi-code-ai shape:
        # the parent repo's own .claude/agents/ has an unrelated
        # writer-shaped agent name (landing-copywriter, matching the
        # 'copywriter' hint), and the nested repo that actually owns the
        # blog has its own, different writer (blog-writer).
        import os
        page_parent = tmp / "page_parent"
        _git_init(page_parent)
        (page_parent / ".claude" / "agents").mkdir(parents=True)
        (page_parent / ".claude" / "agents" / "landing-copywriter.md").write_text(
            "---\nname: landing-copywriter\n---\n", encoding="utf-8",
        )
        page_nested = page_parent / "nested_landing"
        _git_init(page_nested)
        (page_nested / "blog").mkdir(parents=True)
        (page_nested / ".claude" / "agents").mkdir(parents=True)
        (page_nested / ".claude" / "agents" / "blog-writer.md").write_text(
            "---\nname: blog-writer\n---\n", encoding="utf-8",
        )

        # Isolated DB for this check, same as smoke_orchestration_stream.py /
        # smoke_review.py's pattern: point DC_DB_PATH at a throwaway sqlite
        # file before (re-)entering the TestClient context, so the app's
        # lifespan opens a fresh db instead of the live one. The fixture
        # project and its article_blog_dir setting live only here — never
        # in data/dreaming.db, and never as a change to the real 'test'
        # project's settings.
        prior_db_path_env = os.environ.get("DC_DB_PATH")
        page_db_dir = Path(tempfile.mkdtemp(prefix="dc_smoke_articles_page_"))
        os.environ["DC_DB_PATH"] = str(page_db_dir / "test.db")
        try:
            with TestClient(app) as page_client:
                page_project = await ProjectsService(app.state.db).create(
                    slug="smoke-nested-page", label="Smoke Nested Page",
                    working_dir=str(page_parent),
                )
                await ProjectsService(app.state.db).set_setting(
                    page_project.id, "article_blog_dir", "nested_landing/blog",
                )
                resp = page_client.get("/p/smoke-nested-page/articles")
                if resp.status_code != 200:
                    fail(f"articles_page (nested-repo project): {resp.status_code}")
                    return 1
                if "blog-writer" not in resp.text:
                    fail("articles_page did not show the nested repo's own "
                         "agent (blog-writer) as the writer")
                    return 1
                if "landing-copywriter" in resp.text:
                    fail("articles_page showed the parent repo's unrelated "
                         "agent (landing-copywriter) instead of the nested "
                         "repo's blog-writer -- the label is not using the "
                         "resolved article root")
                    return 1
        finally:
            if prior_db_path_env is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior_db_path_env
        print("ok: /p/{slug}/articles shows the nested repo's own writer "
              "agent, not the parent repo's unrelated one")

        # A project with no article_blog_dir configured at all must still
        # render (the existing "not set" banner stays; resolve_article_root
        # must fall back to the project root rather than erroring).
        os.environ["DC_DB_PATH"] = str(page_db_dir / "test.db")
        try:
            with TestClient(app) as page_client:
                unset_project = await ProjectsService(app.state.db).create(
                    slug="smoke-unset-blog-dir", label="Smoke Unset Blog Dir",
                    working_dir=str(page_parent),
                )
                resp = page_client.get("/p/smoke-unset-blog-dir/articles")
                if resp.status_code != 200:
                    fail("articles_page (no article_blog_dir configured): "
                         f"{resp.status_code}")
                    return 1
        finally:
            if prior_db_path_env is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior_db_path_env
        print("ok: /p/{slug}/articles still renders with no article_blog_dir set")

        # ── the NULL-venue case must be byte-identical, through the route ──
        # Pins the regression that matters: a proposal with target_project_id
        # NULL and no article_venue_project setting -- every real proposal in
        # the live database is in this state. resolve_venue_id's own unit
        # test above proves the pure function; this proves the route wiring
        # actually uses it the way wave A always behaved -- own project, own
        # blog dir inside its own repo, own writer agent, no venue anywhere.
        os.environ["DC_DB_PATH"] = str(page_db_dir / "test.db")
        try:
            with TestClient(app) as page_client:
                null_venue_dir = tmp / "null_venue_project"
                _git_init(null_venue_dir)
                (null_venue_dir / "content" / "blog").mkdir(parents=True)
                (null_venue_dir / ".claude" / "agents").mkdir(parents=True)
                (null_venue_dir / ".claude" / "agents" / "blog-writer.md").write_text(
                    "---\nname: blog-writer\n---\n", encoding="utf-8",
                )
                null_venue_project = await ProjectsService(app.state.db).create(
                    slug="smoke-null-venue", label="Smoke Null Venue",
                    working_dir=str(null_venue_dir),
                )
                await ProjectsService(app.state.db).set_setting(
                    null_venue_project.id, "article_blog_dir", "content/blog",
                )
                # Deliberately no article_venue_project setting -- this is
                # the NULL-venue case, not an override.
                await app.state.db.add_article_proposal(
                    null_venue_project.id, source="manual", source_ref="",
                    evidence="smoke: NULL target_project_id must equal wave A",
                    title="Null venue smoke row", angle="…",
                    slug_hint="smoke-null-venue-row",
                )
                resp = page_client.get("/p/smoke-null-venue/articles")
                if resp.status_code != 200:
                    fail(f"articles_page (NULL-venue equivalence): {resp.status_code}")
                    return 1
                # What the route's _venue_for/resolve_writer chain must
                # produce for the *subject's own* article root -- computed
                # from the same pure functions the route calls, not
                # hardcoded, so this stays true if resolve_writer's autodetect
                # logic changes.
                expected_root = await articles.resolve_article_root(
                    str(null_venue_dir), "content/blog",
                )
                expected_writer = articles.resolve_writer(expected_root, "")
                if expected_writer not in resp.text:
                    fail(f"NULL-venue writer label: expected {expected_writer!r} "
                         f"to appear in the page, it did not")
                    return 1
                # The venue badge must stay invisible when venue == subject.
                # The hint text is new, unique wording -- a much sharper
                # signal than checking for the shared badge-brand CSS class,
                # which other cards on this same page legitimately use.
                if "Репозиторий, в который попадёт статья" in resp.text:
                    fail("NULL-venue row rendered the venue badge, but venue "
                         "equals the subject -- it must stay invisible")
                    return 1

                # ── the positive mirror: venue actually differs from subject ──
                # Only the pure resolve_venue_id function covered this case so
                # far. A page render with target_project_id pre-set exercises
                # the route wiring itself (_venue_for + the template's badge
                # condition) without dispatching any session -- no approve, no
                # write-article, nothing paid.
                other_venue_dir = tmp / "other_venue_project"
                other_venue_dir.mkdir(parents=True, exist_ok=True)
                other_venue_project = await ProjectsService(app.state.db).create(
                    slug="smoke-other-venue", label="Smoke Other Venue",
                    working_dir=str(other_venue_dir),
                )
                await app.state.db.add_article_proposal(
                    null_venue_project.id, source="manual", source_ref="",
                    evidence="smoke: an explicit venue override must show its badge",
                    title="Explicit venue smoke row", angle="…",
                    slug_hint="smoke-explicit-venue-row",
                    target_project_id=other_venue_project.id,
                )
                resp2 = page_client.get("/p/smoke-null-venue/articles")
                if resp2.status_code != 200:
                    fail(f"articles_page (explicit venue): {resp2.status_code}")
                    return 1
                if f"площадка: {other_venue_project.slug}" not in resp2.text:
                    fail("explicit-venue row did not render the venue badge "
                         f"naming {other_venue_project.slug!r}: {resp2.text[:2000]}")
                    return 1
        finally:
            if prior_db_path_env is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior_db_path_env
        print("ok: NULL target_project_id with no article_venue_project shows "
              "the subject's own writer and no venue badge")
        print("ok: an explicit target_project_id override renders the venue "
              "badge, naming that project's slug")

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
        for needle in ("/api/articles/", "/written", "verify_ok", "draft_ref",
                       "DC_ARTICLE_SUBJECT_DIR", "DC_ARTICLE_SUBJECT_SLUG"):
            if needle not in body2:
                fail(f"write-article.md does not mention {needle!r}")
                return 1
        print("ok: write-article command shipped in the starter kit")

        # ── delegation must hand the subject to the delegate ────────
        # Fix round 1: the writer-resolution section told the session to
        # delegate to a subagent without ever mentioning
        # $DC_ARTICLE_SUBJECT_DIR, so a cross-project delegate would be
        # asked to write about a repository it was never pointed at.
        # Scope the check to the delegation section itself (not just
        # "anywhere in the file", which the check above already covers) so
        # a future edit that keeps the mention elsewhere but drops it from
        # the delegation instruction still fails loudly here.
        deleg_start = body2.find("## 3. Find out who writes")
        deleg_end = body2.find("## 4. Verify")
        if deleg_start == -1 or deleg_end == -1 or deleg_end < deleg_start:
            fail("write-article.md: could not locate the delegation section "
                 "to check")
            return 1
        delegation_section = body2[deleg_start:deleg_end]
        if "DC_ARTICLE_SUBJECT_DIR" not in delegation_section:
            fail("write-article.md: the delegation section never tells the "
                 "session to hand $DC_ARTICLE_SUBJECT_DIR to the delegate")
            return 1
        print("ok: write-article.md's delegation section hands the subject "
              "directory to the delegate")

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

        # ── a rollback that itself fails must say so honestly ──────────
        # A separate throwaway repo so this doesn't disturb `repo`'s state.
        # The commit failure itself is real (a plain failing pre-commit
        # hook, no lock-file trickery needed for that half). Forcing the
        # *reset* to also fail deterministically is a different matter: the
        # obvious trick -- have the hook leave a stale .git/index.lock behind
        # -- turned out to depend on git's internal commit machinery, which
        # (confirmed empirically while adding the pathspec fix below) cleans
        # up that lock reliably for a *pathspec-scoped* commit but not for a
        # full-index one. Since publish() now always commits with a
        # pathspec, that trick stopped reproducing the scenario at all.
        # Simulating just the reset call's return code via a thin wrapper
        # around _run is the part that's actually under test here -- how the
        # code reacts to "reset also failed" -- without depending on git
        # internals or corrupting real repo state (which would also break
        # the verification diff below).
        from unittest.mock import patch
        lockfail_repo = tmp / "repo_lockfail"
        (lockfail_repo / "content").mkdir(parents=True)
        def git2(*args, cwd=lockfail_repo):
            return subprocess.run(["git", *args], cwd=str(cwd),
                                  capture_output=True, text=True)
        git2("init", "-q")
        git2("config", "user.email", "smoke@example.test")
        git2("config", "user.name", "Smoke")
        (lockfail_repo / "README.md").write_text("seed\n", encoding="utf-8")
        git2("add", "README.md")
        git2("commit", "-q", "-m", "seed")
        (lockfail_repo / "content" / "piece.md").write_text(
            "# piece\n", encoding="utf-8",
        )
        hooks = lockfail_repo / ".git" / "hooks"
        (hooks / "pre-commit").write_text(
            "#!/bin/sh\nexit 1\n", encoding="utf-8",
        )
        real_run = article_publish._run
        async def _run_reset_fails(cmd, cwd):
            if "reset" in cmd:
                return 1, "", "simulated: .git/index.lock exists (stale)"
            return await real_run(cmd, cwd)
        try:
            with patch.object(article_publish, "_run", _run_reset_fails):
                await article_publish.publish(
                    str(lockfail_repo), ["content/piece.md"],
                    message="should fail and fail to roll back", push=False,
                )
        except article_publish.PublishError as e:
            msg = str(e)
            if "could not be rolled back" not in msg or "content/piece.md" not in msg:
                fail(f"reset-failure message did not say so honestly: {msg!r}")
                return 1
        else:
            fail("publish succeeded despite a failing pre-commit hook")
            return 1
        # The simulated reset never actually ran, so real git state is
        # exactly what a genuinely-failed reset would leave: the hook's
        # commit failed, git add's staging is untouched. Verify that ground
        # truth with a real (unmocked) git diff.
        still_staged = git2("diff", "--cached", "--name-only").stdout
        if "content/piece.md" not in still_staged:
            fail("reset failed but the path is no longer staged in reality -- "
                 "the message and reality disagree")
            return 1
        print("ok: a rollback that itself fails says so honestly and leaves "
              "the paths visibly still staged")

        # ── commit must not sweep unrelated staged files into ours ──────
        # `git commit` with no pathspec commits the *entire* index. Proven
        # as a real bug against a throwaway repo: the user had something
        # staged elsewhere, unrelated to the draft, and it rode along into
        # our "content: publish ..." commit. Fixed by passing `-- <paths>`
        # to the commit itself (same scoping `add` already had). Pin both
        # halves: the commit must contain only the draft path, AND the
        # unrelated file must still be staged and uncommitted afterwards --
        # "we didn't touch it" matters as much as "we didn't commit it".
        scope_repo = tmp / "repo_scope"
        (scope_repo / "content").mkdir(parents=True)
        (scope_repo / "other").mkdir(parents=True)
        def git_scope(*args, cwd=scope_repo):
            return subprocess.run(["git", *args], cwd=str(cwd),
                                  capture_output=True, text=True)
        git_scope("init", "-q")
        git_scope("config", "user.email", "smoke@example.test")
        git_scope("config", "user.name", "Smoke")
        (scope_repo / "README.md").write_text("seed\n", encoding="utf-8")
        git_scope("add", "README.md")
        git_scope("commit", "-q", "-m", "seed")

        # The user's own, unrelated work-in-progress, staged before publish
        # ever runs.
        (scope_repo / "other" / "unrelated.txt").write_text(
            "the user's own work in progress\n", encoding="utf-8",
        )
        git_scope("add", "other/unrelated.txt")

        (scope_repo / "content" / "scoped-piece.md").write_text(
            "# Scoped piece\n", encoding="utf-8",
        )
        scope_sha = await article_publish.publish(
            str(scope_repo), ["content/scoped-piece.md"],
            message="publish: scoped piece (unverified)", push=False,
        )
        committed_files = git_scope(
            "show", "--name-only", "--pretty=format:", scope_sha,
        ).stdout.split()
        if committed_files != ["content/scoped-piece.md"]:
            fail("publish swept unrelated staged files into the commit: "
                 f"{committed_files}")
            return 1
        still_staged_scope = git_scope(
            "diff", "--cached", "--name-only",
        ).stdout.split()
        if still_staged_scope != ["other/unrelated.txt"]:
            fail("the user's unrelated staged file was disturbed by publish: "
                 f"still staged = {still_staged_scope}")
            return 1
        print("ok: publish commits only the draft path even when something "
              "else is staged elsewhere, and leaves that unrelated file "
              "staged and uncommitted")

        # ── the same scoping must hold on the rollback path ─────────────
        # A normal (non-lockfile) commit failure: the reset that follows
        # must unstage only our own path and must not touch the user's
        # other staged entry either. This is a different case from the
        # lockfail test above (where the reset *itself* also fails) -- here
        # the reset succeeds, and what's being checked is *what* it touched.
        rollback_scope_repo = tmp / "repo_rollback_scope"
        (rollback_scope_repo / "content").mkdir(parents=True)
        (rollback_scope_repo / "other").mkdir(parents=True)
        def git_rb(*args, cwd=rollback_scope_repo):
            return subprocess.run(["git", *args], cwd=str(cwd),
                                  capture_output=True, text=True)
        git_rb("init", "-q")
        git_rb("config", "user.email", "smoke@example.test")
        git_rb("config", "user.name", "Smoke")
        (rollback_scope_repo / "README.md").write_text("seed\n", encoding="utf-8")
        git_rb("add", "README.md")
        git_rb("commit", "-q", "-m", "seed")
        (rollback_scope_repo / "other" / "unrelated.txt").write_text(
            "the user's own work in progress\n", encoding="utf-8",
        )
        git_rb("add", "other/unrelated.txt")
        (rollback_scope_repo / "content" / "piece.md").write_text(
            "# piece\n", encoding="utf-8",
        )
        rb_hooks = rollback_scope_repo / ".git" / "hooks"
        (rb_hooks / "pre-commit").write_text(
            "#!/bin/sh\nexit 1\n", encoding="utf-8",
        )
        try:
            await article_publish.publish(
                str(rollback_scope_repo), ["content/piece.md"],
                message="should fail, roll back cleanly", push=False,
            )
        except article_publish.PublishError as e:
            msg = str(e)
            if "staged changes rolled back" not in msg:
                fail(f"expected the clean-rollback message, got: {msg!r}")
                return 1
        else:
            fail("publish succeeded despite a failing pre-commit hook")
            return 1
        after_rollback = git_rb("diff", "--cached", "--name-only").stdout.split()
        if after_rollback != ["other/unrelated.txt"]:
            fail("rollback did not scope correctly -- expected only the "
                 f"user's unrelated file still staged, got: {after_rollback}")
            return 1
        print("ok: a failed commit's rollback unstages only our own path, "
              "leaving the user's unrelated staged file untouched")

        # ── C2 pin: a second publish must not drag 'published' back ─────
        # The double-click regression from the final-fixes review: two
        # publish requests both read 'drafted' and pass can_publish; one
        # commits for real and advances the row to 'published', the other's
        # git call finds nothing left to stage (the file already matches
        # HEAD) and raises PublishError. The route's except-branch used to
        # write status='drafted' unconditionally -- dragging the just-
        # published row backwards forever. Reproduce both publish calls
        # against a fresh temp repo (not `repo` above, which by now carries
        # deliberately-dirtied state from the earlier "already staged" test
        # and would muddy what this specific pin is checking), then apply
        # the route's *fixed* handling of the second call's failure and
        # confirm it is a no-op.
        c2_repo = tmp / "repo_c2"
        (c2_repo / "content").mkdir(parents=True)
        def git_c2(*args, cwd=c2_repo):
            return subprocess.run(["git", *args], cwd=str(cwd),
                                  capture_output=True, text=True)
        git_c2("init", "-q")
        git_c2("config", "user.email", "smoke@example.test")
        git_c2("config", "user.name", "Smoke")
        (c2_repo / "README.md").write_text("seed\n", encoding="utf-8")
        git_c2("add", "README.md")
        git_c2("commit", "-q", "-m", "seed")
        c2_file = c2_repo / "content" / "c2-terminal.md"
        c2_file.write_text("# C2 terminal check\n", encoding="utf-8")
        c2_id = await db.add_article_proposal(
            pid, source="center", source_ref="c2-check",
            evidence="smoke: a second publish must not drag 'published' back",
            title="Smoke C2 terminal row", angle="…",
            slug_hint="smoke-c2-terminal",
        )
        await db.set_article_proposal_status(c2_id, "drafted")
        first_sha = await article_publish.publish(
            str(c2_repo), ["content/c2-terminal.md"],
            message="publish: c2 terminal check (unverified)", push=False,
        )
        if not await db.mark_article_published(c2_id, commit_ref=first_sha):
            fail("C2 setup: mark_article_published on a drafted smoke row failed")
            return 1
        try:
            await article_publish.publish(
                str(c2_repo), ["content/c2-terminal.md"],
                message="publish: c2 terminal check, second attempt", push=False,
            )
        except article_publish.PublishError as e:
            # Exactly the route's `except PublishError` handler: only write
            # 'drafted' back if the row is *still* 'drafted'.
            reverted = await db.set_article_proposal_status(
                c2_id, "drafted", error_message=str(e)[:2000],
                expect_statuses=("drafted",),
            )
            if reverted:
                fail("C2: a second, failed publish dragged the row back to "
                     "'drafted' -- the regression is not fixed")
                return 1
        else:
            fail("C2 setup: the second publish should have found nothing "
                 "staged and raised PublishError")
            return 1
        c2_row = await db.get_article_proposal(c2_id)
        if c2_row["status"] != "published" or c2_row["commit_ref"] != first_sha:
            fail("C2: row disturbed by the second publish attempt: "
                 f"status={c2_row['status']!r}, commit_ref={c2_row['commit_ref']!r}")
            return 1
        print("ok: C2 -- publishing twice in a row leaves the row 'published', "
              "not dragged back to 'drafted'")

        # ── scheduler wiring ──────────────────────────────────────
        from dreaming.services import scheduler as sched_mod
        kinds = [row[0] for row in sched_mod._PER_PROJECT_JOBS]
        if "weekly_article_ideas_scan" not in kinds:
            fail(f"weekly_article_ideas_scan not registered; kinds={kinds}")
            return 1
        row = next(r for r in sched_mod._PER_PROJECT_JOBS
                   if r[0] == "weekly_article_ideas_scan")
        if row[4] is not False:
            fail("the weekly article scan must default to disabled")
            return 1
        print("ok: weekly_article_ideas_scan registered, off by default")

        # ── venue resolution (pure) ────────────────────────────────
        class _P:
            def __init__(self, pid, slug): self.id, self.slug = pid, slug
        enabled = [_P(1, "subject"), _P(2, "venue"), _P(3, "other")]
        cases = [
            # (override, configured slug, expected)
            (2,    "other",   2),  # override wins over the setting
            (None, "venue",   2),  # setting used when no override
            (None, "",        1),  # neither -> the subject itself
            (None, "missing", 1),  # unknown slug -> subject, not an error
            (99,   "venue",   2),  # override naming no enabled project -> setting
            (99,   "",        1),  # ... and then the subject
        ]
        for override, configured, want in cases:
            got = articles.resolve_venue_id(1, override, configured, enabled)
            if got != want:
                fail(f"resolve_venue_id(1, {override}, {configured!r}) = {got}, want {want}")
                return 1
        print("ok: resolve_venue_id -- override > setting > subject, unknown falls back")

        # ── the venue's settings are the ones that count ───────────
        # A subject with no blog dir but a venue that has one must be
        # approvable; the reverse must not be.
        venue_enabled = [_P(pid, "subject"), _P(pid + 1000, "venue")]
        venue_id = articles.resolve_venue_id(pid, pid + 1000, "", venue_enabled)
        if venue_id != pid + 1000:
            fail(f"venue_id = {venue_id}, want {pid + 1000}")
            return 1
        print("ok: venue id resolves for a subject that is not the venue")

        # ── target_project_id round-trip ───────────────────────────
        vid = await db.add_article_proposal(
            pid, source="manual", source_ref="",
            evidence="controller smoke: venue column round-trip",
            title="Venue column", angle="", slug_hint="smoke-venue-column",
            target_project_id=pid,
        )
        row = await db.get_article_proposal(vid)
        if row["target_project_id"] != pid:
            fail(f"target_project_id not persisted: {row['target_project_id']}")
            return 1
        plain = await db.add_article_proposal(
            pid, source="manual", source_ref="",
            evidence="controller smoke: default venue is NULL",
            title="No venue", angle="", slug_hint="smoke-venue-null",
        )
        row = await db.get_article_proposal(plain)
        if row["target_project_id"] is not None:
            fail(f"default target_project_id = {row['target_project_id']!r}, want None")
            return 1
        if not await db.set_article_proposal_venue(plain, pid):
            fail("set_article_proposal_venue returned False on a proposed row")
            return 1
        if (await db.get_article_proposal(plain))["target_project_id"] != pid:
            fail("set_article_proposal_venue did not persist")
            return 1
        await db.set_article_proposal_status(plain, "published")
        if await db.set_article_proposal_venue(plain, None):
            fail("set_article_proposal_venue must refuse a non-proposed row")
            return 1
        print("ok: target_project_id defaults to NULL, round-trips, and is "
              "settable only while proposed")

        # ── pin_article_proposal_venue: the internal, status-guard-free pin ──
        # Distinct from set_article_proposal_venue above: a retry dispatches
        # from 'drafted' or 'failed', not just 'proposed', so this method
        # must not refuse a row already moved past 'proposed'. `plain` is
        # 'published' at this point -- the sharpest case available.
        if not await db.pin_article_proposal_venue(plain, pid + 1000):
            fail("pin_article_proposal_venue refused a non-'proposed' row -- "
                 "it must carry no status guard")
            return 1
        pinned_row = await db.get_article_proposal(plain)
        if pinned_row["target_project_id"] != pid + 1000:
            fail(f"pin_article_proposal_venue did not persist: "
                 f"{pinned_row['target_project_id']}")
            return 1
        print("ok: pin_article_proposal_venue records the resolved venue "
              "regardless of status, unlike the user-facing setter")

        # ── schema-order regression pin ──────────────────────────────
        # article_proposals has two columns (verify_label, target_project_id)
        # that were added after the table's first release via ALTER TABLE
        # ADD COLUMN in _migrate_orchestration, which can only append -- so a
        # database migrated from before either column existed ends up with
        # them at the end, in append order. The CREATE TABLE string has to
        # declare them in that same trailing order, or a fresh database and
        # a migrated one silently disagree about column order (harmless
        # today since every reader uses name-based access, but a footgun for
        # anything that ever reads positionally). Pin the full column list
        # against a throwaway fresh database so a future column added in the
        # wrong spot fails loudly here instead of staying invisible.
        order_tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_articles_order_"))
        order_db = SqliteDB(str(order_tmp / "order.db"))
        await order_db.connect()
        try:
            async with order_db._conn.execute(
                "PRAGMA table_info(article_proposals)"
            ) as cur:
                fresh_cols = [row[1] for row in await cur.fetchall()]
        finally:
            await order_db.close()
        want_cols = [
            "id", "project_id", "source", "source_ref", "evidence", "title",
            "angle", "slug_hint", "funnel_level", "locales", "tags_json",
            "related_product", "status", "writer_agent", "draft_ref",
            "verify_output", "verify_ok", "commit_ref", "session_id",
            "error_message", "created_at", "decided_at", "written_at",
            "published_at", "verify_label", "target_project_id",
        ]
        if fresh_cols != want_cols:
            fail(f"article_proposals column order: got {fresh_cols}, "
                 f"want {want_cols}")
            return 1
        print("ok: article_proposals column order matches a migrated "
              "database's (verify_label, target_project_id trail in "
              "append order)")

        print("PASS")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
