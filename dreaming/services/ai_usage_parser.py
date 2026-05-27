"""Incremental JSONL parser for Claude Code session logs.

Reads `~/.claude/projects/**/*.jsonl` (and `subagents/agent-*.jsonl`), extracts
per-message token usage, stores events into `ai_usage_events` keyed on
`message.id`. Per-file ingest state lives in `ai_usage_files` (byte offset).

Dreaming-center variant: each event must belong to a known project (FK
`project_id NOT NULL`). The parser builds a `cwd → project_id` map once per
ingest run from the `projects` table, then skips rows whose `cwd` doesn't
match any project's `working_dir`.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService

log = logging.getLogger(__name__)


# ── file discovery ────────────────────────────────────────────────

def resolve_claude_projects_root(override: str | None = None) -> Path:
    """Return root: explicit override, or default ~/.claude/projects."""
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "projects"


def discover_jsonl_files(root: Path) -> Iterator[tuple[Path, bool, str]]:
    """Yield (path, is_subagent, project_slug) for every JSONL under root.

    Layout:
      root/<slug>/<session-uuid>.jsonl                                  (main)
      root/<slug>/<session-uuid>/subagents/agent-<agent-id>.jsonl       (subagent)
    """
    if not root.exists():
        return
    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue
        slug = project_dir.name
        for jsonl in project_dir.rglob("*.jsonl"):
            is_subagent = jsonl.parent.name == "subagents"
            yield jsonl, is_subagent, slug


def read_agent_name(jsonl_path: Path) -> str | None:
    """For a subagent file `agent-<hash>.jsonl`, read its sibling
    `agent-<hash>.meta.json` and return the `agentType`, or None."""
    meta = jsonl_path.with_name(jsonl_path.stem + ".meta.json")
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = (data.get("agentType") or "").strip() if isinstance(data, dict) else ""
    return name or None


# ── cwd → project_id resolver ─────────────────────────────────────

def _normalize_cwd(cwd: str | None) -> str | None:
    """Normalize a path string for hashable comparison.

    We use Path.resolve() with strict=False to canonicalize separators and
    case (where the OS normalizes case). On Windows this folds drive letter
    case and replaces forward slashes with backslashes.
    """
    if not cwd:
        return None
    try:
        # `resolve()` may touch the FS to expand symlinks; fall back to no-op
        # on missing directories so we still match on string-equality.
        p = Path(cwd)
        try:
            p = p.resolve(strict=False)
        except (OSError, RuntimeError):
            pass
        return str(p).lower() if hasattr(Path(), "drive") and Path(cwd).drive else str(p)
    except Exception:
        return cwd


def _norm_for_match(cwd: str) -> str:
    """Lower-cased absolute string form for hash key. Windows-friendly."""
    try:
        p = Path(cwd)
        try:
            p = p.resolve(strict=False)
        except (OSError, RuntimeError):
            pass
        return str(p).lower()
    except Exception:
        return cwd.lower()


async def build_cwd_to_project_id(db: SqliteDB) -> dict[str, int]:
    """Build a map of normalized working_dir -> project_id.

    Used once per ingest run to avoid N+1 lookups.
    """
    rows = await db.fetch_all("SELECT id, working_dir FROM projects")
    out: dict[str, int] = {}
    for r in rows:
        wd = r["working_dir"]
        if not wd:
            continue
        out[_norm_for_match(wd)] = int(r["id"])
    return out


# ── parsing ────────────────────────────────────────────────────────

def parse_line(
    raw: str,
    *,
    project_slug: str,
    source_file: str,
    source_line: int,
) -> dict[str, Any] | None:
    """Parse a single JSONL line → event row, or None to skip."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parse_obj(
        obj,
        project_slug=project_slug,
        source_file=source_file,
        source_line=source_line,
    )


