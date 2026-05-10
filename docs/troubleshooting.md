# Troubleshooting

Типовые проблемы и быстрые диагностические команды.

## Содержание

- [Setup wizard ничего не находит](#setup-wizard-ничего-не-находит)
- [Start session не делает ничего](#start-session-не-делает-ничего)
- [Порт 8086 занят](#порт-8086-занят)
- [DB locked](#db-locked)
- [/p/{slug}/ возвращает 404](#pslug-возвращает-404)
- [nightly_learning не сработал](#nightly_learning-не-сработал)
- [AI Usage показывает 0](#ai-usage-показывает-0-events)
- [Jira кнопка отдаёт 400](#jira-кнопка-отдаёт-400)
- [Orchestration page пустая](#orchestration-page-пустая)
- [i18n показывает raw keys](#i18n-показывает-raw-keys)
- [Mojibake на Cyrillic](#mojibake-на-cyrillic)

## Setup wizard ничего не находит

**Симптомы**: На `/setup` после нажатия Scan, в правой части — «В каталоге X не найдено подпапок (или каталог не существует)».

**Причины**:
1. `projects_root` пустой или указан несуществующий путь.
2. Все подпапки начинаются с `.` (тогда `scan_projects_root` их игнорирует, см. [`projects.py:144`](../dreaming/services/projects.py)).
3. `projects_root` указывает на файл, не директорию.

**Диагностика** (PowerShell):

```powershell
# Проверь путь
Test-Path "D:\Work\micode"      # должно вернуть True
Get-ChildItem "D:\Work\micode" -Directory | Where-Object { $_.Name -notmatch '^\.' }
```

**Лечение**: Введи валидный абсолютный путь типа `D:\Work\micode`. Проверь права чтения на каталог.

## Start session не делает ничего

**Симптомы**: жмёшь «Start» на rotation page, страница перезагружается, но в `/p/{slug}/live` нет нового активного run'а.

**Причины**:
1. `claude` не в PATH (или `claude_path` неверен).
2. `max_concurrent` достигнут — другие сессии заняли слоты.
3. agent с этим именем уже running для этого проекта.

**Диагностика**:

PowerShell:

```powershell
# Найдётся ли claude?
Get-Command claude -ErrorAction SilentlyContinue
# Должна быть ссылка на claude.cmd

# Тест:
& claude --version
```

Bash:

```bash
which claude
shutil.which("claude")  # python
```

В коде: `_resolve_claude_path` ([`process_manager.py:31`](../dreaming/services/process_manager.py)) делает `shutil.which(claude_path)` — если возвращает None, то fallback на исходную строку и spawn провалится с `FileNotFoundError`.

**Лечение**:
- Открой Settings → "Claude path" → впиши абсолютный путь к `claude.cmd` (Windows).
- Если max_concurrent заблокировал — подожди существующие сессии или поправь setting.

Логи покажут:

```
ERROR Claude CLI not found at 'claude'. Check Settings → Claude Path.
```

## Порт 8086 занят

**Симптомы**: `OSError: [Errno 98] Address already in use` или `[WinError 10048]` при старте uvicorn.

**Диагностика** (PowerShell):

```powershell
Get-NetTCPConnection -LocalPort 8086 -ErrorAction SilentlyContinue
# Покажет PID
Get-Process -Id <PID>
```

```powershell
# Убить orphan uvicorn:
Stop-Process -Id <PID> -Force
```

Bash:

```bash
lsof -i:8086
# или: ss -tlnp | grep 8086
kill -9 <PID>
```

**Лечение**: убей процесс или поменяй `port` в `config.yaml`.

## DB locked

**Симптомы**: `sqlite3.OperationalError: database is locked`.

**Причины**:
- Долгий transaction в другом process'е.
- WAL не checkpoint'нулся.
- Какой-то external tool (DB Browser) держит exclusive lock.

**Диагностика**:

```powershell
# Кто держит файл?
handle.exe data\dreaming.db    # https://learn.microsoft.com/sysinternals/downloads/handle
```

Bash:

```bash
fuser data/dreaming.db
lsof data/dreaming.db
```

**Лечение**:
- Закрой DB Browser / sqlite-shell.
- WAL files: проверь `data/dreaming.db-wal` — если очень большой (> 100MB), сделай checkpoint:

```bash
sqlite3 data/dreaming.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

- Перезапусти сервис.

## /p/{slug}/ возвращает 404

**Симптомы**: страница говорит «Project not found» или «Project disabled».

**Причины** (см. [`project_resolver.py:18`](../dreaming/middleware/project_resolver.py)):
1. Проект с таким slug удалён.
2. `enabled=0`.

**Диагностика**:

```bash
sqlite3 data/dreaming.db "SELECT slug, enabled FROM projects"
```

В template `project_not_found.html` различается случай `is_disabled` vs «не существует»: смотри текст ошибки.

**Лечение**:
- Зайди на `/projects` → toggle.
- Или прямой SQL: `UPDATE projects SET enabled=1 WHERE slug='X'`.

## nightly_learning не сработал

**Симптомы**: ночь прошла, в БД нет sessions для проекта.

**Причины**:
1. `cron_enabled=false` (per-project через resolver).
2. Cron expression невалидный (тогда `register_project_jobs` молча пропустит, см. [`scheduler.py:198`](../dreaming/services/scheduler.py)).
3. Scheduler не стартовал.
4. Все агенты `enabled=0` или `next_agents_for_nightly` вернул пустой список.

**Диагностика**:

```bash
# Активные jobs:
sqlite3 data/dreaming.db "SELECT slug FROM projects WHERE enabled=1"
```

Логи:

```
INFO Scheduled job: nightly_learning_<slug>
INFO nightly_learning [<slug>]: N candidates
```

Если строки `nightly_learning [<slug>]: 0 candidates` — у тебя нет enabled-агентов в `agent_learning_rotation`.

**Лечение**:
- Проверь `/p/{slug}/settings` → `cron_enabled` (override = true) или global.
- Проверь cron expr: 5 полей, разделённых пробелом (`min hour day month dow`). `0 2 * * *` — каждый день в 02:00 UTC.
- Зайди на `/p/{slug}/rotation` — есть ли там enabled-агенты?

## AI Usage показывает 0 events

**Симптомы**: `/ai-usage` или `/p/{slug}/ai-usage` показывают «events_total: 0» или нули по моделям.

**Причины**:
1. `claude_projects_dir` указывает не туда (не `~/.claude/projects/`).
2. Claude никогда не запускался под этим юзером — нет JSONL файлов.
3. cwd в JSONL не совпадает с `working_dir` ни одного зарегистрированного проекта (тогда rows скипаются).

**Диагностика**:

```powershell
# Где живут Claude jsonl'ы?
Test-Path "$env:USERPROFILE\.claude\projects"
Get-ChildItem "$env:USERPROFILE\.claude\projects" -Recurse -Filter *.jsonl | Measure-Object
```

Bash:

```bash
ls -la ~/.claude/projects/
find ~/.claude/projects -name '*.jsonl' | wc -l
```

Лог ingest'а каждые 5 минут:

```
INFO ai_usage_ingest: files=42 inserted=18 skipped=2 errors=0 in 234ms
```

Если `inserted=0`, `skipped >> 0` — у тебя cwd-mismatch. Проверь что в JSONL реально стоит:

```powershell
Get-Content "$env:USERPROFILE\.claude\projects\<slug>\<session>.jsonl" | Select-Object -First 5
# найди "cwd": "..." и сверь с working_dir в БД
```

```bash
sqlite3 data/dreaming.db "SELECT slug, working_dir FROM projects"
```

**Лечение**: настрой `working_dir` в `projects` так, чтобы он 1-в-1 совпадал с реальным cwd Claude'а. Если запускаешь через WSL и Claude через Windows — пути будут разные (`/mnt/d/...` vs `D:\\...`).

## Jira кнопка отдаёт 400

**Симптомы**: жмёшь «Create Jira Task» в `/p/{slug}/ideas/...`, получаешь 400 с сообщением «Настройте Jira (email + API token) в /settings» или подобным.

**Причины** (см. [`jira.py:62`](../dreaming/services/jira.py)):
- `jira_email` или `jira_api_token` не задан.
- `jira_user_account_id` не задан.
- `jira_url` не задан.
- `jira_project_key` ни в global, ни в project_settings.

**Диагностика**:

```bash
sqlite3 data/dreaming.db "SELECT key, value FROM project_settings WHERE key LIKE 'jira_%'"
```

```bash
grep -E '^jira_' config.yaml
```

**Лечение**: открой `/settings`, заполни все 5 jira_* полей, сохрани.

Если конкретный проект должен использовать другой Jira project key — открой `/p/{slug}/settings`, override'ни `jira_project_key`.

## Orchestration page пустая

**Симптомы**: создал run через UI или curl, но `/p/{slug}/orchestration/{run_id}` показывает 0 nodes / 0 messages.

**Причины**:
1. Watcher (`ClaudeSessionTail`) не нашёл jsonl-файл — он не появился потому что claude не стартанул.
2. `working_dir` неверный — jsonl создаётся в неожиданном месте.
3. `claude_projects_dir` override указан неверно.

**Диагностика**:

В логах при start:

```
INFO orchestration_start_form: jsonl not yet visible for session <id>; backfill will recover
```

либо:

```
INFO tail_session_file: attach run=... node=... path=...
```

Если первое — watcher не нашёл и не запустил tail.

Найди файл вручную:

```powershell
Get-ChildItem "$env:USERPROFILE\.claude\projects" -Recurse -Filter "<external_id>.jsonl"
```

Если он есть — значит watcher не успел его увидеть. Запусти backfill:

```python
# Через REPL:
from dreaming.services.subagent_backfill import backfill_run
await backfill_run(run_id, db, hub)
```

Или используй `scripts/smoke_*.py` если есть подходящий.

**Лечение**:
- Проверь `working_dir` проекта — это должен быть **тот же путь**, откуда обычно запускается claude в этом проекте.
- Проверь что claude вообще стартанул: смотри `/p/{slug}/live` или `tasklist | findstr claude.cmd`.

## i18n показывает raw keys

**Симптомы**: на странице видишь `p.dashboard` вместо `Панель`.

**Причины**:
- Ключ есть в template, но нет в `messages_ru.json` (или EN).
- `messages_*.json` не загрузился (битый JSON).
- Locale cookie указывает на nonexistent locale.

**Диагностика**:

```bash
python scripts/check_i18n.py
# Покажет ключи which exist in one file but not the other.
```

Открой `dreaming/i18n/messages_ru.json` в IDE — она подсветит JSON syntax errors.

**Лечение**:
- Добавь ключ в **оба** файла (`messages_ru.json` И `messages_en.json`). Запусти `check_i18n.py` снова — должен exit 0.
- Если JSON битый — поправь синтаксис, перезапусти app.

## Mojibake на Cyrillic

**Симптомы**: Cyrillic читается как `Ð?Ñ?ÐµÐ¼Ð¸Ð¼ ÐµÐ³Ð¾`. JSON parser падает с `UnicodeDecodeError`.

**Причины**:
- Файл сохранён в UTF-16 LE (default PowerShell `Set-Content` в PS5.1).
- BOM присутствует там, где парсер его не ожидает.

**Диагностика** (PowerShell):

```powershell
$bytes = [IO.File]::ReadAllBytes("dreaming\i18n\messages_ru.json")
$bytes[0..3] -join ' '
# 255 254  -> UTF-16 LE BOM
# 239 187 191 -> UTF-8 BOM
# 123 ... -> начинается с {, нормально
```

**Лечение**:
- В PowerShell 5.1: `Out-File -Encoding utf8` всё равно добавляет BOM. Используй:
  ```powershell
  [IO.File]::WriteAllText("path", $content, [System.Text.UTF8Encoding]::new($false))
  ```
- В PowerShell 7+: `Out-File -Encoding utf8NoBOM`.
- В Bash/git-bash: `echo "..." > file` использует UTF-8 без BOM нативно.
- Или просто: используй Write tool из Claude Code — он пишет UTF-8 без BOM.

См. также [`development.md`](development.md) → encoding на Windows.

## Cross-references

- Логи и monitoring — [`deployment.md`](deployment.md).
- Конфиг — [`configuration.md`](configuration.md).
- Архитектура (понять, что куда дёргается) — [`architecture.md`](architecture.md).
