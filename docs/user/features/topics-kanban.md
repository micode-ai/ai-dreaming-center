# Topics и Kanban

Две страницы про темы изучения:
- **Topics** (`/p/{slug}/topics`) — read-only weekly checklist агентов из starter-kit'а.
- **Kanban** (`/p/{slug}/kanban`) — CRUD на custom topics, которые подмешиваются в prompt nightly self-study.

## Содержание

- [Topics: weekly checklist](#topics-weekly-checklist)
- [Kanban: custom topics](#kanban-custom-topics)
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

**Это read-only страница.** Чек-лист генерирует и редактирует сам агент-стартеркит (например, `team-lead.md`) во время своего self-study. UI не позволяет добавлять/удалять пункты — только читать.

Если у тебя нет starter-kit'а — на этой странице будет всегда «не найден». Это нормально, страница опциональна.

## Kanban: custom topics

`/p/{slug}/kanban` — отличается от Topics тем, что это твои собственные темы. Не файл, а строки в SQL-таблице `custom_topics`.

На странице:
- Сверху — белая карточка с формой добавления.
- Под ней — таблица существующих topics (если есть).

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

Когда nightly cron (или ручной `Start session`) запускает агента, DC:
1. Читает все `custom_topics` для этого `project_id` где `active=true`.
2. Фильтрует по `target_agents`: если `*` или пустое — все, если csv — содержит ли agent_name.
3. Подмешивает их в prompt через шаблонные переменные slash-команды `/self-study`. Конкретный механизм зависит от реализации команды в starter-kit'е, но обычно через env vars или дополнительные args.

Например, если есть topic «Refactor auth» с `target_agents=vera`, и этой ночью cron запускает Vera — её prompt будет включать секцию «Custom topics for tonight: …».

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
