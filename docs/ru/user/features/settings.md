# Настройки

DC имеет двухуровневую систему настроек:
- **Глобальные** на `/settings` — дефолты для всех проектов.
- **Per-project** на `/p/{slug}/settings` — override'ы поверх глобальных.

## Содержание

- [Inherit / Override](#inherit--override)
- [Глобальные настройки](#глобальные-настройки)
- [Per-project настройки](#per-project-настройки)
- [13 групп ключей](#13-групп-ключей)
- [Bool ключи](#bool-ключи)
- [Token / api_key ключи](#token--api_key-ключи)

## Inherit / Override

Каждое значение настройки может быть в одном из двух состояний для проекта:

- **Inherit** — используется global default (или built-in fallback если global тоже не задан).
- **Override** — у проекта есть собственное значение, которое подменяет global.

В UI на per-project странице ты видишь рядом с каждым ключом:
- `inherit` (radio-кнопка по умолчанию выбрана если не overridden).
- `override:` (radio-кнопка) + поле ввода. Текущее значение global показано рядом мелким шрифтом для справки.

При сохранении формы DC удаляет/добавляет строки в `project_settings (project_id, key, value)`. Inherit — удаляет, Override — пишет.

Resolution:
1. ConfigResolver.get(project, key) сначала смотрит в `project_settings`.
2. Если нет — берёт из AppSettings (config.yaml / env).
3. Если и там нет — built-in default из Pydantic Field.

## Глобальные настройки

Открой `/settings` (без `/p/`). Заголовок «Глобальные настройки. Per-project overrides — на /p/{slug}/settings.»

Форма разбита на fieldset'ы по группам. В каждом — список ключей (моноширинный), под ним input или checkbox.

После Save:
- Pydantic-settings перечитывается из обновлённого `config.yaml`.
- `request.app.state.settings` заменяется новым.
- Изменения применяются сразу — рестарт uvicorn не нужен.

Исключение: некоторые server-level ключи (`host`, `port`, `db_path`) требуют рестарта потому что uvicorn привязывается к ним при старте.

## Per-project настройки

Открой `/p/{slug}/settings`. Логика та же что у global, но:
- Сверху — текст «Per-project overrides. Inherit = используется global; Override = индивидуальное значение.»
- Каждый ключ имеет radio-pair: inherit / override.
- Под ключом мелким шрифтом — global-значение для справки.

Save → INSERT/DELETE строк в `project_settings`. Изменения применяются сразу.

Не все ключи доступны per-project. Server-level (`host`, `port`, `db_path`, `default_locale`) — только global. В UI они даже не показываются на per-project странице.

## 13 групп ключей

DC имеет 92 настройки в 13 группах. Краткое summary, что в каждой:

### 1. Database
`db_path` — путь к SQLite БД. Только global.

### 2. Projects
`projects_root`, `default_locale`. Корневой каталог сканирования и язык дефолтный.

### 3. Server
`host`, `port`. Bind-адрес uvicorn. Только global.

### 4. Claude CLI / runners
`claude_path`, `orchestration_local_runner`, `codex_path`, `continue_path`, `model_backend_profile`, `anthropic_base_url`, `anthropic_auth_token`, `anthropic_api_key`, `openai_proxy_*`. Где живёт Claude CLI и как с ним общаться.

### 5. Self-study
`self_study_command` (default `/self-study`), `self_study_max_turns` (default 50), `self_study_model` (override модели), `learning_notes_dir` (куда писать конспекты), `agents_dir` (по дефолту `.claude/agents/` под working_dir).

### 6. Scheduling — nightly
`cron_enabled` (bool), `cron_expression` (5-частный cron), `agents_per_night` (default 3), `wait_between_sec` (default 30), `nightly_max_concurrent` (опц.).

### 7. Scheduling — weekly (opt-in)
`weekly_tech_debt_scan_enabled` (default false), `weekly_tech_debt_scan_cron`, `weekly_tech_debt_scan_agent`. Аналогично для product_ideas_scan и wiki_lint.

### 8. Watchdogs
`timeout_minutes` (default 20), `reconcile_interval_min` (default 5), `kill_grace_seconds` (default 5).

### 9. Paths
`tech_debt_dir`, `product_ideas_dir`, `wiki_dir`, `evolutions_dir`, `loops_dir`, `plans_dir`, `cascade_artifacts_dir`, `sidecar_findings_dir`, `contracts_dir`, `context_overrides_dir`. Куда смотреть для read-only страниц.

### 10. Jira
`jira_base_url`, `jira_email`, `jira_api_token`, `jira_user_account_id`, `jira_project_key`, `jira_issuetype` (default `Task`).

### 11. Harness (orchestration)
`harness_enabled`, `harness_url`, `harness_api_key`. Если используешь external harness adapter для cascade.

### 12. AI Usage ingest
`claude_projects_dir` (default `~/.claude/projects/`), `ai_usage_ingest_enabled`, `ai_usage_ingest_interval_min` (default 5).

### 13. Routing
`default_project_slug` (для default-route'а), всякие routing flags.

Полный список с типами, defaults и use-case'ами — [`../../configuration.md`](../../configuration.md).

## Bool ключи

Bool-ключи (`cron_enabled`, `weekly_*_enabled`, `harness_enabled`, etc.) рендерятся как checkbox.

В global-форме — простой `<input type="checkbox">`. Hidden-input с `value="false"` стоит перед ним (стандартный браузерный workaround: если checkbox unchecked — браузер отправляет только hidden-value, иначе — checkbox-value).

В per-project — то же, но обёрнуто в radio inherit/override.

Если бу не знаешь точно тип ключа — просто открой `/settings`, найди ключ, увидишь форм-control:
- `<input type="text">` — строковый.
- `<input type="checkbox">` — bool.
- `<input type="password">` — secret (token / api_key).

## Token / api_key ключи

Ключи содержащие `token` или `api_key` в имени автоматически рендерятся как `<input type="password">` с `autocomplete="off"`.

Это для:
- Скрытия в скриншотах / shoulder-surfing.
- Защиты от browser autocomplete.

Не защищает от того, что значение уже попало в `config.yaml` plain-text. Если хочешь secret-management — храни в env var (`DC_JIRA_API_TOKEN=...`) и не вписывай в форму.

Important: при Override per-project token-ключа значение пишется в `project_settings.value` plain. Если БД украдут — секреты в ней. Бэкап БД исключай или зашифруй.

---

См. также:
- [`../workflows/jira-integration.md`](../workflows/jira-integration.md) — конкретный пример Jira creds.
- [`../workflows/nightly-cron.md`](../workflows/nightly-cron.md) — nightly-настройки.
- [`../workflows/weekly-scanners.md`](../workflows/weekly-scanners.md) — weekly settings.
- Технически: [`../../configuration.md`](../../configuration.md), [`../../features/settings.md`](../../features/settings.md).
