# Weekly scanners

В дополнение к ежедневному self-study, DC может запускать еженедельные «scanner»-агенты, которые анализируют проект целиком и пишут аналитику в виде markdown-файлов:
- **Tech-debt scanner** — обходит код, ищет технический долг, пишет md-файлы в `tech_debt_dir`.
- **Product ideas scanner** — анализирует фичи / pain-points, пишет идеи в `product_ideas_dir`.
- **Wiki linter** — проверяет wiki-domain'ы, апдейтит/добавляет.

По дефолту все три **выключены** (opt-in). Здесь — как их включить.

## Содержание

- [Зачем weekly](#зачем-weekly)
- [Список scanner'ов](#список-scanner-ов)
- [Включить scanner](#включить-scanner)
- [Настройка cron-expression](#настройка-cron-expression)
- [Manual trigger](#manual-trigger)
- [Что делает scanner внутри](#что-делает-scanner-внутри)

## Зачем weekly

Self-study каждую ночь — это «изучение зоны ответственности агента». Это полезно, но не покрывает:
- Анализ всего проекта в одном проходе.
- Поиск cross-cutting проблем (технический долг разбросан по модулям).
- Систематическую генерацию backlog'а идей.

Weekly scanner — другой жанр: один агент, одна задача, один большой проход по всему проекту, результат — структурированный markdown-каталог.

## Список scanner'ов

### `weekly_tech_debt_scan_{slug}`

Запускает агента, который сканит код и пишет md-файлы в `tech_debt_dir`. Каждый файл — один tech-debt item с frontmatter (id, title, status, priority, module).

Дефолтный agent — `tech-debt-scanner` или `td-scanner` (в `.claude/agents/` твоего стартеркита). Configurable через `weekly_tech_debt_scan_agent`.

### `weekly_product_ideas_scan_{slug}`

Запускает агента, который анализирует UX / feature-gaps / user pain и пишет md-файлы в `product_ideas_dir`. Каждый — одна идея с frontmatter (id, title, status, priority, jira_ticket).

Дефолтный agent — `product-ideas-generator` или подобное. Configurable через `weekly_product_ideas_scan_agent`.

### `weekly_wiki_lint_{slug}`

Запускает агента, который проверяет wiki:
- Все ли domain'ы покрыты.
- Не пропали ли модули с обновлением кода.
- Стилистические проблемы.

Пишет/обновляет md-файлы в `wiki_dir`. Configurable через `weekly_wiki_lint_agent`.

## Включить scanner

Возьмём пример с tech-debt. Для остальных — аналогично.

1. Открой `/p/{slug}/settings`.
2. Прокрути до группы «Scheduling — weekly (opt-in)».
3. Найди ключ `weekly_tech_debt_scan_enabled`. По дефолту inherit'ится с global (там тоже `false`).
4. Кликни radio `Override`. Появится checkbox.
5. Поставь checkbox в checked.
6. Здесь же убедись что `tech_debt_dir` прописан (override или inherit с global). Если глобально пусто — впиши абсолютный путь.
7. Save.

После Save:
- Scheduler перерегистрирует jobs. Новый `weekly_tech_debt_scan_{slug}` появится.
- На следующем cron-tick'е (по `weekly_tech_debt_scan_cron`, default `0 4 * * 0` — воскресенье 4:00) job запустится.
- Создаст или обновит md-файлы в `tech_debt_dir`.
- На `/p/{slug}/findings` ты увидишь items.

## Настройка cron-expression

Те же 5-частный cron что в [`nightly-cron.md`](nightly-cron.md). Дефолты:
- `weekly_tech_debt_scan_cron = 0 4 * * 0` — воскресенье 4 утра.
- `weekly_product_ideas_scan_cron = 30 4 * * 0` — воскресенье 4:30.
- `weekly_wiki_lint_cron = 0 5 * * 0` — воскресенье 5 утра.

Сдвиги по 30 мин — чтобы не запускать всё одновременно (избежать peak load на API Anthropic).

Чтобы изменить:
- `/settings` (global) или `/p/{slug}/settings` (per-project).
- Группа Scheduling — weekly.
- Ключ `weekly_*_cron` → впиши новое значение.
- Save.

Если хочешь не еженедельно, а раз в две недели — сложнее. Cron не умеет «every other week» нативно. Workaround: запусти каждое воскресенье, но в самом scanner-агенте (slash-command) добавь логику «если уже сканировал на этой неделе — выйди».

## Manual trigger

Хочешь запустить scanner сейчас, не дожидаясь cron'а?

В UI **прямой кнопки нет** для tech-debt и product-ideas scanner'ов. Workaround:

**Способ 1: через `/p/{slug}/orchestration`**
- Введи в форму goal вида `Run tech-debt scan now` (или с явной формулировкой задачи scanner-агента).
- `Start Roman`.
- Roman возьмёт задачу и запустит подсказанного агента.

Не идеально (Roman добавляет overhead), но работает.

**Способ 2: через `Start session` на rotation**
- Если scanner-агент есть как md-файл в `.claude/agents/` (например `tech-debt-scanner.md`) — он будет в Rotation.
- Жми `Start session` рядом с ним.
- Это запустит обычный self-study (не weekly_*_scan job), но эффект тот же — агент-scanner отработает.

**Способ 3: через `Run /wiki-bootstrap` (только для wiki)**
- Кнопка прямо на `/p/{slug}/wiki`. См. [`../features/wiki.md`](../features/wiki.md).

**Способ 4: ручной cron tick** (advanced)
- Если ты разрабатываешь — можно через REPL вызвать функцию scanner job'а напрямую. См. `dreaming/services/scheduler.py`.

## Что делает scanner внутри

Технически weekly_tech_debt_scan_{slug} — это APScheduler job, который при триггере:

1. Получает project_id из job-name.
2. Резолвит `weekly_tech_debt_scan_agent` (default `tech-debt-scanner`) и `weekly_tech_debt_scan_command` (default `/tech-debt-scan`).
3. Спавнит `claude` с slash-command'ом и `cwd={working_dir}`.
4. Создаёт session row в БД с `agent_name='_weekly-tech-debt-scan'`.
5. Watchdog по `timeout_minutes` (но обычно scanner работает дольше — может стоит увеличить до 60).
6. После завершения — sessions row помечается success/failed.

Slash-command `/tech-debt-scan` (в `~/.claude/commands/tech-debt-scan.md`) описывает, что именно делать:
- Прочитай весь код.
- Сравни с предыдущими findings (чтобы не дублировать).
- Напиши новые md-файлы в `tech_debt_dir`.
- Closer старые findings, которые уже не актуальны.

Конкретное поведение зависит от твоего starter-kit'а. Если у тебя нет такого slash-command'а — нужно его написать.

---

См. также:
- [`nightly-cron.md`](nightly-cron.md) — ежедневное self-study расписание.
- [`../features/tech-debt.md`](../features/tech-debt.md) — где видеть результаты tech-debt scan'а.
- [`../features/ideas.md`](../features/ideas.md) — где product ideas.
- [`../features/wiki.md`](../features/wiki.md) — где wiki status.
- [`../features/settings.md`](../features/settings.md) — где включать.
- Технически: [`../../features/pipelines.md`](../../features/pipelines.md), [`../../services.md#scheduler`](../../services.md).
