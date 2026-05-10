# AI Usage — аналитика токенов и стоимости

Две страницы:
- **Per-project** (`/p/{slug}/ai-usage`) — агрегаты для одного проекта.
- **Global** (`/ai-usage`) — кросс-проектный обзор: top проекты по расходу токенов.

## Содержание

- [Откуда берутся данные](#откуда-берутся-данные)
- [Per-project страница](#per-project-страница)
- [Global страница](#global-страница)
- [Project ID mapping](#project-id-mapping)
- [Если данных нет](#если-данных-нет)
- [Cost vs tokens](#cost-vs-tokens)

## Откуда берутся данные

Источник — JSONL-файлы, которые Claude CLI пишет в `~/.claude/projects/<workdir-encoded>/<session>.jsonl`. В каждой строке — одно событие, и в финальных событиях есть поля:
- `total_cost_usd` — стоимость сессии.
- `usage.input_tokens` — input токены.
- `usage.output_tokens` — output.
- `usage.cache_read_input_tokens`, `cache_creation_input_tokens` — кэш.

DC запускает cron-job `ai_usage_ingest` каждые 5 минут. Он:
1. Сканит все JSONL под `claude_projects_dir` (default `~/.claude/projects/`).
2. Парсит новые/изменённые.
3. Пишет в таблицу `ai_usage_events`: `(project_id, model, input_tokens, output_tokens, cache_read_tokens, cost_usd, ts)`.
4. Маппит JSONL'у на DC-проект через `cwd` поле в JSONL → `working_dir` в `projects`.

То есть — DC пассивно собирает аналитику работы Claude. Не важно, запустил ли ты сессию через DC или вручную через `claude` CLI в терминале — оба попадут в БД.

## Per-project страница

Открой `/p/{slug}/ai-usage`.

Если данных нет (`summary.error` или пустой набор) — увидишь:
- Либо красное «Ошибка: …» (если parser упал).
- Либо «Нет данных. Запусти ingest или подожди следующий тик cron'а.»

Если данные есть — увидишь:

**Топ-блок: 4 карточки в grid.**
- **Last 7d input** — input токены за последние 7 дней.
- **Last 7d output** — output.
- **Last 7d cache (read)** — кэш-read (это сильно дешевле обычного input'а).
- **Last 30d total** — total tokens за 30 дней.

Все числа — большие, моноширинные.

**Таблица «By model (last 30d)»** — если есть события за 30d:
- model — имя модели Claude (например `claude-sonnet-4-5`).
- input — токены.
- output — токены.
- cache_read — токены.
- events — количество событий ingest'а (примерно равно количеству API-calls).

Используй когда:
- «Сколько токенов уходит этот проект последние 7 дней?»
- «Какая модель доминирует — sonnet или haiku?»
- «Сравнить 7d vs 30d — растёт ли потребление?»

## Global страница

Открой `/ai-usage` (без `/p/{slug}/`).

Заголовок «AI Usage — все проекты». Логика та же, что у per-project, но:
- 4 карточки сверху — totals для **всех** проектов сразу.
- 4-я карточка — `events total` (вместо «30d total»).
- Таблица «By project (last 30d)» — группировка по проекту:
  - `project` — slug, кликабельный (ведёт на per-project ai-usage). Если slug `__unmapped__` — данные с JSONL без матчинга на DC project.
  - `input`, `output`, `events`.

Используй для:
- «Какой проект потребляет больше всех?»
- «Есть ли unmapped события?» (значит, JSONL есть, но cwd не совпал с registry).

## Project ID mapping

Mapping JSONL → project_id:
1. Из JSONL берётся `cwd` (рабочая директория сессии Claude).
2. `cwd` нормализуется (lowercase, slashes).
3. Ищется в `projects.working_dir` с такой же нормализацией.
4. Если найден — `project_id` присваивается. Если нет — `project_id = NULL` (показывается как `__unmapped__`).

Что делать если `__unmapped__` бесит:
- Проверь, что `working_dir` в `projects` точно совпадает с `cwd` в JSONL.
- На Windows внимание к слэшам и регистру.
- Если ты в одной сессии переключал cwd — ingest возьмёт первое значение.

Если хочешь полностью убрать unmapped — сделай `working_dir` в registry точно как `cwd` Claude'а.

## Если данных нет

Возможные причины:
1. **Только что запустил DC** — ingest cron ещё не сработал. Подожди 5 минут.
2. **`claude_projects_dir` неверный** — в settings прописан не тот путь. Проверь, что в `~/.claude/projects/` действительно есть JSONL'ы. (На Windows: `%USERPROFILE%\.claude\projects\`.)
3. **Ты не пользовался Claude CLI** — нет JSONL'ов. Запусти любую сессию через DC или в консоли — JSONL появится.
4. **Mapping не сошёлся** — JSONL есть, но `cwd` не матчится с `working_dir`. Все события упадут как `__unmapped__`. На `/p/{slug}/ai-usage` пусто, на `/ai-usage` — будет строка `__unmapped__`.

Проверка:
- Открой `/ai-usage` (global). Если там `events total > 0`, ingest работает.
- Если global пустой — проблема в `claude_projects_dir`.
- Если global непуст, но per-project пуст — проблема в mapping'е.

## Cost vs tokens

DC хранит и tokens, и `cost_usd`. На /ai-usage страницах в Wave 2.5 показывает только tokens.

Где смотреть стоимость:
- На orchestration runs — `/p/{slug}/cascade-costs` (если запускали Roman'a) показывает `total_cost_usd` per-run.
- В JSONL самих сессий — `result.total_cost_usd` есть в финальном событии.

В будущих волнах (4+) планируется визуализация cost trends. Пока — только raw tokens.

---

См. также:
- [`analytics-extras.md`](analytics-extras.md) — Cascade Costs и другие аналитики.
- [`settings.md`](settings.md) — `claude_projects_dir`, `ai_usage_*` ключи.
- Технически: [`../../features/analytics.md`](../../features/analytics.md), [`../../schema.md#ai_usage_events`](../../schema.md), [`../../services.md`](../../services.md).
