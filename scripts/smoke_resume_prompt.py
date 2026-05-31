"""Regression guard for the orchestrator "Продолжить" (resume) button.

The bug: resuming a finished run spawns claude with `--input-format stream-json
--resume <id>` and an open stdin PIPE, then relies on start_command to push the
prompt into that stdin. The send condition used to be

    if interactive_stdin and prompt and not resume_session_id:

so the resume case (resume_session_id set) was excluded — the prompt was never
written, claude blocked forever waiting for stdin input, the run sat in
"running" with zero output, and the UI looked like "нажимаю Продолжить, ничего
не происходит".

This test drives start_command with interactive_stdin=True + resume_session_id
and asserts:
  1. the prompt IS delivered via stdin (send_user_message called with it), and
  2. the prompt is NOT in argv (interactive mode never passes -p <prompt>),
     while --resume <id> IS in argv.

Does NOT spawn a real claude process — fakes the subprocess factory.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services import process_manager as pm_mod
from dreaming.services.process_manager import ProcessManager, RunningSession


class _StubSettings:
    max_concurrent = 4
    learning_notes_dir = None
    session_logs_dir = tempfile.gettempdir()


class _StubDB:
    async def execute(self, sql: str, params: tuple = ()) -> None:
        return None

    async def create_session(self, *a, **kw) -> str:
        return "db-sid"


class _FakeStdout:
    async def readline(self) -> bytes:
        return b""  # immediate EOF → reader exits, cleanup runs


class _FakeStdin:
    def write(self, b: bytes) -> None:  # send_user_message is patched, never hit
        pass

    async def drain(self) -> None:
        return None


class _FakeProc:
    def __init__(self) -> None:
        self.stdout = _FakeStdout()
        self.stdin = _FakeStdin()
        self.returncode = 0
        self.pid = 4321

    async def wait(self) -> int:
        return 0


class _StubProject:
    id = 7
    slug = "acct"
    working_dir = "."


async def _run_start_command(*, resume: str | None):
    """Call start_command with the fakes wired in; return (recorded, argv)."""
    captured_argv: list[str] = []
    recorded: list[str] = []

    async def fake_factory(*argv, **kwargs):
        captured_argv.extend(argv)
        return _FakeProc()

    async def fake_send(self, text: str) -> bool:
        recorded.append(text)
        return True

    orig_factory = pm_mod.create_subprocess_exec_compat
    orig_resolve = pm_mod._resolve_claude_path
    orig_send = RunningSession.send_user_message
    pm_mod.create_subprocess_exec_compat = fake_factory
    pm_mod._resolve_claude_path = lambda p: p
    RunningSession.send_user_message = fake_send
    try:
        pm = ProcessManager(_StubSettings(), _StubDB(), projects=None)
        await pm.start_command(
            _StubProject(),
            command_name="resume-deadbeef" if resume else "fresh",
            prompt="продолжай",
            claude_path="claude",
            model="sonnet",
            max_turns=10,
            timeout_minutes=1,
            resume_session_id=resume,
            interactive_stdin=True,
        )
        # Let the reader task hit EOF and run _cleanup (which cancels watchdog),
        # so we don't leak pending tasks.
        for _ in range(5):
            await asyncio.sleep(0)
    finally:
        pm_mod.create_subprocess_exec_compat = orig_factory
        pm_mod._resolve_claude_path = orig_resolve
        RunningSession.send_user_message = orig_send
    return recorded, captured_argv


async def amain() -> int:
    # 1) RESUME: prompt must reach stdin; argv carries --resume, not the prompt.
    recorded, argv = await _run_start_command(resume="sess-123")
    assert recorded == ["продолжай"], (
        f"resume did NOT deliver prompt to stdin (regression!); recorded={recorded!r}"
    )
    assert "--resume" in argv and "sess-123" in argv, f"--resume missing from argv: {argv}"
    assert "--input-format" in argv and "stream-json" in argv, f"interactive flags missing: {argv}"
    assert "продолжай" not in argv, f"prompt leaked into argv (should go via stdin): {argv}"
    print("OK resume: prompt delivered via stdin, --resume in argv, prompt not in argv")

    # 2) FRESH interactive (control): still delivers prompt via stdin, no --resume.
    recorded2, argv2 = await _run_start_command(resume=None)
    assert recorded2 == ["продолжай"], f"fresh interactive lost its prompt: {recorded2!r}"
    assert "--resume" not in argv2, f"fresh start should not --resume: {argv2}"
    print("OK fresh interactive: prompt delivered via stdin, no --resume")

    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
