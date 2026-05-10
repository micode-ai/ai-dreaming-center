"""OrchestrationHub — DB-backed runs/nodes/messages tracking for Roman-style multi-agent flows.

Wave 3 lean scope: create runs, append messages, list runs, simple status updates.
SSE fan-out, sub-agent watching, cascade pipelines — Wave 3 full.
"""
from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestrationHub:
    def __init__(self, db, projects):
        self.db = db
        self.projects = projects

    # -- Runs -----------------------------------------

    async def create_run(self, project_id: int, goal: str, external_id: str | None = None) -> str:
        run_id = str(uuid.uuid4())
        ts = _now()
        await self.db.execute(
            "INSERT INTO orchestrator_runs (id, project_id, external_id, goal, status, started_at) "
            "VALUES (?, ?, ?, ?, 'running', ?)",
            (run_id, project_id, external_id, goal, ts),
        )
        return run_id

    async def get_run(self, run_id: str):
        return await self.db.fetch_one(
            "SELECT * FROM orchestrator_runs WHERE id=?", (run_id,))

    async def list_runs(self, project_id: int, limit: int = 50) -> list:
        return await self.db.fetch_all(
            "SELECT * FROM orchestrator_runs WHERE project_id=? "
            "ORDER BY started_at DESC LIMIT ?",
            (project_id, limit),
        )

    async def has_running_run(self, project_id: int) -> str | None:
        """Returns run_id of the running run for this project, or None."""
        row = await self.db.fetch_one(
            "SELECT id FROM orchestrator_runs WHERE project_id=? AND status='running' "
            "ORDER BY started_at DESC LIMIT 1",
            (project_id,),
        )
        return row["id"] if row else None

    async def finish_run(self, run_id: str, status: str = "completed", error_message: str | None = None) -> bool:
        async with self.db._conn.execute(
            "UPDATE orchestrator_runs SET status=?, finished_at=?, error_message=? WHERE id=?",
            (status, _now(), error_message, run_id),
        ) as cur:
            n = cur.rowcount
        await self.db._conn.commit()
        return n > 0

    # -- Nodes ----------------------------------------

    async def create_node(
        self, run_id: str, project_id: int, agent_name: str, role: str = "executor",
        parent_node_id: str | None = None, external_id: str | None = None,
    ) -> str:
        node_id = str(uuid.uuid4())
        ts = _now()
        await self.db.execute(
            "INSERT INTO orchestrator_nodes "
            "(id, project_id, run_id, external_id, parent_node_id, agent_name, role, status, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)",
            (node_id, project_id, run_id, external_id, parent_node_id, agent_name, role, ts),
        )
        return node_id

    async def list_nodes(self, run_id: str) -> list:
        return await self.db.fetch_all(
            "SELECT * FROM orchestrator_nodes WHERE run_id=? ORDER BY started_at ASC",
            (run_id,),
        )

    async def update_node_status(self, node_id: str, status: str) -> None:
        finished = _now() if status in ("completed", "failed", "cancelled") else None
        await self.db.execute(
            "UPDATE orchestrator_nodes SET status=?, finished_at=COALESCE(?, finished_at), last_heartbeat_at=? "
            "WHERE id=?",
            (status, finished, _now(), node_id),
        )

    # -- Messages -------------------------------------

    async def append_message(
        self, run_id: str, node_id: str, project_id: int,
        author: str, kind: str, text: str,
        client_message_id: str | None = None,
    ) -> str:
        msg_id = str(uuid.uuid4())
        await self.db.execute(
            "INSERT INTO orchestrator_messages "
            "(id, project_id, run_id, node_id, ts, author, kind, text, delivery_status, client_message_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'delivered', ?)",
            (msg_id, project_id, run_id, node_id, _now(),
             author, kind, text, client_message_id),
        )
        return msg_id

    async def list_messages(self, run_id: str) -> list:
        return await self.db.fetch_all(
            "SELECT * FROM orchestrator_messages WHERE run_id=? "
            "ORDER BY ts ASC",
            (run_id,),
        )

    async def list_messages_for_node(self, node_id: str) -> list:
        return await self.db.fetch_all(
            "SELECT * FROM orchestrator_messages WHERE node_id=? "
            "ORDER BY ts ASC",
            (node_id,),
        )

    # -- Events (audit log, optional) -----------------

    async def append_event(self, run_id: str, event_type: str, payload: dict) -> None:
        await self.db.execute(
            "INSERT INTO orchestrator_events (id, run_id, ts, event_type, payload_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), run_id, _now(), event_type, json.dumps(payload, ensure_ascii=False)),
        )

    async def list_events(self, run_id: str, limit: int = 200) -> list:
        return await self.db.fetch_all(
            "SELECT * FROM orchestrator_events WHERE run_id=? "
            "ORDER BY ts ASC LIMIT ?",
            (run_id, limit),
        )

    # ── Stages ───────────────────────────────────────

    async def ensure_stage(
        self, run_id: str, stage_index: int, stage_key: str, label: str,
    ) -> str:
        """Idempotent — returns stage_id (existing or new)."""
        existing = await self.db.fetch_one(
            "SELECT id FROM orchestrator_stages WHERE run_id=? AND stage_key=?",
            (run_id, stage_key),
        )
        if existing:
            return existing["id"]
        stage_id = str(uuid.uuid4())
        await self.db.execute(
            "INSERT INTO orchestrator_stages (id, run_id, stage_index, stage_key, label, status) "
            "VALUES (?, ?, ?, ?, ?, 'pending')",
            (stage_id, run_id, stage_index, stage_key, label),
        )
        return stage_id

    async def start_stage(self, stage_id: str) -> None:
        await self.db.execute(
            "UPDATE orchestrator_stages SET status='running', started_at=? WHERE id=?",
            (_now(), stage_id),
        )

    async def finish_stage(self, stage_id: str, status: str = "completed") -> None:
        await self.db.execute(
            "UPDATE orchestrator_stages SET status=?, finished_at=? WHERE id=?",
            (status, _now(), stage_id),
        )

    async def list_stages(self, run_id: str) -> list:
        return await self.db.fetch_all(
            "SELECT * FROM orchestrator_stages WHERE run_id=? ORDER BY stage_index ASC",
            (run_id,),
        )

    async def get_stage(self, stage_id: str):
        return await self.db.fetch_one(
            "SELECT * FROM orchestrator_stages WHERE id=?", (stage_id,))

    # ── Gate verdicts ────────────────────────────────

    async def record_gate_verdict(
        self, run_id: str, stage_id: str, verdict: str,
        returned_to_stage_id: str | None = None,
        iteration: int = 1, comment: str | None = None,
        decided_by_node_id: str | None = None,
    ) -> str:
        v_id = str(uuid.uuid4())
        await self.db.execute(
            "INSERT INTO orchestrator_gate_verdicts "
            "(id, run_id, stage_id, verdict, returned_to_stage_id, iteration, comment, decided_by_node_id, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (v_id, run_id, stage_id, verdict, returned_to_stage_id, iteration,
             comment, decided_by_node_id, _now()),
        )
        return v_id

    async def list_gate_verdicts(self, run_id: str) -> list:
        return await self.db.fetch_all(
            "SELECT * FROM orchestrator_gate_verdicts WHERE run_id=? ORDER BY ts ASC",
            (run_id,),
        )

    # ── Artifacts ────────────────────────────────────

    async def append_artifact(
        self, run_id: str, kind: str, title: str,
        stage_id: str | None = None, node_id: str | None = None,
        url: str | None = None, content_preview: str | None = None,
        dedup_hash: str | None = None,
    ) -> str | None:
        """Insert artifact; if dedup_hash collides on (run_id, dedup_hash), return None."""
        a_id = str(uuid.uuid4())
        try:
            await self.db.execute(
                "INSERT INTO orchestrator_artifacts "
                "(id, run_id, stage_id, node_id, kind, title, url, content_preview, ts, dedup_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (a_id, run_id, stage_id, node_id, kind, title, url,
                 content_preview, _now(), dedup_hash),
            )
            return a_id
        except Exception:
            # Most likely UNIQUE constraint on (run_id, dedup_hash)
            return None

    async def list_artifacts(self, run_id: str) -> list:
        return await self.db.fetch_all(
            "SELECT * FROM orchestrator_artifacts WHERE run_id=? ORDER BY ts DESC",
            (run_id,),
        )
