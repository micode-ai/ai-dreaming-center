# SQLite Schema Reference

Все 16 таблиц БД `data/dreaming.db` (SQLite в WAL mode). Источник истины: строка `_SCHEMA` в [`dreaming/services/db.py`](../dreaming/services/db.py) (строки 23–259) + блок `_migrate_orchestration` (строки 282–348).

## Содержание

- [Общее](#общее)
- [`projects`](#projects)
- [`project_settings`](#project_settings)
- [`agent_learning_sessions`](#agent_learning_sessions)
- [`agent_learning_rotation`](#agent_learning_rotation)
- [`custom_topics`](#custom_topics)
- [`orchestrator_runs`](#orchestrator_runs)
- [`orchestrator_nodes`](#orchestrator_nodes)
- [`orchestrator_messages`](#orchestrator_messages)
- [`orchestrator_events`](#orchestrator_events)
- [`orchestrator_stages`](#orchestrator_stages)
- [`orchestrator_gate_verdicts`](#orchestrator_gate_verdicts)
- [`orchestrator_artifacts`](#orchestrator_artifacts)
- [`orchestrator_questions`](#orchestrator_questions)
- [`orchestrator_tts_messages`](#orchestrator_tts_messages)
- [`ai_usage_events`](#ai_usage_events)
- [`ai_usage_files`](#ai_usage_files)
- [Идемпотентные миграции](#идемпотентные-миграции)
- [Cascade-удаление](#cascade-удаление)

## Общее

Все timestamps хранятся как ISO-строки UTC (формат: `2026-05-09T14:33:21+00:00`). См. `_now()` в [`projects.py:11`](../dreaming/services/projects.py) и [`orchestration_hub.py:15`](../dreaming/services/orchestration_hub.py).

PRAGMA на старте (db.py:275–276):

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
```

`foreign_keys=ON` обязателен — иначе CASCADE не сработает.

WAL даёт несколько rader'ов параллельно с одним writer'ом. После старта в `data/` появятся `.db`, `.db-wal`, `.db-shm`. Бэкапить нужно все три (либо использовать `sqlite3 .backup` API, см. [`deployment.md`](deployment.md)).

Типы:
- `INTEGER` — int64.
- `TEXT` — UTF-8 строка.
- `REAL` — float64.

## `projects`

**Назначение**: реестр зарегистрированных проектов. Каждый проект указывает на свой `working_dir` где живут `.claude/agents/`.

```sql
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
```

| Колонка | Тип | Null? | Описание |
|---|---|---|---|
| `id` | INTEGER | NO (PK) | Auto-increment. |
| `slug` | TEXT | NO (UNIQUE) | URL-friendly идентификатор (используется в `/p/{slug}/`). |
| `label` | TEXT | NO | Display-name для UI. |
| `working_dir` | TEXT | NO | Абсолютный путь к корню проекта (там лежит `.claude/agents/`). |
| `enabled` | INT | NO (def 1) | 0/1 — выключен ли проект (роуты `/p/{slug}/*` 404'ят при 0). |
| `is_default` | INT | NO (def 0) | 0/1 — default-проект для slash-команды без `project_slug`. |
| `sort_order` | INT | NO (def 0) | Сортировка списков. |
| `color` | TEXT | YES | Optional hex для UI badges. |
| `created_at` | TEXT | NO | ISO timestamp. |
| `updated_at` | TEXT | NO | ISO timestamp; обновляется в `update()`. |

**Индексы**: `idx_projects_enabled (enabled, sort_order)` — для быстрой выборки enabled-проектов в порядке.

**Кто читает/пишет**:
- `ProjectsService` ([`dreaming/services/projects.py`](../dreaming/services/projects.py)) — все CRUD + `import_from_scan`.
- `setup_gate_middleware` — проверяет наличие хотя бы одной строки.
- `project_resolver_middleware` — `get_by_slug` на каждом `/p/{slug}/*` запросе.

## `project_settings`

**Назначение**: KV-overrides per project. Значения хранятся как JSON-encoded scalars (см. `set_setting`/`get_setting` в `projects.py:109–126`).

```sql
CREATE TABLE IF NOT EXISTS project_settings (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    PRIMARY KEY (project_id, key)
);
```

- PK составной — `(project_id, key)`. Один проект, одна override-запись на ключ.
- ON DELETE CASCADE — если удаляем проект, все его overrides уходят.
- `value` — JSON. Для `True`/`False` хранится `"true"`/`"false"`, для строк — `"\"text\""`, для int — `"42"` и т.д.

**Кто использует**: [`ConfigResolver`](../dreaming/services/config_resolver.py) при resolve override → fallback. Перечитывается per-request, кэшируется в `_cache: dict[int, dict]` (config_resolver.py:18).

См. также [`features/settings.md`](features/settings.md).

## `agent_learning_sessions`

**Назначение**: история self-study сессий.

```sql
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
```

| Колонка | Тип | Описание |
|---|---|---|
| `id` | TEXT (PK) | UUID v4. |
| `project_id` | INT (FK) | CASCADE. |
| `agent_name` | TEXT | Имя агента, либо `cmd:{slug}:{cmdname}` для command-style. |
| `started_at` | TEXT | ISO. |
| `finished_at` | TEXT | NULL пока running. |
| `status` | TEXT | `running` (NULL допускается изначально), затем `success` / `no_gap` / `failed` / `timeout` / `cancelled`. |
| `tokens_total` | INT | NULL пока не известно. |
| `model` | TEXT | `sonnet` / `haiku` / `opus`. |
| `topic` | TEXT | Что изучал. |
| `note_path` | TEXT | Путь к созданной .md-заметке. |
| `error_message` | TEXT | NULL если success. |
| `entity_page` | TEXT | Optional ссылка на wiki-страницу. |
| `confidence` | REAL | 0..1. |

**Индексы**: 3 — по agent_name, по started_at DESC (для всех sessions), и compound `(project_id, started_at DESC)` для быстрого `/p/{slug}/` dashboard'а.

**Кто пишет**: 
- `db.create_session(project_id, agent_name, model)` — `INSERT ... status='running'` (db.py:369).
- `db.get_or_create_session(...)` — reuse если есть свежий running в окне `reuse_window_sec=120` (db.py:381).
- `db.finish_session(session_id, status, ...)` — `UPDATE` финиш + бьёт rotation `last_studied_at` (db.py:398).
- `db.cancel_session(session_id)` — `UPDATE status='cancelled'` если был `running` (db.py:432).
- `ProcessManager._cleanup` через `db.reconcile_stale_sessions()` — закрывает orphan'ы (process_manager.py:618).

**Кто читает**:
- `db.list_sessions(project_id, limit)` — last N (db.py:444).
- `db.list_running_sessions(project_id)` — только активные (db.py:451).
- `db.week_stats(project_id)` — счётчик статусов с понедельника UTC (db.py:459).

## `agent_learning_rotation`

**Назначение**: per-project rotation: тиры, last_studied_at, enabled-флаг.

```sql
CREATE TABLE IF NOT EXISTS agent_learning_rotation (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    tier INTEGER DEFAULT 2,
    last_studied_at TEXT,
    enabled INTEGER DEFAULT 1,
    PRIMARY KEY (project_id, agent_name)
);
```

PK переделан под `(project_id, agent_name)` (в ALC оригинале PK был только `agent_name`). Это — главное dreaming-расширение этой таблицы.

| Колонка | Описание |
|---|---|
| `tier` | 1 / 2 / 3 — приоритет в nightly выборке. 1 — самый часто. |
| `last_studied_at` | Обновляется в `finish_session`. |
| `enabled` | 0 — агент исключён из nightly. |

**Кто пишет**:
- `db.upsert_agent_rotation` — `INSERT OR IGNORE` (db.py:499). Никогда не апдейтит существующую запись.
- `db.set_agent_tier` (db.py:511).
- `db.set_agent_enabled` (db.py:518).
- `db.finish_session` — UPDATE `last_studied_at` (db.py:425).

**Кто читает**:
- `db.list_rotation(project_id)` — все, отсортированы tier ASC, name ASC (db.py:482).
- `db.next_agents_for_nightly(project_id, count)` — для nightly_learning cron'а: `WHERE enabled=1 ORDER BY last_studied_at IS NOT NULL, last_studied_at ASC, tier ASC, agent_name ASC LIMIT ?` (db.py:489). Даёт NULL last_studied_at first, затем самые старые.

## `custom_topics`

**Назначение**: пользовательские топики (kanban на `/p/{slug}/kanban`); инжектируются в self-study prompt стартовой kit-командой.

```sql
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
```

`target_agents` — comma-separated list, либо пусто (тогда матчится любой агент). См. `db.list_custom_topics_for_agent` для LIKE-логики (db.py:535).

**Кто пишет**: `db.add_custom_topic` (db.py:545), `db.delete_custom_topic` (db.py:559).
**Кто читает**: `db.list_custom_topics(project_id, active_only)` (db.py:527).

## `orchestrator_runs`

```sql
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
```

| Колонка | Описание |
|---|---|
| `id` | UUID v4 (DC-internal). |
| `external_id` | Claude session UUID — то же что в `~/.claude/projects/<workdir>/<external_id>.jsonl`. Используется для resume и backfill. |
| `goal` | Текстовая цель run'а. |
| `status` | `running` / `completed` / `failed` / `cancelled`. |

**Кто пишет**:
- `OrchestrationHub.create_run` (orchestration_hub.py:26).
- `OrchestrationHub.finish_run` (orchestration_hub.py:56).

**Кто читает**:
- `OrchestrationHub.get_run`, `list_runs`, `has_running_run`.
- `cascade_costs.list_cascade_costs` (cascade_costs.py:21).

## `orchestrator_nodes`

```sql
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
    -- + dreaming via _migrate_orchestration:
    stage_id TEXT,
    FOREIGN KEY(run_id) REFERENCES orchestrator_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_or_nodes_run ON orchestrator_nodes (run_id);
CREATE INDEX IF NOT EXISTS idx_or_nodes_parent ON orchestrator_nodes (parent_node_id);
CREATE INDEX IF NOT EXISTS idx_or_nodes_project_run
    ON orchestrator_nodes (project_id, run_id);
```

`stage_id` добавляется через `ALTER TABLE` в `_migrate_orchestration` (db.py:287). Это nullable текстовая ссылка (не FK constraint).

| Колонка | Описание |
|---|---|
| `external_id` | Для root-ноды orch-run'а равен `external_id` run'а (Claude session). Для subagent'а — agent_hash (имя файла `agent-<hash>.jsonl`). |
| `parent_node_id` | Для root NULL; для subagent'а — id root-ноды. |
| `role` | `orchestrator` / `worker` / etc. |
| `status` | `running` / `completed` / `failed` / `cancelled`. |
| `progress` | 0..1 опционально. |
| `last_heartbeat_at` | Обновляется в `update_node_status`. |

**Кто пишет**:
- `OrchestrationHub.create_node` (orchestration_hub.py:67).
- `OrchestrationHub.update_node_status` (orchestration_hub.py:87).
- `subagent_watcher._resolve_node_for_subagent` (subagent_watcher.py:49) — резолвит существующий по `external_id == agent_hash` или создаёт новый.

## `orchestrator_messages`

```sql
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
```

| Колонка | Описание |
|---|---|
| `author` | `agent` / `user` / `system`. |
| `kind` | `text` / `tool_use` / `tool_result` / `chat` / `reasoning`. См. `_ingest_line` в [`claude_session_tail.py:276`](../dreaming/services/claude_session_tail.py). |
| `delivery_status` | `delivered` (после INSERT). Зарезервирован для retry-логики. |
| `client_message_id` | для idempotency на стороне внешнего клиента. |

**Кто пишет**:
- `OrchestrationHub.append_message` (orchestration_hub.py:97).
- Вызывается из `claude_session_tail._ingest_line` для каждой live-строки.

**Кто читает**:
- `list_messages(run_id)` (orch_hub.py:112).
- `list_messages_for_node(node_id)` (orch_hub.py:119).

## `orchestrator_events`

Аудит-лог всех событий в run. Не денормализован: `project_id` достаётся через JOIN с `orchestrator_runs` если нужно.

```sql
CREATE TABLE IF NOT EXISTS orchestrator_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_or_evt_run_ts ON orchestrator_events (run_id, ts DESC);
```

`event_type` — semantic string: `run_started`, `run_finished`, `run_failed`, `run_resumed`, `run_resume_failed`, `cascade_init`, `cascade_stage_started`, `cascade_stage_finished`, `cascade_gate`, `cascade_finished`, `message_added`. Полный набор см. в `dreaming/routes/api.py` и `dreaming/services/claude_session_tail.py`.

**payload_json** — `dict`, например `{"cost_usd": 0.34}`. Парсер `cascade_costs.list_cascade_costs` именно отсюда суммирует cost (cascade_costs.py:39–48).

## `orchestrator_stages`

```sql
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
```

Cascade stages, не денормализован.

`stage_key` — стабильный ID (`contract`, `design`, ...). `stage_index` — порядковый, для UI sort.
`status` ∈ {`pending`, `running`, `completed`, `failed`}.
`iteration` — счётчик повторов (если gate вернул на стадию).

**Кто пишет**: `ensure_stage` (orch_hub.py:144), `start_stage`, `finish_stage`.

## `orchestrator_gate_verdicts`

```sql
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
```

`verdict` ∈ {`approve`, `return-to-stage`, `reject`}.

**Кто пишет**: `record_gate_verdict` (orch_hub.py:186) — POST `/api/cascade/{run_id}/gate`.

## `orchestrator_artifacts`

```sql
CREATE TABLE IF NOT EXISTS orchestrator_artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_id TEXT,
    node_id TEXT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    content_preview TEXT,
    ts TEXT NOT NULL,
    -- + dreaming via _migrate_orchestration:
    dedup_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_or_artifacts_run ON orchestrator_artifacts (run_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_or_artifacts_stage ON orchestrator_artifacts (stage_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_or_artifacts_dedup
    ON orchestrator_artifacts (run_id, dedup_hash) WHERE dedup_hash IS NOT NULL;
```

`dedup_hash` — добавлен в migration (db.py:300). Уникальный partial-индекс гарантирует что внутри run'а одна и та же `(run_id, dedup_hash)` пара существует один раз.

**Кто пишет**: `append_artifact` (orch_hub.py:210). Возвращает `None` при коллизии — endpoint `/api/cascade/{run_id}/artifact` отдаёт `{"id": null, "deduped": true}`.

## `orchestrator_questions`

Создаётся в `_migrate_orchestration` (db.py:316–345), не в `_SCHEMA`.

```sql
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
);
CREATE INDEX IF NOT EXISTS idx_questions_run ON orchestrator_questions(run_id, status);
CREATE INDEX IF NOT EXISTS idx_questions_pending ON orchestrator_questions(status, asked_at);
CREATE INDEX IF NOT EXISTS idx_questions_project_run_status
    ON orchestrator_questions(project_id, run_id, status);
```

Используется AskUserQuestion-flow: когда Claude задаёт вопрос пользователю (через `tool_use` с типом `AskUserQuestion`), DC создаёт здесь pending row. ProcessManager watchdog проверяет `_has_pending_question` (process_manager.py:575) — если есть pending, тишина не считается за silence (мы ждём пользователя), watchdog не убивает процесс.

В Wave 3.9 финальное API на этой таблице ещё не зашито — это backfill-friendly хранилище для будущей AskUserQuestion обвязки.

## `orchestrator_tts_messages`

```sql
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
```

TTS (text-to-speech) сообщения для голосового канала. `dedup_hash` UNIQUE — повторно не вставится. `cleared=1` — TTS-агент уже произнёс.

В Wave 3.9 [`tts_backfill.py`](../dreaming/services/tts_backfill.py) — stub возвращает 0 (полная реализация отложена).

## `ai_usage_events`

```sql
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
```

**Назначение**: каждое assistant-message с usage из Claude session JSONL'ов. PK = `message_id` (Claude-side `message.id`). Это гарантирует idempotent re-ingest (повторный INSERT OR IGNORE — no-op).

`ts_date` — `YYYY-MM-DD` префикс `ts`. Используется в индексах для group-by-date запросов.

`is_sidechain` — sub-agent message (true) vs main session (false).

`project_id` — резолвится через `cwd → project_id` мап (см. [`ai_usage_parser.py:91`](../dreaming/services/ai_usage_parser.py)). Если `cwd` не матчится с никаким `working_dir`, событие пропускается (`events_skipped++`).

**Кто пишет**: `ai_usage_parser._insert_events` (ai_usage_parser.py:196) — batch INSERT OR IGNORE. Запускается по cron'у `ai_usage_ingest` на 5-минутном interval'е (scheduler.py:227).

**Кто читает**: `ai_usage_stats.project_summary` / `global_summary` (ai_usage_stats.py:117–149).

## `ai_usage_files`

State per JSONL-файл: где остановились читать.

```sql
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
```

PK составной `(project_id, path)` — переделан под мультипроектность (ALC PK был просто `path`).

`byte_offset` — где остановились в прошлый раз. При следующем ingest'e читаем с него.

`is_missing=1` — файл исчез. Не удаляем, чтобы не потерять offset (вдруг вернётся).

## Идемпотентные миграции

`_migrate_orchestration` ([`db.py:282`](../dreaming/services/db.py)) — ровно эти три действия:

1. `ALTER TABLE orchestrator_nodes ADD COLUMN stage_id TEXT` если нет.
2. `ALTER TABLE orchestrator_artifacts ADD COLUMN dedup_hash TEXT` если нет, плюс `CREATE UNIQUE INDEX ... idx_or_artifacts_dedup`.
3. `CREATE TABLE IF NOT EXISTS orchestrator_questions` + 3 индекса.

Каждый шаг обёрнут в `try/except` с warning'ом в лог — если не удалось, приложение всё равно стартует (но возможно с понижением функциональности).

**Disciplines**:
- НЕ ставим `NOT NULL` на ALTER TABLE'ed колонки (SQLite требует default; nullable проще).
- Никогда не делаем PK rebuild через ALTER. Если нужно — пишем new table, copy data, drop old, rename. См. ALC discipline в [`development.md`](development.md).

## Cascade-удаление

Все таблицы с `project_id` имеют `REFERENCES projects(id) ON DELETE CASCADE`. То есть `DELETE FROM projects WHERE id=N` каскадирует:

- `project_settings` → удалится.
- `agent_learning_sessions`, `agent_learning_rotation`, `custom_topics` → удалится.
- `orchestrator_runs`, `orchestrator_nodes`, `orchestrator_messages`, `orchestrator_questions`, `orchestrator_tts_messages` → удалится.
- `ai_usage_events`, `ai_usage_files` → удалится.

**НЕ каскадируется** через `project_id`:
- `orchestrator_events` — нет `project_id` (FK через `run_id` отсутствует, MVP). Будут orphan events.
- `orchestrator_stages`, `orchestrator_gate_verdicts`, `orchestrator_artifacts` — то же. Они зависят от `run_id`, но FK constraint в SQLite стоит без CASCADE (см. db.py:165, 196).

После удаления проекта, запустите вручную:

```sql
DELETE FROM orchestrator_events WHERE run_id NOT IN (SELECT id FROM orchestrator_runs);
DELETE FROM orchestrator_stages WHERE run_id NOT IN (SELECT id FROM orchestrator_runs);
DELETE FROM orchestrator_gate_verdicts WHERE run_id NOT IN (SELECT id FROM orchestrator_runs);
DELETE FROM orchestrator_artifacts WHERE run_id NOT IN (SELECT id FROM orchestrator_runs);
```

## Cross-references

- Исходник схемы: [`dreaming/services/db.py`](../dreaming/services/db.py).
- Доменные методы DB: см. [`services.md`](services.md) раздел Storage.
- Какой endpoint бьёт какую таблицу — [`api.md`](api.md).
- Backup тактика: [`deployment.md`](deployment.md).
