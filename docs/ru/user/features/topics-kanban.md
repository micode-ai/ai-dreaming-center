# Topics и Kanban

Две страницы про темы изучения:
- **Topics** (`/p/{slug}/topics`) — read-only weekly checklist агентов из starter-kit'а.
- **Kanban** (`/p/{slug}/kanban`) — CRUD на custom topics, которые подмешиваются в prompt nightly self-study.

## Содержание

- [Topics: weekly checklist](#topics-weekly-checklist)
- [Kanban: custom topics](#kanban-custom-topics)
- [Кнопка «Сгенерировать темы»](#кнопка-сгенерировать-темы)
- [Еженедельный авто-скан](#еженедельный-авто-скан)
- [Поля формы](#поля-формы)
- [Как темы попадают в self-study](#как-темы-попадают-в-self-study)
- [Удаление topic](#удаление-topic)

## Topics: weekly checklist

Открой `/p/{slug}/topics`. DC ищет markdown-файл с чек-листом в одном из двух стандартных мест:

1. `{working_dir}/.claude/agents/lessons/_weekly-learning-checklist.md`
2. `{working_dir}/.claude/agents/_weekly-learning-checklist.md`

Если файл найден — DC парсит его в список и показывает на странице:
- Сверху — путь к файлу.
- Дальше — белый блок с моноширинным текстом, по строке на пункт чек-листа.

Если файл не найден — увидишь предупреждение «Weekly checklist не найден. Ожидаемые пути: ...» и список двух кандидатов.

**Это read-only представление файла `_weekly-learning-checklist.md`.** Сам файл — для человеческих заметок (если вообще используешь). Чтобы темы попадали в агента, добавляй их на странице **Kanban** — там же кнопка «Сгенерировать темы». Topics-страница только показывает то, что лежит в файле; она ничего не пишет и парсер не вызывает агентов.

Если у тебя нет starter-kit'а — на этой странице будет всегда «не найден». Это нормально, страница опциональна.

## Kanban: custom topics

`/p/{slug}/kanban` — отличается от Topics тем, что это твои собственные темы. Не файл, а строки в SQL-таблице `custom_topics`.

На странице:
- Сверху — белая карточка с формой добавления.
- Под ней — таблица существующих topics (если есть).

## Кнопка «Сгенерировать темы»

Справа от заголовка «Custom topics» — кнопка **«Сгенерировать темы»**.
POST на `/p/{slug}/topics/generate` запускает в проекте Claude CLI с
командой `/topics-scan` (одноразовая, не self-study). Команда:

1. читает `git log -50`, `.claude/agents/learning-notes/`,
   `.claude/agents/sidecar-findings/`, `CLAUDE.md`, `README.md`;
2. предлагает 5–10 тем на неделю;
3. POST'ит каждую в `/api/p/{slug}/topics/ingest` → строки появляются
   в этой же таблице после перезагрузки страницы.

Пока команда работает, кнопка заблокирована (`Генерируется…`).
Лог сессии — на `/p/{slug}/live`.

Шаблон команды лежит в `templates/starter-kit/commands/topics-scan.md`
— устанавливается в проект через starter-kit install.

## Еженедельный авто-скан

Cron-job `weekly_topics_scan` запускает тот же `/topics-scan` по расписанию
(дефолт: понедельник 03:00 локально). По умолчанию выключен — включается
per-project на странице Settings:

- `weekly_topics_scan_enabled` — true/false, дефолт false.
- `weekly_topics_scan_cron` — выражение crontab (5 полей), дефолт `0 3 * * 1`.

Под капотом — отдельный `command_name="weekly-topics-scan"`, не пересекается
с ручной кнопкой (`command_name="topics-scan"`), так что кнопка и cron могут
работать параллельно если их триггерят в одну минуту.

## Поля формы

Форма добавления нового topic'а имеет 5 полей:

1. **Заголовок темы** (`title`, обязательное) — короткое название, что нужно изучить. Пример: «Refactor session management — переход на FastAPI dependency injection».
2. **Модуль** (`module`, опциональное) — название модуля/раздела проекта. Пример: `auth`, `billing`.
3. **Агенты** (`target_agents`, опциональное) — кому подмешать. Можно указать через запятую (`vera,svetlana`) или оставить пустым (= всем).
4. **Что именно изучить** (`question`, опциональное textarea) — детальный вопрос, на который агент должен ответить. Пример: «Какие side-effects у текущей `auth.login()`? Какие 3 main pain-points?».
5. **Почему важно** (`why_important`, опциональное textarea) — обоснование, контекст. Пример: «Через 2 недели начинаем переписывание; до этого нужна inventory pain-points'ов».

Кнопка `Добавить` снизу — POST на `/p/{slug}/kanban/add`. Создаётся запись с `active=true`.

Если ты вводишь пустой `title` — браузер не пропустит (HTML required).

## Как темы попадают в self-study

Когда nightly cron (или кнопка `Start` на странице **Rotation**) запускает
агента, DC:
1. Читает `custom_topics` для этого `project_id` где `active=1`.
2. Фильтрует по `target_agents`: пусто или `*` — для всех; CSV — только если
   имя агента в списке.
3. Форматирует как markdown-блок «## Темы на сегодня (из DC)» и подмешивает
   к prompt'у `/self-study <agent>` через `extra_prompt`.

Помощник `dreaming/services/topics_prompt.py:build_topics_extra_prompt`
возвращает `""` если тем нет — для проектов без custom_topics поведение не
меняется (нулевая регрессия).

После завершения сессии `active` остаётся true (не auto-mark'ится done). Это сделано намеренно: тему можно «оставить в work» на несколько ночей, пока не сочтёшь нужным удалить.

## Удаление topic

В таблице справа в каждой строке есть подчёркнутая красная ссылка `delete`. POST на `/p/{slug}/kanban/{id}/delete`.

Запись удаляется навсегда. Подтверждения нет — будь аккуратен.

Если хочешь не удалять, а только «выключить» (чтобы не подмешивалось в self-study) — нужен ручной UPDATE в БД (`UPDATE custom_topics SET active=false WHERE id=...`). UI не имеет toggle.

## Если topics нет

Если в Kanban пусто — увидишь текст «Нет custom topics. Добавь выше — они подмешаются в prompt nightly_learning.»

Это нормальный режим: можно вообще не использовать Kanban и довольствоваться weekly checklist'ом из Topics.

---

См. также:
- [`self-study.md`](self-study.md) — что такое nightly_learning.
- [`rotation.md`](rotation.md) — управление списком агентов.
- [`../workflows/daily.md`](../workflows/daily.md) — типичная роль Kanban в день.
- Технически: [`../../schema.md#custom_topics`](../../schema.md), [`../../features/pipelines.md`](../../features/pipelines.md).
