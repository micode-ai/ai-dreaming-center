# Документация для пользователя AI Dreaming Center

Здесь собраны end-user-ориентированные руководства: «как пользоваться» инструментом. Если ты разработчик и хочешь понять, как DC устроен внутри (код, схема БД, API) — иди в `../README.md` (технический индекс).

## Быстрый старт

- [`getting-started.md`](getting-started.md) — установка и первая сессия за 15–20 минут.
- [`overview.md`](overview.md) — что такое AI Dreaming Center, кому и зачем нужен.
- [`features/out-of-the-box.md`](features/out-of-the-box.md) — установка «из коробки»: starter-kit, autoconfig каталогов, управление сессиями.
- [`workflows/onboarding.md`](workflows/onboarding.md) — расширенный «первый день» от нуля до настроенного nightly cron.

## Гайды по фичам

Каждый пункт меню в шапке проекта = отдельный файл здесь:

- [`features/projects.md`](features/projects.md) — registry проектов: добавить, отключить, удалить.
- [`features/self-study.md`](features/self-study.md) — что такое self-study и как его запускать вручную / через cron.
- [`features/rotation.md`](features/rotation.md) — таблица агентов: tier, enabled, кнопка `Start session`.
- [`features/live-log.md`](features/live-log.md) — наблюдение live-стрима stdout, кнопка `Kill`.
- [`features/topics-kanban.md`](features/topics-kanban.md) — недельный чек-лист (read-only) и kanban с custom topics.
- [`features/notes.md`](features/notes.md) — браузер конспектов агентов.
- [`features/tech-debt.md`](features/tech-debt.md) — findings list, detail, close/delete + tech-debt aggregate.
- [`features/ideas.md`](features/ideas.md) — board продуктовых идей и кнопка `→ Jira`.
- [`features/wiki.md`](features/wiki.md) — статус wiki проекта и `Run /wiki-bootstrap`.
- [`features/ai-usage.md`](features/ai-usage.md) — аналитика токенов и стоимости (per-project + global).
- [`features/orchestration.md`](features/orchestration.md) — запуск Романа, наблюдение live, resume, **Bulk queue** для массового запуска findings/ideas/evolutions.
- [`features/evolutions.md`](features/evolutions.md) — предложения правок для агентов: Apply / force-apply / conflict-gate / фильтры.
- [`features/cascade.md`](features/cascade.md) — каскадный конвейер: contract → design → … → qa.
- [`features/analytics-extras.md`](features/analytics-extras.md) — Evolutions, Loops, Plans, Cascade Costs, Sidecar findings, Contracts.
- [`features/settings.md`](features/settings.md) — глобальные vs per-project настройки.
- [`features/language.md`](features/language.md) — переключение между русским и английским.

## Типичные сценарии

- [`workflows/daily.md`](workflows/daily.md) — один день жизни инструмента.
- [`workflows/onboarding.md`](workflows/onboarding.md) — расширенный первый запуск.
- [`workflows/new-project.md`](workflows/new-project.md) — добавить новый проект в работающий instance.
- [`workflows/jira-integration.md`](workflows/jira-integration.md) — настроить Jira creds и создать тикет из идеи.
- [`workflows/nightly-cron.md`](workflows/nightly-cron.md) — настройка ночного расписания.
- [`workflows/weekly-scanners.md`](workflows/weekly-scanners.md) — включение weekly scan'еров.

## Reference

- [`faq.md`](faq.md) — частые вопросы.
- [`glossary.md`](glossary.md) — словарь терминов.

## Если что-то непонятно

Сначала открой [`faq.md`](faq.md). Если ответа нет — глянь технический [`../troubleshooting.md`](../troubleshooting.md) (там диагностические команды). Если и там нет — заведи issue в репозитории.
