# Cascade pipelines

Cascade — отдельный паттерн оркестрации поверх runs/nodes: 5 жёстких стадий + gate verdicts между ними + dedup'нутые артефакты.

## Содержание

- [5 стадий](#5-стадий)
- [Gate verdicts](#gate-verdicts)
- [Artifacts с dedup](#artifacts-с-dedup)
- [Cascade API](#cascade-api)
- [Stage detection heuristic](#stage-detection-heuristic)
- [HarnessClient](#harnessclient)
- [Slash-команды (внешние)](#slash-команды-внешние)

## 5 стадий

Default набор стадий ([`api.py:217–222`](../../dreaming/routes/api.py)):

| index | key | label | Что делает |
|---|---|---|---|
| 0 | `contract` | Contract | Бизнес-требования, принимающее лицо. |
| 1 | `design` | Design | Архитектура, design doc. |
| 2 | `implementation` | Implementation | Код. |
| 3 | `review` | Review | Code review, security audit. |
| 4 | `qa` | QA | Acceptance testing, документация. |

Хранится в `orchestrator_stages` (см. [`schema.md`](../schema.md#orchestrator_stages)):

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
`iteration` — счётчик повторов после `return-to-stage`.

Кастомный набор стадий — передай `stages: [{"key": "...", "label": "..."}]` в `/api/cascade/init`.

## Gate verdicts

Между стадиями (или после стадии) Roman может записать verdict:

`POST /api/cascade/{run_id}/gate` ([`api.py:260`](../../dreaming/routes/api.py)):

```json
{
  "stage_key": "review",
  "verdict": "approve",          // | "return-to-stage" | "reject"
  "returned_to_stage_key": null, // обязателен если verdict="return-to-stage"
  "iteration": 1,
  "comment": "Looks good",
  "decided_by_node_id": "..."
}
```

INSERT в `orchestrator_gate_verdicts` (см. [`schema.md`](../schema.md#orchestrator_gate_verdicts)).

Семантика:
- **approve** — стадия пройдена, можно идти к следующей.
- **return-to-stage** — обратно на стадию `returned_to_stage_key` с `iteration+1`.
- **reject** — run отменён.

Сам endpoint **не** меняет state run'а / стадий — только записывает verdict. Клиент (внешний оркестратор / Roman через slash-команду) сам решает что дальше.

## Artifacts с dedup

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

Если `dedup_hash` коллизит на `(run_id, dedup_hash)` (UNIQUE INDEX `idx_or_artifacts_dedup`, добавляется в [`db.py:307`](../../dreaming/services/db.py)) — INSERT падает, endpoint возвращает `{"id": null, "deduped": true}` (api.py:289).

Иначе `{"id": "<uuid>", "deduped": false}`.

Используй `dedup_hash` чтобы Roman не записывал один и тот же файл/модуль дважды (например, при retry'е).

## Cascade API

7 endpoint'ов, все под `/api/cascade/`:

| Method | Path | Описание |
|---|---|---|
| POST | `/init` | Создать cascade run + стадии. |
| POST | `/{run_id}/stage/start` | Старт стадии (status='running'). |
| POST | `/{run_id}/stage/finish` | Финиш стадии. |
| POST | `/{run_id}/gate` | Verdict. |
| POST | `/{run_id}/artifact` | Артефакт. |
| POST | `/{run_id}/message` | Сообщение в run (если node_id None — берётся root). |
| POST | `/{run_id}/finish` | Финиш run'а. |

Подробные body-схемы и примеры — в [`api.md`](../api.md#cascade-api).

Каждый endpoint автоматически делает `append_event` соответствующего типа:
- `cascade_init`, `cascade_stage_started`, `cascade_stage_finished`, `cascade_gate`, `cascade_finished`.

Это даёт audit-log в `orchestrator_events` (полезно для cost tracking — см. [`features/analytics.md`](analytics.md#cascade-costs)).

### Лучший workflow

Стартер-кит slash-команды (живут в external project, не в DC) обычно делают:

```bash
# 1. Init
curl -X POST http://localhost:8086/api/cascade/init \
  -d '{"project_slug":"rgs","goal":"Add OAuth login"}'
# → {"run_id":"R", "root_node_id":"N", "stages":[...]}

# 2. Stage start (contract)
curl -X POST http://localhost:8086/api/cascade/R/stage/start \
  -d '{"stage_key":"contract"}'

# 3. Roman работает...
curl -X POST http://localhost:8086/api/cascade/R/message \
  -d '{"author":"agent","kind":"text","text":"Спросил у бизнеса..."}'

# 4. Артефакт
curl -X POST http://localhost:8086/api/cascade/R/artifact \
  -d '{"kind":"contract","title":"OAuth contract.md","stage_key":"contract","dedup_hash":"hash:1"}'

# 5. Stage finish
curl -X POST http://localhost:8086/api/cascade/R/stage/finish \
  -d '{"stage_key":"contract","status":"completed"}'

# 6. Gate
curl -X POST http://localhost:8086/api/cascade/R/gate \
  -d '{"stage_key":"contract","verdict":"approve"}'

# ... повторить для design / implementation / review / qa ...

# Финиш
curl -X POST http://localhost:8086/api/cascade/R/finish
```

## Stage detection heuristic

[`dreaming/services/cascade_stage_detect.py`](../../dreaming/services/cascade_stage_detect.py).

```python
def detect_stage(agent_name: str, description: str = "") -> str | None
```

Возвращает one of `'contract' | 'design' | 'implementation' | 'review' | 'qa'` либо None.

Правила в `_RULES` (cascade_stage_detect.py:17–57): порядок rules важен, first match wins.

Используется как **fallback**: если Roman не указал явно `stage_key` при создании subagent-ноды, можно прогнать `detect_stage(agent_type, description)` и attach'нуть к подходящей стадии.

В Wave 3.9 эта функция написана, но в active codepath ещё не запускается (на subagent создании attach происходит без auto-stage). Резерв для будущего.

Примеры:
- `detect_stage("alisa-frontend")` → `'implementation'`
- `detect_stage("vera-reviewer")` → `'review'`
- `detect_stage("forecast-expert")` → `None` (не матчится)

## HarnessClient

[`dreaming/services/harness_client.py`](../../dreaming/services/harness_client.py) — адаптер к внешнему harness API. Используется когда Roman работает не локально через claude CLI, а на удалённом сервисе.

```python
client = HarnessClient(settings)
if client.enabled:    # если harness_base_url задан
    run_external_id = await client.start_orchestration(goal, meta={...})
    async for event in client.stream_events(run_external_id):
        # event = {"event_type": "node_created", "payload": {...}}
        ...
```

`HarnessClientCache.get_for_project(project, resolver)` — ленивый per-project client. Если `harness_base_url` не задан в project_settings — возвращает None. Если задан — создаёт client с per-project overrides на остальные `harness_*` настройки.

Currently: `start_orchestration` UI кнопка использует local claude, не harness. Чтобы переключить — нужен код, который сначала проверяет `harness_clients.get_for_project(project)`, если не None — делегирует туда.

`_normalize_event` (harness_client.py:215) маппит aliases:

| External | Normalized |
|---|---|
| `spawn`, `agent_spawned`, `node_spawned` | `node_created` |
| `status` | `node_status_changed` |
| `action` | `node_action_changed` |
| `message`, `chat` | `message_added` |
| `run_completed`, `completed`, `done` | `run_finished` |

Это даёт стабильный event_type для consumer'а.

## Slash-команды (внешние)

В стартер-ките external-проекта обычно есть `/cascade-task`, `/cascade-contract`, и т.д. Они:
1. Делают `curl /api/cascade/init`.
2. Парсят response, сохраняют `run_id` и `stages` в локальный state.
3. Дёргают остальные endpoint'ы по мере прогресса.

DC сам этих slash-команд не содержит — это external concern. **Audit**: в стартовом kit'е нужно проверить что они передают `DREAMING_API_URL` и используют `LEARNING_*` env vars (если хочешь интеграцию с self-study).

## Cross-references

- Schema: [`schema.md`](../schema.md#orchestrator_stages).
- Routes / API: [`api.md`](../api.md#cascade-api).
- Cost analytics: [`features/analytics.md`](analytics.md#cascade-costs).
- Orchestration основы: [`features/orchestration.md`](orchestration.md).
