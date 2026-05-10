# FAQ

Частые вопросы по эксплуатации AI Dreaming Center.

## Содержание

- [Установка и запуск](#установка-и-запуск)
- [Запуск сессий](#запуск-сессий)
- [Tech-debt и Product ideas](#tech-debt-и-product-ideas)
- [Cron и расписание](#cron-и-расписание)
- [Безопасность и creds](#безопасность-и-creds)
- [Обновление и переезд](#обновление-и-переезд)
- [Разница с ALC](#разница-с-alc)

## Установка и запуск

**Q: На каком порту по дефолту работает DC?**
A: 8086. Можно сменить через `--port 9000` при запуске uvicorn или через настройку `port`.

**Q: Как остановить ai-dreaming-center?**
A: Ctrl+C в окне uvicorn. Все running-сессии Claude получат signal через watchdog или закроются по `cancel_remaining_tasks` в lifespan-shutdown.

**Q: Как запустить как Windows-сервис / systemd?**
A: См. `../deployment.md` — там описание для NSSM (Windows), Task Scheduler, и systemd.

**Q: Если я перезагружу машину — running-сессии переживут?**
A: Нет. Subprocess'ы claude'а умрут вместе с uvicorn. Их DB rows будут в статусе `running`, и через 5 минут после рестарта DC reconcile job их закроет как `failed`.

**Q: Можно ли запустить DC на одной машине, а Claude CLI на другой?**
A: Нет. DC спавнит `claude` через локальный `asyncio.create_subprocess_exec` — Claude должен быть на той же машине.

**Q: Поддерживается ли macOS / Linux?**
A: Да. Windows-специфичный код (`shutil.which("claude")` подхватывает `claude.cmd`, KeepAwake) — defensive: на других ОС не делает ничего вредного.

**Q: Что если я открою `/` без `config.yaml`?**
A: Middleware redirect'ит тебя на `/setup`. Все остальные routes тоже редиректятся, кроме `/static/*`.

## Запуск сессий

**Q: Сколько сессий могут идти одновременно?**
A: Глобально — `max_concurrent` (default 1). Per-project — `per_project_max_concurrent` если задан. Если очередь полна — кнопка `Start session` отдаст 409 или поставит в очередь.

**Q: Что значит «session timeout»?**
A: Watchdog убивает процесс claude'а через `timeout_minutes` минут после старта (default 20). Часто это значит, что агент попал в loop или ждёт что-то, что не приходит.

**Q: Я нажал Kill, но процесс всё ещё в логах?**
A: Kill шлёт terminate, потом через ~5 секунд kill -9. Если скрипт claude'а перехватывает signal — может задержаться. Жди до 30 секунд, потом проверь Task Manager / `ps aux | grep claude`.

**Q: Как агент узнаёт, что он в self-study режиме?**
A: DC передаёт ему prompt вида `/self-study {agent_name}`. Slash-команда `self-study` живёт в `~/.claude/commands/self-study.md` (через agent-team-starter-kit) и описывает задачу.

**Q: Я добавил новый md-файл в `.claude/agents/`, но в Rotation его нет.**
A: Открой `/p/{slug}/rotation` — при загрузке страницы DC сканирует filesystem и автоматически добавляет недостающие агенты с `tier=2`. Если всё равно нет — проверь, что файл валидный markdown и имя без пробелов.

**Q: Можно ли передать агенту дополнительный контекст?**
A: Через Kanban: добавь custom topic с указанием `target_agents`. Nightly cron подмешает его в prompt. См. [`features/topics-kanban.md`](features/topics-kanban.md).

**Q: Где смотреть полный stdout сессии после её завершения?**
A: На `/live` — только в момент streaming'а. После завершения JSONL остаётся в `~/.claude/projects/<workdir>/<session>.jsonl` — это файл самого Claude, DC его не дублирует.

## Tech-debt и Product ideas

**Q: Откуда берутся tech-debt items?**
A: Их пишет weekly_tech_debt_scan агент в `tech_debt_dir`. По дефолту scanner off — нужно включить (см. [`workflows/weekly-scanners.md`](workflows/weekly-scanners.md)).

**Q: Можно ли создать tech-debt item вручную через UI?**
A: Нет. UI только закрывает (`close`) и удаляет (`delete`). Создание — через scanner или ручной правкой md-файла в `tech_debt_dir`.

**Q: Что значит close на findings?**
A: DC переписывает frontmatter: `status: closed`. Файл остаётся, в списке findings элемент перестаёт показывать кнопку `close`. Если у тебя фильтр по статусу — можно скрыть closed.

**Q: Удалю findings — потеряется ли история?**
A: Файл физически удалится с диска. Если у тебя репо под git'ом — он будет в истории, можно восстановить через `git restore`.

**Q: Зачем кнопка `→ Jira` если я могу руками?**
A: DC берёт title и body из md-файла, создаёт Jira Task через REST API, и записывает обратный линк (`jira_ticket: PROJ-123`) в frontmatter. Меньше шансов забыть/опечататься.

## Cron и расписание

**Q: Где смотреть, какие cron-jobs зарегистрированы?**
A: В UI пока нет страницы. В техническом отладе — см. [`../troubleshooting.md`](../troubleshooting.md), там команда для введения introspection в lifespan.

**Q: Как изменить время nightly?**
A: `/settings` → группа «Scheduling — nightly» → ключ `cron_expression`. Формат — стандартный 5-частный cron.

**Q: Cron не сработал ночью. Что проверить?**
A: 1) `cron_enabled = true` (глобально и per-project, если override). 2) `enabled = true` у проекта. 3) DC сервер не падал в момент cron'а — посмотри uvicorn логи. 4) В rotation хотя бы один агент с `enabled = true`.

**Q: Что если DC выключен в момент срабатывания cron'а?**
A: Job не запустится. Когда DC снова стартует, scheduler возьмёт следующий tick. Backfill за пропущенный — нет.

**Q: Можно ли разное расписание для разных проектов?**
A: Да. На `/p/{slug}/settings` ставишь `cron_expression` в `override`, выбираешь радиокнопку Override, вписываешь свой cron — Save.

## Безопасность и creds

**Q: Где хранится Jira API token?**
A: По дефолту — в `config.yaml` (если ты ввёл через global settings) или в `project_settings` table (если через per-project). Оба файла лучше не коммитить — `config.yaml` не в .gitignore тебе нужно положить, а `data/dreaming.db` тоже исключить.

**Q: Можно ли token хранить в env?**
A: Да. Pydantic-settings читает env vars с префиксом `DC_`. Например `DC_JIRA_API_TOKEN=...`.

**Q: DC сам кому-то отправляет данные?**
A: Только Jira (если ты создаёшь тикет) и Anthropic (когда Claude делает API-запросы). Никакой телеметрии в DC встроено нет.

**Q: Кто может попасть в UI?**
A: Аутентификации в DC нет. Если ты слушаешь на `0.0.0.0:8086` — все, кто доступен по сети, увидят твою БД. Используй `host = 127.0.0.1` для local-only или закрой firewall'ом.

## Обновление и переезд

**Q: Как обновить DC?**
A: `git pull && pip install -e .` в активном venv. Перезапусти uvicorn. Schema migrations идут идемпотентно при первом подключении — их не нужно запускать руками.

**Q: Если я перенесу `data/dreaming.db` на другую машину?**
A: Перенеси также `config.yaml` (там пути) и `~/.claude/projects/<workdir>/...` если хочешь сохранить AI Usage историю. На новой машине пути будут другие — поправь `working_dir` в registry.

**Q: Как сбросить DB и начать с нуля?**
A: Останови uvicorn, удали `data/dreaming.db` и `data/dreaming.db-wal/.db-shm`, запусти снова. Schema создастся пустая.

## Разница с ALC

**Q: В чём отличие DC от agent-learning-center?**
A: DC — мульти-проектная версия. ALC работает с одним проектом (one `working_dir`); DC — N проектов сразу с registry, agg dashboard и orchestration. Schema форк-greenfield: 14 ALC-таблиц получили `project_id`, добавились 2 новых (`projects`, `project_settings`).

**Q: Можно ли использовать ALC и DC одновременно?**
A: Да. Они слушают разные порты (8085 vs 8086), у них разные SQLite БД (`data/learning.db` vs `data/dreaming.db`). Никаких конфликтов.

**Q: Я могу мигрировать данные из ALC в DC?**
A: Не автоматически. Нужно вручную выполнить ETL — экспорт ALC через SQL, transformation (добавить `project_id`), импорт в DC. Это разовая операция, не задокументирована — пиши issue если нужно.

**Q: ALC всё ещё развивается?**
A: ALC — single-project, base, не получает новых фич. Все новые волны (orchestration, cascade, AI usage) идут только в DC.