def parse_obj(
    obj: dict[str, Any],
    *,
    project_slug: str,
    source_file: str,
    source_line: int,
) -> dict[str, Any] | None:
    """Build an event row from an already-parsed JSONL object, or None to skip."""
    t = obj.get("type")
    if t != "assistant":
        return None
    msg = obj.get("message") or {}
    if not isinstance(msg, dict):
        return None

    message_id = msg.get("id")
    if not message_id:
        return None

    usage = msg.get("usage") or {}
    input_t = int(usage.get("input_tokens") or 0)
    output_t = int(usage.get("output_tokens") or 0)
    cache_read_t = int(usage.get("cache_read_input_tokens") or 0)
    cache_creation_t = int(usage.get("cache_creation_input_tokens") or 0)
    if not (input_t or output_t or cache_read_t or cache_creation_t):
        return None

    ts = obj.get("timestamp") or ""
    ts_date = ts[:10] if len(ts) >= 10 else ""
    if not ts_date:
        return None

    return {
        "message_id": message_id,
        "ts": ts,
        "ts_date": ts_date,
        "session_id": obj.get("sessionId") or "",
        "project_slug": project_slug,
        "project_cwd": obj.get("cwd"),
        "git_branch": obj.get("gitBranch"),
        "model": msg.get("model"),
        "is_sidechain": 1 if obj.get("isSidechain") else 0,
        "agent_id": obj.get("agentId"),
        "agent_name": None,
        "input_tokens": input_t,
        "output_tokens": output_t,
        "cache_read_tokens": cache_read_t,
        "cache_creation_tokens": cache_creation_t,
        "source_file": source_file,
        "source_line": source_line,
    }


def extract_skill_invocations(
    obj: dict[str, Any],
    *,
    source_file: str,
) -> list[dict[str, Any]]:
    """Return one row per distinct `Skill` tool_use block in an assistant message.

    Independent of the usage>0 gate parse_obj applies: skill rows do NOT require
    token usage to be present. `project_id` is attached later by the caller from
    the cwd→project map. Multiple Skill calls in one message are de-duped per
    skill name (the PK is (message_id, skill_name))."""
    if obj.get("type") != "assistant":
        return []
    msg = obj.get("message") or {}
    if not isinstance(msg, dict):
        return []
    message_id = msg.get("id")
    content = msg.get("content")
    if not message_id or not isinstance(content, list):
        return []
    ts = obj.get("timestamp") or ""
    ts_date = ts[:10] if len(ts) >= 10 else ""
    if not ts_date:
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in content:
        if not isinstance(c, dict):
            continue
        if c.get("type") != "tool_use" or c.get("name") != "Skill":
            continue
        inp = c.get("input")
        skill = (inp.get("skill") or "").strip() if isinstance(inp, dict) else ""
        if not skill or skill in seen:
            continue
        seen.add(skill)
        out.append({
            "message_id": message_id,
            "skill_name": skill,
            "ts": ts,
            "ts_date": ts_date,
            "session_id": obj.get("sessionId") or "",
            "is_sidechain": 1 if obj.get("isSidechain") else 0,
            "model": msg.get("model"),
            "source_file": source_file,
        })
    return out


# ── incremental reader ─────────────────────────────────────────────

def read_new_lines(path: Path, offset: int, size: int) -> tuple[list[bytes], int]:
    """Read bytes from `offset` to `size`, return (complete_lines, new_offset).

    Only lines terminated by '\\n' are considered complete; the trailing tail
    without a newline is left for the next tick (offset stays before it).
    """
    if offset >= size:
        return [], offset
    with path.open("rb") as f:
        f.seek(offset)
        chunk = f.read(size - offset)
    if not chunk:
        return [], offset

    last_nl = chunk.rfind(b"\n")
    if last_nl < 0:
        return [], offset  # no complete line yet
    complete = chunk[: last_nl + 1]
    lines = complete.split(b"\n")[:-1]  # last split is "" after trailing \n
    return lines, offset + last_nl + 1


# ── DB helpers (inline; we don't depend on ALC's full db.py port) ──

async def _list_known_files(db: SqliteDB) -> dict[str, dict[str, Any]]:
    rows = await db.fetch_all("SELECT * FROM ai_usage_files")
    return {r["path"]: dict(r) for r in rows}


