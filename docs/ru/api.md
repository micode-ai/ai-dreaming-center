# REST API Reference

Все REST-эндпоинты приложения. Группировка — по логической области. Для каждого эндпоинта приводится HTTP-метод, путь, схема тела (если есть), коды ответов, curl-пример (Bash + PowerShell) и ссылка в исходники с номером строки.

## Содержание

- [Sessions API](#sessions-api)
- [Orchestration API](#orchestration-api)
- [Cascade API](#cascade-api)
- [Form-based actions](#form-based-actions)
- [Health и системные](#health-и-системные)

База URL: `http://localhost:8086` (см. [`configuration.md`](configuration.md)).

Все JSON-эндпоинты принимают и возвращают `application/json` (UTF-8). Form-based — `application/x-www-form-urlencoded`.

## Sessions API

Назначение: callback из `/self-study` slash-команды (живущей в стартовом kit'е external-проекта). Multi-tenant routing идёт через body `project_slug`.

Источник: [`dreaming/routes/api.py`](../dreaming/routes/api.py) строки 13–66.

### POST `/api/session/start`

Создать DB-запись об открывшейся self-study сессии. Slash-команда вызывает этот endpoint в начале своей работы (если хочет автономно регистрироваться).

**Request body** (`SessionStartIn`, api.py:13):

```json
{
  "project_slug": "rgs-frontend",
  "agent_name": "alisa-frontend",
  "model": "sonnet"
}
```

- `project_slug` (str | null) — slug проекта; если null, берётся `is_default=1` проект (с warning'ом в логе, см. api.py:39).
- `agent_name` (str, обязательно) — имя агента.
- `model` (str, default `"sonnet"`).

**Response** (200):

```json
{"id": "f6e5d4c3-...-uuid"}
```

**Status codes**:

- `200` — создано.
- `400` — нет default-проекта и `project_slug` не передан (api.py:38).
- `404` — проект с таким slug не найден.

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

**Side effects**: INSERT в `agent_learning_sessions` (status=`running`).

### POST `/api/session/finish`

Закрыть сессию. Вызывается slash-командой когда self-study обмотался.

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

- `session_id` (str, required) — UUID из `/api/session/start`.
- `status` (str, required) — `success` | `no_gap` | `failed` | `timeout` | etc.
- остальные — опциональные.

**Response** (200):

```json
{"ok": true, "found": true}
```

`found=false` означает что сессии с таким ID нет (или она уже закрыта).

**Status codes**: 200 (всегда; even when session not found — мы возвращаем `found: false`).

**curl (Bash)**:

```bash
curl -X POST http://localhost:8086/api/session/finish \
  -H "Content-Type: application/json" \
  -d '{"session_id":"abc-123","status":"success","tokens_total":14523}'
```

**Side effects**: UPDATE `agent_learning_sessions` (finished_at, status, ...). Если row найден — UPDATE `agent_learning_rotation.last_studied_at` (см. db.py:425).

## Orchestration API

Назначение: запуск Roman runs из внешних harness'ов и контроль их жизни. Source: [`dreaming/routes/api.py`](../dreaming/routes/api.py) строки 68–155.

### POST `/api/orchestration/start`

Запустить новый run.

**Request body** (`OrchStartIn`, api.py:70):

```json
{
  "project_slug": "rgs-frontend",
  "goal": "Implement user auth via OAuth2",
  "external_id": null,
  "enforce_single": true
}
```

- `enforce_single` (default `true`) — если есть другой running run в этом проекте, вернётся 409.
- `external_id` — Claude session UUID; если null, генерируется новый (api.py:106).

**Response** (200):

```json
{
  "run_id": "uuid-v4",
  "root_node_id": "uuid-v4"
}
```

Создаётся root-нода с `agent_name="roman", role="orchestrator", external_id=<тот же>`.

**Status codes**:
- `200` — запущено.
- `400` — нет default-проекта и `project_slug` пуст.
- `404` — slug неизвестен.
- `409` — `enforce_single=true` и есть running. Body: `{"detail": {"error": "...", "run_id": "<existing>"}}`.

**curl (Bash)**:

```bash
curl -X POST http://localhost:8086/api/orchestration/start \
  -H "Content-Type: application/json" \
  -d '{"project_slug":"rgs-frontend","goal":"Refactor auth"}'
```

**Side effects**: INSERT `orchestrator_runs` + INSERT `orchestrator_nodes` (root) + INSERT `orchestrator_events` (`run_started`).

### GET `/api/orchestration/{run_id}`

Полный snapshot run'а: run row, все nodes, все messages.

**Response** (200):

```json
{
  "run": {"id": "...", "project_id": 1, "goal": "...", "status": "running", ...},
  "nodes": [{...}, {...}],
  "messages": [{...}]
}
```

**Status codes**:
- `200` — найден.
- `404` — run отсутствует.

**curl (Bash)**:

```bash
curl http://localhost:8086/api/orchestration/abc-123
```

### POST `/api/orchestration/{run_id}/nodes/{node_id}/message`

Записать сообщение в node.

**Request body** (`OrchAppendMessageIn`, api.py:78):

```json
{
  "node_id": null,
  "author": "agent",
  "kind": "text",
  "text": "Я начал работу.",
  "client_message_id": "client-uuid"
}
```

- `author` ∈ {`agent`, `user`, `system`}.
- `kind` ∈ {`text`, `tool_use`, `tool_result`, ...}.
- `client_message_id` — для идемпотентности retry'ев на стороне клиента.

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

Завершить run.

**Request body** (`OrchFinishIn`, api.py:86):

```json
{"status": "completed", "error_message": null}
```

`status` ∈ {`completed`, `failed`, `cancelled`}.

**Response** (200):

```json
{"ok": true}
```

`ok=false` если run уже не существовал.

**Side effects**: UPDATE `orchestrator_runs` (`finished_at`=now); INSERT `orchestrator_events` (`run_finished`).

## Cascade API

Источник: [`dreaming/routes/api.py`](../dreaming/routes/api.py) строки 158–321.

5 стандартных стадий: `contract` → `design` → `implementation` → `review` → `qa`.

### POST `/api/cascade/init`

Создать cascade run с готовым набором стадий.

**Request body** (`CascadeStartIn`, api.py:160):

```json
{
  "project_slug": "rgs-frontend",
  "goal": "...",
  "external_id": null,
  "stages": null
}
```

`stages` — список `[{"key": "...", "label": "..."}]`. Если null, ставится default 5 стадий (api.py:217).

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

**Status codes**: 200, 409 (другой run уже идёт), 400 (нет default-проекта).

**curl**:

```bash
curl -X POST http://localhost:8086/api/cascade/init \
  -H "Content-Type: application/json" \
  -d '{"project_slug":"rgs","goal":"Add billing"}'
```

### POST `/api/cascade/{run_id}/stage/start`

Стартовать стадию.

**Body**:

```json
{"stage_key": "contract", "label": null, "iteration": 1}
```

**Response**: `{"stage_id": "..."}`

**Status codes**: 200, 404 (`stage 'X' not found in run Y`, api.py:237).

### POST `/api/cascade/{run_id}/stage/finish`

Завершить стадию.

**Body**: `{"stage_key": "contract", "status": "completed"}`

**Response**: `{"ok": true}`

### POST `/api/cascade/{run_id}/gate`

Записать вердикт gate'а между стадиями.

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
Если `return-to-stage`, передай `returned_to_stage_key`.

**Response**: `{"verdict_id": "..."}`

### POST `/api/cascade/{run_id}/artifact`

Зарегистрировать артефакт (модуль, страницу, doc).

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

`dedup_hash` — если передан, вторая запись с тем же `(run_id, dedup_hash)` будет молча отклонена (UNIQUE INDEX `idx_or_artifacts_dedup`, см. db.py:307–311).

**Response**:

```json
{"id": "artifact-uuid", "deduped": false}
```

или `{"id": null, "deduped": true}` если был коллизия.

### POST `/api/cascade/{run_id}/message`

Сообщение в run; если `node_id` не указан, выбирается первый node (api.py:300–306).

**Body** (`CascadeMessageIn`, api.py:197).

**Response**: `{"id": "msg-uuid"}`

### POST `/api/cascade/{run_id}/finish`

Завершить cascade run (`status=completed`).

**Response**: `{"ok": true}`

## Form-based actions

Эти эндпоинты принимают `application/x-www-form-urlencoded` и обычно возвращают `303 See Other` редирект на page после действия. Используются прямо из HTML-форм.

### Setup wizard

- `GET /setup` ([`dreaming/routes/setup.py:24`](../dreaming/routes/setup.py)) — render формы с defaults и (опц.) результатом сканирования.
- `POST /setup` ([`setup.py:46`](../dreaming/routes/setup.py)):
  - `action=scan` — сканирует `projects_root`, рендерит ту же страницу с найденными подпапками.
  - `action=` (или отсутствует) — сохраняет global config, импортирует выбранные проекты, регистрирует cron jobs, редиректит на `/`.

### Projects CRUD

- `GET /projects` ([`projects.py:12`](../dreaming/routes/projects.py)) — список.
- `POST /projects/{project_id}/toggle` ([`projects.py:23`](../dreaming/routes/projects.py)) — переключает enabled, (un)register'ит per-project crons.
- `POST /projects/{project_id}/delete` ([`projects.py:40`](../dreaming/routes/projects.py)) — удаляет (CASCADE удалит все project_id-зависимые rows).
- `POST /projects/import` body `root=...` ([`projects.py:50`](../dreaming/routes/projects.py)) — повторный массовый scan + import.

### Settings

- `GET /settings` ([`settings.py:46`](../dreaming/routes/settings.py)).
- `POST /settings` ([`settings.py:57`](../dreaming/routes/settings.py)) — сохраняет в `config.yaml`, перезагружает `app.state.settings`.

### Locale

- `POST /locale` body `locale=ru&next=/` ([`root.py:126`](../dreaming/routes/root.py)) — ставит cookie `dc_locale`, max-age=год, редиректит обратно.

### Per-project endpoints (за `/p/{slug}/`)

| Method+Path | Описание | Source |
|---|---|---|
| GET `/p/{slug}/` | Dashboard. | [`project_dashboard.py:9`](../dreaming/routes/project_dashboard.py) |
| GET `/p/{slug}/live` | Live-логи + список активных. | [`project_live.py:11`](../dreaming/routes/project_live.py) |
| GET `/p/{slug}/live/stream/{agent}` | SSE-стрим stdout (`event: log` / `event: end`). | [`project_live.py:26`](../dreaming/routes/project_live.py) |
| POST `/p/{slug}/live/kill/{agent}` | Убить процесс. | [`project_live.py:47`](../dreaming/routes/project_live.py) |
| GET `/p/{slug}/rotation` | Rotation-таблица; авто-добавляет агентов из ФС если их нет в DB. | [`project_rotation.py:12`](../dreaming/routes/project_rotation.py) |
| POST `/p/{slug}/rotation/tier` form `agent_name=&tier=` | Set tier 1\|2\|3. | [`project_rotation.py:36`](../dreaming/routes/project_rotation.py) |
| POST `/p/{slug}/rotation/toggle` form `agent_name=` | Toggle enabled. | [`project_rotation.py:45`](../dreaming/routes/project_rotation.py) |
| POST `/p/{slug}/rotation/start/{agent}` | Start self-study session. | [`project_rotation.py:57`](../dreaming/routes/project_rotation.py) |
| GET/POST `/p/{slug}/settings` | Per-project overrides. | [`project_settings.py`](../dreaming/routes/project_settings.py) |
| GET `/p/{slug}/topics` | Weekly checklist. | [`project_topics.py:10`](../dreaming/routes/project_topics.py) |
| GET `/p/{slug}/kanban` | Custom topics. | [`project_kanban.py:10`](../dreaming/routes/project_kanban.py) |
| POST `/p/{slug}/kanban/add` form fields | Add topic. | [`project_kanban.py:24`](../dreaming/routes/project_kanban.py) |
| POST `/p/{slug}/kanban/{id}/delete` | Delete topic. | [`project_kanban.py:41`](../dreaming/routes/project_kanban.py) |
| GET `/p/{slug}/notes` | Notes browser. | [`project_notes.py:17`](../dreaming/routes/project_notes.py) |
| GET `/p/{slug}/notes/raw?path=` | Raw текст; path-traversal-safe. | [`project_notes.py:33`](../dreaming/routes/project_notes.py) |
| GET `/p/{slug}/findings` | TD list. | [`project_findings.py:16`](../dreaming/routes/project_findings.py) |
| GET `/p/{slug}/findings/{id}` | TD detail. | [`project_findings.py:49`](../dreaming/routes/project_findings.py) |
| POST `/p/{slug}/findings/{id}/close` | Close (rewrite frontmatter). | [`project_findings.py:84`](../dreaming/routes/project_findings.py) |
| POST `/p/{slug}/findings/{id}/delete` | Delete .md file. | [`project_findings.py:95`](../dreaming/routes/project_findings.py) |
| GET `/p/{slug}/tech-debt` | TD aggregate. | [`project_tech_debt.py:11`](../dreaming/routes/project_tech_debt.py) |
| GET `/p/{slug}/ideas?status=` | Ideas board. | [`project_ideas.py:16`](../dreaming/routes/project_ideas.py) |
| POST `/p/{slug}/ideas/{id}/jira` | Создать Jira Task; запоминает key в frontmatter. | [`project_ideas.py:54`](../dreaming/routes/project_ideas.py) |
| GET `/p/{slug}/wiki` | Wiki status. | [`project_wiki.py:14`](../dreaming/routes/project_wiki.py) |
| POST `/p/{slug}/wiki/bootstrap` | Запустить `/wiki-bootstrap` через claude. | [`project_wiki.py:33`](../dreaming/routes/project_wiki.py) |
| GET `/p/{slug}/ai-usage` | AI usage analytics. | [`project_ai_usage.py:10`](../dreaming/routes/project_ai_usage.py) |
| GET `/p/{slug}/orchestration` | Список runs. | [`project_orchestration.py:16`](../dreaming/routes/project_orchestration.py) |
| GET `/p/{slug}/orchestration/{run_id}` | Run detail (live polling). | [`project_orchestration.py:30`](../dreaming/routes/project_orchestration.py) |
| POST `/p/{slug}/orchestration/start` form `goal=` | Запустить run + спавнит claude + tail/watcher. 409→редирект на existing. | [`project_orchestration.py:50`](../dreaming/routes/project_orchestration.py) |
| POST `/p/{slug}/orchestration/{run_id}/finish` | Завершить. | [`project_orchestration.py:147`](../dreaming/routes/project_orchestration.py) |
| GET `/p/{slug}/orchestration/{run_id}/refresh` | JSON polling endpoint. | [`project_orchestration.py:159`](../dreaming/routes/project_orchestration.py) |
| POST `/p/{slug}/orchestration/{run_id}/resume` form `prompt=` | claude --resume. | [`project_orchestration.py:187`](../dreaming/routes/project_orchestration.py) |
| GET `/p/{slug}/contracts` | Contracts list. | [`project_contracts.py:10`](../dreaming/routes/project_contracts.py) |
| GET `/p/{slug}/sidecar-findings?severity=` | Sidecar JSON findings. | [`project_sidecar_findings.py:10`](../dreaming/routes/project_sidecar_findings.py) |
| GET `/p/{slug}/evolutions` | Evolutions list. | [`project_evolutions.py:10`](../dreaming/routes/project_evolutions.py) |
| GET `/p/{slug}/loops` | Loops list. | [`project_loops.py:10`](../dreaming/routes/project_loops.py) |
| GET `/p/{slug}/plans` | Plans list. | [`project_plans.py:10`](../dreaming/routes/project_plans.py) |
| GET `/p/{slug}/cascade-costs` | Cascade-costs roll-up. | [`project_cascade_costs.py:9`](../dreaming/routes/project_cascade_costs.py) |

Подробный разбор каждого роута — в [`routes.md`](routes.md).

## Health и системные

### GET `/health`

Простой health-check; не требует БД (но lifespan уже выполнился).

**Response** (200):

```json
{"ok": true}
```

**curl**:

```bash
curl http://localhost:8086/health
```

### GET `/`

Root index — agg dashboard. Если БД пустая, `setup_gate_middleware` редиректит в `/setup`. Render: [`templates/index_dashboard.html`](../dreaming/templates/index_dashboard.html).

### GET `/ai-usage`

Глобальный AI Usage dashboard. Source: [`root.py:109`](../dreaming/routes/root.py).

### GET `/static/{path}`

Статические файлы. Mount в `main.py:80`.

### Зарезервированные пути

`/docs`, `/redoc`, `/openapi.json` — FastAPI auto-mount Swagger UI / ReDoc / OpenAPI schema. **НЕ создавайте свои роуты на этих путях** — они тихо переопределятся (см. `setup_gate.py:8`, эти пути в `_BYPASS_PREFIXES` чтобы swagger работал даже без проектов в БД).

## Модели запросов и ошибок

Все 4xx/5xx ответы FastAPI — формат `{"detail": "..."}` или `{"detail": {...}}`. Если на 409 от orchestration_start пришёл detail-словарь, он содержит `error` (текст) и `run_id` (ссылка на конфликтующий run).

## Cross-references

- Подробнее про какую таблицу обновляет каждый endpoint — [`schema.md`](schema.md).
- Подробнее про spawn'ы и SSE — [`features/orchestration.md`](features/orchestration.md), [`features/self-study.md`](features/self-study.md).
- Подробнее про какие настройки влияют на endpoint behavior — [`configuration.md`](configuration.md).
