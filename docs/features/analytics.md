# Analytics

Read-only dashboards: AI Usage, Cascade Costs, Evolutions, Loops, Plans.

## Содержание

- [AI Usage](#ai-usage)
- [Cascade Costs](#cascade-costs)
- [Evolutions](#evolutions)
- [Loops](#loops)
- [Plans](#plans)

## AI Usage

**Что это**: per-project + global token usage, на основе Claude session JSONL'ов из `~/.claude/projects/`.

**Source**: [`ai_usage_parser.py`](../../dreaming/services/ai_usage_parser.py), [`ai_usage_stats.py`](../../dreaming/services/ai_usage_stats.py), [`project_ai_usage.py`](../../dreaming/routes/project_ai_usage.py), [`root.py:109`](../../dreaming/routes/root.py).

### Layout

Claude CLI хранит каждую сессию в:

```
~/.claude/projects/<workdir-encoded>/<session-uuid>.jsonl
~/.claude/projects/<workdir-encoded>/<session-uuid>/subagents/agent-<id>.jsonl
```

`<workdir-encoded>` — путь к cwd Claude'а с заменой каждого non-alnum символа на `-`. Например `D:\Work\micode\rgs` → `D--Work-micode-rgs`.

JSONL содержит per-line:

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

Job `ai_usage_ingest` registers globally в [`scheduler.py:227`](../../dreaming/services/scheduler.py):

```python
sched.add_job(_ai_usage_ingest_job, "interval", minutes=5, args=[app_state],
              id="ai_usage_ingest")
```

Каждые 5 минут вызывает `ingest_ai_usage(db, projects)`:

1. `build_cwd_to_project_id(db)` — мап `_norm_for_match(working_dir) → project_id`.
2. `discover_jsonl_files(root)` — yield все JSONL'ы под `~/.claude/projects/`.
3. Для каждого file:
   - `read_new_lines(path, stored_offset, st.st_size)` — читает только новые байты.
   - `parse_line` каждой строки.
   - Если `cwd` не в map — `events_skipped++`.
   - Иначе INSERT OR IGNORE в `ai_usage_events` (PK = `message_id`).
   - `_upsert_file` — сохранить новый offset.
4. Files which vanished — `_mark_missing(path)`.

Возвращает `{files, events_inserted, events_skipped, errors, duration_ms}` (логируется как INFO).

`max_files=1000`, `batch_size=500` — лимиты ([`ai_usage_parser.py:255`](../../dreaming/services/ai_usage_parser.py)).

### Per-project dashboard

`GET /p/{slug}/ai-usage` ([`project_ai_usage.py:10`](../../dreaming/routes/project_ai_usage.py)):

```python
summary = await project_summary(db, project.id)
# {
#   "project_id": ...,
#   "last_7d": {input_tokens, output_tokens, cache_read_tokens,
#               cache_creation_tokens, total_tokens, events},
#   "last_30d": {... тот же шейп ...},
#   "by_model": [{model, events, ...}, ...]   # отсортировано по total_tokens DESC
# }
```

### Global dashboard

`GET /ai-usage` ([`root.py:109`](../../dreaming/routes/root.py)):

```python
summary = await global_summary(db)
# {
#   "last_7d": {...},
#   "last_30d": {...},
#   "by_project": [{project_id, slug, label, events, ...}, ...],
#   "events_total": <int> # all-time
# }
```

`by_project` LEFT JOIN'ится с `projects`, чтобы добавить slug+label. Если project удалён, slug/label будут NULL.

### Что показывают tokens

- `input_tokens` — сколько отправили в API.
- `output_tokens` — сколько получили.
- `cache_read_tokens` — прочитано из prompt cache (в 10x дешевле).
- `cache_creation_tokens` — записано в cache (на 25% дороже).
- `total_tokens = input + output + cache_read + cache_creation`.

Стоимость считай руками по pricing'у Anthropic. DC текущей версии не считает $$$ напрямую (только в orchestrator_events.payload_json — см. [Cascade Costs](#cascade-costs)).

## Cascade Costs

**Что это**: per-run сумма cost_usd из orchestrator_events.

**Source**: [`cascade_costs.py`](../../dreaming/services/cascade_costs.py), [`project_cascade_costs.py`](../../dreaming/routes/project_cascade_costs.py).

### Алгоритм

[`list_cascade_costs(db, project_id, limit=50)`](../../dreaming/services/cascade_costs.py:21):

```sql
SELECT id, project_id, goal, status, started_at, finished_at
FROM orchestrator_runs
WHERE project_id=?
ORDER BY started_at DESC
LIMIT ?
```

Для каждого run'а:

```sql
SELECT payload_json FROM orchestrator_events WHERE run_id=?
```

Парсим JSON, суммируем `payload.get("cost_usd")` или `payload.get("total_cost_usd")` по всем events.

Возвращает `list[CascadeRunCost]`:

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

`GET /p/{slug}/cascade-costs` ([`project_cascade_costs.py:9`](../../dreaming/routes/project_cascade_costs.py)).

В UI показывается:
- Таблица runs с goal, status, started_at, total_cost_usd.
- Sum по всем runs.

Заметка: cost_usd нужно записывать в события через `hub.append_event("...", {"cost_usd": ...})` — вне DC это делается стартер-кит slash-командами или harness'ом. Если эти не пишут — таблица будет с нулями.

В Wave 3 `pm._parse_stream_json` распаковывает `result` event с `total_cost_usd` для UI live-логов, но в `orchestrator_events` это не пушит автоматически — нужна отдельная обвязка (Wave 4 lite показывает только агрегат, ingest cost'ов из jsonl-файлов отложен).

## Evolutions

**Что это**: list агентских overrides (frontmatter в `_context/` директории).

**Source**: [`evolutions.py`](../../dreaming/services/evolutions.py), [`project_evolutions.py`](../../dreaming/routes/project_evolutions.py).

**Setting**: `evolutions_dir` или `context_overrides_dir`. Default: `{working_dir}/.claude/agents/_context`.

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

`list_evolutions` возвращает `list[EvolutionItem]`:
- `path, name, agent_name, title, status, has_conflict, raw_frontmatter`.

`agent_name` берётся из frontmatter `agent:` или `agent_name:`, либо `parent.dir.name`.

### Page

`GET /p/{slug}/evolutions`.

Wave 4 lite — простая таблица. Conflict-resolution / reapply UX отложены.

## Loops

**Что это**: reflex loops (markdown с frontmatter).

**Source**: [`loops.py`](../../dreaming/services/loops.py), [`project_loops.py`](../../dreaming/routes/project_loops.py).

**Setting**: `loops_dir`. Default: `{obsidian_vault}/03-Team/loops`.

Frontmatter:

```yaml
---
title: Daily standup loop
status: running       # running | paused | done
iterations: 12
---
```

`list_loops` возвращает `list[LoopItem]`:
- `path, name, title, status, iterations, raw_frontmatter`.

### Page

`GET /p/{slug}/loops`.

## Plans

**Что это**: planning документы, с прогрессом по чекбоксам.

**Source**: [`plans.py`](../../dreaming/services/plans.py), [`project_plans.py`](../../dreaming/routes/project_plans.py).

**Setting**: `plans_dir`. Default: `{obsidian_vault}/03-Team/plans`.

Markdown body содержит:

```markdown
- [x] Шаг 1
- [ ] Шаг 2
- [X] Шаг 3
- [ ] Шаг 4
```

Прогресс:
- `done = 2` (X case-insensitive).
- `todo = 2`.
- `progress_pct = done * 100 // total = 50`.

Если `total=0` — `progress_pct=0`.

`status` — берётся из frontmatter, иначе если `total>0 && todo==0` → `done`, иначе `active`.

### Page

`GET /p/{slug}/plans`.

## Cross-references

- Schema ai_usage_*: [`schema.md`](../schema.md#ai_usage_events).
- Schema orchestrator_events (cost source): [`schema.md`](../schema.md#orchestrator_events).
- Service внутренности: [`services.md`](../services.md#cross-cutting).
- Cron jobs ingestion: [`features/multi-project.md`](multi-project.md) + [`scheduler.py`](../../dreaming/services/scheduler.py).
