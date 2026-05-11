# Установка «из коробки»

DC при первом заходе в новый проект **не** требует от тебя руками копировать slash-команды и прописывать пути к каталогам в `config.yaml`. Везде, где раньше было сообщение «не настроено / не существует», теперь стоит inline-кнопка, которая создаёт нужное за один клик.

Эта страница рассказывает про четыре механизма:

- [Bootstrap everything](#bootstrap-everything) — master-кнопка на дашборде, делает starter-kit + autoconfig разом.
- [Starter-kit](#starter-kit) — установка slash-команд (`/self-study`, weekly checklist, и т.п.) из шаблонов в репо.
- [Autoconfig каталогов](#autoconfig-каталогов) — one-click создание `docs/tech-debt/`, `docs/wiki/`, и т.п. с одновременным сохранением настройки `*_dir`.
- [Управление сессиями](#управление-сессиями) — Stop / Delete / Force-close для зависших и старых записей.

## Содержание

- [Bootstrap everything](#bootstrap-everything)
- [Starter-kit](#starter-kit)
  - [Что лежит в шаблоне](#что-лежит-в-шаблоне)
  - [Установка через UI](#установка-через-ui)
  - [Установка через CLI](#установка-через-cli)
  - [Как расширять](#как-расширять-starter-kit)
- [Autoconfig каталогов](#autoconfig-каталогов)
  - [Какие каталоги покрыты](#какие-каталоги-покрыты)
  - [Поток клика](#поток-клика)
  - [Если хочешь другой путь](#если-хочешь-другой-путь)
- [Управление сессиями](#управление-сессиями)
  - [Stop / Force-close](#stop--force-close)
  - [Delete](#delete)
  - [Force-close all stale](#force-close-all-stale)

## Bootstrap everything

Master-кнопка живёт на **дашборде проекта** (`/p/{slug}/`) — это первая страница, на которую ты попадаешь, кликнув проект. Если что-то ещё не настроено, наверху появляется жёлтая плашка:

```
┌─ Проект ещё не настроен «из коробки» ─────────────────────────────────┐
│ Одна кнопка ниже сделает всё разом:                                    │
│  • скопирует 2 файла starter-kit (commands/self-study.md,              │
│    agents/lessons/_weekly-learning-checklist.md) в .claude/            │
│  • создаст 8 каталогов и пропишет в Settings:                          │
│    tech_debt_dir, product_ideas_dir, wiki_dir, evolutions_dir,         │
│    loops_dir, plans_dir, contracts_dir, sidecar_findings_dir           │
│                                                                         │
│ Существующие файлы и уже выставленные настройки не трогаются.          │
│ Если хочешь другие пути — поменяй потом в Settings.                    │
│                                                                         │
│ [ Bootstrap everything ]                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

Кнопка дёргает `POST /p/{slug}/bootstrap-all` и за один заход:

1. Запускает `starter_kit.install(working_dir, force=False)` — копирует все недостающие файлы из `templates/starter-kit/` в `{working_dir}/.claude/`. Существующие не перезаписывает.
2. Запускает `autoconfig.apply_all_defaults(skip_existing=True)` — для каждого ключа в `autoconfig.DEFAULTS` создаёт каталог и сохраняет setting, **только если override этого ключа ещё не задан**. Если ты уже руками прописал `tech_debt_dir = ...` — оно не будет затёрто.

После клика страница перерендерится: жёлтый баннер исчезнет (всё настроено), и ты увидишь обычный дашборд с метриками и Recent sessions.

Эта кнопка не заменяет per-page-кнопки — они остаются для случая «хочу настроить только эту фичу» или «удалил папку, нужно создать заново».

## Starter-kit

Без `/self-study` файла claude CLI не знает, что значит `/self-study aba-architect`, и выходит через 7 ms со статусом success и нулевой стоимостью. Симптом: на `/p/{slug}/live` поток заканчивается мгновенно, на dashboard'е сессии копятся в статусе success без `note_path`.

### Что лежит в шаблоне

`templates/starter-kit/` в репо DC — это source-of-truth набор файлов, который копируется в `{project.working_dir}/.claude/` целевого проекта. Структура шаблона **зеркалит** структуру `.claude/`:

```
templates/starter-kit/
├── commands/
│   └── self-study.md                          → .claude/commands/self-study.md
└── agents/
    └── lessons/
        └── _weekly-learning-checklist.md       → .claude/agents/lessons/_weekly-learning-checklist.md
```

Что внутри:

- **`commands/self-study.md`** — slash-команда, которую DC дёргает у claude CLI при каждом запуске self-study. Читает `.claude/agents/{name}.md`, sample'ит репо, пишет конспект в `.claude/agents/learning-notes/`, POST'ит `/api/session/finish`. См. [`self-study.md`](self-study.md).
- **`agents/lessons/_weekly-learning-checklist.md`** — заготовка недельного чек-листа тем. Парсится страницей «Темы»: см. [`topics-kanban.md`](topics-kanban.md).

Со временем сюда можно класть `/wiki-bootstrap.md`, `/tech-debt-scan.md` и любые другие slash-команды — UI сам начнёт их предлагать к установке во всех проектах.

### Установка через UI

**Страница Ротация** (`/p/{slug}/rotation`) — главный индикатор. Сверху, под строкой «N agents in DB; M on disk», один из двух баннеров:

- **Жёлтый «Starter-kit slash-commands are missing»** — перечисляет недостающие файлы и предлагает кнопку **Install starter kit**.
- **Свёрнутая зелёная строка «✓ starter kit installed (N files)»** — раскрываешь и видишь, что установлено + кнопка **Reinstall (overwrite)** на случай, если нужно подтянуть свежую версию из шаблона.

**Страница Темы** (`/p/{slug}/topics`) — если отсутствует именно weekly checklist, на ней появляется отдельная жёлтая плашка с кнопкой **Создать заготовку checklist**. Установка возвращает тебя обратно на Темы (а не на Ротацию), чтобы было удобно проверить результат.

Любая другая страница может в будущем тоже завести у себя такой баннер — механика для этого общая (см. [«Как расширять starter-kit»](#как-расширять-starter-kit)).

### Установка через CLI

Альтернатива UI — `scripts/install_starter_kit.py`. Полезно если у тебя нет доступа к UI (поднимаешь instance заново) или хочешь массово раскатить starter-kit на все проекты:

```bash
# в один проект по slug'у (читает working_dir из DB)
python scripts/install_starter_kit.py --slug ai-budget-assistant

# в произвольный путь (без чтения DB)
python scripts/install_starter_kit.py --working-dir "D:/Work/micode/foo"

# во все enabled-проекты разом
python scripts/install_starter_kit.py --all

# модификаторы
--dry-run     # печатает что бы скопировалось, не пишет
--force       # перезаписывает существующие файлы
--db-path     # явный путь к data/dreaming.db
```

По умолчанию **не перезаписывает** существующие файлы. Если ты руками подкрутил `self-study.md` под себя — повторная установка его не тронет, пока не передашь `--force`.

### Как расширять starter-kit

Когда тебе нужна новая slash-команда (например, `/wiki-bootstrap`, `/tech-debt-scan`):

1. Создаёшь файл `templates/starter-kit/commands/wiki-bootstrap.md` в репо DC.
2. На следующем заходе на Ротацию (или Темы — где он нужен) баннер автоматически скажет «не установлено». Жмёшь кнопку → файл копируется в проект.

Никакой код, никакие endpoint'ы трогать не надо. Сервис `starter_kit.py` сам рекурсивно проходит `templates/starter-kit/**` и сравнивает с `{working_dir}/.claude/`.

## Autoconfig каталогов

8 страниц проекта зависят от per-project настроек вида `tech_debt_dir`, `wiki_dir`, `loops_dir` и т.п. Раньше пустые они показывали «не настроен, иди в Settings». Теперь — жёлтую плашку с предложенным путём и кнопкой **Создать каталог и сохранить настройку**.

### Какие каталоги покрыты

| Страница | Setting key | Default путь (относительно `working_dir`) |
|---|---|---|
| `/p/{slug}/tech-debt` | `tech_debt_dir` | `docs/tech-debt` |
| `/p/{slug}/ideas` | `product_ideas_dir` | `docs/product-ideas` |
| `/p/{slug}/wiki` | `wiki_dir` | `docs/wiki` |
| `/p/{slug}/evolutions` | `evolutions_dir` | `.claude/agents/_context` |
| `/p/{slug}/loops` | `loops_dir` | `docs/loops` |
| `/p/{slug}/plans` | `plans_dir` | `docs/plans` |
| `/p/{slug}/contracts` | `contracts_dir` | `docs/contracts` |
| `/p/{slug}/sidecar-findings` | `sidecar_findings_dir` | `.claude/agents/sidecar-findings` |

Дефолты собраны в `dreaming/services/autoconfig.py:DEFAULTS`. Соглашение: «человеческие» артефакты идут в `docs/<feature>/`, агентские (output для self-study, sidecar reports) — в `.claude/agents/<feature>/`.

### Поток клика

1. На странице, например `/p/{slug}/tech-debt`, видишь жёлтый баннер: «Tech-debt ещё не настроен. Создам каталог: `D:\Work\micode\foo\docs\tech-debt`».
2. Жмёшь **Создать каталог и сохранить настройку**.
3. POST уходит на `/p/{slug}/settings/autoconfig`. Сервер:
   - делает `mkdir -p` на полный путь;
   - сохраняет `tech_debt_dir = ...` в таблицу `project_settings`;
   - редиректит обратно на ту же страницу через Referer-header (Same-origin-проверка: redirect только если путь начинается с `/p/{slug}`).
4. Страница перерендеривается — теперь либо пустой список («нет файлов»), либо реальный контент, если в этом каталоге что-то уже лежало (например, тебе кто-то commit'ом подкинул).

То же самое работает в состоянии «настройка есть, но каталог не существует» (например, ты сменил путь, а каталог не создал). Баннер тот же, кнопка тоже — повторно `mkdir -p` ничего не ломает.

### Если хочешь другой путь

Открываешь `/p/{slug}/settings`, находишь нужный ключ (`tech_debt_dir` и т.п.), нажимаешь **override**, вписываешь свой путь. Если каталога ещё нет — создашь сам через файловый менеджер / `mkdir`.

Autoconfig нужен для быстрого старта; финальная конфигурация всё равно живёт в Settings и редактируется там.

### Wiki — особый случай

Wiki после autoconfig находится в состоянии «папка есть, доменов нет». На странице `/p/{slug}/wiki` появляется голубая плашка **«Wiki ещё пустая»** + кнопка **Run /wiki-bootstrap**. Эта кнопка спавнит claude CLI с promptом `/wiki-bootstrap`. Когда тот завершит — обновляешь страницу, видишь N доменов. См. [`wiki.md`](wiki.md).

## Управление сессиями

На странице проекта-дашборд (`/p/{slug}/`) в таблице **Recent sessions** теперь есть колонка действий, а сверху — баннер при наличии «зависших running rows».

### Stop / Force-close

Для каждой строки в статусе `running`:

- Если процесс **жив** (есть в `pm.list_running()`) — кнопка **Stop**. SIGTERM на дочернем claude процессе. После выхода `_cleanup` пробует обновить DB-запись (см. [troubleshooting.md](../../troubleshooting.md#reconcile-warning)).
- Если процесс **умер**, но row остался `running` (orphan — статус помечен «orphan» в таблице) — кнопка **Force-close**. Дёргает `db.cancel_session(id)`, ставит `status='cancelled'`, `finished_at=now`.

Каждое действие просит подтверждение через `confirm()`.

### Delete

Доступна для **любого** статуса. Удаляет row из `agent_learning_sessions` целиком. Если процесс ещё жив — сначала kill'ит его, потом удаляет row. Это нужно, например, чтобы убрать failed-сессии-мусор из dashboard'а.

### Force-close all stale

Если у тебя одновременно много orphan'ов (накопились после краха сервера или Wave-0 reconcile-бага) — сверху над таблицей появляется баннер:

```
N stuck running rows (process gone, DB never closed).   [ Force-close all stale ]
```

Одной кнопкой ставит `status='cancelled'` всем running-row'ам этого проекта. **Не убивает живые процессы** — они в `pm.running` и не попадают в эту операцию.

## См. также

- [`self-study.md`](self-study.md) — что именно делает `/self-study` slash-команда.
- [`topics-kanban.md`](topics-kanban.md) — формат `_weekly-learning-checklist.md`.
- [`settings.md`](settings.md) — Settings UI, override механика.
- Технически: [`../../services.md#starter-kit`](../../services.md#starter-kit), [`../../services.md#autoconfig`](../../services.md#autoconfig), [`../../routes.md#starter-kit`](../../routes.md#starter-kit).
