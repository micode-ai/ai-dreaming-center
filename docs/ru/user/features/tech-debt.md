# Tech-debt

Две страницы про технический долг:
- **Findings** (`/p/{slug}/findings`) — flat список всех tech-debt items с операциями close/delete.
- **Tech-Debt** (`/p/{slug}/tech-debt`) — агрегат: total, by_status, top modules.

## Содержание

- [Откуда берутся items](#откуда-берутся-items)
- [Findings: flat список](#findings-flat-список)
- [Detail: одна заметка](#detail-одна-заметка)
- [Close](#close)
- [Delete](#delete)
- [Tech-Debt: агрегат](#tech-debt-агрегат)
- [Если каталог не настроен](#если-каталог-не-настроен)

## Откуда берутся items

Tech-debt items — markdown-файлы в директории `tech_debt_dir` (настраивается в settings, дефолта нет — нужно прописать). Файлы создаёт `weekly_tech_debt_scan_{slug}` cron-агент (по дефолту off).

Структура одного файла:
```
---
id: TD-2026-05-001
title: "auth/login имеет 3 разных кодовых пути"
status: open
priority: high
module: auth
created_at: 2026-05-01
---

# TD-2026-05-001 — auth/login имеет 3 разных кодовых пути

Описание...

## Проявления
- ...

## Предложение
- ...
```

Frontmatter — обязателен. DC читает поля: `id`, `title`, `status`, `priority`, `module`. Body — произвольный markdown.

`status` — обычно `open` / `in-progress` / `closed`. UI поддерживает любые строки, фильтра нет.

## Findings: flat список

Открой `/p/{slug}/findings`.

Если `tech_debt_dir` не настроен — амбер-плашка «Каталог tech-debt не настроен» с ссылкой на settings. Если настроен но не существует — серый текст «Каталог `{td_dir}` не существует.» Если есть ошибка парсинга md — красная плашка с error message.

Если всё ок — увидишь:
- Сверху строку «N items in `{td_dir}`».
- Таблицу с колонками: `id`, `title`, `status`, `priority`, `module`, и в последней колонке кнопки `close` и `delete`.
- ID в первой колонке — кликабельный, ведёт на detail-страницу.

Status-бейдж моноширинный, цвет нейтральный (без цветовой шкалы).

Если items > 50–100 — таблица длинная, прокручиваешь руками. Pagination'а пока нет.

## Detail: одна заметка

Клик по ID в колонке `id` ведёт на `/p/{slug}/findings/{id}`.

Что увидишь:
- Хлебные крошки: ссылка `← к findings`.
- Заголовок (`title` из frontmatter).
- Метаданные (status, priority, module, дата).
- Body markdown — рендерится в HTML (для удобства чтения).
- Кнопки `close` и `delete` (повторяющие действия из списка).

Если файл удалён с диска между загрузкой списка и кликом — 404.

## Close

Кнопка `close` (только для items с `status != 'closed'`):
- POST на `/p/{slug}/findings/{id}/close`.
- DC переписывает frontmatter: меняет `status: open` → `status: closed`.
- Файл остаётся на диске.
- В таблице элемент остаётся, но кнопка `close` больше не показывается.

Smart move: close — это soft-delete. История остаётся в git'е, можно потом вернуться, можно reopen вручную (отредактировав файл).

Если в frontmatter нет поля `status` — DC добавит его.

## Delete

Кнопка `delete` (красная):
- JS-confirm: «Удалить {id}?». Жмёшь OK.
- POST на `/p/{slug}/findings/{id}/delete`.
- DC удаляет файл с диска (`os.unlink`).
- Редирект обратно на `/findings`.

Удаляется навсегда. Если репо под git'ом — восстанавливается через `git restore <path>`.

Используй когда:
- Item был ошибкой / дубликатом.
- Item больше неактуален и не нужно даже истории.

В большинстве случаев предпочитай close.

## Tech-Debt: агрегат

Открой `/p/{slug}/tech-debt`. Это статистика, не редактирование.

Если `tech_debt_dir` не настроен / не существует / parser-error — увидишь те же предупреждения что в findings.

Если ок — увидишь:
- Две карточки сверху: «Всего» (большим шрифтом — total) и «По статусу» (список status → count).
- Заголовок «Top modules».
- Таблицу из топ-10 модулей по количеству items: `module` / `count`.
- Внизу — «Источник: `{td_dir}` · полный список: findings».

Используй для:
- Быстрой проверки: сколько долга накопилось?
- Где плохо? Какой модуль топ-1 по items?
- Прогресс: сколько closed vs open?

## Если каталог не настроен

По дефолту `tech_debt_dir` пустой. Чтобы прописать:
1. Открой `/p/{slug}/settings`.
2. В группе «Paths» (или там, где tech_debt_dir) выбери `Override` и впиши абсолютный путь, например `D:\Work\micode\my-app\docs\tech-debt\`.
3. Save.

Каталог должен существовать. DC его не создаёт — создай вручную или дай scanner'у его создать.

После настройки и первого weekly scan'а — на `/findings` появятся items.

---

См. также:
- [`ideas.md`](ideas.md) — параллельная страница для product ideas.
- [`settings.md`](settings.md) — где прописывается `tech_debt_dir`.
- [`../workflows/weekly-scanners.md`](../workflows/weekly-scanners.md) — как включить weekly tech-debt scan.
- Технически: [`../../features/pipelines.md`](../../features/pipelines.md), [`../../routes.md`](../../routes.md).
