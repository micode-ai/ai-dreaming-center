# Product Ideas

`/p/{slug}/ideas` — board продуктовых идей с фильтром по статусу и кнопкой `→ Jira` для создания тикета одним кликом.

## Содержание

- [Откуда берутся ideas](#откуда-берутся-ideas)
- [Что показывает страница](#что-показывает-страница)
- [Фильтр по статусу](#фильтр-по-статусу)
- [Кнопка → Jira](#кнопка--jira)
- [После создания тикета](#после-создания-тикета)
- [Если каталог не настроен](#если-каталог-не-настроен)

## Откуда берутся ideas

Ideas — markdown-файлы в директории `product_ideas_dir` (настраивается в settings). Создаются `weekly_product_ideas_scan_{slug}` cron-агентом (по дефолту off, opt-in).

Структура файла такая же как у tech-debt:
```
---
id: IDEA-2026-05-001
title: "Add live preview to settings form"
status: backlog
priority: medium
module: ui
created_at: 2026-05-01
jira_ticket: ""
---

# IDEA-2026-05-001 — Add live preview to settings form

## Pain
- Сейчас непонятно как изменения настроек выглядят на UI до Save.

## Proposal
- ...
```

Поля frontmatter: `id`, `title`, `status`, `priority`, `module`, `jira_ticket`. Status — обычно `backlog` / `proposed` / `accepted` / `in-progress` / `done` / `rejected`. Произвольная строка, UI не валидирует.

## Что показывает страница

Открой `/p/{slug}/ideas`. Логика отображения такая же как у findings:

- Если `product_ideas_dir` не настроен — амбер-плашка с ссылкой на settings.
- Если каталог не существует — серый «не существует».
- Если parser-error — красный.
- Если ок — таблица с заголовком «N ideas in `{ideas_dir}`».

Колонки таблицы:
- `id` — моноширинный.
- `title` — обычный текст.
- `status` — моноширинный bейдж.
- `priority` — моноширинный.
- `jira` — либо тикет (если уже создан), либо кнопка `→ Jira`.

## Фильтр по статусу

Если есть хотя бы одна idea — справа сверху появится `<select>` со списком уникальных статусов из текущего набора + опция «все статусы».

Логика:
- Выбираешь статус из dropdown'а.
- Form auto-submit'нется (`onchange="this.form.submit()"`).
- URL станет `/p/{slug}/ideas?status=backlog`.
- Таблица отфильтруется.

Чтобы вернуться ко всем — выбери «все статусы».

Удобно использовать для:
- «Покажи мне только backlog — что взять следующим?»
- «Сколько `accepted` уже в работе?»
- «Где rejected — заархивировать или удалить?»

## Кнопка → Jira

Для каждой idea без `jira_ticket` рядом — синяя кнопка `→ Jira` (форма с одной кнопкой). POST на `/p/{slug}/ideas/{id}/jira`.

Что происходит:
1. DC читает md-файл, берёт `title` и `body`.
2. Через `JiraService` дёргает Jira REST API: `POST /rest/api/3/issue` с payload содержащим `project.key`, `summary` (=title), `description` (=body), `issuetype.name='Task'`, `assignee.accountId`.
3. Если успех (HTTP 201) — берёт `key` из response (например `PROJ-1234`) и переписывает frontmatter md-файла: `jira_ticket: PROJ-1234`.
4. Редиректит обратно на `/ideas`.
5. Теперь в колонке `jira` для этой idea вместо кнопки — текст `PROJ-1234` (моноширинный).

Если креды Jira не настроены или неверны — DC отдаст 500/4xx с описанием. Открой `/p/{slug}/settings` и заполни `jira_email`, `jira_api_token`, `jira_user_account_id`, `jira_project_key`.

Подробнее — [`../workflows/jira-integration.md`](../workflows/jira-integration.md).

## После создания тикета

После клика на `→ Jira`:
- В md-файле frontmatter обновлён.
- В Jira создан Task.
- В UI — `jira_ticket` показывается как plain текст. Кликабельной ссылки на Jira нет (да, можно было бы добавить — тиhem в product_ideas_dir уже есть base_url Jira).

Если хочешь reopen / closed-link:
- Открой Jira-тикет руками: скопируй `PROJ-1234` и подставь в URL.
- Или открой md-файл и посмотри frontmatter.

Если хочется удалить idea (после того как оно ушло в Jira) — никаких UI-кнопок. Удали md-файл вручную или через git.

## Если каталог не настроен

По дефолту `product_ideas_dir` пустой. Чтобы настроить:
1. `/p/{slug}/settings` → группа «Paths» → `product_ideas_dir` → Override → впиши абсолютный путь.
2. Save.

Каталог создавать вручную (DC его не создаст). Дальше:
- Либо подожди следующего weekly scan'а — agent сам напишет файлы.
- Либо ручками положи туда несколько md-файлов с правильным frontmatter — UI их подхватит.

---

См. также:
- [`tech-debt.md`](tech-debt.md) — параллельная страница для tech-debt.
- [`../workflows/jira-integration.md`](../workflows/jira-integration.md) — настройка Jira creds.
- [`settings.md`](settings.md) — где прописывается `product_ideas_dir` и Jira-конфиг.
- [`../workflows/weekly-scanners.md`](../workflows/weekly-scanners.md) — как включить weekly product ideas scan.
- Технически: [`../../features/pipelines.md`](../../features/pipelines.md), [`../../services.md#jira`](../../services.md), [`../../api.md`](../../api.md).
