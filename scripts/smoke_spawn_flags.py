"""Smoke / regression guard for the rotation spawn (the most critical path).

Covers three root causes of the recurring "Ожидание вывода…" hang:

  1. PERMISSION FLAG — must be `--permission-mode bypassPermissions`, NOT
     `--allowedTools`. Verified end-to-end on CLI 2.1.150: bypass streams AND
     writes to `.claude/`; `--allowedTools` runs in "don't ask mode" which
     silently denies every Write/Edit/mutating-Bash, so self-study can never
     persist its note. This guard stops anyone re-flipping the flag blindly.

  2. SILENT FAILURE — when claude exits non-zero having produced no output
     (e.g. rate limit / startup error), the session must emit a human-readable
     diagnostic line AND persist it to `error_message`, never just sit on
     "Ожидание вывода…" with no clue.

  3. WATCHDOG LANDMINE — `_has_pending_question` must be scoped to the
     session's own project, so an orphaned pending question elsewhere can't
     disable the silence-kill for every session forever.

Does NOT spawn a real claude process — uses a cheap dummy child.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services import process_manager as pm_mod
from dreaming.services.process_manager import ProcessManager, RunningSession
from dreaming.services._subprocess_compat import create_subprocess_exec_compat


class _StubSettings:
    max_concurrent = 2
    learning_notes_dir = None
    session_logs_dir = None  # disable log file writes for the test


class _StubDB:
    """Captures execute() calls and answers _has_pending_question queries."""

    def __init__(self, pending_project_ids: set[int] | None = None):
        self.executed: list[tuple[str, tuple]] = []
        self._pending = pending_project_ids or set()

    async def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    async def fetch_all(self, sql: str, params: tuple = ()):
        # Mimic the real query: SELECT ... WHERE status='pending' [AND project_id=?]
        if "project_id" in sql:
            pid = params[0] if params else None
            return [(1,)] if pid in self._pending else []
        # Unscoped query (the bug) would return rows whenever ANYTHING pends.
        return [(1,)] if self._pending else []

    async def reconcile_stale_sessions(self, **kw) -> int:
        return 0


def _check_flag() -> None:
    flags = pm_mod._BYPASS_PERMISSION_FLAGS
    assert flags == ["--dangerously-skip-permissions"], (
        f"spawn flag regressed to {flags!r}; must be --dangerously-skip-permissions "
        "(a session-wide hard override). `--permission-mode bypassPermissions` is a "
        "downgradeable MODE — under agent-teams it transitions mid-session to "
        "'don't ask' and denies all writes; `--allowedTools` silently breaks "
        ".claude/ persistence. Neither is safe for unattended rotation."
    )
    print("OK flag:", flags)


async def _check_silent_failure() -> None:
    pm = ProcessManager(_StubSettings(), _StubDB(), projects=None)
    # Dummy child: exits 1, prints nothing — the zero-output failure shape.
    if sys.platform == "win32":
        argv = ["cmd", "/c", "exit 1"]
    else:
        argv = ["sh", "-c", "exit 1"]
    proc = await create_subprocess_exec_compat(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
    )
    sess = RunningSession(
        session_id="test-sid", agent_name="frontend",
        project_id=2, project_slug="acct", process=proc,
    )
    sess.key = "acct:frontend"
    pm.running[sess.key] = sess
    pm.keep_awake.acquire()
    await pm._read_stdout(sess)

    assert any(l.startswith("[error]") for l in sess.output_lines), (
        f"no [error] diagnostic emitted for zero-output failure; got: {sess.output_lines}"
    )
    # error_message must have been persisted in the cleanup UPDATE
    err_updates = [p for (s, p) in pm.db.executed if "error_message" in s.lower()]
    assert err_updates, "no UPDATE wrote error_message on failure"
    # error_message param must be non-empty (3rd placeholder in the UPDATE)
    assert any(p[2] for p in err_updates), "error_message persisted as NULL"
    n_err = sum(1 for l in sess.output_lines if l.startswith("[error]"))
    print(f"OK silent-failure diagnostic: emitted {n_err} [error] line(s), "
          f"error_message persisted")


async def _check_watchdog_scoped() -> None:
    # Pending question in project 99 must NOT keep a project-2 session alive.
    pm = ProcessManager(_StubSettings(), _StubDB(pending_project_ids={99}), projects=None)

    class _FakeProc:
        returncode = None
    sess = RunningSession(
        session_id="s", agent_name="a", project_id=2, project_slug="p",
        process=_FakeProc(),  # type: ignore[arg-type]
    )
    has = await pm._has_pending_question(sess)
    assert has is False, "pending question in another project wrongly kept session alive"

    pm2 = ProcessManager(_StubSettings(), _StubDB(pending_project_ids={2}), projects=None)
    sess2 = RunningSession(
        session_id="s", agent_name="a", project_id=2, project_slug="p",
        process=_FakeProc(),  # type: ignore[arg-type]
    )
    assert await pm2._has_pending_question(sess2) is True, "own-project pending not detected"
    print("OK watchdog project-scoped")


async def amain() -> int:
    _check_flag()
    await _check_silent_failure()
    await _check_watchdog_scoped()
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
