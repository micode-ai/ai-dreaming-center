# AI Dreaming Center — Технический индекс документации

Карта документов под `docs/`. Если ты знакомишься с кодовой базой впервые — читай в порядке списка. Все ссылки — относительные от этого файла.

## User documentation

End-user-oriented guides under `docs/user/`. Read these if you want to USE the tool, not modify it.

- [user/README.md](user/README.md) — index of user-facing docs
- [user/getting-started.md](user/getting-started.md) — first-time setup walkthrough
- [user/overview.md](user/overview.md) — what is AI Dreaming Center, who it's for
- [user/faq.md](user/faq.md) — frequently asked questions
- [user/glossary.md](user/glossary.md) — terminology

Per-feature user guides under `user/features/`; typical workflows under `user/workflows/`.

## Назначение проекта

`ai-dreaming-center` (DC) — мульти-проектный FastAPI-дашборд, который оркеструет команды агентов Claude CLI поверх произвольного множества локальных проектов. Это форк `agent-learning-center` (ALC), расширенный first-class multi-project поддержкой, оркестрацией Романа (cascade pipelines), сборкой AI Usage и unified analytics.

Серверный процесс крутится на порту `8086` по умолчанию (см. [`config.example.yaml`](../config.example.yaml)). Главный процесс — один `uvicorn` с asyncio loop'ом, один persistent SQLite connection (WAL), один `APScheduler.AsyncIOScheduler`, один `ProcessManager` (управляет subprocess'ами `claude` CLI), плюс orchestration hub.

## Карта документов

### Базовый уровень — обязательно к прочтению

| Файл | О чём |
|------|------|
| [`architecture.md`](architecture.md) | Высокоуровневая архитектура: lifespan, middleware, синглтоны, диаграммы. |
| [`schema.md`](schema.md) | Все 16 SQLite-таблиц: колонки, индексы, FK-каскады, идемпотентные миграции. |
| [`api.md`](api.md) | REST API: sessions, orchestration, cascade pipelines, form-based actions, health. |
| [`services.md`](services.md) | Layer слой: каждый сервис, его публичный API, депенденси. |
| [`routes.md`](routes.md) | Маршрутный реестр (19 модулей), сгруппированный по URL prefix. |
| [`configuration.md`](configuration.md) | Все 92 ключа настроек, сгруппированы в 13 категорий, defaults, override scope. |

### Эксплуатация и развитие

| Файл | О чём |
|------|------|
| [`deployment.md`](deployment.md) | Запуск, persistent run (Task Scheduler/NSSM/systemd), backup, monitoring. |
| [`development.md`](development.md) | Конвенции, как добавлять страницу/настройку/cron/парсер, i18n discipline, Git. |
| [`waves.md`](waves.md) | История Wave 0..5 с git-тегами, что вошло в каждую волну, что было отложено. |
| [`troubleshooting.md`](troubleshooting.md) | Типовые проблемы с диагностическими командами. |

### Глубже — по фичам

| Файл | О чём |
|------|------|
| [`features/self-study.md`](features/self-study.md) | Ночное самообучение агентов: rotation, cron, sessions API, slash-command env. |
| [`features/orchestration.md`](features/orchestration.md) | Roman runs, ClaudeSessionTail, SubagentWatcher, resume, backfill. |
| [`features/cascade.md`](features/cascade.md) | Cascade pipelines: stages, gate verdicts, artifacts, harness adapter. |
| [`features/pipelines.md`](features/pipelines.md) | TD/Ideas/Wiki/Sidecar/Contracts/Topics/Kanban/Notes — read-only пайплайны. |
| [`features/analytics.md`](features/analytics.md) | AI Usage, Cascade Costs, Evolutions, Loops, Plans. |
| [`features/settings.md`](features/settings.md) | Глобальные + per-project настройки, override-with-fallback, ConfigResolver. |
| [`features/i18n.md`](features/i18n.md) | RU/EN, key parity, CLDR plurals, Jinja `t()` filter. |
| [`features/multi-project.md`](features/multi-project.md) | Resolver middleware, registry, setup wizard, agg dashboard. |

## Где источник истины

Сами тексты документов были собраны из:

1. Спецификации [`docs/superpowers/specs/2026-05-09-ai-dreaming-center-design.md`](superpowers/specs/2026-05-09-ai-dreaming-center-design.md).
2. Кода под `dreaming/` (он первичен — если doc и код расходятся, верь коду).
3. Истории `git log` (для волн).

## Глоссарий

- **DC** — AI Dreaming Center, этот проект.
- **ALC** — agent-learning-center, single-project предок.
- **Roman** — корневой агент-оркестратор; в коде `agent_name="roman"`, `role="orchestrator"`.
- **Cascade** — конвейер из 5 стадий: contract → design → implementation → review → qa.
- **Run** — одна оркестрация (`orchestrator_runs.id` — UUID, `external_id` — Claude session UUID).
- **Node** — узел оркестрации, агент в run'е (`orchestrator_nodes`).
- **Subagent** — child Claude process, спавнится через Task/Agent tool, jsonl лежит под `~/.claude/projects/<workdir>/<session>/subagents/agent-<hash>.jsonl`.
- **Project (DC project)** — запись в `projects` таблице, не путать с Claude project (папкой под `~/.claude/projects/`).

## Локальная навигация

```
docs/
+-- README.md                # этот файл
+-- architecture.md
+-- api.md
+-- schema.md
+-- services.md
+-- routes.md
+-- configuration.md
+-- deployment.md
+-- development.md
+-- waves.md
+-- troubleshooting.md
+-- smoke-tests.md            # уже существовал (smoke-сценарии под scripts/)
+-- features/
|   +-- self-study.md
|   +-- orchestration.md
|   +-- cascade.md
|   +-- pipelines.md
|   +-- analytics.md
|   +-- settings.md
|   +-- i18n.md
|   +-- multi-project.md
+-- superpowers/
    +-- specs/2026-05-09-ai-dreaming-center-design.md
```

## Изменения в документации

Документы оформляют состояние Waves 0..5 (тег `wave-5`, последний коммит `b49aafd` — Wave 3.9 финиш). Если ты вносишь изменения в код после этой даты — обнови соответствующий раздел и cross-ref.
