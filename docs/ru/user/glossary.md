# Глоссарий

Термины, которые встречаются в DC и его документации. Сортировка по русскому алфавиту, но в скобках — английское/техническое имя, под которым понятие появляется в коде и UI.

## A–Z базовых терминов

**ALC (Agent Learning Center)** — single-project предок DC. Если у тебя где-то крутится экземпляр ALC — он не конфликтует с DC: разные порты, разные базы.

**APScheduler** — библиотека планировщика. DC использует `AsyncIOScheduler`. Технически невидимый для пользователя, но если в логах увидишь `apscheduler.scheduler` — это он.

**Cascade (каскад)** — конвейер из 5 фаз: contract → design → implementation → review → qa, где между фазами есть gate-verdict (approve / return-to-stage / reject). Запускается через orchestration с типом `cascade`. Подробнее в [`features/cascade.md`](features/cascade.md).

**ClaudeSessionTail** — внутренний компонент DC, который читает stdout claude'а в JSONL-формате и рассылает события в SSE-стрим и в orchestrator events. Пользователю невидим.

**Claude Code project (vs DC project)** — Claude Code хранит свою историю в `~/.claude/projects/<workdir>/...`. DC project — запись в таблице `projects` с маппингом slug ↔ working_dir. Это разные вещи: один Claude Code project может быть DC project'ом, а может и нет.

**Claude project dir** — `claude_projects_dir` в настройках, по умолчанию `~/.claude/projects/`. Откуда DC ingest'ит JSONL для AI Usage аналитики.

**Cron expression** — 5-частная строка вроде `0 3 * * *` (минута / час / день / месяц / день-недели). Используется в `cron_expression`, `weekly_*_cron`. Парсер — APScheduler.

**Custom topic** — запись в таблице `custom_topics`, добавляется через Kanban. Подмешивается в prompt nightly self-study.

**DC (AI Dreaming Center)** — этот проект. В коде префикс env vars `DC_`.

**Default project** — проект, отмеченный `is_default=true` в registry. Влияет на главную страницу `/` (если есть default — редирект на его dashboard; иначе показывается aggregated).

**Disable / Enable** — toggle в registry: disabled-проекты исчезают из dropdown'а в шапке, их cron-jobs автоматически unregister'ятся, но данные в БД сохраняются.

**Domain (wiki)** — отдельный markdown-файл в `wiki_dir`, описывающий один логический домен проекта (auth, billing, ui-shell). Их количество показывается на `/p/{slug}/wiki`.

**Evolution** — markdown-файл в `_context/` каталоге проекта, описывающий override behaviour агента (что-то типа personality patch). Видны на `/p/{slug}/evolutions`.

**Finding (sidecar)** — JSON-отчёт reviewer-агента (vera/svetlana/silent-failure-hunter) в `sidecar_findings_dir`. Каждый — bag of fields: id, severity, module, file, rule, title.

**Gate verdict** — решение оркестратора на границе stage'а cascade'а: `approve` (двигаем дальше), `return-to-stage` (возвращаем итерацию), `reject` (run fail).

**Inherit / Override** — механизм наследования настроек. Per-project значение в `project_settings` либо наследует global default (inherit), либо подменяет (override). См. [`features/settings.md`](features/settings.md).

**Jira ticket** — ID тикета в Jira (например `PROJ-1234`). Сохраняется в frontmatter md-файла идеи после успешного `→ Jira` action'а.

**Kanban** — доска custom topics, страница `/p/{slug}/kanban`. CRUD над `custom_topics` таблицей.

**Kill (button)** — POST-запрос на `/p/{slug}/live/kill/{agent}`. Шлёт terminate в subprocess claude'а; DB row помечается failed.

**KeepAwake** — Windows-специфичный сервис, который запрещает Modern Standby пока есть running-сессии. На macOS/Linux no-op.

**Locale** — язык интерфейса: `ru` или `en`. Хранится в куке `dc_locale`. Переключается кнопкой `EN/RU` в шапке.

**Loop** — markdown-файл в `loops_dir`. Описывает «reflex-loop» агента (повторяющийся самокорректирующийся цикл). На `/p/{slug}/loops` — список с iterations counter.

**Node (orchestrator)** — узел в орке́страции: один агент в run'е. Может быть root (Orchestrator) или sub-agent. Видны на detail-странице run'а.

**Note (конспект)** — markdown-файл, который агент пишет по итогам self-study. Лежит в `learning_notes_dir`. Путь записывается в `agent_learning_sessions.note_path`.

**Plan** — markdown-файл с tasks-чек-листом, который Orchestrator пишет в `plans_dir`. На странице — progress bar (`done/total`).

**Process Manager** — внутренний компонент DC, отвечающий за spawn/track/kill всех subprocess'ов claude. Невидим пользователю.

