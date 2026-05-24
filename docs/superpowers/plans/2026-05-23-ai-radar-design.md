# AI Radar — план фичи «Исследование лидеров и трендов ИИ»

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` или `superpowers:executing-plans`. Шаги — чекбоксы `- [ ]`.

**Цель.** Добавить в AI Dreaming Center раздел **AI Radar**: каталог лидеров и лабораторий ИИ (Karpathy, Sutskever, Anthropic, OpenAI, DeepMind, Mistral, xAI, HF, Meta AI, китайские лаборатории и др.) + периодический скан их публичной активности (твиты, блог-посты, paper-релизы, модели на HF, кейноуты, подкасты) с фильтром «новые веяния» и связкой результатов с уже существующими сущностями ADC (idea / topic / tech-debt / wiki / note).

**Зачем.** В центре уже есть локальные источники (per-project scans, weekly checklist). Не хватает внешнего слоя — что происходит в индустрии прямо сейчас и какие из этих сигналов стоит «втащить» внутрь конкретного проекта (как идею, как тему недели, как зависимость, как тех-долг).

**Архитектура (коротко).**
- Глобальный раздел `/ai-radar` (рядом с `/ai-usage`, `/projects`, `/settings`) + per-project linker `/p/{slug}/ai-radar` для отфильтрованной по релевантности ленты.
- Watchlist (источники) — YAML под `data/ai-radar/sources.yaml`; редактируется из UI настроек.
- Хранение findings — SQLite-таблица `ai_radar_findings` (greenfield, без миграций).
- Скан — Claude CLI команда `/ai-radar-scan`, живёт в выбранном «host-проекте» (`.claude/commands/ai-radar-scan.md`) в соответствии с правилом из `CLAUDE.md`: агенты/команды лежат в репозитории проекта, не в этом репозитории. `radar_host_project` — глобальная настройка (slug одного из импортированных проектов).
- Планировщик — глобальный недельный job (а не `_PER_PROJECT_JOBS`), управляется через `radar_scan_cron` / `radar_scan_enabled` в `config.yaml`.
- Интеграция «в центр» — у каждого finding есть кнопка «применить»: создать запись в `product_ideas` / `topics` / `tech_debt` / `notes` целевого проекта (через существующие сервисы).

**Не входит в этот план.** Полноценный crawler с парсингом HTML/RSS своими силами. Скан выполняет Claude CLI с `WebSearch`/`WebFetch` (как у `/topics-scan`); собственный парсер появится только если упрётся в лимиты — отдельным waveʼом.

**Спека.** Этот документ выполняет роль одновременно спеки и плана wave-ов R1…R3. При утверждении его можно расщепить на `docs/superpowers/specs/2026-05-23-ai-radar-design.md` (общая картина) + три wave-плана.

---

## Контракт фичи

### Что считается «findings»

Запись в `ai_radar_findings`:

| Поле                 | Тип        | Примечание                                                              |
|----------------------|------------|-------------------------------------------------------------------------|
| `id`                 | INTEGER PK |                                                                          |
| `source_key`         | TEXT       | `karpathy_x`, `anthropic_blog`, `openai_blog`, `hf_models`, ...         |
| `source_kind`        | TEXT       | `person` \| `org` \| `feed` \| `paper_venue`                            |
| `url`                | TEXT       | каноничная ссылка                                                        |
| `title`              | TEXT       | заголовок / первая строка                                                |
| `summary_ru`         | TEXT       | 1–3 предложения, генерит модель                                          |
| `summary_en`         | TEXT       | то же на EN                                                              |
| `published_at`       | DATETIME   | если удалось извлечь                                                     |
| `discovered_at`      | DATETIME   | момент попадания в БД                                                    |
| `tags`               | TEXT       | JSON-массив (`['agents','rlhf','inference','eval']`)                    |
| `novelty_score`      | REAL       | 0..1 — оценка «насколько новое веяние», ставится моделью при скане       |
| `relevance_hint`     | TEXT       | свободный список slug-ов проектов («куда вероятно применимо»)            |
| `status`             | TEXT       | `new` \| `seen` \| `applied` \| `dismissed`                              |
| `applied_to_kind`    | TEXT       | `idea` \| `topic` \| `tech_debt` \| `note` \| NULL                       |
| `applied_to_ref`     | TEXT       | внешний id/path в целевом сервисе                                        |
| `raw_payload`        | TEXT       | JSON, чтобы не терять оригинал                                           |

Уникальность: `UNIQUE(source_key, url)` — повторный скан не плодит дубли.

### Watchlist (`data/ai-radar/sources.yaml`)

```yaml
people:
  - key: karpathy
    name: "Andrej Karpathy"
    x: "https://x.com/karpathy"
    blog: "https://karpathy.github.io/"
    youtube: "https://www.youtube.com/@AndrejKarpathy"
    tags: [education, agents, llm-internals]
  - key: sutskever
    name: "Ilya Sutskever"
    org: "Safe Superintelligence"
  # ...
