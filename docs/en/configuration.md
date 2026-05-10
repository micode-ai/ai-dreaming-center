# Configuration Reference

Every setting in the application. The source of truth is the `AppSettings` class in [`dreaming/config.py`](../../dreaming/config.py) (92 fields, 13 groups).

## Contents

- [Where the config lives](#where-the-config-lives)
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

## Where the config lives

`config.yaml` at the repo root (next to `pyproject.toml`). Created by the setup wizard or by hand from [`config.example.yaml`](../../config.example.yaml).

Heads up: the path is relative (`Path("config.yaml")` in config.py:8). If you start from a different CWD — the wizard and save_yaml will miss. Run uvicorn from the repo root, or override via env vars `DC_DB_PATH=/abs/path/dreaming.db` and friends.

Reloading settings:
- On startup — `AppSettings.load()` in lifespan.
- The wizard and `/settings POST` explicitly do `request.app.state.settings = type(settings).load()`.

## Env vars

Prefix `DC_`. For example `DC_PORT=9000`, `DC_DEFAULT_LOCALE=en`.

Pydantic-settings reads env vars **on top of** YAML (config.py:19 `env_prefix="DC_"`, `extra="ignore"`).

## Per-project overrides

Most keys can be overridden per-project via the `project_settings (project_id, key, value)` table. Access — through `ConfigResolver.get(project, key, default)` ([`config_resolver.py:23`](../../dreaming/services/config_resolver.py)).

Override scope:
- **Global only** — typically server-level (db_path, host, port, default_locale).
- **Global + per-project** — everything else.

In the tables below the "Per-proj" column flags GLB-only explicitly.

## Cache invalidation

`ConfigResolver` is per-request, so changes to `project_settings` are not visible to the current request but are visible to the next. `HarnessClientCache.invalidate(project_id)` must be called by hand if you change harness_* per-project on the fly (but the current code doesn't call it — just restart the app).

## Group: Database

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `db_path` | str | `"data/dreaming.db"` | GLB | SQLite file (relative or absolute path). When starting from a different CWD — set absolute. **Example use**: `db_path: "/var/lib/dc/dreaming.db"`. |

Used by: [`SqliteDB.__init__`](../../dreaming/services/db.py) — `Path(self._path).parent.mkdir(parents=True, exist_ok=True)` if the directory is missing.

## Group: Projects

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `projects_root` | str | `""` | GLB | Root directory where all projects live (for the wizard scan). Default in setup.py — `D:\Work\micode`. **Example use**: `projects_root: "D:\\Work\\micode"`. |
| `default_locale` | str | `"ru"` | GLB | UI default language (if the `dc_locale` cookie is unset). Allowed: `ru`/`en`. **Example use**: `default_locale: "en"`. |

## Group: Server

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `host` | str | `"0.0.0.0"` | GLB | Bind host for uvicorn — uvicorn is configured via CLI, this key is exposed for in-app readers. |
| `port` | int | `8086` | GLB | Port (default 8086). Used to build `DREAMING_API_URL=http://localhost:{port}` in env-overrides for Claude. **Example use**: `port: 9000`. |

## Group: Claude CLI / runners

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `claude_path` | str | `"claude"` | per-proj | Path to the Claude CLI. On Windows `shutil.which("claude")` will pick `claude.cmd`. **Example use**: `claude_path: "C:\\Users\\me\\AppData\\Roaming\\npm\\claude.cmd"`. |
| `orchestration_local_runner` | str | `"claude"` | per-proj | `claude` \| `codex` \| `continue`. Wave 3+ (used per plan; codex/continue not implemented in current code). |
| `codex_path` | str | `"codex"` | per-proj | Path to the codex CLI. |
| `codex_api_key` | str (secret) | `""` | per-proj | Secret. Don't commit to a public repo. |
| `continue_path` | str | `".continue\\continue.cmd"` | per-proj | Path to the continue CLI. |
| `model_backend_profile` | str | `"native"` | per-proj | `native` \| `openrouter` \| `openai_proxy`. |
| `anthropic_base_url` | str | `""` | per-proj | Custom base URL for Anthropic API. |
| `anthropic_auth_token` | str (secret) | `""` | per-proj | Bearer token. |
| `anthropic_api_key` | str (secret) | `""` | per-proj | API key for Anthropic. |
| `openai_proxy_base_url` | str | `""` | per-proj | OpenAI-compatible proxy. |
| `openai_proxy_api_key` | str (secret) | `""` | per-proj | API key for the proxy. |
| `codex_command_template` | str | `'codex -p "{prompt}" --model {model}'` | per-proj | Codex command template. |
| `continue_command_template` | str | `'continue -p "{prompt}"'` | per-proj | Continue command template. |

Used by: [`ProcessManager._resolve_claude_path`](../../dreaming/services/process_manager.py) and cron jobs in `scheduler.py`. **secret** fields render as `type=password` in the settings UI.

## Group: Self-study

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `model` | str | `"sonnet"` | per-proj | Claude model for self-study (`sonnet` / `haiku` / `opus`). **Example**: `model: "haiku"` for cheap nightly scans. |
| `max_turns` | int | `25` | per-proj | `--max-turns N` for the Claude CLI. |
| `timeout_minutes` | int | `20` | per-proj | Silence-timeout watchdog. |
| `self_study_command` | str | `"/self-study"` | per-proj | Slash command. Full prompt: `{self_study_command} {agent_name}`. |
| `question_reminder_minutes` | int | `15` | per-proj | After N minutes without an answer to a pending question — TTS reminder (full implementation deferred). |
| `question_expire_minutes` | int | `60` | per-proj | After M minutes — questions expire (pending is cleared). |

## Group: Scheduling — nightly

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `cron_expression` | str | `"0 2 * * *"` | per-proj | Cron expression for nightly_learning. **Example**: `"0 3 * * *"` — every day at 3am. |
| `cron_enabled` | bool | `true` | per-proj | Toggle nightly. **Example**: `cron_enabled: false`. |
| `agents_per_night` | int | `5` | per-proj | How many top agents to pick. |
| `max_concurrent` | int | `2` | GLB (read from settings in `ProcessManager.__init__`) | Concurrency limit for parallel Claude sessions in ProcessManager. |
| `wait_between_sec` | int | `5` | per-proj | Pause between spawns in nightly_learning. |

`max_concurrent` is actually fetched as `getattr(settings, "max_concurrent", 2)` in `ProcessManager.__init__` — therefore a per-project override has no effect (set globally).

## Group: Scheduling — weekly (opt-in)

All weekly_*_enabled — **default false**. Turn them on only when needed (per-project via `/p/{slug}/settings`).

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `weekly_tech_debt_scan_cron` | str | `"0 3 * * 6"` | per-proj | Every Saturday 3:00. |
| `weekly_tech_debt_scan_enabled` | bool | `false` | per-proj | Enable tech-debt scan via the `/tech-debt-scan` slash command. |
| `weekly_timur_duty_cron` | str | `"0 2 * * 0"` | per-proj | Sunday 2:00. |
| `weekly_timur_duty_enabled` | bool | `false` | per-proj | (reserved for the future, not in `_PER_PROJECT_JOBS` yet). |
| `weekly_product_ideas_scan_cron` | str | `"0 20 * * 0"` | per-proj | Sunday 20:00. |
| `weekly_product_ideas_scan_enabled` | bool | `false` | per-proj | Enable product-ideas scan. |
| `weekly_wiki_lint_cron` | str | `"0 1 * * 6"` | per-proj | Saturday 1:00. |
| `weekly_wiki_lint_enabled` | bool | `false` | per-proj | Enable wiki-lint. |
| `weekly_evolve_apply_cron` | str | `"0 4 * * 0"` | per-proj | Sunday 4:00. |
| `weekly_evolve_apply_enabled` | bool | `false` | per-proj | (reserved). |
| `daily_bootstrap_cron` | str | `"0 4 * * *"` | per-proj | Daily 4:00. |
| `daily_bootstrap_enabled` | bool | `false` | per-proj | (reserved). |
| `daily_plans_cleanup_cron` | str | `"30 23 * * *"` | per-proj | Daily 23:30. |
| `daily_plans_cleanup_enabled` | bool | `false` | per-proj | (reserved). |
| `monthly_deep_audit_cron` | str | `"0 5 1 * *"` | per-proj | 1st of month at 5:00. |
| `monthly_deep_audit_enabled` | bool | `false` | per-proj | (reserved). |

"Reserved" = the key exists in `AppSettings`, but it isn't registered in `_PER_PROJECT_JOBS` ([`scheduler.py:173`](../../dreaming/services/scheduler.py)) → effectively a no-op. See [`development.md`](development.md) on how to add a new job.

## Group: Watchdogs

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `loop_watchdog_enabled` | bool | `true` | per-proj | Watchdog over reflex-loop stagnation. |
| `loop_watchdog_interval_minutes` | int | `60` | per-proj | Interval. |
| `sidecar_findings_enabled` | bool | `false` | per-proj | Enable the sidecar-findings UI. |
| `evolutions_stale_days` | int | `7` | per-proj | After how many days without updates an evolution is considered stale. |
| `loop_stagnation_hours` | int | `6` | per-proj | After how many hours without iterations a loop is considered stagnant. |
| `plans_archive_days` | int | `14` | per-proj | After how many days without updates a plan is archived. |

These keys set thresholds, but the actual usage is partly deferred.

## Group: Paths (Obsidian / artifacts)

These paths can be empty — then features don't work (the UI shows "not set").

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `obsidian_vault` | str | `""` | per-proj | Obsidian vault root. Used as a fallback base for other paths. **Example**: `Z:\\my-vault`. |
| `agents_dir` | str | `""` | per-proj | Override for `.claude/agents`. Default `{working_dir}/.claude/agents`. |
| `tech_debt_dir` | str | `""` | per-proj | Where TD-*.md live. **Example**: `D:\\Work\\micode\\rgs\\.claude\\tech-debt`. |
| `product_ideas_dir` | str | `""` | per-proj | Where PI-*.md live. |
| `contracts_dir` | str | `""` | per-proj | Module/page contracts. Default `{obsidian_vault}/03-Team/specs/contracts`. |
| `learning_notes_dir` | str | `""` | per-proj | Notes browser default = `{working_dir}/.claude/agents/learning-notes`. |
| `evolutions_dir` | str | `""` | per-proj | Default = `{working_dir}/.claude/agents/_context`. |
| `context_overrides_dir` | str | `""` | per-proj | Alternative to evolutions_dir. |
| `lessons_cursor_path` | str | `""` | per-proj | (reserved). |
| `loops_dir` | str | `""` | per-proj | Default = `{obsidian_vault}/03-Team/loops`. |
| `plans_dir` | str | `""` | per-proj | Default = `{obsidian_vault}/03-Team/plans`. |
| `sidecar_findings_dir` | str | `""` | per-proj | Default = `{obsidian_vault}/03-Team/sidecar-findings`. |
| `loops_templates_dir` | str | `""` | per-proj | (reserved). |
| `wiki_dir` | str | `""` | per-proj | Wiki root, for status and bootstrap. |

The default fallbacks are baked into the routes (e.g. project_evolutions.py:14, project_loops.py:15).

## Group: Jira

All Jira fields are secret, rendered in the UI as password.

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `jira_url` | str | `""` | per-proj | Full base URL. **Example**: `https://acme.atlassian.net`. |
| `jira_email` | str (secret) | `""` | per-proj | User email for Basic Auth. |
| `jira_api_token` | str (secret) | `""` | per-proj | API token (created in the Atlassian profile). |
| `jira_project_key` | str | `""` | per-proj | Project key (RGS, ENG etc.). Per-project override applied in [`project_ideas.py:74`](../../dreaming/routes/project_ideas.py). |
| `jira_user_account_id` | str | `""` | per-proj | Account ID for reporter+assignee. **Example**: `5b10a2844c20165700ede21g`. |

Used by: [`jira.create_task`](../../dreaming/services/jira.py) — POST to `/rest/api/3/issue`.

## Group: Harness (orchestration)

Adapter to an external harness (if used instead of local claude).

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `harness_base_url` | str | `""` | per-proj | If empty — `HarnessClient.enabled = False`, methods return stubs. **Example**: `https://harness.acme.com`. |
| `harness_api_key` | str (secret) | `""` | per-proj | Bearer token. |
| `harness_timeout_sec` | int | `30` | per-proj | HTTP timeout. |
| `harness_stream_enabled` | bool | `true` | per-proj | Use SSE (true) or polling fallback. |
| `harness_start_path` | str | `"/api/orchestration/start"` | per-proj | Path for POST start. |
| `harness_events_stream_path` | str | `"/api/orchestration/{run_id}/stream"` | per-proj | SSE endpoint. |
| `harness_events_path` | str | `"/api/orchestration/{run_id}/events"` | per-proj | Polling endpoint. |
| `harness_send_input_path` | str | `"/api/orchestration/{run_id}/nodes/{node_id}/message"` | per-proj | Send-input endpoint. |
| `harness_verify_tls` | bool | `true` | per-proj | Validate TLS certs. **Example**: `false` for self-signed dev. |

## Group: AI Usage ingest

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `claude_projects_dir` | str | `""` | per-proj (typically GLB) | Override for `~/.claude/projects/`. **Example**: `C:\\Users\\me\\.claude\\projects`. |
| `ai_usage_scan_enabled` | bool | `true` | GLB | Whether the cron `ai_usage_ingest` runs. (Currently always registered in `build_scheduler` regardless of this key — reserved.) |
| `ai_usage_scan_interval_minutes` | int | `5` | GLB | Period (reserved; the code hardcodes 5 in scheduler.py). |
| `ai_usage_scan_on_startup` | bool | `true` | GLB | Run ingest on startup (reserved). |

## Group: Routing

| Key | Type | Default | Per-proj | Description |
|---|---|---|---|---|
| `work_routing_mode` | str | `"ask"` | per-proj | `ask` \| `claude` \| `codex` \| `continue`. (Reserved; see orchestration_local_runner for current usage.) |

## Cross-references

- Per-project override flow — [`features/settings.md`](features/settings.md).
- Which settings each service reads — [`services.md`](services.md).
- How to add a new key — [`development.md`](development.md).
- Setup wizard — [`features/multi-project.md`](features/multi-project.md).
