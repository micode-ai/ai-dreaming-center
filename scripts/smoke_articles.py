"""Smoke-тест article pipeline.

Покрывает: вставку предложения, дедуп по (project_id, slug_hint), переходы
статусов, фиксацию черновика с выводом верификации и публикацию.

Выход 0 — всё ок; ненулевой код + диагностика в stderr — что упало.
"""
from __future__ import annotations
import asyncio
import json
import logging
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Windows console here is cp1250: an unencodable char in print() aborts the
# run mid-way. Force UTF-8 on both streams (fail() writes to stderr).
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

from dreaming.services import starter_kit  # noqa: E402
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

        # ── evidence is a structural guard, not a per-caller habit ──
        # Promoted from the API boundary (articles_ingest's own 400) into
        # add_article_proposal itself so every present and future caller —
        # not just /articles/ingest — inherits the rule: a queue of
        # unfalsifiable suggestions is worse than an empty one.
        try:
            await db.add_article_proposal(
                pid, source="project_scan", source_ref="x",
                evidence="   ", title="No evidence", angle="…",
                slug_hint="smoke-blank-evidence",
            )
        except ValueError:
            print("ok: add_article_proposal refuses blank-after-strip evidence")
        else:
            fail("add_article_proposal accepted blank evidence")
            return 1

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

        # ── session-crash-visibility fix 1: process_manager._cleanup must
        # prefer the stream-json result's terminal status over the exit
        # code -- a claude CLI process that hits error_during_execution
        # mid-write still exits 0, and used to be recorded as 'success'. ──
        from dreaming.services.process_manager import ProcessManager, RunningSession
        import types as _types

        pm = ProcessManager(
            settings=_types.SimpleNamespace(), db=db, projects=ProjectsService(db),
        )

        # (a) a result event reporting an error, with exit code 0 (the
        # exact shape from the real incident: "[done] status=
        # error_during_execution ..." followed by "[exit] code=0") must be
        # recorded 'failed', with the subtype surfacing in error_message.
        sid_crash = await db.create_session(pid, "smoke-crash-agent", "sonnet")
        session_crash = RunningSession(
            session_id=sid_crash, agent_name="smoke-crash-agent",
            project_id=pid, project_slug="demo", process=None,
        )
        pm._parse_stream_json(session_crash, json.dumps({
            "type": "result", "subtype": "error_during_execution",
            "duration_ms": 370909, "total_cost_usd": 2.8876,
        }))
        if session_crash.terminal_status != "error_during_execution":
            fail("_parse_stream_json did not store the result subtype on "
                 f"the session: {session_crash.terminal_status!r}")
            return 1
        await pm._cleanup(session_crash, exit_code=0, error_message=None)
        row = await db.fetch_one(
            "SELECT status, error_message FROM agent_learning_sessions WHERE id=?",
            (sid_crash,),
        )
        if row["status"] != "failed":
            fail(f"crashed-but-exit-0 session recorded status={row['status']!r}, "
                 "want 'failed'")
            return 1
        if "error_during_execution" not in (row["error_message"] or ""):
            fail("crashed session's error_message doesn't name the subtype: "
                 f"{row['error_message']!r}")
            return 1
        print("ok: fix 1 -- exit code 0 with an error result subtype is "
              "recorded 'failed', with the subtype in error_message")

        # (b) no result event at all (stream never produced one -- killed,
        # crashed before finishing, watchdog) must still fall back to the
        # exit code exactly as before this fix.
        sid_noresult = await db.create_session(pid, "smoke-noresult-agent", "sonnet")
        session_noresult = RunningSession(
            session_id=sid_noresult, agent_name="smoke-noresult-agent",
            project_id=pid, project_slug="demo", process=None,
        )
        await pm._cleanup(session_noresult, exit_code=0, error_message=None)
        row = await db.fetch_one(
            "SELECT status FROM agent_learning_sessions WHERE id=?",
            (sid_noresult,),
        )
        if row["status"] != "success":
            fail("no-result-event session with exit code 0 recorded "
                 f"status={row['status']!r}, want 'success' (exit-code fallback)")
            return 1

        sid_noresult_fail = await db.create_session(pid, "smoke-noresult-fail-agent", "sonnet")
        session_noresult_fail = RunningSession(
            session_id=sid_noresult_fail, agent_name="smoke-noresult-fail-agent",
            project_id=pid, project_slug="demo", process=None,
        )
        await pm._cleanup(
            session_noresult_fail, exit_code=1,
            error_message="claude exited code=1: some line",
        )
        row = await db.fetch_one(
            "SELECT status, error_message FROM agent_learning_sessions WHERE id=?",
            (sid_noresult_fail,),
        )
        if row["status"] != "failed" or row["error_message"] != "claude exited code=1: some line":
            fail("no-result-event session with exit code 1: "
                 f"status={row['status']!r}, error_message={row['error_message']!r}")
            return 1
        print("ok: fix 1 -- no result event still follows the exit code "
              "(0 -> success, non-zero -> failed) unchanged")

        # (c) a stored terminal status of 'success' must NOT overrule a
        # non-zero exit code. This is the interactive multi-turn case: an
        # earlier turn reports subtype=success, then the process is killed
        # (watchdog silence timeout / hard cap) and exits non-zero. The
        # downgrade is one-way only -- a remembered success can never turn
        # a dirty exit back into 'success'.
        sid_stale_success = await db.create_session(pid, "smoke-stale-success-agent", "sonnet")
        session_stale_success = RunningSession(
            session_id=sid_stale_success, agent_name="smoke-stale-success-agent",
            project_id=pid, project_slug="demo", process=None,
        )
        pm._parse_stream_json(session_stale_success, json.dumps({
            "type": "result", "subtype": "success",
            "duration_ms": 1000, "total_cost_usd": 0.01,
        }))
        await pm._cleanup(session_stale_success, exit_code=1, error_message=None)
        row = await db.fetch_one(
            "SELECT status FROM agent_learning_sessions WHERE id=?",
            (sid_stale_success,),
        )
        if row["status"] != "failed":
            fail("a stored terminal status of 'success' overruled a "
                 f"non-zero exit code: recorded status={row['status']!r}, "
                 "want 'failed'")
            return 1
        print("ok: fix 1 -- a stored 'success' status never overrules a "
              "non-zero exit code (one-way downgrade only)")

        # (d) [review fix 3] a `result` event that omits `subtype` and only
        # carries `stop_reason` (the display-path fallback) must NOT be
        # stored as the session's terminal status -- storing that fallback
        # let a clean `stop_reason: "end_turn"` read as a non-"success"
        # terminal status and fail every ordinary session. The [done]
        # display line's own text is unaffected -- it still shows the
        # stop_reason fallback for display only.
        sid_stopreason = await db.create_session(pid, "smoke-stopreason-agent", "sonnet")
        session_stopreason = RunningSession(
            session_id=sid_stopreason, agent_name="smoke-stopreason-agent",
            project_id=pid, project_slug="demo", process=None,
        )
        display_lines = pm._parse_stream_json(session_stopreason, json.dumps({
            "type": "result", "stop_reason": "end_turn",
            "duration_ms": 500, "total_cost_usd": 0.01,
        }))
        if session_stopreason.terminal_status is not None:
            fail("a result event without a subtype was stored as the "
                 f"session's terminal status: {session_stopreason.terminal_status!r}")
            return 1
        if not any("status=end_turn" in line for line in display_lines):
            fail("the [done] display line lost its stop_reason fallback text: "
                 f"{display_lines!r}")
            return 1
        await pm._cleanup(session_stopreason, exit_code=0, error_message=None)
        row = await db.fetch_one(
            "SELECT status FROM agent_learning_sessions WHERE id=?",
            (sid_stopreason,),
        )
        if row["status"] != "success":
            fail("a clean exit with a subtype-less result event (stop_reason "
                 f"fallback only) was recorded status={row['status']!r}, want "
                 "'success'")
            return 1
        print("ok: fix 3 -- a result event's stop_reason fallback is display-"
              "only and never corrupts the stored terminal status")

        # ── session-crash-visibility fix 2: reconcile_stranded_article_
        # proposals fails a 'writing' row whose dispatched session has
        # finished without a write-back. ────────────────────────────────
        # `reconcile_stranded_article_proposals` scans ALL 'writing' rows
        # globally (no project filter) and now decides liveness purely from
        # `active_session_ids` (round 2 -- see below), so every call in this
        # script must pass the full accumulated set of session ids meant to
        # still read as "alive" at that point, or an earlier block's
        # deliberately-still-running row would be collaterally failed by a
        # later call that forgot to re-assert it. This mirrors production:
        # the scheduler always passes the *whole* current live set, not one
        # scoped to a single proposal.
        still_alive_session_ids: set[str] = set()

        sid_running = await db.create_session(pid, "smoke-writer-running", "sonnet")
        still_alive_session_ids.add(sid_running)
        stranded_running = await db.add_article_proposal(
            pid, source="smoke", source_ref="stranded-running",
            evidence="test", title="Stranded but session still running",
            angle="…", slug_hint="stranded-running",
        )
        await db.start_article_attempt(stranded_running, session_id=sid_running)

        sid_done = await db.create_session(pid, "smoke-writer-done", "sonnet")
        await db.execute(
            "UPDATE agent_learning_sessions SET status='failed', finished_at=? "
            "WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), sid_done),
        )
        stranded_done = await db.add_article_proposal(
            pid, source="smoke", source_ref="stranded-done",
            evidence="test", title="Stranded, session finished",
            angle="…", slug_hint="stranded-done",
        )
        await db.start_article_attempt(stranded_done, session_id=sid_done)

        stranded_empty = await db.add_article_proposal(
            pid, source="smoke", source_ref="stranded-empty",
            evidence="test", title="Stranded, no session_id at all",
            angle="…", slug_hint="stranded-empty",
        )
        await db.set_article_proposal_status(stranded_empty, "writing")

        n_failed = await db.reconcile_stranded_article_proposals(
            active_session_ids=still_alive_session_ids,
        )
        if n_failed != 1:
            fail(f"reconcile_stranded_article_proposals: failed {n_failed} rows, want 1")
            return 1

        row = await db.get_article_proposal(stranded_running)
        if row["status"] != "writing":
            fail("reconcile touched a proposal whose session is still "
                 f"'running': status={row['status']!r}")
            return 1

        row = await db.get_article_proposal(stranded_done)
        if row["status"] != "failed":
            fail("reconcile left a stranded proposal (finished session) "
                 f"as {row['status']!r}, want 'failed'")
            return 1
        if sid_done not in row["error_message"] or "failed" not in row["error_message"]:
            fail("reconcile's error_message doesn't name the session/status: "
                 f"{row['error_message']!r}")
            return 1

        row = await db.get_article_proposal(stranded_empty)
        if row["status"] != "writing":
            fail("reconcile touched a proposal with an empty session_id: "
                 f"status={row['status']!r}")
            return 1
        print("ok: fix 2 -- reconcile_stranded_article_proposals fails a "
              "'writing' row whose session has finished, leaves a still-"
              "running session and an empty session_id untouched")

        # ── review fix 1: reconcile_stranded_article_proposals must not
        # fail a 'writing' proposal while its writer's process is still
        # running in ProcessManager, even though its session row already
        # reads something else -- the DB status column is not consulted for
        # liveness at all (round 2 hardened this further -- see the LEFT
        # JOIN / no-active-set block below). ──────────────────────────────
        sid_live_but_cancelled = await db.create_session(
            pid, "cmd:demo:write-article", "sonnet",
        )
        still_alive_session_ids.add(sid_live_but_cancelled)
        await db.execute(
            "UPDATE agent_learning_sessions SET status='cancelled', finished_at=? "
            "WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), sid_live_but_cancelled),
        )
        stranded_live = await db.add_article_proposal(
            pid, source="smoke", source_ref="stranded-live",
            evidence="test", title="Session row says cancelled but is still running",
            angle="…", slug_hint="stranded-live",
        )
        await db.start_article_attempt(stranded_live, session_id=sid_live_but_cancelled)

        n_failed2 = await db.reconcile_stranded_article_proposals(
            active_session_ids=still_alive_session_ids,
        )
        if n_failed2 != 0:
            fail("reconcile failed a proposal whose session_id is in the "
                 f"active set: {n_failed2} row(s) failed, want 0")
            return 1
        row = await db.get_article_proposal(stranded_live)
        if row["status"] != "writing":
            fail("reconcile touched a 'writing' proposal whose session is "
                 f"still in the active process set: status={row['status']!r}")
            return 1
        print("ok: fix 1 -- a 'writing' proposal whose session is still in "
              "the active process set is left alone even though its "
              "session row reads 'cancelled'")

        # ── review fix 1 (db half): reconcile_stale_sessions must never
        # touch a cmd: row -- it isn't describable by the (project_id,
        # agent_name) active_pairs contract, and _cleanup owns its
        # lifecycle directly. This is the corruption that makes the above
        # scenario routine on master: any unrelated session exiting sweeps
        # every live cmd: row older than 2 minutes to 'cancelled'. ───────
        sid_cmd_row = await db.create_session(pid, "cmd:demo:roman-x", "sonnet")
        old_iso = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        await db.execute(
            "UPDATE agent_learning_sessions SET started_at=? WHERE id=?",
            (old_iso, sid_cmd_row),
        )
        await db.reconcile_stale_sessions(active_pairs=[])
        row = await db.fetch_one(
            "SELECT status FROM agent_learning_sessions WHERE id=?",
            (sid_cmd_row,),
        )
        if row["status"] != "running":
            fail("reconcile_stale_sessions touched a cmd: row: "
                 f"status={row['status']!r}, want unchanged 'running'")
            return 1
        print("ok: fix 1 -- reconcile_stale_sessions never touches a cmd: "
              "row (its agent_name IS the composite key, not a "
              "(project_id, agent_name) pair)")

        # ── review fix 2: a proposal whose session_id has no matching
        # agent_learning_sessions row at all (create_session failed and
        # start_command fell back to a generated uuid, or the row was
        # deleted) must be logged, not silently skipped -- and not
        # auto-failed either, since there's no reliable way to tell how
        # long the row has looked like this. ─────────────────────────────
        stranded_no_row = await db.add_article_proposal(
            pid, source="smoke", source_ref="stranded-no-row",
            evidence="test", title="session_id with no session row at all",
            angle="…", slug_hint="stranded-no-row",
        )
        await db.start_article_attempt(
            stranded_no_row, session_id="ghost-session-id-not-in-db",
        )

        class _CaptureHandler(logging.Handler):
            def __init__(self):
                super().__init__()
                self.messages: list[str] = []

            def emit(self, record):
                self.messages.append(record.getMessage())

        cap = _CaptureHandler()
        db_logger = logging.getLogger("dreaming.services.db")
        db_logger.addHandler(cap)
        try:
            await db.reconcile_stranded_article_proposals(
                active_session_ids=still_alive_session_ids,
            )
        finally:
            db_logger.removeHandler(cap)
        row = await db.get_article_proposal(stranded_no_row)
        if row["status"] != "writing":
            fail("reconcile auto-failed a proposal with no matching session "
                 f"row at all: status={row['status']!r}, want it left as "
                 "'writing' and merely logged")
            return 1
        if not any(str(stranded_no_row) in m for m in cap.messages):
            fail("reconcile did not log a warning naming the id of the "
                 f"proposal with no session row: {cap.messages!r}")
            return 1
        print("ok: fix 2 -- a 'writing' proposal whose session_id has no "
              "matching session row at all is logged (with its id) and "
              "left alone, not silently skipped and not auto-failed")

        # ── round-2 review finding: after an ungraceful app death a cmd:
        # session row can be stuck at status='running' forever -- nothing
        # ever revisits it (reconcile_stale_sessions now correctly excludes
        # cmd: rows, and there's no startup sweep). The status column must
        # never be trusted for liveness: a session id absent from the live
        # active set is failed regardless of a 'running' row. (The mirror
        # assertion -- a session id PRESENT in the active set is left alone
        # even though its row says 'cancelled' -- already exists above as
        # "fix 1 -- a 'writing' proposal whose session is still in the
        # active process set..."; not duplicated here.) ──────────────────
        sid_stale_running = await db.create_session(
            pid, "cmd:demo:write-article-2", "sonnet",
        )
        # Deliberately NOT added to still_alive_session_ids and left at its
        # default status='running' -- this is the stale-row-after-a-hard-
        # kill shape: the row still says 'running' but no process backs it.
        stranded_stale_running = await db.add_article_proposal(
            pid, source="smoke", source_ref="stranded-stale-running",
            evidence="test", title="Session row says running but the process is long gone",
            angle="…", slug_hint="stranded-stale-running",
        )
        await db.start_article_attempt(
            stranded_stale_running, session_id=sid_stale_running,
        )

        n_failed4 = await db.reconcile_stranded_article_proposals(
            active_session_ids=still_alive_session_ids,
        )
        if n_failed4 != 1:
            fail(f"reconcile_stranded_article_proposals: failed {n_failed4} "
                 "row(s) for the stale-'running'-row scenario, want 1")
            return 1
        row = await db.get_article_proposal(stranded_stale_running)
        if row["status"] != "failed":
            fail("a proposal whose session row still says 'running' but "
                 f"whose id is absent from active_session_ids was left as "
                 f"{row['status']!r}, want 'failed' -- the status column "
                 "must never be trusted for liveness")
            return 1
        if sid_stale_running not in row["error_message"]:
            fail("reconcile's error_message for the stale-'running' row "
                 f"doesn't name the session id: {row['error_message']!r}")
            return 1
        print("ok: fix 1 (round 2) -- a proposal whose session row still "
              "says 'running' is failed once its session id is absent from "
              "the live active set; the status column alone is never "
              "enough to call it alive")

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

                # ── all-Cyrillic topics: the slug fallback must be
                # deterministic on the topic's own text, not the clock ────
                # slugify drops non-ASCII rather than transliterating, so an
                # all-Cyrillic topic (this user's default case, not an edge
                # case) always hits the fallback. A clock-based fallback gets
                # dedup backwards both ways: two different topics posted in
                # the same UTC second would falsely collide, and the same
                # topic posted twice, seconds apart -- the normal human case
                # -- would NOT collide. Pin both directions for real.
                import json as _json
                from urllib.parse import unquote
                import time as _time
                cyr_a = "Смок кириллица один"
                cyr_b = "Смок кириллица два"

                first_cyr = client.post("/p/ai-dreaming-center/articles/add",
                                        data={"title": cyr_a, "angle": ""},
                                        follow_redirects=False)
                if first_cyr.status_code != 303:
                    fail(f"manual add (cyrillic topic A): {first_cyr.status_code}, want 303")
                    return 1
                cyr_a_row = None
                for r in await real_db.list_article_proposals(status="proposed"):
                    if r["title"] == cyr_a:
                        cyr_a_row = r
                        break
                if cyr_a_row is None:
                    fail("cyrillic manual proposal (topic A) was not created")
                    return 1
                slug_a = cyr_a_row["slug_hint"]
                suffix_a = slug_a[len("manual-"):]
                if (not slug_a.startswith("manual-") or len(suffix_a) != 10
                        or any(c not in "0123456789abcdef" for c in suffix_a)):
                    fail(f"cyrillic fallback slug_hint malformed: {slug_a!r}")
                    return 1

                # A real gap (>1s) between two submissions of the SAME topic
                # is exactly the case a clock-based fallback got wrong --
                # forcing a real sleep here makes this a genuine regression
                # pin, not an accident of two fast calls landing in the same
                # UTC second.
                _time.sleep(1.1)
                second_cyr = client.post("/p/ai-dreaming-center/articles/add",
                                         data={"title": cyr_a, "angle": ""},
                                         follow_redirects=False)
                if second_cyr.status_code != 303:
                    fail(f"manual add (cyrillic topic A, repeat): {second_cyr.status_code}, want 303")
                    return 1
                dup_flash = _json.loads(unquote(second_cyr.cookies.get("flash", "")))
                if dup_flash.get("level") != "info":
                    fail("repeating the same cyrillic topic a second apart was "
                         f"not reported as a duplicate: {dup_flash}")
                    return 1
                same_slug_rows = [
                    r for r in await real_db.list_article_proposals(status="proposed")
                    if r["slug_hint"] == slug_a
                ]
                if len(same_slug_rows) != 1:
                    fail(f"same cyrillic topic, >1s apart, produced "
                         f"{len(same_slug_rows)} rows instead of deduping to 1 "
                         "-- the fallback slug is still clock-derived")
                    return 1
                print("ok: same all-Cyrillic topic, seconds apart, dedupes to "
                      "one row (fallback slug derives from the topic, not the clock)")

                different_cyr = client.post("/p/ai-dreaming-center/articles/add",
                                            data={"title": cyr_b, "angle": ""},
                                            follow_redirects=False)
                if different_cyr.status_code != 303:
                    fail(f"manual add (cyrillic topic B): {different_cyr.status_code}, want 303")
                    return 1
                cyr_b_row = None
                for r in await real_db.list_article_proposals(status="proposed"):
                    if r["title"] == cyr_b:
                        cyr_b_row = r
                        break
                if cyr_b_row is None:
                    fail("cyrillic manual proposal (topic B) was not created")
                    return 1
                if cyr_b_row["slug_hint"] == slug_a:
                    fail("two DIFFERENT cyrillic topics collided on the same "
                         f"fallback slug_hint: {slug_a!r}")
                    return 1
                print("ok: two different all-Cyrillic topics get different fallback slug_hints")

                await real_db.execute("DELETE FROM article_proposals WHERE id=?", (cyr_a_row["id"],))
                await real_db.execute("DELETE FROM article_proposals WHERE id=?", (cyr_b_row["id"],))

                ai_dc_project = await ProjectsService(real_db).get_by_slug(
                    "ai-dreaming-center",
                )

                # ── venue route: settable while proposed, refused afterwards ──
                # Task 1's set_article_proposal_venue already proves the DB
                # setter's own status guard (see the round-trip check further
                # below); this proves the route wraps it correctly: 404 for a
                # missing row, 303 while 'proposed' (both setting and clearing
                # the override), and 409 once the row has moved past
                # 'proposed' -- the venue is no longer the user's to change.
                vroute_id = await real_db.add_article_proposal(
                    ai_dc_project.id, source="manual", source_ref="",
                    evidence="smoke: venue route", title="Smoke venue route",
                    angle="…", slug_hint="smoke-venue-route",
                )
                try:
                    missing = client.post(
                        "/p/ai-dreaming-center/articles/999999999/venue",
                        data={"venue": ""}, follow_redirects=False,
                    )
                    if missing.status_code != 404:
                        fail(f"venue route on a missing row: "
                             f"{missing.status_code}, want 404")
                        return 1

                    set_resp = client.post(
                        f"/p/ai-dreaming-center/articles/{vroute_id}/venue",
                        data={"venue": ai_dc_project.slug},
                        follow_redirects=False,
                    )
                    if set_resp.status_code != 303:
                        fail(f"venue route on a proposed row: "
                             f"{set_resp.status_code}, want 303")
                        return 1
                    vrow = await real_db.get_article_proposal(vroute_id)
                    if vrow["target_project_id"] != ai_dc_project.id:
                        fail("venue route did not persist the override: "
                             f"{vrow['target_project_id']!r}")
                        return 1

                    clear_resp = client.post(
                        f"/p/ai-dreaming-center/articles/{vroute_id}/venue",
                        data={"venue": ""}, follow_redirects=False,
                    )
                    if clear_resp.status_code != 303:
                        fail(f"venue route clearing the override: "
                             f"{clear_resp.status_code}, want 303")
                        return 1
                    vrow = await real_db.get_article_proposal(vroute_id)
                    if vrow["target_project_id"] is not None:
                        fail("venue route did not clear a previously set "
                             f"override: {vrow['target_project_id']!r}")
                        return 1

                    await real_db.set_article_proposal_status(vroute_id, "writing")
                    dispatched_resp = client.post(
                        f"/p/ai-dreaming-center/articles/{vroute_id}/venue",
                        data={"venue": ai_dc_project.slug},
                        follow_redirects=False,
                    )
                    if dispatched_resp.status_code != 409:
                        fail(f"venue route on a 'writing' row: "
                             f"{dispatched_resp.status_code}, want 409")
                        return 1
                    vrow = await real_db.get_article_proposal(vroute_id)
                    if vrow["target_project_id"] is not None:
                        fail("venue route's refused 409 still changed the "
                             f"row: {vrow['target_project_id']!r}")
                        return 1
                finally:
                    await real_db.execute(
                        "DELETE FROM article_proposals WHERE id=?", (vroute_id,),
                    )
                print("ok: venue route -- 404 missing row, 303 set/clear "
                      "while proposed, 409 once dispatched")

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
                null_venue_row_id = await app.state.db.add_article_proposal(
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
                explicit_venue_row_id = await app.state.db.add_article_proposal(
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

                # ── review fix round 1: the <select> preselection must use ──
                # the RAW override, not the resolved venue_slug. The
                # resolved slug always equals some real project (override ->
                # article_venue_project -> the subject itself), so comparing
                # against it made the "no override" default option
                # unreachable -- an operator confirming the form untouched
                # would silently pin a previously-unpinned row. Isolate each
                # card's own <form ...venue> block by proposal id (both rows
                # are 'proposed' and share one page) and inspect its
                # <option> tags directly rather than the raw HTML text,
                # since exact inter-attribute whitespace is a template
                # rendering detail, not the thing under test.
                import re as _re

                def _venue_form(html: str, row_id) -> str:
                    m = _re.search(
                        r'<form method="post" action="/p/smoke-null-venue'
                        r'/articles/%s/venue".*?</form>' % row_id,
                        html, _re.DOTALL,
                    )
                    if m is None:
                        fail(f"no venue <form> found for proposal {row_id}")
                        raise LookupError
                    return m.group(0)

                def _option(html: str, value: str) -> str:
                    m = _re.search(
                        r'<option value="%s"[^>]*>' % _re.escape(value), html,
                    )
                    if m is None:
                        fail(f"no <option value={value!r}> found: {html[:500]}")
                        raise LookupError
                    return m.group(0)

                try:
                    no_override_form = _venue_form(resp2.text, null_venue_row_id)
                    if "selected" not in _option(no_override_form, ""):
                        fail("no-override row: the default option is not "
                             f"selected: {no_override_form}")
                        return 1
                    if "selected" in _option(no_override_form, other_venue_project.slug):
                        fail("no-override row: a project option is "
                             f"selected when it should not be: {no_override_form}")
                        return 1

                    override_form = _venue_form(resp2.text, explicit_venue_row_id)
                    if "selected" in _option(override_form, ""):
                        fail("overridden row: the default option is "
                             f"selected when an override exists: {override_form}")
                        return 1
                    if "selected" not in _option(override_form, other_venue_project.slug):
                        fail("overridden row: its own venue's option is not "
                             f"selected: {override_form}")
                        return 1
                except LookupError:
                    return 1
                print("ok: the venue <select> preselects the default option "
                      "for an unpinned row and the actual override's option "
                      "for a pinned one")
        finally:
            if prior_db_path_env is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior_db_path_env
        print("ok: NULL target_project_id with no article_venue_project shows "
              "the subject's own writer and no venue badge")
        print("ok: an explicit target_project_id override renders the venue "
              "badge, naming that project's slug")

        # ── regression pin: the starter-kit check must target the derived ──
        # article root, not the venue's own working_dir, when the blog lives
        # in a nested repository (the mi-code-ai / micode-landing-page
        # shape). Before this fix, articles_approve checked
        # starter_kit.command_installed(venue.working_dir, "write-article")
        # -- which can be True even though the nested repo the session
        # actually runs in has no write-article.md at all (Claude CLI
        # resolves project-level slash commands from its own cwd, not from a
        # parent), burning a real paid CLI session for nothing. Own throwaway
        # fixture + isolated DB — never the live database.
        os.environ["DC_DB_PATH"] = str(page_db_dir / "test.db")
        try:
            with TestClient(app) as sk_client:
                sk_venue_dir = tmp / "sk_venue_project"
                _git_init(sk_venue_dir)
                sk_nested_repo = sk_venue_dir / "micode-landing-page"
                _git_init(sk_nested_repo)
                (sk_nested_repo / "blog").mkdir(parents=True)

                sk_project = await ProjectsService(app.state.db).create(
                    slug="smoke-starter-kit-nested", label="Smoke SK Nested",
                    working_dir=str(sk_venue_dir),
                )
                await ProjectsService(app.state.db).set_setting(
                    sk_project.id, "article_blog_dir",
                    "micode-landing-page/blog",
                )

                # Case A: write-article.md exists only in the venue's own
                # .claude/commands/, NOT in the nested repo that actually
                # owns the blog. The buggy check (against venue.working_dir)
                # would have passed here and let a paid session dispatch
                # into a cwd with no write-article command at all. The fixed
                # check must refuse -- with 400, before any dispatch, and
                # without mutating the row.
                (sk_venue_dir / ".claude" / "commands").mkdir(parents=True)
                (sk_venue_dir / ".claude" / "commands" / "write-article.md").write_text(
                    "installed only in the parent, not the nested repo\n",
                    encoding="utf-8",
                )
                sk_row_a = await app.state.db.add_article_proposal(
                    sk_project.id, source="manual", source_ref="",
                    evidence="smoke: starter-kit check must target the "
                    "nested article root, not the venue's own working_dir",
                    title="SK nested check A", angle="…",
                    slug_hint="smoke-sk-nested-a",
                )
                resp_a = sk_client.post(
                    f"/p/smoke-starter-kit-nested/articles/{sk_row_a}/approve",
                    follow_redirects=False,
                )
                if resp_a.status_code != 400:
                    fail(
                        "starter-kit check (nested repo, command only in "
                        f"parent): got {resp_a.status_code}, want 400 -- the "
                        "check must look in the nested repo and find "
                        "nothing there, not pass against the parent"
                    )
                    return 1
                if "write-article" not in resp_a.json().get("detail", ""):
                    fail("400 for a missing write-article command must name "
                         f"it: {resp_a.text[:200]}")
                    return 1
                row_a_after = await app.state.db.get_article_proposal(sk_row_a)
                if row_a_after["status"] != "proposed":
                    fail("starter-kit refusal (nested, case A) must not "
                         f"mutate the row: status={row_a_after['status']!r}")
                    return 1
                print("ok: starter-kit check (nested repo) refuses before "
                      "dispatch when write-article is installed only in the "
                      "venue's own working_dir, not the nested blog repo")

                # Case B: the positive mirror. write-article.md now exists
                # only in the nested repo. process_manager.start_command is
                # faked so no real CLI session is ever spawned -- the fixed
                # check must pass, and the session must be started with
                # working_dir set to the NESTED repo's root, not the venue's.
                (sk_venue_dir / ".claude" / "commands" / "write-article.md").unlink()
                (sk_nested_repo / ".claude" / "commands").mkdir(parents=True)
                (sk_nested_repo / ".claude" / "commands" / "write-article.md").write_text(
                    "installed in the nested repo\n", encoding="utf-8",
                )
                from unittest.mock import AsyncMock
                real_start_command = app.state.process_manager.start_command
                fake_start_command = AsyncMock(
                    return_value="smoke-sk-nested-fake-session",
                )
                app.state.process_manager.start_command = fake_start_command
                try:
                    sk_row_b = await app.state.db.add_article_proposal(
                        sk_project.id, source="manual", source_ref="",
                        evidence="smoke: starter-kit check must pass once "
                        "write-article.md exists in the nested article root",
                        title="SK nested check B", angle="…",
                        slug_hint="smoke-sk-nested-b",
                    )
                    resp_b = sk_client.post(
                        f"/p/smoke-starter-kit-nested/articles/{sk_row_b}/approve",
                        follow_redirects=False,
                    )
                    if resp_b.status_code != 303:
                        fail(
                            "starter-kit check (nested repo, command "
                            f"installed there): got {resp_b.status_code}, "
                            f"want 303 -- {resp_b.text[:300]}"
                        )
                        return 1
                    if fake_start_command.await_args is None:
                        fail("approve (case B) never reached "
                             "process_manager.start_command")
                        return 1
                    call_kwargs = fake_start_command.await_args.kwargs
                    expected_root = str(sk_nested_repo.resolve())
                    got_working_dir = str(
                        Path(call_kwargs["working_dir"]).resolve()
                    )
                    if got_working_dir != expected_root:
                        fail(
                            "approve dispatched with working_dir="
                            f"{got_working_dir!r}, want the nested repo "
                            f"root {expected_root!r} -- the session would "
                            "run with the wrong cwd"
                        )
                        return 1
                finally:
                    app.state.process_manager.start_command = real_start_command
                print("ok: starter-kit check (nested repo) passes and "
                      "dispatches with the nested repo as cwd once "
                      "write-article is installed there")
        finally:
            if prior_db_path_env is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior_db_path_env

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

        # ── the question channel must be documented ─────────────────
        # Task 6: the writer needs to know how to ask, poll, and what to do
        # on dismissed/unanswered. These three needles are the minimum
        # proof the section exists and names the right endpoints/fields --
        # the fuller wording is checked by hand, not by grep.
        for needle in ("/api/questions/create", "poll", "tool_use_id"):
            if needle not in body2:
                fail(f"write-article.md does not document {needle!r} "
                     "(the question channel)")
                return 1
        print("ok: write-article.md documents the question channel")

        # ── the articles page must surface a pending question, scoped to
        # the proposal that asked it ────────────────────────────────
        # Review fix round 1, finding 2: orchestrator_questions is shared
        # by every kind of session on a project (self-study, rotation,
        # ...), and two proposals can be 'writing' at once. A project-wide
        # "anything pending?" boolean would light up every 'writing' card
        # whenever ANY question is pending -- including one that has
        # nothing to do with either row. The fix scopes by run_id
        # (write-article.md now passes the proposal id as run_id), so this
        # has to prove three things a single row/single question fixture
        # cannot: an unrelated run_id lights up nothing, the row that
        # actually asked shows the line and only that row, and answering
        # clears it. Isolated DB (DC_DB_PATH override), same pattern as the
        # nested-repo / NULL-venue page checks above -- this never touches
        # the user's live data/dreaming.db, so there is nothing here to
        # clean up on that database; every row created below lives only in
        # this throwaway sqlite file.
        os.environ["DC_DB_PATH"] = str(page_db_dir / "test.db")
        try:
            with TestClient(app) as q_client:
                q_project = await ProjectsService(app.state.db).create(
                    slug="smoke-waiting-question", label="Smoke Waiting Question",
                    working_dir=str(tmp),
                )
                waiting_text = app.state.i18n.t("article.waiting_answer", locale="ru")

                # Two 'writing' rows on the same project -- row A will ask,
                # row B never does. Both must exist before any question is
                # created, or a project-wide implementation would pass this
                # check by accident (only one 'writing' row to light up).
                row_a = await app.state.db.add_article_proposal(
                    q_project.id, source="manual", source_ref="",
                    evidence="smoke: the row that actually asks a question",
                    title="Smoke waiting-on-question row A", angle="…",
                    slug_hint="smoke-waiting-question-row-a",
                )
                row_b = await app.state.db.add_article_proposal(
                    q_project.id, source="manual", source_ref="",
                    evidence="smoke: a second writing row that never asks",
                    title="Smoke waiting-on-question row B", angle="…",
                    slug_hint="smoke-waiting-question-row-b",
                )
                for rid in (row_a, row_b):
                    await app.state.db.set_article_proposal_status(rid, "approved")
                    await app.state.db.set_article_proposal_status(rid, "writing")

                # An unrelated pending question on the same project -- no
                # run_id, exactly how a self-study or rotation session asks
                # today. Neither row asked this; neither card may show it.
                await app.state.db.create_question(
                    project_id=q_project.id, run_id=None, node_id=None,
                    tool_use_id="smoke-waiting-question-unrelated-q1",
                    questions_json='{"question": "unrelated self-study question", "options": []}',
                )
                resp0 = q_client.get(f"/p/{q_project.slug}/articles")
                if resp0.status_code != 200:
                    fail(f"/p/{q_project.slug}/articles with only an "
                         f"unrelated pending question: {resp0.status_code}")
                    return 1
                if waiting_text in resp0.text:
                    fail("a pending question with no matching run_id lit "
                         "up a card that never asked it")
                    return 1

                # Now row A asks, scoped by run_id=row_a (mirrors
                # write-article.md's instruction to pass the proposal id).
                question_id = await app.state.db.create_question(
                    project_id=q_project.id, run_id=str(row_a), node_id=None,
                    tool_use_id="smoke-waiting-question-q1",
                    questions_json='{"question": "real number for this claim?", "options": []}',
                )
                resp1 = q_client.get(f"/p/{q_project.slug}/articles")
                if resp1.status_code != 200:
                    fail(f"/p/{q_project.slug}/articles with row A's "
                         f"pending question: {resp1.status_code}")
                    return 1
                if f"/p/{q_project.slug}/questions" not in resp1.text:
                    fail("row A's pending question does not link to the "
                         "questions page")
                    return 1
                # Exactly one occurrence: if the flag were still
                # project-wide, both 'writing' rows (A and B) would each
                # render the line, giving two.
                count1 = resp1.text.count(waiting_text)
                if count1 != 1:
                    fail(f"waiting line appeared {count1} times with one "
                         "row asking and one not (want exactly 1 -- a "
                         "project-wide flag would show it on both "
                         "'writing' rows)")
                    return 1

                # Answering row A's question must clear its own line while
                # the still-pending, still-unrelated question changes
                # nothing (it was never able to trigger anything to begin
                # with).
                await app.state.db.answer_question(
                    question_id, answer_text="42%", status="answered",
                )
                resp2 = q_client.get(f"/p/{q_project.slug}/articles")
                if waiting_text in resp2.text:
                    fail("the waiting line is still shown after row A's "
                         "question was answered")
                    return 1
        finally:
            if prior_db_path_env is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior_db_path_env
        print("ok: the waiting line is scoped to the proposal that asked "
              "(run_id) -- an unrelated pending question lights up nothing, "
              "a second 'writing' row that never asked stays silent, and "
              "the line clears once the asking row's question is answered")

        # ── final-fixes round (FIX 1, 2, 3, 6): real HTTP calls ─────
        # Isolated DB (DC_DB_PATH override), same pattern as the nested-repo
        # / NULL-venue / waiting-line checks above -- these projects and
        # rows never touch data/dreaming.db.
        os.environ["DC_DB_PATH"] = str(page_db_dir / "test.db")
        try:
            with TestClient(app) as fix_client:
                fix_db = app.state.db
                fix_ps = ProjectsService(fix_db)

                # ── FIX 1: /written must compute verify_label from the ──
                # VENUE's article_verify_cmd, not the subject's. Reproduces
                # the worst case from the review: the SUBJECT has a verify
                # command configured, the VENUE (where the session actually
                # ran and where verify_ok=true was actually observed) does
                # not. Reading the subject's command would label this
                # "verified" -- a false claim about a build that never ran.
                f1_subject = await fix_ps.create(
                    slug="smoke-fix1-subject", label="Smoke Fix1 Subject",
                    working_dir=str(tmp),
                )
                f1_venue = await fix_ps.create(
                    slug="smoke-fix1-venue", label="Smoke Fix1 Venue",
                    working_dir=str(tmp),
                )
                await fix_ps.set_setting(
                    f1_subject.id, "article_verify_cmd", "npm run build",
                )
                f1_row = await fix_db.add_article_proposal(
                    f1_subject.id, source="manual", source_ref="",
                    evidence="smoke: FIX1 -- verify_label must read the venue",
                    title="Smoke FIX1 row", angle="…",
                    slug_hint="smoke-fix1-row", target_project_id=f1_venue.id,
                )
                await fix_db.set_article_proposal_status(f1_row, "writing")
                f1_resp = fix_client.post(
                    f"/api/articles/{f1_row}/written",
                    json={"draft_ref": "content/piece.md", "verify_output": "",
                          "writer_agent": "self", "verify_ok": True},
                )
                if f1_resp.status_code != 200:
                    fail(f"FIX1 write-back: {f1_resp.status_code} {f1_resp.text[:200]}")
                    return 1
                if f1_resp.json().get("verify_label") != "unverified":
                    fail("FIX1: venue has no verify_cmd but verify_label = "
                         f"{f1_resp.json().get('verify_label')!r}, want "
                         "'unverified' -- looks computed from the SUBJECT's "
                         "article_verify_cmd instead of the venue's")
                    return 1
                f1_row_after = await fix_db.get_article_proposal(f1_row)
                if f1_row_after["verify_label"] != "unverified":
                    fail("FIX1: persisted verify_label = "
                         f"{f1_row_after['verify_label']!r}, want 'unverified'")
                    return 1
                print("ok: FIX1 -- /written computes verify_label from the "
                      "venue's article_verify_cmd, not the subject's")

                # ── FIX 2: publish refuses a pinned venue that is no ──────
                # longer enabled, rather than falling back to the subject's
                # repository.
                f2_subject = await fix_ps.create(
                    slug="smoke-fix2-subject", label="Smoke Fix2 Subject",
                    working_dir=str(tmp),
                )
                f2_venue = await fix_ps.create(
                    slug="smoke-fix2-venue", label="Smoke Fix2 Venue",
                    working_dir=str(tmp), enabled=False,
                )
                f2_row = await fix_db.add_article_proposal(
                    f2_subject.id, source="manual", source_ref="",
                    evidence="smoke: FIX2 -- publish must refuse a disabled "
                    "pinned venue",
                    title="Smoke FIX2 row", angle="…",
                    slug_hint="smoke-fix2-row", target_project_id=f2_venue.id,
                )
                await fix_db.set_article_proposal_status(f2_row, "drafted")
                f2_resp = fix_client.post(
                    f"/p/{f2_subject.slug}/articles/{f2_row}/publish",
                    follow_redirects=False,
                )
                if f2_resp.status_code != 409:
                    fail("FIX2: publish with a disabled pinned venue: "
                         f"{f2_resp.status_code}, want 409")
                    return 1
                if f2_venue.slug not in f2_resp.text:
                    fail(f"FIX2: 409 must name the venue: {f2_resp.text[:300]}")
                    return 1
                f2_row_after = await fix_db.get_article_proposal(f2_row)
                if f2_row_after["status"] != "drafted":
                    fail("FIX2: a refused publish must not disturb the row: "
                         f"status={f2_row_after['status']!r}")
                    return 1
                print("ok: FIX2 -- publish refuses (409) when the row's "
                      "pinned venue is no longer enabled, naming it, and "
                      "leaves the row untouched")

                # ── FIX 3: an abandoned question must not stay pending ────
                # forever once its proposal leaves 'writing'. Two call
                # sites are HTTP-reachable without dispatching a real CLI
                # session: articles_cancel, and the /written failure path.
                # (The third call site -- the re-dispatch path inside
                # articles_approve -- only fires after a real write-article
                # session is actually launched via process_manager, which
                # this suite never does; its shared dismissal mechanism is
                # pinned directly against the db method a few blocks below.)
                f3_project = await fix_ps.create(
                    slug="smoke-fix3-project", label="Smoke Fix3 Project",
                    working_dir=str(tmp),
                )

                # -- cancel --
                f3_cancel_row = await fix_db.add_article_proposal(
                    f3_project.id, source="manual", source_ref="",
                    evidence="smoke: FIX3 -- cancel must dismiss its own "
                    "pending question",
                    title="Smoke FIX3 cancel row", angle="…",
                    slug_hint="smoke-fix3-cancel-row",
                )
                await fix_db.set_article_proposal_status(f3_cancel_row, "approved")
                await fix_db.set_article_proposal_status(f3_cancel_row, "writing")
                f3_cancel_qid = await fix_db.create_question(
                    project_id=f3_project.id, run_id=str(f3_cancel_row),
                    node_id=None, tool_use_id="smoke-fix3-cancel-q1",
                    questions_json='{"question": "real number?", "options": []}',
                )
                f3_cancel_resp = fix_client.post(
                    f"/p/{f3_project.slug}/articles/{f3_cancel_row}/cancel",
                    follow_redirects=False,
                )
                if f3_cancel_resp.status_code != 303:
                    fail(f"FIX3 cancel: {f3_cancel_resp.status_code}, want 303")
                    return 1
                f3_cancel_q = await fix_db.get_question(f3_cancel_qid)
                if f3_cancel_q["status"] != "dismissed":
                    fail("FIX3: cancel did not dismiss the proposal's own "
                         f"pending question: status={f3_cancel_q['status']!r}")
                    return 1
                print("ok: FIX3 -- cancel dismisses the cancelled proposal's "
                      "own pending question")

                # -- /written failure path --
                f3_fail_row = await fix_db.add_article_proposal(
                    f3_project.id, source="manual", source_ref="",
                    evidence="smoke: FIX3 -- a reported failure must "
                    "dismiss its own pending question",
                    title="Smoke FIX3 written-failure row", angle="…",
                    slug_hint="smoke-fix3-written-failure-row",
                )
                await fix_db.set_article_proposal_status(f3_fail_row, "approved")
                await fix_db.set_article_proposal_status(f3_fail_row, "writing")
                f3_fail_qid = await fix_db.create_question(
                    project_id=f3_project.id, run_id=str(f3_fail_row),
                    node_id=None, tool_use_id="smoke-fix3-written-failure-q1",
                    questions_json='{"question": "real number?", "options": []}',
                )
                f3_fail_resp = fix_client.post(
                    f"/api/articles/{f3_fail_row}/written",
                    json={"draft_ref": "",
                          "error_message": "unanswered question: no real number"},
                )
                if f3_fail_resp.status_code != 200:
                    fail(f"FIX3 written-failure: {f3_fail_resp.status_code} "
                         f"{f3_fail_resp.text[:200]}")
                    return 1
                f3_fail_q = await fix_db.get_question(f3_fail_qid)
                if f3_fail_q["status"] != "dismissed":
                    fail("FIX3: the /written failure path did not dismiss "
                         f"the proposal's own pending question: "
                         f"status={f3_fail_q['status']!r}")
                    return 1
                print("ok: FIX3 -- the /written failure path dismisses the "
                      "failed proposal's own pending question")

                # ── Round-1 fix: the /written failure report, EXACTLY as ──
                # documented. write-article.md's own text: "On failure,
                # POST the same endpoint with `{"error_message": "<what
                # failed>"}`." -- no draft_ref, no other keys. Before this
                # round, ArticleWrittenIn.draft_ref had no default, so
                # Pydantic rejected that literal payload with 422 before
                # the handler ever ran -- a writer that failed honestly
                # could not say so. Pin the shape verbatim from the
                # command's own text, not a shape convenient for the test.
                r1_project = await fix_ps.create(
                    slug="smoke-r1-failure-shape", label="Smoke R1 Failure Shape",
                    working_dir=str(tmp),
                )
                r1_row = await fix_db.add_article_proposal(
                    r1_project.id, source="manual", source_ref="",
                    evidence="smoke: round-1 -- the documented failure "
                    "payload must not 422",
                    title="Smoke R1 failure-shape row", angle="…",
                    slug_hint="smoke-r1-failure-shape-row",
                )
                await fix_db.set_article_proposal_status(r1_row, "approved")
                await fix_db.set_article_proposal_status(r1_row, "writing")
                r1_resp = fix_client.post(
                    f"/api/articles/{r1_row}/written",
                    json={"error_message": "npm run build exited 1"},
                )
                if r1_resp.status_code != 200:
                    fail("round-1: the command's own documented failure "
                         'payload ({"error_message": "..."}, no other '
                         f"keys) got {r1_resp.status_code}, want 200: "
                         f"{r1_resp.text[:300]}")
                    return 1
                r1_row_after = await fix_db.get_article_proposal(r1_row)
                if r1_row_after["status"] != "failed":
                    fail(f"round-1: status={r1_row_after['status']!r}, "
                         "want 'failed'")
                    return 1
                if "npm run build exited 1" not in (r1_row_after["error_message"] or ""):
                    fail("round-1: error_message not stored: "
                         f"{r1_row_after['error_message']!r}")
                    return 1
                print("ok: round-1 -- the documented failure payload "
                      '({"error_message": "..."}, no draft_ref, no other '
                      "keys) is accepted (200), the row becomes 'failed', "
                      "and the message is stored")

                # The success branch must still refuse a blank draft_ref
                # (422) -- the fix must not be readable as loosening that
                # contract. An empty JSON body means both error_message and
                # draft_ref default to "", which is unambiguously the
                # success path with nothing to record.
                r1_success_row = await fix_db.add_article_proposal(
                    r1_project.id, source="manual", source_ref="",
                    evidence="smoke: round-1 -- a blank draft_ref must "
                    "still 422 on the success branch",
                    title="Smoke R1 blank-draft-ref row", angle="…",
                    slug_hint="smoke-r1-blank-draft-ref-row",
                )
                await fix_db.set_article_proposal_status(r1_success_row, "approved")
                await fix_db.set_article_proposal_status(r1_success_row, "writing")
                r1_blank_resp = fix_client.post(
                    f"/api/articles/{r1_success_row}/written", json={},
                )
                if r1_blank_resp.status_code != 422:
                    fail("round-1: a payload with no error_message and no "
                         f"draft_ref got {r1_blank_resp.status_code}, want "
                         "422 -- the success branch must still refuse a "
                         "blank draft_ref")
                    return 1
                r1_success_row_after = await fix_db.get_article_proposal(r1_success_row)
                if r1_success_row_after["status"] != "writing":
                    fail("round-1: a refused write-back must not disturb "
                         f"the row: status={r1_success_row_after['status']!r}")
                    return 1
                print("ok: round-1 -- the success branch still refuses a "
                      "blank draft_ref with 422, unaffected by the "
                      "failure-path fix")

                # ── FIX 6: the venue can be re-pinned on a 'failed' row, ──
                # and the failed card offers the venue <select>.
                f6_subject = await fix_ps.create(
                    slug="smoke-fix6-subject", label="Smoke Fix6 Subject",
                    working_dir=str(tmp),
                )
                f6_venue = await fix_ps.create(
                    slug="smoke-fix6-venue", label="Smoke Fix6 Venue",
                    working_dir=str(tmp),
                )
                f6_row = await fix_db.add_article_proposal(
                    f6_subject.id, source="manual", source_ref="",
                    evidence="smoke: FIX6 -- a failed row's venue is not welded",
                    title="Smoke FIX6 row", angle="…",
                    slug_hint="smoke-fix6-row",
                )
                await fix_db.set_article_proposal_status(
                    f6_row, "failed",
                    error_message="wrong venue picked the first time",
                )
                if not await fix_db.set_article_proposal_venue(f6_row, f6_venue.id):
                    fail("FIX6: set_article_proposal_venue refused a "
                         "'failed' row")
                    return 1
                f6_row_after = await fix_db.get_article_proposal(f6_row)
                if f6_row_after["target_project_id"] != f6_venue.id:
                    fail("FIX6: the venue override did not persist on a "
                         f"'failed' row: {f6_row_after['target_project_id']!r}")
                    return 1
                f6_page = fix_client.get(f"/p/{f6_subject.slug}/articles")
                if f6_page.status_code != 200:
                    fail(f"FIX6 page: {f6_page.status_code}")
                    return 1
                f6_form_action = f"/p/{f6_subject.slug}/articles/{f6_row}/venue"
                if f6_form_action not in f6_page.text:
                    fail("FIX6: the failed card does not offer the venue "
                         f"<select> (no form posting to {f6_form_action!r})")
                    return 1
                print("ok: FIX6 -- set_article_proposal_venue allows a "
                      "'failed' row, and its card offers the venue <select>")
        finally:
            if prior_db_path_env is None:
                os.environ.pop("DC_DB_PATH", None)
            else:
                os.environ["DC_DB_PATH"] = prior_db_path_env
        print("ok: final-fixes round -- FIX1 (venue verify_label), FIX2 "
              "(disabled pinned venue refused), FIX3 (cancel + written-"
              "failure dismiss their own pending question), FIX6 (venue "
              "re-pinnable on failed, select shown) all pass over real HTTP")

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

        # ── Wave C: article_publish_extra_paths stages a build's output ──
        # A fresh repo: draft_ref keeps committing single files, but
        # extra_paths (unlike draft_ref) may name a directory -- a build
        # output is a subtree.
        extra_repo = tmp / "repo_extra"
        (extra_repo / "content").mkdir(parents=True)
        def git_extra(*args, cwd=extra_repo):
            return subprocess.run(["git", *args], cwd=str(cwd),
                                  capture_output=True, text=True)
        git_extra("init", "-q")
        git_extra("config", "user.email", "smoke@example.test")
        git_extra("config", "user.name", "Smoke")
        (extra_repo / "README.md").write_text("seed\n", encoding="utf-8")
        git_extra("add", "README.md")
        git_extra("commit", "-q", "-m", "seed")

        site_dir = extra_repo / "site"
        (site_dir / "blog").mkdir(parents=True)
        (site_dir / "index.html").write_text("<html>home</html>\n", encoding="utf-8")
        (site_dir / "blog" / "post.html").write_text("<html>post</html>\n", encoding="utf-8")
        (extra_repo / "content" / "extra-piece.md").write_text(
            "# Extra piece\n", encoding="utf-8",
        )
        extra_sha = await article_publish.publish(
            str(extra_repo), ["content/extra-piece.md"],
            message="publish: extra piece (unverified)", push=False,
            extra_paths=["site"],
        )
        extra_listed = set(git_extra(
            "show", "--name-only", "--pretty=format:", extra_sha,
        ).stdout.split())
        want = {"content/extra-piece.md", "site/index.html", "site/blog/post.html"}
        if extra_listed != want:
            fail(f"extra_paths directory staging: got {extra_listed}, want {want}")
            return 1
        extra_commit_msg = git_extra("log", "-1", "--format=%B", extra_sha).stdout
        if "build: 2 files from article_publish_extra_paths" not in extra_commit_msg:
            fail(f"commit message missing the build-count line: {extra_commit_msg!r}")
            return 1
        print("ok: extra_paths stages a directory tree -- the commit contains "
              "both the draft file and the tree's files, message names the count")

        # -- Wave A's guarantee, re-asserted with extra_paths in play: an
        #    unrelated modified file outside both draft_ref and extra_paths
        #    stays uncommitted and still dirty afterward --
        outside = extra_repo / "unrelated.txt"
        outside.write_text("leave me alone\n", encoding="utf-8")
        (extra_repo / "content" / "extra-piece-2.md").write_text(
            "# Extra piece two\n", encoding="utf-8",
        )
        (site_dir / "blog" / "post2.html").write_text(
            "<html>post2</html>\n", encoding="utf-8",
        )
        await article_publish.publish(
            str(extra_repo), ["content/extra-piece-2.md"],
            message="publish: extra piece two (unverified)", push=False,
            extra_paths=["site"],
        )
        status_outside = git_extra(
            "status", "--porcelain", "--", "unrelated.txt",
        ).stdout
        if not status_outside.strip() or not status_outside.lstrip().startswith("??"):
            fail("wave A guarantee broken: the unrelated file outside "
                 f"draft_ref and extra_paths did not stay dirty: {status_outside!r}")
            return 1
        print("ok: an unrelated file outside draft_ref and extra_paths stays "
              "dirty and uncommitted -- Wave A's guarantee holds with "
              "extra_paths in play")

        # -- a build that changed nothing is not an error: the draft still
        #    publishes and the message carries no build-count line --
        (extra_repo / "content" / "extra-piece-4.md").write_text(
            "# Extra piece four\n", encoding="utf-8",
        )
        noop_sha = await article_publish.publish(
            str(extra_repo), ["content/extra-piece-4.md"],
            message="publish: extra piece four (unverified)", push=False,
            extra_paths=["site"],
        )
        noop_listed = git_extra(
            "show", "--name-only", "--pretty=format:", noop_sha,
        ).stdout.split()
        if noop_listed != ["content/extra-piece-4.md"]:
            fail(f"an unchanged build output leaked into the commit: {noop_listed}")
            return 1
        noop_msg = git_extra("log", "-1", "--format=%B", noop_sha).stdout
        if "build:" in noop_msg:
            fail("a build that changed nothing must not add a build-count "
                 f"line: {noop_msg!r}")
            return 1
        print("ok: an extra_paths build that changed nothing is not an "
              "error, and adds no build-count line")

        # -- a non-existent extra path refuses the publish, naming it, and
        #    leaves the index clean --
        (extra_repo / "content" / "extra-piece-3.md").write_text(
            "# Extra piece three\n", encoding="utf-8",
        )
        before_missing = git_extra("diff", "--cached", "--name-only").stdout
        try:
            await article_publish.publish(
                str(extra_repo), ["content/extra-piece-3.md"],
                message="should never commit", push=False,
                extra_paths=["site-missing"],
            )
        except article_publish.PublishError as e:
            if "site-missing" not in str(e):
                fail(f"non-existent extra path error didn't name it: {e}")
                return 1
        else:
            fail("publish accepted a non-existent extra path")
            return 1
        after_missing = git_extra("diff", "--cached", "--name-only").stdout
        if after_missing != before_missing:
            fail("a refused extra path still touched the index: "
                 f"before={before_missing!r} after={after_missing!r}")
            return 1
        print("ok: a non-existent extra path refuses the publish, naming "
              "it, and leaves the index clean")

        # -- extra_paths get the same '..'/absolute/glob refusals as
        #    draft_ref; only the directory rule differs --
        before_bad_extra = git_extra("diff", "--cached", "--name-only").stdout
        abs_site = str((extra_repo / "site").resolve())
        for bad, why in [
            ("site/../site", "a '..' segment"),
            (abs_site, "an absolute path"),
            ("site/*.html", "a glob character"),
        ]:
            try:
                await article_publish.publish(
                    str(extra_repo), ["content/extra-piece-3.md"],
                    message="should never commit", push=False,
                    extra_paths=[bad],
                )
            except article_publish.PublishError:
                pass
            else:
                fail(f"publish accepted an invalid extra path ({why}): {bad!r}")
                return 1
        after_bad_extra = git_extra("diff", "--cached", "--name-only").stdout
        if after_bad_extra != before_bad_extra:
            fail("a rejected extra path still touched the index: "
                 f"before={before_bad_extra!r} after={after_bad_extra!r}")
            return 1
        print("ok: extra_paths get the same '..'/absolute/glob refusals as "
              "draft_ref, index untouched")

        # -- the asymmetry this wave exists to establish: draft_ref may
        #    never be a directory, even when extra_paths, in the very same
        #    call, names one and is accepted --
        try:
            await article_publish.publish(
                str(extra_repo), ["content"], message="should never commit",
                push=False, extra_paths=["site"],
            )
        except article_publish.PublishError as e:
            if "not a regular file" not in str(e):
                fail(f"draft_ref-as-directory refusal message unexpected: {e}")
                return 1
        else:
            fail("publish accepted a directory as draft_ref merely because "
                 "extra_paths allows directories")
            return 1
        print("ok: draft_ref still refuses a directory even though "
              "extra_paths, in the same call, accepts one -- the asymmetry "
              "this wave exists to establish")

        # -- empty extra_paths (article_publish_extra_paths="" -> []) must
        #    reproduce today's behaviour exactly: same set of committed
        #    files, no build-count line in the message --
        empty_repo = tmp / "repo_extra_empty"
        (empty_repo / "content").mkdir(parents=True)
        def git_empty(*args, cwd=empty_repo):
            return subprocess.run(["git", *args], cwd=str(cwd),
                                  capture_output=True, text=True)
        git_empty("init", "-q")
        git_empty("config", "user.email", "smoke@example.test")
        git_empty("config", "user.name", "Smoke")
        (empty_repo / "README.md").write_text("seed\n", encoding="utf-8")
        git_empty("add", "README.md")
        git_empty("commit", "-q", "-m", "seed")
        (empty_repo / "content" / "empty-extra.md").write_text(
            "# No extra paths\n", encoding="utf-8",
        )
        empty_sha = await article_publish.publish(
            str(empty_repo), ["content/empty-extra.md"],
            message="publish: no extra paths (unverified)", push=False,
            extra_paths=[],
        )
        empty_listed = git_empty(
            "show", "--name-only", "--pretty=format:", empty_sha,
        ).stdout.split()
        if empty_listed != ["content/empty-extra.md"]:
            fail(f"extra_paths=[] committed {empty_listed}, want only the draft path")
            return 1
        empty_msg = git_empty("log", "-1", "--format=%B", empty_sha).stdout
        if "build:" in empty_msg:
            fail(f"extra_paths=[] must not add a build-count line: {empty_msg!r}")
            return 1
        print("ok: empty extra_paths reproduces the pre-Wave-C behaviour -- "
              "only the draft path is committed, no build-count line")

        # ── review round 1, Critical: a failed extra-paths `git add` must ──
        # roll back, not leave the draft staged with no disclosure. Every
        # refusal tested so far is caught by _validate_paths before any git
        # call runs -- none of them exercise a *mid-sequence* git failure.
        # A gitignored extra path is the realistic trigger the spec's own
        # risk table waved through without asking what state it leaves
        # behind: `git add` on it returns non-zero, but only *after* the
        # first `git add` call (for draft_ref) already succeeded and staged
        # the draft. Assert the index ends up exactly where it started, and
        # the error says a rollback happened.
        gi_repo = tmp / "repo_gitignore_add"
        (gi_repo / "content").mkdir(parents=True)
        (gi_repo / "site").mkdir(parents=True)
        def git_gi(*args, cwd=gi_repo):
            return subprocess.run(["git", *args], cwd=str(cwd),
                                  capture_output=True, text=True)
        git_gi("init", "-q")
        git_gi("config", "user.email", "smoke@example.test")
        git_gi("config", "user.name", "Smoke")
        (gi_repo / ".gitignore").write_text("site\n", encoding="utf-8")
        (gi_repo / "README.md").write_text("seed\n", encoding="utf-8")
        git_gi("add", ".gitignore", "README.md")
        git_gi("commit", "-q", "-m", "seed")
        (gi_repo / "content" / "piece.md").write_text(
            "# Piece\n", encoding="utf-8",
        )
        (gi_repo / "site" / "index.html").write_text(
            "<html>home</html>\n", encoding="utf-8",
        )
        before_gi = git_gi("diff", "--cached", "--name-only").stdout
        try:
            await article_publish.publish(
                str(gi_repo), ["content/piece.md"],
                message="should roll back fully", push=False,
                extra_paths=["site"],
            )
        except article_publish.PublishError as e:
            msg = str(e)
            if "git add failed" not in msg:
                fail(f"gitignored extra path: wrong step named: {msg!r}")
                return 1
            if "staged changes rolled back" not in msg:
                fail(f"gitignored extra path: rollback not disclosed: {msg!r}")
                return 1
            if "site" not in msg:
                fail(f"gitignored extra path: git's own message lost: {msg!r}")
                return 1
        else:
            fail("publish accepted a gitignored extra path")
            return 1
        after_gi = git_gi("diff", "--cached", "--name-only").stdout
        if after_gi != before_gi:
            fail("a failed extra-paths git add left the draft (or part of "
                 f"the extra tree) staged: before={before_gi!r} "
                 f"after={after_gi!r}")
            return 1
        draft_status = git_gi(
            "status", "--porcelain", "--", "content/piece.md",
        ).stdout
        if not draft_status.lstrip().startswith("??"):
            fail("the draft must be back to untracked/dirty after the "
                 f"rollback, got: {draft_status!r}")
            return 1
        print("ok: a gitignored extra path fails the (second) git add "
              "mid-sequence, and the draft staged by the first add is "
              "rolled back too -- not left behind with no disclosure")

        # -- the worse case the review flagged: a single `git add` call can
        #    return non-zero for one bad pathspec while still silently
        #    staging another good one in the same call. extra_paths=[good,
        #    bad] reaches git as ONE `git add -- good bad` invocation. --
        (gi_repo / "good").mkdir(parents=True)
        (gi_repo / "good" / "ok.txt").write_text("fine\n", encoding="utf-8")
        (gi_repo / "content" / "piece2.md").write_text(
            "# Piece two\n", encoding="utf-8",
        )
        before_multi = git_gi("diff", "--cached", "--name-only").stdout
        try:
            await article_publish.publish(
                str(gi_repo), ["content/piece2.md"],
                message="should roll back fully", push=False,
                extra_paths=["good", "site"],
            )
        except article_publish.PublishError as e:
            if "staged changes rolled back" not in str(e):
                fail(f"multi-entry rollback not disclosed: {e}")
                return 1
        else:
            fail("publish accepted a multi-entry extra_paths list "
                 "containing a gitignored path")
            return 1
        after_multi = git_gi("diff", "--cached", "--name-only").stdout
        if after_multi != before_multi:
            fail("the good pathspec's partial stage (from the same failing "
                 "git add call) survived the rollback: "
                 f"before={before_multi!r} after={after_multi!r}")
            return 1
        print("ok: a multi-entry extra_paths list where one path is "
              "gitignored rolls back the other, partially-staged path too")

        # ── review round 1, Important: a nested .git becomes a dangling ──
        # gitlink, not a refusal, unless caught explicitly -- git add's own
        # return code is 0 for this. Refused at validation time, before any
        # git call, so nothing is ever staged.
        vendored_repo = tmp / "repo_vendored_git"
        (vendored_repo / "content").mkdir(parents=True)
        def git_vendored(*args, cwd=vendored_repo):
            return subprocess.run(["git", *args], cwd=str(cwd),
                                  capture_output=True, text=True)
        git_vendored("init", "-q")
        git_vendored("config", "user.email", "smoke@example.test")
        git_vendored("config", "user.name", "Smoke")
        (vendored_repo / "README.md").write_text("seed\n", encoding="utf-8")
        git_vendored("add", "README.md")
        git_vendored("commit", "-q", "-m", "seed")
        (vendored_repo / "content" / "piece.md").write_text(
            "# Piece\n", encoding="utf-8",
        )
        vendored_asset = vendored_repo / "site" / "vendor" / "theme" / ".git"
        vendored_asset.mkdir(parents=True)
        (vendored_asset / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        before_vendored = git_vendored("diff", "--cached", "--name-only").stdout
        try:
            await article_publish.publish(
                str(vendored_repo), ["content/piece.md"],
                message="should never commit", push=False,
                extra_paths=["site"],
            )
        except article_publish.PublishError as e:
            msg = str(e)
            if "nested .git" not in msg or "gitlink" not in msg:
                fail(f"nested .git refusal message unexpected: {msg!r}")
                return 1
        else:
            fail("publish accepted an extra path whose tree contains a "
                 "nested .git (would stage a dangling gitlink)")
            return 1
        after_vendored = git_vendored("diff", "--cached", "--name-only").stdout
        if after_vendored != before_vendored:
            fail("a rejected nested-.git path still touched the index: "
                 f"before={before_vendored!r} after={after_vendored!r}")
            return 1
        print("ok: an extra path whose tree contains a nested .git is "
              "refused (would stage a dangling gitlink), index untouched")

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

        # ── FIX 6: a 'failed' row's venue is not welded ─────────────
        # No draft exists on disk for a 'failed' row (the write-back never
        # landed a draft_ref), so the reason set_article_proposal_venue is
        # otherwise restricted does not apply to it -- it must be settable
        # on 'failed' exactly like 'proposed', and refused on everything
        # else ('drafted', 'writing', 'published' all had -- or are
        # producing -- a real draft the venue is now bound to).
        failed_venue_row = await db.add_article_proposal(
            pid, source="manual", source_ref="",
            evidence="smoke: FIX6 -- a failed row's venue is not welded",
            title="Smoke FIX6 DB row", angle="…",
            slug_hint="smoke-fix6-db-row",
        )
        await db.set_article_proposal_status(
            failed_venue_row, "failed", error_message="wrong venue the first time",
        )
        if not await db.set_article_proposal_venue(failed_venue_row, pid):
            fail("FIX6: set_article_proposal_venue refused a 'failed' row")
            return 1
        if (await db.get_article_proposal(failed_venue_row))["target_project_id"] != pid:
            fail("FIX6: the venue override did not persist on a 'failed' row")
            return 1
        # And the boundary still holds: 'drafted' must still be refused,
        # exactly as before this fix -- only 'proposed' and 'failed' widen.
        await db.set_article_proposal_status(failed_venue_row, "drafted")
        if await db.set_article_proposal_venue(failed_venue_row, None):
            fail("FIX6: set_article_proposal_venue must still refuse a "
                 "'drafted' row")
            return 1
        print("ok: FIX6 -- set_article_proposal_venue allows 'proposed' and "
              "'failed', still refuses 'drafted'/'writing'/'published'")

        # ── FIX 5: create_question's dedupe only reuses a PENDING row ────
        # A repeated tool_use_id while the row is still pending is the same
        # ask (a resumed session) and must return that same id. Once the
        # row has moved past pending (answered/dismissed), a repeated
        # tool_use_id is a fresh ask that happens to collide with an old
        # one -- reusing that row would silently hand back a previous
        # attempt's answer to a question it never actually asked.
        dedupe_tool_use_id = "smoke-fix5-dedupe-tool-use-id"
        qid_first = await db.create_question(
            project_id=pid, run_id="smoke-fix5-run", node_id=None,
            tool_use_id=dedupe_tool_use_id,
            questions_json='{"question": "first ask", "options": []}',
        )
        qid_resumed = await db.create_question(
            project_id=pid, run_id="smoke-fix5-run", node_id=None,
            tool_use_id=dedupe_tool_use_id,
            questions_json='{"question": "first ask, resumed", "options": []}',
        )
        if qid_resumed != qid_first:
            fail("FIX5: a repeated tool_use_id on a still-pending row must "
                 f"return the same id: got {qid_resumed!r}, want {qid_first!r}")
            return 1
        print("ok: FIX5 -- create_question dedupes a repeated tool_use_id "
              "while the existing row is still pending")

        await db.answer_question(qid_first, answer_text="the old answer",
                                  status="answered")
        qid_collision = await db.create_question(
            project_id=pid, run_id="smoke-fix5-run", node_id=None,
            tool_use_id=dedupe_tool_use_id,
            questions_json='{"question": "second ask, forgot the run tag", '
            '"options": []}',
        )
        if qid_collision == qid_first:
            fail("FIX5: a repeated tool_use_id on an already-answered row "
                 "must not hand back that same stale row")
            return 1
        fresh_question = await db.get_question(qid_collision)
        if fresh_question["status"] != "pending" or (fresh_question.get("answer_text") or ""):
            fail("FIX5: the fresh row must be pending with no answer, got "
                 f"status={fresh_question['status']!r} "
                 f"answer_text={fresh_question.get('answer_text')!r}")
            return 1
        if await db.get_question(qid_first) is not None:
            fail("FIX5: the stale answered row should have been replaced, "
                 f"but the old id {qid_first} still resolves")
            return 1
        print("ok: FIX5 -- a repeated tool_use_id on an already-answered/"
              "dismissed row gets a fresh pending row instead of the stale "
              "answer, and the stale row is gone")

        # ── FIX 3 (db level): dismiss_article_proposal_questions ────
        # Covers the shared mechanism all three call sites (cancel, the
        # /written failure path, and the re-dispatch path inside
        # articles_approve) use -- the HTTP-level pins above already prove
        # the first two call sites wire it in; this proves the method
        # itself: scoped to run_id==str(proposal_id) (an unrelated pending
        # question on the same project must survive), idempotent (a second
        # call finds nothing left to dismiss), and a safe no-op for a
        # proposal that never asked anything at all.
        dismiss_target_id = await db.add_article_proposal(
            pid, source="manual", source_ref="",
            evidence="smoke: FIX3 db-level -- dismiss_article_proposal_questions",
            title="Smoke FIX3 db row", angle="…",
            slug_hint="smoke-fix3-db-row",
        )
        dismiss_own_qid = await db.create_question(
            project_id=pid, run_id=str(dismiss_target_id), node_id=None,
            tool_use_id="smoke-fix3-db-own-q1",
            questions_json='{"question": "own question", "options": []}',
        )
        dismiss_unrelated_qid = await db.create_question(
            project_id=pid, run_id="some-other-run", node_id=None,
            tool_use_id="smoke-fix3-db-unrelated-q1",
            questions_json='{"question": "unrelated question", "options": []}',
        )
        n_dismissed = await db.dismiss_article_proposal_questions(dismiss_target_id)
        if n_dismissed != 1:
            fail(f"dismiss_article_proposal_questions: dismissed {n_dismissed}, want 1")
            return 1
        if (await db.get_question(dismiss_own_qid))["status"] != "dismissed":
            fail("dismiss_article_proposal_questions did not dismiss the "
                 "proposal's own pending question")
            return 1
        if (await db.get_question(dismiss_unrelated_qid))["status"] != "pending":
            fail("dismiss_article_proposal_questions touched an unrelated "
                 "run_id's pending question")
            return 1
        # Idempotent: nothing pending left to dismiss.
        if await db.dismiss_article_proposal_questions(dismiss_target_id) != 0:
            fail("dismiss_article_proposal_questions must be a no-op once "
                 "nothing of this proposal's is still pending")
            return 1
        # A proposal with no questions at all is also a no-op, not an error.
        if await db.dismiss_article_proposal_questions(dismiss_target_id + 999999) != 0:
            fail("dismiss_article_proposal_questions must no-op for a "
                 "proposal with no questions at all")
            return 1
        print("ok: FIX3 -- dismiss_article_proposal_questions dismisses "
              "only this proposal's own pending questions and no-ops "
              "otherwise")

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

        # ---- starter-kit command drift ------------------------------------
        # The center saw a command missing but never one gone stale, so an
        # installed copy aged silently as the templates moved on. The signal
        # only earns trust if it never cries wolf: the templates in this repo
        # are CRLF and a checkout elsewhere is routinely LF, so a
        # line-ending difference must NOT read as drift, while a single
        # changed heading must.
        kit_dir = Path(tempfile.mkdtemp(prefix="dc_smoke_kit_"))
        cmds = kit_dir / ".claude" / "commands"
        cmds.mkdir(parents=True)
        tpl = starter_kit.TEMPLATE_DIR / "commands" / "write-article.md"
        raw = tpl.read_bytes()
        installed = cmds / "write-article.md"

        noise_cases = [
            ("byte-identical", raw),
            ("LF instead of CRLF", raw.replace(b"\r\n", b"\n")),
            ("no trailing newline", raw.rstrip(b"\r\n")),
            ("extra trailing newlines", raw + b"\n\n"),
        ]
        for label, content in noise_cases:
            installed.write_bytes(content)
            if starter_kit.command_stale(kit_dir, "write-article"):
                fail(f"command_stale called {label} drift — a false alarm here "
                     f"trains the operator to ignore the real signal")
                return 1
        print(f"ok: command_stale ignores {len(noise_cases)} kinds of "
              f"line-ending / trailing-newline noise")

        drift_cases = [
            ("a renamed heading", raw.replace(b"## 4. Verify", b"## Sprawdzenie")),
            ("the wave-A truncation that shipped for real", raw[:3680]),
            ("an empty file", b""),
        ]
        for label, content in drift_cases:
            installed.write_bytes(content)
            if not starter_kit.command_stale(kit_dir, "write-article"):
                fail(f"command_stale missed {label}")
                return 1
        print(f"ok: command_stale catches {len(drift_cases)} kinds of real "
              f"content drift, including the wave-A copy that actually shipped")

        installed.unlink()
        if starter_kit.command_stale(kit_dir, "write-article"):
            fail("command_stale reported an absent command as drifted — that "
                 "is command_installed's signal, and reporting both would say "
                 "two different things about one file")
            return 1
        if starter_kit.command_installed(kit_dir, "write-article"):
            fail("command_installed reported an absent command as present")
            return 1
        print("ok: an absent command is missing, not stale — one signal per "
              "file")

        # status() over a whole kit, which is what the rotation page renders.
        kit2 = Path(tempfile.mkdtemp(prefix="dc_smoke_kit2_"))
        starter_kit.install(kit2, force=True)
        st = starter_kit.status(kit2)
        if st.stale or not st.up_to_date or not st.all_present:
            fail(f"a fresh install is not up to date: missing={st.missing} "
                 f"stale={st.stale} up_to_date={st.up_to_date}")
            return 1
        print("ok: status() calls a fresh install up_to_date with nothing stale")

        (kit2 / ".claude" / "commands" / "self-study.md").write_bytes(b"stub\n")
        st = starter_kit.status(kit2)
        if st.stale != ["commands/self-study.md"]:
            fail(f"status().stale should name exactly the drifted file, got "
                 f"{st.stale}")
            return 1
        if not st.all_present:
            fail("all_present must keep meaning 'nothing missing' — three "
                 "pages already render it, and folding drift into it would "
                 "change what they claim without touching them")
            return 1
        if st.up_to_date:
            fail("up_to_date must be False when a file has drifted")
            return 1
        print("ok: status() separates drift from absence — all_present stays "
              "True, up_to_date goes False, stale names the one file")

        for p in (kit2 / ".claude").rglob("*"):
            if p.is_file():
                p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))
        st = starter_kit.status(kit2)
        if st.stale != ["commands/self-study.md"]:
            fail(f"converting the whole kit to LF changed the drift verdict: "
                 f"{st.stale}")
            return 1
        print("ok: converting an entire installed kit to LF adds no drift")

        print("PASS")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
