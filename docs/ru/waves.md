# Waves history

История разработки AI Dreaming Center: что было сделано в каждой волне, какой git-тег, что было отложено.

## Содержание

- [Wave 0 — Foundation](#wave-0--foundation)
- [Wave 1 — Self-study core](#wave-1--self-study-core)
- [Wave 2 — Pipeline pages](#wave-2--pipeline-pages)
- [Wave 2.5 — Tech-debt + Jira + Wiki bootstrap](#wave-25--tech-debt--jira--wiki-bootstrap)
- [Wave 3 lean — OrchestrationHub](#wave-3-lean--orchestrationhub)
- [Wave 3.6 — claude_session_tail / subagent_watcher / backfill](#wave-36--claude_session_tail--subagent_watcher--backfill)
- [Wave 3.7 — orchestration spawns claude](#wave-37--orchestration-spawns-claude)
- [Wave 3.8 — cascade pipelines API](#wave-38--cascade-pipelines-api)
- [Wave 3.9 (Wave 3 full) — contracts + sidecar + tts stub](#wave-39-wave-3-full--contracts--sidecar--tts-stub)
- [Wave 4 lite — AI Usage analytics](#wave-4-lite--ai-usage-analytics)
- [Wave 4 full — evolutions / loops / plans / cascade-costs](#wave-4-full--evolutions--loops--plans--cascade-costs)
- [Wave 5 — aggregated dashboard](#wave-5--aggregated-dashboard)
- [Wave D1/D2 — Design system foundation](#wave-d1d2--design-system-foundation)
- [Не реализованные пока](#не-реализованные-пока)

## Wave 0 — Foundation

**Тег**: `wave-0`. Acceptance commit'ы: `c9800b3` (skeleton) → `efaef43` (smoke OK).

**Цель**: минимальный FastAPI app со схемой БД, middleware'ами и стартовым setup wizard'ом.

**Что вошло**:
- Skeleton проекта: `pyproject.toml`, `dreaming/main.py`, `dreaming/__init__.py`.
- Минимальный FastAPI app на 8086 с `/health` (`96795d4`).
- SQLite schema fork из ALC + `project_id` (`5ee789b`).
- ProjectsService — CRUD + scan_projects_root (`c1cfc2e`).
- ConfigResolver — override-with-fallback (`10ae4fe`).
- setup_gate + project_resolver middleware + `project_not_found.html` (`2200281`).
- i18n loader + Jinja `t()` + CLDR Russian plurals (`3860dee`).
- Key-parity verifier `scripts/check_i18n.py` (`5da55c8`).
- Setup wizard: global config + projects_root scan + bulk import (`a529c9c`).
- /projects list, toggle, delete, import (`c174a89`).
- /settings минимальный UI (`e1f0843`).
- Stub services + минимальный scheduler (`df1849f`).
- End-to-end smoke (`efaef43`).

**Acceptance**: app стартует, wizard работает, проекты регистрируются, идемпотентный import.

**Отложено**:
- Реальный ProcessManager (Wave 1).
- Sessions API (Wave 1).
- Pipeline pages (Wave 2).

## Wave 1 — Self-study core

**Тег**: `wave-1`. Acceptance commit'ы: `a6ed585` → `b7824f9`.

**Цель**: ночное самообучение + per-project dashboard + sessions REST API.

**Что вошло**:
- Port `keep_awake.py` из ALC (`1743d9a`).
- Port ProcessManager + project_id awareness (`a6ed585`).
- SqliteDB session/rotation domain methods (`79ac75f`).
- /api/session/start|finish (`e0e87cf`).
- Project-scoped роуты `/p/{slug}/{,live,rotation}` + agents discovery (`6ef210f`).
- /p/{slug}/settings минимальный UI (`651afcb`).
- per-project nightly_learning_{slug} cron + register/unregister hooks (`5f9855e`).
- End-to-end smoke (`b7824f9`).

**Acceptance**:
- Session API работает в multi-project режиме.
- Dashboard рендерит week_stats.
- Rotation page с tier/enabled inline edit.
- Live SSE streaming.
- Nightly cron срабатывает и стартует claude.

**Отложено**:
- Pipeline pages (Wave 2).
- Topics, Kanban, Notes (Wave 2.1).

## Wave 2 — Pipeline pages

**Тег**: `wave-2`. Acceptance commits: `3b9995b`, `87fc009`, `f3270d3`, `8bd34b8`, `5a6f5b4`.

**Цель**: read-only страницы для всех ALC pipelines.

**Что вошло**:
- Wave 2.1 (3b9995b): Topics, Kanban, Notes.
- Wave 2.2 (87fc009): tech-debt parser + /findings + /tech-debt minimal.
- Wave 2.3+2.4 (f3270d3): Product Ideas board + Wiki bootstrap status.
- Wave 2.5 weekly_*_{slug} cron kinds + start_command project-scoping (8bd34b8).
- Smoke E2E для всех 7 pipeline pages (5a6f5b4).

**Acceptance**:
- Каждая pipeline страница рендерится без 500 (даже если dir пустой).
- weekly_tech_debt_scan_{slug} регистрируется при `weekly_tech_debt_scan_enabled=true`.

**Отложено**:
- TD detail / close / delete (Wave 2.5).
- Jira integration (Wave 2.5).
- Wiki bootstrap button (Wave 2.5).

## Wave 2.5 — Tech-debt + Jira + Wiki bootstrap

**Тег**: `wave-2.5`. Acceptance commit: `e39a0fe`.

**Цель**: actionable действия из UI на pipeline-страницах.

**Что вошло**:
- TD detail page (`/p/{slug}/findings/{id}`).
- TD close (rewrite frontmatter `status: closed`).
- TD delete (unlink файла).
- Jira service (`dreaming/services/jira.py`).
- Ideas → Jira кнопка с persist'ом `jira_ticket: <key>` в frontmatter.
- Wiki bootstrap button — `/p/{slug}/wiki/bootstrap` POST → `pm.start_command("/wiki-bootstrap")`.

**Acceptance**:
- Кнопки реально что-то делают.
- Per-project `jira_project_key` override работает.
- Wiki bootstrap появляется в `/p/{slug}/live` через несколько секунд.

## Wave 3 lean — OrchestrationHub

**Тег**: `wave-3-lean`. Acceptance commit: `dcec547`.

**Цель**: DB-backed runs/nodes/messages для Roman flows + минимальный набор API endpoint'ов + UI для просмотра.

**Что вошло**:
- `OrchestrationHub` real impl: create_run, create_node, append_message, finish_run, ensure_stage, append_event и т.д.
- 4 базовых API endpoints: `/api/orchestration/start`, `/{run_id}`, `.../message`, `/finish`.
- /p/{slug}/orchestration list page.
- /p/{slug}/orchestration/{run_id} detail page.
- One-Roman-per-project lock в `has_running_run` + 409.

**Acceptance**:
- Можно создать run руками через curl и увидеть его в UI.
- Lock не позволяет создать второй параллельный run.

**Отложено**:
- Spawn claude из POST /start (Wave 3.7).
- ClaudeSessionTail (Wave 3.6).
- SubagentWatcher (Wave 3.6).
- Cascade stages API (Wave 3.8).
- TTS, sidecar, contracts (Wave 3.9).

## Wave 3.6 — claude_session_tail / subagent_watcher / backfill

**Тег**: (нет отдельного, входит в `wave-3-full` пик). Commit: `75e67b0`.

**Цель**: реальная имплементация tail-watcher'ов для Claude jsonl-файлов.

**Что вошло**:
- `dreaming/services/claude_session_tail.py` — `tail_session_file`, `ClaudeSessionTail`, helpers (encode_workdir, find_session_file_by_id, find_recent_session_files и т.д.).
- `dreaming/services/subagent_watcher.py` — `watch_subagents_for_run`, `SubagentWatcher`, `_resolve_node_for_subagent`.
- `dreaming/services/subagent_backfill.py` — `backfill_run` для offline replay.

**Acceptance**:
- Запускаешь run, файл `~/.claude/projects/<workdir>/<session>.jsonl` обновляется live, сообщения появляются в БД.

**Отложено**: spawning claude из form-based start (Wave 3.7).

## Wave 3.7 — orchestration spawns claude

**Commit**: `f13babe`.

**Цель**: form-based кнопка «Start Orchestration» теперь реально стартует claude и подвешивает watchers.

**Что вошло**:
- `POST /p/{slug}/orchestration/start` форма принимает `goal` и:
  - Создаёт run + root_node.
  - Спавнит claude через `pm.start_command(session_id=claude_session_id)`.
  - Стартует `ClaudeSessionTail` + `SubagentWatcher` через `asyncio.create_task`.
  - Сохраняет таски в `app.state.orchestration_tails` и `orchestration_watchers`.
- `GET /refresh` — JSON для polling из браузера.
- `POST /resume` — `claude --resume <session_id>` + `interactive_stdin=True`.

**Acceptance**:
- Жмёшь Start, через секунды появляются messages в детальной странице.
- Resume работает с прошлым session_id.

## Wave 3.8 — cascade pipelines API

**Commit**: `f59a8ea`.

**Цель**: API для cascade pipelines (5 стадий с gates и артефактами).

**Что вошло**:
- 7 endpoint'ов под `/api/cascade/`:
  - `init` (создание run + 5 default стадий).
  - `stage/start`, `stage/finish`.
  - `gate` (verdict).
  - `artifact` (с dedup_hash).
  - `message`.
  - `finish`.
- `dreaming/services/harness_client.py` — `HarnessClient` + `HarnessClientCache`.
- `dreaming/services/cascade_stage_detect.py` — heuristic detector.

**Acceptance**:
- `curl /api/cascade/init` создаёт run и 5 стадий.
- `dedup_hash` коллизия возвращает `{"id": null, "deduped": true}`.

**Отложено**: starter-kit slash-команды `/cascade-task` и `/cascade-contract` — это часть external project'а, не DC.

## Wave 3.9 (Wave 3 full) — contracts + sidecar + tts stub

**Тег**: `wave-3-full`. Commit: `b49aafd`.

**Цель**: финализация Wave 3 — добавить contracts page, sidecar findings page, tts_backfill stub.

**Что вошло**:
- `dreaming/services/contracts.py` + route + template.
- `dreaming/services/sidecar_findings.py` + route + template.
- `dreaming/services/tts_backfill.py` (stub).

**Acceptance**:
- /p/{slug}/contracts и /p/{slug}/sidecar-findings рендерятся.

**Отложено**:
- Реальный TTS backfill (stub возвращает 0).
- AskUserQuestion полная обвязка (table создан в migration, но full API ещё нет).

## Wave 4 lite — AI Usage analytics

**Тег**: `wave-4-lite`. Commit: `1c84f44a`/`1c84f44`/`1c84f44` — фактически `1c8...` (см `git log --grep "Wave 4 lite"`). Тэг вешает `1c8`.

**Цель**: per-project + global token usage.

**Что вошло**:
- `dreaming/services/ai_usage_parser.py` — incremental JSONL → `ai_usage_events`.
- `dreaming/services/ai_usage_stats.py` — `project_summary`, `global_summary`.
- `/p/{slug}/ai-usage` route + template.
- `/ai-usage` global route + template.
- ingest cron (every 5 min).

**Acceptance**:
- В таблице `ai_usage_events` появляются rows после первого ingest'а.
- Dashboard показывает last_7d / last_30d totals + by_model.

## Wave 4 full — evolutions / loops / plans / cascade-costs

**Тег**: `wave-4-full`. Commit: `9841f53`.

**Цель**: ещё 4 read-only dashboard'а.

**Что вошло**:
- `dreaming/services/evolutions.py` + route + template.
- `dreaming/services/loops.py` + route + template.
- `dreaming/services/plans.py` + route + template (с progress%).
- `dreaming/services/cascade_costs.py` + route + template.
- Full ~80-key settings UI grouped by category (`4a44f02`).

**Acceptance**:
- Все 4 страницы рендерятся.
- Per-project + global settings UI отображает все 80+ ключей.

## Wave 5 — aggregated dashboard

**Тег**: `wave-5`. Commit: `d33bd3c`.

**Цель**: главная страница `/` показывает per-project cards + global totals + active runs.

**Что вошло**:
- `index_dashboard.html` template.
- `root.py:index` собирает stats для всех проектов одной handler-функцией.
- Cross-project metrics: total success/failed/timeout/running, sum td/ideas, wiki_present.
- Active runs aside.
- README/CLAUDE.md финал.

**Acceptance**:
- `/` рендерит N cards (по числу enabled проектов).
- Active running keys отображаются.

## Wave D1/D2 — Design system foundation

**Тег**: `design-system`. Merge-коммит `83df347`, диапазон `666c72b`..`5aebaa5` — 80 коммитов, 56 файлов, +2719/−1670.

**Спек**: [`docs/superpowers/specs/2026-08-16-design-system-foundation-design.md`](../superpowers/specs/2026-08-16-design-system-foundation-design.md)
**План**: [`docs/superpowers/plans/2026-08-16-design-system-foundation.md`](../superpowers/plans/2026-08-16-design-system-foundation.md)

**Проблема**: токены в `app.css` существовали, но шаблоны их почти не использовали. Внешний вид был закодирован прямо в разметке — **491 статический инлайновый `style=`** и **464 светлотемные утилиты Tailwind** (`bg-white`, `text-slate-900`, `border-slate-200`), унаследованные при портировании из ALC. Блок из ~50 правил с `!important` в конце `app.css` натягивал тёмную тему на те утилиты, которые кто-то не забыл пропатчить. Непропатченные рендерились светлыми.

**Результат**:

| | До | После |
|---|---|---|
| Статические инлайновые `style=` | 491 | **0** |
| Светлотемные цветовые утилиты | 464 | **0** |
| `!important` в `dreaming/static/` | ~50 | **0** |
| Классы кнопок | 0 (100+ вариаций разметки) | `.btn` + 5 вариантов |

**Что вошло**:

- **Разделение таблиц стилей** на три файла с жёсткими границами: [`tokens.css`](../../dreaming/static/tokens.css) — только `:root` (89 токенов, единственное место, где живёт внешний вид); [`components.css`](../../dreaming/static/components.css) — семантические классы, ни одного цветового литерала; [`app.css`](../../dreaming/static/app.css) — база, элементы форм, шелл сайдбара, `.md-content`.
- **Слой компонентов**: `.btn` (+ `primary` / `danger` / `warn` / `ghost` / `success` / `sm`), `.card`, `.panel`, `.banner` (+ `info` / `warn` / `danger` / `brand` / `--inline`), `.page-header`, `.section-title`, `.toolbar`, `.empty-state`, `.field`, `.num`, `.data-table.is-dense`, `.meter-track` / `.meter-fill`, `.filter-tab`, `.stat-chip`, `.rubric-tile`, `.queue-item`.
- **Миграция всех 51 шаблона** — шелл, три экрана-приёмки (дашборд, оркестрация, находки), затем пачками.
- **Удаление `!important`-блока** последним коммитом, за зелёными воротами линтера.
- **Две новые проверки** (см. ниже).

**Исправленные баги** (не только внешний вид):

- `bg-sky-50` и `bg-amber-50` в семи файлах рендерились почти белыми плашками на тёмном фоне — не были покрыты `!important`-блоком.
- Кнопки `border-purple-500 text-purple-700` — тёмно-фиолетовый текст на тёмной карточке.
- **~20 светлотемных цветов, которых спек не знал**, найдены при миграции и исправлены с пересчётом контраста: `#059669` при 3.97:1, `#b91c1c` при 2.46:1, девять штук в `orchestration_swimlane.css` (статус-пилюля «failed» — 2.4:1), подсветка строки канбана 2.61:1 → 12.09:1.
- `orchestration_swimlane.css` ссылался на `var(--bg-surface)` — **токен, которого никогда не существовало**; обёртка swimlane рендерилась прозрачной.
- Кнопка Kill в живом просмотре несла `hover:bg-red-100`, а `!important`-блок покрывал красные фоны, но не их hover-варианты — при наведении вспыхивал буквальный светлый цвет.
- `.field__control` задавал фон со специфичностью (0,1,0), тогда как базовое правило бьёт по `input` через девять атрибутных селекторов — (0,9,1). Фон компонента не применялся к `<input>`, но применялся к `<select>`: на `/setup` три поля подряд рендерились двумя разными цветами.

**Новые проверки** (в конвенции `scripts/check_*` / `smoke_*`):

- [`scripts/check_css_tokens.py`](../../scripts/check_css_tokens.py) — четыре утверждения: нет цветовых литералов в `components.css` (включая `rgb()`/`rgba()`/`hsl()`, кроме чёрного для теней); нет светлотемных утилит в шаблонах; нет статических инлайновых `style=`; **каждый класс, на который ссылается разметка, определён** — либо в нашем CSS, либо в `<style>`-блоке шаблона, либо упомянут в JavaScript как хук. Выходит с 0.
- [`scripts/smoke_templates_render.py`](../../scripts/smoke_templates_render.py) — компилирует все 51 шаблон (ловит опечатки Jinja на страницах, которые никто не открывает) и обходит все 45 GET-маршрутов без параметров, проверяя отсутствие 500. Раньше такой страховки не было вовсе.

**Acceptance**: `check_css_tokens.py` → `ALL OK`, exit 0. `smoke_templates_render.py` → 51 шаблон, 45 маршрутов, exit 0. `check_i18n.py`, `check_no_native_dialogs.py`, `smoke_table_tools.py`, `smoke_ai_radar.py` — все зелёные. Обход 30 страниц с подсчётом яркости фона 8487 элементов: светлых островов ноль.

**Что НЕ менялось**: ни одного файла приложения на Python. Ни одной строки, ни одного `data-*`, `hx-*`, `id`, `name`, `action`, `data-confirm` или вызова `| t()` — проверено сравнением мультимножеств по всем 51 шаблону между базой и результатом.

**Отложено**:

- **Унаследованный мёртвый код** — `.pill-nav` / `.pill` в `components.css` (не используется ни одним шаблоном), недостижимый блок `{% if flash %}` в `base.html` (`read_flash` не вызывается ниоткуда; сообщения показывает клиентский скрипт в `_app_modal.html`), `.md-content` в `app.css` (37 строк; реальный класс рендерера — `markdown-body`), мёртвый шаблон `project_orchestration_detail.html`. Удаление унаследованного мёртвого кода — отдельное решение, не дело миграции. **~90 строк одним коммитом.**
- **Семь однопроходных цветовых утилит `.text-*`** в `components.css` — третья параллельная система рядом с `.badge-*` и `.metric.metric-*`, ~115 мест использования. Рост заморожен, консолидация в один базовый класс с модификаторами — вход в D3.
- **`_is_tailwind()` в линтере слишком широк**: принимает любой токен, чей первый сегмент — корень Tailwind, поэтому `.text-warn` и `.bg-elevated` неотличимы от настоящих утилит. **Опечатка в любом из восьми собственных классов проходит молча** — ровно тот дефект, ради которого писалась проверка. Ужесточить вместе с консолидацией `.text-*`.
- **Тени карточек несогласованы**: `.metric` и `.pill-nav` носят `--shadow-card`, `.card` и `.data-table` — нет. Направление A декларирует отсутствие теней; унификация — заметное изменение на каждом дашборде, поэтому в D3.
- **Плотность таблиц расходится со спеком**: `project_notes`, `project_plans`, `project_contracts` названы в спеке «обычными», но получили `.is-dense`. `project_kanban` и `project_topics` показывают одни данные с разной плотностью.
- **D3** (применение визуального направления) и **D4** (ключевые экраны, эргономика) — получат свои спеки.

**Известный дефект, обнаруженный попутно (не относится к волне)**: `scripts/smoke_dashboard_tiles.py` печатает все OK, но **не завершается** — процесс висит, удерживая открытым SQLite-соединение. Похоже на незакрытое async-соединение или неотменённую задачу, удерживающую event loop. Результат верный, но в CI такой прогон повиснет.

## Не реализованные пока

На дату `wave-3-full` (последний коммит `b49aafd`) этот список deferred:

- **Реальный TTS backfill** (`tts_backfill.backfill_tts` — stub возвращает 0).
- **AskUserQuestion полная обвязка** — таблица `orchestrator_questions` уже существует, но API endpoints для создания / ответов ещё не добавлены. ProcessManager watchdog уже умеет учитывать pending question ([`process_manager.py:561`](../dreaming/services/process_manager.py)).
- **codex / continue runners** — `orchestration_local_runner` config есть, но в коде только claude путь.
- **work_routing_mode** — settings есть, в коде не используется.
- **Реальная harness-интеграция через UI** — сервис `HarnessClient` готов, но `/p/{slug}/orchestration/start` его не дёргает (использует local claude). Подключить можно через изменение `start_command` и проверку `await harness_clients.get_for_project(...)`.
- **Smoke-тесты для Wave 3+** — есть отдельные smoke-сценарии, но end-to-end orchestration smoke не написан.

## Cross-references

- Где какой код — [`services.md`](services.md), [`routes.md`](routes.md).
- Какие настройки активны в каждой волне — [`configuration.md`](configuration.md).
- Архитектура — [`architecture.md`](architecture.md).
