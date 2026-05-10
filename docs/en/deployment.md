# Deployment

How to run AI Dreaming Center locally and in production-like modes. Backup, monitoring, rolling upgrade.

## Contents

- [Local development](#local-development)
- [venv setup](#venv-setup)
- [Persistent run](#persistent-run)
  - [Windows Task Scheduler](#windows-task-scheduler)
  - [NSSM](#nssm-windows-service)
  - [WSL + systemd](#wsl--systemd)
- [Logs and rotation](#logs-and-rotation)
- [DB backup](#db-backup)
- [Coexistence with ALC](#coexistence-with-alc)
- [Rolling upgrade](#rolling-upgrade)
- [Monitoring](#monitoring)

## Local development

```bash
cd D:\Work\micode\ai-dreaming-center
pip install -e .
python -m uvicorn dreaming.main:app --port 8086 --reload
```

`--reload` watches `*.py` changes and restarts the app. For templates this isn't needed — Jinja2 reloads automatically.

The config is created by the wizard at `http://localhost:8086`:
- On first launch `setup_gate` redirects to `/setup`.
- Fill in `claude_path`, `projects_root` (default `D:\Work\micode`), `default_locale`.
- Click Scan, pick projects (mark default), Save.

After that `config.yaml` and `data/dreaming.db` appear.

## venv setup

```powershell
# From the repo root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Bash (WSL/git-bash):

```bash
python -m venv .venv
source .venv/Scripts/activate    # on Windows
# or: source .venv/bin/activate   # on Linux/macOS
pip install -e .
```

`pip install -e .` is an editable install. Changes in `dreaming/` are visible to uvicorn immediately.

## Persistent run

### Windows Task Scheduler

Create an XML with the trigger "At log on of any user" and a `Start a program` action.

Minimum XML (place in `dc-dashboard.xml`):

```xml
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>D:\Work\micode\ai-dreaming-center\.venv\Scripts\python.exe</Command>
      <Arguments>-m uvicorn dreaming.main:app --port 8086 --host 0.0.0.0</Arguments>
      <WorkingDirectory>D:\Work\micode\ai-dreaming-center</WorkingDirectory>
    </Exec>
  </Actions>
  <Settings>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
</Task>
```

Import:

```powershell
schtasks /Create /TN "AI Dreaming Center" /XML dc-dashboard.xml
```

Start/stop:

```powershell
schtasks /Run /TN "AI Dreaming Center"
schtasks /End /TN "AI Dreaming Center"
```

### NSSM (Windows service)

An alternative is to make a service via NSSM. Download `nssm.exe` from https://nssm.cc/, unpack.

```powershell
nssm install AIDreamingCenter "D:\Work\micode\ai-dreaming-center\.venv\Scripts\python.exe"
nssm set AIDreamingCenter AppParameters "-m uvicorn dreaming.main:app --port 8086 --host 0.0.0.0"
nssm set AIDreamingCenter AppDirectory "D:\Work\micode\ai-dreaming-center"
nssm set AIDreamingCenter AppStdout "D:\Work\micode\ai-dreaming-center\logs\stdout.log"
nssm set AIDreamingCenter AppStderr "D:\Work\micode\ai-dreaming-center\logs\stderr.log"
nssm set AIDreamingCenter Start SERVICE_AUTO_START
nssm start AIDreamingCenter
```

Stop: `nssm stop AIDreamingCenter`. Remove: `nssm remove AIDreamingCenter confirm`.

### WSL + systemd

If running under WSL2 with systemd enabled:

```ini
# /etc/systemd/system/dc-dashboard.service
[Unit]
Description=AI Dreaming Center
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/mnt/d/Work/micode/ai-dreaming-center
ExecStart=/mnt/d/Work/micode/ai-dreaming-center/.venv/bin/python -m uvicorn dreaming.main:app --port 8086 --host 0.0.0.0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dc-dashboard
sudo journalctl -u dc-dashboard -f
```

## Logs and rotation

uvicorn writes to stdout/stderr. Without explicit setup — to the console. For persistent runs:

- **Task Scheduler**: add `>> logs\stdout.log 2>&1` in Arguments via a cmd.exe shim, or configure `<Exec>` via `cmd.exe /c "..."`.
- **NSSM**: see `AppStdout`/`AppStderr` above. NSSM can rotate — `nssm set AIDreamingCenter AppRotateFiles 1`, `AppRotateBytes 10485760` (10MB).
- **systemd**: journaled via journald, read via `journalctl -u dc-dashboard`.

In-app logging — standard `logging`. The level is set via env `LOG_LEVEL=INFO` (if you wrap a uvicorn launcher), or via `dictConfig` if you want more control.

App logs go through `log = logging.getLogger(__name__)` in every module — so the output shows module names.

## DB backup

SQLite with WAL — you can't just copy the `.db` file because `.db-wal` may contain unflushed pages.

Use the `sqlite3 .backup` API:

```bash
# In Bash or WSL:
sqlite3 data/dreaming.db ".backup data/dreaming-backup-$(date +%Y%m%d-%H%M).db"
```

PowerShell:

```powershell
$ts = Get-Date -Format "yyyyMMdd-HHmm"
sqlite3 data/dreaming.db ".backup data/dreaming-backup-$ts.db"
```

Files:
- `dreaming.db` — main DB.
- `dreaming.db-wal` — WAL log, freed at checkpoint.
- `dreaming.db-shm` — shared memory, ephemeral.

Backing up only the `.backup` result is enough, it contains a consistent snapshot.

For a cron job (Windows Task Scheduler):

```xml
<Exec>
  <Command>cmd.exe</Command>
  <Arguments>/c sqlite3 D:\Work\micode\ai-dreaming-center\data\dreaming.db .backup D:\backups\dc\dreaming-%date:~0,4%%date:~5,2%%date:~8,2%.db</Arguments>
</Exec>
```

## Coexistence with ALC

The old ALC sits on `:8085` (see ALC `CLAUDE.md`). DC — on `:8086`. You can keep both live at the same time.

Conflicts during simultaneous operation:
- Both try to spawn claude — they compete for Anthropic API limits.
- Both read `~/.claude/projects/*.jsonl` for AI Usage. That's OK — each has its own `ai_usage_files` state.
- ALC wrote to `data/learning_sessions.db`, DC writes to `data/dreaming.db`. Don't overlap.

## Rolling upgrade

```bash
# 1. Backup
cp data/dreaming.db data/dreaming.db.bak.$(date +%Y%m%d)

# 2. Pull
git fetch origin
git checkout main
git pull

# 3. Re-install (deps may have changed)
pip install -e .

# 4. Restart service
nssm restart AIDreamingCenter   # or: systemctl restart dc-dashboard
```

Schema migrations are idempotent (`_migrate_orchestration` in [`db.py:282`](../../dreaming/services/db.py)) — re-running on an already-migrated DB is a no-op. But if you hack the DB by hand or do a non-standard migration — **back up first**.

## Monitoring

### Health-check

`GET /health` returns `{"ok": true}` without touching the DB. Suitable for a load-balancer health-check or uptime monitor.

```bash
curl -fsS http://localhost:8086/health || echo DOWN
```

### Scheduler state

In a running app you can probe via a Python REPL (if you have SSH/ipython access). The scheduler has `print_jobs()`:

```python
import requests
# Hot-reload doesn't suit; you need runtime introspection via a dedicated endpoint.
# Quick check via the log:
tail -f logs/stdout.log | grep -E "scheduler|Scheduled"
```

There is no dedicated endpoint for job state in code — add one if you need (see [`development.md`](development.md) → adding a route).

### AI Usage ingest

Cron every 5 minutes (`ai_usage_ingest` job). On a normal run the log:

```
INFO ai_usage_ingest: files=42 inserted=18 skipped=2 errors=0 in 234ms
```

If `inserted=0` all the time:
- Check `claude_projects_dir` in settings (or that `~/.claude/projects/` exists).
- Check that the project `working_dir` in the DB matches the actual paths where claude is spawned.

### Reconcile job

Also every 5 minutes. Log:

```
INFO Auto-closed N DB session(s) after <key> exit
```

If sessions hang in `running` forever — you have orphans; you can verify via:

```bash
sqlite3 data/dreaming.db "SELECT id, agent_name, started_at FROM agent_learning_sessions WHERE status='running' ORDER BY started_at DESC LIMIT 10"
```

And cross-check with `pm.list_running()` through a REPL or with running processes via `tasklist /FI "IMAGENAME eq claude.cmd"`.

### Log noise budget

Under normal load: 1–2 INFO/min from ai_usage_ingest, 1 line/sec from ProcessManager during an active session. If you see spam like `WARN tail io error` — there's a filesystem problem or antivirus locking Claude's jsonl files.

## Cross-references

- Configuration: [`configuration.md`](configuration.md).
- Troubleshooting: [`troubleshooting.md`](troubleshooting.md).
- Setup wizard flow: [`features/multi-project.md`](features/multi-project.md).