**Product idea** — markdown-файл в `product_ideas_dir` с frontmatter (id/title/status/priority/jira_ticket). Создаётся weekly_product_ideas_scan'ером.

**Project (DC project)** — запись в `projects` таблице. Уникальный slug, label, working_dir, флаги enabled/is_default.

**Projects root** — корневой каталог под которым лежат все DC-проекты. По умолчанию `D:\Work\micode\` или подобное.

**Reconcile job** — interval-job который раз в 5 минут смотрит running-сессии в БД, и если процесс claude'а уже мёртв — закрывает row статусом `failed`/`timeout`.

**Resume** — продолжение оркестрации: спавн нового claude-subprocess'а с `--resume {session_id}`. Доступно для finished-runs.

**Orchestrator** — корневой агент-оркестратор. В коде `agent_name="orchestrator"`, `role="orchestrator"`. Запускается через форму на `/p/{slug}/orchestration`. Раньше (до 2026-05-12) назывался **Roman** — старые run'ы в DB могут иметь `agent_name="roman"`, это backward-compat, нового кода это не касается.

**Rotation** — список агентов проекта с tier и enabled-флагом. Используется ночным cron'ом для выбора top-N кандидатов на сегодня.

**Scheduler** — компонент DC с APScheduler внутри. Регистрирует cron-jobs для каждого включённого проекта.

**Autoconfig (каталоги)** — one-click механизм на 8 dashboard-страницах: создаёт дефолтный каталог (`docs/<feature>/` или `.claude/agents/<feature>/`) и сохраняет per-project setting. Дефолты в `dreaming/services/autoconfig.py:DEFAULTS`. См. [`features/out-of-the-box.md`](features/out-of-the-box.md#autoconfig-каталогов).

**Orphan (session)** — row в `agent_learning_sessions` со `status='running'`, у которого процесс умер, но запись не закрылась. Возникает из-за Wave-0 reconcile-бага. Лечится кнопкой Force-close на dashboard'е.

**Self-study** — slash-команда `/self-study {agent}`, заставляющая Claude перечитать свой агент-файл и написать конспект.

**Session (agent learning)** — одна попытка self-study. Запись в `agent_learning_sessions` (id, project_id, agent_name, status, started_at, finished_at, note_path, error_message).

**Sidecar (reviewer)** — отдельный агент-ревьюер (vera, svetlana, silent-failure-hunter) который пишет JSON-отчёты в `sidecar_findings_dir`. Запускается через слэш-команды или Orchestrator'ом.

**Slash-command** — команда вида `/{name}` которую Claude понимает. DC спавнит claude с одним из таких prompts (`/self-study agent`, `/wiki-bootstrap`, etc.).

**Starter-kit** — набор файлов под `templates/starter-kit/` в репо DC, которые мирорятся в `{working_dir}/.claude/` проекта (slash-команды + skeleton'ы типа weekly checklist). Установка через UI-кнопку на Ротации/Темах или через `scripts/install_starter_kit.py`. См. [`features/out-of-the-box.md`](features/out-of-the-box.md#starter-kit).

**Slug** — короткий машинный идентификатор проекта (`my-app`, `wishlist`, `mi-code-ai`). Уникален. Не меняется через UI (только через DB).

**SSE (Server-Sent Events)** — way of pushing live-events from server to browser. Используется для streaming stdout на `/live` и polling-replacement на orchestration detail.

**Stage (cascade)** — одна из 5 фаз cascade'а: contract, design, implementation, review, qa. Каждый — отдельный set of nodes.

**Status (session)** — `running` / `success` / `failed` / `timeout`. Тру-статусы terminal'ные кроме `running`.

**Subagent** — child claude-process, спавненный через Task/Agent tool из Orchestrator'а. Виден как отдельный node на orchestration detail.

**Tech debt (тех-долг)** — markdown-файл в `tech_debt_dir` с frontmatter (id/title/status/priority/module). Создаётся weekly_tech_debt_scan'ером.

**Tier** — приоритет агента в rotation: 1 (high) / 2 (normal, default) / 3 (low). Влияет на сортировку в nightly cron при выборе top-N.

**Topic (weekly checklist)** — пункт из weekly-learning-checklist.md (read-only, генерируется агентом-стартеркитом). Видим на `/p/{slug}/topics`.

**Watchdog** — async-task который убивает claude-subprocess по истечении `timeout_minutes`.

**Weekly scanner** — opt-in cron-job вида `weekly_tech_debt_scan_{slug}`, `weekly_product_ideas_scan_{slug}`, `weekly_wiki_lint_{slug}`. По дефолту off, включается через project settings.

**Working dir** — абсолютный путь к папке проекта на диске. Один из ключевых атрибутов записи `projects`. Передаётся как cwd при спавне claude'а.

Если встретишь термин, которого здесь нет — посмотри в [`../README.md`](../README.md) (там тоже есть глоссарий) или в [`faq.md`](faq.md).
