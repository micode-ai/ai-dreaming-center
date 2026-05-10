# Analytics

Read-only dashboards: AI Usage, Cascade Costs, Evolutions, Loops, Plans.

## Contents

- [AI Usage](#ai-usage)
- [Cascade Costs](#cascade-costs)
- [Evolutions](#evolutions)
- [Loops](#loops)
- [Plans](#plans)

## AI Usage

**What it is**: per-project + global token usage, based on Claude session JSONLs from `~/.claude/projects/`.

**Source**: [`ai_usage_parser.py`](../../../dreaming/services/ai_usage_parser.py), [`ai_usage_stats.py`](../../../dreaming/services/ai_usage_stats.py), [`project_ai_usage.py`](../../../dreaming/routes/project_ai_usage.py), [`root.py:109`](../../../dreaming/routes/root.py).

### Layout

The Claude CLI stores each session in:

```
~/.claude/projects/<workdir-encoded>/<session-uuid>.jsonl
~/.claude/projects/<workdir-encoded>/<session-uuid>/subagents/agent-<id>.jsonl
```

`<workdir-encoded>` is the path to Claude's cwd with every non-alnum character replaced by `-`. For example `D:\Work\micode\rgs` → `D--Work-micode-rgs`.

A JSONL holds per-line:

```json
{
  "type": "assistant",
  "uuid": "...",
  "sessionId": "...",
  "cwd": "D:\\Work\\micode\\rgs",
  "gitBranch": "main",
  "isSidechain": false,
  "agentId": null,
  "timestamp": "2026-04-30T14:23:11.123Z",
  "message": {
    "id": "msg_01abc...",
    "model": "claude-sonnet-4",
    "usage": {
      "input_tokens": 1234,
      "output_tokens": 567,
      "cache_read_input_tokens": 89000,
      "cache_creation_input_tokens": 1000
    }
  }
}
```

### Ingest cron

Job `ai_usage_ingest` registers globally in [`scheduler.py:227`](../../../dreaming/services/scheduler.py):

```python
sched.add_job(_ai_usage_ingest_job, "interval", minutes=5, args=[app_state],
              id="ai_usage_ingest")
```

Every 5 minutes calls `ingest_ai_usage(db, projects)`:

1. `build_cwd_to_project_id(db)` — map `_norm_for_match(working_dir) → project_id`.
2. `discover_jsonl_files(root)` — yield every JSONL under `~/.claude/projects/`.
3. For each file:
   - `read_new_lines(path, stored_offset, st.st_size)` — reads only new bytes.
   - `parse_line` for each line.
   - If `cwd` is not in the map — `events_skipped++`.
   - Otherwise INSERT OR IGNORE into `ai_usage_events` (PK = `message_id`).
   - `_upsert_file` — saves the new offset.
4. Files that vanished — `_mark_missing(path)`.

Returns `{files, events_inserted, events_skipped, errors, duration_ms}` (logged as INFO).

`max_files=1000`, `batch_size=500` are the limits ([`ai_usage_parser.py:255`](../../../dreaming/services/ai_usage_parser.py)).

### Per-project dashboard

`GET /p/{slug}/ai-usage` ([`project_ai_usage.py:10`](../../../dreaming/routes/project_ai_usage.py)):

```python
summary = await project_summary(db, project.id)
# {
#   "project_id": ...,
#   "last_7d": {input_tokens, output_tokens, cache_read_tokens,
#               cache_creation_tokens, total_tokens, events},
#   "last_30d": {... same shape ...},
#   "by_model": [{model, events, ...}, ...]   # sorted by total_tokens DESC
# }
```

### Global dashboard

`GET /ai-usage` ([`root.py:109`](../../../dreaming/routes/root.py)):

```python
summary = await global_summary(db)
# {
#   "last_7d": {...},
#   "last_30d": {...},
#   "by_project": [{project_id, slug, label, events, ...}, ...],
#   "events_total": <int> # all-time
# }
```

`by_project` is LEFT JOINed with `projects` to add slug+label. If the project is deleted, slug/label come back as NULL.

### What the tokens mean

- `input_tokens` — sent to the API.
- `output_tokens` — received.
- `cache_read_tokens` — read from prompt cache (10× cheaper).
- `cache_creation_tokens` — written to cache (25% more expensive).
- `total_tokens = input + output + cache_read + cache_creation`.

Cost calculations are done by hand against Anthropic pricing. The current DC version doesn't compute $$$ directly (only in orchestrator_events.payload_json — see [Cascade Costs](#cascade-costs)).

## Cascade Costs

**What it is**: per-run sum of cost_usd from orchestrator_events.

**Source**: [`cascade_costs.py`](../../../dreaming/services/cascade_costs.py), [`project_cascade_costs.py`](../../../dreaming/routes/project_cascade_costs.py).

### Algorithm

[`list_cascade_costs(db, project_id, limit=50)`](../../../dreaming/services/cascade_costs.py:21):

```sql
SELECT id, project_id, goal, status, started_at, finished_at
FROM orchestrator_runs
WHERE project_id=?
ORDER BY started_at DESC
LIMIT ?
```

For each run:

```sql
SELECT payload_json FROM orchestrator_events WHERE run_id=?
```

Parse JSON, sum `payload.get("cost_usd")` or `payload.get("total_cost_usd")` across all events.

Returns `list[CascadeRunCost]`:

```python
@dataclass
class CascadeRunCost:
    run_id: str
    project_id: int
    goal: str
    status: str
    started_at: str
    finished_at: str | None
    total_cost_usd: float
    event_count: int
```

### Page

`GET /p/{slug}/cascade-costs` ([`project_cascade_costs.py:9`](../../../dreaming/routes/project_cascade_costs.py)).

The UI shows:
- A table of runs with goal, status, started_at, total_cost_usd.
- Sum across all runs.

Note: cost_usd has to be written into events via `hub.append_event("...", {"cost_usd": ...})` — outside DC this is done by starter-kit slash commands or the harness. If they don't write — the table is full of zeros.

In Wave 3 `pm._parse_stream_json` unpacks the `result` event with `total_cost_usd` for UI live logs, but it doesn't push it into `orchestrator_events` automatically — needs separate plumbing (Wave 4 lite shows only the aggregate, ingest of costs from jsonl files is deferred).

## Evolutions

**What it is**: list of agent overrides (frontmatter in the `_context/` directory).

**Source**: [`evolutions.py`](../../../dreaming/services/evolutions.py), [`project_evolutions.py`](../../../dreaming/routes/project_evolutions.py).

**Setting**: `evolutions_dir` or `context_overrides_dir`. Default: `{working_dir}/.claude/agents/_context`.

Layout (recursive `*.md`):

```yaml
---
agent: alisa-frontend
title: React 19 transition
status: active        # active | applied | deprecated
conflict: false
---
Override body...
```

`list_evolutions` returns `list[EvolutionItem]`:
- `path, name, agent_name, title, status, has_conflict, raw_frontmatter`.

`agent_name` is taken from the frontmatter `agent:` or `agent_name:`, or `parent.dir.name`.

### Page

`GET /p/{slug}/evolutions`.

Wave 4 lite — simple table. Conflict resolution / reapply UX is deferred.

## Loops

**What it is**: reflex loops (markdown with frontmatter).

**Source**: [`loops.py`](../../../dreaming/services/loops.py), [`project_loops.py`](../../../dreaming/routes/project_loops.py).

**Setting**: `loops_dir`. Default: `{obsidian_vault}/03-Team/loops`.

Frontmatter:

```yaml
---
title: Daily standup loop
status: running       # running | paused | done
iterations: 12
---
```

`list_loops` returns `list[LoopItem]`:
- `path, name, title, status, iterations, raw_frontmatter`.

### Page

`GET /p/{slug}/loops`.

## Plans

**What it is**: planning documents with progress derived from checkboxes.

**Source**: [`plans.py`](../../../dreaming/services/plans.py), [`project_plans.py`](../../../dreaming/routes/project_plans.py).

**Setting**: `plans_dir`. Default: `{obsidian_vault}/03-Team/plans`.

Markdown body holds:

```markdown
- [x] Step 1
- [ ] Step 2
- [X] Step 3
- [ ] Step 4
```

Progress:
- `done = 2` (X case-insensitive).
- `todo = 2`.
- `progress_pct = done * 100 // total = 50`.

If `total=0` — `progress_pct=0`.

`status` — taken from frontmatter, otherwise if `total>0 && todo==0` → `done`, else `active`.

### Page

`GET /p/{slug}/plans`.

## Cross-references

- Schema ai_usage_*: [`schema.md`](../schema.md#ai_usage_events).
- Schema orchestrator_events (cost source): [`schema.md`](../schema.md#orchestrator_events).
- Service internals: [`services.md`](../services.md#cross-cutting).
- Cron job ingestion: [`features/multi-project.md`](multi-project.md) + [`scheduler.py`](../../../dreaming/services/scheduler.py).
