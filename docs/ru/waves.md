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
- [Wave A — Article pipeline](#wave-a--article-pipeline)
- [Wave B — Article cross-project](#wave-b--article-cross-project)
- [Wave C — Article committed build output](#wave-c--article-committed-build-output)
- [Wave E — Creative pipeline](#wave-e--creative-pipeline)
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

## Wave A — Article pipeline

**Ветка**: `feature/article-pipeline`, диапазон `e4f4bcc`..`211b538` — 28 коммитов, 27 файлов, +2683/−13. (`b9430e9` был неверной базой — это коммит спека, уже слитый в master; реальная точка ветвления — `e4f4bcc`.)

**Спек**: [`docs/superpowers/specs/2026-08-20-article-pipeline-design.md`](../superpowers/specs/2026-08-20-article-pipeline-design.md)
**План**: [`docs/superpowers/plans/2026-08-20-article-pipeline.md`](../superpowers/plans/2026-08-20-article-pipeline.md)
**Issue**: [#34](https://github.com/micode-ai/ai-dreaming-center/issues/34)

**Цель**: центр предлагает темы статей по проектам, по согласованию запускает агента-писателя самого проекта, и после второго согласования публикует статью коммитом в репозиторий проекта.

**Две поправки к вводным, которые определили дизайн**. Агент-писатель есть только в 3 из 11 подключённых проектов (`blog-writer` в `mi-code-ai` и `ai-budget-assistant`, `kb-page-author` в `legalka-kb`) — значит конвейер обязан работать и без него, не делая вид, что он есть. И формат публикации у проектов разный: у лендинга проза лежит данными в `blog-posts.json` плюс запись в `vite.config.ts`, у `accounting-ai-agent` — markdown по локалям со строгим фронтматтером, у `legalka-kb` своя структура. Поэтому центр владеет предложением, а форму статьи держит проект.

**Что вошло**:

- Таблица `article_proposals` со статусной машиной `proposed → approved → writing → drafted → published` (плюс `rejected` / `failed`) и `UNIQUE(project_id, slug_hint)`, чтобы три фидера на один сюжет давали одну строку.
- API для фидеров: `POST /api/p/{slug}/articles/ingest` (пустой `evidence` → **400**), `GET .../articles/list` для дедупа, `GET /api/articles/{id}` и `POST /api/articles/{id}/written` с защитой перехода на 409.
- Три фидера: команда `article-ideas-scan` в starter-kit, кнопка «Предложить статью» на карточке AI Radar и такая же на странице идей.
- Команда `write-article` в starter-kit: читает бриф из API, выбирает писателя (настройка → автодетект по `.claude/agents/` → сама), учится форме по соседним постам, прогоняет `article_verify_cmd`, репортит `draft_ref` и вывод верификации назад.
- Публикация коммитом только путей из `draft_ref` — никогда `git add -A`, никогда `git stash`.
- Страница `/p/{slug}/articles` со статусными группами и кросс-проектная очередь `/articles`.
- Недельный крон `weekly_article_ideas_scan`, выключен по умолчанию. Крон только предлагает: ни писать, ни публиковать он структурно не может.

**Правило, перенесённое из `micode-landing-page`**: у предложения обязателен `evidence` — трассируемый факт (коммит, закрытая волна, датированный релиз, измеренная дыра). Это принцип `scripts/ai-visibility/advice.mjs`, сформулированный там прямым текстом: «a suggestion nobody can check is worse than no suggestion». Проверка стоит на API, а не в промпте.

**Дефекты, найденные ревью по ходу волны** (все чинились в тех же задачах):

- `slugify` обрезала заголовок до шести слов, а `slug_hint` уникален — два разных сюжета с общим началом («Improve error handling in the parser» и «... in the scheduler») давали один слаг, второе предложение возвращалось как дубликат и **терялось молча**. Починено детерминированным суффиксом только при реальной обрезке.
- `git add -- <path>` честно отбивает пути за границей репозитория, но так же честно исполняет pathspec-магию: `draft_ref` со значением `:(glob)**/*` превращал путевой add в фактический `git add -A`. Закрыто валидацией (абсолютные пути, `..`, glob-символы, только существующий файл) плюс `--literal-pathspecs`. `-f` не передаётся никогда — отказ git добавлять игнорируемые файлы держит gitignore'нутые секреты вне наших коммитов.
- Отказ `git commit` после удавшегося `git add` оставлял индекс застейдженным, и повтор навсегда упирался в собственную же проверку «тут уже есть staged-правки». Добавлен откат ровно наших путей.
- Отказ `git push` после удавшегося коммита терял sha из учёта и навсегда блокировал повтор на «nothing staged». Теперь коммит фиксируется, строка помечается published с сообщением, что нужен ручной push.
- Страница считала `article_status_counts` и не использовала его: все числа брались из списка, ограниченного 200 строками. После 200 предложений экран показывал бы часть как всё.
- Строка со статусом вне списка групп исчезала с экрана, оставаясь в общем счётчике. `CHECK`-констрейнта на `status` нет, так что сценарий достижимый — добавлена группа-уловитель.
- Ретрай не сбрасывал результаты прошлой попытки: после неудачного повтора карточка показывала новую ошибку рядом с «сборка прошла» от предыдущего запуска.
- Строка, застрявшая в `writing` (сессия убита watchdog'ом или потеряна при перезапуске), рендерилась без единой кнопки. Добавлено действие «Отменить», доступное только в этом статусе; процесс оно не убивает, и это написано в докстринге.

**Гейт публикации — три случая, и различает их то, что карточке позволено утверждать**: `article_verify_cmd` задан и вернул ноль → публикация разрешена, показано «сборка прошла»; задан и упал → публикация заблокирована; не задан → публикация разрешена, но и карточка, и сообщение коммита говорят **«без проверки»**. Запрет третьего случая сделал бы фичу бесполезной в `accounting-ai-agent`, у чьего markdown-блога шага сборки нет вовсе; а объявить непройденную верификацию пройденной — сломать единственное правило, ради которого всё это построено.

**Acceptance**: [`scripts/smoke_articles.py`](../../scripts/smoke_articles.py) — 25 проверок, exit 0, включая настоящий временный git-репозиторий, где публикация коммитит только путь черновика, оставляет посторонний файл в рабочем дереве нетронутым и отбивает застейдженный путь. `check_i18n.py`, `check_css_tokens.py`, `smoke_ai_radar.py` — зелёные. Одиннадцать затронутых страниц отдают 200.

**Отложено**:

- **End-to-end на живом проекте не прогонялся.** Это единственный шаг плана, требующий платной сессии и коммита в чужой репозиторий, поэтому он делается под наблюдением человека, а не автоматом.
- **Кнопка на странице идей не гаснет** после того, как идея уже предложена — нужен запрос статуса по каждой идее.
- **У выключенного проекта предложения исчезают из очереди** без пометки на странице. Исключение задумано; тишина — нет.
- **`commit_ref` не показан** на опубликованной карточке.
- **Нет sweep'а для строк, застрявших в `writing`** — только ручная кнопка отмены.
- **`can_publish` не защищает `verify_cmd` от `None`** так, как защищает `publish_mode`.

**Известный дефект, обнаруженный попутно (не относится к волне)**: `scripts/smoke_node_skills.py` печатает результат, но **не завершается** — тот же класс, что уже отмечен у `smoke_dashboard_tiles.py`: незакрытое async-соединение держит event loop. В CI такой прогон повиснет.

## Wave B — Article cross-project

**Ветка**: `feature/article-cross-project`, диапазон `cec9010`..`d57cf01` — 15 коммитов, 12 файлов, +1307/−57.

**Спек**: [`docs/superpowers/specs/2026-08-20-article-cross-project-design.md`](../superpowers/specs/2026-08-20-article-cross-project-design.md)
**План**: [`docs/superpowers/plans/2026-08-20-article-cross-project.md`](../superpowers/plans/2026-08-20-article-cross-project.md)
**Расширяет**: [Wave A — Article pipeline](#wave-a--article-pipeline)
**Issue**: [#35](https://github.com/micode-ai/ai-dreaming-center/issues/35)

**Цель**: статья про один проект может публиковаться на площадке другого проекта, человек может сам сформулировать тему, а писатель может задать вопрос и дождаться ответа вместо того, чтобы гадать.

**Проблема**: конвейер волны A привязывал предложение к одному проекту — факты, написание и цель публикации были одним и тем же `project_id`. Эта модель оказалась исключением, а не правилом: у семи из одиннадцати подключённых проектов нет вообще никакого блога, так что по правилу волны A их статьи в принципе не могли быть написаны; а лендинг компании уже публикует статьи *о* других продуктах (`accounting-ai-agent-architecture`, `ai-budget-assistant-ai-architecture`) — доказательство того, что один репозиторий регулярно служит площадкой для многих сюжетов, лежало прямо в его собственном каталоге блога.

Не хватало и двух возможностей целиком. `source="manual"` существовал в модели данных, но не было ни одного роута, который бы его производил, — человек не мог просто сформулировать тему сам. А `write-article.md` уже предписывал писателю спрашивать, если факт не подтверждён, но канала для самого вопроса не существовало — инструкция указывала на инфраструктуру, которой никогда не строили.

**Что вошло**:

- Nullable-колонка `article_proposals.target_project_id` плюс per-project настройка `article_venue_project`, и чистая функция `resolve_venue_id(subject_id, override_id, configured_slug, enabled) -> int`: override важнее настройки, настройка важнее самого сюжета, а слаг, не называющий ни один включённый проект, откатывается назад вместо отказа.
- `_venue_for()` в `project_articles.py`, перепроводка `articles_page`, `articles_approve` и `articles_publish` на чтение каждой статейной настройки — агент-писатель, команда верификации, режим публикации, каталог блога, корень статьи — из разрешённой **площадки**, тогда как карточка, строка очереди и вопросы остаются за **сюжетом**. Площадка фиксируется на строке (`pin_article_proposal_venue`) сразу после успешного запуска, так что публикация воспроизводит решение согласования, а не пересчитывает его заново, рискуя разъехаться, если настройка поменяется между шагами.
- `DC_ARTICLE_SUBJECT_DIR` / `DC_ARTICLE_SUBJECT_SLUG` добавлены в окружение сессии, и новый раздел в `write-article.md`: рабочая директория самой сессии — это площадка (формат, сборка, git-репозиторий); директория сюжета — материал только для чтения. Раздел делегирования теперь явно называет сюжет, чтобы делегированный субагент не выдумывал факты, на которые его не навели.
- Форма ручного добавления статьи (`POST /p/{slug}/articles/add`): тема, вводный промпт и выбор площадки, с `source="manual"` и evidence, которое говорит правду — человек попросил, и когда — а не выдумывает коммит. Проверка на пустой evidence переехала с роута ingest прямо в `db.add_article_proposal`, так что теперь она держится структурно для любого фидера, настоящего и будущего.
- Селектор площадки на карточке в статусе `proposed` (`POST /p/{slug}/articles/{id}/venue`), доступный только до того, как писатель запущен.
- Канал вопросов: `write-article.md` документирует `POST /api/questions/create` и опрос `GET /api/questions/{id}/poll` по слагу сюжета, с явным правилом «не выдумывай факт» на `dismissed` или неотвеченный вопрос. Карточка показывает индикатор ожидания со ссылкой на `/p/{slug}/questions` для строки в `writing` с висящим вопросом.

**Дефекты, найденные ревью по ходу волны** (все чинились в тех же задачах):

- Свежий `CREATE TABLE` объявлял `target_project_id` сразу после `project_id` (индекс 2), а защищённый путь `ALTER TABLE`-миграции для уже существующей базы умеет только дописывать колонки в конец (индекс 25 на живой базе) — одна и та же таблица, два разных физических порядка колонок. Перенесено в конец списка `CREATE TABLE`, чтобы совпадать с тем, что всегда даёт миграция, плюс постоянная smoke-проверка полного порядка колонок на свежей базе.
- Та же ловушка уже сидела там со времён волны A: `verify_label`, добавленный более ранним `ALTER TABLE`, всё ещё объявлялся рядом с `verify_ok` в строке `CREATE TABLE` вместо своей настоящей позиции после миграции. Перенесён и покрыт той же проверкой порядка колонок.
- `articles_publish` пересчитывал площадку заново вместо того, чтобы переиспользовать решение согласования, так что строка могла разъехаться, если `article_venue_project` менялась между этими двумя шагами. Теперь `pin_article_proposal_venue` (без защиты по статусу) фиксирует разрешение в момент согласования, а публикация читает зафиксированное значение.
- Эта фиксация сначала стояла *до* вызова `start_command`, так что запуск, который `start_command` сам отказывается выполнять (блокировка «один одновременно», 409), всё равно фиксировал бы решение о площадке для попытки, которая так и не состоялась. Перенесено на момент после успешного запуска и до `start_article_attempt`.
- Инструкция делегирования в `write-article.md` никогда не сообщала делегированному субагенту про `$DC_ARTICLE_SUBJECT_DIR`, так что кросс-проектный делегат выдумывал бы факты, на которые его не навели.
- Фолбэк слага при ручном добавлении для темы без ASCII-слов был `manual-{timestamp}`, взятый дословно из брифа. Но пользователь пишет темы по-русски, так что путь «сплошная кириллица» (slugify отбрасывает не-ASCII, давая пустой слаг) — это здесь основной случай, а не краевой, и фолбэк на основе часов ломает дедуп в обе стороны: два разных предложения в одну и ту же секунду UTC схлопываются в одно, а одно и то же предложение секундами позже не дедуплицируется. Исправлено хешированием нормализованного текста темы вместо этого.
- Правило про пустой evidence жило только на HTTP-границе `/articles/ingest`, полагаясь на то, что каждый фидер по договорённости составляет непустую строку. Поднято в сам `add_article_proposal`, так что будущий фидер наследует правило структурно.
- Выпадающий список площадки на карточке сравнивал свои опции с *разрешённым* слагом площадки — который, по самой логике фолбэка `resolve_venue_id`, всегда указывает на какой-нибудь реальный проект, — из-за чего опция «по умолчанию для проекта» была фактически недостижима в UI, а сохранение формы «как есть» молча закрепило бы площадку за непривязанной строкой. Исправлено передачей в шаблон сырого per-row override вместо разрешённого значения.

- `tool_use_id` для вопроса строился из id предложения, а `create_question` при повторе того же ключа возвращает **существующую** строку, не обновляя текст. Значит повтор упавшей статьи прочитал бы ответ на вопрос **первой** попытки как ответ на свой — или, если тот вопрос отклонили, вовсе лишился бы возможности спросить. Починено привязкой ключа к прогону.
- Индикатор «писатель ждёт ответа» считался один раз на проект и делился между всеми карточками, а таблица вопросов общая для всех сессий проекта. Поэтому вопрос от постороннего скана заставил бы **каждую** пишущуюся статью утверждать, что ждут вас. Починено привязкой вопроса к предложению.
**Acceptance**: [`scripts/smoke_articles.py`](../../scripts/smoke_articles.py) — 57 проверок, exit 0. `scripts/smoke_ai_radar.py`, `check_i18n.py`, `check_css_tokens.py` — все зелёные; `python -c "import dreaming.main"` завершается с 0. Девять затронутых страниц отдают 200 через `TestClient`, включая `/p/budlog/articles` (единственный проект, у которого `article_venue_project` намеренно настроен как кросс-проектный). Регрессия, которая важнее всего: подтверждено, проект за проектом, что предложение с `target_project_id` NULL и без настройки `article_venue_project` разрешает площадку в сам сюжет и читает собственные `article_blog_dir` и корень статьи сюжета — для всех трёх сейчас настроенных проектов (`test`, `accounting-ai-agent`, `ai-budget-assistant`) — воспроизводя поведение волны A один в один. Намеренно другой результат у `budlog` (`article_venue_project=test`, разрешается в `test`) подтверждён как задуманная кросс-проектная демонстрация, а не регрессия.

**Отложено**:

- **Живой end-to-end прогон написания статьи так и не состоялся ни в одной из волн.** По-настоящему прогонялась только половина конвейера — предложение.
- Строки, которые были `drafted` ещё до появления фиксации площадки, сохраняют `target_project_id` NULL и остаются уязвимы к дрейфу площадки при прямой публикации; они самовосстанавливаются при любом повторном согласовании.
- Центр обнаруживает *отсутствующую* команду starter-kit, но не имеет никакого сигнала для *устаревшей* — так что установленная копия в каждом проекте молча стареет по мере изменения шаблонов. Собственное зеркало `.claude/commands/write-article.md` этого репозитория успело разойтись с шаблоном (не хватало раздела канала вопросов из задачи 6) и было обновлено в рамках проверочного прохода этой задачи; следующий дрейф ничто не ловит автоматически. **Закрыто 21.08.2026**: `starter_kit.command_stale` и `status().stale` сравнивают содержимое с нормализацией переводов строк (шаблоны здесь CRLF, а выгрузка на другой машине обычно LF — иначе сигнал кричал бы «волк» на каждой копии), страница статей показывает баннер рядом с кнопками, которые тратят сессию, а страница ротации — рядом с кнопкой перезаписи. Сессия при этом **не** блокируется: первый же прогон по парку показал, что дрейф бывает двух разных родов — 8 проектов из 11 держат отставшую на 1255 байт копию `self-study.md` (одинаковый md5 у всех), а `budlog` осознанно заменил в примере имя агента на своё. Различить их сравнением нельзя, поэтому баннер говорит «разошлась», а не «устарела», и предлагает посмотреть диф до перезаписи.
- Smoke-проверка «две разные кириллические темы» не форсирует попадание обоих постов в одну и ту же секунду UTC, так что это направление — вероятностная, а не железная фиксация.
- Деталь 409 в роуте площадки подставляет статус, прочитанный прямо перед записью, так что очень узкая гонка могла бы назвать устаревший статус.
- `smoke_node_skills.py` по-прежнему никогда не завершается — тот же класс незакрытого соединения, что уже отмечен у `smoke_dashboard_tiles.py` в Wave D1/D2 и оставлен как известная проблема в конце волны A.

## Wave C — Article committed build output

**Ветка**: `feature/article-build-output`, диапазон `cdfb3f9`..`e02fe32` — 4 коммита, 5 файлов, +626/−25. Отдельного плана нет: волна — одна задача, и спек описывает её целиком.

**Спек**: [`docs/superpowers/specs/2026-08-21-article-committed-build-output-design.md`](../superpowers/specs/2026-08-21-article-committed-build-output-design.md)
**Расширяет**: [Wave A — Article pipeline](#wave-a--article-pipeline), [Wave B — Article cross-project](#wave-b--article-cross-project)
**Issue**: [#36](https://github.com/micode-ai/ai-dreaming-center/issues/36)

**Цель**: публикация должна доходить до живого сайта и на том проекте, который держит в гите собранный сайт, а не только исходники.

**Проблема**: волны A и B коммитили ровно те пути, которые назвал писатель. Для двух проектов из трёх это верно — `mi-code-ai` и `accounting-ai-agent` коммитят исходники, а собирает CI. Третий устроен иначе, и именно на нём пользователь попробовал первым: `ai-budget-assistant` держит в гите 208 файлов сгенерированного сайта под `docs/marketing/seo/site/blog`, а `web-deploy.yml` копирует на сервер именно этот каталог — «Committed builds (regenerate then commit)» написано в самом workflow. Первый живой прогон это и доказал: писатель выдал корректную польскую статью на 10 КБ с фронтматтером как у 21 соседа, и от этого файла к `ai-budget.pl/blog` не было ни одного пути.

**Отвергнутое решение**: «публикация сама запускает сборку». `build_blog.py` рендерит все языки, генерирует OG-картинки через PIL и пересобирает sitemap — это минуты внутри POST по нажатию кнопки. У сборки уже есть законное место: команда верификации, которую запускает сессия, а не веб-запрос. Для этого проекта сборка *и есть* верификация в самом сильном смысле — она доказывает, что статья отрендерилась в тот каталог, который увезёт деплой.

**Что вошло**: одна настройка площадки, `article_publish_extra_paths` — пути через запятую или перенос строки, относительно корня статьи, которые стейджатся вместе с `draft_ref`. Пусто означает поведение волн A/B байт в байт, так что у двух других проектов не меняется ничего.

Асимметрия здесь — суть, а не недосмотр: эти пути **могут** называть каталог, а `draft_ref` — нет. `draft_ref` приходит от Claude-сессии по неаутентифицированному localhost HTTP, и каталог там дал бы одному отчёту застейджить целое поддерево. `article_publish_extra_paths` набирает человек в настройках проекта, а вывод сборки — это и есть поддерево на 208 файлов. Всё остальное — запрет `..`, абсолютных путей и glob-символов, проверка вхождения в репозиторий, `--literal-pathspecs`, отсутствие `-f` — действует для обоих одинаково.

**Дефекты, найденные ревью по ходу волны** (все чинились в тех же задачах):

- Таблица рисков в спеке закрывала случай «вывод сборки в gitignore» словами «`git add` без `-f` отказывает, публикация падает с сообщением git». Формально верно — и потому опасно: описан исход, но не состояние после него. `git add` не атомарен по набору путей: отказав на игнорируемом, он всё равно стейджит остальные — файл статьи оставался в индексе **чужого** репозитория, и убирать за нами пришлось бы человеку. Починено общим `_rollback_or_raise` для обоих `git add` и для `git commit`, с проверкой кода возврата самого отката и честным сообщением о том, что осталось.
- Каталог с вложенным `.git` (vendored-репозиторий внутри вывода сборки) застейджился бы как висячий gitlink — коммит со ссылкой на объект, которого в репозитории нет. Отказ перенесён в валидацию, до любого вызова git.

**Acceptance**: [`scripts/smoke_articles.py`](../../scripts/smoke_articles.py) — 90 проверок, exit 0. `scripts/smoke_ai_radar.py`, `check_i18n.py`, `check_css_tokens.py` — все зелёные; `python -c "import dreaming.main"` завершается с 0. Проверено на одноразовых репозиториях, отдельно от прогона исполнителя: дерево сборки попадает в коммит вместе со статьёй; посторонний файл, застейдженный человеком, в коммит **не** попадает и остаётся застейдженным; `draft_ref` по-прежнему отказывает каталогу, тогда как настроенный путь его принимает; и каждый отказ — игнорируемый вывод, вложенный `.git`, `..`, абсолютный путь, glob, несуществующий путь — оставляет индекс побайтово тем же, чем он был.

**Что выяснилось на первой живой публикации** (статья 22 в `ai-budget-assistant`, 22.08.2026):

- Волна C дала возможность коммитить вывод сборки, но не могла знать, что у проекта **два** генератора. Апексный `sitemap.xml` — тот, который реально отдаёт `ai-budget.pl` — эмитит `build_landing.py`, читая карту блога, а `web-deploy.yml` ничего не пересобирает, он собирает закоммиченный вывод. Настроенный `article_verify_cmd` запускал только `build_blog.py`, поэтому статья уехала живой и достижимой (на неё ссылаются 22 соседние страницы, IndexNow пропинговал каждую изменённую), но в карте сайта её не было. Починено: verify-команда теперь цепочка из двух генераторов через `&&`, а `article_publish_extra_paths` называет оба дерева. Правило записано в комментарии к `article_verify_cmd` в [`config.py`](../../dreaming/config.py) — verify обязан пересобирать всё, что увозит деплой, а не только ближайшее к статье.
- Второе дерево оказалось недостижимо и по другой причине: `docs/marketing/*` в `.gitignore` проекта исключал каталог landing, а публикация принципиально не передаёт `-f`. То есть `git add` был бы отвергнут, волна C честно откатилась бы и сказала об этом — но опубликовать не смогла. Лечится только в самом проекте: негация `!docs/marketing/landing/`, парная к уже существовавшей для `seo/`.
- `meta_description` вылезал за 155 символов у pl (160) и fr (161). Не беда этой статьи: хотя бы один язык переполнен у 15 тем из 22, а генератор длину не проверял вовсе. В `build_blog.py` добавлено предупреждение — намеренно не фатальное, иначе сборка ломалась бы на 30 унаследованных переполнениях, которые автор новой статьи исправить не может.
- Побочно выяснилось, что у этого проекта вывод сборки зависит от **даты коммита источника** (`dateModified` берётся из git), так что один проход «собрать и закоммитить» самосогласованным быть не может: правильную дату даёт только сборка после коммита. Для конвейера это значит, что идеальной чистоты дерева после публикации ждать не стоит.

**Отложено**:

- `article_publish_mode` у `ai-budget-assistant` выставлен в `commit`, на ступень ниже выбранного пользователем `commit+push`: первый живой коммит на 208-файловом каталоге стоит посмотреть глазами до пуша. Это моё решение, не пользователя.
- **Живой end-to-end — написание, публикация, появление на сайте — так и не состоялся ни в одной из волн.**
- Огромный случайный путь (`.`) в настройке проходит проверки вхождения и существования и закоммитит рабочее дерево. Смягчено лишь тем, что это настройка оператора, видимая на странице настроек — тот же уровень доверия, что у `article_publish_mode`.
- Установщик starter-kit не умеет целиться в корень статьи внутри вложенного репозитория (для `mi-code-ai` обойдено руками). Это пробел установщика, не публикации.

## Wave E — Creative pipeline

**Ветка**: `feature/creative-pipeline`, диапазон `5cd74f0`..`6de80c8` — 2 коммита, 17 файлов, +2691/−2.

**Спек**: [`docs/superpowers/specs/2026-08-22-creative-pipeline-design.md`](../superpowers/specs/2026-08-22-creative-pipeline-design.md)
**Родня**: [Wave A — Article pipeline](#wave-a--article-pipeline), [Wave B](#wave-b--article-cross-project), [Wave C](#wave-c--article-committed-build-output)
**Issue**: [#37](https://github.com/micode-ai/ai-dreaming-center/issues/37)

**Цель**: рекламные креативы проходят тот же цикл, что статьи — предложение от центра или от человека, согласование, сборка агентом площадки, просмотр, доработка по замечаниям, публикация.

**Проблема**: три проекта уже делают рекламу руками, и центр в этом не участвовал. Формы у всех разные: у `accounting-ai-agent` 77 файлов — HTML-шаблон на формат и локаль, `assets/`, `build.mjs`, `build-reel.mjs`, `renders/pl/`, тексты в `creatives/captions/`; у `ai-budget-assistant` 249 файлов — исходные скриншоты кампании, потом `renders/`, тексты в `docs/marketing/copy/`; у лендинга 310 файлов — `<slug>/src/` и `<slug>/renders/`. Одни и те же три сущности (рендеры, текст поста, план) под тремя укладами — тот же урок, что дали волны статей: **форму владеет площадка**, и центр не должен знать ни одну из них.

**Решения, принятые до дизайна** (с оператором): публикация — это коммит, а не постинг через API соцсетей (это единственное необратимое действие в конвейере и требует токенов каждой площадки); видео входит с первой волны, потому что рилсы — это то, как контент и потребляют; материал для сборки прикрепляет человек после шага идеи, как уже устроено у `ai-budget-assistant`.

**Что вошло**:

- Своя таблица `creative_proposals`, а не флаг `kind` у статей: у креатива есть форматы, вложения и бинарные результаты, которых у статьи нет, а четыре nullable-колонки на каждой статье заставили бы каждый запрос по статьям объясняться. Переиспользована **дисциплина**, а не схема: правило доказательства в самом методе БД, сюжет против площадки, path-scoped `git add` без `-f`, `revision_notes` со снятием при отчёте, один путь отправки для первой сборки и любой доработки. Универсальные хелперы (корень git-репозитория, гейт публикации, нормализация режима) импортированы из `articles`, а не скопированы.
- Слаг кампании фиксируется при создании предложения, а не выбирается сборщиком: вложения приезжают в `<creative_dir>/<slug>/src/` **до** запуска сессии, значит имя каталога должно существовать раньше сборщика.
- Загрузка вложений исходит из того, что вызывающий небрежен, и отказывает в любом случае: остаётся только basename (путь **сокращается**, а не отвергается — браузер, присылающий путь, это норма), имя нормализуется до `[a-z0-9._-]`, расширение по белому списку, размер ограничивается по ходу потока, каталог назначения фиксирован, и путь потом проверяется валидатором публикации — то есть роут не может записать туда, откуда публикация не смогла бы закоммитить.
- **Роут выдачи медиа** — то, чего у статей нет вовсе: рекламу нельзя согласовать не увидев. Три заслона: путь обязан быть тем, что строка сама сообщила в `draft_ref`; он проходит валидатор публикации; его тип входит в список того, что конвейер производит. Первое и делает параметр выбирающим, а не открывающим.
- Проверки для доработки, вычислимые без знания инструментария площадки: формат, не давший ни одного файла; рендер, чьи пиксели не совпадают с объявленным размером формата (читается из заголовка PNG/JPEG/GIF, без графических библиотек); локаль без рендеров; отсутствие текста поста. Размер видео не измеряется и не угадывается — проверяется только его наличие.
- Команды starter-kit `creative-ideas-scan.md` и `make-creative.md`, вторая с разделом про доработку по образцу 1a у писателя.

**Найдено по ходу**: автодетект агента сначала выбрал `blog-writer` для лендинга — подсказка «writer» оказалась слишком широкой, и сборка рилсов ушла бы агенту для прозы. Подсказку убрал; площадка без ничего маркетингового получает `self`, и сессия делает работу сама, что честнее ближайшего по звучанию.

**Acceptance**: [`scripts/smoke_creatives.py`](../../scripts/smoke_creatives.py) — 13 проверок, exit 0, включая нейтрализацию семи враждебных имён файлов, отказ архиву и превышению размера без следов на диске, отказ прикреплению во время сборки, чтение размеров из заголовков PNG, отказ роута медиа несообщённому пути, немедийному типу и traversal. `smoke_articles.py` (107 проверок), `smoke_ai_radar.py`, `check_i18n.py`, `check_css_tokens.py` — все зелёные; `python -c "import dreaming.main"` завершается с 0. Страница отдаёт 200 на четырёх проектах, включая тот, у которого каталог креативов лежит во вложенном репозитории (`test` → `micode-landing-page`), и тот, где ничего не настроено — там показывается баннер про `creative_dir`.

**Настроено**: `creative_dir` у трёх площадок (`accounting-ai-agent`, `ai-budget-assistant`, и `test` с путём во вложенный репозиторий), локали у двух. `creative_verify_cmd` намеренно оставлен пустым: у каждой кампании accounting свой `build.mjs`, и выдумывать за проект команду сборки хуже, чем оставить метку «без проверки сборкой», которая честна.

**Отложено**:

- Постинг в соцсети через API — выбор оператора, не пробел.
- Кросс-проектная очередь `/creatives` и плановые сканы — следом, тем же порядком, каким шли волны статей.
- Живой прогон сборки не состоялся: конвейер собран и проверен, но ни одна кампания через него пока не прошла. То же, чем начинались волны статей.

## Не реализованные пока

На дату `wave-3-full` (последний коммит `b49aafd`) этот список deferred:

- **Реальный TTS backfill** (`tts_backfill.backfill_tts` — stub возвращает 0).
- **AskUserQuestion полная обвязка** — таблица `orchestrator_questions` уже существует, но API endpoints для создания / ответов ещё не добавлены. ProcessManager watchdog уже умеет учитывать pending question ([`process_manager.py:561`](../../dreaming/services/process_manager.py)).
- **codex / continue runners** — `orchestration_local_runner` config есть, но в коде только claude путь.
- **work_routing_mode** — settings есть, в коде не используется.
- **Реальная harness-интеграция через UI** — сервис `HarnessClient` готов, но `/p/{slug}/orchestration/start` его не дёргает (использует local claude). Подключить можно через изменение `start_command` и проверку `await harness_clients.get_for_project(...)`.
- **Smoke-тесты для Wave 3+** — есть отдельные smoke-сценарии, но end-to-end orchestration smoke не написан.

## Cross-references

- Где какой код — [`services.md`](services.md), [`routes.md`](routes.md).
- Какие настройки активны в каждой волне — [`configuration.md`](configuration.md).
- Архитектура — [`architecture.md`](architecture.md).
