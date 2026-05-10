# Configuration Reference

Все настройки приложения. Источник истины — класс `AppSettings` в [`dreaming/config.py`](../dreaming/config.py) (92 поля, 13 групп).

## Содержание

- [Где живёт config](#где-живёт-config)
- [Env vars](#env-vars)
- [Per-project overrides](#per-project-overrides)
- [Cache invalidation](#cache-invalidation)
- [Group: Database](#group-database)
- [Group: Projects](#group-projects)
- [Group: Server](#group-server)
- [Group: Claude CLI / runners](#group-claude-cli--runners)
- [Group: Self-study](#group-self-study)
- [Group: Scheduling — nightly](#group-scheduling--nightly)
- [Group: Scheduling — weekly (opt-in)](#group-scheduling--weekly-opt-in)
- [Group: Watchdogs](#group-watchdogs)
- [Group: Paths](#group-paths-obsidian--artifacts)
- [Group: Jira](#group-jira)
- [Group: Harness (orchestration)](#group-harness-orchestration)
- [Group: AI Usage ingest](#group-ai-usage-ingest)
- [Group: Routing](#group-routing)

## Где живёт config

`config.yaml` в корне проекта (рядом с `pyproject.toml`). Создаётся setup wizard'ом или вручную из [`config.example.yaml`](../config.example.yaml).

Внимание: путь относительный (`Path("config.yaml")` в config.py:8). Если стартуешь из другого CWD — wizard и save_yaml промахнутся. Запускай uvicorn из корня репозитория, либо переопредели через env var `DC_DB_PATH=/abs/path/dreaming.db` и т.д.

Перезагрузка settings:
- При старте — `AppSettings.load()` в lifespan.
- Wizard и `/settings POST` явно делают `request.app.state.settings = type(settings).load()`.

## Env vars

Префикс `DC_`. Например `DC_PORT=9000`, `DC_DEFAULT_LOCALE=en`.

Pydantic-settings читает env vars **поверх** YAML (config.py:19 `env_prefix="DC_"`, `extra="ignore"`).

## Per-project overrides

Большая часть ключей может быть override'нута per-project через таблицу `project_settings (project_id, key, value)`. Доступ — через `ConfigResolver.get(project, key, default)` ([`config_resolver.py:23`](../dreaming/services/config_resolver.py)).

Override scope:
- **Global only** — обычно serve-level (db_path, host, port, default_locale).
- **Global + per-project** — всё остальное.

В таблицах ниже колонка «Per-proj» отмечает GLB-only явно.

## Cache invalidation

`ConfigResolver` per-request, поэтому изменение `project_settings` не виден на текущий request, но виден на следующий. `HarnessClientCache.invalidate(project_id)` нужно вызывать руками если меняешь harness_* per-project на лету (но в текущем коде не зовётся — просто перезагрузи приложение).

## Group: Database

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `db_path` | str | `"data/dreaming.db"` | GLB | SQLite файл (относительный или абсолютный путь). Кагда стартуем с другого CWD — задавай абсолютный. **Example use**: `db_path: "/var/lib/dc/dreaming.db"`. |

Used by: [`SqliteDB.__init__`](../dreaming/services/db.py) — `Path(self._path).parent.mkdir(parents=True, exist_ok=True)` если каталога нет.

## Group: Projects

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `projects_root` | str | `""` | GLB | Корневой каталог где живут все проекты (для wizard scan). Default в setup.py — `D:\Work\micode`. **Example use**: `projects_root: "D:\\Work\\micode"`. |
| `default_locale` | str | `"ru"` | GLB | Язык интерфейса по умолчанию (если кука `dc_locale` не выставлена). Допустимые: `ru`/`en`. **Example use**: `default_locale: "en"`. |

## Group: Server

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `host` | str | `"0.0.0.0"` | GLB | Bind host для uvicorn — но uvicorn конфигурится через CLI, эти ключи доступны для собственных читателей. |
| `port` | int | `8086` | GLB | Порт (default 8086). Используется для построения `DREAMING_API_URL=http://localhost:{port}` в env-overrides Claude. **Example use**: `port: 9000`. |

## Group: Claude CLI / runners

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `claude_path` | str | `"claude"` | per-proj | Путь к Claude CLI. На Windows `shutil.which("claude")` найдёт `claude.cmd`. **Example use**: `claude_path: "C:\\Users\\me\\AppData\\Roaming\\npm\\claude.cmd"`. |
| `orchestration_local_runner` | str | `"claude"` | per-proj | `claude` \| `codex` \| `continue`. Wave 3+ (используется по plan, в текущем коде codex/continue не реализованы). |
| `codex_path` | str | `"codex"` | per-proj | Путь к codex CLI. |
| `codex_api_key` | str (secret) | `""` | per-proj | Secret. Не пишите в открытый репо. |
| `continue_path` | str | `".continue\\continue.cmd"` | per-proj | Путь к continue CLI. |
| `model_backend_profile` | str | `"native"` | per-proj | `native` \| `openrouter` \| `openai_proxy`. |
| `anthropic_base_url` | str | `""` | per-proj | Custom base URL для Anthropic API. |
| `anthropic_auth_token` | str (secret) | `""` | per-proj | Bearer token. |
| `anthropic_api_key` | str (secret) | `""` | per-proj | API key для Anthropic. |
| `openai_proxy_base_url` | str | `""` | per-proj | OpenAI-совместимый прокси. |
| `openai_proxy_api_key` | str (secret) | `""` | per-proj | API key для прокси. |
| `codex_command_template` | str | `'codex -p "{prompt}" --model {model}'` | per-proj | Шаблон команды codex. |
| `continue_command_template` | str | `'continue -p "{prompt}"'` | per-proj | Шаблон команды continue. |

Used by: [`ProcessManager._resolve_claude_path`](../dreaming/services/process_manager.py:31) и cron jobs в `scheduler.py`. **secret** — поля рендерятся как `type=password` в settings UI.

## Group: Self-study

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `model` | str | `"sonnet"` | per-proj | Модель Claude для self-study (`sonnet` / `haiku` / `opus`). **Example**: `model: "haiku"` для дешёвого ночного скана. |
| `max_turns` | int | `25` | per-proj | `--max-turns N` Claude CLI. |
| `timeout_minutes` | int | `20` | per-proj | Silence-timeout watchdog. |
| `self_study_command` | str | `"/self-study"` | per-proj | Slash-команда. Полный prompt: `{self_study_command} {agent_name}`. |
| `question_reminder_minutes` | int | `15` | per-proj | После N минут без ответа на pending question — TTS reminder (полная реализация отложена). |
| `question_expire_minutes` | int | `60` | per-proj | После M минут — questions expire'ся (стирается pending). |

## Group: Scheduling — nightly

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `cron_expression` | str | `"0 2 * * *"` | per-proj | Cron-выражение для nightly_learning. **Example**: `"0 3 * * *"` — каждый день в 3 ночи. |
| `cron_enabled` | bool | `true` | per-proj | Включить/выключить nightly. **Example**: `cron_enabled: false`. |
| `agents_per_night` | int | `5` | per-proj | Сколько top агентов брать. |
| `max_concurrent` | int | `2` | GLB (читается из settings в `ProcessManager.__init__`) | Лимит параллельных Claude-сессий в ProcessManager. |
| `wait_between_sec` | int | `5` | per-proj | Пауза между spawn'ами в nightly_learning. |

`max_concurrent` фактически берётся `getattr(settings, "max_concurrent", 2)` в `ProcessManager.__init__` — поэтому per-project override не повлияет (нужно глобальный задавать).

## Group: Scheduling — weekly (opt-in)

Все weekly_*_enabled — **default false**. Включай только когда нужно (per-project через `/p/{slug}/settings`).

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `weekly_tech_debt_scan_cron` | str | `"0 3 * * 6"` | per-proj | Каждую субботу в 3:00. |
| `weekly_tech_debt_scan_enabled` | bool | `false` | per-proj | Включить tech-debt scan через `/tech-debt-scan` slash-команду. |
| `weekly_timur_duty_cron` | str | `"0 2 * * 0"` | per-proj | Воскресенье 2:00. |
| `weekly_timur_duty_enabled` | bool | `false` | per-proj | (резерв на будущее, в `_PER_PROJECT_JOBS` пока нет). |
| `weekly_product_ideas_scan_cron` | str | `"0 20 * * 0"` | per-proj | Воскресенье 20:00. |
| `weekly_product_ideas_scan_enabled` | bool | `false` | per-proj | Включить product-ideas scan. |
| `weekly_wiki_lint_cron` | str | `"0 1 * * 6"` | per-proj | Суббота 1:00. |
| `weekly_wiki_lint_enabled` | bool | `false` | per-proj | Включить wiki-lint. |
| `weekly_evolve_apply_cron` | str | `"0 4 * * 0"` | per-proj | Воскресенье 4:00. |
| `weekly_evolve_apply_enabled` | bool | `false` | per-proj | (резерв). |
| `daily_bootstrap_cron` | str | `"0 4 * * *"` | per-proj | Daily 4:00. |
| `daily_bootstrap_enabled` | bool | `false` | per-proj | (резерв). |
| `daily_plans_cleanup_cron` | str | `"30 23 * * *"` | per-proj | Daily 23:30. |
| `daily_plans_cleanup_enabled` | bool | `false` | per-proj | (резерв). |
| `monthly_deep_audit_cron` | str | `"0 5 1 * *"` | per-proj | 1-го числа в 5:00. |
| `monthly_deep_audit_enabled` | bool | `false` | per-proj | (резерв). |

«Резерв» = ключ объявлен в `AppSettings`, но в `_PER_PROJECT_JOBS` ([`scheduler.py:173`](../dreaming/services/scheduler.py)) не зарегистрирован → фактически no-op. См. в [`development.md`](development.md), как добавить новую job.

## Group: Watchdogs

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `loop_watchdog_enabled` | bool | `true` | per-proj | Watchdog за reflex-loop стагнацией. |
| `loop_watchdog_interval_minutes` | int | `60` | per-proj | Интервал. |
| `sidecar_findings_enabled` | bool | `false` | per-proj | Включить sidecar-findings UI. |
| `evolutions_stale_days` | int | `7` | per-proj | Через сколько дней без updates evolution считать stale. |
| `loop_stagnation_hours` | int | `6` | per-proj | Через сколько часов без iterations loop считать stagnant. |
| `plans_archive_days` | int | `14` | per-proj | После скольки дней без updates plan архивировать. |

Эти ключи задают thresholds, но фактическое использование частично deferred.

## Group: Paths (Obsidian / artifacts)

Эти пути могут быть pустыми — тогда фичи не работают (UI покажет «not set»).

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `obsidian_vault` | str | `""` | per-proj | Корень Obsidian vault. Используется как fallback-base для других paths. **Example**: `Z:\\my-vault`. |
| `agents_dir` | str | `""` | per-proj | Override для `.claude/agents`. По умолчанию `{working_dir}/.claude/agents`. |
| `tech_debt_dir` | str | `""` | per-proj | Где живут TD-*.md. **Example**: `D:\\Work\\micode\\rgs\\.claude\\tech-debt`. |
| `product_ideas_dir` | str | `""` | per-proj | Где живут PI-*.md. |
| `contracts_dir` | str | `""` | per-proj | Module/page contracts. По умолчанию `{obsidian_vault}/03-Team/specs/contracts`. |
| `learning_notes_dir` | str | `""` | per-proj | Notes browser default = `{working_dir}/.claude/agents/learning-notes`. |
| `evolutions_dir` | str | `""` | per-proj | Default = `{working_dir}/.claude/agents/_context`. |
| `context_overrides_dir` | str | `""` | per-proj | Альтернатива evolutions_dir. |
| `lessons_cursor_path` | str | `""` | per-proj | (резерв). |
| `loops_dir` | str | `""` | per-proj | Default = `{obsidian_vault}/03-Team/loops`. |
| `plans_dir` | str | `""` | per-proj | Default = `{obsidian_vault}/03-Team/plans`. |
| `sidecar_findings_dir` | str | `""` | per-proj | Default = `{obsidian_vault}/03-Team/sidecar-findings`. |
| `loops_templates_dir` | str | `""` | per-proj | (резерв). |
| `wiki_dir` | str | `""` | per-proj | Wiki root, для status и bootstrap. |

Default fallback'ы зашиты в роутах (например, project_evolutions.py:14, project_loops.py:15).

## Group: Jira

Все Jira-поля — secret, рендерятся в UI как password.

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `jira_url` | str | `""` | per-proj | Полный URL базы. **Example**: `https://acme.atlassian.net`. |
| `jira_email` | str (secret) | `""` | per-proj | Email пользователя для Basic Auth. |
| `jira_api_token` | str (secret) | `""` | per-proj | API token (создаётся в Atlassian profile). |
| `jira_project_key` | str | `""` | per-proj | Project key (RGS, ENG и т.д.). Per-проектный override применяется в [`project_ideas.py:74`](../dreaming/routes/project_ideas.py). |
| `jira_user_account_id` | str | `""` | per-proj | Account ID для reporter+assignee. **Example**: `5b10a2844c20165700ede21g`. |

Used by: [`jira.create_task`](../dreaming/services/jira.py) — POST на `/rest/api/3/issue`.

## Group: Harness (orchestration)

Адаптер к внешнему harness'у (если используется вместо local claude).

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `harness_base_url` | str | `""` | per-proj | Если пустой — `HarnessClient.enabled = False`, методы возвращают stub. **Example**: `https://harness.acme.com`. |
| `harness_api_key` | str (secret) | `""` | per-proj | Bearer token. |
| `harness_timeout_sec` | int | `30` | per-proj | HTTP timeout. |
| `harness_stream_enabled` | bool | `true` | per-proj | Использовать SSE (true) или polling fallback. |
| `harness_start_path` | str | `"/api/orchestration/start"` | per-proj | Path для POST start. |
| `harness_events_stream_path` | str | `"/api/orchestration/{run_id}/stream"` | per-proj | SSE-endpoint. |
| `harness_events_path` | str | `"/api/orchestration/{run_id}/events"` | per-proj | Polling-endpoint. |
| `harness_send_input_path` | str | `"/api/orchestration/{run_id}/nodes/{node_id}/message"` | per-proj | Send-input endpoint. |
| `harness_verify_tls` | bool | `true` | per-proj | Validate TLS-сертификаты. **Example**: `false` для self-signed dev. |

## Group: AI Usage ingest

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `claude_projects_dir` | str | `""` | per-proj (обычно GLB) | Override `~/.claude/projects/`. **Example**: `C:\\Users\\me\\.claude\\projects`. |
| `ai_usage_scan_enabled` | bool | `true` | GLB | Включён ли cron `ai_usage_ingest`. (Сейчас всегда регистрируется в `build_scheduler` независимо от этого ключа — резерв). |
| `ai_usage_scan_interval_minutes` | int | `5` | GLB | Период (резерв; в коде хардкод 5 в scheduler.py). |
| `ai_usage_scan_on_startup` | bool | `true` | GLB | Запустить ingest на старте (резерв). |

## Group: Routing

| Key | Type | Default | Per-proj | Описание |
|---|---|---|---|---|
| `work_routing_mode` | str | `"ask"` | per-proj | `ask` \| `claude` \| `codex` \| `continue`. (Резерв; см. orchestration_local_runner для текущего использования.) |

## Cross-references

- Per-project override flow — [`features/settings.md`](features/settings.md).
- Какие настройки читают какие сервисы — [`services.md`](services.md).
- Как добавить новый ключ — [`development.md`](development.md).
- Setup wizard — [`features/multi-project.md`](features/multi-project.md).
