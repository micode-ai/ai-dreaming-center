# Self-study

Nightly agent self-study is the headline Wave 1 feature. Every day a cron picks the top-N agents from rotation, spawns `claude /self-study {agent}` for each, waits for the result.

## Contents

- [What self-study is](#what-self-study-is)
- [Rotation](#rotation)
- [Cron schedule](#cron-schedule)
- [Manual start (UI)](#manual-start-ui)
- [Session lifecycle](#session-lifecycle)
- [Sessions API](#sessions-api)
- [Custom topics](#custom-topics)
- [Slash-command env vars](#slash-command-env-vars)

## What self-study is

In every project under `.claude/agents/` agents live. The slash command `/self-study {agent}` (lives in the external project's starter kit, not in DC) is launched through the Claude CLI and should:
1. Read the agent description.
2. Find gaps in its knowledge base.
3. Create an `.md` note with findings.
4. Register the session via POST `/api/session/finish`.

DC itself does not implement the slash command logic — it just spawns claude and logs the results.

## Rotation

Per-project [`agent_learning_rotation`](../schema.md#agent_learning_rotation) table: one row per (project_id, agent_name).

Columns:
- `tier` ∈ {1, 2, 3} — priority (1 — wanted more often).
- `enabled` — 0/1.
- `last_studied_at` — bumped in [`finish_session`](../services.md#dbpy--sqlitedb).

On entering `/p/{slug}/rotation` ([`project_rotation.py:12`](../../../dreaming/routes/project_rotation.py)):
1. `list_agent_names(working_dir)` scans `.claude/agents/`.
2. For each name not in DB, calls `upsert_agent_rotation(project_id, name, tier=2)` — inserts with tier=2 enabled=1.
3. Renders the table with inline edits (POST `/tier`, POST `/toggle`).

Selection algorithm for nightly:

```sql
SELECT *
FROM agent_learning_rotation
WHERE project_id=? AND enabled=1
ORDER BY last_studied_at IS NOT NULL,    -- NULL first (new agents)
         last_studied_at ASC,             -- then the oldest
         tier ASC,                        -- tier 1 before tier 2/3
         agent_name ASC                   -- stability
LIMIT ?
```

See [`db.py:489`](../../../dreaming/services/db.py).

## Cron schedule

Per-project job `nightly_learning_{slug}` is registered through [`scheduler.py:_PER_PROJECT_JOBS`](../../../dreaming/services/scheduler.py):

```python
("nightly_learning", "cron_expression", "cron_enabled",
 "0 2 * * *",   # default: every day at 02:00 UTC
 True,           # default: enabled
 _nightly_learning),
```

Job function [`_nightly_learning`](../../../dreaming/services/scheduler.py:56):
1. Loads the project via `get_by_id`. If absent or `enabled=0` — skip.
2. `n = resolver.get(proj, "agents_per_night", 5)`.
3. `pause = resolver.get(proj, "wait_between_sec", 5)`.
4. `candidates = db.next_agents_for_nightly(proj.id, n)`.
5. For each: `pm.start_session(...)` with per-project `claude_path`/`model`/`max_turns`/`timeout_minutes`/`self_study_command`.
6. `await asyncio.sleep(pause)` between spawns.

If `start_session` raises `RuntimeError` (already running, max_concurrent reached, claude not found) — log `WARNING`, move on to the next.

Configurable per-project via `/p/{slug}/settings`:
- `cron_expression`, `cron_enabled`, `agents_per_night`, `wait_between_sec`.
- `claude_path`, `model`, `max_turns`, `timeout_minutes`, `self_study_command`.

See [`configuration.md`](../configuration.md) for the full list.

## Manual start (UI)

`POST /p/{slug}/rotation/start/{agent}` ([`project_rotation.py:57`](../../../dreaming/routes/project_rotation.py)):
1. `pm.start_session(project, agent_name=agent, ...)` with the same parameters as nightly.
2. On success — 303 to `/p/{slug}/live`.
3. On `RuntimeError` — 409 with detail.

Env vars passed:
- `DREAMING_PROJECT_SLUG=<slug>`
- `DREAMING_API_URL=http://localhost:<port>`

## Session lifecycle

```
+--------------------+
|  schedule fires    |  (or /rotation/start/{agent} or NUMBER)
|  _nightly_learning |
+---------+----------+
          |
          v
+---------+----------+
|  pm.start_session  |
|  - verify key      |
|  - check max_      |
|    concurrent      |
|  - db.create_      |
|    session() →     |
|    UUID            |
|  - resolve claude  |
|    path (which)    |
|  - spawn subprocess|
|  - reader_task,    |
|    watchdog_task   |
|  - keep_awake.acq  |
+---------+----------+
          |
          v   stream-json over stdout
+---------+----------+
|  _read_stdout      |
|  - emit() into ring|
|    buffer + SSE    |
|  - last_stdout_at  |
+---------+----------+
          |
          v   process exits
+---------+----------+
|  _cleanup          |
|  - keep_awake.rel  |
|  - watchdog cancel |
|  - sessions.pop()  |
|  - db.reconcile_   |
|    stale (if not   |
|    cmd:*)          |
+---------+----------+
          |
          v   slash command separately calls /api/session/finish
+---------+-------------+
|  /api/session/finish  |
|  - update sessions    |
|  - bump rotation.     |
|    last_studied_at    |
+-----------------------+
```

If the slash command didn't call finish (crashed, timed out) — `_cleanup` already closed it via `reconcile_stale_sessions` with status `cancelled` or `timeout`.

There's also a watchdog ([`process_manager.py:544`](../../../dreaming/services/process_manager.py)): if `time.time() - last_stdout_at >= timeout_minutes*60`, kill the process. A pending question (`orchestrator_questions.status='pending'`) resets the counter — that's a valid state of waiting for the user.

## Sessions API

Detailed examples — in [`api.md`](../api.md#sessions-api).

### POST /api/session/start

```bash
curl -X POST http://localhost:8086/api/session/start \
  -H "Content-Type: application/json" \
  -d '{"project_slug":"rgs","agent_name":"alisa","model":"sonnet"}'
# → {"id":"<uuid>"}
```

INSERT into `agent_learning_sessions` with status='running'.

### POST /api/session/finish

```bash
curl -X POST http://localhost:8086/api/session/finish \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<uuid>","status":"success","topic":"Auth","tokens_total":12345,"note_path":"Z:/notes/x.md"}'
# → {"ok":true,"found":true}
```

UPDATE sessions + UPDATE rotation.last_studied_at.

## Custom topics

The [`custom_topics`](../schema.md#custom_topics) table — user-defined topics (`/p/{slug}/kanban`).

Field `target_agents` is comma-separated. The starter-kit slash command can collect topics relevant to the current agent via `db.list_custom_topics_for_agent(project_id, agent_name)` and inject them into the prompt.

DC itself does NOT do the injection — that's the responsibility of the external project's slash command (it calls `/api/session/start` and reads env vars).

## Slash-command env vars

On spawn `start_session` passes:

| Env | Source | Value |
|---|---|---|
| `DREAMING_PROJECT_SLUG` | from `env_overrides` | Project slug. |
| `DREAMING_PROJECT_ID` | code | Project.id (str). |
| `DREAMING_API_URL` | from `env_overrides` | `http://localhost:<port>`. |
| `LEARNING_SESSION_ID` | auto, if `db_session_id` is created | UUID of the DB session. The slash command sends it back to `/api/session/finish`. |
| `LEARNING_AGENT_NAME` | auto | Agent name. |
| `LEARNING_PROJECT_SLUG` | auto | Same slug. |
| `LEARNING_PROJECT_ID` | auto | Same ID. |

See [`process_manager.py:171–173`](../../../dreaming/services/process_manager.py) for the auto-inject of `LEARNING_*`.

In the nightly cron job additionally: `DREAMING_API_URL` via `env_overrides` ([`scheduler.py:81–83`](../../../dreaming/services/scheduler.py)).

## Cross-references

- Schema sessions / rotation: [`schema.md`](../schema.md).
- ProcessManager details: [`services.md`](../services.md#process_managerpy--processmanager-runningsession).
- Settings keys: [`configuration.md`](../configuration.md#group-self-study).
- API: [`api.md`](../api.md#sessions-api).