async def _insert_events(db: SqliteDB, project_id: int, rows: list[dict[str, Any]]) -> int:
    """Batch INSERT OR IGNORE into ai_usage_events. Returns inserted count."""
    if not rows or db._conn is None:
        return 0
    before = db._conn.total_changes
    await db._conn.executemany(
        "INSERT OR IGNORE INTO ai_usage_events "
        "(message_id, project_id, ts, ts_date, session_id, project_slug, project_cwd, "
        "git_branch, model, is_sidechain, agent_id, agent_name, input_tokens, output_tokens, "
        "cache_read_tokens, cache_creation_tokens, source_file, source_line) "
        "VALUES (:message_id, :project_id, :ts, :ts_date, :session_id, :project_slug, "
        ":project_cwd, :git_branch, :model, :is_sidechain, :agent_id, :agent_name, :input_tokens, "
        ":output_tokens, :cache_read_tokens, :cache_creation_tokens, :source_file, :source_line)",
        [{**r, "project_id": project_id} for r in rows],
    )
    await db._conn.commit()
    return db._conn.total_changes - before


async def _insert_skill_invocations(
    db: SqliteDB, project_id: int, rows: list[dict[str, Any]]
) -> int:
    """Batch INSERT OR IGNORE into ai_skill_invocations. Returns inserted count."""
    if not rows or db._conn is None:
        return 0
    before = db._conn.total_changes
    await db._conn.executemany(
        "INSERT OR IGNORE INTO ai_skill_invocations "
        "(message_id, skill_name, project_id, ts, ts_date, session_id, "
        "is_sidechain, model, source_file) "
        "VALUES (:message_id, :skill_name, :project_id, :ts, :ts_date, "
        ":session_id, :is_sidechain, :model, :source_file)",
        [{**r, "project_id": project_id} for r in rows],
    )
    await db._conn.commit()
    return db._conn.total_changes - before


