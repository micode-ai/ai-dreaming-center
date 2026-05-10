# Дополнительная аналитика

Шесть «вспомогательных» страниц в шапке проекта, каждая read-only:

- **Evolutions** (`/p/{slug}/evolutions`) — список агент-overrides из `_context/`.
- **Loops** (`/p/{slug}/loops`) — reflex-loop файлы.
- **Plans** (`/p/{slug}/plans`) — Roman-плаnы с progress.
- **Cascade Costs** (`/p/{slug}/cascade-costs`) — стоимость orchestration runs.
- **Sidecar findings** (`/p/{slug}/sidecar-findings`) — JSON-отчёты reviewer-агентов.
- **Contracts** (`/p/{slug}/contracts`) — module/page contracts.

## Содержание

- [Evolutions](#evolutions)
- [Loops](#loops)
- [Plans](#plans)
- [Cascade Costs](#cascade-costs)
- [Sidecar findings](#sidecar-findings)
- [Contracts](#contracts)

## Evolutions

`/p/{slug}/evolutions` — список «эволюций» агентов. Эволюция — это markdown-файл-override, описывающий изменение поведения конкретного агента (что-то типа personality patch). Лежит в `evolutions_dir` или `context_overrides_dir` (по `_context/{agent}/`).

Что показывает страница:
- Если каталог не существует — серый текст «Каталог `{path}` не существует. Переопредели `evolutions_dir` или `context_overrides_dir` в Settings, или создай папку.»
- Если parser-error — красный «Ошибка: ...».
- Если есть evolutions — таблица:
  - `agent` — имя агента.
  - `name` — имя evolution-файла.
  - `status` — статус (active / archived / proposed / etc).
  - `conflict` — `⚠` если есть conflict-маркеры в файле.
  - `title` — короткое описание.

Используй для:
- Аудита: какие override'ы применены.
- Поиска конфликтов: значок ⚠.

UI не позволяет редактировать — только просматривать. Управляешь через filesystem: добавил/удалил/переименовал файл — обновил страницу.

## Loops

`/p/{slug}/loops` — reflex-loops агентов. Loop — это markdown-описание самокорректирующегося цикла, который агент выполняет (например, «найди bug → fix → test → если test fail, повтори»).

Что показывает:
- Если `loops_dir` не настроен — «loops_dir не настроен. См. Settings.»
- Если каталог не существует / ошибка / пусто — соответствующий текст.
- Если есть loops — таблица:
  - `name` — имя loop-файла.
  - `title` — заголовок.
  - `status` — running / completed / paused.
  - `iterations` — количество итераций (number, выровненный по правому краю).

Используй для:
- Понимания, какие активные loops есть в проекте.
- Аудита истории: 10 итераций — это много.

Тоже read-only. Создаются обычно агентами в их работе.

## Plans

`/p/{slug}/plans` — markdown-планы, которые Roman/agent пишут с tasks-чек-листом. Лежат в `plans_dir`.

Что показывает:
- Если `plans_dir` не настроен — «plans_dir не настроен. См. Settings.»
- Если каталог не существует / пуст — соответствующее.
- Если есть — таблица:
  - `name` — имя файла.
  - `title` — заголовок.
  - `status` — pending / in-progress / done.
  - `progress` — визуальный прогресс-бар: бар (32 unit'а wide, зелёный fill) + текст `done/total`.

Progress считается DC по чекбоксам в md-файле:
- `[x]` — done.
- `[ ]` — todo.
- `done / (done + todo)` — процент.

Если Roman пишет план как `## Tasks` секцию с чекбоксами — DC автоматически парсит и считает.

Используй для:
- Видеть, какие планы уже на 80% — близки к завершению.
- Какие в pending — ждут начала.

## Cascade Costs

`/p/{slug}/cascade-costs` — стоимость orchestration runs (включая cascade и обычные Roman'ы) в USD.

Источник: `orchestrator_events` со полем `cost_usd` (из финального result-event'а Claude). Агрегируется per run.

Что показывает:
- Если ошибка — «Ошибка: ...».
- Если runs нет — «Нет orchestration runs. Cascade pipelines поднимаются в Wave 3.»
- Если есть — два карточки сверху:
  - **Runs (latest 50)** — number.
  - **Total cost USD** — `$X.XXXX`.
  - Таблица latest-50:
    - `run_id` — короткий UUID.
    - `goal` — обрезанный.
    - `status`.
    - `events` — количество events с cost'ом.
    - `cost USD` — `$X.XXXX`.

Используй для:
- «Сколько мне стоила за последний месяц orchestration?»
- «Какой run был самый дорогой?»
- «Cascade vs обычный Roman — где больше cost'а?»

Self-study costs здесь **не учитываются** — они в [`ai-usage.md`](ai-usage.md).

## Sidecar findings

`/p/{slug}/sidecar-findings` — JSON-отчёты reviewer-агентов (vera, svetlana, silent-failure-hunter). Каждый отчёт — finding с уровнем severity.

Что показывает:
- Если `sidecar_findings_dir` не настроен / нет каталога / ошибка — соответствующий текст.
- Если есть — фильтр-dropdown по severity (critical / high / medium / low / info) + таблица:
  - `reviewer` — кто написал (vera / svetlana / etc).
  - `id` — id finding'а.
  - `title` — что нашли.
  - `severity` — уровень.
  - `module` — модуль кода.
  - `file` — файл.
  - `rule` — правило/категория.

Фильтр работает так же как у ideas: выбираешь в dropdown'e — auto-submit, URL `?severity=critical` — таблица отфильтровывается.

Используй для:
- «Какие critical finding'и у меня сейчас открыты?»
- «Какой reviewer чаще всего находит проблемы в `auth/`?»
- Триаж перед спринтом.

В отличие от tech-debt findings — эти JSON, не markdown. UI не имеет close/delete (нет конвенций). Управляй filesystem'ом.

## Contracts

`/p/{slug}/contracts` — формальные контракты модулей и страниц. Полезны для cascade-flow (там contract — отдельный stage).

Что показывает:
- Если `contracts_dir` не настроен / нет каталога — соответствующее.
- Если есть — таблица:
  - `name` — имя контракта.
  - `kind` — module / page / API / другое.
  - `module` — какой модуль покрывает.
  - `page` — какая страница (если относится).
  - `status` — draft / accepted / deprecated.
  - `last review` — timestamp последнего ревью.

Используй для:
- Аудит: всё ли покрыто контрактами.
- Поиск deprecated: что нужно перепроверить.

---

См. также:
- [`tech-debt.md`](tech-debt.md) — параллельная страница для tech-debt.
- [`ideas.md`](ideas.md) — для product ideas.
- [`orchestration.md`](orchestration.md), [`cascade.md`](cascade.md) — где используются эти артефакты.
- [`settings.md`](settings.md) — где настраиваются `*_dir` ключи.
- Технически: [`../../features/analytics.md`](../../features/analytics.md), [`../../features/pipelines.md`](../../features/pipelines.md).
