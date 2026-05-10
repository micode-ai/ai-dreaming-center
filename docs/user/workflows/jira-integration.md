# Jira интеграция

Кнопка `→ Jira` на странице ideas создаёт Jira Task одним кликом. Чтобы это работало, нужно настроить креды.

## Содержание

- [Что такое и зачем](#что-такое-и-зачем)
- [Шаг 1. Получить API token](#шаг-1-получить-api-token)
- [Шаг 2. Получить accountId](#шаг-2-получить-accountid)
- [Шаг 3. Настройка в DC](#шаг-3-настройка-в-dc)
- [Шаг 4. Тест](#шаг-4-тест)
- [Best practice: env var](#best-practice-env-var)
- [Per-project override](#per-project-override)
- [Troubleshooting](#troubleshooting)

## Что такое и зачем

Если у тебя есть Jira (cloud-версия — atlassian.net) и ты используешь её для tracking'а задач — DC может автоматически создавать Task'и из идей продукта.

Workflow:
1. Weekly product_ideas_scanner (или ты сам) положил md-файл с идеей в `product_ideas_dir`.
2. На `/p/{slug}/ideas` ты видишь идею с пустой `jira` колонкой.
3. Нажимаешь `→ Jira`.
4. DC создаёт Task в Jira с title и body из md-файла, записывает в frontmatter `jira_ticket: PROJ-1234`, в UI колонка показывает ticket-id.

Никакого ручного copy-paste из markdown в Jira-форму.

## Шаг 1. Получить API token

API token — это long-lived credential, который Atlassian выдаёт для programmatic access без пароля.

1. Открой https://id.atlassian.com/manage-profile/security/api-tokens
2. Войди в свой Atlassian-аккаунт (тот же, под которым работаешь в Jira).
3. Нажми «Create API token».
4. Введи label, например `dc-dreaming-center`. Нажми Create.
5. Скопируй token. **Покажут только один раз** — сохрани в надёжном месте (password manager).

Token выглядит примерно как `ATATT3xFfGF0...` — длинная буквенно-цифровая строка.

## Шаг 2. Получить accountId

Чтобы Jira знала, кому ассайнить созданный тикет, нужен твой `accountId`.

Способ 1 — через API:
1. Открой в браузере: `https://yourcompany.atlassian.net/rest/api/3/myself` (замени `yourcompany` на свой sub-domain).
2. Если не залогинен — войди.
3. Увидишь JSON. Найди поле `accountId` (например `5b10ac8d82e05b22cc7d4ef5`).

Способ 2 — через Jira UI:
1. Открой свой профиль в Jira (клик на аватар → Profile).
2. URL содержит accountId: `/people/<accountId>`.

## Шаг 3. Настройка в DC

Открой `/settings` (для глобальной настройки) или `/p/{slug}/settings` (для per-project).

Группа «Jira» содержит ключи:
- `jira_base_url` — URL твоего Jira: `https://yourcompany.atlassian.net`. Без trailing-slash. **Обязательно.**
- `jira_email` — твой email в Atlassian. **Обязательно.**
- `jira_api_token` — токен из шага 1. **Обязательно.** Поле password (input хранится скрытно).
- `jira_user_account_id` — accountId из шага 2. **Обязательно.**
- `jira_project_key` — ключ проекта в Jira (например `PROJ`, `MYAPP`). **Обязательно.**
- `jira_issuetype` — тип ишьюшки. По дефолту `Task`. Можно `Story`, `Bug` если нужно.

Заполни все обязательные. Save.

## Шаг 4. Тест

1. Создай тестовую идею: положи md-файл в `product_ideas_dir`:
   ```
   ---
   id: TEST-001
   title: "Test Jira integration"
   status: backlog
   priority: low
   module: test
   jira_ticket: ""
   ---

   # Test idea

   This is a test to verify DC → Jira integration.

   ## Acceptance criteria
   - Click → Jira button on ideas page.
   - Verify ticket created in Jira.
   - Verify md frontmatter updated with jira_ticket.
   ```

2. Открой `/p/{slug}/ideas`. Найди эту запись.
3. В колонке `jira` — кнопка `→ Jira`. Нажми.
4. Через 1–3 секунды страница перезагрузится. Колонка теперь показывает ticket-id, например `PROJ-1234`.
5. Открой Jira — должен быть тикет с твоим title и description.
6. Открой md-файл — frontmatter обновлён: `jira_ticket: PROJ-1234`.

Если всё ок — интеграция работает.

## Best practice: env var

Хранить `jira_api_token` в `config.yaml` или `project_settings` в БД — небезопасно. Если репо/бэкап БД утекут — токен в открытом виде.

Лучший подход — env var. Pydantic-settings читает env vars с префиксом `DC_`:

```
$env:DC_JIRA_API_TOKEN = "ATATT3xFfGF0..."   # PowerShell session-level
```

Или в systemd unit / Windows service config:
```
Environment="DC_JIRA_API_TOKEN=ATATT3xFfGF0..."
```

Если env var задан — он перебивает значение из `config.yaml` (env > yaml priority в pydantic-settings).

В UI поле `jira_api_token` останется пустым (потому что не из config.yaml), но реально DC будет использовать env-значение. Чтобы это видеть — посмотри логи или dev-shell:
```python
from dreaming.config import AppSettings
print(AppSettings.load().jira_api_token)
```

## Per-project override

Если у тебя несколько Jira-проектов (каждый DC-проект → свой Jira-project), используй per-project override.

Глобально пропиши общие креды (`jira_base_url`, `jira_email`, `jira_api_token`, `jira_user_account_id`).

Per-project на `/p/{slug}/settings` override'ни только `jira_project_key`:
- Project A: `jira_project_key = APP1`.
- Project B: `jira_project_key = APP2`.

Когда жмёшь `→ Jira` на ideas Project A — тикет уходит в `APP1`. На Project B — в `APP2`.

## Troubleshooting

**`401 Unauthorized` после клика на → Jira:**
- Token устарел (Jira invalidate'ит после неактивности).
- Email не совпадает с тем, под которым выдан token.
- Получи новый token, обнови.

**`403 Forbidden`:**
- `jira_user_account_id` не имеет permission'ов create issue в `jira_project_key`.
- Проверь в Jira: открой проект → Settings → People → есть ли у тебя роль с Create Issues.

**`404 Not Found`:**
- `jira_project_key` неверный. Открой Jira, посмотри ключ проекта (обычно UPPERCASE-сокращение).

**`400 Bad Request`:**
- `jira_issuetype` не существует в проекте. Проверь в Jira: Settings → Issue types. Часто `Story` или `Task` есть, но redactions могут быть кастомные.

**Тикет создаётся, но frontmatter не обновляется:**
- Проблема с file system permissions — DC не может писать в md-файл.
- Проверь права на `product_ideas_dir`.

**Ticket-id не появляется в UI после клика:**
- POST вернул error — открой Network tab в DevTools, посмотри response.
- Или uvicorn логи — там будет stack trace.

---

См. также:
- [`../features/ideas.md`](../features/ideas.md) — страница ideas.
- [`../features/settings.md`](../features/settings.md) — где Jira-ключи.
- Технически: [`../../services.md#jira`](../../services.md), [`../../api.md`](../../api.md).
