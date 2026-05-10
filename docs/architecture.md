# Архитектура AI Dreaming Center

Документ описывает общую устройство приложения: какие процессы крутятся, какие синглтоны живут на `app.state`, в каком порядке отрабатывает middleware, как происходит запуск/остановка, и куда какие подсистемы дёргаются.

## Содержание

- [Высокоуровневая диаграмма](#высокоуровневая-диаграмма)
- [Процесс-модель](#процесс-модель)
- [Lifespan](#lifespan)
- [Middleware](#middleware)
- [Синглтоны на `app.state`](#синглтоны-на-appstate)
- [URL-routing и project resolver](#url-routing-и-project-resolver)
- [Concurrency model](#concurrency-model)
- [Файловая раскладка](#файловая-раскладка)
- [Cross-references](#cross-references)

## Высокоуровневая диаграмма

```
+--------------------+         +------------------------+
|    Browser         |  HTTP   |   uvicorn (asyncio)    |
|  htmx + Tailwind   +---------+    FastAPI app         |
|  SSE для /live     |         |                        |
+--------------------+         +-----------+------------+
                                           |
                                           v
                            +---------------------------+
                            |   Middleware chain        |
                            |   1. setup_gate (OUTER)   |
                            |   2. project_resolver     |
                            +-------------+-------------+
                                          |
                                          v
                              +-----------+-----------+
                              |   Routers (19 шт.)    |
                              |   /, /setup, /api,    |
                              |   /p/{slug}/*         |
                              +-----------+-----------+
                                          |
            +-----------------------------+-----------------------------+
            |                             |                             |
            v                             v                             v
+-----------+-----------+    +------------+--------------+   +----------+----------+
|   Service layer       |    |   ProcessManager          |   |   APScheduler      |
|   (db, projects,      |    |   spawn(claude CLI)       |   |   AsyncIOScheduler |
|   resolver, hubs,     |    |   ring buffer + SSE       |   |   nightly + 5min   |
|   parsers)            |    |   KeepAwake refcount      |   |   reconcile + ai-  |
+-----------+-----------+    +------------+--------------+   |   usage + per-prj  |
            |                             |                  +----------+---------+
            v                             v                             |
+-----------+----------------------------+-----------+                  |
|                     SQLite (WAL)                   |  <---------------+
|  data/dreaming.db — 16 таблиц + idemp. migrations |
+----------------------------------------------------+
```

Стрелки идут только в одну сторону: routes -> services -> db. Сервисы между собой пересекаются через явный dependency injection (передача в конструкторе или явные аргументы).

## Процесс-модель

Один процесс `python -m uvicorn dreaming.main:app --port 8086` (см. [`pyproject.toml`](../pyproject.toml) — зависимости, и [`README.md`](../README.md) — quickstart). Внутри него:

- **asyncio loop** — единственный, всё IO (HTTP, SQLite, subprocess, scheduler) сидит на нём.
- **Один persistent SQLite connection** в WAL режиме (см. [`dreaming/services/db.py`](../dreaming/services/db.py) строки 269–280: `PRAGMA journal_mode=WAL` и `PRAGMA foreign_keys=ON` ставятся ДО `executescript(_SCHEMA)`).
- **Subprocess'ы** Claude CLI, спавнятся через `asyncio.create_subprocess_exec` — лимит `STDOUT_BUFFER_LIMIT = 16 MB` (process_manager.py:28), потому что stream-json от Claude может присылать очень крупные assistant-блоки.
- **APScheduler** в режиме `AsyncIOScheduler` — крутится на том же loop'е, не создаёт отдельный thread/процесс (см. [`dreaming/services/scheduler.py`](../dreaming/services/scheduler.py) `build_scheduler`, строка 219).

Параллелизм ограничен:
- `max_concurrent` (default 2) — сколько параллельных Claude-сессий держит ProcessManager (process_manager.py:92).
- Per-project: composite key `'{slug}:{agent}'` или `'cmd:{slug}:{name}'` — см. process_manager.py:91.

Single-process design выбран сознательно: Roman — корневой long-lived процесс, и не хочется fork'ать состояние БД между worker'ами. Если будете масштабировать — пишите second instance с другим `port`/`db_path`, не workers одного uvicorn.

## Lifespan

[`dreaming/main.py`](../dreaming/main.py) определяет `@asynccontextmanager async def lifespan(app)` — порядок строго:

1. `app.state.settings = load_settings()` — Pydantic `AppSettings.load()` читает [`config.yaml`](../config.example.yaml) + env vars `DC_*`.
2. `app.state.db = SqliteDB(settings.db_path)` + `await db.connect()` — создаёт каталог, открывает connection, ставит PRAGMA, запускает `_SCHEMA + _migrate_orchestration`.
3. `app.state.projects = ProjectsService(db)` — registry-сервис.
4. `app.state.templates = Jinja2Templates("dreaming/templates")` — Jinja2.
5. `app.state.i18n = I18n(Path("dreaming/i18n"))` — загружает `messages_ru.json` + `messages_en.json`.
6. Bind `t()` фильтр в Jinja env: `templates.env.filters["t"] = _t` (main.py:40).
7. `app.state.process_manager = ProcessManager(settings, db, projects)`.
8. `app.state.orchestration_hub = OrchestrationHub(db, projects)`.
9. `app.state.harness_clients = HarnessClientCache()`.
10. `app.state.scheduler = build_scheduler(app.state)` + `scheduler.start()`.
11. Для каждого enabled-проекта: `register_project_jobs(scheduler, app.state, proj)`.
12. `app.state.resolver_factory = get_resolver` — функция-фабрика, ConfigResolver создаётся PER-REQUEST (см. main.py:69).
13. `yield` — приложение работает.
14. На shutdown: `scheduler.shutdown(wait=False)` + `await db.close()` (в `finally:` — выполнится даже при exception).

Lifespan важен потому что **в роутах нельзя инстанцировать сервисы повторно**: всегда `request.app.state.<name>`.

## Middleware

Зарегистрированы в [`main.py`](../dreaming/main.py) строки 65–66:

```python
app.middleware("http")(project_resolver_middleware)   # внутренний
app.middleware("http")(setup_gate_middleware)         # внешний
```

В Starlette middleware, зарегистрированный последним, идёт ПЕРВЫМ на пути запроса. Поэтому:

```
Request --> setup_gate (OUTER) --> project_resolver (INNER) --> route
```

Логика:

1. **`setup_gate`** ([`dreaming/middleware/setup_gate.py`](../dreaming/middleware/setup_gate.py)) — если `projects` таблица пустая И путь не в `_BYPASS_PREFIXES = ("/setup", "/static", "/health", "/api", "/docs", "/redoc", "/openapi")`, делает `RedirectResponse("/setup", 303)`. Это — first-run wizard gate.

2. **`project_resolver`** ([`dreaming/middleware/project_resolver.py`](../dreaming/middleware/project_resolver.py)) — если путь начинается с `/p/<slug>/`, парсит `<slug>`, ищет проект через `projects.get_by_slug(slug)`. Если проект не найден ИЛИ `enabled=False` — возвращает 404 с шаблоном `project_not_found.html`. Если найден — пишет в `request.state.project = project`, и роуты дальше читают именно оттуда (вместо повторного DB-lookup'а).

Порядок важен: setup_gate раньше, чтобы /p/* запросы при пустой БД сразу редиректились в /setup, а не пытались резолвить slug по пустой таблице.

## Синглтоны на `app.state`

| Атрибут | Тип | Где создаётся |
|--------|------|------|
| `settings` | `AppSettings` (Pydantic) | main.py:30 |
| `db` | `SqliteDB` | main.py:31 |
| `projects` | `ProjectsService` | main.py:33 |
| `templates` | `Jinja2Templates` | main.py:34 |
| `i18n` | `I18n` | main.py:35 |
| `process_manager` | `ProcessManager` | main.py:41 |
| `orchestration_hub` | `OrchestrationHub` | main.py:43 |
| `harness_clients` | `HarnessClientCache` | main.py:44 |
| `scheduler` | `AsyncIOScheduler` | main.py:45 |
| `resolver_factory` | `Callable[[Request], ConfigResolver]` | main.py:50 |
| `orchestration_tails` | `dict[run_id, Task]` | создаётся ленивo в [`project_orchestration.py:118`](../dreaming/routes/project_orchestration.py) |
| `orchestration_watchers` | `dict[run_id, Task]` | создаётся ленивo в [`project_orchestration.py:136`](../dreaming/routes/project_orchestration.py) |

Помни: `ConfigResolver` НЕ синглтон, он создаётся на каждый request через `resolver_factory(request)`. Это сделано чтобы кэш `_cache: dict[int, dict]` per-request не накапливался.

## URL-routing и project resolver

Реестр роутеров — в `main.py` строки 74–80:

```
/        ->  root_router            (dashboard, /health, /locale, /ai-usage)
/setup   ->  setup_router           (wizard)
/projects ->  projects_router       (CRUD проектов)
/settings ->  settings_router       (глобальные настройки)
/api/*   ->  api_router             (sessions, orchestration, cascade)
/p/*     ->  project_router         (агрегатор 19 sub-роутеров /p/{slug}/*)
/static  ->  StaticFiles            (CSS/JS)
```

Все `/p/{slug}/...` роуты получают `project` через `request.state.project` (его раньше выставил `project_resolver_middleware`). Если бы они сами доставали slug, было бы N+1 — middleware экономит lookup.

Внутри `project_router`:

- См. [`dreaming/routes/project_router.py`](../dreaming/routes/project_router.py) — он только агрегирует 19 sub-роутеров через `include_router`.
- Подробный реестр маршрутов — в [`routes.md`](routes.md).

## Concurrency model

ProcessManager держит словарь `running: dict[str, RunningSession]` с composite key:

- `"{project_slug}:{agent_name}"` — для `start_session` (self-study).
- `"cmd:{project_slug}:{command_name}"` — для `start_command` (slash-команды и raw).

При spawn'е:
1. `start_session/start_command` проверяет `if key in self.running: raise`. Перевычисляет `len(self.running) >= max_concurrent`.
2. Заранее создаёт DB-row через `db.create_session(project_id, agent_name, model)` — чтобы у нас был ID до спавна (process_manager.py:142).
3. `asyncio.create_subprocess_exec(claude, "-p", prompt, ...)` с пайпом stdout, `stderr=STDOUT`, лимитом 16MB.
4. Создаёт `_reader_task` (читает stdout, fan-out в subscribers' queues — это SSE) и `_watchdog_task` (убивает при `timeout_minutes` тишины).
5. `keep_awake.acquire()` — подкручивает Windows ExecutionState чтобы система не уходила в Modern Standby.

При завершении:
- `_read_stdout` доезжает до EOF, шлёт sentinel `None` всем subscriber'ам, вызывает `_cleanup`.
- `_cleanup` удаляет сессию из `running`, `keep_awake.release()`, и (если не `cmd:*`) запускает `db.reconcile_stale_sessions()` чтобы закрыть orphaned DB-rows у которых процесс умер.
- Watchdog отдельно: каждые `min(60, timeout_minutes*60)` секунд проверяет `time.time() - last_stdout_at`. Если есть pending question (запись в `orchestrator_questions` со статусом `pending`) — сбрасывает счётчик (это валидное состояние ожидания ответа пользователя).

Reconcile job на 5-минутном interval'е (scheduler.py:223) собирает `(project_id, agent_name)` пары из in-memory `pm.running`, передаёт в `pm.reconcile_stale_sessions(active_pairs)`. Сервер ничего не знает о том, что Claude умер сам — `_cleanup` это и закроет.

Дополнительно: при `start_session` через [`project_orchestration.py:84`](../dreaming/routes/project_orchestration.py) спавнятся:
- `ClaudeSessionTail` — таск который читает Claude jsonl-файл и переливает его в `orchestrator_messages`.
- `SubagentWatcher` — таск который смотрит за `subagents/agent-*.meta.json` и спавнит child tail на каждый sub-агент.

Эти таски сохраняются в `app.state.orchestration_tails` / `app.state.orchestration_watchers` (per-run).

## Файловая раскладка

```
dreaming/
+-- main.py                    # FastAPI app, lifespan, middleware, router mount
+-- config.py                  # AppSettings (92 поля) + SETTINGS_GROUPS (13 групп)
+-- middleware/
|   +-- setup_gate.py          # /setup redirect когда БД пустая
|   +-- project_resolver.py    # /p/{slug}/ -> request.state.project
+-- routes/
|   +-- root.py                # / + /health + /locale + /ai-usage
|   +-- setup.py               # /setup wizard
|   +-- projects.py            # /projects CRUD (toggle, delete, import)
|   +-- settings.py            # /settings global form
|   +-- api.py                 # /api/* (sessions + orchestration + cascade)
|   +-- project_router.py      # агрегатор /p/{slug}/* sub-роутеров
|   +-- project_dashboard.py   # /p/{slug}/
|   +-- project_live.py        # /p/{slug}/live + SSE stream + kill
|   +-- project_rotation.py    # /p/{slug}/rotation
|   +-- project_settings.py    # /p/{slug}/settings (per-project overrides)
|   +-- project_orchestration.py
|   +-- project_topics.py      # weekly-learning-checklist
|   +-- project_kanban.py      # custom_topics CRUD
|   +-- project_notes.py       # learning-notes browser
|   +-- project_findings.py    # tech-debt list+detail+close+delete
|   +-- project_tech_debt.py   # tech-debt aggregate
|   +-- project_ideas.py       # product ideas + Jira
|   +-- project_wiki.py        # wiki status + bootstrap button
|   +-- project_ai_usage.py    # per-project token usage
|   +-- project_evolutions.py
|   +-- project_loops.py
|   +-- project_plans.py
|   +-- project_cascade_costs.py
|   +-- project_contracts.py
|   +-- project_sidecar_findings.py
+-- services/
|   +-- db.py                  # SqliteDB + _SCHEMA + _migrate_orchestration + ~30 domain methods
|   +-- projects.py            # ProjectsService + scan_projects_root
|   +-- config_resolver.py     # ConfigResolver (override-with-fallback)
|   +-- process_manager.py     # claude CLI spawn / SSE / watchdog / reconcile
|   +-- keep_awake.py          # Windows SetThreadExecutionState refcount
|   +-- scheduler.py           # _PER_PROJECT_JOBS, build_scheduler
|   +-- orchestration_hub.py   # runs/nodes/messages/stages/verdicts/artifacts
|   +-- claude_session_tail.py # JSONL tail-watcher
|   +-- subagent_watcher.py    # subagents/ folder watcher
|   +-- subagent_backfill.py   # offline replay
|   +-- harness_client.py      # HTTP/SSE harness adapter
|   +-- cascade_stage_detect.py # heuristic agent_name -> stage
|   +-- tts_backfill.py        # stub Wave 3.9
|   +-- ai_usage_parser.py     # JSONL -> ai_usage_events
|   +-- ai_usage_stats.py      # aggregate dashboards
|   +-- tech_debt.py           # parser + close/delete
|   +-- product_ideas.py       # parser
|   +-- contracts.py           # parser
|   +-- sidecar_findings.py    # JSON parser
|   +-- wiki_data.py           # WikiStatus
|   +-- evolutions.py          # markdown parser
|   +-- loops.py               # markdown parser
|   +-- plans.py               # markdown parser + checkbox progress
|   +-- cascade_costs.py       # cost roll-up
|   +-- notes.py               # learning-notes lister + safe reader
|   +-- checklist.py           # weekly checklist parser
|   +-- agents.py              # discover .claude/agents/
|   +-- jira.py                # create_task для Jira REST API v3
|   +-- i18n.py                # I18n + russian_plural / english_plural
+-- templates/
|   +-- base.html
|   +-- _navbar.html
|   +-- _project_layout.html
|   +-- index_dashboard.html
|   +-- project_*.html         # ~20 страниц
+-- i18n/
|   +-- messages_ru.json
|   +-- messages_en.json
+-- static/
    +-- app.css                # дополнительный CSS поверх Tailwind CDN
```

Корень репо:

```
+-- pyproject.toml             # editable install, deps
+-- config.yaml                # рабочий конфиг (создаётся wizard'ом)
+-- config.example.yaml        # шаблон
+-- data/dreaming.db           # SQLite (создаётся при connect())
+-- scripts/                   # smoke-сценарии (нет test framework, см. development.md)
+-- docs/                      # эта документация
```

## Cross-references

- Подробнее про БД: [`schema.md`](schema.md).
- Про каждый сервис отдельно: [`services.md`](services.md).
- Про каждый роут с кодом ответа: [`api.md`](api.md), [`routes.md`](routes.md).
- Про настройки и override-цепочку: [`configuration.md`](configuration.md), [`features/settings.md`](features/settings.md).
- Про deployment, persistent run и backup: [`deployment.md`](deployment.md).
- Про i18n: [`features/i18n.md`](features/i18n.md).
- Про multi-project resolver и setup wizard: [`features/multi-project.md`](features/multi-project.md).
