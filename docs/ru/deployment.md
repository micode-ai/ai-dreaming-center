# Deployment

Как запускать AI Dreaming Center локально и в production-подобных режимах. Бэкап, мониторинг, rolling upgrade.

## Содержание

- [Local development](#local-development)
- [venv setup](#venv-setup)
- [Persistent run](#persistent-run)
  - [Windows Task Scheduler](#windows-task-scheduler)
  - [NSSM](#nssm-windows-service)
  - [WSL + systemd](#wsl--systemd)
- [Логи и rotation](#логи-и-rotation)
- [Backup БД](#backup-бд)
- [Coexistence с ALC](#coexistence-с-alc)
- [Rolling upgrade](#rolling-upgrade)
- [Monitoring](#monitoring)

## Local development

```bash
cd D:\Work\micode\ai-dreaming-center
pip install -e .
python -m uvicorn dreaming.main:app --port 8086 --reload
```

`--reload` следит за изменениями `*.py` и перезапускает app. Для шаблонов это не нужно — Jinja2 reloads автоматически.

Конфиг создаётся wizard'ом по адресу `http://localhost:8086`:
- При первом запуске `setup_gate` редиректит на `/setup`.
- Заполни `claude_path`, `projects_root` (default `D:\Work\micode`), `default_locale`.
- Жми Scan, выбери проекты (помечь default), Save.

После этого появятся `config.yaml` и `data/dreaming.db`.

## venv setup

```powershell
# Из корня проекта
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Bash (WSL/git-bash):

```bash
python -m venv .venv
source .venv/Scripts/activate    # на Windows
# или: source .venv/bin/activate   # на Linux/macOS
pip install -e .
```

`pip install -e .` — editable install. Изменения в `dreaming/` сразу видны uvicorn'у.

## Persistent run

### Windows Task Scheduler

Создай XML с триггером «At log on of any user», `Start a program` действие.

Минимальный XML (положи в `dc-dashboard.xml`):

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

Импорт:

```powershell
schtasks /Create /TN "AI Dreaming Center" /XML dc-dashboard.xml
```

Запуск/остановка:

```powershell
schtasks /Run /TN "AI Dreaming Center"
schtasks /End /TN "AI Dreaming Center"
```

### NSSM (Windows service)

Альтернатива — создать сервис через NSSM. Скачай `nssm.exe` с https://nssm.cc/, распакуй.

```powershell
nssm install AIDreamingCenter "D:\Work\micode\ai-dreaming-center\.venv\Scripts\python.exe"
nssm set AIDreamingCenter AppParameters "-m uvicorn dreaming.main:app --port 8086 --host 0.0.0.0"
nssm set AIDreamingCenter AppDirectory "D:\Work\micode\ai-dreaming-center"
nssm set AIDreamingCenter AppStdout "D:\Work\micode\ai-dreaming-center\logs\stdout.log"
nssm set AIDreamingCenter AppStderr "D:\Work\micode\ai-dreaming-center\logs\stderr.log"
nssm set AIDreamingCenter Start SERVICE_AUTO_START
nssm start AIDreamingCenter
```

Останов: `nssm stop AIDreamingCenter`. Удалить: `nssm remove AIDreamingCenter confirm`.

### WSL + systemd

Если запускаешь под WSL2 с включённым systemd:

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

## Логи и rotation

uvicorn пишет в stdout/stderr. Без явной настройки — на консоль. Для persistent'а:

- **Task Scheduler**: добавь `>> logs\stdout.log 2>&1` в Arguments через cmd.exe shim, либо настрой `<Exec>` через `cmd.exe /c "..."`.
- **NSSM**: см. `AppStdout`/`AppStderr` выше. NSSM умеет ротейтить — `nssm set AIDreamingCenter AppRotateFiles 1`, `AppRotateBytes 10485760` (10MB).
- **systemd**: журналируется через journald, читаешь через `journalctl -u dc-dashboard`.

Внутри-приложения логирование — стандартный `logging`. Уровень настраивается через env `LOG_LEVEL=INFO` (если оборачиваешь uvicorn-launcher), либо через `dictConfig` если хочешь больше контроля.

Логи приложения пишутся через `log = logging.getLogger(__name__)` в каждом модуле — поэтому в выдаче будешь видеть имена модулей.

## Backup БД

SQLite с WAL — нельзя просто скопировать `.db` файл, потому что `.db-wal` может содержать незаписанные страницы.

Используй `sqlite3 .backup` API:

```bash
# В Bash или WSL:
sqlite3 data/dreaming.db ".backup data/dreaming-backup-$(date +%Y%m%d-%H%M).db"
```

PowerShell:

```powershell
$ts = Get-Date -Format "yyyyMMdd-HHmm"
sqlite3 data/dreaming.db ".backup data/dreaming-backup-$ts.db"
```

Файлы:
- `dreaming.db` — основная БД.
- `dreaming.db-wal` — WAL log, освобождается при checkpoint.
- `dreaming.db-shm` — shared memory, эфемерный.

Достаточно бекапить только результат `.backup`, он содержит consistent snapshot.

Для cron'а (Windows Task Scheduler):

```xml
<Exec>
  <Command>cmd.exe</Command>
  <Arguments>/c sqlite3 D:\Work\micode\ai-dreaming-center\data\dreaming.db .backup D:\backups\dc\dreaming-%date:~0,4%%date:~5,2%%date:~8,2%.db</Arguments>
</Exec>
```

## Coexistence с ALC

Старый ALC сидит на `:8085` (см. ALC `CLAUDE.md`). DC — на `:8086`. Можно держать оба live одновременно.

Конфликты при одновременной работе:
- Оба пытаются спавнить claude — конкурируют за лимиты Anthropic API.
- Оба читают `~/.claude/projects/*.jsonl` для AI Usage. Это OK — каждый имеет свой `ai_usage_files` state.
- ALC писал в `data/learning_sessions.db`, DC — в `data/dreaming.db`. Не пересекаются.

## Rolling upgrade

```bash
# 1. Бекап
cp data/dreaming.db data/dreaming.db.bak.$(date +%Y%m%d)

# 2. Pull
git fetch origin
git checkout main
git pull

# 3. Re-install (deps могли поменяться)
pip install -e .

# 4. Restart service
nssm restart AIDreamingCenter   # или: systemctl restart dc-dashboard
```

Schema migrations идемпотентны (`_migrate_orchestration` в [`db.py:282`](../dreaming/services/db.py)) — повторный запуск на already-migrated БД no-op'ит. Но если ты хакаешь БД руками или делаешь нестандартную миграцию — **бэкапь сначала**.

## Monitoring

### Health-check

`GET /health` возвращает `{"ok": true}` без касания БД. Подходит для load-balancer health-check'а или uptime monitor.

```bash
curl -fsS http://localhost:8086/health || echo DOWN
```

### Scheduler state

В running app можно опрашивать через Python REPL (если есть SSH/ipython доступ). У scheduler'а есть `print_jobs()`:

```python
import requests
# Hot-reload не подходит; нужен runtime introspection через специальный endpoint.
# Quick check через лог:
tail -f logs/stdout.log | grep -E "scheduler|Scheduled"
```

В коде нет dedicated endpoint'а для job state — добавь сам если нужно (см. [`development.md`](development.md) → adding a route).

### AI Usage ingest

Cron каждые 5 минут (`ai_usage_ingest` job). При нормальном run'е лог:

```
INFO ai_usage_ingest: files=42 inserted=18 skipped=2 errors=0 in 234ms
```

Если `inserted=0` всё время:
- Проверь `claude_projects_dir` в settings (или `~/.claude/projects/` существует?).
- Проверь что `working_dir` проектов в БД совпадают с реальными путями где спавнится claude.

### Reconcile job

Также каждые 5 минут. Лог:

```
INFO Auto-closed N DB session(s) after <key> exit
```

Если sessions висят в `running` навсегда — у тебя orphan'ы; это можно проверить через:

```bash
sqlite3 data/dreaming.db "SELECT id, agent_name, started_at FROM agent_learning_sessions WHERE status='running' ORDER BY started_at DESC LIMIT 10"
```

И сверить с `pm.list_running()` через REPL или с running процессами через `tasklist /FI "IMAGENAME eq claude.cmd"`.

### Log noise budget

В normal load: 1-2 INFO/min из ai_usage_ingest, 1 строка/sec из ProcessManager при активной сессии. Если видишь spam'и `WARN tail io error` — у тебя problem с filesystem'ом или antivirus locks Claude jsonl'ы.

## Cross-references

- Configuration: [`configuration.md`](configuration.md).
- Troubleshooting: [`troubleshooting.md`](troubleshooting.md).
- Setup wizard flow: [`features/multi-project.md`](features/multi-project.md).
