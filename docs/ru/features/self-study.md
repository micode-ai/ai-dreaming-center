# Self-study

Ночное самообучение агентов — основная фича Wave 1. Cron каждые сутки выбирает top-N агентов из rotation, спавнит для каждого `claude /self-study {agent}`, ждёт результата.

## Содержание

- [Что такое self-study](#что-такое-self-study)
- [Rotation](#rotation)
- [Cron schedule](#cron-schedule)
- [Manual start (UI)](#manual-start-ui)
- [Lifecycle сессии](#lifecycle-сессии)
- [Sessions API](#sessions-api)
- [Custom topics](#custom-topics)
- [Slash-command env vars](#slash-command-env-vars)

## Что такое self-study

В каждом проекте под `.claude/agents/` живут агенты. Slash-команда `/self-study {agent}` (живёт в стартер-ките external-проекта, не в DC) запускается через Claude CLI и должна:
1. Прочитать описание агента.
2. Найти gap'ы в его knowledge base.
3. Создать `.md`-конспект с findings.
4. Зарегистрировать сессию через POST `/api/session/finish`.

DC сам не реализует логику slash-команды — он только спавнит claude и логирует результаты.

## Rotation

Per-проектная таблица [`agent_learning_rotation`](../schema.md#agent_learning_rotation): один row на (project_id, agent_name).

Колонки:
- `tier` ∈ {1, 2, 3} — приоритет (1 — хочется чаще).
- `enabled` — 0/1.
- `last_studied_at` — обновляется в [`finish_session`](../services.md#dbpy--sqlitedb).

При заходе на `/p/{slug}/rotation` ([`project_rotation.py:12`](../../dreaming/routes/project_rotation.py)):
1. `list_agent_names(working_dir)` сканит `.claude/agents/`.
2. Для каждого имени, которого нет в DB, делает `upsert_agent_rotation(project_id, name, tier=2)` — добавляет с tier=2 enabled=1.
3. Рендерит таблицу с inline-edit'ами (POST `/tier`, POST `/toggle`).

Selection algorithm для nightly:

```sql
SELECT *
FROM agent_learning_rotation
WHERE project_id=? AND enabled=1
ORDER BY last_studied_at IS NOT NULL,    -- NULL first (новые агенты)
         last_studied_at ASC,             -- затем самые старые
         tier ASC,                        -- tier 1 раньше tier 2/3
         agent_name ASC                   -- стабильность
LIMIT ?
```

См. [`db.py:489`](../../dreaming/services/db.py).

## Cron schedule

Per-project job `nightly_learning_{slug}` регистрируется через [`scheduler.py:_PER_PROJECT_JOBS`](../../dreaming/services/scheduler.py):

```python
("nightly_learning", "cron_expression", "cron_enabled",
 "0 2 * * *",   # default: каждый день в 02:00 UTC
 True,           # default: enabled
 _nightly_learning),
```

Job-функция [`_nightly_learning`](../../dreaming/services/scheduler.py:56):
1. Загружает project через `get_by_id`. Если проект отсутствует или `enabled=0` — skip.
2. `n = resolver.get(proj, "agents_per_night", 5)`.
3. `pause = resolver.get(proj, "wait_between_sec", 5)`.
4. `candidates = db.next_agents_for_nightly(proj.id, n)`.
5. Для каждого: `pm.start_session(...)` с per-project `claude_path`/`model`/`max_turns`/`timeout_minutes`/`self_study_command`.
6. `await asyncio.sleep(pause)` между spawn'ами.

Если `start_session` бросает `RuntimeError` (already running, max_concurrent reached, claude not found) — лог `WARNING`, идём к следующему.

Configurable per-project через `/p/{slug}/settings`:
- `cron_expression`, `cron_enabled`, `agents_per_night`, `wait_between_sec`.
- `claude_path`, `model`, `max_turns`, `timeout_minutes`, `self_study_command`.

См. [`configuration.md`](../configuration.md) для полного списка.

## Manual start (UI)

`POST /p/{slug}/rotation/start/{agent}` ([`project_rotation.py:57`](../../dreaming/routes/project_rotation.py)):
1. `pm.start_session(project, agent_name=agent, ...)` с теми же параметрами что nightly.
2. На успех — 303 на `/p/{slug}/live`.
3. На `RuntimeError` — 409 с detail.

Env vars передаются:
- `DREAMING_PROJECT_SLUG=<slug>`
- `DREAMING_API_URL=http://localhost:<port>`

## Lifecycle сессии

```
+--------------------+
|  schedule fires    |  (или /rotation/start/{agent} or NUMBER)
|  _nightly_learning |
+---------+----------+
          |
          v
+---------+----------+
|  pm.start_session  |
|  - проверка key    |
|  - проверка max_   |
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
          v   stream-json по stdout
+---------+----------+
|  _read_stdout      |
|  - emit() в ring   |
|    buffer + SSE    |
|  - last_stdout_at  |
+---------+----------+
          |
          v   процесс закончился (exit code)
+---------+----------+
|  _cleanup          |
|  - keep_awake.rel  |
|  - watchdog cancel |
|  - sessions.pop()  |
|  - db.reconcile_   |
|    stale (если не  |
|    cmd:*)          |
+---------+----------+
          |
          v   slash-команда отдельно вызвала /api/session/finish
+---------+-------------+
|  /api/session/finish  |
|  - update sessions    |
|  - bump rotation.     |
|    last_studied_at    |
+-----------------------+
```

Если slash-команда не вызвала finish (упала, timed out) — `_cleanup` уже её закрыл через `reconcile_stale_sessions` со статусом `cancelled` или `timeout`.

Также есть watchdog ([`process_manager.py:544`](../../dreaming/services/process_manager.py)): если `time.time() - last_stdout_at >= timeout_minutes*60`, kill process. Pending question (`orchestrator_questions.status='pending'`) сбрасывает счётчик — это валидное состояние ожидания пользователя.

## Sessions API

Подробные примеры — в [`api.md`](../api.md#sessions-api).

### POST /api/session/start

```bash
curl -X POST http://localhost:8086/api/session/start \
  -H "Content-Type: application/json" \
  -d '{"project_slug":"rgs","agent_name":"alisa","model":"sonnet"}'
# → {"id":"<uuid>"}
```

INSERT в `agent_learning_sessions` со status='running'.

### POST /api/session/finish

```bash
curl -X POST http://localhost:8086/api/session/finish \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<uuid>","status":"success","topic":"Auth","tokens_total":12345,"note_path":"Z:/notes/x.md"}'
# → {"ok":true,"found":true}
```

UPDATE sessions + UPDATE rotation.last_studied_at.

## Custom topics

Таблица [`custom_topics`](../schema.md#custom_topics) — пользовательские темы (`/p/{slug}/kanban`).

Поле `target_agents` — comma-separated. Slash-команда стартер-кита может через `db.list_custom_topics_for_agent(project_id, agent_name)` собрать topics, релевантные текущему агенту, и вставить их в prompt.

В DC сам инжект НЕ делается — это ответственность slash-команды external-проекта (она выполняет `/api/session/start` и читает env vars).

## Slash-command env vars

При spawn'е `start_session` передаются:

| Env | Source | Значение |
|---|---|---|
| `DREAMING_PROJECT_SLUG` | from `env_overrides` | Slug проекта. |
| `DREAMING_PROJECT_ID` | code | Project.id (str). |
| `DREAMING_API_URL` | from `env_overrides` | `http://localhost:<port>`. |
| `LEARNING_SESSION_ID` | auto, если `db_session_id` создан | UUID DB-сессии. Slash-команда передаёт его обратно в `/api/session/finish`. |
| `LEARNING_AGENT_NAME` | auto | Имя агента. |
| `LEARNING_PROJECT_SLUG` | auto | Тот же slug. |
| `LEARNING_PROJECT_ID` | auto | Тот же ID. |

См. [`process_manager.py:171–173`](../../dreaming/services/process_manager.py) для авто-инжекта `LEARNING_*`.

В nightly cron job дополнительно: `DREAMING_API_URL` через `env_overrides` ([`scheduler.py:81–83`](../../dreaming/services/scheduler.py)).

## Cross-references

- Schema sessions / rotation: [`schema.md`](../schema.md).
- ProcessManager детали: [`services.md`](../services.md#process_managerpy--processmanager-runningsession).
- Settings keys: [`configuration.md`](../configuration.md#group-self-study).
- API: [`api.md`](../api.md#sessions-api).
