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

        print("PASS")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