async def _upsert_file(
    db: SqliteDB,
    *,
    project_id: int,
    path: str,
    project_slug: str,
    is_subagent: bool,
    byte_offset: int,
    file_size: int,
    mtime: float,
    lines_parsed: int,
    events_inserted: int,
    parse_errors: int,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO ai_usage_files (project_id, path, project_slug, is_subagent, "
        "byte_offset, file_size, mtime, lines_parsed, events_inserted, parse_errors, "
        "is_missing, last_scanned_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?) "
        "ON CONFLICT(project_id, path) DO UPDATE SET "
        "project_slug=excluded.project_slug, is_subagent=excluded.is_subagent, "
        "byte_offset=excluded.byte_offset, file_size=excluded.file_size, mtime=excluded.mtime, "
        "lines_parsed=ai_usage_files.lines_parsed+excluded.lines_parsed, "
        "events_inserted=ai_usage_files.events_inserted+excluded.events_inserted, "
        "parse_errors=ai_usage_files.parse_errors+excluded.parse_errors, "
        "is_missing=0, last_scanned_at=excluded.last_scanned_at",
        (project_id, path, project_slug, 1 if is_subagent else 0, byte_offset,
         file_size, mtime, lines_parsed, events_inserted, parse_errors, now),
    )


async def _mark_missing(db: SqliteDB, path: str) -> None:
    await db.execute(
        "UPDATE ai_usage_files SET is_missing=1 WHERE path=?", (path,)
    )


# ── main ingest loop ───────────────────────────────────────────────

async def ingest_ai_usage(
    db: SqliteDB,
    projects: ProjectsService,
    claude_projects_dir: str | None = None,
    max_files: int = 1000,
    batch_size: int = 500,
) -> dict:
    """Walk the Claude projects root, ingest unread JSONL tails into
    `ai_usage_events`. Rows whose cwd doesn't match any project's
    working_dir are skipped.

    Returns:
        {'files': N, 'events_inserted': N, 'events_skipped': N, 'errors': N}
    """
    started = time.monotonic()
    result = {
        "files": 0,
        "events_inserted": 0,
        "skills_inserted": 0,
        "events_skipped": 0,
        "errors": 0,
        "duration_ms": 0,
    }

    try:
        cwd_to_pid = await build_cwd_to_project_id(db)
        if not cwd_to_pid:
            log.info("ai_usage_ingest: no projects in DB, nothing to ingest")
            result["duration_ms"] = int((time.monotonic() - started) * 1000)
            return result

        root = resolve_claude_projects_root(claude_projects_dir)
        known = await _list_known_files(db)
        on_disk: set[str] = set()

        files = list(discover_jsonl_files(root))
        if max_files and len(files) > max_files:
            log.info("ai_usage_ingest: truncating %d files to %d", len(files), max_files)
            files = files[:max_files]

        for jsonl, is_subagent, slug in files:
            result["files"] += 1
            path_str = str(jsonl)
            on_disk.add(path_str)
            agent_name = read_agent_name(jsonl) if is_subagent else None
            try:
                st = jsonl.stat()
            except OSError as e:
                log.warning("ai_usage_ingest stat failed: %s: %s", path_str, e)
                result["errors"] += 1
                continue

            stored = known.get(path_str)
            stored_offset = int(stored["byte_offset"]) if stored else 0
            stored_size = int(stored["file_size"]) if stored else 0

            # Truncation / rotation — start over (INSERT OR IGNORE protects dups)
            if st.st_size < stored_size:
                stored_offset = 0

            if st.st_size == stored_size and stored is not None:
                continue

            try:
                lines, new_offset = read_new_lines(jsonl, stored_offset, st.st_size)
            except OSError as e:
                log.warning("ai_usage_ingest read failed: %s: %s", path_str, e)
                result["errors"] += 1
                continue

            # Group rows by resolved project_id; skip those that don't map.
            per_project_rows: dict[int, list[dict[str, Any]]] = {}
            per_project_skills: dict[int, list[dict[str, Any]]] = {}
            errors_in_file = 0
            skipped_rows = 0
            file_project_id = stored["project_id"] if stored else None
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                try:
                    text = line.decode("utf-8", errors="replace")
                except Exception:
                    errors_in_file += 1
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    if text.strip() and not text.startswith("{"):
                        errors_in_file += 1
                    continue

                # Same pid resolution as before — the original resolved from
                # row["project_cwd"], which parse_obj sets to obj["cwd"]; this is
                # equivalent, just hoisted so skill rows can reuse it.
                cwd = obj.get("cwd")
                pid = cwd_to_pid.get(_norm_for_match(cwd)) if cwd else None

                row = parse_obj(
                    obj, project_slug=slug, source_file=path_str, source_line=i,
                )
                if row is not None:
                    if pid is None:
                        skipped_rows += 1
                    else:
                        row["agent_name"] = agent_name
                        per_project_rows.setdefault(pid, []).append(row)
                        if file_project_id is None:
                            file_project_id = pid

                skill_rows = extract_skill_invocations(obj, source_file=path_str)
                if skill_rows and pid is not None:
                    per_project_skills.setdefault(pid, []).extend(skill_rows)

            inserted_here = 0
            for pid, prows in per_project_rows.items():
                for start in range(0, len(prows), batch_size):
                    inserted_here += await _insert_events(
                        db, pid, prows[start:start + batch_size]
                    )

            skills_here = 0
            for pid, srows in per_project_skills.items():
                for start in range(0, len(srows), batch_size):
                    skills_here += await _insert_skill_invocations(
                        db, pid, srows[start:start + batch_size]
                    )

            # Pick a project_id for the ai_usage_files row. Prefer the most
            # recently observed one; fall back to whatever we've stored before;
            # if nothing matched, skip writing the row (we have no FK target).
            file_pid: int | None = file_project_id
            if per_project_rows:
                # Use whichever project contributed the most rows in this batch
                file_pid = max(per_project_rows.items(), key=lambda kv: len(kv[1]))[0]

            if file_pid is None:
                # File never matched any project — don't track its offset.
                result["events_skipped"] += skipped_rows
                result["errors"] += errors_in_file
                continue

            await _upsert_file(
                db,
                project_id=file_pid,
                path=path_str,
                project_slug=slug,
                is_subagent=is_subagent,
                byte_offset=new_offset,
                file_size=st.st_size,
                mtime=st.st_mtime,
                lines_parsed=len(lines),
                events_inserted=inserted_here,
                parse_errors=errors_in_file,
            )

            result["events_inserted"] += inserted_here
            result["skills_inserted"] += skills_here
            result["events_skipped"] += skipped_rows
            result["errors"] += errors_in_file

        # Mark vanished files
        for missing_path in set(known) - on_disk:
            try:
                await _mark_missing(db, missing_path)
            except Exception as e:
                log.warning("mark_missing failed for %s: %s", missing_path, e)

    except Exception as e:
        log.exception("ai_usage_ingest failed")
        result["errors"] += 1
        result["error_message"] = f"{type(e).__name__}: {e}"

    result["duration_ms"] = int((time.monotonic() - started) * 1000)
    log.info(
        "ai_usage_ingest: files=%d inserted=%d skipped=%d errors=%d in %dms",
        result["files"], result["events_inserted"], result["events_skipped"],
        result["errors"], result["duration_ms"],
    )
    return result


async def backfill_skill_agent_stats(
    db: SqliteDB,
    projects: ProjectsService,
    claude_projects_dir: str | None = None,
    max_files: int = 20000,
) -> dict:
    """One-time re-scan from offset 0 that backfills `agent_name` on existing
    ai_usage_events rows and fills ai_skill_invocations for historical files.

    The incremental ingest tracks byte offsets and skips unchanged files, and
    INSERT OR IGNORE won't update the new column on existing rows — so history
    needs this dedicated pass. Idempotent: the UPDATE is deterministic and skill
    inserts use INSERT OR IGNORE.

    Two-phase approach:
    1. Walk discovered on-disk JSONL files for skill invocations.
    2. Query the DB for existing event rows with NULL agent_name whose
       source_file has a sibling .meta.json — covers files already tracked
       in the DB but no longer present on disk."""
    result = {"files": 0, "agent_files": 0, "skills_inserted": 0, "errors": 0}
    try:
        cwd_to_pid = await build_cwd_to_project_id(db)
        if not cwd_to_pid:
            return result

        # ── Phase 1: walk on-disk files for skill invocations ────────────
        root = resolve_claude_projects_root(claude_projects_dir)
        files = list(discover_jsonl_files(root))
        if max_files and len(files) > max_files:
            files = files[:max_files]

        for jsonl, is_subagent, slug in files:
            result["files"] += 1
            path_str = str(jsonl)

            if is_subagent:
                agent_name = read_agent_name(jsonl)
                if agent_name:
                    try:
                        await db.execute(
                            "UPDATE ai_usage_events SET agent_name=? "
                            "WHERE source_file=? AND (agent_name IS NULL OR agent_name='')",
                            (agent_name, path_str),
                        )
                        result["agent_files"] += 1
                    except Exception:
                        result["errors"] += 1

            try:
                per_pid: dict[int, list[dict[str, Any]]] = {}
                with jsonl.open(encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if '"Skill"' not in line:
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        srows = extract_skill_invocations(obj, source_file=path_str)
                        if not srows:
                            continue
                        cwd = obj.get("cwd")
                        pid = cwd_to_pid.get(_norm_for_match(cwd)) if cwd else None
                        if pid is None:
                            continue
                        per_pid.setdefault(pid, []).extend(srows)
                for pid, srows in per_pid.items():
                    result["skills_inserted"] += await _insert_skill_invocations(
                        db, pid, srows
                    )
            except OSError:
                result["errors"] += 1

        # ── Phase 2: backfill agent_name from DB rows not yet updated ────
        # Query distinct source_file paths that still have NULL agent_name.
        # For each, read its sibling .meta.json if it exists.
        try:
            null_rows = await db.fetch_all(
                "SELECT DISTINCT source_file FROM ai_usage_events "
                "WHERE agent_name IS NULL OR agent_name=''"
            )
            for r in null_rows:
                src = r["source_file"]
                if not src:
                    continue
                jsonl_path = Path(src)
                # Only process subagent files (in a 'subagents' directory)
                if jsonl_path.parent.name != "subagents":
                    continue
                agent_name = read_agent_name(jsonl_path)
                if not agent_name:
                    continue
                try:
                    await db.execute(
                        "UPDATE ai_usage_events SET agent_name=? "
                        "WHERE source_file=? AND (agent_name IS NULL OR agent_name='')",
                        (agent_name, src),
                    )
                    result["agent_files"] += 1
                except Exception:
                    result["errors"] += 1
        except Exception:
            log.exception("backfill_skill_agent_stats phase-2 failed")
            result["errors"] += 1

    except Exception:
        log.exception("backfill_skill_agent_stats failed")
        result["errors"] += 1
    log.info("backfill_skill_agent_stats: %s", result)
    return result