orgs:
  - key: anthropic
    name: "Anthropic"
    blog: "https://www.anthropic.com/news"
    research: "https://www.anthropic.com/research"
    tags: [safety, claude, interpretability]
  - key: openai
    name: "OpenAI"
    blog: "https://openai.com/blog"
  - key: deepmind
    name: "Google DeepMind"
    blog: "https://deepmind.google/discover/blog/"
  # ...
feeds:
  - key: hf_daily
    name: "Hugging Face Daily Papers"
    url: "https://huggingface.co/papers"
    tags: [papers]
  - key: arxiv_cs_cl
    name: "arXiv cs.CL новинки"
    url: "http://export.arxiv.org/rss/cs.CL"
```

Файл редактируется руками или из UI настроек (textarea с YAML-валидацией) — никакого секретного формата. Если файла нет, фича гасит сама себя (`/ai-radar` показывает onboarding-карточку «добавьте источники»).

### Сканер (Claude command `/ai-radar-scan`)

Команда живёт в `.claude/commands/ai-radar-scan.md` host-проекта. Промпт:

1. Прочитать `data/ai-radar/sources.yaml` (путь приходит из env `DREAMING_RADAR_SOURCES`).
2. Для каждого источника:
   - WebFetch (или WebSearch для тех, у кого только бренд без RSS) — взять последние N материалов с момента `since` (env `DREAMING_RADAR_SINCE`, ISO-дата прошлого успешного скана).
   - Для каждого нового материала собрать поля `title`, `url`, `published_at`, `summary_ru`, `summary_en`, `tags`, `novelty_score`, `relevance_hint` (на основе списка известных проектов из env `DREAMING_RADAR_PROJECTS`).
3. Сохранить пачку как `data/ai-radar/inbox/{YYYY-MM-DD}-{source_key}.json`.
4. Завершить с человекочитаемым отчётом в stdout.

ADC после успешного завершения job-а читает `inbox/*.json`, мёрджит в `ai_radar_findings` (INSERT OR IGNORE по `UNIQUE(source_key, url)`), переносит обработанные файлы в `data/ai-radar/archive/`.

### UI

**Глобальная страница `/ai-radar`:**
- Top bar: фильтры (по источнику, по типу, по тегу, по статусу), переключатель «только новое за 7 дней».
- Лента карточек: заголовок → 2 строки саммари (RU по умолчанию, тоггл EN) → источник + дата → теги-чипы → кнопки `Применить в...` (popover с выбором проекта и типа сущности), `Скрыть`, `Уже видел`.
- Боковая колонка: топ-теги недели + список людей/орг с количеством новых.

**Per-project `/p/{slug}/ai-radar`:**
- Та же лента, отфильтрованная: `relevance_hint` содержит `slug` ИЛИ user вручную нажал «закрепить за проектом».
- Применённые findings показываются с обратной ссылкой на созданную сущность (idea PI-N / topic / tech-debt-row).

**Глобальные настройки `/settings` → блок «AI Radar»:**
- `radar_host_project` (dropdown из импортированных проектов).
- `radar_scan_cron` (default `0 7 * * 1` — понедельник 07:00).
- `radar_scan_enabled` (default `false`, чтобы фича не молотила без явного включения).
- Кнопка «Открыть `sources.yaml`» (показ + правка с YAML-валидацией).
- Кнопка «Запустить скан сейчас» (триггерит тот же job вне расписания).

---

## Структура файлов

**Новые файлы:**
- `dreaming/services/ai_radar.py` — сервис: парс YAML, мердж inbox в БД, фильтры, apply-to-X.
- `dreaming/routes/ai_radar.py` — глобальные роуты `/ai-radar`, `/ai-radar/apply`, `/ai-radar/scan-now`.
- `dreaming/routes/project_ai_radar.py` — per-project `/p/{slug}/ai-radar`.
- `dreaming/templates/ai_radar.html` — глобальная лента.
- `dreaming/templates/project_ai_radar.html` — per-project лента.
- `dreaming/templates/_ai_radar_card.html` — partial карточки finding-а.
- `scripts/smoke_ai_radar.py` — smoke: импорт sources.yaml, инжест из mock-inbox, проверки apply-to-idea/topic.
- `docs/superpowers/specs/2026-05-23-ai-radar-design.md` — расщепление этого документа на формальную спеку (опционально, после ревью).

**Изменяемые файлы:**
- `dreaming/services/db.py` — таблица `ai_radar_findings` + helpers `insert_findings`, `list_findings`, `mark_status`.
- `dreaming/services/scheduler.py` — глобальный job `_radar_scan_job` (по аналогии с `_reconcile_job` / `_ai_usage_ingest_job`), регистрация в `build_scheduler` под флагом `radar_scan_enabled`.
- `dreaming/config.py` — поля `radar_host_project: str | None`, `radar_scan_cron: str`, `radar_scan_enabled: bool`.
- `dreaming/main.py` — регистрация двух новых роутеров; mount static если потребуется иконка.
- `dreaming/templates/_sidebar.html` — пункт «AI Radar» в секции `sidebar.section.global` и в per-project блоке.
- `dreaming/templates/settings.html` — блок настроек radar.
- `dreaming/i18n/messages_ru.json` + `messages_en.json` — ключи `radar.*` (`title`, `card.apply`, `card.dismiss`, `filter.new_week`, `settings.host_project`, `settings.cron`, `settings.enabled`, `settings.run_now`, ...).
- `config.example.yaml` — комментированные дефолты для радара.
- `scripts/check_i18n.py` — должен пройти после добавления новых ключей.

**Не трогаем (намеренно):**
- Существующие weekly-jobs (`weekly_topics_scan` и пр.) — radar живёт глобально, не дублирует per-project pipeline.
- Хранилище идей/тем — apply-to-X пишет через их публичные сервисы (`product_ideas.create_*`, `topics`/`checklist`, `tech_debt.create_*`, `notes`), без дублирования таблиц.

---

## Wave R1 — Каркас и ручное наполнение (≈ полдня)

Цель: страница `/ai-radar` работает на seed-данных, без какого-либо скана.

- [ ] **R1.1.** Схема: миграция (создание таблицы) в `db.py` + `insert_findings(records: list[dict])`, `list_findings(filter)`, `set_status(id, status)`.
- [ ] **R1.2.** Сервис `ai_radar.py`: `load_sources(path) -> Watchlist`, `merge_inbox(db, inbox_dir) -> int`, `apply_finding(db, projects, finding_id, kind, target_project) -> ref`.
- [ ] **R1.3.** Роут `/ai-radar` (GET) + шаблон `ai_radar.html`: лента, фильтры, RU/EN toggle.
- [ ] **R1.4.** Роут `/ai-radar/{id}/status` (POST) + `/ai-radar/{id}/apply` (POST).
- [ ] **R1.5.** Per-project `/p/{slug}/ai-radar` (GET) + шаблон `project_ai_radar.html`.
- [ ] **R1.6.** Сайдбар: пункт «AI Radar» в global-секции и в per-project.
- [ ] **R1.7.** i18n ключи (RU/EN); `scripts/check_i18n.py` — green.
- [ ] **R1.8.** Seed: положить `scripts/seed_ai_radar.py` — 5 фейковых findings (Karpathy / Anthropic / OpenAI / HF / arXiv), чтобы UI было что показывать.
- [ ] **R1.9.** Smoke: `scripts/smoke_ai_radar.py` — sources.yaml парсится, seed заезжает в БД, apply-to-idea создаёт реальный `PI-N.md` (или в `notes`, если PI-сервис недоступен в смоке).

**Acceptance R1:**
1. `GET /ai-radar` показывает 5 seed-карточек.
2. Кнопка «Применить → topic» создаёт запись в `topics` выбранного проекта.
3. Фильтр «новое за 7 дней» работает, статусы переключаются и сохраняются.

---

## Wave R2 — Реальный скан через Claude CLI (≈ день)

- [ ] **R2.1.** Глобальные настройки: поля в `config.py` + блок в `/settings`.
- [ ] **R2.2.** Шаблон команды `/ai-radar-scan` — отдать в `docs/agents/ai-radar-scan.md` (заготовка, которую пользователь сам положит в `.claude/commands/` host-проекта; в этом репо хранится только описание).
- [ ] **R2.3.** Job `_radar_scan_job(app_state)` в `scheduler.py`:
  - читает `radar_host_project`, резолвит проект через `projects.get_by_slug`;
  - вычисляет `since` = max(`published_at`) из БД или 14 дней назад;
  - вызывает `pm.start_command(proj, command_name="ai-radar-scan", prompt="/ai-radar-scan", ...)` с env `DREAMING_RADAR_SOURCES`, `DREAMING_RADAR_SINCE`, `DREAMING_RADAR_PROJECTS`;
  - по успешному завершению — вызывает `ai_radar.merge_inbox(...)`.
- [ ] **R2.4.** Регистрация job в `build_scheduler` по флагу `radar_scan_enabled` (cron из настроек, fallback `0 7 * * 1`).
- [ ] **R2.5.** Кнопка «Запустить сейчас» в `/settings` — POST в `/ai-radar/scan-now`, который дёргает тот же job вне расписания и редиректит на `/ai-radar`.
- [ ] **R2.6.** Smoke: добавить в `scripts/smoke_ai_radar.py` сценарий «положили fake-inbox JSON → merge_inbox → новые findings».

**Acceptance R2:**
1. С включённым `radar_scan_enabled` и валидным `radar_host_project` job отрабатывает по cron-у (проверка ручным запуском через кнопку).
2. После запуска `data/ai-radar/inbox/*.json` появляется, мёржится в БД, перемещается в `archive/`.
3. Двойной запуск не плодит дубли (UNIQUE-индекс).

---

## Wave R3 — Интеграция «внутрь центра» (≈ день)

- [ ] **R3.1.** «Применить → idea»: вызов `product_ideas.create(...)` (или прямая запись `PI-{N}.md`) с предзаполненными `title`, `summary`, `tags`, `source_url`, `discovered_at`.
- [ ] **R3.2.** «Применить → topic»: дописать пункт в `_weekly-learning-checklist.md` выбранного проекта (через `checklist.append_item`).
- [ ] **R3.3.** «Применить → tech-debt»: запись в `tech_debt`-сервис.
- [ ] **R3.4.** «Применить → note»: создать markdown в notes-каталоге проекта.
- [ ] **R3.5.** Обратные ссылки: на странице idea/topic/tech-debt — badge «Из AI Radar: {source} — {date}» с deep-link к карточке.
- [ ] **R3.6.** Per-project лента (`/p/{slug}/ai-radar`) использует `relevance_hint` + ручной pin (`POST /ai-radar/{id}/pin?project={slug}`).
- [ ] **R3.7.** Дашборд проекта (`project_dashboard.html`) — мини-виджет «Свежие сигналы AI Radar» (последние 3 finding-а с `relevance_hint = slug`).

**Acceptance R3:**
1. Все четыре цели apply-to работают и оставляют обратную ссылку.
2. На дашборде проекта виден виджет с релевантными свежими сигналами.

---

## Принятые решения

### 1. Host-проект — переиспользуем существующий, не плодим meta-проект

**Решение.** `radar_host_project` — slug любого уже импортированного проекта. По умолчанию подставляется проект, чей `working_dir` совпадает с корнем ADC (если он импортирован), иначе — первый enabled-проект из списка. Создание отдельного фейкового `ai-radar-host` отклонено: лишний проект в дашборде, лишний CRON-таб «никогда не используемого» проекта.

**Защита от мусора.** При включении `radar_scan_enabled` сервис проверяет:
- проект существует и `enabled = true`;
- в `{working_dir}/.claude/commands/ai-radar-scan.md` лежит команда (если нет — UI показывает кнопку «Установить шаблон команды», которая копирует заготовку из `docs/agents/ai-radar-scan.md` в проект).

Если оба условия не выполняются — флаг не включается, ошибка с понятной формулировкой в `/settings`.

**Эффект на план.** В R2.1 добавить валидацию `radar_host_project` в `dreaming/config.py` (Pydantic-валидатор, который проверяет существование проекта только при `radar_scan_enabled=true`, чтобы дефолтный конфиг загружался). В R2.2 — добавить шаг «при первом старте предложить установить шаблон».

### 2. WebFetch квоты — батчируем по 5 источников, dispatcher-job

**Решение.** Не один моноскан на 30 источников, а **dispatcher-pattern**: глобальный недельный job создаёт **батчи по 5 источников** и для каждого батча запускает отдельный `pm.start_command(..., command_name="ai-radar-scan", prompt="/ai-radar-scan --batch={i}")` с паузой `wait_between_sec` между запусками (тот же ConfigResolver-ключ, что у `nightly_learning`). У каждого батча свой `max_turns=25` и `timeout_minutes=20` — поместится в стандартный per-project лимит.

**Почему батчи, а не один большой запуск.** При 30 источниках `WebFetch` подряд в одной сессии: (а) рискуем словить `max_turns` или 20-минутный timeout, (б) если упадёт на 25-м источнике — теряем всю сессию, а не один батч.

**Семантика `--batch={i}`.** Команда принимает индекс батча, берёт срез `sources[i*5 : (i+1)*5]` детерминистично (по порядку из YAML). Это позволяет ретраить отдельный батч руками и не дублировать findings (`UNIQUE(source_key, url)`).

**Эффект на план.** Переписать R2.3 — job не выполняет скан, а планирует N запусков команды. R2.4 — `radar_scan_batch_size` (default 5) в `config.py`. Inbox-файлы получают суффикс батча: `{YYYY-MM-DD}-batch-{i}-{source_key}.json`. Merge-шаг (`ai_radar.merge_inbox`) — отдельный лёгкий job, запускается каждые 5 минут и подметает inbox (по аналогии с `_ai_usage_ingest_job`).

### 3. Саммари — оба языка сразу, без оптимизации

**Решение.** Скан генерит `summary_ru` и `summary_en` за один проход. +20–30% токенов на запуск, но: (а) запуск раз в неделю, (б) UI с RU/EN-тоггл уже существует и оба языка ожидаются «бесплатно» без второго round-trip, (в) повторный проход «генерь второй язык по запросу» требует отдельной команды и кэша — overengineering для wave R2.

**Эффект на план.** Никаких — это и так был дефолт. Фиксируем в спеке как **окончательное** решение.

### 4. `sources.yaml` живёт в `data/ai-radar/`, override через конфиг

**Решение.** Дефолт: `data/ai-radar/sources.yaml` в репозитории ADC (`data/` уже gitignored — пользовательский конфиг не утекает в коммиты). Опциональный override `radar_sources_path` в `config.yaml` для тех, кто хочет держать список в `{working_dir}/.claude/ai-radar/sources.yaml` host-проекта (для версионирования вместе с проектом).

**Почему не каноничный путь по `CLAUDE.md`-конвенции.** Правило «агенты живут в `.claude/agents/` проекта» относится к **исполняемым артефактам** (промптам команд, sub-agentʼам). `sources.yaml` — это **данные ADC** (watchlist радара), а не промпт. Дашборд оперирует ими напрямую (UI-редактор, валидация), и держать данные в полу-чужой директории host-проекта неудобно: смена `radar_host_project` потеряет список источников.

**Эффект на план.** В R1.2 `load_sources(path)` принимает путь явно (как сейчас задумано). В R2.1 при загрузке настроек: `path = settings.radar_sources_path or "data/ai-radar/sources.yaml"`. Команда `/ai-radar-scan` получает абсолютный путь через env `DREAMING_RADAR_SOURCES` — ей всё равно, откуда он.

---

## Сводка изменений в плане после решений

- R2.1 → добавить Pydantic-валидатор `radar_host_project` (lazy, активен только при `radar_scan_enabled=true`) + поле `radar_scan_batch_size` (default 5) + `radar_sources_path` (default `null` → `data/ai-radar/sources.yaml`).
- R2.2 → добавить шаблон команды в `docs/agents/ai-radar-scan.md` с поддержкой `--batch={i}` и шаг «Установить шаблон в host-проект» (одноклик-кнопка в `/settings`).
- R2.3 → переписать как **dispatcher**: вычислить число батчей, запустить их через `pm.start_command` с паузой; merge — отдельный 5-мин job, как `_ai_usage_ingest_job`.
- R2.4 → регистрация **двух** глобальных jobʼов: dispatcher (cron) + inbox-merge (interval 5 мин, всегда включён, no-op если inbox пуст).
- Acceptance R2 → добавить: «один упавший батч не блокирует остальные» (проверка ручным удалением одного inbox-файла перед merge).

---

## Тег и порядок мержа

После прохождения R1-R3 — тег `radar-1` (по аналогии с `wave-N`). Каждая wave мержится отдельным PR в основную ветку (`main`); фича выкатывается выключенной (`radar_scan_enabled: false`), включается явно в `config.yaml` после ручной приёмки.
