"""Process Manager — runs claude CLI sessions with stdout streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
from pathlib import Path
from typing import AsyncIterator, Callable, TYPE_CHECKING
from uuid import uuid4

from dreaming.services.keep_awake import KeepAwake
from dreaming.services._subprocess_compat import create_subprocess_exec_compat

if TYPE_CHECKING:
    from dreaming.services.projects import Project

log = logging.getLogger(__name__)

RING_BUFFER_SIZE = 5000

# stream-json от claude может присылать assistant-блоки заметно крупнее
# дефолтных 64 KB asyncio.StreamReader (планы с многими tool_use, длинные
# tool_result-вложения). Поднимаем лимит, чтобы readline() не бросал
# LimitOverrunError и не обрывал чтение посреди сессии.
STDOUT_BUFFER_LIMIT = 16 * 1024 * 1024  # 16 MB

# Permission grant for unattended sessions. We run claude with no TTY (-p /
# --print), so it can never prompt for a permission; any tool not pre-approved
# is silently denied.
#
# History of what does NOT work on Claude CLI >= 2.1.x outside a sandbox:
#   - `--dangerously-skip-permissions` — gated ("sandboxes with no internet
#     access only"); downgrades the session to `dontAsk` mode.
#   - `--permission-mode bypassPermissions` — also downgraded to `dontAsk`
#     in this environment (verified 2026-05-24: self-study still reported
#     Write/Bash denied with the flag set).
# In `dontAsk` mode the CLI denies anything not on the allow-list WITHOUT
# prompting. The reliable lever is therefore the allow-list itself:
# `--allowedTools` is honoured in every mode. We grant the full tool set the
# self-study / orchestrator agents need (notes + evolution files via Write/Edit,
# report-back curl via Bash, sub-agents via Task). `--permission-mode
# bypassPermissions` is kept too — harmless if downgraded, and if a future CLI
# honours it we get clean full access.
_AGENT_TOOLS = "Bash Read Write Edit Glob Grep Task TodoWrite WebFetch WebSearch NotebookEdit Skill"
_BYPASS_PERMISSION_FLAGS = [
    "--permission-mode", "bypassPermissions",
    "--allowedTools", _AGENT_TOOLS,
]


# Human-readable hints for the most common claude.exe exit codes. Appended
# to the `[exit] code=N — <hint>` line so users can tell at a glance whether
# the process died from inside (1/2) or was killed by something external
# (130 = Ctrl+C, 137 = SIGKILL, 143 = SIGTERM, 3221225786 = STATUS_CONTROL_C_EXIT on Windows).
_EXIT_CODE_HINTS: dict[int, str] = {
    0:    "ok",
    1:    "internal error in claude CLI",
    2:    "claude CLI usage/argument error",
    130:  "Ctrl+C (SIGINT)",
    137:  "killed (SIGKILL or watchdog)",
    143:  "terminated (SIGTERM)",
    -1:   "process did not exit cleanly",
    3221225786: "Ctrl+C on Windows (STATUS_CONTROL_C_EXIT)",
    3221225794: "killed on Windows (STATUS_DLL_INIT_FAILED / other)",
}


def _resolve_claude_path(claude_path: str) -> str:
    """Resolve the Claude CLI executable for the current platform.

    On Windows bare 'claude' is a bash script that can't be executed directly;
    shutil.which picks up 'claude.cmd'. On Linux/macOS it returns the same path.
    Falls back to the original string so the caller raises a clear FileNotFoundError.
    """
    return shutil.which(claude_path) or claude_path


@dataclass
class RunningSession:
    session_id: str
    agent_name: str
    project_id: int
    project_slug: str
    process: asyncio.subprocess.Process
    output_lines: list[str] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    last_stdout_at: float = field(default_factory=time.time)
    _reader_task: asyncio.Task | None = None
    _watchdog_task: asyncio.Task | None = None
    key: str = ""  # composite key in pm.running dict
    log_path: str | None = None  # absolute path to per-session stdout log file

    async def send_user_message(self, text: str) -> bool:
        """Записать stream-json user-message в stdin живого процесса.
        Возвращает True если записано, False если stdin недоступен."""
        proc = self.process
        if proc.stdin is None:
            return False
        envelope = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": text}],
            },
        }
        line = (json.dumps(envelope, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            proc.stdin.write(line)
            await proc.stdin.drain()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError, RuntimeError, ValueError):
            return False


class ProcessManager:
    """Manages concurrent claude CLI processes with stdout streaming."""

    def __init__(
        self,
        settings,
        db,
        projects,
        env_resolver: Callable[[], dict[str, str]] | None = None,
    ):
        self.settings = settings
        self.db = db
        self.projects = projects
        self.running: dict[str, RunningSession] = {}  # composite key: '{slug}:{agent}' or 'cmd:{name}'
        self.max_concurrent = getattr(settings, "max_concurrent", 2)
        self.learning_notes_dir = getattr(settings, "learning_notes_dir", None)
        self.session_logs_dir = getattr(settings, "session_logs_dir", "data/session_logs")
        self.env_resolver = env_resolver
        # Pока есть хотя бы одна running-сессия — Windows не даёт системе уйти
        # в Modern Standby (иначе дочерние Claude-процессы умирают, см. инцидент
        # 05.05 — машина уснула в 06:53, каскад умер в 07:03).
        self.keep_awake = KeepAwake()

    def _allocate_log_path(self, session_id: str) -> str | None:
        """Compute a fresh log file path for a session, creating the date dir.
        Returns the absolute path or None if the directory can't be created."""
        if not session_id:
            return None
        try:
            base = Path(self.session_logs_dir)
            date_dir = base / time.strftime("%Y-%m-%d")
            date_dir.mkdir(parents=True, exist_ok=True)
            return str((date_dir / f"{session_id}.log").resolve())
        except OSError as e:
            log.warning("session_log dir create failed: %s", e)
            return None

    def _build_env(
        self,
        env_overrides: dict[str, str] | None = None,
        *,
        include_resolved: bool = True,
    ) -> dict[str, str]:
        env = os.environ.copy()
        if include_resolved and self.env_resolver:
            try:
                env.update(self.env_resolver() or {})
            except Exception as e:
                log.warning("Failed to resolve process env overrides: %s", e)
        if env_overrides:
            env.update(env_overrides)
        return env

    async def start_session(
        self,
        project,
        *,
        agent_name: str,
        claude_path: str,
        working_dir: str,
        model: str = "sonnet",
        max_turns: int = 25,
        timeout_minutes: int = 20,
        self_study_command: str = "/self-study",
        extra_prompt: str = "",
        env_overrides: dict[str, str] | None = None,
    ) -> str:
        """Start a claude CLI session for the given agent. Returns session_id."""
        key = f"{project.slug}:{agent_name}"
        if key in self.running:
            raise RuntimeError(f"Agent {agent_name} is already running for {project.slug}")
        if len(self.running) >= self.max_concurrent:
            raise RuntimeError(
                f"Max concurrent sessions ({self.max_concurrent}) reached"
            )

        # Pre-create DB session so we own its lifecycle
        db_session_id: str | None = None
        if self.db is not None:
            try:
                db_session_id = await self.db.create_session(project.id, agent_name, model)
            except Exception as e:
                log.warning("Failed to pre-create DB session for %s: %s", key, e)

        session_id = db_session_id or str(uuid4())

        prompt = f"{self_study_command} {agent_name}"
        if extra_prompt:
            prompt = f"{prompt}\n\n{extra_prompt}"

        resolved_path = _resolve_claude_path(claude_path)

        cmd = [
            resolved_path,
            "-p",
            prompt,
            "--model", model,
            *_BYPASS_PERMISSION_FLAGS,
            "--max-turns", str(max_turns),
            "--output-format", "stream-json",
            "--verbose",
        ]

        log.info("Starting session %s for %s: %s", session_id, key, " ".join(cmd))

        env = self._build_env(env_overrides)
        if db_session_id:
            env["LEARNING_SESSION_ID"] = db_session_id
        env["LEARNING_AGENT_NAME"] = agent_name
        env["LEARNING_PROJECT_SLUG"] = project.slug
        env["LEARNING_PROJECT_ID"] = str(project.id)

        try:
            process = await create_subprocess_exec_compat(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=working_dir,
                # Pass empty stdin so claude doesn't wait for input
                stdin=asyncio.subprocess.DEVNULL,
                env=env,
                limit=STDOUT_BUFFER_LIMIT,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"Claude CLI not found at '{claude_path}'. "
                f"Check Settings → Claude Path."
            )
        except OSError as e:
            raise RuntimeError(f"Failed to start Claude CLI: {e}")

        session = RunningSession(
            session_id=session_id,
            agent_name=agent_name,
            project_id=project.id,
            project_slug=project.slug,
            process=process,
        )
        session.key = key
        session.log_path = self._allocate_log_path(session_id)

        self.running[key] = session
        self.keep_awake.acquire()

        # Start stdout reader and watchdog
        session._reader_task = asyncio.create_task(
            self._read_stdout(session), name=f"reader-{key}"
        )
        session._watchdog_task = asyncio.create_task(
            self._watchdog(session, timeout_minutes), name=f"watchdog-{key}"
        )

        return session_id

    async def start_command(
        self,
        project,
        *,
        command_name: str,
        prompt: str,
        claude_path: str,
        working_dir: str | None = None,
        model: str = "sonnet",
        max_turns: int = 25,
        timeout_minutes: int = 30,
        env_overrides: dict[str, str] | None = None,
        session_id: str | None = None,
        resume_session_id: str | None = None,
        interactive_stdin: bool = False,
    ) -> str:
        """Start a claude CLI command/task (not a self-study session). Returns session_id.

        Uses a composite key 'cmd:{project.slug}:{command_name}' in self.running so
        the same command can run concurrently for different projects.
        """
        key = f"cmd:{project.slug}:{command_name}"
        if key in self.running:
            raise RuntimeError(
                f"Command {command_name} is already running for project {project.slug}"
            )
        if working_dir is None:
            working_dir = project.working_dir

        # Pre-create DB session so we own its lifecycle (commands are visible in
        # the sessions list with agent_name = composite key).
        db_session_id: str | None = None
        if self.db is not None and resume_session_id is None and session_id is None:
            try:
                db_session_id = await self.db.create_session(project.id, key, model)
            except Exception as e:
                log.warning("Failed to pre-create DB session for %s: %s", key, e)

        # session_id передаём в CLI как --session-id, чтобы потом дёргать --resume.
        # Если задан resume_session_id — это «второй ход» в существующей сессии.
        session_id = resume_session_id or session_id or db_session_id or str(uuid4())

        resolved_path = _resolve_claude_path(claude_path)

        # При interactive_stdin=True ни в коем случае не передаём prompt через
        # -p <prompt>: Claude CLI с --input-format stream-json игнорирует
        # позиционный prompt и ждёт ввод через stdin. Если оставить и -p, и
        # stream-json — процесс висит вечно (зафиксировано на каскаде
        # forecast-editor/dashboard 05.05). Поэтому для interactive-режима
        # оставляем только флаг --print (он же -p без аргумента) и шлём prompt
        # в stdin сразу после создания процесса.
        cmd = [
            resolved_path,
            "--print",
            "--model", model,
            *_BYPASS_PERMISSION_FLAGS,
            "--max-turns", str(max_turns),
            "--output-format", "stream-json",
            "--verbose",
        ]
        if interactive_stdin:
            cmd += ["--input-format", "stream-json"]
        else:
            # Non-interactive: prompt передаётся как позиционный аргумент.
            cmd.append(prompt)
        if resume_session_id:
            cmd += ["--resume", resume_session_id]
        else:
            cmd += ["--session-id", session_id]

        log.info("Starting command %s: %s", command_name, " ".join(cmd[:6]))

        # Build env including the LEARNING_* hooks so slash-commands spawned
        # via start_command can report back to /api/session/finish exactly like
        # /self-study does.
        env = self._build_env(env_overrides)
        if db_session_id:
            env["LEARNING_SESSION_ID"] = db_session_id
        env["LEARNING_AGENT_NAME"] = key
        env["LEARNING_PROJECT_SLUG"] = project.slug
        env["LEARNING_PROJECT_ID"] = str(project.id)

        try:
            process = await create_subprocess_exec_compat(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=working_dir,
                stdin=(asyncio.subprocess.PIPE if interactive_stdin else asyncio.subprocess.DEVNULL),
                env=env,
                limit=STDOUT_BUFFER_LIMIT,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"Claude CLI not found at '{claude_path}'. "
                f"Check Settings → Claude Path."
            )
        except OSError as e:
            raise RuntimeError(f"Failed to start Claude CLI: {e}")

        session = RunningSession(
            session_id=session_id,
            agent_name=key,
            project_id=project.id,
            project_slug=project.slug,
            process=process,
        )
        session.key = key
        session.log_path = self._allocate_log_path(session_id)

        self.running[key] = session
        self.keep_awake.acquire()

        # В interactive-режиме prompt не доехал в argv — отправляем его сейчас
        # через stdin как первое user-message. resume-сессия не получает prompt
        # повторно (caller сам решит, нужно ли что-то слать).
        if interactive_stdin and prompt and not resume_session_id:
            ok = await session.send_user_message(prompt)
            if not ok:
                log.warning(
                    "Failed to send initial prompt to interactive session %s",
                    session_id,
                )

        session._reader_task = asyncio.create_task(
            self._read_stdout(session), name=f"reader-{key}"
        )
        session._watchdog_task = asyncio.create_task(
            self._watchdog(session, timeout_minutes), name=f"watchdog-{key}"
        )

        return session_id

    async def start_raw_command(
        self,
        project,
        *,
        command_name: str,
        argv: list[str],
        working_dir: str | None = None,
        timeout_minutes: int = 30,
        env_overrides: dict[str, str] | None = None,
    ) -> str:
        """Start an arbitrary CLI command and stream its stdout.

        Composite key: 'cmd:{project.slug}:{command_name}'.
        """
        key = f"cmd:{project.slug}:{command_name}"
        if key in self.running:
            raise RuntimeError(
                f"Command {command_name} is already running for project {project.slug}"
            )
        if not argv:
            raise RuntimeError("Empty command argv")
        if working_dir is None:
            working_dir = project.working_dir

        session_id = str(uuid4())
        log.info("Starting raw command %s: %s", command_name, " ".join(argv[:8]))

        try:
            process = await create_subprocess_exec_compat(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=working_dir,
                stdin=asyncio.subprocess.DEVNULL,
                env=self._build_env(env_overrides, include_resolved=False),
                limit=STDOUT_BUFFER_LIMIT,
            )
        except FileNotFoundError:
            raise RuntimeError(f"Executable not found: {argv[0]}")
        except OSError as e:
            raise RuntimeError(f"Failed to start command: {e}")

        session = RunningSession(
            session_id=session_id,
            agent_name=key,
            project_id=project.id,
            project_slug=project.slug,
            process=process,
        )
        session.key = key
        self.running[key] = session
        self.keep_awake.acquire()
        session._reader_task = asyncio.create_task(
            self._read_stdout(session), name=f"reader-{key}"
        )
        session._watchdog_task = asyncio.create_task(
            self._watchdog(session, timeout_minutes), name=f"watchdog-{key}"
        )
        return session_id

    def _parse_stream_json(self, raw_line: str) -> list[str]:
        """Parse a stream-json line and return human-readable lines for display."""
        try:
            event = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            # Not JSON — pass through as-is
            return [raw_line] if raw_line.strip() else []

        etype = event.get("type", "")
        subtype = event.get("subtype", "")
        lines: list[str] = []

        if etype == "system" and subtype == "init":
            model = event.get("model", "unknown")
            lines.append(f"[system] Session initialized, model: {model}")

        elif etype == "assistant":
            msg = event.get("message", {})
            for block in msg.get("content", []):
                btype = block.get("type", "")
                if btype == "text":
                    text = block.get("text", "")
                    for text_line in text.splitlines():
                        lines.append(text_line)
                elif btype == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    # Show a compact summary of the tool call
                    if tool_name == "Bash":
                        cmd = tool_input.get("command", "")
                        lines.append(f"[tool] Bash: {cmd[:200]}")
                    elif tool_name == "Read":
                        path = tool_input.get("file_path", "")
                        lines.append(f"[tool] Read: {path}")
                    elif tool_name in ("Edit", "Write"):
                        path = tool_input.get("file_path", "")
                        lines.append(f"[tool] {tool_name}: {path}")
                    elif tool_name == "Grep":
                        pattern = tool_input.get("pattern", "")
                        lines.append(f"[tool] Grep: {pattern}")
                    elif tool_name == "Glob":
                        pattern = tool_input.get("pattern", "")
                        lines.append(f"[tool] Glob: {pattern}")
                    elif tool_name == "TodoWrite":
                        lines.append(f"[tool] TodoWrite")
                    elif tool_name == "Skill":
                        skill = tool_input.get("skill", "")
                        lines.append(f"[tool] Skill: {skill}")
                    elif tool_name in ("Agent", "spawn_agent", "SpawnAgent"):
                        desc = tool_input.get("description", "")
                        agent_type = (
                            tool_input.get("subagent_type")
                            or tool_input.get("agent_type")
                            or tool_input.get("agent_role")
                            or ""
                        )
                        if agent_type:
                            lines.append(f'[tool] Agent: subagent_type="{agent_type}"')
                        elif desc:
                            lines.append(f"[tool] Agent: {desc}")
                        else:
                            lines.append("[tool] Agent")
                    else:
                        lines.append(f"[tool] {tool_name}")

        elif etype == "tool_result":
            # Optionally show truncated tool output
            content = event.get("content", "")
            if isinstance(content, str) and content.strip():
                preview = content[:300].replace("\n", " ")
                lines.append(f"  → {preview}")

        elif etype == "result":
            status = subtype or event.get("stop_reason", "")
            duration = event.get("duration_ms", 0)
            cost = event.get("total_cost_usd", 0)
            lines.append(
                f"[done] status={status} duration={duration}ms cost=${cost:.4f}"
            )

        return lines

    async def _read_stdout(self, session: RunningSession) -> None:
        """Read stdout line by line, parse stream-json, and broadcast."""
        assert session.process.stdout is not None
        stdout = session.process.stdout

        def _emit(line: str) -> None:
            session.output_lines.append(line)
            if len(session.output_lines) > RING_BUFFER_SIZE:
                session.output_lines.pop(0)
            if session.log_path:
                try:
                    with open(session.log_path, "a", encoding="utf-8") as lf:
                        lf.write(line + "\n")
                except OSError as e:
                    log.warning(
                        "session log write failed for %s: %s",
                        session.key or session.session_id, e,
                    )
                    session.log_path = None  # stop retrying for this session
            dead_queues = []
            for q in session.subscribers:
                try:
                    q.put_nowait(line)
                except asyncio.QueueFull:
                    dead_queues.append(q)
            for q in dead_queues:
                session.subscribers.remove(q)

        try:
            while True:
                try:
                    line_bytes = await stdout.readline()
                except asyncio.LimitOverrunError as e:
                    # Слишком длинная строка stream-json (assistant-блок > limit).
                    # Выкачиваем её до конца разделителя, чтобы не зациклиться,
                    # помечаем потерю в логе терминала и продолжаем читать.
                    try:
                        await stdout.readexactly(e.consumed)
                        await stdout.readuntil(b"\n")
                    except asyncio.IncompleteReadError:
                        # EOF посреди слишком длинной строки — нечего больше читать.
                        break
                    log.warning(
                        "stdout reader: oversized line dropped for %s (>%d bytes)",
                        session.agent_name, STDOUT_BUFFER_LIMIT,
                    )
                    _emit(
                        f"[warn] пропущена слишком длинная строка stream-json "
                        f"(> {STDOUT_BUFFER_LIMIT // (1024 * 1024)} MB)"
                    )
                    continue

                if not line_bytes:
                    break
                # Любая прилетевшая строка — признак, что процесс жив:
                # обновляем heartbeat для silence-watchdog'а.
                session.last_stdout_at = time.time()
                raw = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")
                if not raw:
                    continue

                for line in self._parse_stream_json(raw):
                    _emit(line)
        except Exception as e:
            log.error("stdout reader error for %s: %s", session.agent_name, e)
        finally:
            # Wait briefly for the child to actually exit so we can record
            # its exit code as the last line in the log — that's the single
            # most useful diagnostic when claude dies mid-run (0=clean,
            # 130=Ctrl+C, 137=SIGKILL, 1-2=internal error, etc).
            exit_code: int | None = None
            try:
                exit_code = await asyncio.wait_for(
                    session.process.wait(), timeout=2.0,
                )
            except (asyncio.TimeoutError, Exception):
                exit_code = session.process.returncode
            if exit_code is not None:
                hint = _EXIT_CODE_HINTS.get(exit_code, "")
                tag = f"[exit] code={exit_code}" + (f" — {hint}" if hint else "")
                _emit(tag)
            # Process finished — notify subscribers with sentinel
            for q in session.subscribers:
                try:
                    q.put_nowait(None)  # None = stream ended
                except asyncio.QueueFull:
                    pass
            await self._cleanup(session, exit_code=exit_code)

    async def _watchdog(self, session: RunningSession, timeout_minutes: int) -> None:
        """Kill process after `timeout_minutes` of stdout silence.

        Семантика «макс. молчания», а не «макс. жизни»: пока CLI стримит
        что угодно (assistant, tool_use, tool_result subagent'а) — процесс
        живой. Убиваем только если ничего не приходило `timeout_minutes`.
        Если процесс ждёт ответа на AskUserQuestion (есть pending в
        orchestrator_questions) — это не молчание, а валидное состояние,
        счётчик тишины сбрасывается.
        """
        timeout_sec = timeout_minutes * 60
        # Шаг проверки: либо минута, либо весь таймаут (чтобы маленькие
        # таймауты для тестов отрабатывали моментально).
        step = min(60.0, timeout_sec)
        try:
            while True:
                await asyncio.sleep(step)
                if await self._has_pending_question(session):
                    session.last_stdout_at = time.time()
                    continue
                idle = time.time() - session.last_stdout_at
                if idle >= timeout_sec:
                    log.warning(
                        "Session %s for %s silent for %.0fs (>%dm) — killing",
                        session.session_id, session.agent_name, idle, timeout_minutes,
                    )
                    await self._kill_process(session)
                    return
        except asyncio.CancelledError:
            pass  # Normal — session finished before timeout

    async def _has_pending_question(self, session: RunningSession) -> bool:
        """Best-effort: проверяем есть ли pending вопросы для этой сессии.
        Грубо — любой pending в БД считаем «своим». Точная привязка
        session ↔ run_id не сохранена в RunningSession, и нам это
        достаточно: ложно-позитивный исход (не убивать когда мог бы)
        безопаснее, чем ложно-негативный (убить ждущую сессию)."""
        if self.db is None:
            return False
        try:
            rows = await self.db.fetch_all(
                "SELECT 1 FROM orchestrator_questions WHERE status='pending' LIMIT 1",
                (),
            )
            return bool(rows)
        except Exception as e:
            log.warning("_has_pending_question failed: %s", e)
            return False

    async def _kill_process(self, session: RunningSession) -> None:
        """Terminate then kill the process tree.

        Windows note: shutil.which("claude") resolves to claude.CMD, so Popen
        wraps it in cmd.exe /c — Popen.pid is the cmd.exe wrapper, not the
        actual claude.exe child. proc.terminate() kills only cmd.exe, leaving
        claude.exe orphaned but still holding our stdout pipe → _read_stdout
        hangs forever and pm.running never cleans up. taskkill /F /T descends
        the tree and kills both, so the pipe closes and cleanup fires.
        """
        proc = session.process
        if proc.returncode is not None:
            return  # Already finished — and PID may be reused, so don't taskkill it
        if sys.platform == "win32" and proc.pid:
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired) as e:
                log.warning("taskkill failed for pid %s: %s", proc.pid, e)
            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pass
            return
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        except ProcessLookupError:
            pass

    async def _cleanup(self, session: RunningSession, exit_code: int | None = None) -> None:
        """Remove session from running dict, cancel watchdog, sync DB.

        When the child process exits we update the session row's status
        immediately (mapped from `exit_code`), so the UI doesn't keep
        showing «В эфире» until the 5-minute reconcile cron catches up.
        """
        key = session.key or session.agent_name
        if session._watchdog_task and not session._watchdog_task.done():
            session._watchdog_task.cancel()
        was_running = self.running.pop(key, None) is not None
        if was_running:
            self.keep_awake.release()
        log.info("Session %s for %s cleaned up (exit_code=%s)",
                 session.session_id, key, exit_code)
        if self.db is None:
            return
        # Map exit code → DB status. 0 = success; anything else = failed.
        # Watchdog kills go through here too (exit code = negative signal
        # on POSIX, large positive on Windows); those count as failed.
        target_status = "success" if exit_code == 0 else "failed"
        # Command-style entries ('cmd:...') don't have agent_learning_sessions
        # rows of their own — the row's `agent_name` IS the composite key.
        # Update by id (which is the claude session_id passed to start_session).
        try:
            await self.db.execute(
                "UPDATE agent_learning_sessions "
                "SET status=?, finished_at=COALESCE(finished_at, ?) "
                "WHERE id=? AND status='running'",
                (target_status, _now_iso(), session.session_id),
            )
        except Exception as e:
            log.warning("update session %s status failed: %s", session.session_id, e)
        # Skip the broader reconcile sweep for cmd:* — they don't live in
        # agent_learning_sessions in the same way; reconcile handles them.
        if key.startswith("cmd:"):
            return
        try:
            active_pairs = [
                (s.project_id, s.agent_name)
                for s in self.running.values()
                if not (s.key or "").startswith("cmd:")
            ]
            closed = await self.db.reconcile_stale_sessions(
                active_pairs=active_pairs,
                learning_notes_dir=self.learning_notes_dir,
                grace_minutes=2,
            )
            if closed:
                log.info("Auto-closed %d DB session(s) after %s exit", closed, key)
        except Exception as e:
            log.warning("reconcile after %s exit failed: %s", key, e)

    async def kill(self, key: str) -> bool:
        """Kill a running session by composite key. Returns True if found."""
        session = self.running.get(key)
        if not session:
            return False
        await self._kill_process(session)
        return True

    # Backward-compat alias (ALC name).
    async def kill_session(self, key: str) -> bool:
        return await self.kill(key)

    def subscribe(self, key: str, catchup_lines: int = 100) -> tuple[list[str], asyncio.Queue] | None:
        """Subscribe to a running session's stdout stream.

        Returns (catchup_lines, queue) or None if session not running.
        The queue yields str lines; None means stream ended.
        """
        session = self.running.get(key)
        if not session:
            return None
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        session.subscribers.append(q)
        # Catch-up: last N lines from buffer
        catchup = session.output_lines[-catchup_lines:]
        return catchup, q

    def get_running_agents(self) -> list[str]:
        """Get list of currently running session keys."""
        return list(self.running.keys())

    def list_running(self) -> dict[str, RunningSession]:
        """Snapshot of running sessions keyed by composite key."""
        return dict(self.running)

    async def stream_subscriber(self, key: str):
        """Subscribe to live stdout lines of a running session.
        Yields strings, or None when the stream ends."""
        sess = self.running.get(key)
        if sess is None:
            return
        q: asyncio.Queue = asyncio.Queue(maxsize=10000)
        sess.subscribers.append(q)
        try:
            while True:
                item = await q.get()
                yield item
                if item is None:
                    break
        finally:
            try:
                sess.subscribers.remove(q)
            except ValueError:
                pass

    def get_session_output(self, key: str) -> list[str] | None:
        """Get full buffered output for a running session."""
        session = self.running.get(key)
        if not session:
            return None
        return list(session.output_lines)

    async def reconcile_stale_sessions(
        self, active_pairs: list[tuple[int, str]]
    ) -> int:
        """Kill any in-memory session whose (project_id, agent_name) is not in active_pairs.

        Skips command-style entries (cmd:*). Returns the number of sessions closed.
        """
        active_keys: set[str] = set()
        for pid, name in active_pairs:
            try:
                proj = await self.projects.get_by_id(pid)
            except Exception as e:
                log.warning("reconcile_stale_sessions: get_by_id(%s) failed: %s", pid, e)
                continue
            if proj:
                active_keys.add(f"{proj.slug}:{name}")
        closed = 0
        for key in list(self.running.keys()):
            if key.startswith("cmd:"):
                continue  # commands aren't tracked by rotation
            if key not in active_keys:
                try:
                    if await self.kill(key):
                        closed += 1
                except Exception as e:
                    log.warning("reconcile_stale_sessions: kill(%s) failed: %s", key, e)
        return closed

    async def kill_all(self) -> None:
        """Kill all running sessions (used at shutdown)."""
        keys = list(self.running.keys())
        for key in keys:
            await self.kill(key)
