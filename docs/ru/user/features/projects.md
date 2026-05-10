# Управление проектами

Регистр проектов — таблица всех зарегистрированных в DC директорий. Каждая запись = один проект с уникальным slug, label, рабочим путём и флагами.

## Содержание

- [Что такое registry](#что-такое-registry)
- [Страница `/projects`](#страница-projects)
- [Импорт из projects_root](#импорт-из-projects_root)
- [Toggle Disable / Enable](#toggle-disable--enable)
- [Delete (с подтверждением)](#delete-с-подтверждением)
- [Default project](#default-project)
- [Изменение slug / label](#изменение-slug--label)

## Что такое registry

DC хранит список проектов в SQLite-таблице `projects`. Каждая запись:
- `slug` — короткое уникальное имя (`my-app`, `wishlist`).
- `label` — человекочитаемое имя (видно в шапке).
- `working_dir` — абсолютный путь к папке проекта на диске.
- `enabled` — boolean: показывать ли в dropdown'e и регистрировать ли cron-jobs.
- `is_default` — boolean: один проект может быть default'ом.

DC сам сканирует подпапки `projects_root` и ничего не делает автоматически: ты явно выбираешь, какие папки регистрировать, через setup wizard или через `/projects`.

## Страница `/projects`

Открой `http://localhost:8086/projects`. Ты увидишь:

- Заголовок «Проекты».
- Если registry непустой — таблицу с колонками: `slug`, `label`, `working_dir` (мелким шрифтом), `enabled` (`✓` или `—`), `default` (`★` или пусто), и две кнопки `Disable`/`Enable` и `Delete` справа.
- Если registry пустой — текст «Нет зарегистрированных проектов» и ссылка `→ /setup`.
- Внизу — блок «Импорт из projects_root» с input'ом и кнопкой `Просканировать и импортировать новые`.

## Импорт из projects_root

Когда полезно: добавить новые проекты в работающий instance, не пересоздавая регистр.

Шаги:
1. На `/projects` пролистай вниз до блока «Импорт из projects_root».
2. В input'е увидишь текущий `projects_root` из настроек. Можешь оставить или поменять (на одноразовое сканирование).
3. Нажми синюю кнопку `Просканировать и импортировать новые`.
4. DC просканит указанный путь, отфильтрует уже зарегистрированные (по `working_dir`), и импортирует все новые с `enabled=true`, `is_default=false`. Slug подставится автоматически из имени папки (lowercase, замена `_` на `-`).
5. Тебя перенаправит обратно на `/projects` с обновлённой таблицей.

Если новых проектов в `projects_root` нет — таблица не изменится.

## Toggle Disable / Enable

Кнопка `Disable` (или `Enable`, если уже disabled) — POST на `/projects/{id}/toggle`.

Что происходит при Disable:
- В БД `enabled=false`.
- Scheduler автоматически unregister'ит все cron-jobs этого проекта (`nightly_learning_{slug}`, `weekly_*_{slug}`).
- Проект исчезает из dropdown'а в шапке (но остаётся в `/projects` таблице).
- Все его метрики на агрегированном `/` дашборде перестают учитываться.
- Sessions и runs в БД — никуда не пропадают.

При Enable — обратное: cron-jobs пересоздаются, проект снова в dropdown'e.

Используй disable когда:
- Временно не хочешь крутить cron'ы для проекта.
- Не хочешь сейчас видеть в UI.
- Нужно «заархивировать» без потери истории.

## Delete (с подтверждением)

Кнопка `Delete` (красная) — POST на `/projects/{id}/delete` с защитой: JS-prompt спросит «Введите slug `{slug}` чтобы удалить:». Должен ввести точно как в колонке slug, иначе POST не отправится.

Что происходит при Delete:
- Все строки `agent_learning_sessions`, `agent_learning_rotation`, `custom_topics`, `orchestrator_runs`, `orchestrator_nodes`, `orchestrator_messages`, `ai_usage_events`, `project_settings` для этого `project_id` удаляются каскадно через ON DELETE CASCADE FK.
- Markdown-артефакты на диске (`.claude/agents/`, `tech_debt_dir`, `product_ideas_dir`, конспекты, wiki) **не удаляются** — DC не управляет filesystem-объектами проекта.
- Cron-jobs unregister'ятся.
- Запись из `projects` пропадает.

Используй удалю когда:
- Проект полностью больше не нужен.
- Slug нужно сменить (удалить и заимпортировать заново).

**Внимание:** delete необратимо для DB-данных. Если есть сомнение — сначала `Disable`.

## Default project

Default — это один проект с флагом `is_default=true`. Выбирается на setup-wizard'е (radio-кнопка в колонке «по умолч.»). Через UI после setup'а сменить default нельзя — нужно править БД напрямую.

Что значит default:
- На `/` (корне) если есть default — DC показывает aggregated dashboard всё равно (default используется только в нескольких роутах для подсказок).
- Можно жить без default'а — UI работает.

## Изменение slug / label

Через UI **нельзя**. UI не показывает edit-форму для записи projects. Если нужно сменить slug:

1. Останови DC (uvicorn Ctrl+C).
2. Открой `data/dreaming.db` в SQLite-клиенте (DB Browser, sqlite3 CLI).
3. Выполни:
   ```
   UPDATE projects SET slug='new-slug' WHERE slug='old-slug';
   ```
4. Запусти DC снова.

Внимание: если у тебя есть customised cron expressions, артефакты в путях с slug'ом — не забудь их обновить тоже. Проще удалить и пересоздать.

Если хочешь сменить только label:
```
UPDATE projects SET label='New Label' WHERE slug='my-app';
```

---

См. также:
- [`../workflows/new-project.md`](../workflows/new-project.md) — пошаговое добавление нового проекта.
- [`../workflows/onboarding.md`](../workflows/onboarding.md) — первый запуск с setup wizard'ом.
- Технические детали — [`../../features/multi-project.md`](../../features/multi-project.md) и [`../../schema.md`](../../schema.md).
