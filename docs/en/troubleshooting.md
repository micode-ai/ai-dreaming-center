# Troubleshooting

Common issues and quick diagnostic commands.

## Contents

- [Setup wizard finds nothing](#setup-wizard-finds-nothing)
- [Start session does nothing](#start-session-does-nothing)
- [Port 8086 in use](#port-8086-in-use)
- [DB locked](#db-locked)
- [/p/{slug}/ returns 404](#pslug-returns-404)
- [nightly_learning didn't fire](#nightly_learning-didnt-fire)
- [AI Usage shows 0](#ai-usage-shows-0-events)
- [Jira button returns 400](#jira-button-returns-400)
- [Orchestration page is empty](#orchestration-page-is-empty)
- [i18n shows raw keys](#i18n-shows-raw-keys)
- [Mojibake on Cyrillic](#mojibake-on-cyrillic)

## Setup wizard finds nothing

**Symptoms**: on `/setup` after clicking Scan, on the right side — "В каталоге X не найдено подпапок (или каталог не существует)" (No subfolders in directory X (or the directory does not exist)).

**Causes**:
1. `projects_root` is empty or points to a non-existent path.
2. Every subfolder starts with `.` (then `scan_projects_root` ignores them, see [`projects.py:144`](../../dreaming/services/projects.py)).
3. `projects_root` points at a file, not a directory.

**Diagnosis** (PowerShell):

```powershell
# Verify the path
Test-Path "D:\Work\micode"      # should return True
Get-ChildItem "D:\Work\micode" -Directory | Where-Object { $_.Name -notmatch '^\.' }
```

**Cure**: type a valid absolute path like `D:\Work\micode`. Verify read permissions on the directory.

## Start session does nothing

**Symptoms**: clicking "Start" on the rotation page reloads the page but no new active run appears in `/p/{slug}/live`.

**Causes**:
1. `claude` not in PATH (or `claude_path` is wrong).
2. `max_concurrent` reached — other sessions hold the slots.
3. An agent with this name is already running for this project.

**Diagnosis**:

PowerShell:

```powershell
# Will claude be found?
Get-Command claude -ErrorAction SilentlyContinue
# Should be a reference to claude.cmd

# Test:
& claude --version
```

Bash:

```bash
which claude
shutil.which("claude")  # python
```

In code: `_resolve_claude_path` ([`process_manager.py:31`](../../dreaming/services/process_manager.py)) does `shutil.which(claude_path)` — if it returns None, falls back to the original string and the spawn fails with `FileNotFoundError`.

**Cure**:
- Open Settings → "Claude path" → type the absolute path to `claude.cmd` (Windows).
- If max_concurrent has blocked you — wait for existing sessions or fix the setting.

The logs will show:

```
ERROR Claude CLI not found at 'claude'. Check Settings → Claude Path.
```

## Port 8086 in use

**Symptoms**: `OSError: [Errno 98] Address already in use` or `[WinError 10048]` when starting uvicorn.

**Diagnosis** (PowerShell):

```powershell
Get-NetTCPConnection -LocalPort 8086 -ErrorAction SilentlyContinue
# Will show PID
Get-Process -Id <PID>
```

```powershell
# Kill orphan uvicorn:
Stop-Process -Id <PID> -Force
```

Bash:

```bash
lsof -i:8086
# or: ss -tlnp | grep 8086
kill -9 <PID>
```

**Cure**: kill the process or change `port` in `config.yaml`.

## DB locked

**Symptoms**: `sqlite3.OperationalError: database is locked`.

**Causes**:
- A long transaction in another process.
- WAL hasn't checkpointed.
- Some external tool (DB Browser) holds an exclusive lock.

**Diagnosis**:

```powershell
# Who holds the file?
handle.exe data\dreaming.db    # https://learn.microsoft.com/sysinternals/downloads/handle
```

Bash:

```bash
fuser data/dreaming.db
lsof data/dreaming.db
```

**Cure**:
- Close DB Browser / sqlite-shell.
- WAL files: check `data/dreaming.db-wal` — if very large (> 100MB), checkpoint:

```bash
sqlite3 data/dreaming.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

- Restart the service.

## /p/{slug}/ returns 404

**Symptoms**: page says "Project not found" or "Project disabled".

**Causes** (see [`project_resolver.py:18`](../../dreaming/middleware/project_resolver.py)):
1. The project with that slug was deleted.
2. `enabled=0`.

**Diagnosis**:

```bash
sqlite3 data/dreaming.db "SELECT slug, enabled FROM projects"
```

The `project_not_found.html` template distinguishes `is_disabled` vs "doesn't exist": check the error text.

**Cure**:
- Visit `/projects` → toggle.
- Or direct SQL: `UPDATE projects SET enabled=1 WHERE slug='X'`.

## nightly_learning didn't fire

**Symptoms**: night passed, the DB has no sessions for the project.

**Causes**:
1. `cron_enabled=false` (per-project via the resolver).
2. The cron expression is invalid (then `register_project_jobs` silently skips, see [`scheduler.py:198`](../../dreaming/services/scheduler.py)).
3. The scheduler didn't start.
4. Every agent is `enabled=0` or `next_agents_for_nightly` returned an empty list.

**Diagnosis**:

```bash
# Active jobs:
sqlite3 data/dreaming.db "SELECT slug FROM projects WHERE enabled=1"
```

Logs:

```
INFO Scheduled job: nightly_learning_<slug>
INFO nightly_learning [<slug>]: N candidates
```

If you see `nightly_learning [<slug>]: 0 candidates` — there are no enabled agents in `agent_learning_rotation`.

**Cure**:
- Check `/p/{slug}/settings` → `cron_enabled` (override = true) or global.
- Check the cron expr: 5 fields separated by spaces (`min hour day month dow`). `0 2 * * *` — every day at 02:00 UTC.
- Visit `/p/{slug}/rotation` — are there enabled agents?

## AI Usage shows 0 events

**Symptoms**: `/ai-usage` or `/p/{slug}/ai-usage` show "events_total: 0" or zeros across models.

**Causes**:
1. `claude_projects_dir` points to the wrong place (not `~/.claude/projects/`).
2. Claude has never been launched under this user — no JSONL files.
3. cwd in JSONL doesn't match `working_dir` of any registered project (rows are skipped).

**Diagnosis**:

```powershell
# Where do Claude jsonls live?
Test-Path "$env:USERPROFILE\.claude\projects"
Get-ChildItem "$env:USERPROFILE\.claude\projects" -Recurse -Filter *.jsonl | Measure-Object
```

Bash:

```bash
ls -la ~/.claude/projects/
find ~/.claude/projects -name '*.jsonl' | wc -l
```

Ingest log every 5 minutes:

```
INFO ai_usage_ingest: files=42 inserted=18 skipped=2 errors=0 in 234ms
```

If `inserted=0`, `skipped >> 0` — you have a cwd mismatch. Check what's actually in the JSONL:

```powershell
Get-Content "$env:USERPROFILE\.claude\projects\<slug>\<session>.jsonl" | Select-Object -First 5
# find "cwd": "..." and compare with working_dir in DB
```

```bash
sqlite3 data/dreaming.db "SELECT slug, working_dir FROM projects"
```

**Cure**: tune `working_dir` in `projects` so it matches Claude's real cwd 1-to-1. If you run via WSL and Claude through Windows — paths will differ (`/mnt/d/...` vs `D:\\...`).

## Jira button returns 400

**Symptoms**: clicking "Create Jira Task" in `/p/{slug}/ideas/...` returns 400 with the message "Настройте Jira (email + API token) в /settings" (Configure Jira (email + API token) in /settings) or similar.

**Causes** (see [`jira.py:62`](../../dreaming/services/jira.py)):
- `jira_email` or `jira_api_token` not set.
- `jira_user_account_id` not set.
- `jira_url` not set.
- `jira_project_key` not set in either global or project_settings.

**Diagnosis**:

```bash
sqlite3 data/dreaming.db "SELECT key, value FROM project_settings WHERE key LIKE 'jira_%'"
```

```bash
grep -E '^jira_' config.yaml
```

**Cure**: open `/settings`, fill all 5 jira_* fields, save.

If a specific project should use a different Jira project key — open `/p/{slug}/settings`, override `jira_project_key`.

## Orchestration page is empty

**Symptoms**: created a run via UI or curl, but `/p/{slug}/orchestration/{run_id}` shows 0 nodes / 0 messages.

**Causes**:
1. The watcher (`ClaudeSessionTail`) didn't find the jsonl file — it didn't appear because claude didn't start.
2. `working_dir` is wrong — the jsonl is created somewhere unexpected.
3. The `claude_projects_dir` override is wrong.

**Diagnosis**:

In the logs at start:

```
INFO orchestration_start_form: jsonl not yet visible for session <id>; backfill will recover
```

or:

```
INFO tail_session_file: attach run=... node=... path=...
```

If the first — the watcher didn't find and didn't start the tail.

Find the file by hand:

```powershell
Get-ChildItem "$env:USERPROFILE\.claude\projects" -Recurse -Filter "<external_id>.jsonl"
```

If it exists — the watcher just didn't catch it. Run the backfill:

```python
# Via REPL:
from dreaming.services.subagent_backfill import backfill_run
await backfill_run(run_id, db, hub)
```

Or use a `scripts/smoke_*.py` if there's a fitting one.

**Cure**:
- Check the project's `working_dir` — it must be the **same path** from which claude is normally invoked in this project.
- Check that claude actually started: look at `/p/{slug}/live` or `tasklist | findstr claude.cmd`.

## i18n shows raw keys

**Symptoms**: on a page you see `p.dashboard` instead of "Панель" (Dashboard).

**Causes**:
- The key exists in the template but not in `messages_ru.json` (or EN).
- `messages_*.json` failed to load (broken JSON).
- The locale cookie points to a non-existent locale.

**Diagnosis**:

```bash
python scripts/check_i18n.py
# Shows keys that exist in one file but not the other.
```

Open `dreaming/i18n/messages_ru.json` in an IDE — it'll highlight JSON syntax errors.

**Cure**:
- Add the key to **both** files (`messages_ru.json` AND `messages_en.json`). Run `check_i18n.py` again — should exit 0.
- If the JSON is broken — fix the syntax, restart the app.

## Mojibake on Cyrillic

**Symptoms**: Cyrillic reads as `Ð?Ñ?ÐµÐ¼Ð¸Ð¼ ÐµÐ³Ð¾`. JSON parser fails with `UnicodeDecodeError`.

**Causes**:
- The file was saved as UTF-16 LE (default PowerShell `Set-Content` on PS 5.1).
- A BOM is present where the parser doesn't expect one.

**Diagnosis** (PowerShell):

```powershell
$bytes = [IO.File]::ReadAllBytes("dreaming\i18n\messages_ru.json")
$bytes[0..3] -join ' '
# 255 254  -> UTF-16 LE BOM
# 239 187 191 -> UTF-8 BOM
# 123 ... -> starts with {, OK
```

**Cure**:
- On PowerShell 5.1: `Out-File -Encoding utf8` still adds a BOM. Use:
  ```powershell
  [IO.File]::WriteAllText("path", $content, [System.Text.UTF8Encoding]::new($false))
  ```
- On PowerShell 7+: `Out-File -Encoding utf8NoBOM`.
- In Bash/git-bash: `echo "..." > file` uses UTF-8 without BOM natively.
- Or just: use the Write tool from Claude Code — it writes UTF-8 without BOM.

See also [`development.md`](development.md) → Encoding on Windows.

## Cross-references

- Logs and monitoring — [`deployment.md`](deployment.md).
- Config — [`configuration.md`](configuration.md).
- Architecture (to understand who calls whom) — [`architecture.md`](architecture.md).
