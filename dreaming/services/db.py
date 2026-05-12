"""SQLite async client for ai-dreaming-center.

Greenfield schema: forks ALC's _SCHEMA verbatim; injects project_id where the
spec requires; new projects + project_settings registries on top.

Wave 0 exposes only generic helpers (`execute`, `fetch_one`, `fetch_all`).
ALC's full db.py has ~50 domain methods (`finish_session`, `set_agent_tier`,
`create_orchestration_run`, `append_orchestration_message`,
`insert_ai_usage_events`, `reconcile_stale_sessions`, ...) which Wave 1+ will
port in lockstep with the routes that need them.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import aiosqlite

log = logging.getLogger(__name__)


_SCHEMA = """
-- + dreaming: project registry
CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT UNIQUE NOT NULL,
    label        TEXT NOT NULL,
    working_dir  TEXT NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 1,
    is_default   INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    color        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_enabled ON projects(enabled, sort_order);

-- + dreaming: KV overrides per project
CREATE TABLE IF NOT EXISTS project_settings (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    PRIMARY KEY (project_id, key)
);

-- == ALC tables (verbatim columns) + project_id ============================

CREATE TABLE IF NOT EXISTS agent_learning_sessions (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,
    tokens_total INTEGER,
    model TEXT,
    topic TEXT,
    note_path TEXT,
    error_message TEXT,
    entity_page TEXT,
    confidence REAL
);
CREATE INDEX IF NOT EXISTS idx_als_agent ON agent_learning_sessions (agent_name);
CREATE INDEX IF NOT EXISTS idx_als_started ON agent_learning_sessions (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_als_project_started
    ON agent_learning_sessions (project_id, started_at DESC);

-- + dreaming: PK rebuilt as (project_id, agent_name)
CREATE TABLE IF NOT EXISTS agent_learning_rotation (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    tier INTEGER DEFAULT 2,
    last_studied_at TEXT,
    enabled INTEGER DEFAULT 1,
    PRIMARY KEY (project_id, agent_name)
);

CREATE TABLE IF NOT EXISTS custom_topics (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    module TEXT DEFAULT '',
    target_agents TEXT DEFAULT '',
    question TEXT DEFAULT '',
    why_important TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_topics_project_active
    ON custom_topics (project_id, active);

CREATE TABLE IF NOT EXISTS orchestrator_runs (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    external_id TEXT,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_or_runs_started ON orchestrator_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_or_runs_project_started
    ON orchestrator_runs (project_id, started_at DESC);

CREATE TABLE IF NOT EXISTS orchestrator_nodes (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL,
    external_id TEXT,
    parent_node_id TEXT,
    agent_name TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    current_action TEXT,
    progress REAL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    last_heartbeat_at TEXT,
    FOREIGN KEY(run_id) REFERENCES orchestrator_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_or_nodes_run ON orchestrator_nodes (run_id);
CREATE INDEX IF NOT EXISTS idx_or_nodes_parent ON orchestrator_nodes (parent_node_id);
CREATE INDEX IF NOT EXISTS idx_or_nodes_project_run
    ON orchestrator_nodes (project_id, run_id);

CREATE TABLE IF NOT EXISTS orchestrator_messages (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    author TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    delivery_status TEXT,
    client_message_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_or_msg_node_ts ON orchestrator_messages (node_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_or_msg_project_node_ts
    ON orchestrator_messages (project_id, node_id, ts DESC);

-- NOT denormalized: project reached via JOIN to orchestrator_runs
CREATE TABLE IF NOT EXISTS orchestrator_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_or_evt_run_ts ON orchestrator_events (run_id, ts DESC);

-- NOT denormalized
CREATE TABLE IF NOT EXISTS orchestrator_stages (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_index INTEGER NOT NULL,
    stage_key TEXT NOT NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    iteration INTEGER NOT NULL DEFAULT 1,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY(run_id) REFERENCES orchestrator_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_or_stages_run ON orchestrator_stages (run_id, stage_index);

-- NOT denormalized
CREATE TABLE IF NOT EXISTS orchestrator_gate_verdicts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    returned_to_stage_id TEXT,
    iteration INTEGER NOT NULL DEFAULT 1,
    comment TEXT,
    decided_by_node_id TEXT,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_or_verdicts_run ON orchestrator_gate_verdicts (run_id, ts DESC);

-- NOT denormalized
CREATE TABLE IF NOT EXISTS orchestrator_artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_id TEXT,
    node_id TEXT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    content_preview TEXT,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_or_artifacts_run ON orchestrator_artifacts (run_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_or_artifacts_stage ON orchestrator_artifacts (stage_id);

CREATE TABLE IF NOT EXISTS ai_usage_events (
    message_id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    ts_date TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_slug TEXT NOT NULL,
    project_cwd TEXT,
    git_branch TEXT,
    model TEXT,
    is_sidechain INTEGER NOT NULL DEFAULT 0,
    agent_id TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    source_file TEXT NOT NULL,
    source_line INTEGER
);
CREATE INDEX IF NOT EXISTS idx_aue_ts_date   ON ai_usage_events (ts_date);
CREATE INDEX IF NOT EXISTS idx_aue_project   ON ai_usage_events (project_slug, ts_date);
CREATE INDEX IF NOT EXISTS idx_aue_model     ON ai_usage_events (model, ts_date);
CREATE INDEX IF NOT EXISTS idx_aue_session   ON ai_usage_events (session_id);
CREATE INDEX IF NOT EXISTS idx_aue_sidechain ON ai_usage_events (is_sidechain, ts_date);
CREATE INDEX IF NOT EXISTS idx_aue_dreaming_project_ts
    ON ai_usage_events (project_id, ts_date);

-- + dreaming: PK rebuilt as (project_id, path); rest of columns verbatim
CREATE TABLE IF NOT EXISTS ai_usage_files (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    project_slug TEXT NOT NULL,
    is_subagent INTEGER NOT NULL DEFAULT 0,
    byte_offset INTEGER NOT NULL DEFAULT 0,
    file_size INTEGER NOT NULL DEFAULT 0,
    mtime REAL NOT NULL DEFAULT 0,
    lines_parsed INTEGER NOT NULL DEFAULT 0,
    events_inserted INTEGER NOT NULL DEFAULT 0,
    parse_errors INTEGER NOT NULL DEFAULT 0,
    is_missing INTEGER NOT NULL DEFAULT 0,
    last_scanned_at TEXT,
    PRIMARY KEY (project_id, path)
);
CREATE INDEX IF NOT EXISTS idx_auf_project ON ai_usage_files (project_slug);

CREATE TABLE IF NOT EXISTS orchestrator_tts_messages (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL,
    node_id TEXT,
    agent_name TEXT,
    channel TEXT NOT NULL,
    text TEXT NOT NULL,
    ts TEXT NOT NULL,
    dedup_hash TEXT NOT NULL UNIQUE,
    cleared INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(run_id) REFERENCES orchestrator_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_or_tts_run_ts ON orchestrator_tts_messages (run_id, ts);
CREATE INDEX IF NOT EXISTS idx_or_tts_project_ts
    ON orchestrator_tts_messages (project_id, ts DESC);
"""


class SqliteDB:
    """Async SQLite wrapper with a single persistent connection (WAL mode)."""

    def __init__(self, path: str):
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        # PRAGMAs MUST run outside of executescript (which wraps statements in
        # a transaction; PRAGMA journal_mode is a no-op inside a transaction).
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.executescript(_SCHEMA)
        await self._migrate_orchestration()
        await self._conn.commit()
        log.info("SQLite connected: %s", self._path)

    async def _migrate_orchestration(self) -> None:
        """Idempotent migrations for orchestration extensions (stage_id on nodes,
        artifact dedup, orchestrator_questions table). Greenfield-safe."""
        async with self._conn.execute("PRAGMA table_info(orchestrator_nodes)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        if "stage_id" not in cols:
            try:
                await self._conn.execute(
                    "ALTER TABLE orchestrator_nodes ADD COLUMN stage_id TEXT"
                )
            except Exception as e:
                log.warning("Failed to add stage_id column: %s", e)

        async with self._conn.execute(
            "PRAGMA table_info(orchestrator_artifacts)"
        ) as cur:
            art_cols = {row[1] for row in await cur.fetchall()}
        if "dedup_hash" not in art_cols:
            try:
                await self._conn.execute(
                    "ALTER TABLE orchestrator_artifacts ADD COLUMN dedup_hash TEXT"
                )
            except Exception as e:
                log.warning("Failed to add dedup_hash column: %s", e)
        try:
            await self._conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_or_artifacts_dedup "
                "ON orchestrator_artifacts (run_id, dedup_hash) "
                "WHERE dedup_hash IS NOT NULL"
            )
            await self._conn.commit()
        except Exception as e:
            log.warning("Failed to create idx_or_artifacts_dedup: %s", e)

        try:
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_questions (
                    id TEXT PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    run_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    tool_use_id TEXT NOT NULL UNIQUE,
                    questions_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    asked_at TEXT NOT NULL,
                    answered_at TEXT,
                    answer_text TEXT,
                    tts_reminded_at TEXT
                )
                """
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_questions_run "
                "ON orchestrator_questions(run_id, status)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_questions_pending "
                "ON orchestrator_questions(status, asked_at)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_questions_project_run_status "
                "ON orchestrator_questions(project_id, run_id, status)"
            )
            await self._conn.commit()
        except Exception as e:
            log.warning("Failed to create orchestrator_questions table: %s", e)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()) -> None:
        await self._conn.execute(sql, params)
        await self._conn.commit()

    async def fetch_one(self, sql: str, params: tuple = ()):
        async with self._conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def fetch_all(self, sql: str, params: tuple = ()) -> list:
        async with self._conn.execute(sql, params) as cur:
            return list(await cur.fetchall())

    # ── Sessions (project-scoped) ─────────────────────────────────

    async def create_session(self, project_id: int, agent_name: str, model: str = "sonnet") -> str:
        """Insert a new running session, return its UUID."""
        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self.execute(
            "INSERT INTO agent_learning_sessions "
            "(id, project_id, agent_name, started_at, status, model) "
            "VALUES (?, ?, ?, ?, 'running', ?)",
            (sid, project_id, agent_name, now, model),
        )
        return sid

    async def get_or_create_session(
        self, project_id: int, agent_name: str,
        model: str = "sonnet", reuse_window_sec: int = 120,
    ) -> str:
        """Reuse a fresh 'running' session for this (project, agent) if one exists, else create new."""
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(seconds=reuse_window_sec)).isoformat()
        row = await self.fetch_one(
            "SELECT id FROM agent_learning_sessions "
            "WHERE project_id=? AND agent_name=? AND status='running' AND started_at >= ? "
            "ORDER BY started_at DESC LIMIT 1",
            (project_id, agent_name, cutoff),
        )
        if row:
            return row["id"]
        return await self.create_session(project_id, agent_name, model)

    async def finish_session(
        self, session_id: str, status: str,
        topic: str | None = None,
        note_path: str | None = None,
        entity_page: str | None = None,
        confidence: float | None = None,
        tokens_total: int | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Finish a session and update rotation last_studied_at. Returns True if found."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._conn.execute(
            "UPDATE agent_learning_sessions SET "
            "finished_at=?, status=?, topic=?, note_path=?, entity_page=?, "
            "confidence=?, tokens_total=?, error_message=? "
            "WHERE id=?",
            (now, status, topic, note_path, entity_page, confidence,
             tokens_total, error_message, session_id),
        ) as cur:
            n = cur.rowcount
        await self._conn.commit()
        if n > 0:
            row = await self.fetch_one(
                "SELECT project_id, agent_name FROM agent_learning_sessions WHERE id=?",
                (session_id,),
            )
            if row:
                await self.execute(
                    "UPDATE agent_learning_rotation SET last_studied_at=? "
                    "WHERE project_id=? AND agent_name=?",
                    (now, row["project_id"], row["agent_name"]),
                )
        return n > 0

    async def cancel_session(self, session_id: str) -> bool:
        """Mark a stuck 'running' session as cancelled."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._conn.execute(
            "UPDATE agent_learning_sessions SET finished_at=?, status='cancelled' "
            "WHERE id=? AND (status='running' OR (status IS NULL AND finished_at IS NULL))",
            (now, session_id),
        ) as cur:
            n = cur.rowcount
        await self._conn.commit()
        return n > 0

    async def delete_session(self, session_id: str) -> bool:
        """Remove a session row entirely. Returns True if a row was deleted."""
        async with self._conn.execute(
            "DELETE FROM agent_learning_sessions WHERE id=?", (session_id,),
        ) as cur:
            n = cur.rowcount
        await self._conn.commit()
        return n > 0

    async def cancel_stale_running(self, project_id: int) -> int:
        """Close every 'running' row for a project as cancelled. Returns rowcount."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._conn.execute(
            "UPDATE agent_learning_sessions SET finished_at=?, status='cancelled' "
            "WHERE project_id=? AND (status='running' OR (status IS NULL AND finished_at IS NULL))",
            (now, project_id),
        ) as cur:
            n = cur.rowcount
        await self._conn.commit()
        return n

    # ── orchestrator_questions (AskUserQuestion plumbing) ─────────────

    async def create_question(
        self,
        *,
        project_id: int,
        run_id: str | None,
        node_id: str | None,
        tool_use_id: str,
        questions_json: str,
    ) -> str:
        """Insert a pending question. Returns the question id.

        `tool_use_id` is UNIQUE — if claude calls AskUserQuestion with the same
        tool_use_id twice (e.g. on resume), we return the existing row's id
        instead of erroring.
        """
        existing = await self.fetch_one(
            "SELECT id FROM orchestrator_questions WHERE tool_use_id=?",
            (tool_use_id,),
        )
        if existing:
            return existing["id"]
        from uuid import uuid4
        qid = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "INSERT INTO orchestrator_questions "
            "(id, project_id, run_id, node_id, tool_use_id, questions_json, "
            " status, asked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (qid, project_id, run_id or "", node_id or "", tool_use_id,
             questions_json, now),
        )
        await self._conn.commit()
        return qid

    async def answer_question(
        self, question_id: str, *, answer_text: str, status: str = "answered",
    ) -> bool:
        """Mark a question answered (or 'cancelled' / 'dismissed').
        Returns True if a pending row was found and updated."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._conn.execute(
            "UPDATE orchestrator_questions "
            "SET status=?, answered_at=?, answer_text=? "
            "WHERE id=? AND status='pending'",
            (status, now, answer_text, question_id),
        ) as cur:
            n = cur.rowcount
        await self._conn.commit()
        return n > 0

    async def get_question(self, question_id: str) -> dict | None:
        row = await self.fetch_one(
            "SELECT * FROM orchestrator_questions WHERE id=?", (question_id,),
        )
        return dict(row) if row else None

    async def list_questions(
        self, project_id: int, *, status: str | None = None, limit: int = 100,
    ) -> list:
        if status:
            return await self.fetch_all(
                "SELECT * FROM orchestrator_questions "
                "WHERE project_id=? AND status=? "
                "ORDER BY asked_at DESC LIMIT ?",
                (project_id, status, limit),
            )
        return await self.fetch_all(
            "SELECT * FROM orchestrator_questions "
            "WHERE project_id=? ORDER BY asked_at DESC LIMIT ?",
            (project_id, limit),
        )

    async def reconcile_stale_sessions(
        self,
        active_pairs: list[tuple[int, str]],
        learning_notes_dir: str | None = None,
        grace_minutes: int = 2,
    ) -> int:
        """Close orphan running rows whose process is gone.

        `active_pairs` — currently-alive `(project_id, agent_name)` tuples from
        `pm.running` (caller provides). Anything in DB with status=running and
        started_at older than `grace_minutes` that's NOT in active_pairs is
        considered an orphan.

        For each orphan:
          - if a note file already exists on disk at the row's `note_path`
            (relative to learning_notes_dir or absolute), mark `success` —
            the slash command did the work but failed to POST /finish;
          - otherwise mark `cancelled`.

        Returns the count of rows closed.
        """
        from pathlib import Path
        now_dt = datetime.now(timezone.utc)
        cutoff = (now_dt - timedelta(minutes=grace_minutes)).isoformat()
        rows = await self.fetch_all(
            "SELECT id, project_id, agent_name, note_path FROM agent_learning_sessions "
            "WHERE (status='running' OR (status IS NULL AND finished_at IS NULL)) "
            "AND started_at < ?",
            (cutoff,),
        )
        active_set = {(int(pid), name) for pid, name in active_pairs}
        now_iso = now_dt.isoformat()
        closed = 0
        for row in rows:
            pair = (int(row["project_id"]), row["agent_name"])
            if pair in active_set:
                continue
            note_path = row["note_path"]
            success = False
            if note_path:
                p = Path(note_path)
                if not p.is_absolute() and learning_notes_dir:
                    p = Path(learning_notes_dir) / note_path
                try:
                    if p.exists():
                        success = True
                except OSError:
                    pass
            status = "success" if success else "cancelled"
            async with self._conn.execute(
                "UPDATE agent_learning_sessions SET finished_at=?, status=? "
                "WHERE id=? AND (status='running' OR (status IS NULL AND finished_at IS NULL))",
                (now_iso, status, row["id"]),
            ) as cur:
                if cur.rowcount > 0:
                    closed += 1
                    if status == "success":
                        await self._conn.execute(
                            "UPDATE agent_learning_rotation SET last_studied_at=? "
                            "WHERE project_id=? AND agent_name=?",
                            (now_iso, row["project_id"], row["agent_name"]),
                        )
        await self._conn.commit()
        return closed

    async def cancel_stale_orchestration_runs(
        self,
        active_session_ids: set[str] | list[str],
        *,
        grace_minutes: int = 5,
    ) -> int:
        """Close orphan orchestrator_runs whose claude process is gone.

        `active_session_ids` — claude session-ids currently alive in PM (we
        take them from `cmd:*` keys of pm.list_running — those whose
        agent_name starts with `cmd:{slug}:roman-`). Any run with
        status='running' and `external_id` NOT in that set, started more
        than `grace_minutes` ago, is marked status='failed' with a synthetic
        error_message so the user sees what happened on the list page.

        Returns the count of runs closed.
        """
        now_dt = datetime.now(timezone.utc)
        cutoff = (now_dt - timedelta(minutes=grace_minutes)).isoformat()
        rows = await self.fetch_all(
            "SELECT id, external_id, project_id FROM orchestrator_runs "
            "WHERE status='running' AND started_at < ?",
            (cutoff,),
        )
        active = set(active_session_ids)
        now_iso = now_dt.isoformat()
        closed = 0
        for row in rows:
            ext = row["external_id"]
            if ext and ext in active:
                continue
            async with self._conn.execute(
                "UPDATE orchestrator_runs "
                "SET status='failed', finished_at=?, "
                "    error_message='Claude process exited without calling /api/orchestration/{id}/finish — likely hit non-interactive AskUserQuestion limit. See logs for details.' "
                "WHERE id=? AND status='running'",
                (now_iso, row["id"]),
            ) as cur:
                if cur.rowcount > 0:
                    closed += 1
                    # Best effort: also close any still-running nodes for the run
                    await self._conn.execute(
                        "UPDATE orchestrator_nodes SET status='failed', finished_at=? "
                        "WHERE run_id=? AND status='running'",
                        (now_iso, row["id"]),
                    )
        await self._conn.commit()
        return closed

    async def delete_orchestration_run(self, run_id: str, project_id: int) -> bool:
        """Hard-delete an orchestration run plus all its child rows.
        run_id ⇄ project_id pair must match for the delete to apply (defence in depth).
        Returns True if a row was deleted."""
        # Defensive: only act if the run actually belongs to this project.
        row = await self.fetch_one(
            "SELECT id FROM orchestrator_runs WHERE id=? AND project_id=?",
            (run_id, project_id),
        )
        if row is None:
            return False
        # Cascade — child tables don't have FK CASCADE on run_id (only on project_id),
        # so we delete each child set manually.
        await self._conn.execute(
            "DELETE FROM orchestrator_messages WHERE run_id=?", (run_id,),
        )
        await self._conn.execute(
            "DELETE FROM orchestrator_nodes WHERE run_id=?", (run_id,),
        )
        await self._conn.execute(
            "DELETE FROM orchestrator_events WHERE run_id=?", (run_id,),
        )
        await self._conn.execute(
            "DELETE FROM orchestrator_questions WHERE run_id=?", (run_id,),
        )
        await self._conn.execute(
            "DELETE FROM orchestrator_runs WHERE id=? AND project_id=?",
            (run_id, project_id),
        )
        await self._conn.commit()
        return True

    async def cancel_stale_orchestration_runs_for_project(self, project_id: int) -> int:
        """User-triggered: close every running run for this project, regardless of age."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._conn.execute(
            "UPDATE orchestrator_runs "
            "SET status='cancelled', finished_at=?, "
            "    error_message='Force-closed by user from the orchestration list page' "
            "WHERE project_id=? AND status='running'",
            (now_iso, project_id),
        ) as cur:
            n = cur.rowcount
        if n > 0:
            await self._conn.execute(
                "UPDATE orchestrator_nodes SET status='cancelled', finished_at=? "
                "WHERE project_id=? AND status='running'",
                (now_iso, project_id),
            )
        await self._conn.commit()
        return n

    async def list_sessions(self, project_id: int, limit: int = 50) -> list:
        return await self.fetch_all(
            "SELECT * FROM agent_learning_sessions "
            "WHERE project_id=? ORDER BY started_at DESC LIMIT ?",
            (project_id, limit),
        )

    async def list_running_sessions(self, project_id: int) -> list:
        return await self.fetch_all(
            "SELECT * FROM agent_learning_sessions "
            "WHERE project_id=? AND (status='running' OR (status IS NULL AND finished_at IS NULL)) "
            "ORDER BY started_at DESC",
            (project_id,),
        )

    async def week_stats(self, project_id: int) -> dict:
        """Returns dict with success/no_gap/failed/timeout/running counts since Monday 00:00 UTC."""
        now = datetime.now(timezone.utc)
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        row = await self.fetch_one(
            """
            SELECT
                COALESCE(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END), 0) AS success,
                COALESCE(SUM(CASE WHEN status='no_gap' THEN 1 ELSE 0 END), 0) AS no_gap,
                COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END), 0) AS failed,
                COALESCE(SUM(CASE WHEN status='timeout' THEN 1 ELSE 0 END), 0) AS timeout,
                COALESCE(SUM(CASE WHEN status='running' OR (status IS NULL AND finished_at IS NULL) THEN 1 ELSE 0 END), 0) AS running
            FROM agent_learning_sessions
            WHERE project_id=? AND started_at >= ?
            """,
            (project_id, monday.isoformat()),
        )
        return dict(row) if row else {}

    # ── Rotation (project-scoped) ─────────────────────────────────

    async def list_rotation(self, project_id: int) -> list:
        return await self.fetch_all(
            "SELECT * FROM agent_learning_rotation WHERE project_id=? "
            "ORDER BY tier ASC, agent_name ASC",
            (project_id,),
        )

    async def next_agents_for_nightly(self, project_id: int, count: int = 5) -> list:
        """Pick top-N agents by oldest last_studied_at (NULL first), tier ASC, then name."""
        return await self.fetch_all(
            "SELECT * FROM agent_learning_rotation "
            "WHERE project_id=? AND enabled=1 "
            "ORDER BY last_studied_at IS NOT NULL, last_studied_at ASC, tier ASC, agent_name ASC "
            "LIMIT ?",
            (project_id, count),
        )

    async def upsert_agent_rotation(
        self, project_id: int, agent_name: str,
        tier: int = 2, last_studied_at: str | None = None,
    ) -> None:
        """Insert if not exists; never updates an existing row (mirrors ALC `add_agent` semantics)."""
        await self.execute(
            "INSERT OR IGNORE INTO agent_learning_rotation "
            "(project_id, agent_name, tier, enabled, last_studied_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (project_id, agent_name, tier, last_studied_at),
        )

    async def set_agent_tier(self, project_id: int, agent_name: str, tier: int) -> None:
        await self.execute(
            "UPDATE agent_learning_rotation SET tier=? "
            "WHERE project_id=? AND agent_name=?",
            (tier, project_id, agent_name),
        )

    async def set_agent_enabled(self, project_id: int, agent_name: str, enabled: bool) -> None:
        await self.execute(
            "UPDATE agent_learning_rotation SET enabled=? "
            "WHERE project_id=? AND agent_name=?",
            (1 if enabled else 0, project_id, agent_name),
        )

    # ── Custom Topics (project-scoped) ─────────────────────────────────

    async def list_custom_topics(self, project_id: int, active_only: bool = True) -> list:
        sql = "SELECT * FROM custom_topics WHERE project_id=?"
        params: tuple = (project_id,)
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY created_at DESC"
        return await self.fetch_all(sql, params)

    async def list_custom_topics_for_agent(self, project_id: int, agent_name: str) -> list:
        return await self.fetch_all(
            "SELECT * FROM custom_topics WHERE project_id=? AND active=1 "
            "AND (target_agents='' OR target_agents LIKE ? OR target_agents LIKE ? "
            "OR target_agents LIKE ? OR target_agents=?) "
            "ORDER BY created_at DESC",
            (project_id, f"%,{agent_name},%", f"{agent_name},%",
             f"%,{agent_name}", agent_name),
        )

    async def add_custom_topic(
        self, project_id: int, title: str, module: str = "",
        target_agents: str = "", question: str = "", why_important: str = "",
    ) -> str:
        tid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self.execute(
            "INSERT INTO custom_topics "
            "(id, project_id, title, module, target_agents, question, why_important, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tid, project_id, title, module, target_agents, question, why_important, now),
        )
        return tid

    async def delete_custom_topic(self, project_id: int, topic_id: str) -> bool:
        async with self._conn.execute(
            "DELETE FROM custom_topics WHERE project_id=? AND id=?",
            (project_id, topic_id),
        ) as cur:
            n = cur.rowcount
        await self._conn.commit()
        return n > 0
