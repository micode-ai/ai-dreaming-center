# Settings

DC has a two-level settings system:
- **Global** at `/settings` — defaults for every project.
- **Per-project** at `/p/{slug}/settings` — overrides on top of global.

## Contents

- [Inherit / Override](#inherit--override)
- [Global settings](#global-settings)
- [Per-project settings](#per-project-settings)
- [13 key groups](#13-key-groups)
- [Bool keys](#bool-keys)
- [Token / api_key keys](#token--api_key-keys)

## Inherit / Override

Each setting value can be in one of two states for a project:

- **Inherit** — uses the global default (or built-in fallback if global is also unset).
- **Override** — the project has its own value that replaces global.

In the UI on the per-project page, next to each key you see:
- `inherit` (radio button selected by default if not overridden).
- `override:` (radio button) + an input field. The current global value is shown next to it in small font as reference.

When the form is saved DC removes/adds rows in `project_settings (project_id, key, value)`. Inherit — removes, Override — writes.

Resolution:
1. ConfigResolver.get(project, key) first looks in `project_settings`.
2. If absent — takes from AppSettings (config.yaml / env).
3. If still absent — built-in default from the Pydantic Field.

## Global settings

Open `/settings` (no `/p/`). Heading "Глобальные настройки. Per-project overrides — на /p/{slug}/settings." (Global settings. Per-project overrides — at /p/{slug}/settings.)

The form is split into fieldsets by group. Each one has a list of keys (monospace) and an input or checkbox under each.

After Save:
- Pydantic-settings re-reads from the updated `config.yaml`.
- `request.app.state.settings` is replaced with the new instance.
- Changes apply immediately — uvicorn restart is not needed.

Exception: some server-level keys (`host`, `port`, `db_path`) require a restart because uvicorn binds to them at startup.

## Per-project settings

Open `/p/{slug}/settings`. Same logic as global, but:
- At the top — text "Per-project overrides. Inherit = используется global; Override = индивидуальное значение." (Per-project overrides. Inherit = uses global; Override = individual value.)
- Each key has a radio-pair: inherit / override.
- Below the key in small font — the global value for reference.

Save → INSERT/DELETE rows in `project_settings`. Changes apply immediately.

Not every key is available per-project. Server-level (`host`, `port`, `db_path`, `default_locale`) — global only. They aren't even shown on the per-project page.

## 13 key groups

DC has 92 settings in 13 groups. A short summary of each:

### 1. Database
`db_path` — path to the SQLite DB. Global only.

### 2. Projects
`projects_root`, `default_locale`. Scan root and default UI language.

### 3. Server
`host`, `port`. uvicorn bind address. Global only.

### 4. Claude CLI / runners
`claude_path`, `orchestration_local_runner`, `codex_path`, `continue_path`, `model_backend_profile`, `anthropic_base_url`, `anthropic_auth_token`, `anthropic_api_key`, `openai_proxy_*`. Where the Claude CLI lives and how to talk to it.

### 5. Self-study
`self_study_command` (default `/self-study`), `self_study_max_turns` (default 50), `self_study_model` (model override), `learning_notes_dir` (where to write notes), `agents_dir` (default `.claude/agents/` under working_dir).

### 6. Scheduling — nightly
`cron_enabled` (bool), `cron_expression` (5-part cron), `agents_per_night` (default 3), `wait_between_sec` (default 30), `nightly_max_concurrent` (opt.).

### 7. Scheduling — weekly (opt-in)
`weekly_tech_debt_scan_enabled` (default false), `weekly_tech_debt_scan_cron`, `weekly_tech_debt_scan_agent`. Same for product_ideas_scan and wiki_lint.

### 8. Watchdogs
`timeout_minutes` (default 20), `reconcile_interval_min` (default 5), `kill_grace_seconds` (default 5).

### 9. Paths
`tech_debt_dir`, `product_ideas_dir`, `wiki_dir`, `evolutions_dir`, `loops_dir`, `plans_dir`, `cascade_artifacts_dir`, `sidecar_findings_dir`, `contracts_dir`, `context_overrides_dir`. Where to look for read-only pages.

### 10. Jira
`jira_base_url`, `jira_email`, `jira_api_token`, `jira_user_account_id`, `jira_project_key`, `jira_issuetype` (default `Task`).

### 11. Harness (orchestration)
`harness_enabled`, `harness_url`, `harness_api_key`. If you use an external harness adapter for cascade.

### 12. AI Usage ingest
`claude_projects_dir` (default `~/.claude/projects/`), `ai_usage_ingest_enabled`, `ai_usage_ingest_interval_min` (default 5).

### 13. Routing
`default_project_slug` (for default-route), various routing flags.

Full list with types, defaults and use cases — [`../../configuration.md`](../../configuration.md).

## Bool keys

Bool keys (`cron_enabled`, `weekly_*_enabled`, `harness_enabled`, etc.) render as checkboxes.

In the global form — a plain `<input type="checkbox">`. A hidden input with `value="false"` sits before it (the standard browser workaround: if the checkbox is unchecked the browser sends only the hidden value, otherwise the checkbox value).

In per-project — same, but wrapped in an inherit/override radio.

If you don't remember the exact key type — just open `/settings`, find the key, see the form control:
- `<input type="text">` — string.
- `<input type="checkbox">` — bool.
- `<input type="password">` — secret (token / api_key).

## Token / api_key keys

Keys whose names contain `token` or `api_key` are automatically rendered as `<input type="password">` with `autocomplete="off"`.

This is for:
- Hiding in screenshots / shoulder-surfing.
- Protecting from browser autocomplete.

It does not protect the fact that the value sits in `config.yaml` as plain text. If you want secret-management — store in an env var (`DC_JIRA_API_TOKEN=...`) and don't type it in the form.

Important: on per-project Override of a token key the value lands in `project_settings.value` as plain text. If the DB is stolen — the secrets are in it. Exclude DB backups or encrypt them.

---

See also:
- [`../workflows/jira-integration.md`](../workflows/jira-integration.md) — concrete Jira creds example.
- [`../workflows/nightly-cron.md`](../workflows/nightly-cron.md) — nightly settings.
- [`../workflows/weekly-scanners.md`](../workflows/weekly-scanners.md) — weekly settings.
- Technical: [`../../configuration.md`](../../configuration.md), [`../../features/settings.md`](../../features/settings.md).
