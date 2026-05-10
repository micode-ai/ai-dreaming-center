# Cascade pipelines

Cascade is a separate orchestration pattern on top of runs/nodes: 5 hard stages + gate verdicts between them + dedup'd artifacts.

## Contents

- [5 stages](#5-stages)
- [Gate verdicts](#gate-verdicts)
- [Artifacts with dedup](#artifacts-with-dedup)
- [Cascade API](#cascade-api)
- [Stage detection heuristic](#stage-detection-heuristic)
- [HarnessClient](#harnessclient)
- [Slash commands (external)](#slash-commands-external)

## 5 stages

Default stage set ([`api.py:217–222`](../../../dreaming/routes/api.py)):

| index | key | label | What it does |
|---|---|---|---|
| 0 | `contract` | Contract | Business requirements, the accepting party. |
| 1 | `design` | Design | Architecture, design doc. |
| 2 | `implementation` | Implementation | Code. |
| 3 | `review` | Review | Code review, security audit. |
| 4 | `qa` | QA | Acceptance testing, documentation. |

Stored in `orchestrator_stages` (see [`schema.md`](../schema.md#orchestrator_stages)):

```sql
id TEXT PRIMARY KEY,
run_id TEXT NOT NULL,
stage_index INTEGER NOT NULL,
stage_key TEXT NOT NULL,
label TEXT NOT NULL,
status TEXT NOT NULL DEFAULT 'pending',
iteration INTEGER NOT NULL DEFAULT 1,
started_at TEXT, finished_at TEXT
```

`status` ∈ {`pending`, `running`, `completed`, `failed`}.
`iteration` — repeat counter after `return-to-stage`.

Custom stage set — pass `stages: [{"key": "...", "label": "..."}]` to `/api/cascade/init`.

## Gate verdicts

Between stages (or after a stage) Roman can record a verdict:

`POST /api/cascade/{run_id}/gate` ([`api.py:260`](../../../dreaming/routes/api.py)):

```json
{
  "stage_key": "review",
  "verdict": "approve",          // | "return-to-stage" | "reject"
  "returned_to_stage_key": null, // required if verdict="return-to-stage"
  "iteration": 1,
  "comment": "Looks good",
  "decided_by_node_id": "..."
}
```

INSERT into `orchestrator_gate_verdicts` (see [`schema.md`](../schema.md#orchestrator_gate_verdicts)).

Semantics:
- **approve** — stage passed, move to the next.
- **return-to-stage** — back to stage `returned_to_stage_key` with `iteration+1`.
- **reject** — run cancelled.

The endpoint **does not** change the run/stage state — it only records the verdict. The client (external orchestrator / Roman via slash command) decides what's next.

## Artifacts with dedup

`POST /api/cascade/{run_id}/artifact`:

```json
{
  "kind": "module",
  "title": "auth.module",
  "stage_key": "implementation",
  "node_id": "...",
  "url": "file:///path/to/code",
  "content_preview": "...",
  "dedup_hash": "sha256:abc..."
}
```

If `dedup_hash` collides on `(run_id, dedup_hash)` (UNIQUE INDEX `idx_or_artifacts_dedup`, added in [`db.py:307`](../../../dreaming/services/db.py)) — INSERT fails, the endpoint returns `{"id": null, "deduped": true}` (api.py:289).

Otherwise `{"id": "<uuid>", "deduped": false}`.

Use `dedup_hash` so Roman doesn't record the same file/module twice (e.g. on retry).

## Cascade API

7 endpoints, all under `/api/cascade/`:

| Method | Path | Description |
|---|---|---|
| POST | `/init` | Creates the cascade run + stages. |
| POST | `/{run_id}/stage/start` | Starts a stage (status='running'). |
| POST | `/{run_id}/stage/finish` | Finishes a stage. |
| POST | `/{run_id}/gate` | Verdict. |
| POST | `/{run_id}/artifact` | Artifact. |
| POST | `/{run_id}/message` | Message into the run (if node_id is None — root is used). |
| POST | `/{run_id}/finish` | Finishes the run. |

Detailed body schemas and examples — in [`api.md`](../api.md#cascade-api).

Each endpoint also calls `append_event` of the appropriate type:
- `cascade_init`, `cascade_stage_started`, `cascade_stage_finished`, `cascade_gate`, `cascade_finished`.

This gives an audit log in `orchestrator_events` (useful for cost tracking — see [`features/analytics.md`](analytics.md#cascade-costs)).

### The good workflow

Starter-kit slash commands (live in the external project, not in DC) typically do:

```bash
# 1. Init
curl -X POST http://localhost:8086/api/cascade/init \
  -d '{"project_slug":"rgs","goal":"Add OAuth login"}'
# → {"run_id":"R", "root_node_id":"N", "stages":[...]}

# 2. Stage start (contract)
curl -X POST http://localhost:8086/api/cascade/R/stage/start \
  -d '{"stage_key":"contract"}'

# 3. Roman works...
curl -X POST http://localhost:8086/api/cascade/R/message \
  -d '{"author":"agent","kind":"text","text":"Asked the business..."}'

# 4. Artifact
curl -X POST http://localhost:8086/api/cascade/R/artifact \
  -d '{"kind":"contract","title":"OAuth contract.md","stage_key":"contract","dedup_hash":"hash:1"}'

# 5. Stage finish
curl -X POST http://localhost:8086/api/cascade/R/stage/finish \
  -d '{"stage_key":"contract","status":"completed"}'

# 6. Gate
curl -X POST http://localhost:8086/api/cascade/R/gate \
  -d '{"stage_key":"contract","verdict":"approve"}'

# ... repeat for design / implementation / review / qa ...

# Finish
curl -X POST http://localhost:8086/api/cascade/R/finish
```

## Stage detection heuristic

[`dreaming/services/cascade_stage_detect.py`](../../../dreaming/services/cascade_stage_detect.py).

```python
def detect_stage(agent_name: str, description: str = "") -> str | None
```

Returns one of `'contract' | 'design' | 'implementation' | 'review' | 'qa'` or None.

Rules in `_RULES` (cascade_stage_detect.py:17–57): rule order matters, first match wins.

Used as a **fallback**: if Roman didn't explicitly set `stage_key` when creating a subagent node, you can run `detect_stage(agent_type, description)` and attach to the matching stage.

In Wave 3.9 this function exists but is not in the active codepath (on subagent creation attaching happens without auto-stage). Reserved for the future.

Examples:
- `detect_stage("alisa-frontend")` → `'implementation'`
- `detect_stage("vera-reviewer")` → `'review'`
- `detect_stage("forecast-expert")` → `None` (no match)

## HarnessClient

[`dreaming/services/harness_client.py`](../../../dreaming/services/harness_client.py) — adapter to the external harness API. Used when Roman runs not locally through the claude CLI but on a remote service.

```python
client = HarnessClient(settings)
if client.enabled:    # if harness_base_url is set
    run_external_id = await client.start_orchestration(goal, meta={...})
    async for event in client.stream_events(run_external_id):
        # event = {"event_type": "node_created", "payload": {...}}
        ...
```

`HarnessClientCache.get_for_project(project, resolver)` — lazy per-project client. If `harness_base_url` is not set in project_settings — returns None. If set — creates a client with per-project overrides for the rest of the `harness_*` settings.

Currently: the `start_orchestration` UI button uses local claude, not the harness. To switch — code is needed that first checks `harness_clients.get_for_project(project)` and, if not None, delegates there.

`_normalize_event` (harness_client.py:215) maps aliases:

| External | Normalised |
|---|---|
| `spawn`, `agent_spawned`, `node_spawned` | `node_created` |
| `status` | `node_status_changed` |
| `action` | `node_action_changed` |
| `message`, `chat` | `message_added` |
| `run_completed`, `completed`, `done` | `run_finished` |

This gives a stable event_type for the consumer.

## Slash commands (external)

The external project's starter kit usually has `/cascade-task`, `/cascade-contract`, and so on. They:
1. Call `curl /api/cascade/init`.
2. Parse the response, save `run_id` and `stages` to local state.
3. Hit the rest of the endpoints as progress unfolds.

DC itself doesn't ship these slash commands — that's an external concern. **Audit**: in the starter kit you must verify that they pass `DREAMING_API_URL` and use `LEARNING_*` env vars (if you want self-study integration).

## Cross-references

- Schema: [`schema.md`](../schema.md#orchestrator_stages).
- Routes / API: [`api.md`](../api.md#cascade-api).
- Cost analytics: [`features/analytics.md`](analytics.md#cascade-costs).
- Orchestration basics: [`features/orchestration.md`](orchestration.md).
