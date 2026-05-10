# Orchestration (Roman runs)

Roman is the root Claude agent with the role `orchestrator`. He takes a task (goal), decomposes it via the `Task` tool into sub-agents, and DC tracks all activity in the DB through ClaudeSessionTail + SubagentWatcher.

## Contents

- [What a run is](#what-a-run-is)
- [One-Roman-per-project lock](#one-roman-per-project-lock)
- [Starting a run](#starting-a-run)
- [Detail page (live polling)](#detail-page-live-polling)
- [ClaudeSessionTail mechanics](#claudesessiontail-mechanics)
- [SubagentWatcher mechanics](#subagentwatcher-mechanics)
- [Resume](#resume)
- [Backfill](#backfill)
- [API](#api)

## What a run is

`orchestrator_runs` (see [`schema.md`](../schema.md#orchestrator_runs)) — one attempt at a goal.

Lifecycle:

```
+--------+      +---------+      +----------+
| pending| -->  | running | -->  | completed|
+--------+      +---------+      +----------+
                     |                ^
                     v                |
                 +--------+      +--------+
                 | failed |      |cancelled|
                 +--------+      +--------+
```

In code these statuses are written into the `status` column, [`orchestration_hub.create_run`](../../../dreaming/services/orchestration_hub.py:26) sets `'running'`.

Each run has:
- `id` — DC-internal UUID.
- `external_id` — Claude session UUID (equals the basename of the `.jsonl` file under `~/.claude/projects/<workdir>/`).
- `goal` — text goal.
- `started_at`, `finished_at`.

On creation a root node is auto-inserted ([`api.py:108`](../../../dreaming/routes/api.py)):

```python
node_id = await hub.create_node(
    run_id, project.id, agent_name="roman", role="orchestrator",
    external_id=external_id,
)
```

## One-Roman-per-project lock

`OrchestrationHub.has_running_run(project_id)` ([`orchestration_hub.py:47`](../../../dreaming/services/orchestration_hub.py)) returns the existing running `run_id` or None.

In the JSON API endpoint `/api/orchestration/start`:
- If `enforce_single=true` (default) — 409 with `{"detail": {"error": "...", "run_id": <existing>}}`.

In the form-based endpoint `POST /p/{slug}/orchestration/start`:
- 303 redirect to `/p/{slug}/orchestration/{existing}` ([`project_orchestration.py:64`](../../../dreaming/routes/project_orchestration.py)).

Defends against an accidental double click on the "Start" button in the UI.

## Starting a run

UI: on `/p/{slug}/orchestration` there's a form with one `goal` field. Click Start → POST `/p/{slug}/orchestration/start`.

Action in code ([`project_orchestration.py:50`](../../../dreaming/routes/project_orchestration.py)):

1. Validate `goal.strip()` — otherwise 400.
2. `has_running_run` → if there is one, 303 to existing.
3. `claude_session_id = str(uuid.uuid4())` — used as `--session-id` for claude AND as `external_id` for the run.
4. `hub.create_run(project_id, goal, external_id=claude_session_id)`.
5. `hub.create_node(run, agent_name="roman", role="orchestrator", external_id=claude_session_id)`.
6. `hub.append_event("run_started", {project_slug, goal})`.
7. `pm.start_command(project, command_name=f"roman-{run_id[:8]}", prompt=goal, session_id=claude_session_id, ...)` — spawns claude.
8. If spawn fails — `finish_run(run_id, status='failed')` + 303 to detail (with error_message in DB).
9. Otherwise:
   - 1–2 seconds later claude creates the jsonl file. We do `find_session_file_by_id(claude_session_id)`.
   - If jsonl is already there — start `ClaudeSessionTail(run_id, jsonl_path, hub, db)` via `asyncio.create_task`. Save in `app.state.orchestration_tails[run_id]`.
   - Start `SubagentWatcher(run_id, root_node_id, hub, db, claude_projects_dir=...)`. Save in `app.state.orchestration_watchers[run_id]`.

If the jsonl hasn't appeared yet — log `INFO orchestration_start_form: jsonl not yet visible for session ...; backfill will recover` ([`project_orchestration.py:124`](../../../dreaming/routes/project_orchestration.py)) — backfill will catch up later, or on restart.

## Detail page (live polling)

`GET /p/{slug}/orchestration/{run_id}` ([`project_orchestration.py:30`](../../../dreaming/routes/project_orchestration.py)) renders `project_orchestration_detail.html` with:
- run record (goal, status, started_at, finished_at).
- nodes (with agent_name, role, status, started_at).
- messages (every message of the whole run in chronological order).

Client JS (inside the template) does `setInterval` polling `GET /p/{slug}/orchestration/{run_id}/refresh` every ~2 seconds:

```json
{
  "status": "running",
  "finished_at": null,
  "node_count": 3,
  "message_count": 47,
  "nodes": [{"id":"...","agent_name":"alisa-frontend","status":"running","role":"worker"}],
  "messages": [{"id":"...","ts":"...","author":"agent","kind":"text","text":"..."}]
}
```

Returns only the last 100 messages (slice `[-100:]`, [`project_orchestration.py:182`](../../../dreaming/routes/project_orchestration.py)).

POST to `/p/{slug}/orchestration/{run_id}/finish` — finishes the run by button (`status=completed`).

## ClaudeSessionTail mechanics

[`dreaming/services/claude_session_tail.py`](../../../dreaming/services/claude_session_tail.py).

Wrapper object:

```python
tail = ClaudeSessionTail(run_id, jsonl_path, hub, db)
await tail.start()    # idempotent
# ... time passes ...
await tail.stop()
```

`start()`:
1. `_ensure_node()` — find existing orchestrator node in the run, or create one.
2. Launch `asyncio.create_task(tail_session_file(...))`.

`tail_session_file` (claude_session_tail.py:338):

**Catchup pass**: opens jsonl, reads every line, calls `_ingest_line(...)` on each. Records `seen_uuids` to avoid duplicates during the live tail.

**Live tail loop**:
- `path.stat()` every `poll_interval` (1s).
- If `cur_inode != last_inode` — file rotated. `last_size = 0` (read from start).
- If `cur_size < last_size` — truncation. `last_size = 0`.
- If `cur_size > last_size` — open, seek(last_size), read new lines, ingest.
- If `idle_finalize_after` is set and `idle >= idle_finalize_after` — `update_node_status(node_id, 'completed')` and exit.

`_ingest_line` (claude_session_tail.py:276):

```python
obj = json.loads(line)
if obj["type"] not in ("assistant", "user"): return 0
if obj["uuid"] in seen: return 0
text = _extract_text_from_message(obj["message"])
if not text: return 0
author = "assistant" if obj["type"] == "assistant" else "user"
kind = "chat" if obj["type"] == "user" else "reasoning"
msg_id = await hub.append_message(run_id, node_id, project_id, author, kind, text)
seen.add(obj["uuid"])
await hub.append_event(run_id, "message_added", payload)
```

Supported blocks in `_extract_text_from_message`:
- `text` — appended directly.
- `tool_use` — `_summarize_tool_use(name, input)` → one-liner: `[Bash] desc — \`cmd\``, `[Read] path`, `[Task → frontend] desc`, etc.
- `tool_result` — first 400 chars as `[tool_result] ...`.

## SubagentWatcher mechanics

[`dreaming/services/subagent_watcher.py`](../../../dreaming/services/subagent_watcher.py).

When Roman delegates a task via the `Task` tool, the Claude CLI spawns a child process, and its jsonl lives under:

```
~/.claude/projects/<workdir-encoded>/<roman_session>/subagents/agent-<hash>.jsonl
~/.claude/projects/<workdir-encoded>/<roman_session>/subagents/agent-<hash>.meta.json
```

`meta.json` holds:
```json
{"agentType": "alisa-frontend", "description": "Implement login UI"}
```

`SubagentWatcher.start`:
1. `_resolve_folder()` — looks up `<roman_session>.jsonl` under `~/.claude/projects/`, takes `parent / <session> / subagents`.
2. If not found — `idle, watcher remains idle` (subagent_watcher.py:218).
3. Otherwise launches `watch_subagents_for_run(folder=...)`.

`watch_subagents_for_run` (subagent_watcher.py:78):
- Every `poll_interval` (1s):
  - `folder.glob("agent-*.meta.json")`.
  - For every new `agent_hash`:
    - Read `meta.json` → `agent_type`, `description`.
    - `_resolve_node_for_subagent` — find node with `external_id == agent_hash`, or create a worker node parented to root.
    - Launch `tail_session_file(...)` task with `idle_finalize_after=30.0`.
    - Drop the task into `tails[agent_hash]`.

After 30s of silence the subagent auto-finalises via `idle_finalize_after`. The main run keeps running.

`stop_subagent_tails(tails)` — cancels all tail tasks.

## Resume

`POST /p/{slug}/orchestration/{run_id}/resume` form `prompt=` ([`project_orchestration.py:187`](../../../dreaming/routes/project_orchestration.py)):

1. Run must have `external_id` (Claude session UUID). Otherwise 400.
2. Reactivate run: `UPDATE orchestrator_runs SET status='running', finished_at=NULL, error_message=NULL WHERE id=?`.
3. `append_event("run_resumed", {prompt})`.
4. `pm.start_command(...)`:
   - `command_name = f"resume-{run_id[:8]}"`.
   - `resume_session_id = run.external_id` — becomes `claude --resume <id>`.
   - `interactive_stdin = True` — claude waits on stdin, we send the prompt via a stream-json user message.
5. On RuntimeError — `finish_run(failed)`, 409.

`pm.start_command(interactive_stdin=True)` nuance ([`process_manager.py:260`](../../../dreaming/services/process_manager.py)): you cannot pass both `-p <prompt>` and `--input-format stream-json` — claude hangs. So when `interactive_stdin=True` we pass only `--print` (no positional prompt), launch the process, and then `await session.send_user_message(prompt)` over stdin.

## Backfill

[`dreaming/services/subagent_backfill.py`](../../../dreaming/services/subagent_backfill.py) — `backfill_run(run_id, db, hub, claude_projects_dir=None) -> int`.

Used when:
- The run was created but the watcher went offline — orchestration tables are empty.
- The run predates Wave 3 (an old external_id was imported).

Algorithm:
1. `find_session_file_by_id(external_id)` — find jsonl under `~/.claude/projects/`.
2. `_ensure_main_node` — create the orchestrator node if missing.
3. `_replay_jsonl` — line-by-line `_ingest_line`.
4. `subagents/agent-*.meta.json` — for each:
   - `_resolve_node_for_subagent` (worker node parented to main).
   - `_replay_jsonl` for the subagent jsonl.

**Not idempotent** — repeated calls on an already-backfilled run produce duplicates (subagent_backfill.py:14–17). In production either rebuild the DB or check for messages before running.

## API

See [`api.md`](../api.md#orchestration-api) — all 4 endpoints:
- `POST /api/orchestration/start`.
- `GET /api/orchestration/{run_id}`.
- `POST /api/orchestration/{run_id}/nodes/{node_id}/message`.
- `POST /api/orchestration/{run_id}/finish`.

An external harness can start orchestration through the harness API via `HarnessClient.start_orchestration(goal)` — but in the current DC this isn't wired to the UI form (uses local claude). See [`waves.md`](../waves.md#not-implemented-yet).

## Cross-references

- Cascade pipelines: [`features/cascade.md`](cascade.md).
- Schema runs/nodes/messages/events: [`schema.md`](../schema.md).
- Service internals: [`services.md`](../services.md#orchestration).
