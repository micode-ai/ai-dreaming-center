"""Tail-watcher for Claude CLI session .jsonl files.

Claude stores each CLI session under
    ~/.claude/projects/<workdir-encoded>/<session_id>.jsonl
appending new turns (assistant/user/tool_use) line by line. This module:
    1) resolves a session file path from a working_dir + session_id,
    2) runs a background coroutine that reads new lines incrementally and
       persists them into orchestrator_messages / orchestrator_events via the
       OrchestrationHub so the orchestration UI can render real-time activity.

Deduplication is done by Claude's per-line `uuid` field — messages with a uuid
already seen are skipped. Live tail subscribes to the file via mtime/size polling
(no inotify on Windows). Subagent jsonl files (which close once Claude returns
the tool_result) can opt into idle-finalize via `idle_finalize_after`.

This is a port of agent-learning-center's claude_session_tail.py adapted to the
leaner ai-dreaming-center OrchestrationHub. Side-effect tracking that depends on
ALC-only DB tables (TTS, artifacts, AskUserQuestion) is intentionally omitted —
those land in later waves once the corresponding tables/methods exist here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dreaming.services.db import SqliteDB
from dreaming.services.orchestration_hub import OrchestrationHub

log = logging.getLogger(__name__)


def encode_workdir(working_dir: str) -> str:
    """Encode an absolute path the same way Claude CLI names its project folder."""
    return "".join(c if c.isalnum() else "-" for c in working_dir or "")


def claude_projects_root(home: Path | None = None) -> Path:
    base = home or Path.home()
    return base / ".claude" / "projects"


def session_file_path(working_dir: str, session_id: str, home: Path | None = None) -> Path:
    return claude_projects_root(home) / encode_workdir(working_dir) / f"{session_id}.jsonl"


def subagents_dir(working_dir: str, session_id: str, home: Path | None = None) -> Path:
    """Subagents folder for a given session.

    Claude CLI places sub-agent sessions under
        ~/.claude/projects/<workdir-encoded>/<session_id>/subagents/

    The folder may not exist if no sub-agents have been spawned yet — that is OK.
    """
    return claude_projects_root(home) / encode_workdir(working_dir) / session_id / "subagents"


def find_session_file(
    working_dir: str,
    session_id: str | None = None,
    home: Path | None = None,
) -> Path | None:
    """Look up a session jsonl by working_dir + optional session_id.

    Returns None if neither the folder nor the named file exists; callers can
    then fall back to mtime-based heuristics.
    """
    folder = claude_projects_root(home) / encode_workdir(working_dir)
    if not folder.exists():
        return None
    if session_id:
        candidate = folder / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
    return None


def find_session_file_by_id(
    session_id: str,
    claude_projects_dir: Path | str | None = None,
) -> Path | None:
    """Locate a session jsonl by session_id alone, regardless of working_dir.

    Walks every project subfolder of ~/.claude/projects looking for
    `<session_id>.jsonl`. Used by backfill where we may not know the working_dir
    encoding (or the run was started from a different cwd than now).
    """
    root = Path(claude_projects_dir) if claude_projects_dir else claude_projects_root()
    if not root.exists():
        return None
    candidate = root.rglob(f"{session_id}.jsonl")
    for path in candidate:
        if path.is_file():
            return path
    return None


def find_recent_session_files(
    working_dir: str,
    limit: int = 10,
    home: Path | None = None,
) -> list[Path]:
    """Recent jsonl files in the workdir, sorted by mtime descending."""
    folder = claude_projects_root(home) / encode_workdir(working_dir)
    if not folder.exists():
        return []
    files = list(folder.glob("*.jsonl"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def find_session_for_goal(
    working_dir: str,
    goal: str,
    after_iso: str | None = None,
    home: Path | None = None,
) -> Path | None:
    """Heuristic for older runs: find a jsonl whose first user prompt contains
    `goal`. `after_iso` is a lower bound on file mtime to avoid picking up a
    stale unrelated session."""
    after_ts = None
    if after_iso:
        try:
            after_ts = datetime.fromisoformat(after_iso.replace("Z", "+00:00")).timestamp()
        except Exception:
            after_ts = None
    needle = (goal or "").strip()
    if not needle:
        return None
    for path in find_recent_session_files(working_dir, limit=30, home=home):
        if after_ts and path.stat().st_mtime + 60 < after_ts:
            continue
        try:
            with path.open(encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    if i > 5:
                        break
                    if needle in line:
                        return path
        except OSError:
            continue
    return None


def _summarize_tool_use(name: str, inp: dict[str, Any]) -> str:
    """Short (~120 char) one-liner for a tool_use block, suitable for chat display."""
    if not isinstance(inp, dict):
        return f"[tool] {name}"
    nl = (name or "").lower()

    def _short(s: Any, limit: int = 120) -> str:
        if s is None:
            return ""
        s = str(s).replace("\n", " ").strip()
        return s if len(s) <= limit else s[: limit - 1] + "…"

    if nl == "bash":
        desc = _short(inp.get("description"), 80)
        cmd = _short(inp.get("command"), 200)
        if desc:
            return f"[Bash] {desc} — `{cmd}`" if cmd else f"[Bash] {desc}"
        return f"[Bash] `{cmd}`" if cmd else "[Bash]"
    if nl == "read":
        path = _short(inp.get("file_path"), 120)
        return f"[Read] {path}" if path else "[Read]"
    if nl == "write":
        path = _short(inp.get("file_path"), 120)
        return f"[Write] {path}" if path else "[Write]"
    if nl in ("edit", "multiedit"):
        path = _short(inp.get("file_path"), 120)
        return f"[{name}] {path}" if path else f"[{name}]"
    if nl == "glob":
        pat = _short(inp.get("pattern"), 120)
        return f"[Glob] {pat}" if pat else "[Glob]"
    if nl == "grep":
        pat = _short(inp.get("pattern"), 120)
        glob = _short(inp.get("glob") or inp.get("path"), 60)
        return f"[Grep] {pat}" + (f" in {glob}" if glob else "")
    if nl == "task":
        sub = _short(inp.get("subagent_type"), 60)
        desc = _short(inp.get("description"), 100)
        return f"[Task → {sub}] {desc}".rstrip(" ]") if sub else f"[Task] {desc}"
    if nl == "todowrite":
        todos = inp.get("todos") or []
        if isinstance(todos, list) and todos:
            return f"[TodoWrite] {len(todos)} item(s)"
        return "[TodoWrite]"
    if nl == "webfetch":
        url = _short(inp.get("url"), 120)
        return f"[WebFetch] {url}" if url else "[WebFetch]"
    if nl == "websearch":
        q = _short(inp.get("query"), 120)
        return f"[WebSearch] {q}" if q else "[WebSearch]"
    if nl.startswith("mcp__"):
        for key in ("query", "q", "pattern", "path", "name", "sql", "text", "prompt", "url"):
            v = inp.get(key)
            if v:
                return f"[{name}] {_short(v, 120)}"
        return f"[{name}]"
    for k, v in inp.items():
        if isinstance(v, str) and v.strip():
            return f"[{name}] {k}={_short(v, 100)}"
    return f"[tool] {name}"


def _extract_text_from_message(msg: dict[str, Any]) -> str:
    """Build a human-readable text from message.content (text/tool_use/tool_result)."""
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        bt = block.get("type")
        if bt == "text":
            text = block.get("text") or ""
            if text:
                parts.append(text)
        elif bt == "tool_use":
            parts.append(_summarize_tool_use(block.get("name") or "tool", block.get("input") or {}))
        elif bt == "tool_result":
            inner = block.get("content")
            if isinstance(inner, list) and inner:
                first = inner[0]
                if isinstance(first, dict) and first.get("type") == "text":
                    snippet = (first.get("text") or "")[:400]
                    if snippet:
                        parts.append(f"[tool_result] {snippet}")
    # Double newline so block-level Markdown (tables, lists) inside text blocks
    # doesn't get fused with surrounding tool summaries.
    return "\n\n".join(parts).strip()


# ── Pure helpers exposed for tests / sub-agent watcher ──────────────────────


_GIT_COMMIT_M_RE = re.compile(
    r"git\s+commit\b[^|;&]*?\s-m\s+(?:\$?'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    return s.replace("\\", "/")


# ── Hub-backed ingest helpers ───────────────────────────────────────────────


async def _hub_project_id(hub: OrchestrationHub, run_id: str) -> int | None:
    """Resolve project_id for a run via the hub. Returns None if the run is missing."""
    run = await hub.get_run(run_id)
    if run is None:
        return None
    try:
        return run["project_id"]
    except (KeyError, TypeError):
        return None


async def _ingest_line(
    hub: OrchestrationHub,
    db: SqliteDB,
    run_id: str,
    node_id: str,
    project_id: int,
    line: str,
    seen: set[str],
) -> int:
    """Parse one stream-json line and append a message + event for it.

    Returns 1 if a row was appended, 0 if skipped (dedup, non-msg type, blank).
    """
    line = line.strip()
    if not line:
        return 0
    try:
        obj = json.loads(line)
    except (ValueError, json.JSONDecodeError):
        return 0
    t = obj.get("type")
    if t not in ("assistant", "user"):
        return 0
    uuid_ = obj.get("uuid")
    if uuid_ and uuid_ in seen:
        return 0
    text = _extract_text_from_message(obj.get("message") or {})
    if not text:
        if uuid_:
            seen.add(uuid_)
        return 0
    author = "assistant" if t == "assistant" else "user"
    kind = "chat" if t == "user" else "reasoning"
    try:
        msg_id = await hub.append_message(
            run_id=run_id,
            node_id=node_id,
            project_id=project_id,
            author=author,
            kind=kind,
            text=text,
        )
    except Exception as e:
        log.warning("append_message failed: %s", e)
        return 0
    if uuid_:
        seen.add(uuid_)
    payload = {
        "run_id": run_id,
        "node_id": node_id,
        "message_id": msg_id,
        "author": author,
        "kind": kind,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await hub.append_event(run_id, "message_added", payload)
    except Exception as e:
        log.warning("append_event failed: %s", e)
    return 1


async def tail_session_file(
    *,
    run_id: str,
    node_id: str,
    project_id: int,
    path: Path,
    hub: OrchestrationHub,
    db: SqliteDB,
    seen_uuids: set[str] | None = None,
    poll_interval: float = 1.0,
    stop_event: asyncio.Event | None = None,
    idle_finalize_after: float | None = None,
) -> int:
    """Background coroutine: read new lines from `path` and emit message_added.

    Returns the number of new messages persisted across the whole call (catchup
    plus live-tail) when the loop terminates (stop_event set or idle finalize).
    """
    seen = seen_uuids if seen_uuids is not None else set()
    last_size = 0
    last_inode: int | None = None
    last_change_at = asyncio.get_event_loop().time()
    appended = 0
    log.info("tail_session_file: attach run=%s node=%s path=%s", run_id, node_id, path)

    # Catchup pass: fix uuids in `seen` so the live loop doesn't redraw history,
    # but still feed lines through `_ingest_line` so any messages seen before
    # the watcher was attached get persisted.
    try:
        if path.exists():
            with path.open(encoding="utf-8", errors="ignore") as f:
                for line in f:
                    appended += await _ingest_line(
                        hub, db, run_id, node_id, project_id, line, seen,
                    )
            stat = path.stat()
            last_size = stat.st_size
            try:
                last_inode = stat.st_ino
            except AttributeError:
                last_inode = None
    except OSError as e:
        log.warning("tail catchup failed for %s: %s", path, e)

    # Live tail loop
    while True:
        if stop_event is not None and stop_event.is_set():
            return appended
        try:
            if not path.exists():
                await asyncio.sleep(poll_interval)
                continue
            stat = path.stat()
            cur_size = stat.st_size
            try:
                cur_inode = stat.st_ino
            except AttributeError:
                cur_inode = None
            if cur_inode is not None and last_inode is not None and cur_inode != last_inode:
                last_size = 0
                last_inode = cur_inode
            if cur_size < last_size:
                last_size = 0
            if cur_size > last_size:
                with path.open(encoding="utf-8", errors="ignore") as f:
                    f.seek(last_size)
                    for line in f:
                        appended += await _ingest_line(
                            hub, db, run_id, node_id, project_id, line, seen,
                        )
                last_size = cur_size
                last_change_at = asyncio.get_event_loop().time()
            elif idle_finalize_after is not None:
                idle = asyncio.get_event_loop().time() - last_change_at
                if idle >= idle_finalize_after:
                    log.info(
                        "tail_session_file: idle %ss → finalize node %s as completed",
                        int(idle), node_id,
                    )
                    try:
                        await hub.update_node_status(node_id, "completed")
                    except Exception as e:
                        log.warning("update_node_status failed: %s", e)
                    return appended
        except OSError as e:
            log.warning("tail io error for %s: %s", path, e)
        await asyncio.sleep(poll_interval)


class ClaudeSessionTail:
    """Object wrapper around `tail_session_file` matching the Wave 3 spec.

    Construction is cheap: the JSONL is not opened until `start()` is awaited.
    `stop()` is idempotent — safe to call multiple times.
    """

    def __init__(self, run_id: str, jsonl_path: str, hub: OrchestrationHub, db: SqliteDB):
        self.run_id = run_id
        self.jsonl_path = Path(jsonl_path)
        self.hub = hub
        self.db = db
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._node_id: str | None = None

    async def _ensure_node(self) -> tuple[str, int]:
        """Create (or reuse the latest orchestrator node for) this run.

        Returns (node_id, project_id). Raises if the run cannot be found.
        """
        run = await self.hub.get_run(self.run_id)
        if run is None:
            raise RuntimeError(f"run {self.run_id} not found")
        project_id = run["project_id"]
        nodes = await self.hub.list_nodes(self.run_id)
        # Prefer an existing orchestrator node — that's where the main session
        # lines belong.
        for n in nodes:
            try:
                role = n["role"]
            except (KeyError, TypeError):
                role = None
            if (role or "").lower() == "orchestrator":
                return n["id"], project_id
        # No orchestrator yet — create one named after the jsonl basename.
        agent_name = self.jsonl_path.stem or "claude"
        node_id = await self.hub.create_node(
            self.run_id, project_id, agent_name=agent_name, role="orchestrator",
        )
        return node_id, project_id

    async def start(self) -> None:
        """Launch the background tail loop. Idempotent — calling twice is a no-op."""
        if self._task is not None:
            return
        self._stop.clear()
        node_id, project_id = await self._ensure_node()
        self._node_id = node_id
        self._task = asyncio.create_task(
            tail_session_file(
                run_id=self.run_id,
                node_id=node_id,
                project_id=project_id,
                path=self.jsonl_path,
                hub=self.hub,
                db=self.db,
                stop_event=self._stop,
            )
        )

    async def stop(self) -> None:
        """Signal the tail loop to exit and await its termination."""
        self._stop.set()
        task, self._task = self._task, None
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception as e:
                log.warning("tail task ended with error: %s", e)
