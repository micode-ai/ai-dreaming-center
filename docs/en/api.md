# REST API Reference

Every REST endpoint of the application. Grouped by logical area. For each endpoint we list the HTTP method, path, body schema (if any), response codes, a curl example (Bash + PowerShell) and a source link with line number.

## Contents

- [Sessions API](#sessions-api)
- [Orchestration API](#orchestration-api)
- [Cascade API](#cascade-api)
- [Form-based actions](#form-based-actions)
- [Health and system](#health-and-system)

Base URL: `http://localhost:8086` (see [`configuration.md`](configuration.md)).

All JSON endpoints accept and return `application/json` (UTF-8). Form-based — `application/x-www-form-urlencoded`.

## Sessions API

Purpose: callback from the `/self-study` slash command (which lives in the starter kit of the external project). Multi-tenant routing goes through the body's `project_slug`.

Source: [`dreaming/routes/api.py`](../../dreaming/routes/api.py) lines 13–66.

### POST `/api/session/start`

Create a DB record for a freshly opened self-study session. The slash command calls this endpoint at the start of its work (if it wants to register itself autonomously).

**Request body** (`SessionStartIn`, api.py:13):

```json
{
  "project_slug": "rgs-frontend",
  "agent_name": "alisa-frontend",
  "model": "sonnet"
}
```

- `project_slug` (str | null) — project slug; if null, the `is_default=1` project is used (with a warning in the log, see api.py:39).
- `agent_name` (str, required) — agent name.
- `model` (str, default `"sonnet"`).

**Response** (200):

```json
{"id": "f6e5d4c3-...-uuid"}
```

**Status codes**:

- `200` — created.
- `400` — no default project and `project_slug` not given (api.py:38).
- `404` — no project with this slug.

**curl (Bash)**:

```bash
curl -X POST http://localhost:8086/api/session/start \
  -H "Content-Type: application/json" \
  -d '{"project_slug":"rgs-frontend","agent_name":"alisa-frontend","model":"sonnet"}'
```

**curl (PowerShell)**:

```powershell
$body = @{ project_slug = "rgs-frontend"; agent_name = "alisa-frontend"; model = "sonnet" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8086/api/session/start -Method POST `
  -ContentType "application/json" -Body $body
```

**Side effects**: INSERT into `agent_learning_sessions` (status=`running`).

### POST `/api/session/finish`

Close a session. Called by the slash command when self-study has wrapped up.

**Request body** (`SessionFinishIn`, api.py:19):

```json
{
  "session_id": "f6e5d4c3-...",
  "status": "success",
  "topic": "Auth flow refactor",
  "confidence": 0.85,
  "note_path": "Z:/learning-notes/2026-05-09-auth.md",
  "tokens_total": 14523,
  "entity_page": "auth.md",
  "error_message": null
}
```

- `session_id` (str, required) — UUID from `/api/session/start`.
- `status` (str, required) — `success` | `no_gap` | `failed` | `timeout` | etc.
- the rest are optional.

**Response** (200):

```json
{"ok": true, "found": true}
```

`found=false` means no session with this ID exists (or it was already closed).

**Status codes**: 200 (always; even when session not found — we return `found: false`).

**curl (Bash)**:

```bash
curl -X POST http://localhost:8086/api/session/finish \
  -H "Content-Type: application/json" \
  -d '{"session_id":"abc-123","status":"success","tokens_total":14523}'
```

**Side effects**: UPDATE `agent_learning_sessions` (finished_at, status, ...). If the row is found — UPDATE `agent_learning_rotation.last_studied_at` (see db.py:425).

## Orchestration API

Purpose: starting Roman runs from external harnesses and managing their lifecycle. Source: [`dreaming/routes/api.py`](../../dreaming/routes/api.py) lines 68–155.

### POST `/api/orchestration/start`

Start a new run.

**Request body** (`OrchStartIn`, api.py:70):

```json
{
  "project_slug": "rgs-frontend",
  "goal": "Implement user auth via OAuth2",
  "external_id": null,
  "enforce_single": true
}
```

- `enforce_single` (default `true`) — if there's another running run in this project, returns 409.
- `external_id` — Claude session UUID; if null, a new one is generated (api.py:106).

**Response** (200):

```json
{
  "run_id": "uuid-v4",
  "root_node_id": "uuid-v4"
}
```

A root node is created with `agent_name="roman", role="orchestrator", external_id=<the same>`.

**Status codes**:
- `200` — started.
- `400` — no default project and `project_slug` is empty.
- `404` — slug unknown.
- `409` — `enforce_single=true` and a running run exists. Body: `{"detail": {"error": "...", "run_id": "<existing>"}}`.

**curl (Bash)**:

```bash
curl -X POST http://localhost:8086/api/orchestration/start \
  -H "Content-Type: application/json" \
  -d '{"project_slug":"rgs-frontend","goal":"Refactor auth"}'
```

**Side effects**: INSERT `orchestrator_runs` + INSERT `orchestrator_nodes` (root) + INSERT `orchestrator_events` (`run_started`).

### GET `/api/orchestration/{run_id}`

Full snapshot of the run: run row, all nodes, all messages.

**Response** (200):

```json
{
  "run": {"id": "...", "project_id": 1, "goal": "...", "status": "running", ...},
  "nodes": [{...}, {...}],
  "messages": [{...}]
}
```

**Status codes**:
- `200` — found.
- `404` — run absent.

**curl (Bash)**:

```bash
curl http://localhost:8086/api/orchestration/abc-123
```

### POST `/api/orchestration/{run_id}/nodes/{node_id}/message`

Append a message to a node.

**Request body** (`OrchAppendMessageIn`, api.py:78):

```json
{
  "node_id": null,
  "author": "agent",
  "kind": "text",
  "text": "I started working.",
  "client_message_id": "client-uuid"
}
```

- `author` ∈ {`agent`, `user`, `system`}.
- `kind` ∈ {`text`, `tool_use`, `tool_result`, ...}.
- `client_message_id` — for idempotency on client retries.

**Response** (200):

```json
{"id": "msg-uuid"}
```

**Status codes**: 200, 404 (run not found).

**curl (Bash)**:

```bash
curl -X POST http://localhost:8086/api/orchestration/abc/nodes/node-uuid/message \
  -H "Content-Type: application/json" \
  -d '{"author":"agent","kind":"text","text":"Hello"}'
```

### POST `/api/orchestration/{run_id}/finish`

Finish a run.

**Request body** (`OrchFinishIn`, api.py:86):

```json
{"status": "completed", "error_message": null}
```

`status` ∈ {`completed`, `failed`, `cancelled`}.

**Response** (200):

```json
{"ok": true}
```

`ok=false` if the run was already gone.

**Side effects**: UPDATE `orchestrator_runs` (`finished_at`=now); INSERT `orchestrator_events` (`run_finished`).

## Cascade API

Source: [`dreaming/routes/api.py`](../../dreaming/routes/api.py) lines 158–321.

5 standard stages: `contract` → `design` → `implementation` → `review` → `qa`.

### POST `/api/cascade/init`

Create a cascade run with a ready set of stages.

**Request body** (`CascadeStartIn`, api.py:160):

```json
{
  "project_slug": "rgs-frontend",
  "goal": "...",
  "external_id": null,
  "stages": null
}
```

`stages` — list of `[{"key": "...", "label": "..."}]`. If null, the default 5 stages are set (api.py:217).

**Response** (200):

```json
{
  "run_id": "...",
  "root_node_id": "...",
  "stages": [
    {"key": "contract", "id": "stage-uuid"},
    {"key": "design", "id": "stage-uuid"},
    ...
  ]
}
```

**Status codes**: 200, 409 (another run already running), 400 (no default project).

**curl**:

```bash
curl -X POST http://localhost:8086/api/cascade/init \
  -H "Content-Type: application/json" \
  -d '{"project_slug":"rgs","goal":"Add billing"}'
```

### POST `/api/cascade/{run_id}/stage/start`

Start a stage.

**Body**:

```json
{"stage_key": "contract", "label": null, "iteration": 1}
```

**Response**: `{"stage_id": "..."}`

**Status codes**: 200, 404 (`stage 'X' not found in run Y`, api.py:237).

### POST `/api/cascade/{run_id}/stage/finish`

Finish a stage.

**Body**: `{"stage_key": "contract", "status": "completed"}`

**Response**: `{"ok": true}`

### POST `/api/cascade/{run_id}/gate`

Record a gate verdict between stages.

**Body** (`CascadeGateIn`, api.py:178):

```json
{
  "stage_key": "review",
  "verdict": "approve",
  "returned_to_stage_key": null,
  "iteration": 1,
  "comment": "OK",
  "decided_by_node_id": "node-uuid"
}
```

`verdict` ∈ {`approve`, `return-to-stage`, `reject`}.
For `return-to-stage`, pass `returned_to_stage_key`.

**Response**: `{"verdict_id": "..."}`

### POST `/api/cascade/{run_id}/artifact`

Register an artifact (module, page, doc).

**Body** (`CascadeArtifactIn`, api.py:187):

```json
{
  "kind": "module",
  "title": "auth.module",
  "stage_key": "implementation",
  "node_id": null,
  "url": null,
  "content_preview": "...",
  "dedup_hash": "sha256:..."
}
```

`dedup_hash` — if passed, a second record with the same `(run_id, dedup_hash)` is silently rejected (UNIQUE INDEX `idx_or_artifacts_dedup`, see db.py:307–311).

**Response**:

```json
{"id": "artifact-uuid", "deduped": false}
```

or `{"id": null, "deduped": true}` on collision.

### POST `/api/cascade/{run_id}/message`

Message into a run; if `node_id` is missing, the first node is picked (api.py:300–306).

**Body** (`CascadeMessageIn`, api.py:197).

**Response**: `{"id": "msg-uuid"}`

### POST `/api/cascade/{run_id}/finish`

Finish the cascade run (`status=completed`).

**Response**: `{"ok": true}`

## Form-based actions

These endpoints accept `application/x-www-form-urlencoded` and typically return `303 See Other` redirecting to the next page after the action. Used straight from HTML forms.

### Setup wizard

- `GET /setup` ([`dreaming/routes/setup.py:24`](../../dreaming/routes/setup.py)) — renders the form with defaults and (opt.) the scan result.
- `POST /setup` ([`setup.py:46`](../../dreaming/routes/setup.py)):
  - `action=scan` — scans `projects_root`, renders the same page with the discovered subfolders.
  - `action=` (or absent) — saves the global config, imports the selected projects, registers cron jobs, redirects to `/`.

### Projects CRUD

- `GET /projects` ([`projects.py:12`](../../dreaming/routes/projects.py)) — list.
- `POST /projects/{project_id}/toggle` ([`projects.py:23`](../../dreaming/routes/projects.py)) — toggles enabled, (un)registers per-project crons.
- `POST /projects/{project_id}/delete` ([`projects.py:40`](../../dreaming/routes/projects.py)) — deletes (CASCADE removes all project_id-dependent rows).
- `POST /projects/import` body `root=...` ([`projects.py:50`](../../dreaming/routes/projects.py)) — repeated bulk scan + import.

### Settings

- `GET /settings` ([`settings.py:46`](../../dreaming/routes/settings.py)).
- `POST /settings` ([`settings.py:57`](../../dreaming/routes/settings.py)) — saves into `config.yaml`, reloads `app.state.settings`.

### Locale

- `POST /locale` body `locale=ru&next=/` ([`root.py:126`](../../dreaming/routes/root.py)) — sets the cookie `dc_locale`, max-age=1 year, redirects back.

### Per-project endpoints (under `/p/{slug}/`)

| Method+Path | Description | Source |
|---|---|---|
| GET `/p/{slug}/` | Dashboard. | [`project_dashboard.py:9`](../../dreaming/routes/project_dashboard.py) |
| GET `/p/{slug}/live` | Live logs + active list. | [`project_live.py:11`](../../dreaming/routes/project_live.py) |
| GET `/p/{slug}/live/stream/{agent}` | SSE stdout stream (`event: log` / `event: end`). | [`project_live.py:26`](../../dreaming/routes/project_live.py) |
| POST `/p/{slug}/live/kill/{agent}` | Kill the process. | [`project_live.py:47`](../../dreaming/routes/project_live.py) |
| GET `/p/{slug}/rotation` | Rotation table; auto-adds agents from FS if missing in DB. | [`project_rotation.py:12`](../../dreaming/routes/project_rotation.py) |
| POST `/p/{slug}/rotation/tier` form `agent_name=&tier=` | Set tier 1\|2\|3. | [`project_rotation.py:36`](../../dreaming/routes/project_rotation.py) |
| POST `/p/{slug}/rotation/toggle` form `agent_name=` | Toggle enabled. | [`project_rotation.py:45`](../../dreaming/routes/project_rotation.py) |
| POST `/p/{slug}/rotation/start/{agent}` | Start self-study session. | [`project_rotation.py:57`](../../dreaming/routes/project_rotation.py) |
| GET/POST `/p/{slug}/settings` | Per-project overrides. | [`project_settings.py`](../../dreaming/routes/project_settings.py) |
| GET `/p/{slug}/topics` | Weekly checklist. | [`project_topics.py:10`](../../dreaming/routes/project_topics.py) |
| GET `/p/{slug}/kanban` | Custom topics. | [`project_kanban.py:10`](../../dreaming/routes/project_kanban.py) |
| POST `/p/{slug}/kanban/add` form fields | Add topic. | [`project_kanban.py:24`](../../dreaming/routes/project_kanban.py) |
| POST `/p/{slug}/kanban/{id}/delete` | Delete topic. | [`project_kanban.py:41`](../../dreaming/routes/project_kanban.py) |
| GET `/p/{slug}/notes` | Notes browser. | [`project_notes.py:17`](../../dreaming/routes/project_notes.py) |
| GET `/p/{slug}/notes/raw?path=` | Raw text; path-traversal-safe. | [`project_notes.py:33`](../../dreaming/routes/project_notes.py) |
| GET `/p/{slug}/findings` | TD list. | [`project_findings.py:16`](../../dreaming/routes/project_findings.py) |
| GET `/p/{slug}/findings/{id}` | TD detail. | [`project_findings.py:49`](../../dreaming/routes/project_findings.py) |
| POST `/p/{slug}/findings/{id}/close` | Close (rewrite frontmatter). | [`project_findings.py:84`](../../dreaming/routes/project_findings.py) |
| POST `/p/{slug}/findings/{id}/delete` | Delete .md file. | [`project_findings.py:95`](../../dreaming/routes/project_findings.py) |
| GET `/p/{slug}/tech-debt` | TD aggregate. | [`project_tech_debt.py:11`](../../dreaming/routes/project_tech_debt.py) |
| GET `/p/{slug}/ideas?status=` | Ideas board. | [`project_ideas.py:16`](../../dreaming/routes/project_ideas.py) |
| POST `/p/{slug}/ideas/{id}/jira` | Create a Jira Task; remembers the key in frontmatter. | [`project_ideas.py:54`](../../dreaming/routes/project_ideas.py) |
| GET `/p/{slug}/wiki` | Wiki status. | [`project_wiki.py:14`](../../dreaming/routes/project_wiki.py) |
| POST `/p/{slug}/wiki/bootstrap` | Run `/wiki-bootstrap` via claude. | [`project_wiki.py:33`](../../dreaming/routes/project_wiki.py) |
| GET `/p/{slug}/ai-usage` | AI usage analytics. | [`project_ai_usage.py:10`](../../dreaming/routes/project_ai_usage.py) |
| GET `/p/{slug}/orchestration` | List of runs. | [`project_orchestration.py:16`](../../dreaming/routes/project_orchestration.py) |
| GET `/p/{slug}/orchestration/{run_id}` | Run detail (live polling). | [`project_orchestration.py:30`](../../dreaming/routes/project_orchestration.py) |
| POST `/p/{slug}/orchestration/start` form `goal=` | Starts a run + spawns claude + tail/watcher. 409 → redirect to existing. | [`project_orchestration.py:50`](../../dreaming/routes/project_orchestration.py) |
| POST `/p/{slug}/orchestration/{run_id}/finish` | Finish. | [`project_orchestration.py:147`](../../dreaming/routes/project_orchestration.py) |
| GET `/p/{slug}/orchestration/{run_id}/refresh` | JSON polling endpoint. | [`project_orchestration.py:159`](../../dreaming/routes/project_orchestration.py) |
| POST `/p/{slug}/orchestration/{run_id}/resume` form `prompt=` | claude --resume. | [`project_orchestration.py:187`](../../dreaming/routes/project_orchestration.py) |
| GET `/p/{slug}/contracts` | Contracts list. | [`project_contracts.py:10`](../../dreaming/routes/project_contracts.py) |
| GET `/p/{slug}/sidecar-findings?severity=` | Sidecar JSON findings. | [`project_sidecar_findings.py:10`](../../dreaming/routes/project_sidecar_findings.py) |
| GET `/p/{slug}/evolutions` | Evolutions list. | [`project_evolutions.py:10`](../../dreaming/routes/project_evolutions.py) |
| GET `/p/{slug}/loops` | Loops list. | [`project_loops.py:10`](../../dreaming/routes/project_loops.py) |
| GET `/p/{slug}/plans` | Plans list. | [`project_plans.py:10`](../../dreaming/routes/project_plans.py) |
| GET `/p/{slug}/cascade-costs` | Cascade-costs roll-up. | [`project_cascade_costs.py:9`](../../dreaming/routes/project_cascade_costs.py) |

A detailed walk-through of every route — in [`routes.md`](routes.md).

## Health and system

### GET `/health`

Simple health check; doesn't require the DB (but lifespan has run).

**Response** (200):

```json
{"ok": true}
```

**curl**:

```bash
curl http://localhost:8086/health
```

### GET `/`

Root index — aggregated dashboard. If the DB is empty, `setup_gate_middleware` redirects to `/setup`. Render: [`templates/index_dashboard.html`](../../dreaming/templates/index_dashboard.html).

### GET `/ai-usage`

Global AI Usage dashboard. Source: [`root.py:109`](../../dreaming/routes/root.py).

### GET `/static/{path}`

Static files. Mounted in `main.py:80`.

### Reserved paths

`/docs`, `/redoc`, `/openapi.json` — FastAPI auto-mounts Swagger UI / ReDoc / OpenAPI schema. **Do NOT define your own routes on these paths** — they get silently overridden (see `setup_gate.py:8`, these paths are in `_BYPASS_PREFIXES` so swagger works even with no projects in the DB).

## Request and error models

All 4xx/5xx responses follow FastAPI's format: `{"detail": "..."}` or `{"detail": {...}}`. If a 409 from orchestration_start arrives with a detail-dict, it contains `error` (text) and `run_id` (link to the conflicting run).

## Cross-references

- Which table each endpoint updates — [`schema.md`](schema.md).
- About spawns and SSE — [`features/orchestration.md`](features/orchestration.md), [`features/self-study.md`](features/self-study.md).
- Which settings affect endpoint behaviour — [`configuration.md`](configuration.md).
