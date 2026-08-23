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
- [`/articles`](#articles)
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
| POST | `/api/p/{slug}/articles/ingest` | Callback `/article-ideas-scan`: одно предложение статьи. 400 при пустом `evidence`, 422 при плохом `source`. `INSERT OR IGNORE` по `(project_id, slug_hint)` → 200 `duplicate:true`, иначе 201. | api.py:474 |
| GET | `/api/p/{slug}/articles/list` | Дедуп для скана: `[{id, slug_hint, title, status}]` по проекту. | api.py:634 |
| GET | `/api/articles/{proposal_id}` | Бриф для `/write-article`: вся строка `article_proposals`. | api.py:646 |
| POST | `/api/articles/{proposal_id}/written` | Callback `/write-article`. 409 если статус не `writing`. Успех → `drafted`; `{error_message}` → `failed`. | api.py:655 |
| POST | `/api/p/{slug}/creatives/ingest` | То же для `/creative-ideas-scan`. Тот же белый список `source`, тот же 400 на пустой evidence. | api.py:513 |
| GET | `/api/p/{slug}/creatives/list` | Дедуп для скана кампаний. | api.py:552 |
| GET | `/api/creatives/{proposal_id}` | Бриф для `/make-creative`. | api.py:565 |
| POST | `/api/creatives/{proposal_id}/made` | Callback `/make-creative`. 409 если статус не `making`. Успех → `drafted`; `{error_message}` → `failed`. | api.py:574 |

Подробные body-схемы и curl-examples — в [`api.md`](api.md) (кроме восьми
article/creative-строк выше — их контракт задокументирован в
[`features/articles.md`](features/articles.md) и
[`features/creatives.md`](features/creatives.md), а буквальный curl —
в самих командах `templates/starter-kit/commands/*.md`).

## `/articles`

Source: [`dreaming/routes/articles.py`](../../dreaming/routes/articles.py). Смонтирован в `main.py` без префикса, наравне с `ai_radar_router` — не под `/p/{slug}/`.

| Method | Path | Описание | Source |
|---|---|---|---|
| GET | `/articles` | Кросс-проектная очередь: все `article_proposals` в статусе `proposed`, по всем **включённым** проектам сразу (отключённый/удалённый проект — строка не показывается, хотя в БД остаётся). Бейдж проекта на каждой карточке. | articles.py:17 |
| POST | `/articles/scan` form `target_project=` | Ручной запуск `/article-ideas-scan` для выбранного проекта прямо отсюда, без захода в его собственную `/p/{slug}/articles`. Общая функция `dispatch_article_scan` с per-project кнопкой скана. | articles.py:50 |

Единственная кнопка на карточках здесь — Reject; согласовать статью можно
только на странице конкретного проекта. Подробнее — в
[`features/articles.md`](features/articles.md) и
[`user/features/articles.md`](user/features/articles.md).

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
| GET | `/p/{slug}/rotation` | Roster. На входе авто-добавляет агентов из `list_agent_names(working_dir)` если нет в DB. В контексте отдаёт `kit_status` (см. ниже). |
| POST | `/p/{slug}/rotation/tier` form `agent_name=&tier=` | Tier ∈ {1, 2, 3}. |
| POST | `/p/{slug}/rotation/toggle` form `agent_name=` | Toggle enabled. |
| POST | `/p/{slug}/rotation/start/{agent}` | Start self-study session, redirect на `/p/{slug}/live`. 409 если уже running. |

`/rotation/start/{agent}` всегда передаёт env `DREAMING_PROJECT_SLUG` и `DREAMING_API_URL=http://localhost:{port}`.

### Starter-kit

Source: [`project_rotation.py`](../dreaming/routes/project_rotation.py) (эндпоинт инсталлера живёт там по историческим причинам — путь нейтральный).

| Method | Path | Описание |
|---|---|---|
| POST | `/p/{slug}/starter-kit/install` form `force=&redirect_to=` | Копирует `templates/starter-kit/**` в `{working_dir}/.claude/`. `force=1` перезаписывает, иначе skip-if-exists. Редирект на `redirect_to` или Referer (same-origin: только `/p/{slug}*`). |

Используется и страницей Ротации, и страницей Темы — каждая шлёт собственный `redirect_to`, чтобы юзер вернулся туда, откуда стартовал.

См. [`services.md#starter_kit-py—установка-slash-команд`](services.md#starter_kitpy--установка-slash-команд) и [`user/features/out-of-the-box.md#starter-kit`](user/features/out-of-the-box.md#starter-kit).

### Dashboard actions

Source: [`project_dashboard.py`](../dreaming/routes/project_dashboard.py).

| Method | Path | Описание |
|---|---|---|
| GET | `/p/{slug}/` | Dashboard. Передаёт `sessions`, `active_keys`, `active_key_set`, `kit_status`, `missing_dirs`, `bootstrap_needed` в шаблон. |
| POST | `/p/{slug}/bootstrap-all` | Master-кнопка «из коробки»: `starter_kit.install(force=False)` + `autoconfig.apply_all_defaults(skip_existing=True)`. Идемпотентно. Same-origin редирект на Referer. |
| POST | `/p/{slug}/sessions/{session_id}/stop` | Stop: если процесс жив — `pm.kill(key)`, иначе `db.cancel_session(session_id)` (orphan). Редирект на `/p/{slug}/`. |
| POST | `/p/{slug}/sessions/{session_id}/delete` | Delete: kill процесс если жив, затем `db.delete_session(session_id)`. 404 если row не из этого проекта. |
| POST | `/p/{slug}/sessions/force-close-stale` | Массово ставит `status='cancelled'` всем running-row'ам проекта через `db.cancel_stale_running(project_id)`. Живые процессы не трогает. |

См. [`user/features/out-of-the-box.md#управление-сессиями`](user/features/out-of-the-box.md#управление-сессиями).

### Settings (per-project)

Source: [`project_settings.py`](../dreaming/routes/project_settings.py).

| Method | Path | Описание |
|---|---|---|
| GET | `/p/{slug}/settings` | Форма, рендерит `is_overridden` + global value + override value для каждого ключа в SETTINGS_GROUPS. |
| POST | `/p/{slug}/settings` | Per-key action: `inherit` → `unset_setting`; `override` → `set_setting` (или `unset_setting` если text-value пустой). |
| POST | `/p/{slug}/settings/autoconfig` form `key=&redirect_to=` | One-click: `mkdir -p` дефолтный путь для `key` (см. `autoconfig.DEFAULTS`), сохранить override. Same-origin редирект на `redirect_to` или Referer. 400 если `key` не из DEFAULTS. |

См. подробности в [`features/settings.md`](features/settings.md) и [`user/features/out-of-the-box.md#autoconfig-каталогов`](user/features/out-of-the-box.md#autoconfig-каталогов).

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
| POST | `/p/{slug}/ideas/{item_id}/propose-article` | Фидер article pipeline: idea → `article_proposals(source='center')`. Кнопка не гаснет после использования — повторный клик просто вернёт "дубликат". См. [`features/articles.md`](features/articles.md). | project_ideas.py:189 |

### Articles

Source: [`project_articles.py`](../../dreaming/routes/project_articles.py). Полное описание жизненного цикла, venue-резолюции и публикации — в [`features/articles.md`](features/articles.md); эта таблица — только инвентарь.

| Method | Path | Описание | Source |
|---|---|---|---|
| GET | `/p/{slug}/articles` | Предложения проекта, сгруппированные по статусу (`proposed/writing/drafted/published/rejected/failed` + `other`). | project_articles.py:87 |
| POST | `/p/{slug}/articles/add` form `title=&angle=&venue=` | Ручное предложение, `source='manual'`. Пустой `title` → 400. | project_articles.py:225 |
| POST | `/p/{slug}/articles/{id}/reject` | `proposed/... → rejected`. | project_articles.py:294 |
| POST | `/p/{slug}/articles/{id}/restore` | `rejected → proposed`. | project_articles.py:309 |
| POST | `/p/{slug}/articles/{id}/venue` form `venue=` | Меняет venue-override, пока строка ещё `proposed`. 409 после диспетча — venue уже "прибит". | project_articles.py:322 |
| POST | `/p/{slug}/articles/scan` | Диспетчит `/article-ideas-scan` в проект. Только предлагает — никогда не пишет и не публикует. | project_articles.py:399 |
| POST | `/p/{slug}/articles/{id}/approve` | Первый человеческий гейт: резолвит venue + корень блога, диспетчит `/write-article {id}` с `bypassPermissions`. 409, если статус не в `(proposed, approved, failed, drafted)`. | project_articles.py:408 |
| POST | `/p/{slug}/articles/{id}/cancel` | `writing → failed` вручную. Не убивает процесс. | project_articles.py:576 |
| POST | `/p/{slug}/articles/{id}/revise` form `notes=&finding=` | Пишет `revision_notes`, вызывает тот же код, что approve. 400 на пустой запрос. | project_articles.py:615 |
| GET | `/p/{slug}/articles/{id}/preview?lang=&file=` | Показывает рабочее дерево `draft_ref`, провалидированное тем же валидатором, что и publish. | project_articles.py:660 |
| POST | `/p/{slug}/articles/{id}/publish` | Второй гейт: коммитит только пути из `draft_ref` (+ `article_publish_extra_paths`). Терминальный переход в `published`. | project_articles.py:812 |

Четвёртый фидер живёт вне этого файла и вне `/p/{slug}` — `POST
/ai-radar/{finding_id}/propose-article` в
[`dreaming/routes/ai_radar.py`](../../dreaming/routes/ai_radar.py) (`source='radar'`,
evidence собирается из самой находки). AI Radar как раздел в этом инвентаре
отдельно не описан — см. [`features/articles.md`](features/articles.md#кто-подаёт-предложения).

### Creatives

Source: [`project_creatives.py`](../../dreaming/routes/project_creatives.py). Отличия от articles и общая механика — в [`features/creatives.md`](features/creatives.md).

| Method | Path | Описание | Source |
|---|---|---|---|
| GET | `/p/{slug}/creatives` | Кампании проекта по статусам (`proposed/making/drafted/published/rejected/failed` + `other`). | project_creatives.py:202 |
| POST | `/p/{slug}/creatives/scan` | Диспетчит `/creative-ideas-scan`. | project_creatives.py:267 |
| POST | `/p/{slug}/creatives/add` multipart `title=&angle=&venue=&formats=&locales=&files=` | Ручное предложение **с вложениями одним шагом** — единственное отличие формы от articles. | project_creatives.py:305 |
| POST | `/p/{slug}/creatives/{id}/attach` multipart `files=` | Прикрепить материал в `<slug>/src/`. 409, пока кампания в `making`. | project_creatives.py:409 |
| POST | `/p/{slug}/creatives/{id}/approve` | Диспетчит `/make-creative {id}` с `bypassPermissions`. | project_creatives.py:450 |
| POST | `/p/{slug}/creatives/{id}/cancel` | `making → failed` вручную. См. [Известный пробел: reconcile не подключён](features/creatives.md#известный-пробел-reconcile-не-подключён) — авто-recovery, в отличие от статей, нет. | project_creatives.py:526 |
| POST | `/p/{slug}/creatives/{id}/reject` | `proposed/failed → rejected`. | project_creatives.py:541 |
| POST | `/p/{slug}/creatives/{id}/restore` | `rejected → proposed`. | project_creatives.py:554 |
| POST | `/p/{slug}/creatives/{id}/venue` form `venue=` | Меняет venue, пока `proposed`/`failed`. | project_creatives.py:565 |
| GET | `/p/{slug}/creatives/{id}/preview?fmt=&loc=` | Вкладки `(формат, локаль)`, рендеры + текст поста. | project_creatives.py:587 |
| GET | `/p/{slug}/creatives/{id}/media?path=` | Отдаёт один рендер/вложение — только то, что строка сама назвала в `draft_ref` или список своих вложений, только из белого списка расширений (без `.svg`). | project_creatives.py:668 |
| POST | `/p/{slug}/creatives/{id}/revise` form `notes=&finding=` | То же, что у articles: находки + текст → `revision_notes`, вызов approve. | project_creatives.py:716 |
| POST | `/p/{slug}/creatives/{id}/publish` | Тот же `article_publish.publish`, что у статей. 409, если `draft_ref` пуст. | project_creatives.py:742 |

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
