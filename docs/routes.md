# Route Inventory

Полный реестр HTTP-маршрутов. Сгруппирован по prefix'у. Каждый маршрут указывает:

- HTTP-метод и путь.
- Описание поведения.
- Связанный шаблон (если render).
- Используемые сервисы.
- Source: file:line.

## Содержание

- [Корневые](#корневые)
- [`/setup`](#setup)
- [`/projects`](#projects)
- [`/settings`](#settings)
- [`/api/`](#api)
- [`/p/{slug}/`](#pslug)
- [`/static/`](#static)
- [Зарезервированные пути](#зарезервированные-пути)

## Корневые

Source: [`dreaming/routes/root.py`](../dreaming/routes/root.py).

| Method | Path | Описание | Template | Source |
|---|---|---|---|---|
| GET | `/health` | Простой health-check `{"ok": true}`. | — | root.py:12 |
| GET | `/` | Aggregated dashboard: per-project cards (week_stats, running, td_count, ideas_count, wiki_present), top-line totals, active runs aside. | `index_dashboard.html` | root.py:17 |
| GET | `/ai-usage` | Глобальный AI Usage (через `ai_usage_stats.global_summary`). | `global_ai_usage.html` | root.py:109 |
| POST | `/locale` form `locale=&next=` | Set cookie `dc_locale`, max-age 1 год, samesite=lax. | — | root.py:126 |

`/` собирает данные через:
- `db.week_stats(proj.id)`.
- `pm.list_running()` фильтруется по `pfx = f"{slug}:"` или `cmd:{slug}:`.
- `ConfigResolver.get(proj, "tech_debt_dir", "")` + `list_tech_debt(td_dir)` если path существует.
- То же для `product_ideas_dir` и `wiki_dir`.

Заметь: при отсутствии `working_dir` или директорий fallback'ит на 0/false; не падает (root.py:60–61).

## `/setup`

Source: [`dreaming/routes/setup.py`](../dreaming/routes/setup.py).

| Method | Path | Описание | Source |
|---|---|---|---|
| GET | `/setup` | Render формы с defaults из текущего settings. | setup.py:24 |
| POST | `/setup` | Если `action=scan` — сканит `projects_root`, рендерит ту же страницу с найденными подпапками. Иначе — сохраняет global YAML, импортирует выбранные проекты, регистрирует cron jobs, редиректит на `/`. | setup.py:46 |

Form-поля при импорте:
- `claude_path`, `projects_root`, `default_locale` — global config.
- `scan_count` — сколько items пришло из scan.
- `slug_<i>`, `label_<i>`, `path_<i>`, `enabled_<i>`, `default_idx` — per-row.

`_save_global_yaml` (setup.py:14) делает merge с существующим `config.yaml` (создаёт если нет). После save вызывает `type(settings).load()` чтобы перезагрузить in-memory state (setup.py:83).

После `import_from_scan` для каждого нового проекта вызывает `register_project_jobs(scheduler, app_state, proj)` (setup.py:108–111).

`scan_error` рендерится если: путь пустой, или нет подпапок, или каталог не существует.

## `/projects`

Source: [`dreaming/routes/projects.py`](../dreaming/routes/projects.py).

| Method | Path | Описание | Source |
|---|---|---|---|
| GET | `/projects` | Список всех проектов. | projects.py:12 |
| POST | `/projects/{project_id}/toggle` | Toggle enabled. (un)register'ит per-project jobs. | projects.py:23 |
| POST | `/projects/{project_id}/delete` | Удаляет проект (CASCADE из БД); сначала `unregister_project_jobs`. | projects.py:40 |
| POST | `/projects/import` form `root=` | Бульк-import из ФС. | projects.py:50 |

Toggle (projects.py:32–36):
- new_enabled=True → `register_project_jobs`.
- new_enabled=False → `unregister_project_jobs`.

После toggle всегда возвращает 303 на `/projects`.

## `/settings`

Source: [`dreaming/routes/settings.py`](../dreaming/routes/settings.py).

| Method | Path | Описание | Source |
|---|---|---|---|
| GET | `/settings` | Render полной формы из `SETTINGS_GROUPS`. | settings.py:46 |
| POST | `/settings` | Сохраняет в `config.yaml`, перезагружает in-memory settings. | settings.py:57 |

`_coerce` (settings.py:29) приводит form-string обратно к типу default'а (bool/int/float/str).

Bool-поля: если key отсутствует в form, считается unchecked → False (settings.py:68–70). Это — стандартный HTML idiom для unchecked checkbox'а.

Token/api_key поля рендерятся как `type=password` (логика в шаблоне `settings.html`).

## `/api/`

Source: [`dreaming/routes/api.py`](../dreaming/routes/api.py).

| Method | Path | Описание | Source |
|---|---|---|---|
| POST | `/api/session/start` | Создать DB-row сессии. | api.py:43 |
| POST | `/api/session/finish` | Закрыть сессию + bump rotation.last_studied_at. | api.py:52 |
| POST | `/api/orchestration/start` | Создать run + root node + event. 409 если есть running и `enforce_single=true`. | api.py:91 |
| GET | `/api/orchestration/{run_id}` | Snapshot run + nodes + messages. | api.py:118 |
| POST | `/api/orchestration/{run_id}/nodes/{node_id}/message` | Записать message в node. | api.py:133 |
| POST | `/api/orchestration/{run_id}/finish` | Финиш run'а. | api.py:149 |
| POST | `/api/cascade/init` | Создать cascade run + 5 default стадий. | api.py:205 |
| POST | `/api/cascade/{run_id}/stage/start` | Старт стадии. | api.py:240 |
| POST | `/api/cascade/{run_id}/stage/finish` | Финиш стадии. | api.py:250 |
| POST | `/api/cascade/{run_id}/gate` | Gate verdict. | api.py:260 |
| POST | `/api/cascade/{run_id}/artifact` | Артефакт. | api.py:278 |
| POST | `/api/cascade/{run_id}/message` | Message в run. | api.py:294 |
| POST | `/api/cascade/{run_id}/finish` | Финиш cascade run'а. | api.py:314 |

Подробные body-схемы и curl-examples — в [`api.md`](api.md).

## `/p/{slug}/`

`project_resolver_middleware` ставит `request.state.project` для всех. Под '/p/' агрегатор-роутер собирает 19 sub-роутеров через `include_router`, см. [`dreaming/routes/project_router.py`](../dreaming/routes/project_router.py).

### Dashboard

Source: [`project_dashboard.py`](../dreaming/routes/project_dashboard.py).

| Method | Path | Описание | Template |
|---|---|---|---|
| GET | `/p/{slug}/` | week_stats + last 20 sessions + active running keys. | `project_dashboard.html` |

### Live + SSE

Source: [`project_live.py`](../dreaming/routes/project_live.py).

| Method | Path | Описание |
|---|---|---|
| GET | `/p/{slug}/live` | Список активных runs + кнопки Kill. |
| GET | `/p/{slug}/live/stream/{agent}` | SSE-stream stdout. Сначала шлёт catchup (всё что в `output_lines`), затем live. Sentinel `event: end`. |
| POST | `/p/{slug}/live/kill/{agent}` | Kill процесс. |

SSE отправляется через `EventSourceResponse(gen())` (project_live.py:44). Каждое событие: `{"event": "log", "data": line}`.

### Rotation

Source: [`project_rotation.py`](../dreaming/routes/project_rotation.py).

| Method | Path | Описание |
|---|---|---|
| GET | `/p/{slug}/rotation` | Roster. На входе авто-добавляет агентов из `list_agent_names(working_dir)` если нет в DB. |
| POST | `/p/{slug}/rotation/tier` form `agent_name=&tier=` | Tier ∈ {1, 2, 3}. |
| POST | `/p/{slug}/rotation/toggle` form `agent_name=` | Toggle enabled. |
| POST | `/p/{slug}/rotation/start/{agent}` | Start self-study session, redirect на `/p/{slug}/live`. 409 если уже running. |

`/rotation/start/{agent}` всегда передаёт env `DREAMING_PROJECT_SLUG` и `DREAMING_API_URL=http://localhost:{port}`.

### Settings (per-project)

Source: [`project_settings.py`](../dreaming/routes/project_settings.py).

| Method | Path | Описание |
|---|---|---|
| GET | `/p/{slug}/settings` | Форма, рендерит `is_overridden` + global value + override value для каждого ключа в SETTINGS_GROUPS. |
| POST | `/p/{slug}/settings` | Per-key action: `inherit` → `unset_setting`; `override` → `set_setting` (или `unset_setting` если text-value пустой). |

См. подробности в [`features/settings.md`](features/settings.md).

### Topics, Kanban, Notes

| Method | Path | Описание | Source |
|---|---|---|---|
| GET | `/p/{slug}/topics` | weekly-learning-checklist (read-only). | project_topics.py:10 |
| GET | `/p/{slug}/kanban` | Custom topics. | project_kanban.py:10 |
| POST | `/p/{slug}/kanban/add` | Add. | project_kanban.py:24 |
| POST | `/p/{slug}/kanban/{id}/delete` | Delete. | project_kanban.py:41 |
| GET | `/p/{slug}/notes` | List markdown notes. | project_notes.py:17 |
| GET | `/p/{slug}/notes/raw?path=` | Raw text; path-traversal-safe. | project_notes.py:33 |

### Findings (Tech-Debt)

Source: [`project_findings.py`](../dreaming/routes/project_findings.py), [`project_tech_debt.py`](../dreaming/routes/project_tech_debt.py).

| Method | Path | Описание |
|---|---|---|
| GET | `/p/{slug}/findings` | TD list. |
| GET | `/p/{slug}/findings/{id}` | TD detail. |
| POST | `/p/{slug}/findings/{id}/close` | Rewrite frontmatter `status: closed`. |
| POST | `/p/{slug}/findings/{id}/delete` | Unlink .md. |
| GET | `/p/{slug}/tech-debt` | Aggregate by_status + by_module. |

### Ideas

Source: [`project_ideas.py`](../dreaming/routes/project_ideas.py).

| Method | Path | Описание |
|---|---|---|
| GET | `/p/{slug}/ideas?status=` | List, filter by status. |
| POST | `/p/{slug}/ideas/{id}/jira` | Создать Jira Task; запоминает key в frontmatter `jira_ticket: RGS-123`. |

### Wiki

Source: [`project_wiki.py`](../dreaming/routes/project_wiki.py).

| Method | Path | Описание |
|---|---|---|
| GET | `/p/{slug}/wiki` | Status (через `get_wiki_status`). |
| POST | `/p/{slug}/wiki/bootstrap` | Запуск `/wiki-bootstrap` через `pm.start_command`. Redirect на `/p/{slug}/live`. |

### Orchestration

Source: [`project_orchestration.py`](../dreaming/routes/project_orchestration.py).

| Method | Path | Описание |
|---|---|---|
| GET | `/p/{slug}/orchestration` | Список runs (last 50). |
| GET | `/p/{slug}/orchestration/{run_id}` | Run detail с polling (через JS). |
| POST | `/p/{slug}/orchestration/start` form `goal=` | Создаёт run + root node, спавнит claude, запускает ClaudeSessionTail + SubagentWatcher. 409→редирект на existing run. |
| POST | `/p/{slug}/orchestration/{run_id}/finish` | Финиш run'а. |
| GET | `/p/{slug}/orchestration/{run_id}/refresh` | JSON polling. Возвращает `{status, finished_at, node_count, message_count, nodes, messages}`. |
| POST | `/p/{slug}/orchestration/{run_id}/resume` form `prompt=` | claude --resume + interactive_stdin. |

Подробнее — в [`features/orchestration.md`](features/orchestration.md).

### Analytics dashboards (read-only)

| Method | Path | Описание | Service |
|---|---|---|---|
| GET | `/p/{slug}/ai-usage` | Token usage. | `ai_usage_stats.project_summary` |
| GET | `/p/{slug}/cascade-costs` | Cost roll-up per run. | `cascade_costs.list_cascade_costs` |
| GET | `/p/{slug}/evolutions` | Agent _context overrides. | `evolutions.list_evolutions` |
| GET | `/p/{slug}/loops` | Reflex loops. | `loops.list_loops` |
| GET | `/p/{slug}/plans` | Plans с progress%. | `plans.list_plans` |
| GET | `/p/{slug}/contracts` | Module/page contracts. | `contracts.list_contracts` |
| GET | `/p/{slug}/sidecar-findings?severity=` | Sidecar reviewer JSON findings. | `sidecar_findings.list_sidecar_findings` |

Все следуют одинаковому паттерну (resolver → dir setting → list → render).

## `/static/`

Mounted в `main.py:80`:

```python
app.mount("/static", StaticFiles(directory="dreaming/static"), name="static")
```

Файлы: `dreaming/static/app.css`. Tailwind подгружается из CDN (см. `templates/base.html`).

## Зарезервированные пути

FastAPI auto-mount'ит:
- `/docs` — Swagger UI.
- `/redoc` — ReDoc.
- `/openapi.json` — OpenAPI schema.

**НЕ создавайте** свои роуты на этих путях — они тихо переопределятся. setup_gate их пропускает (см. [`middleware/setup_gate.py:8`](../dreaming/middleware/setup_gate.py)).

## Cross-references

- Полные body-схемы и curl-примеры — [`api.md`](api.md).
- Какие сервисы что делают — [`services.md`](services.md).
- Шаблоны и i18n — [`features/i18n.md`](features/i18n.md).
- Multi-project resolver — [`features/multi-project.md`](features/multi-project.md).
